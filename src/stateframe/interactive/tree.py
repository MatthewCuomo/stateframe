"""Compatibility entry point for the web-backed analysis tree."""

from __future__ import annotations

from typing import Any

from stateframe.models import Profile


class LedgerTreeDependencyError(ImportError):
    """Raised when widget dependencies are not importable."""


try:
    import anywidget  # noqa: F401
    import traitlets  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - exercised through ledger_view()
    anywidget = None
    traitlets = None


if anywidget is not None and traitlets is not None:
    from stateframe.interactive.web import WorkspaceWebViewer

    class LedgerTreeViewer(WorkspaceWebViewer):
        """Web-backed analysis tree opened directly to one profile."""

        def __init__(
            self,
            profile: Profile,
            *,
            height: int = 640,
            title: str | None = None,
            selected_entry_id: str | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(
                profile=profile,
                launch_mode="single_tree",
                selected_entry_id=selected_entry_id,
                height=height,
                title=title,
                **kwargs,
            )

else:

    class LedgerTreeViewer:  # pragma: no cover - simple dependency guard
        """Placeholder that explains how to install widget dependencies."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise LedgerTreeDependencyError(_dependency_message())


def ledger_view(
    data_or_profile: Any,
    *,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    scan_depth: str = "standard",
    sample_size: int | None = None,
    height: int = 640,
    title: str | None = None,
) -> LedgerTreeViewer:
    """Create the unified web UI opened directly to one analysis tree."""

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
        )

    return LedgerTreeViewer(
        profile,
        height=height,
        title=title,
    )


def tree_view(*args: Any, **kwargs: Any) -> LedgerTreeViewer:
    """Alias for ``ledger_view`` for notebook-oriented workflows."""

    return ledger_view(*args, **kwargs)


def _ensure_interactive_dependencies() -> None:
    if anywidget is None or traitlets is None:
        raise LedgerTreeDependencyError(_dependency_message())


def _dependency_message() -> str:
    return (
        "The stateframe ledger tree viewer requires widget dependencies that "
        "ship with the base package. Install or refresh with "
        "`pip install stateframe`, or in this repo with `pip install -e .`."
    )
