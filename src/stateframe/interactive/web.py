"""Notebook widget for the stateframe workspace web."""

from __future__ import annotations

import json
from dataclasses import MISSING, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from stateframe.interactive.serialize import (
    _json_safe,
    apply_view_state,
    build_viewer_payload,
    initial_view_state,
    summarize_draft_state,
    summarize_view_state,
    view_state_signature,
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
        visualizer = traitlets.Dict(default_value={}).tag(sync=True)
        files = traitlets.Dict(default_value={}).tag(sync=True)
        command = traitlets.Dict(default_value={}).tag(sync=True)
        command_status = traitlets.Dict(default_value={}).tag(sync=True)
        branch_request = traitlets.Dict(default_value={}).tag(sync=True)
        branch_status = traitlets.Dict(default_value={}).tag(sync=True)

        def __init__(
            self,
            *,
            profile: Any | None = None,
            record_profile: Any | None = None,
            ledger_parent_id: str | None = None,
            launch_mode: str = "workspace",
            selected_entry_id: str | None = None,
            max_rows: int | str | None = 500,
            height: int = 640,
            theme: str = "auto",
            title: str | None = None,
            initial_state: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> None:
            from stateframe import workspace

            self._workspace = workspace.current()
            self._launch_mode = launch_mode
            self._single_profile = profile
            self._embedded_view_profile = None
            self._embedded_record_profile = record_profile or profile
            self._embedded_parent_id: str | None = ledger_parent_id
            self._visualizer_view_profile = None
            self._visualizer_record_profile = record_profile or profile
            self._visualizer_parent_id: str | None = ledger_parent_id
            self._last_command_nonce: Any = None
            self._last_branch_request_nonce: Any = None
            self._last_view_checkpoint_signature: str | None = None
            self._last_view_checkpoint_entry: Any = None
            if profile is None:
                payload = build_web_payload(self._workspace, height=height, title=title)
                state = initial_web_state(payload, selected_entry_id=selected_entry_id)
            else:
                _ensure_profile_has_live_root_state(profile)
                payload = build_profile_web_payload(profile, height=height, title=title)
                state = initial_web_state(
                    payload,
                    selected_tree_id=_profile_tree_id(profile),
                    selected_entry_id=selected_entry_id or ledger_parent_id,
                )
            super().__init__(
                payload=payload,
                state=state,
                viewer={},
                visualizer={},
                files=self._workspace.list_files(purpose="open"),
                command={},
                command_status={},
                branch_request={},
                branch_status={},
                **kwargs,
            )
            try:
                from stateframe.pull import set_active_web_viewer

                set_active_web_viewer(self)
            except Exception:
                pass
            if profile is not None and launch_mode == "viewer":
                self.open_selected_viewer(
                    max_rows=max_rows,
                    height=height,
                    theme=theme,
                    title=title,
                    initial_state=initial_state,
                )

        @property
        def workspace(self):
            """The stateframe workspace backing this web view."""

            return self._workspace

        @property
        def profile(self):
            """The in-memory profile backing focused tree/viewer launches."""

            return self._embedded_view_profile or self._single_profile

        @property
        def record_profile(self):
            """The profile whose ledger receives viewer-created branches."""

            return self._embedded_record_profile

        @property
        def ledger_parent_id(self) -> str | None:
            """The ledger entry that viewer-created branches attach beneath."""

            return self._embedded_parent_id

        def current_state(self) -> dict[str, Any]:
            """Return the latest synced widget state."""

            return dict(self.state)

        def browse_files(
            self,
            path: str | Path | None = None,
            *,
            include_hidden: bool = False,
            max_entries: int = 500,
            purpose: str = "open",
        ) -> dict[str, Any]:
            """List a workspace folder and sync it to the web file browser."""

            listing = self._workspace.list_files(
                path,
                include_hidden=include_hidden,
                max_entries=max_entries,
                purpose=purpose,
            )
            self.files = listing
            return listing

        def scan_file(
            self,
            path: str | Path,
            *,
            name: str | None = None,
            target: str | None = None,
            time: str | None = None,
            reader_params: dict[str, Any] | None = None,
        ):
            """Scan a workspace file and save it as a new tree."""

            info = self._workspace.file_info(path)
            if not info.get("can_scan"):
                raise ValueError(f"Selected path is not a supported data file: {path}")

            from stateframe.api import scan_path

            profile = scan_path(
                str(info["path"]),
                name=name or Path(str(info["path"])).stem,
                target=target,
                time=time,
                reader_params=reader_params,
            )
            profile.save_tree()
            return profile

        def query_data(
            self,
            source: str,
            statement: str,
            *,
            params: dict[str, Any] | None = None,
            name: str | None = None,
            target: str | None = None,
            time: str | None = None,
            store_query: bool = True,
            store_params: bool = True,
            save_tree: bool = True,
            **source_kwargs: Any,
        ):
            """Run a registered data-source query and add it to the workspace."""

            from stateframe.api import query as query_api

            profile = query_api(
                source,
                statement,
                params=params,
                name=name,
                target=target,
                time=time,
                store_query=store_query,
                store_params=store_params,
                save_tree=save_tree,
                **source_kwargs,
            )
            self.refresh()
            return profile

        def save_source_connection(
            self,
            source_id: str,
            import_path: str,
            *,
            display_name: str | None = None,
            description: str = "",
            enabled: bool = True,
            store_query: bool = True,
            store_params: bool = True,
            register_now: bool = True,
        ) -> dict[str, Any]:
            """Save a workspace query connection and optionally import it now."""

            from stateframe import sources

            connection = sources.save_connection(
                source_id,
                import_path,
                display_name=display_name,
                description=description,
                enabled=enabled,
                store_query=store_query,
                store_params=store_params,
                register_now=register_now,
            )
            self.refresh()
            return connection

        def delete_source_connection(self, source_id: str, *, unregister_source: bool = False) -> None:
            """Delete a saved workspace query connection."""

            from stateframe import sources

            sources.delete_connection(source_id, unregister_source=unregister_source)
            self.refresh()

        def refresh_sources(self) -> list[dict[str, Any]]:
            """Import all enabled saved source connections and refresh the web payload."""

            from stateframe import sources

            result = sources.auto_register_connections(raise_errors=False)
            self.refresh()
            return result

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

            if self._single_profile is not None:
                return _profile_tree_payload(self._single_profile)
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

        def selected_entry(self):
            """Return the selected ledger entry object when available."""

            selected = self.selected_entry_id()
            profile = self._single_profile
            if profile is None or selected is None or getattr(profile, "ledger", None) is None:
                return self.selected_entry_record()
            try:
                return profile.ledger.get(selected)
            except KeyError:
                return self.selected_entry_record()

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

        def recommendations(self):
            """Return recommendations for the currently selected dataframe state."""

            return self.selected_profile().recommendations()

        def run_selected(self, lens_id: str, **params: Any):
            """Run a lens on the selected state and record it under that node."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No tree entry is selected.")
            selected_profile = self.selected_profile()

            from stateframe.lenses import run_lens

            result = run_lens(selected_profile, lens_id, **params)
            record_profile = self._single_profile or selected_profile
            record_profile.lens_results[result.id] = result
            if record_profile.ledger is not None:
                record_profile.ledger.record_lens(
                    selected_profile,
                    lens_id=result.id,
                    params=params,
                    result=result,
                    parent_id=selected,
                )
            self.refresh()
            return result

        def run_recommendation(
            self,
            recommendation: int | str | dict[str, Any] = 1,
            **params: Any,
        ):
            """Run a selected-state recommendation and record it under the node."""

            profile = self.selected_profile()
            rec = _resolve_recommendation(profile, recommendation)
            lens_params = _params_from_recommendation(rec)
            lens_params.update(params)
            return self.run_selected(rec.lens, **lens_params)

        def pull_selected(self) -> pd.DataFrame:
            """Load the selected state into the notebook as a DataFrame.

            Saved Parquet snapshots are used when available. Otherwise stateframe
            replays the saved path from the tree's editable base source path.
            """

            entry = self.selected_entry_record()
            if entry is None:
                raise ValueError("No tree entry is selected.")
            if self._single_profile is not None:
                frame = _profile_checkout(self._single_profile, str(entry["id"]))
                return _attach_profile_context(
                    frame,
                    profile=self._single_profile,
                    entry=entry,
                    state=self.selected_state_metadata(),
                )
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

        def pull(
            self,
            name: str | None = None,
            *,
            message: str | None = None,
            note: str | None = None,
            record: bool = True,
            title: str | None = None,
            operation: str = "viewer.pull",
        ) -> pd.DataFrame:
            """Pull data from the active web context.

            When a dataframe viewer is open, this returns the viewer-shaped
            dataframe and can record it as a branch. Otherwise it returns the
            selected saved tree state.
            """

            if self.viewer and self.state.get("viewMode") == "viewer":
                result = self.viewer_dataframe()
                entry = None
                if record:
                    entry = self.save_embedded_viewer_branch(
                        name=name,
                        message=message,
                        note=note,
                        viewer_state=(self.viewer or {}).get("state"),
                        operation=operation,
                        title=title,
                        force=False,
                        save_tree=False,
                    )
                if entry is not None and self._embedded_record_profile is not None:
                    from stateframe.branch import _attach_dataframe_context

                    result = _attach_dataframe_context(
                        result,
                        profile=self._embedded_record_profile,
                        entry_id=entry.id,
                    )
                return result
            return self.pull_selected()

        def filtered_dataframe(self, **kwargs: Any) -> pd.DataFrame:
            """Compatibility alias for pulling the current viewer-shaped data."""

            return self.pull(**kwargs)

        def selected_profile(self):
            """Return a live profile restored around the selected state.

            The returned profile keeps the saved ledger metadata and stable
            tree id, so new viewer pulls can branch from the selected node and
            later be saved back into the same workspace tree.
            """

            if self._single_profile is not None:
                selected = self.selected_entry_id()
                if selected is None:
                    raise ValueError("No tree entry is selected.")
                data = _profile_checkout(self._single_profile, selected)
                return _profile_for_selected_state(self._single_profile, data)
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
            return WorkspaceWebViewer(
                profile=record_profile,
                record_profile=record_profile,
                ledger_parent_id=selected,
                launch_mode="viewer",
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
            if self._single_profile is not None:
                record_profile = self._single_profile
                data = _profile_checkout(record_profile, selected)
            else:
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
            viewer_payload["lineage"] = _viewer_lineage(record_profile, selected)
            viewer_payload["draft"] = summarize_draft_state(
                viewer_payload,
                _viewer_state_for_payload(viewer_payload, initial_state),
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

        def open_visualizer(
            self,
            *,
            viewer_state: dict[str, Any] | None = None,
            max_rows: int | str | None = 500,
            height: int | None = None,
            title: str | None = None,
        ) -> dict[str, Any]:
            """Open the Plotly visual builder for the selected or embedded state."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No tree entry is selected.")
            if self._embedded_view_profile is not None and isinstance(viewer_state, dict):
                current_viewer = dict(self.viewer or {})
                viewer_payload = current_viewer.get("payload") or {}
                state = viewer_state or current_viewer.get("state") or initial_view_state(viewer_payload)
                data = apply_view_state(self._embedded_view_profile.data, viewer_payload, state)
                record_profile = self._embedded_record_profile or self.selected_profile()
                parent_id = self._embedded_parent_id or selected
            elif self._single_profile is not None:
                record_profile = self._single_profile
                data = _profile_checkout(record_profile, selected)
                parent_id = selected
            else:
                record_profile = self.selected_profile()
                data = record_profile.checkout(selected)
                parent_id = selected

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
            payload = _build_visualizer_payload(
                view_profile,
                record_profile=record_profile,
                tree_id=self.selected_tree_id(),
                tree_name=(self.selected_tree_record() or {}).get("tree_name"),
                entry_id=parent_id,
                state_id=self.selected_state_id(),
                entry_title=(self.selected_entry_record() or {}).get("title"),
                max_rows=max_rows,
                height=view_height,
                title=title,
            )
            self._visualizer_view_profile = view_profile
            self._visualizer_record_profile = record_profile
            self._visualizer_parent_id = parent_id
            self.visualizer = {
                "status": "ready",
                "payload": payload,
                "state": _initial_visualizer_state(payload),
                "preview": None,
                "message": "",
            }
            self.state = {
                **dict(self.state),
                "viewMode": "visualizer",
                "selectedTreeId": self.selected_tree_id(),
                "selectedEntryId": parent_id,
            }
            return self.visualizer

        def render_visualizer(
            self,
            spec: dict[str, Any] | None = None,
            *,
            save: bool = False,
            note: str | None = None,
            save_mode: bool = False,
            save_path: str | Path | None = None,
        ) -> dict[str, Any]:
            """Render or save the current visualizer spec."""

            if self._visualizer_view_profile is None or self._visualizer_record_profile is None:
                self.open_visualizer()
            if self._visualizer_view_profile is None or self._visualizer_record_profile is None:
                raise ValueError("No visualizer state is available.")

            from stateframe.visualizer import build_visual_artifact

            current = dict(self.visualizer or {})
            payload = current.get("payload") or {}
            state = current.get("state") or _initial_visualizer_state(payload)
            visual_spec = spec or _spec_from_visualizer_state(state)
            if note is not None:
                visual_spec = {**visual_spec, "note": note}
            visual_spec = _resolve_visual_spec_columns(visual_spec, payload)
            artifact, summary, code = build_visual_artifact(
                self._visualizer_view_profile,
                visual_spec,
                title=visual_spec.get("title") or None,
            )
            if save_mode:
                from stateframe.artifacts import persist_artifact_files

                artifact = persist_artifact_files(
                    artifact,
                    profile=self._visualizer_record_profile,
                    entry_label=artifact.get("title") or "visual",
                    base_path=save_path,
                )

            self.visualizer = {
                **current,
                "status": "rendered",
                "state": state,
                "preview": artifact,
                "message": "Visual rendered",
            }
            if not save:
                return artifact

            entry = self._visualizer_record_profile.record_artifact(
                title=artifact.get("title") or "Visual",
                kind="plot",
                operation=f"visual.{visual_spec.get('kind') or 'plotly'}",
                parent_id=self._visualizer_parent_id,
                artifact=artifact,
                summary=summary,
                code=code,
                note=visual_spec.get("note") or "",
                visual_spec=visual_spec,
            )
            self._visualizer_record_profile.save_tree()
            self._refresh_after_embedded_save(entry.id)
            self.state = {
                **dict(self.state),
                "viewMode": "visualizer",
                "selectedEntryId": entry.id,
            }
            self.command_status = {
                "status": "saved",
                "action": "save_visualizer_leaf",
                "entry_id": entry.id,
                "title": entry.title,
                "message": "Visual leaf saved",
            }
            return entry.to_dict()

        def viewer_dataframe(self, viewer_state: dict[str, Any] | None = None) -> pd.DataFrame:
            """Return the current embedded viewer dataframe without recording it."""

            if self._embedded_view_profile is None:
                raise ValueError("No embedded viewer is open.")
            current_viewer = dict(self.viewer or {})
            viewer_payload = current_viewer.get("payload") or {}
            state = viewer_state or current_viewer.get("state") or initial_view_state(viewer_payload)
            return apply_view_state(self._embedded_view_profile.data, viewer_payload, state)

        def save_current_view(
            self,
            *,
            title: str = "Viewer dataframe state",
            operation: str = "viewer.save_current_view",
            name: str | None = None,
            message: str | None = None,
            note: str | None = None,
            force: bool = True,
        ):
            """Record the current web-embedded viewer state as a ledger branch."""

            return self.save_embedded_viewer_branch(
                name=name,
                message=message,
                note=note,
                operation=operation,
                title=title,
                force=force,
                save_tree=False,
            )

        def record_current_view(self, **kwargs: Any):
            """Alias for ``save_current_view``."""

            return self.save_current_view(**kwargs)

        def last_checkpoint_entry(self):
            """Return the most recent viewer-created ledger entry, if any."""

            return self._last_view_checkpoint_entry

        def selected_column(self) -> str | None:
            """Return the currently inspected source column in the open viewer."""

            viewer_payload = (self.viewer or {}).get("payload") or {}
            viewer_state = (self.viewer or {}).get("state") or {}
            selected_id = viewer_state.get("selectedColumnId")
            for column in viewer_payload.get("columns", []):
                if column.get("id") == selected_id:
                    return column.get("source_name")
            return None

        def save_embedded_viewer_branch(
            self,
            *,
            name: str | None = None,
            message: str | None = None,
            note: str | None = None,
            viewer_state: dict[str, Any] | None = None,
            operation: str = "web.viewer.save_branch",
            title: str | None = None,
            force: bool = True,
            save_tree: bool = True,
            save: bool = False,
            save_path: str | Path | None = None,
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

            signature = view_state_signature(viewer_payload, state)
            checkpoint_signature = _checkpoint_signature(
                signature,
                operation=operation,
                output_name=name,
                message=message,
                note=note,
            )
            if (
                not force
                and checkpoint_signature == self._last_view_checkpoint_signature
                and self._last_view_checkpoint_entry is not None
            ):
                return self._last_view_checkpoint_entry
            entry = self._embedded_record_profile.record_state(
                result,
                title=title or _pull_title(name),
                operation=operation,
                parent_id=self._embedded_parent_id,
                note=note or message or "",
                options=_state_options(self._embedded_record_profile, result),
                viewer_state=dict(state),
                viewer_summary=summary,
                output_name=name,
                message=message,
            )
            self._last_view_checkpoint_signature = checkpoint_signature
            self._last_view_checkpoint_entry = entry
            if save:
                from stateframe import save as save_api

                output_path = Path(save_path) if save_path is not None else _default_state_save_path(
                    self._workspace,
                    self._embedded_record_profile,
                    name or entry.title,
                )
                save_api.data(
                    self._embedded_record_profile,
                    entry_id=entry.id,
                    name=name or entry.title,
                    path=output_path,
                    also_save_tree=False,
                )
            if save_tree:
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

        def save_embedded_plot_leaf(
            self,
            *,
            kind: str = "column",
            column: str | None = None,
            title: str | None = None,
            note: str | None = None,
            viewer_state: dict[str, Any] | None = None,
            params: dict[str, Any] | None = None,
            save: bool | None = None,
            save_path: str | Path | None = None,
        ):
            """Save a rendered plot as an artifact leaf under the selected state."""

            if self._embedded_view_profile is None or self._embedded_record_profile is None:
                self.open_selected_viewer()
            if self._embedded_view_profile is None or self._embedded_record_profile is None:
                raise ValueError("No embedded viewer state is available for plotting.")

            current_viewer = dict(self.viewer or {})
            viewer_payload = current_viewer.get("payload") or {}
            state = viewer_state or current_viewer.get("state") or initial_view_state(viewer_payload)
            result = apply_view_state(self._embedded_view_profile.data, viewer_payload, state)

            from stateframe.profile import build_profile

            plot_profile = build_profile(
                result,
                name=self._embedded_record_profile.dataset_name,
                target=(
                    self._embedded_record_profile.target
                    if self._embedded_record_profile.target in result.columns
                    else None
                ),
                time=(
                    self._embedded_record_profile.time
                    if self._embedded_record_profile.time in result.columns
                    else None
                ),
                goal=self._embedded_record_profile.goal,
                mode=self._embedded_record_profile.mode,
                register=False,
            )
            entry = plot_profile.record_plot_leaf(
                kind=kind,
                column=column if column in result.columns else None,
                title=title,
                parent_id=None,
                params=params,
                note=note or "",
            )
            artifact = entry.artifacts[0] if entry.artifacts else None
            if save and artifact is not None:
                from stateframe.artifacts import persist_artifact_files

                artifact = persist_artifact_files(
                    artifact,
                    profile=self._embedded_record_profile,
                    entry_label=entry.title,
                    base_path=save_path,
                )
            artifact_entry = self._embedded_record_profile.record_artifact(
                title=entry.title,
                kind="plot",
                operation=entry.operation,
                parent_id=self._embedded_parent_id,
                artifact=artifact,
                summary={
                    **entry.summary,
                    "viewer_summary": summarize_view_state(viewer_payload, state, result),
                    "draft": summarize_draft_state(viewer_payload, state),
                },
                metrics=entry.metrics,
                code=entry.code,
                note=note or "",
                plot_spec=(artifact or {}).get("spec"),
                viewer_state=dict(state),
            )
            self._embedded_record_profile.save_tree()
            self._refresh_after_embedded_save(artifact_entry.id)
            self.command_status = {
                "status": "saved",
                "action": "save_plot_leaf",
                "entry_id": artifact_entry.id,
                "title": artifact_entry.title,
                "message": "Plot leaf saved",
            }
            return artifact_entry

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

        def save_selected_entry_note(
            self,
            note: str,
            *,
            entry_id: str | None = None,
        ) -> dict[str, Any]:
            """Replace the note for the selected ledger entry and persist the tree."""

            target_entry_id = str(entry_id or self.selected_entry_id() or "")
            if not target_entry_id:
                raise ValueError("No tree entry is selected.")
            selected_tree = self.selected_tree_id()
            previous_mode = str(self.state.get("viewMode") or "web")
            text = str(note or "")

            updated: dict[str, Any] | None = None
            for profile in (self._single_profile, self._embedded_record_profile):
                if _profile_matches_tree(self._workspace, profile, selected_tree):
                    if getattr(profile, "ledger", None) is None:
                        continue
                    try:
                        updated_entry = profile.update_entry_note(target_entry_id, text)
                    except KeyError:
                        continue
                    profile.save_tree()
                    updated = updated_entry.to_dict()
                    break

            if updated is None:
                record = self.selected_tree_record()
                if record is None:
                    raise ValueError("No workspace tree is selected.")
                payload = self.load_selected_tree()
                updated = _update_tree_payload_entry_note(payload, target_entry_id, text)
                tree_path = record.get("tree_path")
                if not tree_path:
                    raise FileNotFoundError("Selected tree does not have a saved tree path.")
                output_path = self._workspace.resolve_path(tree_path)
                payload["updated_at"] = _now()
                output_path.write_text(
                    json.dumps(payload, indent=2, default=str),
                    encoding="utf-8",
                )

            self.refresh()
            self.state = {
                **dict(self.state),
                "selectedTreeId": selected_tree,
                "selectedEntryId": target_entry_id,
                "viewMode": previous_mode,
            }
            return dict(updated)

        def delete_selected_items(
            self,
            *,
            tree_ids: list[str] | tuple[str, ...] | set[str] | None = None,
            entry_ids: list[str] | tuple[str, ...] | set[str] | None = None,
            tree_id: str | None = None,
        ) -> dict[str, Any]:
            """Delete selected workspace trees and branch/leaf entries."""

            if self._single_profile is not None:
                raise ValueError("Delete mode is only available for saved workspace trees.")

            selected_tree = tree_id or self.selected_tree_id()
            trees = [str(item) for item in (tree_ids or []) if str(item or "").strip()]
            entries = [str(item) for item in (entry_ids or []) if str(item or "").strip()]
            if not trees and not entries:
                raise ValueError("No trees or entries were selected for deletion.")

            deleted_trees = []
            deleted_entries: dict[str, Any] | None = None
            for target_tree in trees:
                deleted_trees.append(self._workspace.delete_tree(target_tree, delete_files=False))

            if entries and selected_tree and selected_tree not in set(trees):
                deleted_entries = self._workspace.delete_tree_entries(selected_tree, entries)

            self.refresh()
            remaining_trees = self.payload.get("trees", []) or []
            next_tree = (
                selected_tree
                if selected_tree and any(tree.get("tree_id") == selected_tree for tree in remaining_trees)
                else (remaining_trees[0].get("tree_id") if remaining_trees else None)
            )
            self.state = {
                **initial_web_state(self.payload, selected_tree_id=next_tree),
                "deleteMode": False,
                "deleteTreeIds": [],
                "deleteEntryIds": [],
            }
            return {
                "deleted_trees": deleted_trees,
                "deleted_tree_count": len(deleted_trees),
                "deleted_entries": deleted_entries,
                "deleted_entry_count": int((deleted_entries or {}).get("deleted_entry_count") or 0),
            }

        def refresh(self) -> None:
            """Reload the active web payload."""

            previous_tree = self.selected_tree_id()
            try:
                previous_entry = self.selected_entry_id()
            except ValueError:
                previous_entry = None
            if self._single_profile is not None:
                payload = build_profile_web_payload(
                    self._single_profile,
                    height=int(self.payload.get("view", {}).get("height") or 640),
                    title=self.payload.get("title"),
                )
            else:
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
                        save=bool(request.get("saveMode")),
                        save_path=request.get("savePath") or None,
                    )
                elif action == "save_plot_leaf":
                    self.save_embedded_plot_leaf(
                        kind=request.get("plotKind") or "column",
                        column=request.get("columnName") or None,
                        title=request.get("title") or None,
                        note=request.get("note") or None,
                        viewer_state=(
                            request.get("viewerState")
                            if isinstance(request.get("viewerState"), dict)
                            else None
                        ),
                        params=(
                            request.get("params")
                            if isinstance(request.get("params"), dict)
                            else None
                        ),
                        save=bool(request.get("saveMode")),
                        save_path=request.get("savePath") or None,
                    )
                elif action == "save_entry_note":
                    updated = self.save_selected_entry_note(
                        str(request.get("note") or ""),
                        entry_id=request.get("entryId") or None,
                    )
                    self.command_status = {
                        "status": "saved",
                        "action": action,
                        "message": "Notes saved",
                        "entry_id": updated.get("id"),
                        "title": updated.get("title"),
                    }
                elif action == "save_source_connection":
                    connection = self.save_source_connection(
                        str(request.get("sourceId") or ""),
                        str(request.get("importPath") or ""),
                        display_name=request.get("displayName") or None,
                        description=str(request.get("description") or ""),
                        enabled=request.get("enabled") is not False,
                        store_query=request.get("storeQuery") is not False,
                        store_params=request.get("storeParams") is not False,
                        register_now=True,
                    )
                    self.state = {
                        **dict(self.state),
                        "viewMode": "get_data",
                        "getDataTab": "query",
                        "querySourceId": connection.get("id"),
                    }
                    self.command_status = {
                        "status": "saved",
                        "action": action,
                        "message": f"Connection saved: {connection.get('display_name') or connection.get('id')}",
                        "source_id": connection.get("id"),
                    }
                elif action == "delete_source_connection":
                    source_id = str(request.get("sourceId") or "")
                    self.delete_source_connection(
                        source_id,
                        unregister_source=request.get("unregisterSource") is not False,
                    )
                    self.state = {
                        **dict(self.state),
                        "viewMode": "get_data",
                        "getDataTab": "connections",
                    }
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": f"Deleted connection {source_id}",
                    }
                elif action == "delete_selected":
                    self.command_status = {
                        "status": "loading",
                        "action": action,
                        "message": "Deleting selected items",
                    }
                    result = self.delete_selected_items(
                        tree_ids=(
                            request.get("treeIds")
                            if isinstance(request.get("treeIds"), list)
                            else []
                        ),
                        entry_ids=(
                            request.get("entryIds")
                            if isinstance(request.get("entryIds"), list)
                            else []
                        ),
                        tree_id=request.get("treeId") or request.get("selectedTreeId") or None,
                    )
                    total = int(result.get("deleted_tree_count") or 0) + int(result.get("deleted_entry_count") or 0)
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": f"Deleted {total} item{'' if total == 1 else 's'}",
                        **result,
                    }
                elif action == "refresh_sources":
                    imports = self.refresh_sources()
                    self.state = {
                        **dict(self.state),
                        "viewMode": "get_data",
                        "getDataTab": "query",
                    }
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": f"Loaded {sum(1 for item in imports if item.get('status') == 'registered')} source connection(s)",
                        "imports": imports,
                    }
                elif action == "open_visualizer":
                    self.command_status = {
                        "status": "loading",
                        "action": action,
                        "message": "Loading visualizer",
                    }
                    self.open_visualizer(
                        max_rows=request.get("maxRows") or 500,
                        height=int(request.get("height") or self.payload.get("view", {}).get("height") or 640),
                        viewer_state=request.get("viewerState") if isinstance(request.get("viewerState"), dict) else None,
                    )
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": "Visualizer loaded",
                    }
                elif action == "render_visualizer":
                    artifact = self.render_visualizer(
                        request.get("visualSpec") if isinstance(request.get("visualSpec"), dict) else None,
                        note=request.get("note") or None,
                        save=False,
                    )
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": "Visual rendered",
                        "title": artifact.get("title"),
                    }
                elif action == "save_visualizer_leaf":
                    saved = self.render_visualizer(
                        request.get("visualSpec") if isinstance(request.get("visualSpec"), dict) else None,
                        note=request.get("note") or None,
                        save=True,
                        save_mode=bool(request.get("saveMode")),
                        save_path=request.get("savePath") or None,
                    )
                    self.command_status = {
                        "status": "saved",
                        "action": action,
                        "message": "Visual leaf saved",
                        "entry_id": saved.get("id"),
                        "title": saved.get("title"),
                    }
                elif action == "refresh":
                    self.refresh()
                    self.browse_files(
                        path=(self.files or {}).get("current_path") or ".",
                        include_hidden=bool((self.files or {}).get("include_hidden")),
                        max_entries=int((self.files or {}).get("max_entries") or 500),
                        purpose=(self.files or {}).get("purpose") or "open",
                    )
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": "Workspace web refreshed",
                    }
                elif action == "browse_files":
                    self.command_status = {
                        "status": "loading",
                        "action": action,
                        "message": "Loading workspace files",
                    }
                    listing = self.browse_files(
                        path=request.get("path") or ".",
                        include_hidden=bool(request.get("includeHidden")),
                        max_entries=int(request.get("maxEntries") or 500),
                        purpose=request.get("purpose") or "open",
                    )
                    self.state = {
                        **dict(self.state),
                        "viewMode": request.get("viewMode") if request.get("viewMode") in {"files", "get_data"} else "files",
                        "getDataTab": request.get("getDataTab") or dict(self.state).get("getDataTab") or "files",
                        "selectedFilePath": None,
                    }
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": f"Listed {listing.get('current_path') or '.'}",
                    }
                elif action == "scan_file":
                    self.command_status = {
                        "status": "loading",
                        "action": action,
                        "message": "Scanning selected file",
                    }
                    profile = self.scan_file(
                        request.get("path"),
                        name=request.get("name") or None,
                        target=request.get("target") or None,
                        time=request.get("time") or None,
                        reader_params=(
                            request.get("readerParams")
                            if isinstance(request.get("readerParams"), dict)
                            else None
                        ),
                    )
                    tree_id = getattr(profile, "tree_id", None)
                    self._refresh_after_file_scan(tree_id)
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": f"Scanned {profile.tree_name or profile.dataset_name or tree_id}",
                        "tree_id": tree_id,
                    }
                elif action == "query_data":
                    self.command_status = {
                        "status": "loading",
                        "action": action,
                        "message": "Running source query",
                    }
                    profile = self.query_data(
                        str(request.get("source") or ""),
                        str(request.get("query") or ""),
                        params=(
                            request.get("params")
                            if isinstance(request.get("params"), dict)
                            else None
                        ),
                        name=request.get("name") or None,
                        target=request.get("target") or None,
                        time=request.get("time") or None,
                        store_query=request.get("storeQuery") is not False,
                        store_params=request.get("storeParams") is not False,
                    )
                    tree_id = getattr(profile, "tree_id", None)
                    self._refresh_after_file_scan(tree_id)
                    self.command_status = {
                        "status": "ready",
                        "action": action,
                        "message": f"Queried {profile.tree_name or profile.dataset_name or tree_id}",
                        "tree_id": tree_id,
                    }
            except Exception as exc:
                if action in {"open_visualizer", "render_visualizer", "save_visualizer_leaf"}:
                    self.visualizer = {
                        **dict(self.visualizer or {}),
                        "status": "error",
                        "message": str(exc),
                    }
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

        @traitlets.observe("branch_request")
        def _observe_branch_request(self, change: Any) -> None:
            request = change.get("new") or {}
            if not isinstance(request, dict):
                return
            nonce = request.get("nonce")
            if not nonce or nonce == self._last_branch_request_nonce:
                return
            self._last_branch_request_nonce = nonce
            try:
                entry = self.save_embedded_viewer_branch(
                    name=request.get("name"),
                    message=request.get("message"),
                    note=request.get("note"),
                    viewer_state=request.get("viewerState") if isinstance(request.get("viewerState"), dict) else None,
                    operation=request.get("operation") or "viewer.save_branch",
                    title=request.get("title") or _pull_title(request.get("name")),
                    force=True,
                    save_tree=True,
                )
                self.branch_status = {
                    "nonce": nonce,
                    "status": "saved",
                    "entry_id": entry.id,
                    "title": entry.title,
                    "message": request.get("message") or "",
                }
            except Exception as exc:
                self.branch_status = {
                    "nonce": nonce,
                    "status": "error",
                    "message": str(exc),
                }

        def _refresh_after_file_scan(self, selected_tree_id: str | None) -> None:
            payload = build_web_payload(
                self._workspace,
                height=int(self.payload.get("view", {}).get("height") or 640),
                title=self.payload.get("title"),
            )
            self.payload = payload
            self.state = {
                **initial_web_state(
                    payload,
                    selected_tree_id=selected_tree_id,
                ),
                "viewMode": "web",
            }

        def _refresh_after_embedded_save(self, selected_entry_id: str) -> None:
            selected_tree = self.selected_tree_id()
            if self._single_profile is not None:
                payload = build_profile_web_payload(
                    self._single_profile,
                    height=int(self.payload.get("view", {}).get("height") or 640),
                    title=self.payload.get("title"),
                )
            else:
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
    from stateframe import sources

    source_imports = sources.auto_register_connections(raise_errors=False)

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
        "sources": sources.list_sources(auto_register=False),
        "source_connections": sources.list_connections(auto_register=False),
        "source_imports": source_imports,
        "settings": workspace.settings(),
    }


