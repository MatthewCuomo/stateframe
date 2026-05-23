"""Serialize stateframe profiles for the notebook dataframe viewer."""

from __future__ import annotations

import math
import json
from typing import Any

import numpy as np
import pandas as pd

from stateframe.models import Profile


DEFAULT_MAX_ROWS = 25_000
NUMERIC_SEMANTIC_TYPES = {
    "numeric",
    "amount",
    "numeric-like",
    "percentage",
    "proportion",
    "numeric_discrete",
}
DATETIME_SEMANTIC_TYPES = {"datetime", "datetime-like"}


def build_viewer_payload(
    profile: Profile,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    height: int = 640,
    theme: str = "auto",
    title: str | None = None,
    include_cleaning: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe payload consumed by the anywidget frontend."""

    if max_rows <= 0:
        raise ValueError("max_rows must be greater than 0")

    df = profile.data
    display_df = df.head(max_rows)
    original_columns = list(display_df.columns)
    column_ids = [f"c{index}" for index in range(len(original_columns))]

    rows = [
        [_json_safe(value) for value in row]
        for row in display_df.itertuples(index=False, name=None)
    ]
    index_values = [_json_safe(value) for value in display_df.index.tolist()]

    recommendations = profile.recommendations().to_list()
    issues_by_column: dict[str, list[dict[str, Any]]] = {}
    for issue in profile.issue_list:
        issue_payload = issue.to_dict()
        for column in issue.columns:
            issues_by_column.setdefault(str(column), []).append(issue_payload)
    insights_by_column: dict[str, list[dict[str, Any]]] = {}
    for insight in profile.insight_list:
        insight_payload = insight.to_dict()
        for column in insight.columns:
            insights_by_column.setdefault(str(column), []).append(insight_payload)
    recommendations_by_column: dict[str, list[dict[str, Any]]] = {}
    for recommendation in recommendations:
        for column in recommendation.get("columns", []):
            recommendations_by_column.setdefault(str(column), []).append(recommendation)
    columns = [
        _column_payload(
            profile,
            df,
            column_id=column_id,
            source_name=source_name,
            display_name=str(source_name),
            position=position,
            issues=issues_by_column.get(str(source_name), []),
            insights=insights_by_column.get(str(source_name), []),
            recommendations=recommendations_by_column.get(str(source_name), []),
        )
        for position, (column_id, source_name) in enumerate(
            zip(column_ids, original_columns, strict=True)
        )
    ]

    payload = {
        "version": 1,
        "title": title or "stateframe dataframe explorer",
        "summary": _json_safe(profile.summary()),
        "view": {
            "height": int(height),
            "theme": theme,
            "row_count": int(df.shape[0]),
            "displayed_row_count": int(display_df.shape[0]),
            "column_count": int(df.shape[1]),
            "max_rows": int(max_rows),
            "truncated": bool(df.shape[0] > display_df.shape[0]),
            "target": profile.target,
            "time": profile.time,
            "goal": profile.goal,
            "mode": profile.mode,
        },
        "index": index_values,
        "columns": columns,
        "rows": rows,
        "issues": _json_safe([issue.to_dict() for issue in profile.issue_list]),
        "insights": _json_safe([insight.to_dict() for insight in profile.insight_list]),
        "recommendations": _json_safe(recommendations),
        "shapes": _json_safe([shape.to_dict() for shape in profile.shapes()]),
        "ledger": _json_safe(
            profile.ledger.to_dict(include_states=True, include_data=False)
            if getattr(profile, "ledger", None) is not None
            else None
        ),
        "suggested_config": _json_safe(
            profile.suggested_config.to_dict() if profile.suggested_config else None
        ),
    }
    if include_cleaning:
        payload["cleaning"] = _json_safe(_cleaning_payload(profile))
    return payload


def build_ledger_payload(
    profile: Profile,
    *,
    height: int = 640,
    title: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe payload for a focused analysis-tree view."""

    ledger = getattr(profile, "ledger", None)
    raw = (
        ledger.to_dict(include_states=True, include_data=False)
        if ledger is not None
        else {
            "root_entry_id": None,
            "active_entry_id": None,
            "entries": [],
            "tree": [],
            "states": {},
        }
    )
    entries = raw.get("entries") or []
    states = raw.get("states") or {}
    root_entry_id = raw.get("root_entry_id")
    active_entry_id = raw.get("active_entry_id")
    enriched_entries = _ledger_entries(entries, states, active_entry_id)
    active_path = _ledger_path(enriched_entries, active_entry_id)

    return {
        "version": 1,
        "title": title or "stateframe analysis tree",
        "view": {
            "height": int(height),
            "target": profile.target,
            "time": profile.time,
            "goal": profile.goal,
            "mode": profile.mode,
        },
        "summary": _json_safe(profile.summary()),
        "ledger": {
            "root_entry_id": root_entry_id,
            "active_entry_id": active_entry_id,
            "entries": _json_safe(enriched_entries),
            "tree": _json_safe(raw.get("tree") or []),
            "states": _json_safe(states),
            "active_path": _json_safe(active_path),
            "stats": _json_safe(_ledger_stats(enriched_entries, states)),
        },
        "recommendations": _json_safe(
            [recommendation.to_dict() for recommendation in profile.recommendations().top(12)]
        ),
        "shapes": _json_safe([shape.to_dict() for shape in profile.shapes()]),
    }


def initial_view_state(payload: dict[str, Any]) -> dict[str, Any]:
    """State shared between the frontend and Python kernel."""

    column_order = [column["id"] for column in payload["columns"]]
    widths = {
        column["id"]: _initial_width(column)
        for column in payload["columns"]
    }
    return {
        "columnOrder": column_order,
        "hiddenColumnIds": [],
        "sorts": [],
        "filters": {},
        "globalSearch": "",
        "selectedColumnId": column_order[0] if column_order else None,
        "showIndex": True,
        "widths": widths,
        "panelWidths": {
            "columns": 240,
            "inspector": 320,
        },
    }


def initial_ledger_state(payload: dict[str, Any]) -> dict[str, Any]:
    """State shared by focused analysis-tree launches."""

    ledger = payload.get("ledger") or {}
    entries = ledger.get("entries") or []
    entry_ids = {entry.get("id") for entry in entries}
    active_id = ledger.get("active_entry_id")
    selected = active_id if active_id in entry_ids else (entries[0].get("id") if entries else None)
    return {
        "selectedEntryId": selected,
        "search": "",
        "kindFilter": "all",
        "showOnlyStateful": False,
        "collapsedEntryIds": [],
    }


def apply_view_state(
    df: pd.DataFrame,
    payload: dict[str, Any],
    state: dict[str, Any] | None,
) -> pd.DataFrame:
    """Apply the synced viewer state to a DataFrame on the Python side."""

    if state is None:
        return df.copy()

    id_to_name = {
        column["id"]: column["source_name"]
        for column in payload.get("columns", [])
    }
    result = df.copy()

    global_search = str(state.get("globalSearch") or "").strip().lower()
    if global_search:
        mask = pd.Series(False, index=result.index)
        for name in id_to_name.values():
            if name in result:
                values = result[name].astype("string").str.lower()
                mask = mask | values.str.contains(global_search, na=False, regex=False)
        result = result[mask]

    filters = state.get("filters") or {}
    for column_id, filter_spec in filters.items():
        name = id_to_name.get(column_id)
        if name not in result or not isinstance(filter_spec, dict):
            continue
        result = _apply_filter(result, name, filter_spec)

    sorts = state.get("sorts") or []
    sort_columns: list[str] = []
    ascending: list[bool] = []
    for sort_spec in sorts:
        if not isinstance(sort_spec, dict):
            continue
        name = id_to_name.get(sort_spec.get("id"))
        direction = sort_spec.get("direction")
        if name in result and direction in {"asc", "desc"}:
            sort_columns.append(name)
            ascending.append(direction == "asc")
    if sort_columns:
        result = result.sort_values(sort_columns, ascending=ascending, na_position="last")

    hidden = set(state.get("hiddenColumnIds") or [])
    ordered_names = [
        id_to_name[column_id]
        for column_id in state.get("columnOrder", [])
        if column_id in id_to_name and column_id not in hidden
    ]
    if ordered_names:
        result = result[[name for name in ordered_names if name in result]]
    return result


def view_state_signature(
    payload: dict[str, Any],
    state: dict[str, Any] | None,
) -> str:
    """Return a stable signature for data-affecting viewer state."""

    normalized = _normalized_view_state(payload, state)
    data_affecting = {
        "column_order": normalized["column_order"],
        "hidden_columns": normalized["hidden_columns"],
        "sorts": normalized["sorts"],
        "filters": normalized["filters"],
        "global_search": normalized["global_search"],
    }
    return json.dumps(data_affecting, sort_keys=True, default=str)


def summarize_view_state(
    payload: dict[str, Any],
    state: dict[str, Any] | None,
    result: pd.DataFrame,
) -> dict[str, Any]:
    """Summarize a viewer state in ledger-friendly, column-name terms."""

    normalized = _normalized_view_state(payload, state)
    source_rows = int(payload.get("view", {}).get("row_count") or 0)
    source_columns = int(payload.get("view", {}).get("column_count") or 0)
    return _json_safe(
        {
            "source": "interactive_dataframe_viewer",
            "row_count": int(result.shape[0]),
            "column_count": int(result.shape[1]),
            "source_row_count": source_rows,
            "source_column_count": source_columns,
            "row_ratio": (int(result.shape[0]) / source_rows) if source_rows else 0.0,
            "column_order": normalized["column_order"],
            "hidden_columns": normalized["hidden_columns"],
            "sorts": normalized["sorts"],
            "filters": normalized["filters"],
            "global_search": normalized["global_search"],
            "selected_column": normalized["selected_column"],
        }
    )


def summarize_draft_state(
    payload: dict[str, Any],
    state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize unsaved viewer changes without applying them to the full data."""

    normalized = _normalized_view_state(payload, state)
    default_order = [column.get("source_name") for column in payload.get("columns", [])]
    changed_order = normalized["column_order"] != [str(name) for name in default_order]
    pills: list[dict[str, Any]] = []
    if normalized["filters"]:
        pills.append(
            {
                "kind": "filters",
                "label": f"{len(normalized['filters'])} filter"
                + ("" if len(normalized["filters"]) == 1 else "s"),
                "details": normalized["filters"],
            }
        )
    if normalized["global_search"]:
        pills.append(
            {
                "kind": "search",
                "label": f"search: {normalized['global_search']}",
                "details": normalized["global_search"],
            }
        )
    if normalized["sorts"]:
        pills.append(
            {
                "kind": "sorts",
                "label": f"{len(normalized['sorts'])} sort"
                + ("" if len(normalized["sorts"]) == 1 else "s"),
                "details": normalized["sorts"],
            }
        )
    if normalized["hidden_columns"]:
        pills.append(
            {
                "kind": "hidden_columns",
                "label": f"{len(normalized['hidden_columns'])} offloaded",
                "details": normalized["hidden_columns"],
            }
        )
    if changed_order:
        pills.append(
            {
                "kind": "column_order",
                "label": "reordered columns",
                "details": normalized["column_order"],
            }
        )
    return _json_safe(
        {
            "source": "interactive_dataframe_viewer",
            "has_changes": bool(pills),
            "pills": pills,
            "normalized": normalized,
        }
    )


def _ledger_entries(
    entries: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    active_entry_id: str | None,
) -> list[dict[str, Any]]:
    by_id = {entry.get("id"): entry for entry in entries}
    children: dict[str | None, list[str]] = {}
    for entry in entries:
        children.setdefault(entry.get("parent_id"), []).append(entry.get("id"))

    def depth_for(entry: dict[str, Any]) -> int:
        depth = 0
        parent_id = entry.get("parent_id")
        seen = {entry.get("id")}
        while parent_id and parent_id in by_id and parent_id not in seen:
            seen.add(parent_id)
            depth += 1
            parent_id = by_id[parent_id].get("parent_id")
        return depth

    result = []
    for entry in entries:
        entry_id = entry.get("id")
        state_id = entry.get("state_id")
        state = states.get(state_id) if state_id else None
        child_ids = [child_id for child_id in children.get(entry_id, []) if child_id]
        enriched = {
            **entry,
            "depth": depth_for(entry),
            "children_ids": child_ids,
            "child_count": len(child_ids),
            "is_leaf": len(child_ids) == 0,
            "is_active": entry_id == active_entry_id,
            "has_state": bool(state_id),
            "state": state,
            "path": _ledger_path_from_entries(by_id, entry_id),
        }
        result.append(enriched)
    return result


def _normalized_view_state(
    payload: dict[str, Any],
    state: dict[str, Any] | None,
) -> dict[str, Any]:
    state = state or {}
    columns = payload.get("columns", [])
    id_to_name = {
        column.get("id"): column.get("source_name")
        for column in columns
    }
    default_order = [column.get("id") for column in columns]
    ordered_ids = [
        column_id
        for column_id in state.get("columnOrder", default_order)
        if column_id in id_to_name
    ]
    ordered_ids.extend(
        column_id for column_id in default_order if column_id not in ordered_ids
    )
    hidden_ids = [
        column_id
        for column_id in state.get("hiddenColumnIds", [])
        if column_id in id_to_name
    ]
    selected_id = state.get("selectedColumnId")
    filters = {
        str(id_to_name[column_id]): dict(filter_spec)
        for column_id, filter_spec in (state.get("filters") or {}).items()
        if column_id in id_to_name and isinstance(filter_spec, dict)
    }
    sorts = [
        {
            "column": id_to_name.get(sort.get("id")),
            "direction": sort.get("direction"),
        }
        for sort in state.get("sorts", [])
        if isinstance(sort, dict)
        and sort.get("id") in id_to_name
        and sort.get("direction") in {"asc", "desc"}
    ]
    return {
        "column_order": [str(id_to_name[column_id]) for column_id in ordered_ids],
        "hidden_columns": [str(id_to_name[column_id]) for column_id in hidden_ids],
        "sorts": sorts,
        "filters": filters,
        "global_search": str(state.get("globalSearch") or ""),
        "selected_column": (
            str(id_to_name[selected_id]) if selected_id in id_to_name else None
        ),
    }


def _ledger_path(
    entries: list[dict[str, Any]],
    entry_id: str | None,
) -> list[dict[str, Any]]:
    by_id = {entry.get("id"): entry for entry in entries}
    return _ledger_path_from_entries(by_id, entry_id)


def _ledger_path_from_entries(
    by_id: dict[str | None, dict[str, Any]],
    entry_id: str | None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = entry_id
    while current and current in by_id and current not in seen:
        seen.add(current)
        entry = by_id[current]
        result.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "kind": entry.get("kind"),
                "operation": entry.get("operation"),
            }
        )
        current = entry.get("parent_id")
    return list(reversed(result))


def _ledger_stats(
    entries: list[dict[str, Any]],
    states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    kind_counts: dict[str, int] = {}
    for entry in entries:
        kind = str(entry.get("kind") or "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    return {
        "entry_count": len(entries),
        "state_count": len(states),
        "leaf_count": sum(1 for entry in entries if entry.get("is_leaf")),
        "max_depth": max((int(entry.get("depth") or 0) for entry in entries), default=0),
        "kind_counts": kind_counts,
        "materialized_state_count": sum(
            1 for state in states.values() if state.get("has_data")
        ),
    }


def _column_payload(
    profile: Profile,
    df: pd.DataFrame,
    *,
    column_id: str,
    source_name: Any,
    display_name: str,
    position: int,
    issues: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    column_profile = profile.column_profiles.get(source_name)
    if column_profile is None:
        column_profile = profile.column_profiles.get(display_name)

    if column_profile is None:
        semantic_type = "unknown"
        base: dict[str, Any] = {
            "name": display_name,
            "dtype": str(df[source_name].dtype),
            "semantic_type": semantic_type,
            "non_null_count": int(df[source_name].notna().sum()),
            "missing_count": int(df[source_name].isna().sum()),
            "missing_ratio": float(df[source_name].isna().mean()) if len(df) else 0.0,
            "distinct_count": int(df[source_name].nunique(dropna=True)),
            "distinct_ratio": (
                float(df[source_name].nunique(dropna=True) / len(df)) if len(df) else 0.0
            ),
            "metrics": {},
            "top_values": [],
            "role": "feature",
            "semantic_confidence": 0.0,
        }
    else:
        semantic_type = column_profile.semantic_type
        base = column_profile.to_dict()

    return _json_safe(
        {
            **base,
            "id": column_id,
            "source_name": source_name,
            "display_name": display_name,
            "position": position,
            "histogram": _numeric_histogram(df[source_name])
            if semantic_type in NUMERIC_SEMANTIC_TYPES
            else None,
            "datetime_range": _datetime_range(df[source_name])
            if semantic_type in DATETIME_SEMANTIC_TYPES
            else None,
            "issues": issues,
            "insights": insights,
            "recommendations": recommendations[:8],
        }
    )


def _cleaning_payload(profile: Profile) -> dict[str, Any]:
    try:
        return profile.cleaning_plan().operation_preview()
    except Exception:
        return {"action_count": 0, "actions": [], "catalog": []}


def _numeric_histogram(series: pd.Series, *, bins: int = 16) -> dict[str, Any] | None:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    if values.nunique(dropna=True) == 1:
        value = float(values.iloc[0])
        return {
            "bins": [{"lower": value, "upper": value, "count": int(values.shape[0])}],
            "max_count": int(values.shape[0]),
        }
    counts, edges = np.histogram(values.to_numpy(dtype=float), bins=bins)
    return {
        "bins": [
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "count": int(count),
            }
            for index, count in enumerate(counts)
        ],
        "max_count": int(max(counts)) if len(counts) else 0,
    }


def _datetime_range(series: pd.Series) -> dict[str, Any] | None:
    parsed = pd.to_datetime(series, errors="coerce").dropna()
    if parsed.empty:
        return None
    return {
        "min": _json_safe(parsed.min()),
        "max": _json_safe(parsed.max()),
        "non_null_count": int(parsed.shape[0]),
    }


def _apply_filter(
    df: pd.DataFrame,
    column: str,
    filter_spec: dict[str, Any],
) -> pd.DataFrame:
    kind = filter_spec.get("kind") or "text"
    series = df[column]

    if kind == "empty":
        mask = series.isna() | series.astype("string").str.strip().isin([""])
        return df[mask]
    if kind == "not_empty":
        mask = ~(series.isna() | series.astype("string").str.strip().isin([""]))
        return df[mask]
    if kind == "numeric":
        values = pd.to_numeric(series, errors="coerce")
        mask = pd.Series(True, index=df.index)
        if filter_spec.get("min") not in {None, ""}:
            mask = mask & (values >= float(filter_spec["min"]))
        if filter_spec.get("max") not in {None, ""}:
            mask = mask & (values <= float(filter_spec["max"]))
        return df[mask.fillna(False)]
    if kind == "datetime":
        values = pd.to_datetime(series, errors="coerce")
        mask = pd.Series(True, index=df.index)
        if filter_spec.get("min"):
            mask = mask & (values >= pd.to_datetime(filter_spec["min"], errors="coerce"))
        if filter_spec.get("max"):
            mask = mask & (values <= pd.to_datetime(filter_spec["max"], errors="coerce"))
        return df[mask.fillna(False)]

    value = str(filter_spec.get("value") or "").lower()
    if not value:
        return df
    mode = filter_spec.get("mode") or "contains"
    text = series.astype("string").str.lower()
    if mode == "equals":
        mask = text == value
    elif mode == "starts":
        mask = text.str.startswith(value, na=False)
    else:
        mask = text.str.contains(value, na=False, regex=False)
    return df[mask.fillna(False)]


def _initial_width(column: dict[str, Any]) -> int:
    name_width = len(str(column.get("display_name", ""))) * 9 + 42
    semantic_type = column.get("semantic_type")
    if semantic_type in NUMERIC_SEMANTIC_TYPES:
        return max(118, min(210, name_width))
    if semantic_type in DATETIME_SEMANTIC_TYPES:
        return max(172, min(240, name_width))
    if semantic_type in {"text", "json-like"}:
        return max(220, min(360, name_width))
    return max(136, min(260, name_width))


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(_json_safe(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        if np.isnat(value):
            return None
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.timedelta64):
        return str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
