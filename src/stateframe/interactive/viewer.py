"""Compatibility entry point for the web-backed dataframe viewer."""

from __future__ import annotations

from typing import Any

from stateframe.interactive.serialize import DEFAULT_MAX_ROWS
from stateframe.models import Profile


class InteractiveDependencyError(ImportError):
    """Raised when widget dependencies are not importable."""


try:
    import anywidget  # noqa: F401
    import traitlets  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - exercised through view()
    anywidget = None
    traitlets = None


if anywidget is not None and traitlets is not None:
    from stateframe.interactive.web import WorkspaceWebViewer

    class DataFrameViewer(WorkspaceWebViewer):
        """Web-backed dataframe explorer opened directly in viewer mode."""

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
            host_profile = record_profile or profile
            selected_entry_id = ledger_parent_id or getattr(getattr(host_profile, "ledger", None), "active_entry_id", None)
            super().__init__(
                profile=host_profile,
                record_profile=record_profile or host_profile,
                ledger_parent_id=selected_entry_id,
                launch_mode="viewer",
                selected_entry_id=selected_entry_id,
                max_rows=max_rows,
                height=height,
                theme=theme,
                title=title,
                **kwargs,
            )

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
    """Create the unified web UI opened directly to the dataframe viewer."""

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


from stateframe.interactive.web import (  # noqa: E402
    _checkpoint_signature,
    _pull_title,
    _state_options,
)
