"""Notebook widget for the stateframe workspace web."""

from __future__ import annotations

from dataclasses import MISSING, replace
from pathlib import Path
from typing import Any

import pandas as pd

from stateframe.interactive.serialize import (
    _json_safe,
    apply_view_state,
    build_viewer_payload,
    initial_view_state,
    summarize_view_state,
)


ASSET_DIR = Path(__file__).with_name("assets")


class WorkspaceWebDependencyError(ImportError):
    """Raised when widget dependencies are not importable."""


try:
    import anywidget
    import traitlets
except ModuleNotFoundError:  # pragma: no cover - exercised through web_view()
    anywidget = None
    traitlets = None


if anywidget is not None and traitlets is not None:

    class WorkspaceWebViewer(anywidget.AnyWidget):
        """Interactive notebook navigator for a workspace's saved trees."""

        _esm = ASSET_DIR / "workspace_web.js"
        _css = ASSET_DIR / "workspace_web.css"

        payload = traitlets.Dict().tag(sync=True)
        state = traitlets.Dict().tag(sync=True)
        viewer = traitlets.Dict(default_value={}).tag(sync=True)
        command = traitlets.Dict(default_value={}).tag(sync=True)
        command_status = traitlets.Dict(default_value={}).tag(sync=True)

        def __init__(
            self,
            *,
            height: int = 640,
            title: str | None = None,
            **kwargs: Any,
        ) -> None:
            from stateframe import workspace

            self._workspace = workspace.current()
            self._embedded_view_profile = None
            self._embedded_record_profile = None
            self._embedded_parent_id: str | None = None
            self._last_command_nonce: Any = None
            payload = build_web_payload(self._workspace, height=height, title=title)
            super().__init__(
                payload=payload,
                state=initial_web_state(payload),
                viewer={},
                command={},
                command_status={},
                **kwargs,
            )

        @property
        def workspace(self):
            """The stateframe workspace backing this web view."""

            return self._workspace

        def current_state(self) -> dict[str, Any]:
            """Return the latest synced widget state."""

            return dict(self.state)

        def selected_tree_id(self) -> str | None:
            """Return the selected tree id."""

            selected = self.state.get("selectedTreeId")
            return str(selected) if selected else None

        def selected_tree_record(self) -> dict[str, Any] | None:
            """Return the selected tree's web record."""

            selected = self.selected_tree_id()
            if selected is None:
                return None
            for record in self.payload.get("trees", []):
                if record.get("tree_id") == selected:
                    return dict(record)
            return None

        def selected_tree_detail(self) -> dict[str, Any]:
            """Return the selected tree's embedded ledger detail."""

            record = self.selected_tree_record()
            if record is None:
                raise ValueError("No workspace tree is selected.")
            detail = record.get("tree_detail")
            if isinstance(detail, dict):
                return dict(detail)
            payload = self.load_selected_tree()
            return _tree_detail_from_payload(self._workspace, record, payload)

        def load_selected_tree(self) -> dict[str, Any]:
            """Load the saved tree metadata for the selected tree."""

            record = self.selected_tree_record()
            if record is None:
                raise ValueError("No workspace tree is selected.")
            return self._workspace.load_tree(str(record["tree_id"]))

        def selected_entry_id(self) -> str | None:
            """Return the selected entry id inside the selected tree."""

            detail = self.selected_tree_detail()
            entry_ids = {entry.get("id") for entry in detail.get("entries", [])}
            selected = self.state.get("selectedEntryId")
            if selected in entry_ids:
                return str(selected)
            fallback = _default_entry_id_from_detail(detail)
            return str(fallback) if fallback else None

        def selected_entry_record(self) -> dict[str, Any] | None:
            """Return the selected saved ledger entry, if any."""

            selected = self.selected_entry_id()
            if selected is None:
                return None
            for entry in self.selected_tree_detail().get("entries", []):
                if entry.get("id") == selected:
                    return dict(entry)
            return None

        def selected_state_id(self) -> str | None:
            """Return the dataframe state id for the selected entry."""

            entry = self.selected_entry_record()
            state_id = entry.get("state_id") if entry else None
            return str(state_id) if state_id else None

        def selected_state_metadata(self) -> dict[str, Any] | None:
            """Return saved metadata for the selected dataframe state."""

            state_id = self.selected_state_id()
            if state_id is None:
                return None
            state = self.selected_tree_detail().get("states", {}).get(state_id)
            return dict(state) if isinstance(state, dict) else None

        def pull_selected(self) -> pd.DataFrame:
            """Load the selected state into the notebook as a DataFrame.

            Saved Parquet snapshots are used when available. Otherwise stateframe
            replays the saved path from the tree's editable base source path.
            """

            entry = self.selected_entry_record()
            if entry is None:
                raise ValueError("No tree entry is selected.")
            state = self.selected_state_metadata()
            artifact = _data_snapshot_artifact(entry)
            if artifact is not None:
                path = _artifact_path(self._workspace, artifact)
                from stateframe.save import load_data

                return _attach_selected_context(
                    load_data(path),
                    workspace=self._workspace,
                    tree_record=self.selected_tree_record(),
                    entry=entry,
                    state=state,
                )

            if state is not None and isinstance(state.get("data"), list):
                return _attach_selected_context(
                    pd.DataFrame(state["data"]),
                    workspace=self._workspace,
                    tree_record=self.selected_tree_record(),
                    entry=entry,
                    state=state,
                )

            replay_error = None
            try:
                from stateframe.replay import replay_tree_state

                return _attach_selected_context(
                    replay_tree_state(
                        self.load_selected_tree(),
                        workspace=self._workspace,
                        entry_id=str(entry["id"]),
                    ),
                    workspace=self._workspace,
                    tree_record=self.selected_tree_record(),
                    entry=entry,
                    state=state,
                )
            except Exception as exc:
                if exc.__class__.__name__ != "ReplayError":
                    raise
                replay_error = exc

            raise ValueError(_missing_snapshot_message(entry, self.selected_tree_record(), replay_error))

        def checkout_selected(self) -> pd.DataFrame:
            """Alias for ``pull_selected`` to match the tree widget API."""

            return self.pull_selected()

        def pull(self) -> pd.DataFrame:
            """Alias for ``pull_selected`` for the unified web workflow."""

            return self.pull_selected()

        def selected_profile(self):
            """Return a live profile restored around the selected state.

            The returned profile keeps the saved ledger metadata and stable
            tree id, so new viewer pulls can branch from the selected node and
            later be saved back into the same workspace tree.
            """

            data = self.pull_selected()
            tree_payload = self.load_selected_tree()
            record = self.selected_tree_record() or {}
            entry_id = self.selected_entry_id()
            state_id = self.selected_state_id()
            profile_payload = _saved_profile_payload(tree_payload)

            from stateframe.profile import build_profile

            profile = build_profile(
                data,
                name=record.get("dataset_name") or record.get("tree_name"),
                target=_valid_column(profile_payload.get("target"), data),
                time=_valid_column(profile_payload.get("time"), data),
                goal=profile_payload.get("goal") or "first-look",
                mode=profile_payload.get("mode") or "standard",
                register=False,
            )
            profile.dataset_name = record.get("dataset_name") or profile_payload.get("dataset_name")
            profile.tree_name = record.get("tree_name") or profile_payload.get("tree_name")
            profile.source = dict(profile_payload.get("source") or record.get("source") or {})
            profile.profile_id = profile_payload.get("profile_id") or profile.profile_id
            profile.workspace_summary = dict(record.get("summary") or {})
            profile.workspace_source_fingerprint = record.get("source_fingerprint")
            profile.ledger = _ledger_from_saved_payload(
                tree_payload,
                selected_entry_id=entry_id,
                selected_state_id=state_id,
                selected_data=data,
            )
            profile.tree_id = record.get("tree_id")
            return profile

        def view_selected(
            self,
            *,
            max_rows: int = 25_000,
            height: int = 640,
            theme: str = "auto",
            title: str | None = None,
        ):
            """Open the selected saved state in a dataframe viewer."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No tree entry is selected.")
            record_profile = self.selected_profile()
            data = record_profile.checkout(selected)

            from stateframe.interactive.viewer import DataFrameViewer
            from stateframe.profile import build_profile

            view_profile = build_profile(
                data,
                name=record_profile.dataset_name,
                target=record_profile.target if record_profile.target in data.columns else None,
                time=record_profile.time if record_profile.time in data.columns else None,
                goal=record_profile.goal,
                mode=record_profile.mode,
                register=False,
            )
            return DataFrameViewer(
                view_profile,
                record_profile=record_profile,
                ledger_parent_id=selected,
                max_rows=max_rows,
                height=height,
                theme=theme,
                title=title or _selected_view_title(self.selected_entry_record()),
            )

        def open_selected_viewer(
            self,
            *,
            max_rows: int | str | None = 500,
            height: int | None = None,
            theme: str = "auto",
            title: str | None = None,
            initial_state: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Hydrate the selected data state into the embedded web viewer."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No tree entry is selected.")
            record_profile = self.selected_profile()
            data = record_profile.checkout(selected)
            resolved_max_rows = _resolve_viewer_max_rows(max_rows, data)

            from stateframe.profile import build_profile

            view_profile = build_profile(
                data,
                name=record_profile.dataset_name,
                target=record_profile.target if record_profile.target in data.columns else None,
                time=record_profile.time if record_profile.time in data.columns else None,
                goal=record_profile.goal,
                mode=record_profile.mode,
                register=False,
            )
            view_height = height or int(self.payload.get("view", {}).get("height") or 640)
            viewer_payload = build_viewer_payload(
                view_profile,
                max_rows=resolved_max_rows,
                height=view_height,
                theme=theme,
                title=title or _selected_view_title(self.selected_entry_record()),
            )
            viewer_payload["context"] = _json_safe(
                {
                    "tree_id": self.selected_tree_id(),
                    "tree_name": (self.selected_tree_record() or {}).get("tree_name"),
                    "entry_id": selected,
                    "state_id": self.selected_state_id(),
                    "entry_title": (self.selected_entry_record() or {}).get("title"),
                }
            )
            self._embedded_record_profile = record_profile
            self._embedded_view_profile = view_profile
            self._embedded_parent_id = selected
            self.viewer = {
                "status": "ready",
                "payload": viewer_payload,
                "state": _viewer_state_for_payload(viewer_payload, initial_state),
                "message": "",
                "preview": {
                    "displayed_rows": int(viewer_payload.get("view", {}).get("displayed_row_count") or 0),
                    "total_rows": int(viewer_payload.get("view", {}).get("row_count") or 0),
                    "is_full": not bool(viewer_payload.get("view", {}).get("truncated")),
                },
            }
            self.state = {
                **dict(self.state),
                "viewMode": "viewer",
                "selectedTreeId": self.selected_tree_id(),
                "selectedEntryId": selected,
            }
            return self.viewer

        def save_embedded_viewer_branch(
            self,
            *,
            name: str | None = None,
            message: str | None = None,
            note: str | None = None,
            viewer_state: dict[str, Any] | None = None,
            operation: str = "web.viewer.save_branch",
        ):
            """Save the embedded viewer's current UI-shaped state as a branch."""

            if self._embedded_view_profile is None or self._embedded_record_profile is None:
                self.open_selected_viewer()
            if self._embedded_view_profile is None or self._embedded_record_profile is None:
                raise ValueError("No embedded viewer state is available to save.")

            current_viewer = dict(self.viewer or {})
            viewer_payload = current_viewer.get("payload") or {}
            state = viewer_state or current_viewer.get("state") or initial_view_state(viewer_payload)
            result = apply_view_state(self._embedded_view_profile.data, viewer_payload, state)
            summary = summarize_view_state(viewer_payload, state, result)
            if name:
                summary["output_name"] = name
            if message:
                summary["message"] = message

            from stateframe.interactive.viewer import _pull_title, _state_options

            entry = self._embedded_record_profile.record_state(
                result,
                title=_pull_title(name),
                operation=operation,
                parent_id=self._embedded_parent_id,
                note=note or message or "",
                options=_state_options(self._embedded_record_profile, result),
                viewer_state=dict(state),
                viewer_summary=summary,
                output_name=name,
                message=message,
            )
            self._embedded_record_profile.save_tree()
            self._refresh_after_embedded_save(entry.id)
            self.command_status = {
                "status": "saved",
                "action": "save_viewer_branch",
                "entry_id": entry.id,
                "title": entry.title,
                "message": message or "",
            }
            return entry

        def set_selected_tree_source_path(
            self,
            path: str | Path,
            *,
            reader_params: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Update the selected tree's editable base data path."""

            record = self.selected_tree_record()
            if record is None:
                raise ValueError("No workspace tree is selected.")
            updated = self._workspace.update_tree_source_path(
                str(record["tree_id"]),
                path,
                reader_params=reader_params,
            )
            self.refresh()
            return updated

        def update_selected_tree_source_path(
            self,
            path: str | Path,
            *,
            reader_params: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Alias for ``set_selected_tree_source_path``."""

            return self.set_selected_tree_source_path(
                path,
                reader_params=reader_params,
            )

        def refresh(self) -> None:
            """Reload the workspace web payload from disk."""

            previous_tree = self.selected_tree_id()
            try:
                previous_entry = self.selected_entry_id()
            except ValueError:
                previous_entry = None
            payload = build_web_payload(
                self._workspace,
                height=int(self.payload.get("view", {}).get("height") or 640),
                title=self.payload.get("title"),
            )
            self.payload = payload
            self.state = initial_web_state(
                payload,
                selected_tree_id=previous_tree,
                selected_entry_id=previous_entry,
            )

        @traitlets.observe("command")
        def _observe_command(self, change: Any) -> None:
            request = change.get("new") or {}
            if not isinstance(request, dict):
                return
            nonce = request.get("nonce")
            if not nonce or nonce == self._last_command_nonce:
                return
            self._last_command_nonce = nonce
            action = str(request.get("action") or "")
            try:
                if action == "open_viewer":
                    self.command_status = {
                        "status": "loading",
                        "action": action,
                        "message": "Loading selected state",
                    }
                    viewer = self.open_selected_viewer(
                        max_rows=request.get("maxRows") or 500,
                        height=int(request.get("height") or self.payload.get("view", {}).get("height") or 640),
                        initial_state=request.get("viewerState") if isinstance(request.get("viewerState"), dict) else None,
                    )
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": "Viewer loaded",
                        "entry_id": (viewer.get("payload") or {}).get("context", {}).get("entry_id"),
                    }
                elif action == "save_viewer_branch":
                    self.save_embedded_viewer_branch(
                        name=request.get("name"),
                        message=request.get("message"),
                        note=request.get("note"),
                        viewer_state=request.get("viewerState") if isinstance(request.get("viewerState"), dict) else None,
                    )
                elif action == "refresh":
                    self.refresh()
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": "Workspace web refreshed",
                    }
            except Exception as exc:
                self.viewer = {
                    **dict(self.viewer or {}),
                    "status": "error",
                    "message": str(exc),
                }
                self.command_status = {
                    "status": "error",
                    "action": action,
                    "message": str(exc),
                }

        def _refresh_after_embedded_save(self, selected_entry_id: str) -> None:
            selected_tree = self.selected_tree_id()
            payload = build_web_payload(
                self._workspace,
                height=int(self.payload.get("view", {}).get("height") or 640),
                title=self.payload.get("title"),
            )
            self.payload = payload
            self.state = {
                **initial_web_state(
                    payload,
                    selected_tree_id=selected_tree,
                    selected_entry_id=selected_entry_id,
                ),
                "viewMode": "viewer",
            }
            current_viewer = dict(self.viewer or {})
            if current_viewer:
                self.viewer = {
                    **current_viewer,
                    "state": current_viewer.get("state") or {},
                    "lastSavedEntryId": selected_entry_id,
                    "status": "ready",
                    "message": "Branch saved",
                }

else:

    class WorkspaceWebViewer:  # pragma: no cover - simple dependency guard
        """Placeholder that explains how to install widget dependencies."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise WorkspaceWebDependencyError(_dependency_message())


def web_view(
    *,
    height: int = 640,
    title: str | None = None,
) -> WorkspaceWebViewer:
    """Create an interactive workspace web view."""

    _ensure_interactive_dependencies()
    return WorkspaceWebViewer(height=height, title=title)


def build_web_payload(workspace: Any, *, height: int, title: str | None) -> dict[str, Any]:
    """Return a JSON-safe payload for the workspace web widget."""

    web = workspace.web()
    trees = [
        _web_tree_record(workspace, record)
        for record in list(web.get("trees", []))
    ]
    return {
        "version": 1,
        "title": title or "stateframe workspace web",
        "view": {
            "height": int(height),
        },
        "workspace": web.get("workspace") or {},
        "created_at": web.get("created_at"),
        "updated_at": web.get("updated_at"),
        "tree_count": len(trees),
        "trees": trees,
        "settings": workspace.settings(),
    }


def initial_web_state(
    payload: dict[str, Any],
    *,
    selected_tree_id: str | None = None,
    selected_entry_id: str | None = None,
) -> dict[str, Any]:
    """State shared by the workspace web widget."""

    trees = payload.get("trees") or []
    tree_ids = {tree.get("tree_id") for tree in trees}
    tree_id = selected_tree_id if selected_tree_id in tree_ids else (trees[0].get("tree_id") if trees else None)
    tree = next((item for item in trees if item.get("tree_id") == tree_id), None)
    entry_ids = {
        entry.get("id")
        for entry in ((tree or {}).get("tree_detail", {}).get("entries", []) or [])
    }
    entry_id = selected_entry_id if selected_entry_id in entry_ids else _default_entry_id_from_detail(
        (tree or {}).get("tree_detail", {}) or {}
    )
    return {
        "selectedTreeId": tree_id,
        "selectedEntryId": entry_id,
        "viewMode": "web",
        "search": "",
        "sort": "updated",
    }


def _ensure_interactive_dependencies() -> None:
    if anywidget is None or traitlets is None:
        raise WorkspaceWebDependencyError(_dependency_message())


def _dependency_message() -> str:
    return (
        "The stateframe workspace web viewer requires widget dependencies that "
        "ship with the base package. Install or refresh with "
        "`pip install stateframe`, or in this repo with `pip install -e .`."
    )


def _web_tree_record(workspace: Any, record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    try:
        tree_payload = workspace.load_tree(str(record["tree_id"]))
    except Exception as exc:
        result["tree_detail"] = {
            "entries": [],
            "tree": [],
            "states": {},
            "stats": {},
            "load_error": str(exc),
        }
        return _json_safe(result)
    result["tree_detail"] = _tree_detail_from_payload(workspace, record, tree_payload)
    return _json_safe(result)


def _tree_detail_from_payload(
    _workspace: Any,
    record: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    ledger = _saved_ledger_payload(payload)
    entries = ledger.get("entries") or []
    states = ledger.get("states") or {}
    active_entry_id = ledger.get("active_entry_id") or record.get("active_entry_id")
    enriched_entries = _ledger_entries(entries, states, active_entry_id)
    return _json_safe(
        {
            "root_entry_id": ledger.get("root_entry_id") or record.get("root_entry_id"),
            "active_entry_id": active_entry_id,
            "entries": enriched_entries,
            "tree": ledger.get("tree") or [],
            "states": states,
            "active_path": _ledger_path(enriched_entries, active_entry_id),
            "stats": _ledger_stats(enriched_entries, states),
            "saved_at": payload.get("saved_at"),
        }
    )


def _saved_ledger_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "root_entry_id": None,
        "active_entry_id": None,
        "entries": [],
        "tree": [],
        "states": {},
    }


def _saved_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    wrapper = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    profile = wrapper.get("profile") if isinstance(wrapper.get("profile"), dict) else {}
    return {
        **profile,
        "profile_id": wrapper.get("profile_id") or payload.get("profile_id"),
        "dataset_name": wrapper.get("dataset_name") or payload.get("dataset_name"),
        "tree_name": wrapper.get("tree_name") or payload.get("tree_name"),
        "source": wrapper.get("source") or {},
    }


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
        artifacts = entry.get("artifacts") or []
        enriched = {
            **entry,
            "depth": depth_for(entry),
            "children_ids": child_ids,
            "child_count": len(child_ids),
            "is_leaf": len(child_ids) == 0,
            "is_active": entry_id == active_entry_id,
            "has_state": bool(state_id),
            "has_snapshot": any(
                isinstance(artifact, dict) and artifact.get("kind") == "data_snapshot"
                for artifact in artifacts
            ),
            "state": state,
            "path": _ledger_path_from_entries(by_id, entry_id),
        }
        result.append(enriched)
    return result


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
        "snapshot_count": sum(1 for entry in entries if entry.get("has_snapshot")),
    }


def _default_entry_id_from_detail(detail: dict[str, Any]) -> str | None:
    entries = detail.get("entries") or []
    entry_ids = {entry.get("id") for entry in entries}
    active = detail.get("active_entry_id")
    root = detail.get("root_entry_id")
    if active in entry_ids:
        return active
    if root in entry_ids:
        return root
    return entries[0].get("id") if entries else None


def _data_snapshot_artifact(entry: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = [
        artifact
        for artifact in entry.get("artifacts", [])
        if isinstance(artifact, dict)
        and artifact.get("kind") == "data_snapshot"
        and artifact.get("format") == "parquet"
        and artifact.get("path")
    ]
    return artifacts[-1] if artifacts else None


def _artifact_path(workspace: Any, artifact: dict[str, Any]) -> Path:
    path = artifact.get("path")
    if not path:
        raise FileNotFoundError("Data snapshot artifact does not include a path.")
    return workspace.resolve_path(path)


def _attach_selected_context(
    frame: pd.DataFrame,
    *,
    workspace: Any,
    tree_record: dict[str, Any] | None,
    entry: dict[str, Any],
    state: dict[str, Any] | None,
) -> pd.DataFrame:
    """Attach enough stateframe context for ``sf.branch(frame)`` to work."""

    record = tree_record or {}
    context = {
        "workspace_root": str(workspace.root),
        "workspace_name": workspace.name,
        "tree_id": record.get("tree_id"),
        "tree_name": record.get("tree_name"),
        "dataset_name": record.get("dataset_name"),
        "entry_id": entry.get("id"),
        "state_id": entry.get("state_id") or (state or {}).get("id"),
    }
    frame.attrs["_stateframe"] = {key: value for key, value in context.items() if value}
    return frame


def _resolve_viewer_max_rows(max_rows: int | str | None, data: pd.DataFrame) -> int:
    if isinstance(max_rows, str) and max_rows.lower() in {"all", "full"}:
        return max(1, int(data.shape[0]))
    if max_rows is None:
        return 500
    try:
        value = int(max_rows)
    except (TypeError, ValueError):
        value = 500
    if value <= 0:
        return max(1, int(data.shape[0]))
    return value


def _viewer_state_for_payload(
    payload: dict[str, Any],
    initial_state: dict[str, Any] | None,
) -> dict[str, Any]:
    state = initial_view_state(payload)
    if not isinstance(initial_state, dict):
        return state
    column_ids = {column.get("id") for column in payload.get("columns", [])}
    preserved_order = [
        column_id
        for column_id in initial_state.get("columnOrder", [])
        if column_id in column_ids
    ]
    if preserved_order:
        state["columnOrder"] = [
            *preserved_order,
            *[column_id for column_id in state["columnOrder"] if column_id not in preserved_order],
        ]
    state["hiddenColumnIds"] = [
        column_id
        for column_id in initial_state.get("hiddenColumnIds", [])
        if column_id in column_ids
    ]
    state["sorts"] = [
        sort
        for sort in initial_state.get("sorts", [])
        if isinstance(sort, dict)
        and sort.get("id") in column_ids
        and sort.get("direction") in {"asc", "desc"}
    ]
    state["filters"] = {
        column_id: filter_spec
        for column_id, filter_spec in (initial_state.get("filters") or {}).items()
        if column_id in column_ids and isinstance(filter_spec, dict)
    }
    if initial_state.get("selectedColumnId") in column_ids:
        state["selectedColumnId"] = initial_state.get("selectedColumnId")
    state["globalSearch"] = str(initial_state.get("globalSearch") or "")
    state["showIndex"] = initial_state.get("showIndex") is not False
    return state


def _missing_snapshot_message(
    entry: dict[str, Any],
    record: dict[str, Any] | None,
    replay_error: Exception | None = None,
) -> str:
    source = (record or {}).get("source") or {}
    source_note = source.get("replay_note") or (
        "Set the tree source path before replaying." if source.get("kind") != "file" else ""
    )
    title = entry.get("title") or entry.get("id")
    replay_note = f" Replay failed: {replay_error}" if replay_error else ""
    return (
        f"Selected state {title!r} has no materialized data snapshot and could "
        "not be replayed from the tree metadata. "
        f"{source_note}{replay_note}"
    ).strip()


def _ledger_from_saved_payload(
    payload: dict[str, Any],
    *,
    selected_entry_id: str | None,
    selected_state_id: str | None,
    selected_data: pd.DataFrame,
):
    from stateframe.ledger import LensLedger

    ledger_payload = _saved_ledger_payload(payload)
    states = {
        state_id: _state_from_payload(state_id, state_payload)
        for state_id, state_payload in (ledger_payload.get("states") or {}).items()
    }
    if selected_state_id in states:
        states[selected_state_id] = replace(states[selected_state_id], data=selected_data.copy())
    entries = [
        _entry_from_payload(entry_payload)
        for entry_payload in (ledger_payload.get("entries") or [])
    ]
    active_entry_id = selected_entry_id or ledger_payload.get("active_entry_id")
    return LensLedger(
        entries=entries,
        states=states,
        active_entry_id=active_entry_id,
        root_entry_id=ledger_payload.get("root_entry_id"),
    )


def _entry_from_payload(payload: dict[str, Any]):
    from stateframe.ledger import LedgerEntry

    fields = LedgerEntry.__dataclass_fields__
    values = {key: payload.get(key) for key in fields if key in payload}
    for key, field_def in fields.items():
        if key in values:
            continue
        if field_def.default is not MISSING:
            values[key] = field_def.default
        elif field_def.default_factory is not MISSING:  # type: ignore[attr-defined]
            values[key] = field_def.default_factory()  # type: ignore[misc]
    return LedgerEntry(**values)


def _state_from_payload(state_id: str, payload: dict[str, Any]):
    from stateframe.ledger import LedgerState

    return LedgerState(
        id=str(payload.get("id") or state_id),
        entry_id=str(payload.get("entry_id") or ""),
        label=str(payload.get("label") or ""),
        row_count=int(payload.get("row_count") or 0),
        column_count=int(payload.get("column_count") or 0),
        memory_bytes=int(payload.get("memory_bytes") or 0),
        columns=[str(column) for column in payload.get("columns", [])],
        dtypes={str(key): str(value) for key, value in (payload.get("dtypes") or {}).items()},
        data=pd.DataFrame(payload["data"]) if isinstance(payload.get("data"), list) else None,
    )


def _valid_column(column: Any, data: pd.DataFrame) -> str | None:
    return str(column) if column in data.columns else None


def _selected_view_title(entry: dict[str, Any] | None) -> str:
    title = (entry or {}).get("title")
    return f"View from {title}" if title else "View selected web state"
