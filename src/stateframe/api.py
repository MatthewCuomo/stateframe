"""Top-level user functions."""

from __future__ import annotations

import inspect
from typing import Any

from stateframe.config import EvidenceSource, ExplanationLevel, GuidanceMode, ScanConfig, SemanticPolicy, VisualPolicy
from stateframe.branch import branch
from stateframe.profile import build_profile
from stateframe.footprint import optimize_footprint
from stateframe.leaf import is_save_mode, leaf, register_ipython_magics, save_mode
from stateframe.modeling import build_modeling_plan, default_modeling_experiment_spec, modeling_experiment_catalog, run_modeling_experiment
from stateframe.pull import pull
from stateframe.transforms import (
    add_date_features,
    add_missing_indicators,
    add_ratio,
    apply_suggested_conversions,
    clean_column_name,
    clean_column_names,
    clean_numeric_outliers,
    impute_missing,
    map_values,
    one_hot_encode,
    rename_columns,
    scale_numeric,
    unify_binary_flags,
)
from stateframe.visuals import plot
from stateframe.visualizer import build_visual_artifact, render_visual, visual_catalog, visual_recommendations


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
    register: bool = True,
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
        register=register,
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
    register: bool = True,
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
        register=register,
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
    register: bool = True,
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
        register=register,
    )


def query(
    source: str,
    statement: str,
    *,
    params: dict[str, Any] | None = None,
    name: str | None = None,
    target: str | None = None,
    time: str | None = None,
    task: str | None = None,
    goal: str = "first-look",
    scan_depth: str = "standard",
    sample_size: int | None = None,
    config: ScanConfig | None = None,
    store_query: bool = True,
    store_params: bool = True,
    save_tree: bool = False,
    save_result: bool | None = None,
    result_name: str | None = None,
    **source_kwargs: Any,
):
    """Run a registered data-source query and start a stateframe tree.

    Source providers are registered through ``sf.sources.register(...)``. The
    provider owns credentials and connection logic; stateframe stores query
    lineage and, when ``save_tree=True``, a Parquet snapshot of the returned
    root dataframe so saved query trees can be opened later without rerunning
    the query. Pass ``save_result=False`` to skip the local data snapshot.
    """

    from stateframe import save
    from stateframe import sources
    from stateframe.io import coerce_dataframe

    result = sources.query(
        source,
        statement,
        params=params,
        store_query=store_query,
        store_params=store_params,
        **source_kwargs,
    )
    data = coerce_dataframe(result.data)
    dataset_name = name or result.name or source
    profile = build_profile(
        data,
        name=dataset_name,
        target=target,
        time=time,
        task=task,
        goal=goal,
        mode=scan_depth,
        config=config,
        sample_size=sample_size,
        register=False,
    )
    profile.source = {
        **result.source,
        "input_kind": "query_result",
        "rows": int(data.shape[0]),
        "columns": int(data.shape[1]),
    }
    profile.dataset_name = dataset_name
    profile.tree_name = dataset_name
    save.register_profile(profile)
    should_save_result = bool(save_tree) if save_result is None else bool(save_result)
    if should_save_result:
        profile.save_data(
            name=result_name or "initial_query_result",
            also_save_tree=save_tree,
        )
    elif save_tree:
        profile.save_tree()
    return profile


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
    """Render the unified web UI opened directly to a dataframe viewer.

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
    """Render the unified web UI opened directly to an analysis tree.

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


def visualize(data_or_profile: Any, spec: dict[str, Any] | None = None):
    """Render a Plotly visual from a declarative stateframe visual spec."""

    if spec is None:
        return visual_catalog()
    return render_visual(data_or_profile, spec)


def suggest_visuals(data_or_profile: Any, *, limit: int = 18):
    """Suggest replayable visual specs for a DataFrame or profile."""

    return visual_recommendations(data_or_profile, limit=limit)


def modeling_plan(data_or_profile: Any, **kwargs: Any):
    """Build a previewable modeling-readiness plan for a DataFrame or profile."""

    profile_obj = data_or_profile if hasattr(data_or_profile, "column_profiles") and hasattr(data_or_profile, "data") else scan(data_or_profile)
    return build_modeling_plan(profile_obj, **kwargs)


def modeling_experiment(data_or_profile: Any, spec: dict[str, Any] | None = None, **kwargs: Any):
    """Run a replayable modeling experiment for supervised learning or clustering."""

    profile_obj = data_or_profile if hasattr(data_or_profile, "column_profiles") and hasattr(data_or_profile, "data") else scan(data_or_profile)
    return run_modeling_experiment(profile_obj, spec, **kwargs)


def modeling_catalog() -> dict[str, Any]:
    """Return UI-readable modeling experiment options."""

    return modeling_experiment_catalog()


def default_modeling_spec(data_or_profile: Any, **kwargs: Any):
    """Return a default replayable modeling experiment spec."""

    profile_obj = data_or_profile if hasattr(data_or_profile, "column_profiles") and hasattr(data_or_profile, "data") else scan(data_or_profile)
    return default_modeling_experiment_spec(profile_obj, **kwargs)


def visual_artifact(data_or_profile: Any, spec: dict[str, Any]):
    """Render a visual spec into a ledger-ready Plotly artifact tuple."""

    profile_obj = data_or_profile if hasattr(data_or_profile, "ledger") and hasattr(data_or_profile, "data") else scan(data_or_profile)
    return build_visual_artifact(profile_obj, spec)


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
    "add_date_features",
    "add_missing_indicators",
    "add_ratio",
    "clean_numeric_outliers",
    "clean_column_name",
    "clean_column_names",
    "connect_web",
    "impute_missing",
    "ledger_view",
    "map_values",
    "modeling_plan",
    "modeling_experiment",
    "modeling_catalog",
    "default_modeling_spec",
    "one_hot_encode",
    "plot",
    "profile",
    "pull",
    "query",
    "rename_columns",
    "report",
    "scale_numeric",
    "scan",
    "scan_path",
    "tree_view",
    "optimize_footprint",
    "unify_binary_flags",
    "view",
    "visual_artifact",
    "visual_catalog",
    "suggest_visuals",
    "visualize",
    "web",
    "web_payload",
]
