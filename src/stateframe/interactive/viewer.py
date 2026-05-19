"""Notebook widget wrapper for the stateframe dataframe explorer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stateframe.interactive.serialize import (
    DEFAULT_MAX_ROWS,
    apply_view_state,
    build_viewer_payload,
    initial_view_state,
    summarize_view_state,
    view_state_signature,
)
from stateframe.models import Profile


ASSET_DIR = Path(__file__).with_name("assets")


class InteractiveDependencyError(ImportError):
    """Raised when widget dependencies are not importable."""


try:
    import anywidget
    import traitlets
except ModuleNotFoundError:  # pragma: no cover - exercised through view()
    anywidget = None
    traitlets = None


if anywidget is not None and traitlets is not None:

    class DataFrameViewer(anywidget.AnyWidget):
        """Interactive dataframe explorer backed by a stateframe ``Profile``."""

        _esm = ASSET_DIR / "viewer.js"
        _css = ASSET_DIR / "viewer.css"

        payload = traitlets.Dict().tag(sync=True)
        state = traitlets.Dict().tag(sync=True)
        branch_request = traitlets.Dict(default_value={}).tag(sync=True)
        branch_status = traitlets.Dict(default_value={}).tag(sync=True)

        def __init__(
            self,
            profile: Profile,
            *,
            record_profile: Profile | None = None,
            ledger_parent_id: str | None = None,
            max_rows: int = DEFAULT_MAX_ROWS,
            height: int = 640,
            theme: str = "auto",
            title: str | None = None,
            **kwargs: Any,
        ) -> None:
            self._profile = profile
            self._record_profile = record_profile or profile
            self._ledger_parent_id = ledger_parent_id
            self._last_branch_request_nonce: Any = None
            payload = build_viewer_payload(
                profile,
                max_rows=max_rows,
                height=height,
                theme=theme,
                title=title,
            )
            if self._record_profile is not profile and self._record_profile.ledger is not None:
                payload["ledger"] = self._record_profile.ledger.to_dict(
                    include_states=True,
                    include_data=False,
                )
            super().__init__(
                payload=payload,
                state=initial_view_state(payload),
                branch_request={},
                branch_status={},
                **kwargs,
            )
            self._last_view_checkpoint_signature: str | None = None
            self._last_view_checkpoint_entry: Any = None

        @property
        def profile(self) -> Profile:
            """The stateframe profile used to power the viewer."""

            return self._profile

        @property
        def record_profile(self) -> Profile:
            """The profile whose ledger receives pulled viewer states."""

            return self._record_profile

        @property
        def ledger_parent_id(self) -> str | None:
            """The ledger entry that the next pulled state will branch from."""

            return self._ledger_parent_id

        def current_state(self) -> dict[str, Any]:
            """Return the latest synced UI state."""

            return dict(self.state)

        def filtered_dataframe(
            self,
            *,
            record: bool = True,
            title: str | None = None,
            operation: str = "viewer.filtered_dataframe",
        ):
            """Return a DataFrame matching the current viewer state.

            ``pull`` is the preferred workflow name; this method remains as a
            compatibility alias.
            """

            return self.pull(
                record=record,
                title=title,
                operation=operation,
            )

        def pull(
            self,
            name: str | None = None,
            *,
            message: str | None = None,
            note: str | None = None,
            record: bool = True,
            title: str | None = None,
            operation: str = "viewer.pull",
        ):
            """Pull the current UI-shaped dataframe back into Python.

            By default this records a ledger checkpoint, so UI filtering,
            sorting, hiding, and reordering become a branch point in the
            analysis tree.

            Parameters
            ----------
            name:
                Optional logical name for the pulled dataframe or branch.
            message:
                Optional short commit-style message describing why this state
                matters.
            note:
                Optional longer note stored on the ledger entry.
            record:
                Set to ``False`` to preview the pulled dataframe without
                changing the ledger.
            """

            result = apply_view_state(self._profile.data, self.payload, self.state)
            entry = None
            if record:
                entry = self._record_current_view(
                    result,
                    title=title or _pull_title(name),
                    operation=operation,
                    force=False,
                    output_name=name,
                    message=message,
                    note=note,
                )
            if entry is not None:
                from stateframe.branch import _attach_dataframe_context

                result = _attach_dataframe_context(
                    result,
                    profile=self._record_profile,
                    entry_id=entry.id,
                )
            return result

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
            """Record the current viewer-shaped dataframe as a ledger state."""

            result = apply_view_state(self._profile.data, self.payload, self.state)
            return self._record_current_view(
                result,
                title=title,
                operation=operation,
                force=force,
                output_name=name,
                message=message,
                note=note,
            )

        def record_current_view(self, **kwargs: Any):
            """Alias for ``save_current_view``."""

            return self.save_current_view(**kwargs)

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
                entry = self.save_current_view(
                    title=request.get("title") or _pull_title(request.get("name")),
                    operation=request.get("operation") or "viewer.save_branch",
                    name=request.get("name"),
                    message=request.get("message"),
                    note=request.get("note"),
                    force=True,
                )
                self._record_profile.save_tree()
                if self._record_profile.ledger is not None:
                    self.payload = {
                        **self.payload,
                        "ledger": self._record_profile.ledger.to_dict(
                            include_states=True,
                            include_data=False,
                        ),
                    }
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

        def last_checkpoint_entry(self):
            """Return the most recent viewer-created ledger entry, if any."""

            return self._last_view_checkpoint_entry

        def selected_column(self) -> str | None:
            """Return the currently inspected source column, if any."""

            selected_id = self.state.get("selectedColumnId")
            for column in self.payload.get("columns", []):
                if column.get("id") == selected_id:
                    return column.get("source_name")
            return None

        def _record_current_view(
            self,
            result,
            *,
            title: str,
            operation: str,
            force: bool,
            output_name: str | None,
            message: str | None,
            note: str | None,
        ):
            signature = view_state_signature(self.payload, self.state)
            checkpoint_signature = _checkpoint_signature(
                signature,
                operation=operation,
                output_name=output_name,
                message=message,
                note=note,
            )
            if (
                not force
                and checkpoint_signature == self._last_view_checkpoint_signature
                and self._last_view_checkpoint_entry is not None
            ):
                return self._last_view_checkpoint_entry
            summary = summarize_view_state(self.payload, self.state, result)
            if output_name:
                summary["output_name"] = output_name
            if message:
                summary["message"] = message
            entry = self._record_profile.record_state(
                result,
                title=title,
                operation=operation,
                parent_id=self._ledger_parent_id,
                note=note or message or "",
                options=_state_options(self._record_profile, result),
                viewer_state=dict(self.state),
                viewer_summary=summary,
                output_name=output_name,
                message=message,
            )
            self._last_view_checkpoint_signature = checkpoint_signature
            self._last_view_checkpoint_entry = entry
            return entry

else:

    class DataFrameViewer:  # pragma: no cover - simple dependency guard
        """Placeholder that explains how to install widget dependencies."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise InteractiveDependencyError(_dependency_message())


