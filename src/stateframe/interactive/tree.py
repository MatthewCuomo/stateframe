"""Notebook widget for navigating a stateframe analysis ledger tree."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stateframe.interactive.serialize import build_ledger_payload, initial_ledger_state
from stateframe.models import Profile


ASSET_DIR = Path(__file__).with_name("assets")


class LedgerTreeDependencyError(ImportError):
    """Raised when widget dependencies are not importable."""


try:
    import anywidget
    import traitlets
except ModuleNotFoundError:  # pragma: no cover - exercised through ledger_view()
    anywidget = None
    traitlets = None


if anywidget is not None and traitlets is not None:

    class LedgerTreeViewer(anywidget.AnyWidget):
        """Interactive notebook navigator for a stateframe ledger tree."""

        _esm = ASSET_DIR / "ledger_tree.js"
        _css = ASSET_DIR / "ledger_tree.css"

        payload = traitlets.Dict().tag(sync=True)
        state = traitlets.Dict().tag(sync=True)

        def __init__(
            self,
            profile: Profile,
            *,
            height: int = 640,
            title: str | None = None,
            **kwargs: Any,
        ) -> None:
            self._profile = profile
            payload = build_ledger_payload(
                profile,
                height=height,
                title=title,
            )
            super().__init__(
                payload=payload,
                state=initial_ledger_state(payload),
                **kwargs,
            )

        @property
        def profile(self) -> Profile:
            """The stateframe profile whose ledger powers this tree."""

            return self._profile

        def current_state(self) -> dict[str, Any]:
            """Return the latest synced widget state."""

            return dict(self.state)

        def selected_entry_id(self) -> str | None:
            """Return the currently selected ledger entry id."""

            selected = self.state.get("selectedEntryId")
            return str(selected) if selected else None

        def selected_entry(self):
            """Return the selected ledger entry, if it still exists."""

            selected = self.selected_entry_id()
            if selected is None or self._profile.ledger is None:
                return None
            try:
                return self._profile.ledger.get(selected)
            except KeyError:
                return None

        def selected_state_id(self) -> str | None:
            """Return the dataframe state id for the selected entry, if any."""

            entry = self.selected_entry()
            return getattr(entry, "state_id", None) if entry is not None else None

        def checkout_selected(self):
            """Return a copy of the dataframe state for the selected entry."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No ledger entry is selected.")
            return self._profile.checkout(selected)

        def selected_profile(self) -> Profile:
            """Return a fresh scan profile for the selected dataframe state."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No ledger entry is selected.")
            data = self._profile.checkout(selected)
            return _profile_for_selected_state(self._profile, data)

        def recommendations(self):
            """Return recommendations for the selected dataframe state."""

            return self.selected_profile().recommendations()

        def run_selected(self, lens_id: str, **params: Any):
            """Run a lens on the selected state and record it under that node."""

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No ledger entry is selected.")
            selected_profile = self.selected_profile()

            from stateframe.lenses import run_lens

            result = run_lens(selected_profile, lens_id, **params)
            self._profile.lens_results[result.id] = result
            if self._profile.ledger is not None:
                self._profile.ledger.record_lens(
                    selected_profile,
                    lens_id=result.id,
                    params=params,
                    result=result,
                    parent_id=selected,
                )
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

        def view_selected(
            self,
            *,
            max_rows: int = 25_000,
            height: int = 640,
            theme: str = "auto",
            title: str | None = None,
        ):
            """Open the selected ledger state's dataframe in a new viewer.

            Pulls from the returned viewer are recorded back onto this tree as
            children of the selected ledger entry.
            """

            selected = self.selected_entry_id()
            if selected is None:
                raise ValueError("No ledger entry is selected.")
            data = self._profile.checkout(selected)

            from stateframe.interactive.viewer import DataFrameViewer

            view_profile = _profile_for_selected_state(self._profile, data)
            return DataFrameViewer(
                view_profile,
                record_profile=self._profile,
                ledger_parent_id=selected,
                max_rows=max_rows,
                height=height,
                theme=theme,
                title=title or _selected_view_title(self.selected_entry()),
            )

        def refresh(self) -> None:
            """Rebuild the widget payload from the current profile ledger."""

            payload = build_ledger_payload(
                self._profile,
                height=int(self.payload.get("view", {}).get("height") or 640),
                title=self.payload.get("title"),
            )
            self.payload = payload
            self.state = initial_ledger_state(payload)

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
    """Create a standalone notebook tree view for a stateframe scan ledger."""

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


def _selected_view_title(entry: Any) -> str:
    title = getattr(entry, "title", None)
    if title:
        return f"View from {title}"
    return "View selected ledger state"


def _profile_for_selected_state(profile: Profile, data: Any) -> Profile:
    from stateframe.profile import build_profile

    return build_profile(
        data,
        target=profile.target if profile.target in data.columns else None,
        time=profile.time if profile.time in data.columns else None,
        goal=profile.goal,
        mode=profile.mode,
        register=False,
    )


def _resolve_recommendation(profile: Profile, recommendation: int | str | dict[str, Any]):
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
