"""Build the first working stateframe Profile from a DataFrame or local file."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from pandas.api import types as pdt

from stateframe.binary import detect_binary_profile, missing_like_counts
from stateframe.config import ScanConfig
from stateframe.insights import build_insights
from stateframe.io import coerce_dataframe, describe_source
from stateframe.issues import build_issues
from stateframe.models import (
    ColumnProfile,
    DatasetSummary,
    EvidenceFact,
    Profile,
    SemanticTypeHypothesis,
    ValueProfile,
)
from stateframe.recommendations import build_recommendations
from stateframe.semantic import infer_semantic_hypotheses
from stateframe.shapes import infer_shapes
from stateframe.targets import (
    build_suggested_config,
    build_target_profile,
    infer_target_candidates,
    infer_task,
    infer_time_candidates,
)
from stateframe.utils import clean_metric, clean_metrics


def build_profile(
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
    source_path: str | None = None,
    reader_params: dict[str, Any] | None = None,
    register: bool = True,
) -> Profile:
    config = config or ScanConfig.from_mode(mode, sample_size=sample_size)
    source = describe_source(
        data,
        source_path=source_path,
        reader_params=reader_params,
    )
    df = coerce_dataframe(data, reader_params=reader_params)
    scan_df = _maybe_sample(df, config)

    columns = _build_column_profiles(scan_df, config=config)
    summary = _build_summary(df, columns, config=config, scanned_rows=scan_df.shape[0])

    target_candidates = infer_target_candidates(columns, explicit_target=target, config=config)
    target_profile = build_target_profile(
        scan_df,
        columns,
        target_candidates,
        explicit_target=target,
        config=config,
    )
    task_inference = infer_task(columns, target_profile, explicit_task=task)
    time_candidates = infer_time_candidates(columns, config=config)
    if time and time in columns:
        time_candidates = _boost_explicit_time(time_candidates, time, columns)

    selected_time = time
    if selected_time is None and time_candidates and time_candidates[0].confidence >= config.time_auto_select_threshold:
        selected_time = time_candidates[0].column

    shapes = infer_shapes(
        scan_df,
        columns,
        target=target_profile.column if target_profile else target,
        time=selected_time,
    )
    issues = build_issues(
        scan_df,
        summary,
        columns,
        target=target_profile.column if target_profile else target,
    )
    insights = build_insights(
        summary,
        columns,
        issues,
        target_candidates=target_candidates,
        target_profile=target_profile,
        time_candidates=time_candidates,
    )
    suggested = build_suggested_config(
        columns,
        target_profile,
        task_inference,
        time_candidates,
        config=config,
    )
    recommendations = build_recommendations(
        scan_df,
        summary,
        columns,
        issues,
        shapes,
        target=target_profile.column if target_profile else target,
        time=selected_time,
        goal=goal,
        config=config,
    )
    facts = _build_facts(summary, columns)

    profile = Profile(
        summary_data=summary,
        column_profiles=columns,
        issue_list=issues,
        recommendation_list=recommendations,
        shape_hypotheses=shapes,
        data=scan_df,
        target=target_profile.column if target_profile else target,
        time=selected_time,
        goal=goal,
        mode=config.scan_depth,
        guidance=config.guidance,
        semantic_policy=config.semantic_policy,
        visual_policy=config.visual_policy,
        explanation_level=config.explanation_level,
        recommendation_basis=list(config.active_recommendation_basis),
        insight_list=insights,
        target_candidate_list=target_candidates,
        target_profile=target_profile,
        task_inference=task_inference,
        time_candidate_list=time_candidates,
        suggested_config_data=suggested,
        facts=facts,
        dataset_name=name,
        tree_name=name,
        source=source,
    )
    from stateframe.ledger import LensLedger

    profile.ledger = LensLedger.start(profile)
    if register:
        try:
            from stateframe.save import register_profile

            register_profile(profile)
        except Exception:
            pass
    return profile


def _maybe_sample(df: pd.DataFrame, config: ScanConfig) -> pd.DataFrame:
    if config.sample_size is None or df.shape[0] <= config.sample_size:
        return df
    return df.sample(n=config.sample_size, random_state=config.random_state)


def _build_summary(
    df: pd.DataFrame,
    columns: dict[str, ColumnProfile],
    *,
    config: ScanConfig,
    scanned_rows: int,
) -> DatasetSummary:
    total_cells = int(scanned_rows * len(columns))
    scan_sample_used = scanned_rows != df.shape[0]
    missing_cells = sum(column.missing_count for column in columns.values())
    missing_ratio = missing_cells / total_cells if total_cells else 0.0
    try:
        duplicate_rows = int(df.duplicated().sum()) if not scan_sample_used else None
    except TypeError:
        duplicate_rows = None
    type_counts = Counter(column.semantic_type for column in columns.values())
    return DatasetSummary(
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
        memory_bytes=int(df.memory_usage(deep=True).sum()),
        missing_cells=int(missing_cells),
        missing_cell_ratio=float(missing_ratio),
        duplicate_rows=duplicate_rows,
        columns_by_type=dict(type_counts),
        backend="pandas",
        scan_mode=config.scan_depth,
        sample_used=scan_sample_used,
        sample_size=scanned_rows if scan_sample_used else None,
    )


def _build_column_profiles(
    df: pd.DataFrame,
    *,
    config: ScanConfig,
) -> dict[str, ColumnProfile]:
    profiles: dict[str, ColumnProfile] = {}
    for name in df.columns:
        series = df[name]
        hypotheses = infer_semantic_hypotheses(
            str(name),
            series,
            semantic_policy=config.semantic_policy,
        )
        primary = hypotheses[0] if hypotheses else SemanticTypeHypothesis("unknown", 0.0)
        binary_profile = detect_binary_profile(str(name), series)
        non_null_count = int(series.notna().sum())
        missing_count = int(series.isna().sum())
        missing_ratio = missing_count / int(series.shape[0]) if series.shape[0] else 0.0
        try:
            distinct_count = int(series.nunique(dropna=True))
        except TypeError:
            distinct_count = 0
        distinct_ratio = distinct_count / non_null_count if non_null_count else 0.0
        value_profile = _value_profile(series, config.max_top_values)
        metrics = _universal_metrics(series, value_profile)
        metrics.update(_type_specific_metrics(series, primary.semantic_type))
        quality = _quality_flags(series, primary.semantic_type, metrics, value_profile)
        actions = _recommended_column_actions(primary.semantic_type, binary_profile, metrics)
        profiles[str(name)] = ColumnProfile(
            name=str(name),
            dtype=str(series.dtype),
            semantic_type=primary.semantic_type,
            non_null_count=non_null_count,
            missing_count=missing_count,
            missing_ratio=float(missing_ratio),
            distinct_count=distinct_count,
            distinct_ratio=float(distinct_ratio),
            metrics=clean_metrics(metrics),
            top_values=value_profile.top_values,
            role=_infer_role(primary.semantic_type),
            semantic_confidence=primary.confidence,
            semantic_hypotheses=hypotheses,
            value_profile=value_profile,
            binary_profile=binary_profile,
            quality=quality,
            examples=_examples(series),
            recommended_actions=actions,
        )
    return profiles


def _value_profile(series: pd.Series, limit: int) -> ValueProfile:
    row_count = int(series.shape[0])
    raw_null_count = int(series.isna().sum())
    raw_null_ratio = raw_null_count / row_count if row_count else 0.0
    missing_like = missing_like_counts(series)
    semantic_null_count = raw_null_count + sum(missing_like.values())
    semantic_null_ratio = semantic_null_count / row_count if row_count else 0.0
    non_null = series.dropna()

    try:
        counts = non_null.value_counts(dropna=True)
    except TypeError:
        counts = non_null.astype("string").value_counts(dropna=True)

    unique_count = int(counts.shape[0])
    unique_ratio = unique_count / int(non_null.shape[0]) if non_null.shape[0] else 0.0
    top_values = [
        {"value": clean_metric(value), "count": int(count)}
        for value, count in counts.head(limit).items()
    ]
    dominant_value = top_values[0]["value"] if top_values else None
    dominant_count = top_values[0]["count"] if top_values else 0
    dominant_ratio = dominant_count / int(non_null.shape[0]) if non_null.shape[0] else 0.0
    rare_count = int((counts <= 5).sum()) if not counts.empty else 0
    rare_rows = int(counts[counts <= 5].sum()) if not counts.empty else 0
    rare_ratio = rare_rows / int(non_null.shape[0]) if non_null.shape[0] else 0.0

    if counts.sum():
        probabilities = counts / counts.sum()
        entropy = float(-(probabilities * np.log2(probabilities)).sum())
        normalized_entropy = entropy / np.log2(unique_count) if unique_count > 1 else 0.0
    else:
        entropy = None
        normalized_entropy = None

    return ValueProfile(
        unique_count=unique_count,
        unique_ratio=float(unique_ratio),
        raw_null_count=raw_null_count,
        raw_null_ratio=float(raw_null_ratio),
        semantic_null_count=semantic_null_count,
        semantic_null_ratio=float(semantic_null_ratio),
        top_values=top_values,
        rare_value_count=rare_count,
        rare_value_ratio=float(rare_ratio),
        dominant_value=dominant_value,
        dominant_value_ratio=float(dominant_ratio),
        entropy=entropy,
        normalized_entropy=normalized_entropy,
        missing_like_values=missing_like,
    )


def _universal_metrics(series: pd.Series, value_profile: ValueProfile) -> dict[str, Any]:
    return {
        "top_ratio": value_profile.dominant_value_ratio,
        "semantic_null_count": value_profile.semantic_null_count,
        "semantic_null_ratio": value_profile.semantic_null_ratio,
        "missing_like_values": value_profile.missing_like_values,
        "entropy": value_profile.entropy,
        "normalized_entropy": value_profile.normalized_entropy,
        "rare_value_count": value_profile.rare_value_count,
        "rare_value_ratio": value_profile.rare_value_ratio,
    }


def _type_specific_metrics(series: pd.Series, semantic_type: str) -> dict[str, Any]:
    if pdt.is_numeric_dtype(series) or semantic_type in {"numeric-like", "amount", "percentage", "proportion"}:
        metrics = _numeric_metrics(series)
        metrics["numeric_parse_ratio"] = _parse_numeric_success_ratio(series)
        return metrics
    if pdt.is_datetime64_any_dtype(series) or semantic_type == "datetime-like":
        return _datetime_metrics(series)
    if pdt.is_bool_dtype(series) or semantic_type in {"binary", "nullable_binary", "boolean"}:
        return _boolean_metrics(series)
    if semantic_type in {
        "category",
        "string",
        "text",
        "identifier",
        "email",
        "url",
        "json-like",
        "postal_code",
        "geographic",
    }:
        return _string_metrics(series)
    return {}


def _numeric_metrics(series: pd.Series) -> dict[str, Any]:
    numeric = _parse_numeric_series(series).dropna()
    if numeric.empty:
        return {}
    finite = numeric[np.isfinite(numeric)]
    if finite.empty:
        return {"infinite_count": int(np.isinf(numeric).sum())}

    metrics: dict[str, Any] = {
        "min": finite.min(),
        "max": finite.max(),
        "mean": finite.mean(),
        "median": finite.median(),
        "std": finite.std(ddof=1) if finite.shape[0] > 1 else 0.0,
        "skew": finite.skew() if finite.shape[0] > 2 else 0.0,
        "kurtosis": finite.kurtosis() if finite.shape[0] > 3 else 0.0,
        "zero_ratio": float((finite == 0).mean()),
        "negative_ratio": float((finite < 0).mean()),
        "positive_ratio": float((finite > 0).mean()),
        "integer_like_ratio": float((finite % 1 == 0).mean()),
        "infinite_count": int(np.isinf(numeric).sum()),
    }

    for quantile in (0.0, 0.01, 0.05, 0.10, 0.25, 0.5, 0.75, 0.90, 0.95, 0.99, 1.0):
        key = "p100" if quantile == 1.0 else f"p{int(quantile * 100):02d}"
        metrics[key] = finite.quantile(quantile)

    q1 = finite.quantile(0.25)
    q3 = finite.quantile(0.75)
    iqr = q3 - q1
    metrics["iqr"] = iqr
    if iqr > 0:
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        metrics["iqr_outlier_count"] = int(((finite < lower) | (finite > upper)).sum())
        metrics["iqr_outlier_ratio"] = metrics["iqr_outlier_count"] / int(finite.shape[0])
    else:
        metrics["iqr_outlier_count"] = 0
        metrics["iqr_outlier_ratio"] = 0.0

    nonnegative = finite[finite >= 0].sort_values(ascending=False)
    if not nonnegative.empty and nonnegative.sum() > 0:
        top_n = max(1, int(np.ceil(nonnegative.shape[0] * 0.01)))
        metrics["top_1pct_share"] = float(nonnegative.head(top_n).sum() / nonnegative.sum())
    else:
        metrics["top_1pct_share"] = None

    return metrics


def _datetime_metrics(series: pd.Series) -> dict[str, Any]:
    parsed = pd.to_datetime(series, errors="coerce")
    values = parsed.dropna()
    if values.empty:
        return {"datetime_parse_ratio": 0.0, "parse_success_ratio": 0.0}

    sorted_values = values.sort_values()
    diffs = sorted_values.diff().dropna()
    metrics: dict[str, Any] = {
        "datetime_parse_ratio": float(parsed.notna().mean()),
        "parse_success_ratio": float(parsed.notna().mean()),
        "min": sorted_values.iloc[0],
        "max": sorted_values.iloc[-1],
        "span_days": (sorted_values.iloc[-1] - sorted_values.iloc[0]).total_seconds()
        / 86400,
        "duplicate_timestamp_count": int(values.duplicated().sum()),
        "duplicate_timestamp_ratio": float(values.duplicated().mean()) if values.shape[0] else 0.0,
        "monotonic_increasing": bool(values.is_monotonic_increasing),
    }
    if not diffs.empty:
        metrics["median_gap_seconds"] = diffs.median().total_seconds()
        metrics["max_gap_seconds"] = diffs.max().total_seconds()
    return metrics


def _boolean_metrics(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna()
    if non_null.empty:
        return {}
    normalized = non_null.map(lambda value: str(value).strip().lower())
    true_count = int(normalized.isin({"true", "1", "yes", "y", "t"}).sum())
    false_count = int(normalized.isin({"false", "0", "no", "n", "f"}).sum())
    if pdt.is_bool_dtype(series):
        true_count = int((non_null == True).sum())  # noqa: E712
        false_count = int((non_null == False).sum())  # noqa: E712
    return {
        "true_count": true_count,
        "false_count": false_count,
        "true_ratio": true_count / int(non_null.shape[0]),
        "false_ratio": false_count / int(non_null.shape[0]),
    }


def _string_metrics(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna().astype("string")
    if non_null.empty:
        return {}
    lengths = non_null.str.len()
    stripped = non_null.str.strip()
    word_counts = stripped.str.split().map(lambda value: len(value) if isinstance(value, list) else 0)
    return {
        "min_length": clean_metric(lengths.min()),
        "max_length": clean_metric(lengths.max()),
        "mean_length": clean_metric(lengths.mean()),
        "median_length": clean_metric(lengths.median()),
        "empty_string_count": int((stripped == "").sum()),
        "mean_word_count": clean_metric(word_counts.mean()),
        "max_word_count": clean_metric(word_counts.max()),
    }


def _parse_numeric_series(series: pd.Series) -> pd.Series:
    if pdt.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _parse_numeric_success_ratio(series: pd.Series) -> float:
    non_null = series.dropna()
    if non_null.empty:
        return 0.0
    text = non_null.astype("string").str.strip().str.lower()
    missing_tokens = {"", "na", "n/a", "nan", "none", "null", "missing", "unknown", "?", "-", "--"}
    semantic_non_missing = non_null[~text.isin(missing_tokens)]
    if semantic_non_missing.empty:
        return 0.0
    parsed = _parse_numeric_series(semantic_non_missing)
    return float(parsed.notna().mean())


def _quality_flags(
    series: pd.Series,
    semantic_type: str,
    metrics: dict[str, Any],
    value_profile: ValueProfile,
) -> dict[str, Any]:
    return {
        "is_constant": value_profile.unique_count <= 1 and series.notna().any(),
        "is_near_constant": value_profile.unique_count > 1
        and value_profile.dominant_value_ratio >= 0.98,
        "has_missing_like_strings": bool(value_profile.missing_like_values),
        "has_iqr_outliers": metrics.get("iqr_outlier_ratio", 0) >= 0.01,
        "is_high_cardinality": value_profile.unique_count >= 50
        and value_profile.unique_ratio >= 0.5
        and semantic_type not in {"identifier", "numeric", "amount"},
    }


def _recommended_column_actions(
    semantic_type: str,
    binary_profile: Any,
    metrics: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if semantic_type in {"numeric", "amount", "numeric-like", "percentage"}:
        actions.append("plot_histogram")
        actions.append("plot_boxplot")
        if metrics.get("skew", 0) and abs(metrics.get("skew", 0)) >= 2:
            actions.append("plot_log_or_robust_distribution")
        if metrics.get("iqr_outlier_ratio", 0) >= 0.01:
            actions.append("inspect_outliers")
    if semantic_type in {"category", "string"}:
        actions.append("plot_value_counts")
        if metrics.get("rare_value_ratio", 0) >= 0.2:
            actions.append("inspect_rare_categories")
    if semantic_type in {"datetime", "datetime-like"}:
        actions.append("run_time_cadence")
        actions.append("plot_records_over_time")
    if semantic_type == "text":
        actions.append("plot_text_lengths")
    if binary_profile is not None:
        actions.append("review_binary_mapping")
    return _dedupe_keep_order(actions)


def _infer_role(semantic_type: str) -> str:
    if semantic_type == "identifier":
        return "id"
    if semantic_type in {"datetime", "datetime-like"}:
        return "timestamp"
    if semantic_type in {"constant", "mostly_missing"}:
        return "ignore_candidate"
    return "feature"


def _examples(series: pd.Series, limit: int = 5) -> list[Any]:
    values = []
    for value in series.dropna().head(limit):
        values.append(clean_metric(value))
    return values


def _boost_explicit_time(
    candidates: list[Any],
    time: str,
    columns: dict[str, ColumnProfile],
) -> list[Any]:
    from stateframe.models import TimeCandidate

    others = [candidate for candidate in candidates if candidate.column != time]
    metrics = columns[time].metrics
    explicit = TimeCandidate(
        column=time,
        confidence=0.99,
        evidence=["time column was provided by user"],
        min_timestamp=metrics.get("min"),
        max_timestamp=metrics.get("max"),
        span_days=metrics.get("span_days"),
    )
    return [explicit] + others


def _build_facts(
    summary: DatasetSummary,
    columns: dict[str, ColumnProfile],
) -> dict[str, EvidenceFact]:
    facts: dict[str, EvidenceFact] = {
        "dataset.shape": EvidenceFact(
            id="dataset.shape",
            subject="dataset",
            value={"rows": summary.row_count, "columns": summary.column_count},
            mode="exact" if not summary.sample_used else "sampled",
            method="pandas.DataFrame.shape",
            evidence_sources=["statistical"],
        ),
        "dataset.missingness": EvidenceFact(
            id="dataset.missingness",
            subject="dataset",
            value=summary.missing_cell_ratio,
            mode="exact" if not summary.sample_used else "sampled",
            method="column missing counts",
            evidence_sources=["quality", "statistical"],
        ),
    }
    for column in columns.values():
        facts[f"column.{column.name}.semantic_type"] = EvidenceFact(
            id=f"column.{column.name}.semantic_type",
            subject=column.name,
            value=column.semantic_type,
            mode="inferred",
            method="rule-based semantic inference",
            confidence=column.semantic_confidence,
            metadata={
                "alternatives": [
                    hypothesis.to_dict() for hypothesis in column.semantic_types()[1:]
                ]
            },
            evidence_sources=["semantic"],
        )
        facts[f"column.{column.name}.missing_ratio"] = EvidenceFact(
            id=f"column.{column.name}.missing_ratio",
            subject=column.name,
            value=column.missing_ratio,
            mode="exact" if not summary.sample_used else "sampled",
            method="pandas.Series.isna.mean",
            evidence_sources=["quality", "statistical"],
        )
    return facts


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