def view(
    data_or_profile: Any,
    *,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    scan_depth: str = "standard",
    sample_size: int | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    height: int = 640,
    theme: str = "auto",
    title: str | None = None,
    source_path: str | None = None,
    reader_params: dict[str, Any] | None = None,
) -> DataFrameViewer:
    """Create an interactive dataframe explorer for a DataFrame, file, or scan."""

    _ensure_interactive_dependencies()

    if isinstance(data_or_profile, Profile):
        profile = data_or_profile
    else:
        from stateframe.profile import build_profile

        profile = build_profile(
            data_or_profile,
            name=name,
            target=target,
            time=time,
            task=task,
            goal=goal,
            mode=scan_depth,
            sample_size=sample_size,
            source_path=source_path,
            reader_params=reader_params,
        )

    return DataFrameViewer(
        profile,
        max_rows=max_rows,
        height=height,
        theme=theme,
        title=title,
    )


def _ensure_interactive_dependencies() -> None:
    if anywidget is None or traitlets is None:
        raise InteractiveDependencyError(_dependency_message())


def _dependency_message() -> str:
    return (
        "The stateframe interactive dataframe viewer requires widget "
        "dependencies that ship with the base package. Install or refresh with "
        "`pip install stateframe`, or in this repo with `pip install -e .`."
    )


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


def _state_options(record_profile: Profile, data) -> list[dict[str, Any]]:
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
