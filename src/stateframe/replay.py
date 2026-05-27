"""Replay saved stateframe tree states from source metadata and operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class ReplayError(ValueError):
    """Raised when a saved tree path cannot be replayed deterministically."""


def replay_tree_state(
    tree_payload: dict[str, Any],
    *,
    workspace: Any | None = None,
    entry_id: str | None = None,
    source_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Replay a saved tree from its base source to a selected entry."""

    ledger = saved_ledger_payload(tree_payload)
    entries = list(ledger.get("entries") or [])
    if not entries:
        raise ReplayError("Saved tree has no ledger entries to replay.")

    selected = entry_id or ledger.get("active_entry_id") or ledger.get("root_entry_id")
    path = _entry_path(entries, selected)
    if not path:
        raise ReplayError(f"Unknown saved tree entry: {selected}")

    frame = load_source_frame(tree_payload, workspace=workspace, params=source_params)
    for entry in path[1:]:
        frame = replay_entry(frame, entry)
    return frame


def load_source_frame(
    tree_payload: dict[str, Any],
    *,
    workspace: Any | None = None,
    params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Load the replayable root source for a saved tree."""

    source = saved_source_payload(tree_payload)
    if source.get("kind") == "query":
        if not source.get("replayable", True):
            raise ReplayError("Saved query source is marked non-replayable.")
        statement = source.get("query")
        if not statement:
            raise ReplayError("Saved query source did not store query text.")
        source_id = source.get("source_id")
        if not source_id:
            raise ReplayError("Saved query source does not include a source id.")
        from stateframe import sources

        merged_params = dict(source.get("params") or {})
        merged_params.update(dict(params or {}))
        result = sources.query(
            str(source_id),
            str(statement),
            params=merged_params,
            store_query=bool(source.get("query_stored", True)),
            store_params=bool(source.get("params_stored", True)),
        )
        from stateframe.io import coerce_dataframe

        return coerce_dataframe(result.data)

    if source.get("kind") != "file":
        note = source.get("replay_note") or "Set a replayable source path for this tree."
        raise ReplayError(
            "Saved tree root is not file-backed, so it cannot be replayed from "
            f"metadata alone. {note}"
        )

    path = _resolve_source_path(source, workspace=workspace)
    if path is None or not path.exists():
        display = source.get("path") or source.get("absolute_path") or "<missing path>"
        raise ReplayError(
            f"Base data source does not exist at {display!r}. "
            "Update the tree source path, then try replay again."
        )

    from stateframe.io import read_table

    return read_table(path, **dict(source.get("reader_params") or {}))


def replay_entry(frame: pd.DataFrame, entry: dict[str, Any]) -> pd.DataFrame:
    """Replay one saved ledger entry against a parent dataframe."""

    kind = entry.get("kind")
    operation = str(entry.get("operation") or "")
    if kind in {"scan", "lens", "note"}:
        return frame

    viewer_summary = _viewer_summary(entry)
    if viewer_summary is not None:
        return apply_viewer_summary(frame, viewer_summary)

    custom_result = _replay_custom_python(frame, entry)
    if custom_result is not None:
        return custom_result

    if entry.get("state_id"):
        raise ReplayError(
            f"Cannot replay state-producing operation {operation!r}. "
            "Only viewer.pull-style operations are replayable right now unless "
            "the state has a saved data snapshot."
        )
    return frame


def _replay_custom_python(
    frame: pd.DataFrame,
    entry: dict[str, Any],
) -> pd.DataFrame | None:
    """Replay a custom user-code transform when it follows the stateframe contract."""

    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    custom = params.get("custom") if isinstance(params.get("custom"), dict) else {}
    if custom.get("kind") != "python":
        return None
    if custom.get("replayable") is False:
        raise ReplayError(
            f"Custom operation {entry.get('operation')!r} was recorded as non-replayable."
        )
    code = str(entry.get("code") or "").strip()
    if not code:
        raise ReplayError(
            f"Custom operation {entry.get('operation')!r} has no stored Python code."
        )

    input_variable = str(custom.get("input_variable") or "df")
    output_variable = str(custom.get("output_variable") or "output")
    namespace: dict[str, Any] = {
        "pd": pd,
        "np": np,
        input_variable: frame.copy(),
        "df": frame.copy(),
        "input_df": frame.copy(),
    }
    try:
        exec(code, namespace, namespace)
    except Exception as exc:
        raise ReplayError(
            f"Custom Python replay failed for {entry.get('title')!r}: {exc}"
        ) from exc

    for candidate in [output_variable, "output", "result"]:
        value = namespace.get(candidate)
        if isinstance(value, pd.DataFrame):
            return value
        if hasattr(value, "to_pandas"):
            converted = value.to_pandas()
            if isinstance(converted, pd.DataFrame):
                return converted
    raise ReplayError(
        "Custom Python replay code did not create a pandas DataFrame named "
        f"{output_variable!r}, 'output', or 'result'."
    )


def apply_viewer_summary(
    frame: pd.DataFrame,
    summary: dict[str, Any],
) -> pd.DataFrame:
    """Apply a saved normalized viewer operation summary."""

    result = frame.copy()

    global_search = str(summary.get("global_search") or "").strip().lower()
    if global_search:
        mask = pd.Series(False, index=result.index)
        for name in result.columns:
            values = result[name].astype("string").str.lower()
            mask = mask | values.str.contains(global_search, na=False, regex=False)
        result = result[mask]

    filters = summary.get("filters") or {}
    if isinstance(filters, dict):
        for column, filter_spec in filters.items():
            if column in result.columns and isinstance(filter_spec, dict):
                result = _apply_filter(result, str(column), filter_spec)

    sorts = summary.get("sorts") or []
    sort_columns: list[str] = []
    ascending: list[bool] = []
    if isinstance(sorts, list):
        for sort_spec in sorts:
            if not isinstance(sort_spec, dict):
                continue
            column = sort_spec.get("column")
            direction = sort_spec.get("direction")
            if column in result.columns and direction in {"asc", "desc"}:
                sort_columns.append(str(column))
                ascending.append(direction == "asc")
    if sort_columns:
        result = result.sort_values(sort_columns, ascending=ascending, na_position="last")

    hidden = {
        str(column)
        for column in (summary.get("hidden_columns") or [])
        if column in result.columns
    }
    if hidden:
        result = result.drop(columns=list(hidden), errors="ignore")

    column_order = [
        str(column)
        for column in (summary.get("column_order") or [])
        if column in result.columns and str(column) not in hidden
    ]
    if column_order:
        remaining = [
            str(column)
            for column in result.columns
            if str(column) not in column_order and str(column) not in hidden
        ]
        result = result[column_order + remaining]

    return result


def saved_ledger_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the saved ledger block from a tree payload."""

    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    ledger = profile.get("ledger") if isinstance(profile.get("ledger"), dict) else None
    if ledger is not None:
        return ledger
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    if profiles:
        first = profiles[0] if isinstance(profiles[0], dict) else {}
        ledger = first.get("ledger") if isinstance(first.get("ledger"), dict) else None
        if ledger is not None:
            return ledger
    return {"entries": [], "states": {}, "root_entry_id": None, "active_entry_id": None}


def saved_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the saved root source block from a tree payload."""

    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    source = profile.get("source") if isinstance(profile.get("source"), dict) else None
    if source is not None:
        return source
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    if profiles:
        first = profiles[0] if isinstance(profiles[0], dict) else {}
        source = first.get("source") if isinstance(first.get("source"), dict) else None
        if source is not None:
            return source
    return {}


def _viewer_summary(entry: dict[str, Any]) -> dict[str, Any] | None:
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    summary = params.get("viewer_summary")
    if isinstance(summary, dict):
        return summary
    summary = entry.get("summary")
    if isinstance(summary, dict) and summary.get("source") == "interactive_dataframe_viewer":
        return summary
    return None


def _entry_path(entries: list[dict[str, Any]], selected: str | None) -> list[dict[str, Any]]:
    by_id = {entry.get("id"): entry for entry in entries}
    if selected not in by_id:
        for entry in entries:
            if entry.get("state_id") == selected:
                selected = entry.get("id")
                break
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = selected
    while current and current in by_id and current not in seen:
        seen.add(str(current))
        entry = by_id[current]
        result.append(entry)
        current = entry.get("parent_id")
    return list(reversed(result))


def _resolve_source_path(source: dict[str, Any], *, workspace: Any | None) -> Path | None:
    source_path = source.get("path")
    if source_path and source.get("path_root") == "workspace" and workspace is not None:
        return workspace.resolve_path(Path(str(source_path)))

    candidates = [source.get("path"), source.get("absolute_path")]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if path.is_absolute() and path.exists():
            return path
        if workspace is not None:
            resolved = workspace.resolve_path(path)
            if resolved.exists():
                return resolved
        if path.exists():
            return path.resolve()
    first = next((item for item in candidates if item), None)
    if first and workspace is not None:
        return workspace.resolve_path(Path(str(first)))
    return Path(str(first)).expanduser() if first else None


def _apply_filter(
    frame: pd.DataFrame,
    column: str,
    filter_spec: dict[str, Any],
) -> pd.DataFrame:
    kind = filter_spec.get("kind") or "text"
    series = frame[column]

    if kind == "empty":
        mask = series.isna() | series.astype("string").str.strip().isin([""])
        return frame[mask]
    if kind == "not_empty":
        mask = ~(series.isna() | series.astype("string").str.strip().isin([""]))
        return frame[mask]
    if kind == "numeric":
        values = pd.to_numeric(series, errors="coerce")
        mask = pd.Series(True, index=frame.index)
        if filter_spec.get("min") not in {None, ""}:
            mask = mask & (values >= float(filter_spec["min"]))
        if filter_spec.get("max") not in {None, ""}:
            mask = mask & (values <= float(filter_spec["max"]))
        return frame[mask.fillna(False)]
    if kind == "datetime":
        values = pd.to_datetime(series, errors="coerce")
        mask = pd.Series(True, index=frame.index)
        if filter_spec.get("min"):
            mask = mask & (values >= pd.to_datetime(filter_spec["min"], errors="coerce"))
        if filter_spec.get("max"):
            mask = mask & (values <= pd.to_datetime(filter_spec["max"], errors="coerce"))
        return frame[mask.fillna(False)]

    value = str(filter_spec.get("value") or "").lower()
    if not value:
        return frame
    mode = filter_spec.get("mode") or "contains"
    text = series.astype("string").str.lower()
    if mode == "equals":
        mask = text == value
    elif mode == "starts":
        mask = text.str.startswith(value, na=False)
    else:
        mask = text.str.contains(value, na=False, regex=False)
    return frame[mask.fillna(False)]
