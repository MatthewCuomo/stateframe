"""Notebook-friendly visual helpers for stateframe scans."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stateframe.models import LensResult, PlotResult, Profile, Recommendation


COLORS = {
    "ink": "#1f2937",
    "muted": "#6b7280",
    "blue": "#2563eb",
    "teal": "#0f766e",
    "green": "#16a34a",
    "gold": "#ca8a04",
    "rose": "#e11d48",
    "slate": "#475569",
    "grid": "#e5e7eb",
}


def plot(
    data_or_profile: Any,
    kind: str = "overview",
    *,
    column: str | None = None,
    target: str | None = None,
    as_result: bool = False,
    **kwargs: Any,
):
    """Plot a DataFrame or existing stateframe scan/profile."""

    from stateframe.api import scan

    profile = data_or_profile if isinstance(data_or_profile, Profile) else scan(data_or_profile)
    if kind in {"overview", "dashboard"}:
        return plot_overview(profile, as_result=as_result, **kwargs)
    if kind in {"missingness", "quality.missingness"}:
        return plot_missingness(profile, as_result=as_result, **kwargs)
    if kind in {"target_candidates", "target.candidates"}:
        return plot_target_candidates(profile, as_result=as_result, **kwargs)
    if kind in {"recommendation", "recommended"}:
        return plot_recommendation(profile, column if column is not None else 1, as_result=as_result, **kwargs)
    if kind in {"column", "auto"}:
        if column is None:
            raise ValueError("kind='column' requires column=...")
        return plot_column(profile, column, target=target, as_result=as_result, **kwargs)
    if kind in {"distribution.numeric", "numeric", "histogram"}:
        if column is None:
            raise ValueError("numeric plot requires column=...")
        return plot_numeric(profile, column, as_result=as_result, **kwargs)
    if kind in {"categorical.value_counts", "categorical", "value_counts"}:
        if column is None:
            raise ValueError("categorical plot requires column=...")
        return plot_categorical(profile, column, as_result=as_result, **kwargs)
    if kind in {"binary.flags", "binary"}:
        return plot_binary_flags(profile, column=column, as_result=as_result, **kwargs)
    if kind in {"time.cadence", "time", "records_over_time"}:
        if column is None:
            column = profile.time or (profile.time_candidates()[0].column if profile.time_candidates() else None)
        if column is None:
            raise ValueError("time plot requires a datetime-like column")
        return plot_records_over_time(profile, column, as_result=as_result, **kwargs)
    if kind in {"target.balance", "target"}:
        target = target or column or profile.target
        if target is None:
            raise ValueError("target balance plot requires target=... or column=...")
        return plot_target_balance(profile, target, as_result=as_result, **kwargs)
    if kind in {"target.associations", "associations"}:
        target = target or column or profile.target
        if target is None:
            raise ValueError("target association plot requires target=... or column=...")
        return plot_target_associations(profile, target, as_result=as_result, **kwargs)
    if kind in {"target.importance", "importance"}:
        target = target or column or profile.target
        if target is None:
            raise ValueError("target importance plot requires target=... or column=...")
        return plot_target_importance(profile, target, as_result=as_result, **kwargs)
    if kind in {"concentration.lorenz", "lorenz", "concentration"}:
        if column is None:
            raise ValueError("concentration plot requires column=...")
        return plot_lorenz(profile, column, as_result=as_result, **kwargs)
    if kind in {"relationships.mixed_associations", "mixed_associations"}:
        return plot_mixed_associations(profile, as_result=as_result, **kwargs)
    raise ValueError(f"Unknown plot kind: {kind}")


def plot_overview(profile: Profile, *, as_result: bool = False):
    plt = _plt()
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.patch.set_facecolor("white")

    _plot_type_counts(profile, axes[0, 0])
    _plot_missingness_axis(profile, axes[0, 1], limit=12)
    _plot_recommendation_categories(profile, axes[1, 0])
    _plot_role_cards(profile, axes[1, 1])

    fig.suptitle("stateframe scan overview", fontsize=18, fontweight="bold", color=COLORS["ink"])
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _plot_result(
        fig,
        as_result=as_result,
        id="overview",
        title="stateframe scan overview",
        source_lens="overview.summary",
        description="A compact dashboard of inferred types, missingness, recommendations, and candidate roles.",
    )


def plot_missingness(profile: Profile, limit: int = 25, *, as_result: bool = False):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(11, max(4, min(10, limit * 0.34))))
    _plot_missingness_axis(profile, ax, limit=limit)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id="quality.missingness", title="Missingness profile", source_lens="quality.missingness")


def plot_target_candidates(profile: Profile, limit: int = 10, *, as_result: bool = False):
    plt = _plt()
    candidates = profile.target_candidates()[:limit]
    fig, ax = plt.subplots(figsize=(10, max(3.5, len(candidates) * 0.45)))
    if not candidates:
        _empty_axis(ax, "No target candidates found")
        return _plot_result(fig, as_result=as_result, id="target.candidates", title="Target candidates", source_lens="target.candidates")
    names = [candidate.column for candidate in candidates][::-1]
    scores = [candidate.confidence for candidate in candidates][::-1]
    ax.barh(names, scores, color=COLORS["blue"], alpha=0.86)
    ax.set_xlim(0, 1)
    ax.set_xlabel("confidence")
    ax.set_title("Possible target columns", loc="left", fontweight="bold")
    _style_axis(ax)
    return _plot_result(fig, as_result=as_result, id="target.candidates", title="Target candidates", source_lens="target.candidates")


def plot_column(profile: Profile, column: str, *, target: str | None = None, as_result: bool = False):
    semantic_type = profile.column(column).semantic_type
    if semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"}:
        return plot_numeric(profile, column, as_result=as_result)
    if semantic_type in {"datetime", "datetime-like"}:
        return plot_records_over_time(profile, column, as_result=as_result)
    if profile.column(column).binary_profile is not None:
        return plot_binary_flags(profile, column=column, as_result=as_result)
    if semantic_type in {"category", "string", "postal_code", "geographic"}:
        return plot_categorical(profile, column, as_result=as_result)
    if semantic_type == "text":
        return plot_text_lengths(profile, column, as_result=as_result)
    return plot_categorical(profile, column, as_result=as_result)


def plot_recommendation(
    profile: Profile,
    recommendation: int | str | Recommendation = 1,
    *,
    as_result: bool = False,
):
    rec = _resolve_recommendation(profile, recommendation)
    if rec.lens == "quality.missingness":
        return plot_missingness(profile, as_result=as_result)
    if rec.lens == "target.candidates":
        return plot_target_candidates(profile, as_result=as_result)
    if rec.lens == "distribution.numeric":
        return plot_numeric(profile, rec.columns[0], as_result=as_result)
    if rec.lens == "categorical.value_counts":
        return plot_categorical(profile, rec.columns[0], as_result=as_result)
    if rec.lens == "binary.flags":
        return plot_binary_flags(profile, column=rec.columns[0] if rec.columns else None, as_result=as_result)
    if rec.lens == "time.cadence":
        return plot_records_over_time(profile, rec.columns[0], as_result=as_result)
    if rec.lens == "target.balance":
        return plot_target_balance(profile, rec.columns[0], as_result=as_result)
    if rec.lens == "target.associations":
        return plot_target_associations(profile, rec.columns[0] if rec.columns else None, as_result=as_result)
    if rec.lens == "target.importance":
        return plot_target_importance(profile, rec.columns[0] if rec.columns else None, as_result=as_result)
    if rec.lens == "concentration.lorenz":
        return plot_lorenz(profile, rec.columns[0], as_result=as_result)
    if rec.lens == "relationships.correlation":
        return plot_correlation(profile, as_result=as_result)
    if rec.lens == "relationships.mixed_associations":
        return plot_mixed_associations(profile, as_result=as_result)
    return plot_column(profile, rec.columns[0], as_result=as_result) if rec.columns else plot_overview(profile, as_result=as_result)


def plot_recommendations(profile: Profile, n: int = 4, *, as_result: bool = False) -> list[Any]:
    return [plot_recommendation(profile, rec, as_result=as_result) for rec in profile.recommendations().top(n)]


def plot_numeric(profile: Profile, column: str, bins: int = 50, *, as_result: bool = False):
    plt = _plt()
    values = pd.to_numeric(profile.data[column], errors="coerce").dropna()
    values = values[np.isfinite(values)]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw={"width_ratios": [2.2, 1]})
    if values.empty:
        _empty_axis(axes[0], f"No numeric values for {column}")
        _empty_axis(axes[1], "")
        return _plot_result(fig, as_result=as_result, id=f"distribution.numeric.{column}", title=f"{column} distribution", source_lens="distribution.numeric")

    ax = axes[0]
    ax.hist(values, bins=bins, color=COLORS["blue"], alpha=0.82, edgecolor="white")
    median = values.median()
    p95 = values.quantile(0.95)
    ax.axvline(median, color=COLORS["rose"], linewidth=2, label=f"median {median:,.0f}")
    ax.axvline(p95, color=COLORS["gold"], linewidth=2, linestyle="--", label=f"p95 {p95:,.0f}")
    ax.set_title(f"{column} distribution", loc="left", fontweight="bold")
    ax.set_ylabel("rows")
    ax.legend(frameon=False)
    _style_axis(ax)

    ax = axes[1]
    quantiles = values.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    labels = ["p01", "p05", "p25", "p50", "p75", "p95", "p99"]
    ax.barh(labels, quantiles.values, color=COLORS["teal"], alpha=0.84)
    ax.set_title("quantiles", loc="left", fontweight="bold")
    _style_axis(ax)

    fig.tight_layout()
    return _plot_result(
        fig,
        as_result=as_result,
        id=f"distribution.numeric.{column}",
        title=f"{column} distribution",
        source_lens="distribution.numeric",
        interpretation_hints=["Compare the median, upper tail, and quantiles before trusting the mean."],
    )


def plot_categorical(profile: Profile, column: str, limit: int = 20, *, as_result: bool = False):
    plt = _plt()
    counts = profile.data[column].value_counts(dropna=False).head(limit)
    fig, ax = plt.subplots(figsize=(11, max(4, len(counts) * 0.42)))
    labels = [_shorten(str(value), 42) for value in counts.index.tolist()][::-1]
    values = counts.values[::-1]
    ax.barh(labels, values, color=COLORS["teal"], alpha=0.84)
    ax.set_title(f"{column} value counts", loc="left", fontweight="bold")
    ax.set_xlabel("rows")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=f"categorical.value_counts.{column}", title=f"{column} value counts", source_lens="categorical.value_counts")


def plot_binary_flags(profile: Profile, column: str | None = None, *, as_result: bool = False):
    plt = _plt()
    flags = profile.binary_flags()
    if column:
        flags = {column: flags[column]} if column in flags else {}
    fig, ax = plt.subplots(figsize=(10, max(3.5, len(flags) * 0.45)))
    if not flags:
        _empty_axis(ax, "No binary flags detected")
        return _plot_result(fig, as_result=as_result, id="binary.flags", title="Binary flag rates", source_lens="binary.flags")
    names = []
    true_rates = []
    missing_rates = []
    for name, binary_profile in flags.items():
        series = profile.data[name]
        mapped = series.map(binary_profile.suggested_mapping)
        names.append(name)
        true_rates.append(float((mapped == 1).mean()))
        missing_rates.append(float(mapped.isna().mean()))
    order = np.argsort(true_rates)
    names = [names[i] for i in order]
    true_rates = [true_rates[i] for i in order]
    missing_rates = [missing_rates[i] for i in order]
    ax.barh(names, true_rates, color=COLORS["green"], alpha=0.82, label="true / yes")
    ax.barh(names, missing_rates, left=true_rates, color=COLORS["slate"], alpha=0.25, label="missing/unmapped")
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of rows")
    ax.set_title("Binary flag rates", loc="left", fontweight="bold")
    ax.legend(frameon=False)
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id="binary.flags", title="Binary flag rates", source_lens="binary.flags")


def plot_records_over_time(profile: Profile, column: str, freq: str = "ME", *, as_result: bool = False):
    plt = _plt()
    values = pd.to_datetime(profile.data[column], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(12, 4.8))
    if values.empty:
        _empty_axis(ax, f"No datetime values for {column}")
        return _plot_result(fig, as_result=as_result, id=f"time.records_over_time.{column}", title=f"Records over time by {column}", source_lens="time.cadence")
    counts = values.dt.to_period(freq).dt.to_timestamp().value_counts().sort_index()
    ax.plot(counts.index, counts.values, color=COLORS["blue"], linewidth=2.5)
    ax.fill_between(counts.index, counts.values, color=COLORS["blue"], alpha=0.15)
    ax.set_title(f"Records over time by {column}", loc="left", fontweight="bold")
    ax.set_ylabel("rows")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=f"time.records_over_time.{column}", title=f"Records over time by {column}", source_lens="time.cadence")


def plot_target_balance(profile: Profile, target: str, limit: int = 25, *, as_result: bool = False):
    column_profile = profile.column(target)
    if column_profile.semantic_type in {"numeric", "amount", "numeric-like"} and column_profile.distinct_count > limit:
        return plot_numeric(profile, target, as_result=as_result)
    return plot_categorical(profile, target, limit=limit, as_result=as_result)


def plot_target_associations(profile: Profile, target: str | None = None, limit: int = 15, *, as_result: bool = False):
    plt = _plt()
    target = target or profile.target
    if target is None:
        raise ValueError("target association plot requires a selected target")
    result = profile.run("target.associations", column=target)
    rows = result.data.get("associations", [])[:limit]
    fig, ax = plt.subplots(figsize=(11, max(4, len(rows) * 0.42)))
    if not rows:
        _empty_axis(ax, "No target associations found")
        return _plot_result(fig, as_result=as_result, id=f"target.associations.{target}", title=f"Top associations with {target}", source_lens="target.associations")
    labels = [row["column"] for row in rows][::-1]
    scores = [abs(float(row.get("score") or 0.0)) for row in rows][::-1]
    colors = [
        COLORS["blue"] if row.get("kind") == "numeric_vs_target" else COLORS["teal"]
        for row in rows
    ][::-1]
    ax.barh(labels, scores, color=colors, alpha=0.84)
    ax.set_title(f"Top associations with {target}", loc="left", fontweight="bold")
    ax.set_xlabel("association strength")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=f"target.associations.{target}", title=f"Top associations with {target}", source_lens="target.associations")


def plot_target_importance(profile: Profile, target: str | None = None, limit: int = 15, *, as_result: bool = False):
    plt = _plt()
    target = target or profile.target
    if target is None:
        raise ValueError("target importance plot requires a selected target")
    result = profile.run("target.importance", target=target)
    rows = result.data.get("feature_importance", [])[:limit]
    fig, ax = plt.subplots(figsize=(11, max(4, len(rows) * 0.42)))
    if not rows:
        _empty_axis(ax, "No target importance results")
        return _plot_result(fig, as_result=as_result, id=f"target.importance.{target}", title=f"Feature importance for {target}", source_lens="target.importance")
    value_key = "importance" if "importance" in rows[0] else "permutation_importance"
    labels = [row["feature"] for row in rows][::-1]
    values = [abs(float(row.get(value_key) or 0.0)) for row in rows][::-1]
    ax.barh(labels, values, color=COLORS["blue"], alpha=0.84)
    ax.set_title(f"Feature importance for {target}", loc="left", fontweight="bold")
    ax.set_xlabel(value_key.replace("_", " "))
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(
        fig,
        as_result=as_result,
        id=f"target.importance.{target}",
        title=f"Feature importance for {target}",
        source_lens="target.importance",
        interpretation_hints=["Treat this as exploratory signal, not causal proof."],
        data=result.data,
    )


def plot_mixed_associations(profile: Profile, limit: int = 20, *, as_result: bool = False):
    plt = _plt()
    result = profile.run("relationships.mixed_associations", limit=limit)
    rows = result.data.get("associations", [])[:limit]
    fig, ax = plt.subplots(figsize=(11, max(4, len(rows) * 0.44)))
    if not rows:
        _empty_axis(ax, "No mixed associations found")
        return _plot_result(fig, as_result=as_result, id="relationships.mixed_associations", title="Mixed associations", source_lens="relationships.mixed_associations")
    labels = [f"{row['left']} / {row['right']}" for row in rows][::-1]
    values = [abs(float(row.get("strength") or 0.0)) for row in rows][::-1]
    colors = [
        COLORS["blue"] if row.get("kind") == "numeric_numeric" else COLORS["teal"]
        for row in rows
    ][::-1]
    ax.barh(labels, values, color=colors, alpha=0.84)
    ax.set_title("Strongest mixed associations", loc="left", fontweight="bold")
    ax.set_xlabel("association strength")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id="relationships.mixed_associations", title="Mixed associations", source_lens="relationships.mixed_associations", data=result.data)


def plot_lorenz(profile: Profile, column: str, *, as_result: bool = False):
    plt = _plt()
    result = profile.run("concentration.lorenz", column=column)
    curve = pd.DataFrame(result.data["curve"])
    fig, ax = plt.subplots(figsize=(6.5, 6))
    if curve.empty:
        _empty_axis(ax, f"No nonnegative values for {column}")
        return _plot_result(fig, as_result=as_result, id=f"concentration.lorenz.{column}", title=f"{column} concentration", source_lens="concentration.lorenz")
    ax.plot(curve["cumulative_row_share"], curve["cumulative_value_share"], color=COLORS["blue"], linewidth=2.5)
    ax.plot([0, 1], [0, 1], color=COLORS["muted"], linestyle="--", linewidth=1.4)
    ax.set_title(f"{column} concentration", loc="left", fontweight="bold")
    ax.set_xlabel("cumulative share of rows")
    ax.set_ylabel("cumulative share of value")
    ax.text(
        0.04,
        0.92,
        f"gini: {result.data.get('gini', 0):.3f}\ntop 10%: {result.data.get('top_10pct_share', 0):.1%}",
        transform=ax.transAxes,
        fontsize=10,
        color=COLORS["ink"],
        bbox={"facecolor": "white", "edgecolor": COLORS["grid"], "boxstyle": "round,pad=0.35"},
    )
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=f"concentration.lorenz.{column}", title=f"{column} concentration", source_lens="concentration.lorenz", data=result.data)


def plot_correlation(profile: Profile, limit: int = 20, *, as_result: bool = False):
    plt = _plt()
    numeric_cols = [
        name
        for name, column in profile.column_profiles.items()
        if column.semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion"}
    ][:limit]
    corr = profile.data[numeric_cols].apply(pd.to_numeric, errors="coerce").corr() if len(numeric_cols) >= 2 else pd.DataFrame()
    fig, ax = plt.subplots(figsize=(9, 8))
    if corr.empty:
        _empty_axis(ax, "Not enough numeric columns for correlation")
        return _plot_result(fig, as_result=as_result, id="relationships.correlation", title="Numeric correlation", source_lens="relationships.correlation")
    image = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)), [_shorten(col, 18) for col in corr.columns], rotation=60, ha="right")
    ax.set_yticks(range(len(corr.index)), [_shorten(col, 18) for col in corr.index])
    ax.set_title("Numeric correlation", loc="left", fontweight="bold")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id="relationships.correlation", title="Numeric correlation", source_lens="relationships.correlation")


def plot_text_lengths(profile: Profile, column: str, *, as_result: bool = False):
    plt = _plt()
    values = profile.data[column].dropna().astype("string")
    lengths = values.str.len()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.hist(lengths, bins=40, color=COLORS["blue"], alpha=0.82, edgecolor="white")
    ax.set_title(f"{column} text lengths", loc="left", fontweight="bold")
    ax.set_xlabel("characters")
    ax.set_ylabel("rows")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=f"text.lengths.{column}", title=f"{column} text lengths", source_lens="text.lengths")


def plot_lens_result(result: LensResult, *, as_result: bool = False):
    if result.id == "target.importance":
        return _plot_importance_result(result, as_result=as_result)
    if result.id == "relationships.mixed_associations":
        return _plot_association_result(result, as_result=as_result)
    raise ValueError(f"No standalone plot renderer for lens result: {result.id}")


def _plot_importance_result(result: LensResult, *, as_result: bool = False):
    plt = _plt()
    rows = result.data.get("feature_importance", [])[:15]
    fig, ax = plt.subplots(figsize=(11, max(4, len(rows) * 0.42)))
    if not rows:
        _empty_axis(ax, "No feature importance results")
        return _plot_result(fig, as_result=as_result, id=result.id, title=result.title, source_lens=result.id)
    value_key = "importance" if "importance" in rows[0] else "permutation_importance"
    ax.barh([row["feature"] for row in rows][::-1], [abs(float(row.get(value_key) or 0.0)) for row in rows][::-1], color=COLORS["blue"], alpha=0.84)
    ax.set_title(result.title, loc="left", fontweight="bold")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=result.id, title=result.title, source_lens=result.id, data=result.data)


def _plot_association_result(result: LensResult, *, as_result: bool = False):
    plt = _plt()
    rows = result.data.get("associations", [])[:20]
    fig, ax = plt.subplots(figsize=(11, max(4, len(rows) * 0.44)))
    if not rows:
        _empty_axis(ax, "No association results")
        return _plot_result(fig, as_result=as_result, id=result.id, title=result.title, source_lens=result.id)
    ax.barh([f"{row['left']} / {row['right']}" for row in rows][::-1], [abs(float(row.get("strength") or 0.0)) for row in rows][::-1], color=COLORS["teal"], alpha=0.84)
    ax.set_title(result.title, loc="left", fontweight="bold")
    _style_axis(ax)
    fig.tight_layout()
    return _plot_result(fig, as_result=as_result, id=result.id, title=result.title, source_lens=result.id, data=result.data)


def _plot_type_counts(profile: Profile, ax: Any) -> None:
    counts = pd.Series(profile.summary()["columns_by_type"]).sort_values()
    ax.barh(counts.index, counts.values, color=COLORS["blue"], alpha=0.84)
    ax.set_title("Inferred column types", loc="left", fontweight="bold")
    ax.set_xlabel("columns")
    _style_axis(ax)


def _plot_missingness_axis(profile: Profile, ax: Any, limit: int) -> None:
    rows = [
        {"column": column.name, "missing_ratio": column.missing_ratio}
        for column in profile.column_profiles.values()
        if column.missing_ratio > 0
    ]
    data = pd.DataFrame(rows).sort_values("missing_ratio", ascending=False).head(limit)
    if data.empty:
        _empty_axis(ax, "No missing values detected")
        return
    data = data.iloc[::-1]
    ax.barh(data["column"], data["missing_ratio"], color=COLORS["rose"], alpha=0.78)
    ax.set_xlim(0, max(1.0, float(data["missing_ratio"].max()) * 1.05))
    ax.set_xlabel("missing share")
    ax.set_title("Top missing columns", loc="left", fontweight="bold")
    _style_axis(ax)


def _plot_recommendation_categories(profile: Profile, ax: Any) -> None:
    categories = pd.Series([rec.category for rec in profile.recommendations().top(30)]).value_counts().sort_values()
    if categories.empty:
        _empty_axis(ax, "No recommendations")
        return
    ax.barh(categories.index, categories.values, color=COLORS["teal"], alpha=0.84)
    ax.set_title("Recommendation focus", loc="left", fontweight="bold")
    ax.set_xlabel("top recommendations")
    _style_axis(ax)


def _plot_role_cards(profile: Profile, ax: Any) -> None:
    ax.axis("off")
    summary = profile.summary()
    candidates = profile.target_candidates()[:3]
    times = profile.time_candidates()[:3]
    shapes = profile.shapes()[:3]
    shape_lines = [f"- {shape.id} ({shape.confidence:.2f})" for shape in shapes] or ["- none found"]
    candidate_lines = [
        f"- {candidate.column} ({candidate.inferred_task}, {candidate.confidence:.2f})"
        for candidate in candidates
    ] or ["- none found"]
    time_lines = [f"- {candidate.column} ({candidate.confidence:.2f})" for candidate in times] or ["- none found"]
    lines = [
        f"Rows: {summary['row_count']:,}",
        f"Columns: {summary['column_count']:,}",
        f"Missing cells: {summary['missing_cell_ratio']:.1%}",
        "",
        "Likely shapes:",
        *shape_lines,
        "",
        "Target candidates:",
        *candidate_lines,
        "",
        "Time candidates:",
        *time_lines,
    ]
    ax.text(
        0,
        1,
        "\n".join(lines),
        va="top",
        ha="left",
        fontsize=11,
        color=COLORS["ink"],
        bbox={"facecolor": "#f8fafc", "edgecolor": COLORS["grid"], "boxstyle": "round,pad=0.55"},
    )
    ax.set_title("What stateframe thinks this is", loc="left", fontweight="bold")


def _resolve_recommendation(profile: Profile, recommendation: int | str | Recommendation) -> Recommendation:
    if isinstance(recommendation, Recommendation):
        return recommendation
    recs = profile.recommendations().top(100)
    if isinstance(recommendation, int):
        if recommendation < 1:
            raise ValueError("Recommendation numbers are 1-based.")
        return recs[recommendation - 1]
    for rec in recs:
        if rec.id == recommendation or rec.lens == recommendation:
            return rec
    raise ValueError(f"Unknown recommendation: {recommendation}")


def _plot_result(
    fig: Any,
    *,
    as_result: bool,
    id: str,
    title: str,
    source_lens: str | None = None,
    description: str = "",
    interpretation_hints: list[str] | None = None,
    data: Any = None,
) -> Any:
    if not as_result:
        return fig
    return PlotResult(
        id=id,
        title=title,
        figure=fig,
        data=data,
        description=description,
        interpretation_hints=interpretation_hints or [],
        source_lens=source_lens,
    )


def _style_axis(ax: Any) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["grid"])
    ax.spines["bottom"].set_color(COLORS["grid"])
    ax.grid(axis="x", color=COLORS["grid"], linewidth=0.8, alpha=0.8)
    ax.tick_params(colors=COLORS["ink"])
    ax.title.set_color(COLORS["ink"])


def _empty_axis(ax: Any, message: str) -> None:
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", color=COLORS["muted"], fontsize=12)


def _shorten(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "..."


def _plt():
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelcolor": COLORS["ink"],
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
        }
    )
    return plt