def build_profile_web_payload(profile: Any, *, height: int, title: str | None) -> dict[str, Any]:
    """Return a web payload focused on one in-memory profile."""

    from stateframe import sources, workspace

    current_workspace = workspace.current()
    source_imports = sources.auto_register_connections(raise_errors=False)
    tree = _profile_tree_record(profile, current_workspace=current_workspace)
    return {
        "version": 1,
        "title": title or tree["tree_name"] or "stateframe web",
        "view": {
            "height": int(height),
            "launch_mode": "single_profile",
        },
        "workspace": current_workspace.settings(),
        "created_at": None,
        "updated_at": None,
        "tree_count": 1,
        "trees": [_json_safe(tree)],
        "sources": sources.list_sources(auto_register=False),
        "source_connections": sources.list_connections(auto_register=False),
        "source_imports": source_imports,
        "settings": current_workspace.settings(),
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
        "collapsedEntryIds": [],
        "panelWidths": {
            "webLeft": 340,
        },
        "saveMode": False,
        "deleteMode": False,
        "deleteTreeIds": [],
        "deleteEntryIds": [],
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


def _profile_tree_record(profile: Any, *, current_workspace: Any) -> dict[str, Any]:
    ledger = getattr(profile, "ledger", None)
    tree_id = _profile_tree_id(profile)
    tree_name = getattr(profile, "tree_name", None) or getattr(profile, "dataset_name", None) or tree_id
    summary = profile.summary() if hasattr(profile, "summary") else {}
    try:
        from stateframe.workspace import source_fingerprint

        fingerprint = source_fingerprint(profile)
    except Exception:
        fingerprint = None
    return {
        "tree_id": tree_id,
        "tree_name": str(tree_name),
        "dataset_name": getattr(profile, "dataset_name", None),
        "profile_id": getattr(profile, "profile_id", None),
        "source_fingerprint": fingerprint,
        "source": dict(getattr(profile, "source", {}) or {}),
        "target": getattr(profile, "target", None),
        "time": getattr(profile, "time", None),
        "summary": _json_safe(summary),
        "entry_count": len(getattr(ledger, "entries", []) or []),
        "state_count": len(getattr(ledger, "states", {}) or {}),
        "root_entry_id": getattr(ledger, "root_entry_id", None),
        "active_entry_id": getattr(ledger, "active_entry_id", None),
        "tree_path": "in-memory",
        "data_dir": "in-memory",
        "data_snapshots": [],
        "created_at": None,
        "updated_at": None,
        "tree_detail": _tree_detail_from_profile(profile),
        "workspace": current_workspace.settings(),
    }


def _profile_tree_payload(profile: Any) -> dict[str, Any]:
    profile_payload = {
        "profile_id": getattr(profile, "profile_id", None),
        "dataset_name": getattr(profile, "dataset_name", None),
        "tree_name": getattr(profile, "tree_name", None),
        "source": dict(getattr(profile, "source", {}) or {}),
        "profile": profile.to_dict() if hasattr(profile, "to_dict") else {},
        "ledger": (
            profile.ledger.to_dict(include_states=True, include_data=False)
            if getattr(profile, "ledger", None) is not None
            else None
        ),
    }
    return {
        "version": 2,
        "kind": "stateframe_tree",
        "saved_at": None,
        "workspace": {},
        "tree_id": _profile_tree_id(profile),
        "tree_name": getattr(profile, "tree_name", None)
        or getattr(profile, "dataset_name", None)
        or _profile_tree_id(profile),
        "dataset_name": getattr(profile, "dataset_name", None),
        "profile_id": getattr(profile, "profile_id", None),
        "profile": profile_payload,
        "profiles": [profile_payload],
    }


def _build_visualizer_payload(
    profile: Any,
    *,
    record_profile: Any,
    tree_id: str | None,
    tree_name: str | None,
    entry_id: str | None,
    state_id: str | None,
    entry_title: str | None,
    max_rows: int | str | None,
    height: int,
    title: str | None,
) -> dict[str, Any]:
    from stateframe.visualizer import visual_catalog

    preview = build_viewer_payload(
        profile,
        max_rows=_resolve_viewer_max_rows(max_rows, profile.data),
        height=height,
        title=title or "Visual builder",
    )
    return _json_safe(
        {
            "kind": "stateframe_visualizer",
            "engine": "plotly",
            "title": title or f"Visualize {entry_title or tree_name or 'state'}",
            "catalog": visual_catalog(),
            "columns": preview.get("columns", []),
            "rows": preview.get("rows", []),
            "index": preview.get("index", []),
            "view": preview.get("view", {}),
            "context": {
                "tree_id": tree_id,
                "tree_name": tree_name,
                "entry_id": entry_id,
                "state_id": state_id,
                "entry_title": entry_title,
                "record_tree_id": _profile_tree_id(record_profile),
            },
            "lineage": _viewer_lineage(record_profile, entry_id),
        }
    )


def _initial_visualizer_state(payload: dict[str, Any]) -> dict[str, Any]:
    catalog = payload.get("catalog", {})
    plot_types = catalog.get("plot_types") or []
    kind = plot_types[0].get("id") if plot_types else "histogram"
    columns = payload.get("columns") or []
    first = columns[0].get("id") if columns else None
    numeric = next(
        (
            column.get("id")
            for column in columns
            if str(column.get("semantic_type") or "").lower() in {"numeric", "amount", "percentage", "proportion"}
        ),
        first,
    )
    fields = {"x": numeric} if numeric else {}
    return {
        "kind": kind,
        "fields": fields,
        "filters": [],
        "options": {},
        "title": "",
        "note": "",
        "collapsedPanels": {
            "library": False,
            "inspector": False,
        },
        "panelWidths": {
            "library": 260,
            "inspector": 360,
        },
    }


def _spec_from_visualizer_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "renderer": "plotly",
        "kind": state.get("kind") or "histogram",
        "title": state.get("title") or "",
        "note": state.get("note") or "",
        "fields": dict(state.get("fields") or {}),
        "filters": list(state.get("filters") or []),
        "options": dict(state.get("options") or {}),
    }


