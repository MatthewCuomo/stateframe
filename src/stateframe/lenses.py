"""Focused diagnostic lenses."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stateframe.models import Issue, LensResult, Profile
from stateframe.lens_registry import resolve_lens_id
from stateframe.utils import clean_metric, clean_metrics


def run_lens(profile: Profile, lens_id: str, **params: Any) -> LensResult:
    lens_id = resolve_lens_id(lens_id)
    if lens_id == "quality.missingness":
        return missingness(profile)
    if lens_id == "quality.type_coercion":
        return type_coercion(profile)
    if lens_id == "time.cadence":
        return time_cadence(profile, **params)
    if lens_id == "grain.keys":
        return grain_keys(profile)
    if lens_id == "concentration.lorenz":
        return concentration_lorenz(profile, **params)
    if lens_id == "relationships.correlation":
        return correlation(profile)
    if lens_id == "relationships.mixed_associations":
        return mixed_associations(profile, **params)
    if lens_id == "target.balance":
        return target_balance(profile, **params)
    if lens_id == "target.candidates":
        return target_candidates(profile)
    if lens_id == "target.associations":
        return target_associations(profile, **params)
    if lens_id == "target.importance":
        return target_importance(profile, **params)
    if lens_id == "distribution.numeric":
        return numeric_distribution(profile, **params)
    if lens_id == "categorical.value_counts":
        return categorical_value_counts(profile, **params)
    if lens_id == "binary.flags":
        return binary_flags(profile, **params)
    if lens_id == "text.lengths":
        return text_lengths(profile, **params)
    if lens_id == "cleaning.transform_preview":
        return cleaning_transform_preview(profile, **params)
    if lens_id == "footprint.optimize":
        return footprint_optimize(profile, **params)
    raise ValueError(f"Unknown lens: {lens_id}")


def missingness(profile: Profile) -> LensResult:
    df = profile.data
    by_column = []
    for name in df.columns:
        missing_count = int(df[name].isna().sum())
        by_column.append(
            {
                "column": str(name),
                "missing_count": missing_count,
                "missing_ratio": missing_count / int(df.shape[0]) if df.shape[0] else 0.0,
            }
        )
    row_missing = df.isna().sum(axis=1) if df.shape[1] else pd.Series(dtype=int)
    data = {
        "missing_cells": int(df.isna().sum().sum()),
        "missing_cell_ratio": profile.summary_data.missing_cell_ratio,
        "by_column": sorted(by_column, key=lambda item: item["missing_ratio"], reverse=True),
        "row_missing_min": int(row_missing.min()) if not row_missing.empty else 0,
        "row_missing_max": int(row_missing.max()) if not row_missing.empty else 0,
        "row_missing_mean": float(row_missing.mean()) if not row_missing.empty else 0.0,
    }
    return LensResult(
        id="quality.missingness",
        title="Missingness profile",
        data=data,
    )


def type_coercion(profile: Profile) -> LensResult:
    candidates = []
    for column in profile.column_profiles.values():
        if column.semantic_type in {"numeric-like", "datetime-like", "json-like"}:
            candidates.append(
                {
                    "column": column.name,
                    "current_dtype": column.dtype,
                    "suggested_semantic_type": column.semantic_type.replace("-like", ""),
                }
            )
    return LensResult(
        id="quality.type_coercion",
        title="Type coercion candidates",
        data={"candidates": candidates},
    )


def numeric_distribution(profile: Profile, column: str | None = None) -> LensResult:
    column = column or _first_column(profile, {"numeric", "amount", "numeric-like", "percentage", "proportion"})
    if column is None:
        raise ValueError("distribution.numeric requires a numeric-like column.")
    column_profile = profile.column(column)
    values = pd.to_numeric(profile.data[column], errors="coerce").dropna()
    values = values[np.isfinite(values)]
    data = {
        "column": column,
        "semantic_type": column_profile.semantic_type,
        "non_null_count": int(values.shape[0]),
        "summary": {
            key: value
            for key, value in column_profile.metrics.items()
            if key
            in {
                "min",
                "max",
                "mean",
                "median",
                "std",
                "skew",
                "kurtosis",
                "zero_ratio",
                "negative_ratio",
                "positive_ratio",
                "iqr_outlier_count",
                "iqr_outlier_ratio",
                "top_1pct_share",
            }
        },
        "quantiles": {
            key: value
            for key, value in column_profile.metrics.items()
            if key.startswith("p")
        },
    }
    issues = []
    if abs(float(column_profile.metrics.get("skew") or 0.0)) >= 2:
        issues.append(
            Issue(
                id="distribution.skewed_numeric",
                title=f"{column} is skewed",
                severity="info",
                confidence=0.8,
                category="distribution",
                columns=[column],
                why_it_matters="Skewed distributions can make means and ordinary-scale plots misleading.",
                suggested_action="Use robust summaries and consider log-scale visualization if values are nonnegative.",
                method="pandas skew",
            )
        )
    return LensResult(
        id="distribution.numeric",
        title=f"Numeric distribution for {column}",
        data=data,
        issues=issues,
    )


def categorical_value_counts(profile: Profile, column: str | None = None, limit: int = 25) -> LensResult:
    column = column or _first_column(profile, {"category", "string", "postal_code", "geographic"})
    if column is None:
        raise ValueError("categorical.value_counts requires a categorical/string column.")
    counts = profile.data[column].value_counts(dropna=False).head(limit)
    total = int(profile.data.shape[0])
    data = {
        "column": column,
        "total": total,
        "distinct_count": profile.column(column).distinct_count,
        "values": [
            {
                "value": clean_metric(value),
                "count": int(count),
                "ratio": int(count) / total if total else 0.0,
            }
            for value, count in counts.items()
        ],
        "rare_value_count": profile.column(column).metrics.get("rare_value_count"),
        "rare_value_ratio": profile.column(column).metrics.get("rare_value_ratio"),
    }
    return LensResult(
        id="categorical.value_counts",
        title=f"Value counts for {column}",
        data=data,
    )


def binary_flags(profile: Profile, column: str | None = None) -> LensResult:
    flags = []
    for name, binary_profile in profile.binary_flags().items():
        if column is not None and name != column:
            continue
        flags.append(
            {
                "column": name,
                **binary_profile.to_dict(),
            }
        )
    if column is not None and not flags:
        raise ValueError(f"{column} is not known as a binary-like column.")
    return LensResult(
        id="binary.flags",
        title="Binary flag mappings",
        data={"flags": flags},
    )


def time_cadence(profile: Profile, column: str | None = None, groupby: str | None = None) -> LensResult:
    df = profile.data
    column = column or profile.time or _first_column(profile, {"datetime", "datetime-like"})
    if column is None:
        raise ValueError("time.cadence requires a datetime-like column.")

    parsed = pd.to_datetime(df[column], errors="coerce")
    values = parsed.dropna().sort_values()
    diffs = values.diff().dropna()
    data: dict[str, Any] = {
        "column": column,
        "non_null_count": int(values.shape[0]),
        "parse_success_ratio": float(parsed.notna().mean()) if parsed.shape[0] else 0.0,
        "duplicate_timestamp_count": int(values.duplicated().sum()),
    }
    if not values.empty:
        data["min"] = clean_metric(values.iloc[0])
        data["max"] = clean_metric(values.iloc[-1])
        data["span_days"] = (values.iloc[-1] - values.iloc[0]).total_seconds() / 86400
    if not diffs.empty:
        gap_seconds = diffs.dt.total_seconds()
        data.update(
            clean_metrics(
                {
                    "min_gap_seconds": gap_seconds.min(),
                    "median_gap_seconds": gap_seconds.median(),
                    "max_gap_seconds": gap_seconds.max(),
                    "mean_gap_seconds": gap_seconds.mean(),
                }
            )
        )
        large_gap_threshold = gap_seconds.quantile(0.95)
        data["large_gap_threshold_seconds"] = clean_metric(large_gap_threshold)
        data["large_gap_count"] = int((gap_seconds > large_gap_threshold).sum())

    if groupby:
        data["groupby"] = groupby
        data["groups"] = int(df[groupby].nunique(dropna=True))

    issues = []
    if data.get("large_gap_count", 0) > 0:
        issues.append(
            Issue(
                id="time.large_gaps",
                title=f"{column} has large time gaps",
                severity="info",
                confidence=0.75,
                category="time",
                columns=[column],
                why_it_matters="Large time gaps can create misleading rolling or trend summaries.",
                suggested_action="Inspect gaps by entity or data source if available.",
                method="95th percentile gap threshold",
            )
        )

    return LensResult(
        id="time.cadence",
        title=f"Cadence analysis for {column}",
        data=data,
        issues=issues,
    )


def grain_keys(profile: Profile) -> LensResult:
    row_count = profile.summary_data.row_count
    candidates = []
    for column in profile.column_profiles.values():
        if row_count and column.missing_count == 0 and column.distinct_count == row_count:
            candidates.append(
                {
                    "column": column.name,
                    "confidence": 0.95 if column.semantic_type == "identifier" else 0.75,
                    "reason": "unique and non-null",
                }
            )
        elif column.semantic_type == "identifier":
            candidates.append(
                {
                    "column": column.name,
                    "confidence": 0.55,
                    "reason": "identifier-like but not unique",
                }
            )
    return LensResult(
        id="grain.keys",
        title="Key and grain candidates",
        data={"row_count": row_count, "candidates": candidates},
    )


def concentration_lorenz(
    profile: Profile,
    column: str | None = None,
    max_points: int = 200,
) -> LensResult:
    df = profile.data
    column = column or _first_column(profile, {"amount", "numeric"})
    if column is None:
        raise ValueError("concentration.lorenz requires a numeric column.")

    values = pd.to_numeric(df[column], errors="coerce").dropna()
    values = values[np.isfinite(values)]
    values = values[values >= 0].sort_values()
    if values.empty:
        data = {"column": column, "nonnegative_count": 0, "total": 0.0}
        return LensResult(id="concentration.lorenz", title=f"Concentration for {column}", data=data)

    total = float(values.sum())
    if total == 0:
        cumulative_value_share = np.zeros(values.shape[0])
    else:
        cumulative_value_share = values.cumsum().to_numpy() / total
    cumulative_row_share = np.arange(1, values.shape[0] + 1) / values.shape[0]
    gini = _gini(values.to_numpy())
    descending = values.sort_values(ascending=False)

    curve = [
        {
            "cumulative_row_share": float(row_share),
            "cumulative_value_share": float(value_share),
        }
        for row_share, value_share in zip(cumulative_row_share, cumulative_value_share)
    ]
    if max_points and len(curve) > max_points:
        indices = np.linspace(0, len(curve) - 1, max_points).round().astype(int)
        curve = [curve[int(index)] for index in indices]

    data = {
        "column": column,
        "nonnegative_count": int(values.shape[0]),
        "total": total,
        "gini": gini,
        "top_1pct_share": _top_share(descending, 0.01),
        "top_5pct_share": _top_share(descending, 0.05),
        "top_10pct_share": _top_share(descending, 0.10),
        "curve": curve,
    }
    return LensResult(
        id="concentration.lorenz",
        title=f"Concentration for {column}",
        data=data,
    )


def correlation(profile: Profile) -> LensResult:
    df = profile.data
    numeric = df.select_dtypes(include=["number"])
    if numeric.shape[1] < 2:
        data = {"columns": list(numeric.columns), "correlations": {}}
    else:
        corr = numeric.corr(numeric_only=True)
        data = {
            "columns": [str(column) for column in corr.columns],
            "correlations": {
                str(row): {
                    str(column): clean_metric(value)
                    for column, value in corr.loc[row].items()
                }
                for row in corr.index
            },
        }
    return LensResult(
        id="relationships.correlation",
        title="Numeric correlation scan",
        data=data,
    )


def target_balance(profile: Profile, column: str | None = None) -> LensResult:
    column = column or profile.target
    if column is None:
        raise ValueError("target.balance requires a target column.")
    counts = profile.data[column].value_counts(dropna=False)
    total = int(counts.sum())
    data = {
        "column": column,
        "total": total,
        "values": [
            {
                "value": clean_metric(value),
                "count": int(count),
                "ratio": int(count) / total if total else 0.0,
            }
            for value, count in counts.items()
        ],
    }
    return LensResult(
        id="target.balance",
        title=f"Target balance for {column}",
        data=data,
    )


def target_candidates(profile: Profile) -> LensResult:
    return LensResult(
        id="target.candidates",
        title="Target candidates",
        data={
            "candidates": [
                candidate.to_dict() for candidate in profile.target_candidates()
            ]
        },
    )


def target_associations(profile: Profile, column: str | None = None, limit: int = 20) -> LensResult:
    target = column or profile.target
    if target is None:
        raise ValueError("target.associations requires a target column.")
    if target not in profile.data.columns:
        raise ValueError(f"Target column not found: {target}")

    df = profile.data
    target_series = df[target]
    target_numeric = pd.to_numeric(target_series, errors="coerce")
    target_is_numeric = target_numeric.notna().mean() >= 0.9
    results = []
    for name, column_profile in profile.column_profiles.items():
        if name == target or column_profile.semantic_type in {"identifier", "datetime", "datetime-like"}:
            continue
        if column_profile.semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion"}:
            values = pd.to_numeric(df[name], errors="coerce")
            if target_is_numeric:
                paired = pd.concat([values, target_numeric], axis=1).dropna()
                score = abs(float(paired.iloc[:, 0].corr(paired.iloc[:, 1]))) if paired.shape[0] > 2 else 0.0
                detail = {"absolute_correlation": clean_metric(score)}
            else:
                grouped = (
                    pd.DataFrame({"value": values, "target": target_series})
                    .dropna()
                    .groupby("target")["value"]
                    .median()
                )
                score = float(grouped.max() - grouped.min()) if grouped.shape[0] > 1 else 0.0
                detail = {
                    "group_medians": {clean_metric(k): clean_metric(v) for k, v in grouped.items()},
                    "median_spread": clean_metric(score),
                }
            results.append(
                {
                    "column": name,
                    "semantic_type": column_profile.semantic_type,
                    "kind": "numeric_vs_target",
                    "score": clean_metric(score),
                    **detail,
                }
            )
        elif column_profile.semantic_type in {"category", "string", "binary", "nullable_binary", "boolean"}:
            frame = pd.DataFrame({"feature": df[name], "target": target_numeric if target_is_numeric else target_series}).dropna()
            if frame.empty:
                continue
            top_levels = frame["feature"].value_counts().head(limit).index
            frame = frame[frame["feature"].isin(top_levels)]
            if target_is_numeric:
                grouped = frame.groupby("feature")["target"].agg(["count", "median", "mean"])
                if grouped.shape[0] < 2:
                    continue
                target_iqr = float(target_numeric.quantile(0.75) - target_numeric.quantile(0.25)) or 1.0
                spread = float(grouped["median"].max() - grouped["median"].min())
                score = spread / target_iqr
                results.append(
                    {
                        "column": name,
                        "semantic_type": column_profile.semantic_type,
                        "kind": "categorical_vs_numeric_target",
                        "score": clean_metric(score),
                        "median_spread": clean_metric(spread),
                        "levels_considered": int(grouped.shape[0]),
                        "top_level_medians": {
                            clean_metric(level): clean_metric(value)
                            for level, value in grouped["median"].sort_values(ascending=False).head(10).items()
                        },
                    }
                )
            else:
                table = pd.crosstab(frame["feature"], frame["target"], normalize="index")
                if table.empty:
                    continue
                spread = float(table.max(axis=1).max() - table.max(axis=1).min()) if table.shape[0] > 1 else 0.0
                results.append(
                    {
                        "column": name,
                        "semantic_type": column_profile.semantic_type,
                        "kind": "categorical_vs_target",
                        "score": clean_metric(spread),
                        "levels_considered": int(min(table.shape[0], limit)),
                        "target_columns": [clean_metric(value) for value in table.columns.tolist()],
                    }
                )

    results = sorted(results, key=lambda item: abs(float(item.get("score") or 0.0)), reverse=True)
    return LensResult(
        id="target.associations",
        title=f"Feature associations with {target}",
        data={"target": target, "associations": results[:limit]},
    )


def mixed_associations(
    profile: Profile,
    *,
    limit: int = 30,
    max_columns: int | None = None,
) -> LensResult:
    df = profile.data
    max_columns = max_columns or 24
    candidates = [
        column
        for column in profile.column_profiles.values()
        if column.semantic_type
        in {
            "numeric",
            "amount",
            "numeric-like",
            "percentage",
            "proportion",
            "category",
            "string",
            "binary",
            "nullable_binary",
            "boolean",
        }
        and column.distinct_count > 1
        and column.missing_ratio < 0.95
    ][:max_columns]
    rows: list[dict[str, Any]] = []
    for i, left in enumerate(candidates):
        for right in candidates[i + 1 :]:
            if left.name == right.name:
                continue
            metric = _pair_association(df, left.name, left.semantic_type, right.name, right.semantic_type)
            if metric is not None:
                rows.append(metric)

    rows.extend(_missingness_associations(profile, max_pairs=limit))
    rows = sorted(rows, key=lambda item: abs(float(item.get("strength") or 0.0)), reverse=True)
    return LensResult(
        id="relationships.mixed_associations",
        title="Mixed association scan",
        data={
            "columns_considered": [column.name for column in candidates],
            "associations": rows[:limit],
        },
    )


def target_importance(
    profile: Profile,
    *,
    target: str | None = None,
    max_features: int = 40,
    permutation: bool = True,
    random_state: int = 42,
) -> LensResult:
    target = target or profile.target
    if target is None:
        raise ValueError("target.importance requires a target column.")
    if target not in profile.data.columns:
        raise ValueError(f"Target column not found: {target}")

    prepared = _prepare_model_frame(profile, target=target, max_features=max_features)
    if prepared["X"].empty:
        return LensResult(
            id="target.importance",
            title=f"Target importance for {target}",
            data={
                "target": target,
                "model_type": "not_run",
                "reason": "no usable features after preprocessing",
                "features": [],
            },
        )

    try:
        data = _sklearn_target_importance(
            prepared["X"],
            prepared["y"],
            task=prepared["task"],
            target=target,
            feature_sources=prepared["feature_sources"],
            permutation=permutation,
            random_state=random_state,
        )
    except Exception as exc:  # sklearn may be absent or data may be too small.
        data = _fallback_target_importance(
            prepared["X"],
            prepared["y"],
            task=prepared["task"],
            target=target,
            feature_sources=prepared["feature_sources"],
            reason=str(exc),
        )

    issues = []
    suspicious = [
        row
        for row in data.get("feature_importance", [])[:8]
        if row.get("suspicion") == "possible_leakage_or_proxy"
    ]
    if suspicious:
        issues.append(
            Issue(
                id="target.possible_leakage_signal",
                title="Some features look suspiciously strong",
                severity="warning",
                confidence=0.72,
                category="target",
                columns=[row["feature"] for row in suspicious[:5]],
                why_it_matters="Very strong early-model signals can be real, but they may also reveal leakage or post-outcome information.",
                suggested_action="Review feature timing, business meaning, and whether these fields would exist at prediction time.",
                method="exploratory model importance",
                evidence_sources=["model", "target"],
            )
        )
    return LensResult(
        id="target.importance",
        title=f"Target importance for {target}",
        data=data,
        issues=issues,
    )


def cleaning_transform_preview(profile: Profile) -> LensResult:
    plan = profile.cleaning_plan()
    return LensResult(
        id="cleaning.transform_preview",
        title="Cleaning transformation preview",
        data={
            "actions": [action.to_dict() for action in plan.actions],
            "action_count": len(plan.actions),
            "binary_null_policy": plan.binary_null_policy,
        },
    )


def footprint_optimize(profile: Profile, **kwargs: Any) -> LensResult:
    from stateframe.footprint import build_footprint_plan

    plan = build_footprint_plan(profile, **kwargs)
    return LensResult(
        id="footprint.optimize",
        title="Memory footprint optimization plan",
        data={
            **plan.summary(),
            "actions": [action.to_dict() for action in plan.actions],
        },
    )


def text_lengths(profile: Profile, column: str | None = None) -> LensResult:
    column = column or _first_column(profile, {"text"})
    if column is None:
        raise ValueError("text.lengths requires a text column.")
    values = profile.data[column].dropna().astype("string")
    lengths = values.str.len()
    words = values.str.strip().str.split().map(lambda value: len(value) if isinstance(value, list) else 0)
    data = clean_metrics(
        {
            "column": column,
            "non_null_count": int(values.shape[0]),
            "min_length": lengths.min() if not lengths.empty else None,
            "median_length": lengths.median() if not lengths.empty else None,
            "mean_length": lengths.mean() if not lengths.empty else None,
            "max_length": lengths.max() if not lengths.empty else None,
            "empty_string_count": int((values.str.strip() == "").sum()) if not values.empty else 0,
            "mean_word_count": words.mean() if not words.empty else None,
            "max_word_count": words.max() if not words.empty else None,
        }
    )
    return LensResult(id="text.lengths", title=f"Text lengths for {column}", data=data)


def _is_numeric_semantic(semantic_type: str) -> bool:
    return semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"}


def _is_categorical_semantic(semantic_type: str) -> bool:
    return semantic_type in {"category", "string", "binary", "nullable_binary", "boolean", "postal_code", "geographic"}


def _pair_association(
    df: pd.DataFrame,
    left: str,
    left_type: str,
    right: str,
    right_type: str,
) -> dict[str, Any] | None:
    if _is_numeric_semantic(left_type) and _is_numeric_semantic(right_type):
        paired = pd.concat(
            [
                pd.to_numeric(df[left], errors="coerce"),
                pd.to_numeric(df[right], errors="coerce"),
            ],
            axis=1,
        ).dropna()
        if paired.shape[0] < 3:
            return None
        if paired.iloc[:, 0].std() == 0 or paired.iloc[:, 1].std() == 0:
            return None
        pearson = paired.iloc[:, 0].corr(paired.iloc[:, 1], method="pearson")
        spearman = paired.iloc[:, 0].corr(paired.iloc[:, 1], method="spearman")
        strength = max(abs(float(pearson or 0.0)), abs(float(spearman or 0.0)))
        return {
            "left": left,
            "right": right,
            "kind": "numeric_numeric",
            "method": "pearson_spearman",
            "strength": clean_metric(strength),
            "pearson": clean_metric(pearson),
            "spearman": clean_metric(spearman),
            "n": int(paired.shape[0]),
        }

    if _is_numeric_semantic(left_type) and _is_categorical_semantic(right_type):
        return _numeric_categorical_association(df, numeric=left, categorical=right)
    if _is_categorical_semantic(left_type) and _is_numeric_semantic(right_type):
        result = _numeric_categorical_association(df, numeric=right, categorical=left)
        if result:
            result["left"], result["right"] = left, right
        return result
    if _is_categorical_semantic(left_type) and _is_categorical_semantic(right_type):
        return _categorical_categorical_association(df, left=left, right=right)
    return None


def _numeric_categorical_association(
    df: pd.DataFrame,
    *,
    numeric: str,
    categorical: str,
) -> dict[str, Any] | None:
    frame = pd.DataFrame(
        {
            "numeric": pd.to_numeric(df[numeric], errors="coerce"),
            "category": df[categorical].astype("string"),
        }
    ).dropna()
    if frame.shape[0] < 5 or frame["category"].nunique() < 2:
        return None
    top_levels = frame["category"].value_counts().head(30).index
    frame = frame[frame["category"].isin(top_levels)]
    if frame["category"].nunique() < 2:
        return None
    overall = frame["numeric"].mean()
    total_ss = float(((frame["numeric"] - overall) ** 2).sum())
    if total_ss <= 0:
        return None
    grouped = frame.groupby("category")["numeric"]
    between_ss = float(sum(group.size * (group.mean() - overall) ** 2 for _, group in grouped))
    eta_squared = between_ss / total_ss
    medians = grouped.median().sort_values(ascending=False)
    return {
        "left": numeric,
        "right": categorical,
        "kind": "numeric_categorical",
        "method": "eta_squared",
        "strength": clean_metric(eta_squared),
        "eta_squared": clean_metric(eta_squared),
        "levels_considered": int(medians.shape[0]),
        "top_medians": {clean_metric(k): clean_metric(v) for k, v in medians.head(8).items()},
        "n": int(frame.shape[0]),
    }


def _categorical_categorical_association(
    df: pd.DataFrame,
    *,
    left: str,
    right: str,
) -> dict[str, Any] | None:
    frame = pd.DataFrame(
        {
            "left": df[left].astype("string"),
            "right": df[right].astype("string"),
        }
    ).dropna()
    if frame.shape[0] < 5 or frame["left"].nunique() < 2 or frame["right"].nunique() < 2:
        return None
    left_levels = frame["left"].value_counts().head(30).index
    right_levels = frame["right"].value_counts().head(30).index
    frame = frame[frame["left"].isin(left_levels) & frame["right"].isin(right_levels)]
    table = pd.crosstab(frame["left"], frame["right"])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return None
    observed = table.to_numpy(dtype=float)
    total = observed.sum()
    row_sums = observed.sum(axis=1, keepdims=True)
    col_sums = observed.sum(axis=0, keepdims=True)
    expected = row_sums @ col_sums / total
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = np.nan_to_num((observed - expected) ** 2 / expected).sum()
    denom = total * (min(table.shape) - 1)
    cramers_v = float(np.sqrt(chi2 / denom)) if denom > 0 else 0.0
    return {
        "left": left,
        "right": right,
        "kind": "categorical_categorical",
        "method": "cramers_v",
        "strength": clean_metric(cramers_v),
        "cramers_v": clean_metric(cramers_v),
        "left_levels": int(table.shape[0]),
        "right_levels": int(table.shape[1]),
        "n": int(frame.shape[0]),
    }


def _missingness_associations(profile: Profile, *, max_pairs: int) -> list[dict[str, Any]]:
    columns = [
        column.name
        for column in profile.column_profiles.values()
        if 0 < column.missing_ratio < 1
    ][:20]
    rows: list[dict[str, Any]] = []
    for i, left in enumerate(columns):
        for right in columns[i + 1 :]:
            pair = profile.data[[left, right]].isna().astype(int)
            if pair[left].std() == 0 or pair[right].std() == 0:
                continue
            corr = pair[left].corr(pair[right])
            if pd.isna(corr):
                continue
            rows.append(
                {
                    "left": left,
                    "right": right,
                    "kind": "missingness_missingness",
                    "method": "phi_correlation",
                    "strength": clean_metric(abs(float(corr))),
                    "phi": clean_metric(corr),
                    "n": int(pair.shape[0]),
                }
            )
    return sorted(rows, key=lambda item: item["strength"], reverse=True)[:max_pairs]


def _prepare_model_frame(
    profile: Profile,
    *,
    target: str,
    max_features: int,
) -> dict[str, Any]:
    df = profile.data
    target_profile = profile.column(target)
    y = df[target]
    task = profile.target_profile.task if profile.target_profile else None
    if task is None:
        task = "regression" if _is_numeric_semantic(target_profile.semantic_type) else "binary_classification"

    features: list[pd.Series] = []
    feature_sources: dict[str, str] = {}
    for name, column in profile.column_profiles.items():
        if name == target:
            continue
        if column.semantic_type in {"identifier", "datetime", "datetime-like", "text", "mostly_missing", "constant"}:
            continue
        if _is_numeric_semantic(column.semantic_type):
            values = pd.to_numeric(df[name], errors="coerce")
            if values.notna().mean() < 0.4:
                continue
            features.append(values.rename(name))
            feature_sources[name] = name
        elif _is_categorical_semantic(column.semantic_type) and column.distinct_count <= 30:
            dummies = pd.get_dummies(df[name].astype("string"), prefix=name, dummy_na=True)
            for dummy_name in dummies.columns[: max(0, max_features - len(features))]:
                features.append(dummies[dummy_name].astype(float).rename(str(dummy_name)))
                feature_sources[str(dummy_name)] = name
        if len(features) >= max_features:
            break

    X = pd.concat(features, axis=1) if features else pd.DataFrame(index=df.index)
    frame = pd.concat([X, y.rename("__target__")], axis=1).dropna(subset=["__target__"])
    X = frame.drop(columns=["__target__"]).copy()
    y = frame["__target__"].copy()
    for column in X.columns:
        X[column] = pd.to_numeric(X[column], errors="coerce")
        if X[column].isna().any():
            X[column] = X[column].fillna(X[column].median() if X[column].notna().any() else 0)
    return {"X": X, "y": y, "task": task, "feature_sources": feature_sources}


def _sklearn_target_importance(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    task: str,
    target: str,
    feature_sources: dict[str, str],
    permutation: bool,
    random_state: int,
) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    is_classification = task in {"binary_classification", "multiclass_classification"}
    if X.shape[0] < 10:
        raise ValueError("not enough rows for sklearn model importance")
    stratify = y if is_classification and y.nunique(dropna=True) > 1 and y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=random_state,
        stratify=stratify,
    )
    if is_classification:
        model = RandomForestClassifier(n_estimators=120, random_state=random_state, n_jobs=-1, min_samples_leaf=2)
        baseline_value = y_train.mode(dropna=True).iloc[0]
        baseline_pred = pd.Series([baseline_value] * len(y_test), index=y_test.index)
        scorer_name = "accuracy"
    else:
        y_train_num = pd.to_numeric(y_train, errors="coerce")
        y_test = pd.to_numeric(y_test, errors="coerce")
        keep_train = y_train_num.notna()
        keep_test = y_test.notna()
        X_train, y_train = X_train.loc[keep_train], y_train_num.loc[keep_train]
        X_test, y_test = X_test.loc[keep_test], y_test.loc[keep_test]
        model = RandomForestRegressor(n_estimators=160, random_state=random_state, n_jobs=-1, min_samples_leaf=2)
        baseline_value = float(y_train.median())
        baseline_pred = pd.Series([baseline_value] * len(y_test), index=y_test.index)
        scorer_name = "r2"

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    if is_classification:
        baseline_score = float(accuracy_score(y_test, baseline_pred))
        model_score = float(accuracy_score(y_test, predictions))
    else:
        baseline_score = {
            "mae": clean_metric(mean_absolute_error(y_test, baseline_pred)),
            "r2": clean_metric(r2_score(y_test, baseline_pred)),
        }
        model_score = {
            "mae": clean_metric(mean_absolute_error(y_test, predictions)),
            "r2": clean_metric(r2_score(y_test, predictions)),
        }

    importances = getattr(model, "feature_importances_", np.zeros(X.shape[1]))
    feature_rows = _importance_rows(X.columns, importances, feature_sources)
    permutation_rows: list[dict[str, Any]] = []
    if permutation and X_test.shape[0] >= 5:
        perm = permutation_importance(
            model,
            X_test,
            y_test,
            n_repeats=5,
            random_state=random_state,
            n_jobs=-1,
        )
        permutation_rows = _importance_rows(X.columns, perm.importances_mean, feature_sources, value_name="permutation_importance")

    return {
        "target": target,
        "task": task,
        "model_type": type(model).__name__,
        "validation": "random_holdout_25pct",
        "scorer": scorer_name,
        "row_count": int(X.shape[0]),
        "feature_count": int(X.shape[1]),
        "baseline_score": baseline_score,
        "model_score": model_score,
        "feature_importance": feature_rows,
        "permutation_importance": permutation_rows,
        "notes": ["Exploratory feature importance; this is not causal evidence."],
    }


def _fallback_target_importance(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    task: str,
    target: str,
    feature_sources: dict[str, str],
    reason: str,
) -> dict[str, Any]:
    y_numeric = pd.to_numeric(y, errors="coerce")
    rows = []
    for column in X.columns:
        values = pd.to_numeric(X[column], errors="coerce")
        paired = pd.concat([values, y_numeric], axis=1).dropna()
        if (
            paired.shape[0] >= 3
            and paired.iloc[:, 1].nunique() > 1
            and paired.iloc[:, 0].std() != 0
            and paired.iloc[:, 1].std() != 0
        ):
            strength = abs(float(paired.iloc[:, 0].corr(paired.iloc[:, 1])))
        else:
            frame = pd.DataFrame({"feature": values, "target": y}).dropna()
            if frame.empty or frame["feature"].nunique() < 2:
                strength = 0.0
            else:
                grouped = frame.groupby("feature")["target"].size()
                strength = float(grouped.max() / grouped.sum())
        rows.append({"feature": column, "importance": clean_metric(strength)})
    rows = _importance_rows(
        [row["feature"] for row in rows],
        [row["importance"] or 0.0 for row in rows],
        feature_sources,
    )
    return {
        "target": target,
        "task": task,
        "model_type": "univariate_fallback",
        "fallback_reason": reason,
        "row_count": int(X.shape[0]),
        "feature_count": int(X.shape[1]),
        "baseline_score": None,
        "model_score": None,
        "feature_importance": rows,
        "permutation_importance": [],
        "notes": [
            "scikit-learn model importance was unavailable; ranked simple univariate associations instead.",
            "Exploratory feature importance; this is not causal evidence.",
        ],
    }


def _importance_rows(
    columns: Any,
    values: Any,
    feature_sources: dict[str, str],
    *,
    value_name: str = "importance",
) -> list[dict[str, Any]]:
    rows = []
    for feature, value in zip(list(columns), list(values)):
        raw_value = float(value or 0.0)
        rows.append(
            {
                "feature": str(feature),
                "source_column": feature_sources.get(str(feature), str(feature)),
                value_name: clean_metric(raw_value),
                "suspicion": "possible_leakage_or_proxy" if raw_value >= 0.45 else None,
            }
        )
    return sorted(rows, key=lambda row: abs(float(row.get(value_name) or 0.0)), reverse=True)


def _first_column(profile: Profile, semantic_types: set[str]) -> str | None:
    for column in profile.column_profiles.values():
        if column.semantic_type in semantic_types:
            return column.name
    return None


def _gini(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    sorted_values = np.sort(values)
    total = sorted_values.sum()
    if total == 0:
        return 0.0
    index = np.arange(1, sorted_values.size + 1)
    return float((2 * np.sum(index * sorted_values)) / (sorted_values.size * total) - (sorted_values.size + 1) / sorted_values.size)


def _top_share(descending_values: pd.Series, fraction: float) -> float:
    if descending_values.empty:
        return 0.0
    total = float(descending_values.sum())
    if total == 0:
        return 0.0
    top_n = max(1, int(np.ceil(descending_values.shape[0] * fraction)))
    return float(descending_values.head(top_n).sum() / total)
