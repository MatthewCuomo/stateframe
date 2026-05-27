"""Reusable flow specs extracted from stateframe trees."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd


@dataclass
class FlowSpec:
    """A reusable path of stateframe work."""

    id: str
    name: str
    steps: list[dict[str, Any]]
    source: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    source_tree_id: str | None = None
    source_entry_id: str | None = None
    include: str = "selected_path"
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "kind": "stateframe_flow",
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "include": self.include,
            "source_tree_id": self.source_tree_id,
            "source_entry_id": self.source_entry_id,
            "source": _json_safe(self.source),
            "parameters": _json_safe(self.parameters),
            "steps": _json_safe(self.steps),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def save(self) -> "FlowSpec":
        save_flow(self)
        return self

    def run(
        self,
        input: Any | None = None,
        *,
        params: dict[str, Any] | None = None,
        name: str | None = None,
        snapshot: bool = False,
        save_tree: bool = True,
    ) -> "FlowRunResult":
        return run_flow(
            self,
            input,
            params=params,
            name=name,
            snapshot=snapshot,
            save_tree=save_tree,
        )


@dataclass
class FlowRunResult:
    """Result returned after running a reusable flow."""

    flow: FlowSpec
    profile: Any
    entries: list[Any]
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def final_entry(self) -> Any | None:
        return self.entries[-1] if self.entries else None

    @property
    def data(self) -> pd.DataFrame:
        if self.final_entry is not None and getattr(self.final_entry, "state_id", None):
            return self.profile.checkout(self.final_entry.id)
        return self.profile.data

    def web(self, **kwargs: Any):
        return self.profile.tree_view(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flow_id": self.flow.id,
            "flow_name": self.flow.name,
            "tree_id": getattr(self.profile, "tree_id", None),
            "tree_name": getattr(self.profile, "tree_name", None),
            "entry_ids": [entry.id for entry in self.entries],
            "final_entry_id": self.final_entry.id if self.final_entry is not None else None,
            "params": _json_safe(self.params),
        }


def from_tree(
    source: Any,
    *,
    name: str | None = None,
    entry_id: str | None = None,
    include: str = "selected_path",
    parameters: dict[str, Any] | list[str] | tuple[str, ...] | None = None,
    description: str = "",
    save: bool = True,
) -> FlowSpec:
    """Promote a selected tree path into a reusable flow."""

    if include != "selected_path":
        raise NotImplementedError("Only include='selected_path' is currently supported.")

    tree_payload, selected_entry_id, tree_record = _tree_payload_from_source(source, entry_id=entry_id)
    ledger = _saved_ledger_payload(tree_payload)
    entries = [entry for entry in ledger.get("entries", []) or [] if isinstance(entry, dict)]
    selected = selected_entry_id or ledger.get("active_entry_id") or ledger.get("root_entry_id")
    path = _entry_path(entries, str(selected) if selected else None)
    if not path:
        raise ValueError("No selected tree path is available to save as a flow.")

    root = path[0]
    flow_name = name or f"{tree_payload.get('tree_name') or tree_record.get('tree_name') or 'stateframe'} flow"
    flow = FlowSpec(
        id=_new_id("flow"),
        name=flow_name,
        description=description,
        include=include,
        source_tree_id=str(tree_payload.get("tree_id") or tree_record.get("tree_id") or ""),
        source_entry_id=str(path[-1].get("id") or ""),
        source=dict(_saved_source_payload(tree_payload)),
        parameters=_normalize_parameters(parameters, _saved_source_payload(tree_payload)),
        steps=[
            _step_from_entry(entry)
            for entry in path[1:]
            if _is_flow_step(entry)
        ],
    )
    if root.get("id"):
        flow.source["root_entry_id"] = root.get("id")
    if save:
        save_flow(flow)
    return flow


def save_flow(flow: FlowSpec | dict[str, Any]) -> FlowSpec:
    """Persist a flow spec under the active workspace."""

    spec = flow if isinstance(flow, FlowSpec) else _flow_from_dict(flow)
    spec.updated_at = _now()
    path = flow_path(spec.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec.to_dict(), indent=2, default=str), encoding="utf-8")
    return spec


def load_flow(reference: str) -> FlowSpec:
    """Load a saved flow by id or name."""

    ref = str(reference)
    for record in list_flows():
        if ref in {str(record.get("id")), str(record.get("name")), _slug(record.get("name"))}:
            path = Path(record["path"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _flow_from_dict(payload)
    raise KeyError(f"Unknown stateframe flow: {reference}")


def list_flows() -> list[dict[str, Any]]:
    """List saved reusable flows in the active workspace."""

    result = []
    for path in sorted(flows_dir().glob("*/flow.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        result.append(
            {
                "id": payload.get("id"),
                "name": payload.get("name"),
                "description": payload.get("description") or "",
                "step_count": len(payload.get("steps") or []),
                "source_tree_id": payload.get("source_tree_id"),
                "source_entry_id": payload.get("source_entry_id"),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
                "path": str(path),
            }
        )
    return result


def run_flow(
    flow: FlowSpec | str,
    input: Any | None = None,
    *,
    params: dict[str, Any] | None = None,
    name: str | None = None,
    snapshot: bool = False,
    save_tree: bool = True,
) -> FlowRunResult:
    """Run a saved flow against a new dataframe, profile, web selection, or source."""

    spec = load_flow(flow) if isinstance(flow, str) else flow
    run_params = dict(params or {})
    profile = _profile_for_run(spec, input, params=run_params, name=name, snapshot=snapshot)
    if getattr(profile, "ledger", None) is None:
        from stateframe.ledger import LensLedger

        profile.ledger = LensLedger.start(profile)
    parent_id = profile.ledger.active_entry_id
    current = profile.checkout(parent_id) if parent_id else profile.data
    created_entries: list[Any] = []

    for step in spec.steps:
        entry = dict(step.get("entry") or {})
        if not entry:
            continue
        if _state_entry(entry):
            from stateframe.replay import replay_entry

            current = replay_entry(current, entry)
            recorded = profile.record_state(
                current,
                title=str(entry.get("title") or step.get("title") or "Flow step"),
                operation=str(entry.get("operation") or "flow.step"),
                parent_id=parent_id,
                code=str(entry.get("code") or ""),
                note=str(entry.get("note") or ""),
                flow={
                    "id": spec.id,
                    "name": spec.name,
                    "source_entry_id": entry.get("id"),
                },
                original_params=dict(entry.get("params") or {}),
            )
            created_entries.append(recorded)
            parent_id = recorded.id
            if snapshot:
                _save_entry_data(profile, recorded, recorded.title)
            continue
        if _code_leaf_entry(entry):
            recorded = _run_code_leaf_step(
                profile,
                parent_id=parent_id,
                current=current,
                entry=entry,
                flow=spec,
                snapshot=snapshot,
            )
            if recorded is not None:
                created_entries.append(recorded)
            continue
        if _output_entry(entry):
            recorded = profile.record_artifact(
                title=str(entry.get("title") or "Flow artifact"),
                kind=str(entry.get("kind") or "artifact"),
                operation=str(entry.get("operation") or "flow.artifact"),
                parent_id=parent_id,
                artifact={
                    "kind": str(entry.get("kind") or "artifact"),
                    "format": "stateframe.flow.copied_artifact.v1",
                    "source_flow_id": spec.id,
                    "source_entry_id": entry.get("id"),
                    "artifacts": list(entry.get("artifacts") or []),
                },
                code=str(entry.get("code") or ""),
                note=str(entry.get("note") or ""),
                flow={"id": spec.id, "name": spec.name},
            )
            created_entries.append(recorded)

    if save_tree and hasattr(profile, "save_tree"):
        profile.save_tree()
    return FlowRunResult(flow=spec, profile=profile, entries=created_entries, params=run_params)


def flows_dir() -> Path:
    from stateframe import workspace

    return workspace.current().metadata_dir / "flows"


def flow_path(flow_id: str) -> Path:
    return flows_dir() / _slug(flow_id) / "flow.json"


def _profile_for_run(
    flow: FlowSpec,
    input: Any | None,
    *,
    params: dict[str, Any],
    name: str | None,
    snapshot: bool,
) -> Any:
    if input is None:
        source = flow.source or {}
        if source.get("kind") == "query":
            from stateframe import query

            merged_params = dict(source.get("params") or {})
            merged_params.update(params)
            return query(
                str(source.get("source_id") or ""),
                str(source.get("query") or ""),
                params=merged_params,
                name=name or f"{flow.name} run",
                save_tree=True,
                save_result=snapshot,
                store_query=bool(source.get("query_stored", True)),
                store_params=bool(source.get("params_stored", True)),
            )
        if source.get("kind") == "file" and source.get("path"):
            from stateframe import scan_path

            return scan_path(
                str(source.get("path")),
                name=name or f"{flow.name} run",
                reader_params=dict(source.get("reader_params") or {}),
            )
        raise ValueError("Flow has no runnable source. Pass a dataframe, profile, or web selection.")

    if hasattr(input, "selected_profile") and hasattr(input, "selected_entry_id"):
        return input.selected_profile()
    if hasattr(input, "column_profiles") and hasattr(input, "data"):
        return input
    if isinstance(input, pd.DataFrame) or hasattr(input, "to_pandas"):
        from stateframe import scan

        return scan(input, name=name or f"{flow.name} run")
    raise TypeError("run_flow input must be a DataFrame, Profile, web selection, or None for a runnable source.")


def _run_code_leaf_step(
    profile: Any,
    *,
    parent_id: str | None,
    current: pd.DataFrame,
    entry: dict[str, Any],
    flow: FlowSpec,
    snapshot: bool,
) -> Any | None:
    code = str(entry.get("code") or "").strip()
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    cell_meta = params.get("cell") if isinstance(params.get("cell"), dict) else {}
    replay_code = str(cell_meta.get("replay_code") or code).strip()
    if not replay_code:
        return None
    from stateframe.cell import run_cell

    namespace = {"df": current.copy()}
    return run_cell(
        replay_code,
        source=profile,
        parent=parent_id,
        name=str(entry.get("title") or "Flow code cell"),
        save=snapshot,
        namespace=namespace,
    )


def _tree_payload_from_source(source: Any, *, entry_id: str | None) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
    if hasattr(source, "load_selected_tree") and hasattr(source, "selected_entry_id"):
        return source.load_selected_tree(), entry_id or source.selected_entry_id(), source.selected_tree_record() or {}
    if hasattr(source, "ledger") and hasattr(source, "save_tree"):
        result = source.save_tree()
        from stateframe import workspace

        return workspace.current().load_tree(getattr(source, "tree_id", "")), entry_id or source.ledger.active_entry_id, {
            "tree_id": getattr(source, "tree_id", None),
            "tree_name": getattr(source, "tree_name", None),
            "tree_path": str(result.path),
        }
    if isinstance(source, str):
        from stateframe import workspace

        record = workspace.current().resolve_tree(source)
        return workspace.current().load_tree(str(record["tree_id"])), entry_id, record
    raise TypeError("from_tree expects a Profile, workspace web/tree object, or tree id/name.")


def _step_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    return {
        "kind": "ledger_entry",
        "entry_id": entry.get("id"),
        "title": entry.get("title"),
        "operation": entry.get("operation"),
        "entry": _json_safe(entry),
        "dependencies": _json_safe(params.get("dependencies") or []),
    }


def _normalize_parameters(
    parameters: dict[str, Any] | list[str] | tuple[str, ...] | None,
    source: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(parameters, dict):
        return dict(parameters)
    names = list(parameters or source.get("param_names") or [])
    result = {}
    source_params = source.get("params") if isinstance(source.get("params"), dict) else {}
    for name in names:
        result[str(name)] = {
            "name": str(name),
            "default": source_params.get(name),
            "required": str(name) not in source_params,
        }
    return result


def _flow_from_dict(payload: dict[str, Any]) -> FlowSpec:
    return FlowSpec(
        id=str(payload.get("id") or _new_id("flow")),
        name=str(payload.get("name") or "stateframe flow"),
        description=str(payload.get("description") or ""),
        include=str(payload.get("include") or "selected_path"),
        source_tree_id=payload.get("source_tree_id"),
        source_entry_id=payload.get("source_entry_id"),
        source=dict(payload.get("source") or {}),
        parameters=dict(payload.get("parameters") or {}),
        steps=list(payload.get("steps") or []),
        created_at=str(payload.get("created_at") or _now()),
        updated_at=str(payload.get("updated_at") or _now()),
    )


def _is_flow_step(entry: dict[str, Any]) -> bool:
    return bool(_state_entry(entry) or _code_leaf_entry(entry) or _output_entry(entry))


def _state_entry(entry: dict[str, Any]) -> bool:
    return bool(entry.get("state_id"))


def _code_leaf_entry(entry: dict[str, Any]) -> bool:
    return str(entry.get("kind") or "") == "code_leaf"


def _output_entry(entry: dict[str, Any]) -> bool:
    return bool(entry.get("artifacts")) and not _state_entry(entry)


def _saved_ledger_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from stateframe.replay import saved_ledger_payload

    return saved_ledger_payload(payload)


def _saved_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from stateframe.replay import saved_source_payload

    return saved_source_payload(payload)


def _entry_path(entries: list[dict[str, Any]], selected: str | None) -> list[dict[str, Any]]:
    by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    if selected not in by_id:
        for entry in entries:
            if entry.get("state_id") == selected:
                selected = str(entry.get("id"))
                break
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = str(selected or "")
    while current and current in by_id and current not in seen:
        seen.add(current)
        entry = by_id[current]
        result.append(entry)
        current = str(entry.get("parent_id") or "")
    return list(reversed(result))


def _save_entry_data(profile: Any, entry: Any, name: str | None) -> None:
    from stateframe import save as save_api

    save_api.data(
        profile,
        entry_id=entry.id,
        name=name or entry.title,
        also_save_tree=False,
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: Any) -> str:
    text = str(value or "stateframe").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text or "stateframe"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


__all__ = [
    "FlowRunResult",
    "FlowSpec",
    "flow_path",
    "flows_dir",
    "from_tree",
    "list_flows",
    "load_flow",
    "run_flow",
    "save_flow",
]
