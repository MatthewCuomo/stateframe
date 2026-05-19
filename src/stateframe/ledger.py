"""A lightweight ledger for recording an exploratory data science path."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LedgerState:
    """A dataframe state that can be checked out from the ledger."""

    id: str
    entry_id: str
    label: str
    row_count: int
    column_count: int
    memory_bytes: int
    columns: list[str] = field(default_factory=list)
    dtypes: dict[str, str] = field(default_factory=dict)
    data: pd.DataFrame | None = field(default=None, repr=False, compare=False)

    def to_dict(self, *, include_data: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "entry_id": self.entry_id,
            "label": self.label,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "memory_bytes": self.memory_bytes,
            "columns": list(self.columns),
            "dtypes": dict(self.dtypes),
            "has_data": self.data is not None,
        }
        if include_data and self.data is not None:
            result["data"] = self.data.to_dict(orient="records")
        return result


@dataclass(frozen=True)
class LedgerEntry:
    """One recorded operation, analysis, option point, or checkpoint."""

    id: str
    parent_id: str | None
    kind: str
    title: str
    operation: str
    timestamp: str
    state_id: str | None = None
    status: str = "completed"
    params: dict[str, Any] = field(default_factory=dict)
    columns: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    options: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    code: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "kind": self.kind,
            "title": self.title,
            "operation": self.operation,
            "timestamp": self.timestamp,
            "state_id": self.state_id,
            "status": self.status,
            "params": _json_safe(self.params),
            "columns": list(self.columns),
            "summary": _json_safe(self.summary),
            "metrics": _json_safe(self.metrics),
            "options": _json_safe(self.options),
            "artifacts": _json_safe(self.artifacts),
            "code": self.code,
            "note": self.note,
        }


class LensLedger:
    """Append-only-ish history for an ``stateframe`` profile.

    The ledger stores operation metadata for every recorded step and stores
    dataframe checkpoints only when explicitly asked. This keeps ordinary lens
    history cheap while still allowing users to jump back to named states.
    """

    def __init__(
        self,
        *,
        entries: list[LedgerEntry] | None = None,
        states: dict[str, LedgerState] | None = None,
        active_entry_id: str | None = None,
        root_entry_id: str | None = None,
    ) -> None:
        self.entries: list[LedgerEntry] = entries or []
        self.states: dict[str, LedgerState] = states or {}
        self.active_entry_id = active_entry_id
        self.root_entry_id = root_entry_id or (self.entries[0].id if self.entries else None)

    @classmethod
    def start(cls, profile: Any) -> "LensLedger":
        entry_id = _new_id("scan")
        state_id = _new_id("state")
        state = _state_from_frame(
            profile.data,
            state_id=state_id,
            entry_id=entry_id,
            label="initial scan data",
            copy_data=False,
        )
        entry = LedgerEntry(
            id=entry_id,
            parent_id=None,
            kind="scan",
            title="Initial stateframe scan",
            operation="scan",
            timestamp=_now(),
            state_id=state_id,
            params={
                "target": profile.target,
                "time": profile.time,
                "goal": profile.goal,
                "mode": profile.mode,
                "guidance": getattr(profile, "guidance", None),
            },
            summary=profile.summary(),
            metrics={
                "issue_count": len(profile.issue_list),
                "insight_count": len(profile.insight_list),
                "recommendation_count": len(profile.recommendation_list),
            },
            options=_recommendation_options(profile),
            code="scan = sf.scan(data)",
        )
        return cls(
            entries=[entry],
            states={state_id: state},
            active_entry_id=entry_id,
            root_entry_id=entry_id,
        )

    def record_lens(
        self,
        profile: Any,
        *,
        lens_id: str,
        params: dict[str, Any],
        result: Any,
        parent_id: str | None = None,
    ) -> LedgerEntry:
        parent = parent_id or self.active_entry_id
        entry = LedgerEntry(
            id=_new_id("lens"),
            parent_id=parent,
            kind="lens",
            title=getattr(result, "title", lens_id),
            operation=lens_id,
            timestamp=_now(),
            state_id=self._parent_state_id(parent),
            params=dict(params),
            columns=_columns_from_result(result),
            summary=_result_summary(result),
            metrics={
                "issue_count": len(getattr(result, "issues", []) or []),
                "recommendation_count": len(getattr(result, "recommendations", []) or []),
                "plot_count": len(getattr(result, "plots", []) or []),
            },
            options=_recommendation_options(profile),
            code=_lens_code(lens_id, params),
        )
        self.entries.append(entry)
        self.active_entry_id = entry.id
        return entry

    def record_state(
        self,
        data: pd.DataFrame,
        *,
        title: str,
        operation: str = "state.checkpoint",
        parent_id: str | None = None,
        params: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        options: list[dict[str, Any]] | None = None,
        code: str = "",
        note: str = "",
        copy_data: bool = True,
    ) -> LedgerEntry:
        parent = parent_id or self.active_entry_id
        entry_id = _new_id("state-entry")
        state_id = _new_id("state")
        state = _state_from_frame(
            data,
            state_id=state_id,
            entry_id=entry_id,
            label=title,
            copy_data=copy_data,
        )
        entry = LedgerEntry(
            id=entry_id,
            parent_id=parent,
            kind="state",
            title=title,
            operation=operation,
            timestamp=_now(),
            state_id=state_id,
            params=dict(params or {}),
            summary=summary or state.to_dict(include_data=False),
            options=list(options or []),
            code=code,
            note=note,
        )
        self.states[state_id] = state
        self.entries.append(entry)
        self.active_entry_id = entry.id
        return entry

    def record_artifact(
        self,
        *,
        title: str,
        kind: str = "artifact",
        operation: str | None = None,
        parent_id: str | None = None,
        artifact: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        code: str = "",
        note: str = "",
    ) -> LedgerEntry:
        """Record a non-dataframe branch output such as a plot or report."""

        clean_kind = str(kind or "artifact")
        parent = parent_id or self.active_entry_id
        entry = LedgerEntry(
            id=_new_id(clean_kind),
            parent_id=parent,
            kind=clean_kind,
            title=title,
            operation=operation or f"{clean_kind}.record",
            timestamp=_now(),
            state_id=self._parent_state_id(parent),
            params=dict(params or {}),
            summary=summary or {},
            metrics=metrics or {},
            artifacts=[_json_safe(artifact)] if artifact else [],
            code=code,
            note=note,
        )
        self.entries.append(entry)
        self.active_entry_id = entry.id
        return entry

    def record_note(
        self,
        title: str,
        note: str,
        *,
        parent_id: str | None = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            id=_new_id("note"),
            parent_id=parent_id or self.active_entry_id,
            kind="note",
            title=title,
            operation="note",
            timestamp=_now(),
            state_id=self._parent_state_id(parent_id or self.active_entry_id),
            note=note,
        )
        self.entries.append(entry)
        self.active_entry_id = entry.id
        return entry

    def checkout(self, entry_or_state_id: str) -> pd.DataFrame:
        """Return the dataframe checkpoint for an entry or state id."""

        state_id = entry_or_state_id
        if entry_or_state_id not in self.states:
            entry = self.get(entry_or_state_id)
            if entry.state_id is None:
                raise KeyError(f"Ledger entry has no dataframe state: {entry_or_state_id}")
            state_id = entry.state_id
        state = self.states[state_id]
        if state.data is None:
            raise ValueError(f"Ledger state was recorded without in-memory data: {state_id}")
        self.active_entry_id = state.entry_id
        return state.data.copy()

    def activate(self, entry_id: str) -> LedgerEntry:
        entry = self.get(entry_id)
        self.active_entry_id = entry.id
        return entry

    def attach_artifact(
        self,
        entry_id: str,
        artifact: dict[str, Any],
    ) -> LedgerEntry:
        """Attach an artifact record to an existing ledger entry."""

        for index, entry in enumerate(self.entries):
            if entry.id == entry_id:
                updated = replace(
                    entry,
                    artifacts=[*entry.artifacts, _json_safe(artifact)],
                )
                self.entries[index] = updated
                return updated
        raise KeyError(entry_id)

    def attach_state_artifact(
        self,
        entry_or_state_id: str,
        artifact: dict[str, Any],
    ) -> LedgerEntry:
        """Attach an artifact to the entry associated with a dataframe state."""

        if entry_or_state_id in self.states:
            entry_id = self.states[entry_or_state_id].entry_id
        else:
            entry = self.get(entry_or_state_id)
            if entry.state_id is None:
                raise KeyError(f"Ledger entry has no dataframe state: {entry_or_state_id}")
            entry_id = entry.id
        return self.attach_artifact(entry_id, artifact)

    def get(self, entry_id: str) -> LedgerEntry:
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        raise KeyError(entry_id)

    def children(self, entry_id: str | None) -> list[LedgerEntry]:
        return [entry for entry in self.entries if entry.parent_id == entry_id]

    def path(self, entry_id: str | None = None) -> list[LedgerEntry]:
        current = entry_id or self.active_entry_id
        by_id = {entry.id: entry for entry in self.entries}
        result: list[LedgerEntry] = []
        while current is not None and current in by_id:
            entry = by_id[current]
            result.append(entry)
            current = entry.parent_id
        return list(reversed(result))

    def tree(self) -> list[dict[str, Any]]:
        by_parent: dict[str | None, list[LedgerEntry]] = {}
        for entry in self.entries:
            by_parent.setdefault(entry.parent_id, []).append(entry)

        def build(parent_id: str | None) -> list[dict[str, Any]]:
            nodes = []
            for entry in by_parent.get(parent_id, []):
                payload = entry.to_dict()
                payload["children"] = build(entry.id)
                nodes.append(payload)
            return nodes

        return build(None)

    def to_dict(self, *, include_states: bool = False, include_data: bool = False) -> dict[str, Any]:
        return {
            "root_entry_id": self.root_entry_id,
            "active_entry_id": self.active_entry_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "tree": self.tree(),
            "states": {
                state_id: state.to_dict(include_data=include_data)
                for state_id, state in self.states.items()
            }
            if include_states
            else {},
        }

    def to_json(
        self,
        path: str | Path | None = None,
        *,
        indent: int = 2,
        include_states: bool = True,
        include_data: bool = False,
    ) -> str:
        text = json.dumps(
            self.to_dict(include_states=include_states, include_data=include_data),
            indent=indent,
            default=str,
        )
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def to_markdown(self, path: str | Path | None = None) -> str:
        lines = ["# stateframe Lens Ledger", ""]
        if self.active_entry_id:
            lines.append(f"- Active entry: `{self.active_entry_id}`")
        lines.append(f"- Entries: {len(self.entries)}")
        lines.append(f"- Dataframe states: {len(self.states)}")
        lines.extend(["", "## Tree"])
        self._append_tree_lines(lines, None, depth=0)
        lines.extend(["", "## Log"])
        for entry in self.entries:
            lines.append(f"### {entry.title}")
            lines.append(f"- ID: `{entry.id}`")
            if entry.parent_id:
                lines.append(f"- Parent: `{entry.parent_id}`")
            lines.append(f"- Kind: `{entry.kind}`")
            lines.append(f"- Operation: `{entry.operation}`")
            lines.append(f"- Time: {entry.timestamp}")
            if entry.state_id:
                lines.append(f"- State: `{entry.state_id}`")
            if entry.code:
                lines.append(f"- Code: `{entry.code}`")
            if entry.summary:
                compact = _compact_summary(entry.summary)
                if compact:
                    lines.append(f"- Summary: {compact}")
            if entry.options:
                lines.append("- Next options:")
                for option in entry.options[:6]:
                    lens = option.get("lens") or option.get("id")
                    title = option.get("title", lens)
                    score = option.get("score")
                    score_text = f" ({float(score):.2f})" if isinstance(score, (int, float)) else ""
                    lines.append(f"  - `{lens}` - {title}{score_text}")
            if entry.note:
                lines.append("")
                lines.append(entry.note)
            lines.append("")
        text = "\n".join(lines)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def _append_tree_lines(
        self,
        lines: list[str],
        parent_id: str | None,
        *,
        depth: int,
    ) -> None:
        for entry in self.children(parent_id):
            prefix = "  " * depth
            active = " **active**" if entry.id == self.active_entry_id else ""
            lines.append(f"{prefix}- `{entry.kind}` {entry.title} [`{entry.id}`]{active}")
            self._append_tree_lines(lines, entry.id, depth=depth + 1)

    def _parent_state_id(self, parent_id: str | None) -> str | None:
        if parent_id is None:
            return None
        by_id = {entry.id: entry for entry in self.entries}
        current = by_id.get(parent_id)
        while current is not None:
            if current.state_id is not None:
                return current.state_id
            current = by_id.get(current.parent_id) if current.parent_id else None
        return None


def _state_from_frame(
    data: pd.DataFrame,
    *,
    state_id: str,
    entry_id: str,
    label: str,
    copy_data: bool,
) -> LedgerState:
    frame = data.copy() if copy_data else data
    return LedgerState(
        id=state_id,
        entry_id=entry_id,
        label=label,
        row_count=int(frame.shape[0]),
        column_count=int(frame.shape[1]),
        memory_bytes=int(frame.memory_usage(deep=True).sum()),
        columns=[str(column) for column in frame.columns],
        dtypes={str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        data=frame,
    )


def _recommendation_options(profile: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    try:
        recommendations = profile.recommendations().top(limit)
    except Exception:
        return []
    return [
        {
            "id": rec.id,
            "title": rec.title,
            "lens": rec.lens,
            "score": rec.score,
            "cost": rec.cost,
            "category": rec.category,
            "columns": list(rec.columns),
            "code": rec.code,
        }
        for rec in recommendations
    ]


def _columns_from_result(result: Any) -> list[str]:
    data = getattr(result, "data", {}) or {}
    columns: list[str] = []
    if isinstance(data, dict):
        if isinstance(data.get("column"), str):
            columns.append(data["column"])
        if isinstance(data.get("columns"), list):
            columns.extend(str(column) for column in data["columns"])
        if isinstance(data.get("target"), str):
            columns.append(data["target"])
    return list(dict.fromkeys(columns))


def _result_summary(result: Any) -> dict[str, Any]:
    data = getattr(result, "data", {}) or {}
    if not isinstance(data, dict):
        return {"result_type": type(data).__name__}
    summary: dict[str, Any] = {}
    for key in [
        "column",
        "target",
        "total",
        "non_null_count",
        "action_count",
        "savings_bytes",
        "savings_ratio",
        "missing_cells",
    ]:
        if key in data:
            summary[key] = data[key]
    if not summary:
        summary["keys"] = list(data.keys())[:12]
    return summary


def _lens_code(lens_id: str, params: dict[str, Any]) -> str:
    args = [repr(lens_id)]
    for key, value in params.items():
        args.append(f"{key}={value!r}")
    return f"scan.run({', '.join(args)})"


def _compact_summary(summary: dict[str, Any]) -> str:
    parts = []
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            parts.append(f"{key}={value}")
        if len(parts) >= 6:
            break
    return ", ".join(parts)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