def _resolve_visual_spec_columns(
    spec: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Translate widget column ids like ``c3`` into dataframe source names."""

    by_id = {
        str(column.get("id")): (
            column.get("source_name")
            or column.get("name")
            or column.get("display_name")
            or column.get("id")
        )
        for column in payload.get("columns", [])
        if column.get("id") is not None
    }

    def resolve(value: Any) -> Any:
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, tuple):
            return [resolve(item) for item in value]
        if isinstance(value, str):
            if value in by_id:
                return by_id[value]
            parts = [part.strip() for part in value.split(",")]
            if len(parts) > 1 and all(part in by_id for part in parts):
                return [by_id[part] for part in parts]
        return value

    fields = {
        key: resolve(value)
        for key, value in dict(spec.get("fields") or {}).items()
    }
    filters = []
    for filter_spec in spec.get("filters") or []:
        if not isinstance(filter_spec, dict):
            continue
        filters.append({
            **filter_spec,
            "column": resolve(filter_spec.get("column")),
        })
    return {
        **spec,
        "fields": fields,
        "filters": filters,
    }


def _profile_matches_tree(workspace: Any, profile: Any | None, tree_id: str | None) -> bool:
    if profile is None or tree_id is None:
        return False
    try:
        return workspace.tree_id_for_profile(profile) == str(tree_id)
    except Exception:
        return False


def _update_tree_payload_entry_note(
    payload: dict[str, Any],
    entry_id: str,
    note: str,
) -> dict[str, Any]:
    updated_entry: dict[str, Any] | None = None
    seen: set[int] = set()
    for ledger in _ledger_payloads(payload):
        marker = id(ledger)
        if marker in seen:
            continue
        seen.add(marker)
        for entry in ledger.get("entries", []) or []:
            if isinstance(entry, dict) and entry.get("id") == entry_id:
                entry["note"] = note
                updated_entry = dict(entry)
    if updated_entry is None:
        raise KeyError(f"Unknown tree entry: {entry_id}")
    return updated_entry


def _ledger_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ledgers: list[dict[str, Any]] = []
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    ledger = profile.get("ledger") if isinstance(profile.get("ledger"), dict) else None
    if ledger is not None:
        ledgers.append(ledger)
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    for profile_payload in profiles:
        if not isinstance(profile_payload, dict):
            continue
        ledger = profile_payload.get("ledger") if isinstance(profile_payload.get("ledger"), dict) else None
        if ledger is not None:
            ledgers.append(ledger)
    return ledgers


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tree_detail_from_profile(profile: Any) -> dict[str, Any]:
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
    active_entry_id = raw.get("active_entry_id")
    enriched_entries = _ledger_entries(entries, states, active_entry_id)
    return _json_safe(
        {
            "root_entry_id": raw.get("root_entry_id"),
            "active_entry_id": active_entry_id,
            "entries": enriched_entries,
            "tree": raw.get("tree") or [],
            "states": states,
            "active_path": _ledger_path(enriched_entries, active_entry_id),
            "stats": _ledger_stats(enriched_entries, states),
            "saved_at": None,
        }
    )


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


def _default_state_save_path(workspace: Any, profile: Any, label: str | None) -> Path:
    tree_id = workspace.tree_id_for_profile(profile) if profile is not None else "floating"
    return workspace.root / "stateframe_saves" / _filename_slug(tree_id) / f"{_filename_slug(label or 'branch')}.parquet"


def _filename_slug(value: Any) -> str:
    import re

    text = str(value or "stateframe").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text or "stateframe"


def _viewer_lineage(profile: Any, entry_id: str | None) -> dict[str, Any]:
    ledger = getattr(profile, "ledger", None)
    if ledger is None or entry_id is None:
        return {"entries": [], "entry_count": 0}
    entries = []
    for entry in ledger.path(entry_id):
        entries.append(
            _json_safe(
                {
                    "id": entry.id,
                    "parent_id": entry.parent_id,
                    "kind": entry.kind,
                    "title": entry.title,
                    "operation": entry.operation,
                    "state_id": entry.state_id,
                    "summary": entry.summary,
                    "params": entry.params,
                    "note": entry.note,
                    "timestamp": entry.timestamp,
                }
            )
        )
    return {
        "entries": entries,
        "entry_count": len(entries),
        "active_entry_id": entry_id,
    }


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
    panel_widths = initial_state.get("panelWidths")
    if isinstance(panel_widths, dict):
        state["panelWidths"] = {
            **state.get("panelWidths", {}),
            **{
                key: int(value)
                for key, value in panel_widths.items()
                if key in {"columns", "inspector"}
                and isinstance(value, (int, float))
                and value > 0
            },
        }
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


def _profile_tree_id(profile: Any) -> str:
    tree_id = getattr(profile, "tree_id", None) or getattr(profile, "workspace_tree_id", None)
    if tree_id:
        return str(tree_id)
    profile_id = getattr(profile, "profile_id", None)
    if profile_id:
        return str(profile_id)
    return "in_memory_tree"


def _ensure_profile_has_live_root_state(profile: Any) -> None:
    if getattr(profile, "ledger", None) is None:
        from stateframe.ledger import LensLedger

        profile.ledger = LensLedger.start(profile)
    ledger = profile.ledger
    root_entry_id = getattr(ledger, "root_entry_id", None)
    if not root_entry_id:
        return
    try:
        root_entry = ledger.get(root_entry_id)
    except KeyError:
        return
    state_id = getattr(root_entry, "state_id", None)
    if not state_id or state_id not in ledger.states:
        return
    state = ledger.states[state_id]
    if getattr(state, "data", None) is None:
        ledger.states[state_id] = replace(state, data=profile.data.copy())


def _profile_checkout(profile: Any, entry_id: str) -> pd.DataFrame:
    _ensure_profile_has_live_root_state(profile)
    try:
        return profile.checkout(entry_id)
    except ValueError:
        if entry_id == getattr(getattr(profile, "ledger", None), "root_entry_id", None):
            return profile.data.copy()
        raise


def _attach_profile_context(
    frame: pd.DataFrame,
    *,
    profile: Any,
    entry: dict[str, Any],
    state: dict[str, Any] | None,
) -> pd.DataFrame:
    context = {
        "tree_id": _profile_tree_id(profile),
        "tree_name": getattr(profile, "tree_name", None),
        "dataset_name": getattr(profile, "dataset_name", None),
        "entry_id": entry.get("id"),
        "state_id": entry.get("state_id") or (state or {}).get("id"),
    }
    frame.attrs["_stateframe"] = {key: value for key, value in context.items() if value}
    return frame


def _profile_for_selected_state(profile: Any, data: pd.DataFrame):
    from stateframe.profile import build_profile

    selected = build_profile(
        data,
        name=getattr(profile, "dataset_name", None),
        target=profile.target if getattr(profile, "target", None) in data.columns else None,
        time=profile.time if getattr(profile, "time", None) in data.columns else None,
        goal=getattr(profile, "goal", "first-look"),
        mode=getattr(profile, "mode", "standard"),
        register=False,
    )
    selected.dataset_name = getattr(profile, "dataset_name", None)
    selected.tree_name = getattr(profile, "tree_name", None)
    selected.source = dict(getattr(profile, "source", {}) or {})
    selected.profile_id = getattr(profile, "profile_id", selected.profile_id)
    selected.ledger = getattr(profile, "ledger", None)
    selected.tree_id = _profile_tree_id(profile)
    return selected


def _pull_title(name: str | None) -> str:
    if name:
        return f"Pull viewer state as {name}"
    return "Pull viewer state"


def _checkpoint_signature(
    view_signature: str,
    *,
    operation: str,
    output_name: str | None,
    message: str | None,
    note: str | None,
) -> str:
    return "|".join(
        [
            view_signature,
            operation or "",
            output_name or "",
            message or "",
            note or "",
        ]
    )


def _state_options(record_profile: Any, data: pd.DataFrame) -> list[dict[str, Any]]:
    try:
        from stateframe.profile import build_profile

        profile = build_profile(
            data,
            target=record_profile.target if record_profile.target in data.columns else None,
            time=record_profile.time if record_profile.time in data.columns else None,
            goal=record_profile.goal,
            mode=record_profile.mode,
            register=False,
        )
        return [recommendation.to_dict() for recommendation in profile.recommendations().top(12)]
    except Exception:
        return []


def _resolve_recommendation(profile: Any, recommendation: int | str | dict[str, Any]):
    recommendations = profile.recommendations()
    if isinstance(recommendation, int):
        top = recommendations.top(max(recommendation, 1))
        if len(top) < recommendation or recommendation < 1:
            raise IndexError(recommendation)
        return top[recommendation - 1]
    if isinstance(recommendation, dict):
        lens = recommendation.get("lens")
        rec_id = recommendation.get("id")
    else:
        lens = recommendation
        rec_id = recommendation
    for rec in recommendations:
        if rec.id == rec_id or rec.lens == lens:
            return rec
    raise ValueError(f"Recommendation not found: {recommendation}")


def _params_from_recommendation(recommendation: Any) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if recommendation.columns:
        first_column = recommendation.columns[0]
        if recommendation.lens.startswith(
            (
                "time.",
                "concentration.",
                "distribution.",
                "categorical.",
                "target.",
                "text.",
            )
        ):
            params["column"] = first_column
    return params


def _selected_view_title(entry: dict[str, Any] | None) -> str:
    title = (entry or {}).get("title")
    return f"View from {title}" if title else "View selected web state"
