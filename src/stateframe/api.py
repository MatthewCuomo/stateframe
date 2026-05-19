"""Top-level user functions."""

from __future__ import annotations

import inspect
from typing import Any

from stateframe.config import EvidenceSource, ExplanationLevel, GuidanceMode, ScanConfig, SemanticPolicy, VisualPolicy
from stateframe.branch import branch
from stateframe.profile import build_profile
from stateframe.footprint import optimize_footprint
from stateframe.transforms import apply_suggested_conversions, unify_binary_flags
from stateframe.visuals import plot


def connect_web(
    *,
    start: str | None = None,
    height: int = 640,
    title: str | None = None,
):
    """Connect to the nearest workspace and open its web widget."""

    from stateframe import workspace

    workspace.connect(start=start)
    return web(height=height, title=title)


def profile(
    data: Any,
    *,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    mode: str = "standard",
    config: ScanConfig | None = None,
    sample_size: int | None = None,
    guidance: GuidanceMode | None = None,
    semantic_policy: SemanticPolicy | None = None,
    recommendation_basis: list[EvidenceSource] | None = None,
    visual_policy: VisualPolicy | None = None,
    explanation_level: ExplanationLevel | None = None,
    source_path: str | None = None,
    reader_params: dict[str, Any] | None = None,
):
    """Profile a DataFrame-like object.

    The first implementation supports pandas DataFrames directly and Polars
    DataFrames through ``to_pandas`` when available.
    """

    if config is None and any(
        value is not None
        for value in [
            guidance,
            semantic_policy,
            recommendation_basis,
            visual_policy,
            explanation_level,
        ]
    ):
        config = ScanConfig.from_mode(
            mode,
            sample_size=sample_size,
            guidance=guidance,
            semantic_policy=semantic_policy,
            recommendation_basis=recommendation_basis,
            visual_policy=visual_policy,
            explanation_level=explanation_level,
        )

    if name is None:
        name = _infer_data_name(data)

    return build_profile(
        data,
        name=name,
        target=target,
        time=time,
        task=task,
        goal=goal,
        mode=mode,
        config=config,
        sample_size=sample_size,
        source_path=source_path,
        reader_params=reader_params,
    )


def scan(
    data: Any,
    *,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    scan_depth: str = "standard",
    sample_size: int | None = None,
    config: ScanConfig | None = None,
    guidance: GuidanceMode | None = None,
    semantic_policy: SemanticPolicy | None = None,
    recommendation_basis: list[EvidenceSource] | None = None,
    visual_policy: VisualPolicy | None = None,
    explanation_level: ExplanationLevel | None = None,
    source_path: str | None = None,
    reader_params: dict[str, Any] | None = None,
):
    """Run the initial stateframe scan.

    ``scan`` is the concept-forward alias for ``profile``. It returns the same
    rich ``Profile`` object so existing code can use either naming style.
    """

    if config is None:
        config = ScanConfig.from_mode(
            scan_depth,
            sample_size=sample_size,
            guidance=guidance,
            semantic_policy=semantic_policy,
            recommendation_basis=recommendation_basis,
            visual_policy=visual_policy,
            explanation_level=explanation_level,
        )

    if name is None:
        name = _infer_data_name(data)

    return build_profile(
        data,
        name=name,
        target=target,
        time=time,
        task=task,
        goal=goal,
        mode=scan_depth,
        config=config,
        sample_size=sample_size,
        source_path=source_path,
        reader_params=reader_params,
    )


def scan_path(
    path: str,
    *,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    scan_depth: str = "standard",
    sample_size: int | None = None,
    config: ScanConfig | None = None,
    guidance: GuidanceMode | None = None,
    semantic_policy: SemanticPolicy | None = None,
    recommendation_basis: list[EvidenceSource] | None = None,
    visual_policy: VisualPolicy | None = None,
    explanation_level: ExplanationLevel | None = None,
    reader_params: dict[str, Any] | None = None,
):
    """Scan a local data path and record it as the tree's replayable root."""

    return scan(
        path,
        name=name,
        target=target,
        time=time,
        task=task,
        goal=goal,
        scan_depth=scan_depth,
        sample_size=sample_size,
        config=config,
        guidance=guidance,
        semantic_policy=semantic_policy,
        recommendation_basis=recommendation_basis,
        visual_policy=visual_policy,
        explanation_level=explanation_level,
        reader_params=reader_params,
    )


def view(
    data: Any,
    *,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    scan_depth: str = "standard",
    sample_size: int | None = None,
    max_rows: int = 25_000,
    height: int = 640,
    theme: str = "auto",
    title: str | None = None,
    source_path: str | None = None,
    reader_params: dict[str, Any] | None = None,
):
    """Render an interactive dataframe explorer in a notebook frontend.

    The widget dependencies ship with the base ``stateframe`` install.
    """

    from stateframe.interactive import view as interactive_view

    if name is None:
        name = _infer_data_name(data)

    return interactive_view(
        data,
        name=name,
        target=target,
        time=time,
        task=task,
        goal=goal,
        scan_depth=scan_depth,
        sample_size=sample_size,
        source_path=source_path,
        reader_params=reader_params,
        max_rows=max_rows,
        height=height,
        theme=theme,
        title=title,
    )


def ledger_view(
    data: Any,
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
):
    """Render a notebook-native analysis tree for a stateframe ledger.

    The widget dependencies ship with the base ``stateframe`` install.
    """

    from stateframe.interactive import ledger_view as interactive_ledger_view

    if name is None:
        name = _infer_data_name(data)

    return interactive_ledger_view(
        data,
        name=name,
        target=target,
        time=time,
        task=task,
        goal=goal,
        scan_depth=scan_depth,
        sample_size=sample_size,
        height=height,
        title=title,
    )


def tree_view(*args: Any, **kwargs: Any):
    """Alias for ``ledger_view``."""

    return ledger_view(*args, **kwargs)


def report(data_or_profile: Any, path: str | None = None) -> str:
    """Render a simple Markdown report for a DataFrame or existing profile."""

    if hasattr(data_or_profile, "to_markdown") and hasattr(data_or_profile, "summary"):
        result = data_or_profile
    else:
        result = scan(data_or_profile)
    text = result.to_markdown()
    if path is not None:
        from pathlib import Path

        Path(path).write_text(text, encoding="utf-8")
    return text


def web(*, height: int = 640, title: str | None = None):
    """Render the active workspace web as a notebook widget."""

    from stateframe.interactive import web_view

    return web_view(height=height, title=title)


def web_payload() -> dict[str, Any]:
    """Return the raw active workspace web metadata."""

    from stateframe import workspace

    return workspace.web()


def _infer_data_name(data: Any) -> str | None:
    """Best-effort dataframe variable-name inference for friendly tree names."""

    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame is not None and frame.f_back is not None else None
    if caller is None:
        return None
    for name, value in caller.f_locals.items():
        if name.startswith("_"):
            continue
        if value is data:
            return name
    return None


__all__ = [
    "apply_suggested_conversions",
    "branch",
    "connect_web",
    "ledger_view",
    "plot",
    "profile",
    "report",
    "scan",
    "scan_path",
    "tree_view",
    "optimize_footprint",
    "unify_binary_flags",
    "view",
    "web",
    "web_payload",
]
