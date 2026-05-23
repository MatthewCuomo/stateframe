"""Rule-based recommendation engine for the first stateframe build."""

from __future__ import annotations

import pandas as pd
from dataclasses import replace

from stateframe.config import EvidenceSource, ScanConfig
from stateframe.models import (
    ColumnProfile,
    DatasetSummary,
    Issue,
    Recommendation,
    RecommendationList,
    ShapeHypothesis,
)
from stateframe.targets import infer_target_candidates


def build_recommendations(
    df: pd.DataFrame,
    summary: DatasetSummary,
    columns: dict[str, ColumnProfile],
    issues: list[Issue],
    shapes: list[ShapeHypothesis],
    *,
    target: str | None = None,
    time: str | None = None,
    goal: str = "first-look",
    config: ScanConfig | None = None,
) -> RecommendationList:
    recommendations: list[Recommendation] = []
    issue_ids = {issue.id for issue in issues}

    if summary.missing_cells > 0:
        recommendations.append(
            Recommendation(
                id="quality.missingness",
                title="Profile missingness patterns",
                lens="quality.missingness",
                score=0.86,
                confidence=1.0,
                cost="cheap",
                category="quality",
                evidence=[f"{summary.missing_cells} missing cells detected"],
                why_it_matters="Missingness can be random, structured, or tied to time and groups.",
                code='profile.run("quality.missingness")',
                produces=["missingness_by_column", "row_missingness_summary"],
                mode="exact" if not summary.sample_used else "sampled",
            )
        )

    cleaning_columns = [
        column.name
        for column in columns.values()
        if column.binary_profile is not None
        or column.semantic_type in {"numeric-like", "datetime-like"}
        or bool(column.value_profile and column.value_profile.missing_like_values)
        or column.missing_count > 0
        or float(column.metrics.get("iqr_outlier_ratio") or 0.0) >= 0.01
        or column.semantic_type == "geographic"
    ]
    if cleaning_columns or summary.duplicate_rows:
        recommendations.append(
            Recommendation(
                id="cleaning.transform_preview",
                title="Preview safe cleaning actions",
                lens="cleaning.transform_preview",
                score=0.87,
                confidence=0.84,
                cost="cheap",
                category="cleaning",
                columns=cleaning_columns[:8],
                evidence=[
                    item
                    for item in [
                        f"{len(cleaning_columns)} columns have binary, parsing, missingness, or outlier cleanup opportunities",
                        f"{summary.duplicate_rows} duplicate rows detected" if summary.duplicate_rows else "",
                    ]
                    if item
                ],
                why_it_matters="A previewable cleaning plan turns scan findings into reversible, auditable transformations.",
                code="scan.cleaning_plan().preview()",
                produces=["transform_actions", "conversion_preview"],
            )
        )

    modeling_columns = [
        column.name
        for column in columns.values()
        if column.name != target
        and column.semantic_type
        in {
            "numeric",
            "amount",
            "numeric-like",
            "percentage",
            "proportion",
            "numeric_discrete",
            "category",
            "string",
            "binary",
            "nullable_binary",
            "boolean",
            "datetime",
            "datetime-like",
            "identifier",
            "constant",
            "mostly_missing",
        }
    ]
    if modeling_columns and (goal == "modeling" or target is not None):
        target_text = f" with target {target}" if target else ""
        recommendations.append(
            Recommendation(
                id="modeling.readiness",
                title="Preview modeling feature preparation",
                lens="modeling.readiness",
                score=0.9 if goal == "modeling" else 0.78,
                confidence=0.82,
                cost="cheap",
                category="modeling",
                columns=([target] if target else []) + modeling_columns[:7],
                evidence=[
                    f"{len(modeling_columns)} candidate feature columns available{target_text}",
                    "plan can review identifiers, missing values, encoding, date features, and scaling",
                ],
                evidence_sources=["model", "statistical", "quality", "cleaning"],
                why_it_matters="A feature-prep plan makes modeling transformations explicit, editable, and replayable before training.",
                code="scan.modeling_plan().preview()",
                produces=["feature_prep_plan", "modeling_transform_actions"],
            )
        )

    footprint_columns = [
        column.name
        for column in columns.values()
        if column.semantic_type in {"category", "string", "postal_code", "geographic"}
        or column.dtype.lower().startswith(("int", "uint", "float"))
        or column.dtype in {"Int64", "UInt64", "Float64"}
    ]
    if footprint_columns:
        recommendations.append(
            Recommendation(
                id="footprint.optimize",
                title="Find safe dtype memory optimizations",
                lens="footprint.optimize",
                score=0.8 if summary.memory_bytes >= 1_000_000 else 0.68,
                confidence=0.86,
                cost="low",
                category="performance",
                columns=footprint_columns[:8],
                evidence=[
                    f"{len(footprint_columns)} columns may have dtype footprint optimization opportunities",
                    f"current DataFrame memory estimate: {summary.memory_bytes:,} bytes",
                ],
                evidence_sources=["performance", "statistical", "cleaning"],
                why_it_matters="Downcasting numeric dtypes and categorizing repeated labels can make large EDA sessions faster and lighter.",
                code='profile.run("footprint.optimize")',
                produces=["memory_savings_estimate", "dtype_transform_plan"],
            )
        )

    datetime_columns = [
        column for column in columns.values() if column.semantic_type in {"datetime", "datetime-like"}
    ]
    for column in datetime_columns:
        recommendations.append(
            Recommendation(
                id=f"time.cadence.{column.name}",
                title=f"Analyze cadence for {column.name}",
                lens="time.cadence",
                score=0.88 if time == column.name else 0.78,
                confidence=0.86,
                cost="low",
                category="time",
                columns=[column.name],
                evidence=[f"{column.name} is {column.semantic_type}"],
                why_it_matters="Time columns often reveal gaps, duplicates, freshness issues, and trend risk.",
                code=f'profile.run("time.cadence", column="{column.name}")',
                produces=["time_range", "gap_summary", "duplicate_timestamp_count"],
            )
        )

    identifier_columns = [column for column in columns.values() if column.semantic_type == "identifier"]
    if identifier_columns:
        recommendations.append(
            Recommendation(
                id="grain.keys",
                title="Infer row grain and key candidates",
                lens="grain.keys",
                score=0.82,
                confidence=0.82,
                cost="cheap",
                category="grain",
                columns=[column.name for column in identifier_columns[:5]],
                evidence=[f"identifier-like columns: {', '.join(c.name for c in identifier_columns[:5])}"],
                why_it_matters="Understanding what one row represents prevents duplicate, join, and leakage mistakes.",
                code='profile.run("grain.keys")',
                produces=["key_candidates", "identifier_repetition"],
            )
        )

    if target is None:
        target_candidates = infer_target_candidates(columns, config=config)
        if target_candidates:
            best = target_candidates[0]
            recommendations.append(
                Recommendation(
                    id="target.candidates",
                    title="Review possible target columns",
                    lens="target.candidates",
                    score=0.91 if best.confidence >= 0.5 else 0.72,
                    confidence=best.confidence,
                    cost="cheap",
                    category="target",
                    columns=[candidate.column for candidate in target_candidates[:5]],
                    evidence=[
                        f"strongest candidate: {best.column} ({best.inferred_task}, confidence {best.confidence:.2f})"
                    ],
                    why_it_matters="A confirmed target unlocks target-aware EDA, association scans, leakage checks, and modeling-readiness guidance.",
                    code="scan.target_candidates()",
                    produces=["ranked_target_candidates", "task_suggestions"],
                    mode="inferred",
                )
            )

    for column in columns.values():
        top_share = column.metrics.get("top_1pct_share")
        zero_ratio = float(column.metrics.get("zero_ratio") or 0.0)
        concentration_relevant = (
            column.semantic_type == "amount"
            and zero_ratio < 0.75
        ) or (
            top_share is not None and top_share >= 0.65 and zero_ratio < 0.25
        )
        if column.semantic_type in {"numeric", "amount", "numeric-like"} and concentration_relevant:
            if column.semantic_type == "amount":
                score = 0.76 if top_share is None else min(0.9, 0.66 + float(top_share) * 0.5)
            else:
                score = min(0.88, 0.55 + float(top_share or 0.0) * 0.4)
            recommendations.append(
                Recommendation(
                    id=f"concentration.lorenz.{column.name}",
                    title=f"Inspect concentration in {column.name}",
                    lens="concentration.lorenz",
                    score=score,
                    confidence=0.8,
                    cost="low",
                    category="concentration",
                    columns=[column.name],
                    evidence=[
                        f"{column.name} is {column.semantic_type}",
                        f"top 1 percent share: {top_share:.3f}" if top_share else "amount-like column name",
                        f"zero ratio: {zero_ratio:.3f}",
                    ],
                    why_it_matters="A few rows may dominate totals and make averages misleading.",
                    code=f'profile.run("concentration.lorenz", column="{column.name}")',
                    produces=["lorenz_curve", "gini", "top_share_metrics"],
                )
            )
        if column.semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion"}:
            score = 0.74
            if abs(float(column.metrics.get("skew") or 0.0)) >= 2:
                score += 0.08
            if float(column.metrics.get("iqr_outlier_ratio") or 0.0) >= 0.01:
                score += 0.06
            recommendations.append(
                Recommendation(
                    id=f"distribution.numeric.{column.name}",
                    title=f"Profile numeric distribution for {column.name}",
                    lens="distribution.numeric",
                    score=min(score, 0.9),
                    confidence=column.semantic_confidence,
                    cost="low",
                    category="distribution",
                    columns=[column.name],
                    evidence=[f"{column.name} is {column.semantic_type}"],
                    why_it_matters="Numeric distributions reveal skew, zero inflation, impossible values, and outliers.",
                    code=f'profile.run("distribution.numeric", column="{column.name}")',
                    produces=["quantile_summary", "tail_summary", "outlier_summary"],
                    mode="exact" if not summary.sample_used else "sampled",
                )
            )
        if column.semantic_type in {"category", "string"} and column.distinct_count <= 500:
            recommendations.append(
                Recommendation(
                    id=f"categorical.value_counts.{column.name}",
                    title=f"Inspect value counts for {column.name}",
                    lens="categorical.value_counts",
                    score=0.7 if column.distinct_count <= 50 else 0.62,
                    confidence=column.semantic_confidence,
                    cost="cheap",
                    category="categorical",
                    columns=[column.name],
                    evidence=[f"{column.distinct_count} distinct values"],
                    why_it_matters="Category distributions expose dominant, rare, inconsistent, and missing-like labels.",
                    code=f'profile.run("categorical.value_counts", column="{column.name}")',
                    produces=["value_counts", "rare_value_summary"],
                )
            )
        if column.binary_profile is not None:
            binary_score = 0.89 if column.binary_profile.ambiguous else 0.76
            if column.binary_profile.kind == "binary_categorical":
                binary_score = 0.6
            recommendations.append(
                Recommendation(
                    id=f"binary.flags.{column.name}",
                    title=f"Review binary mapping for {column.name}",
                    lens="binary.flags",
                    score=binary_score,
                    confidence=column.binary_profile.confidence,
                    cost="cheap",
                    category="binary",
                    columns=[column.name],
                    evidence=column.binary_profile.evidence,
                    why_it_matters="Messy binary encodings should be confirmed before modeling or aggregation.",
                    code=f'profile.run("binary.flags", column="{column.name}")',
                    produces=["normalized_values", "suggested_mapping"],
                )
            )
        if column.semantic_type == "text":
            recommendations.append(
                Recommendation(
                    id=f"text.lengths.{column.name}",
                    title=f"Profile text lengths for {column.name}",
                    lens="text.lengths",
                    score=0.7,
                    confidence=column.semantic_confidence,
                    cost="low",
                    category="text",
                    columns=[column.name],
                    evidence=[f"{column.name} is text-heavy"],
                    why_it_matters="Text length, emptiness, and uniqueness are strong first diagnostics for free-form text.",
                    code=f'profile.run("text.lengths", column="{column.name}")',
                    produces=["length_distribution", "word_count_summary"],
                )
            )

    numeric_columns = [
        column.name
        for column in columns.values()
        if column.semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion"}
    ]
    if 2 <= len(numeric_columns) <= 50:
        score = 0.72 if goal != "modeling" else 0.84
        recommendations.append(
            Recommendation(
                id="relationships.correlation",
                title="Scan numeric relationships",
                lens="relationships.correlation",
                score=score,
                confidence=0.78,
                cost="medium",
                category="relationships",
                columns=numeric_columns[:10],
                evidence=[f"{len(numeric_columns)} numeric columns are available"],
                why_it_matters="Relationship scans reveal redundancy, collinearity, and candidate feature groups.",
                code='profile.run("relationships.correlation")',
                produces=["pearson_correlation_matrix"],
            )
        )

    relationship_columns = [
        column.name
        for column in columns.values()
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
    ]
    if len(relationship_columns) >= 2:
        recommendations.append(
            Recommendation(
                id="relationships.mixed_associations",
                title="Scan mixed feature relationships",
                lens="relationships.mixed_associations",
                score=0.79 if target is None else 0.84,
                confidence=0.78,
                cost="medium",
                category="relationships",
                columns=relationship_columns[:10],
                evidence=[f"{len(relationship_columns)} relationship-compatible columns are available"],
                why_it_matters="Mixed associations catch numeric-categorical and categorical-categorical dependencies that ordinary correlation misses.",
                code='profile.run("relationships.mixed_associations")',
                produces=["association_table", "relationship_strengths"],
            )
        )

    if "type.numeric_like_string" in issue_ids or "type.datetime_like_string" in issue_ids:
        recommendations.append(
            Recommendation(
                id="quality.type_coercion",
                title="Review columns that look mis-typed",
                lens="quality.type_coercion",
                score=0.81,
                confidence=0.88,
                cost="cheap",
                category="types",
                evidence=["One or more columns appear parseable as a richer dtype"],
                why_it_matters="Mis-typed columns block the diagnostics that make EDA powerful.",
                code='profile.run("quality.type_coercion")',
                produces=["type_conversion_candidates"],
            )
        )

    if target and target in columns:
        recommendations.append(
            Recommendation(
                id=f"target.balance.{target}",
                title=f"Inspect target balance for {target}",
                lens="target.balance",
                score=0.9,
                confidence=0.9,
                cost="cheap",
                category="target",
                columns=[target],
                evidence=[f"target provided: {target}"],
                why_it_matters="Target balance shapes validation strategy, metrics, and baseline expectations.",
                code=f'profile.run("target.balance", column="{target}")',
                produces=["target_value_counts", "imbalance_summary"],
            )
        )
        candidate_feature_count = sum(
            1
            for column in columns.values()
            if column.name != target
            and column.semantic_type
            not in {"identifier", "datetime", "datetime-like", "text", "mostly_missing", "constant"}
        )
        if candidate_feature_count >= 2:
            recommendations.append(
                Recommendation(
                    id=f"modeling.baseline.{target}",
                    title=f"Train a quick baseline for {target}",
                    lens="modeling.baseline",
                    score=0.82 if goal == "modeling" else 0.7,
                    confidence=0.7,
                    cost="medium",
                    category="modeling",
                    columns=[target],
                    evidence=[
                        f"target selected: {target}",
                        f"{candidate_feature_count} candidate features after role filtering",
                    ],
                    why_it_matters="A fast baseline checks whether the prepared feature frame is model-ready and whether signal beats a naive predictor.",
                    code=f'profile.run("modeling.baseline", target="{target}")',
                    produces=["baseline_score", "model_score", "validation_summary"],
                )
            )
            recommendations.append(
                Recommendation(
                    id=f"modeling.experiment.{target}",
                    title=f"Run a configurable modeling experiment for {target}",
                    lens="modeling.experiment",
                    score=0.84 if goal == "modeling" else 0.74,
                    confidence=0.72,
                    cost="expensive",
                    category="modeling",
                    columns=[target],
                    evidence=[
                        f"target selected: {target}",
                        f"{candidate_feature_count} candidate features after role filtering",
                    ],
                    why_it_matters="A full experiment records split design, folds, estimator parameters, tuning results, metrics, and model observability in one replayable object.",
                    code='profile.run("modeling.experiment", spec={"estimator": "random_forest"})',
                    produces=["model_metrics", "cv_scores", "feature_importance", "shap_summary"],
                )
            )
            recommendations.append(
                Recommendation(
                    id=f"target.importance.{target}",
                    title=f"Model which features matter for {target}",
                    lens="target.importance",
                    score=0.83 if goal == "modeling" else 0.76,
                    confidence=0.72,
                    cost="medium",
                    category="target",
                    columns=[target],
                    evidence=[
                        f"target selected: {target}",
                        f"{candidate_feature_count} candidate features after role filtering",
                    ],
                    why_it_matters="A small exploratory model can rank likely signal and reveal suspiciously strong leakage candidates.",
                    code=f'profile.run("target.importance", target="{target}")',
                    produces=["baseline_score", "model_score", "feature_importance", "leakage_warnings"],
                )
            )
        recommendations.append(
            Recommendation(
                id=f"target.associations.{target}",
                title=f"Scan feature associations with {target}",
                lens="target.associations",
                score=0.86 if goal == "modeling" else 0.78,
                confidence=0.78,
                cost="medium",
                category="target",
                columns=[target],
                evidence=[f"target selected: {target}"],
                why_it_matters="Target-aware EDA surfaces likely signal, leakage candidates, and features worth plotting.",
                code=f'profile.run("target.associations", column="{target}")',
                produces=["numeric_target_associations", "categorical_target_associations"],
                mode="exact" if not summary.sample_used else "sampled",
            )
        )
        recommendations.append(
            Recommendation(
                id=f"target.best_splits.{target}",
                title=f"Find strongest simple splits for {target}",
                lens="target.best_splits",
                score=0.82 if goal == "modeling" else 0.74,
                confidence=0.76,
                cost="medium",
                category="target",
                columns=[target],
                evidence=[f"target selected: {target}"],
                why_it_matters="Entropy and variance-reduction splits expose simple decision rules, leakage candidates, and useful binning ideas before modeling.",
                code=f'profile.run("target.best_splits", column="{target}")',
                produces=["split_candidates", "information_gain", "variance_reduction"],
                mode="exact" if not summary.sample_used else "sampled",
            )
        )

    for shape in shapes:
        if shape.id == "wide_sparse_matrix":
            recommendations.append(
                Recommendation(
                    id="quality.sparsity",
                    title="Inspect sparsity across rows and columns",
                    lens="quality.sparsity",
                    score=0.74,
                    confidence=shape.confidence,
                    cost="low",
                    category="quality",
                    evidence=shape.evidence,
                    why_it_matters="Sparse-wide data often needs different summaries and modeling treatment.",
                    code='profile.run("quality.sparsity")',
                )
            )

    return _dedupe(recommendations, config=config)


def _dedupe(
    recommendations: list[Recommendation],
    *,
    config: ScanConfig | None = None,
) -> RecommendationList:
    by_id: dict[str, Recommendation] = {}
    for rec in recommendations:
        rec = _finalize_recommendation(rec, config=config)
        if rec is None:
            continue
        existing = by_id.get(rec.id)
        if existing is None or rec.score > existing.score:
            by_id[rec.id] = rec
    return RecommendationList(by_id.values())


def _finalize_recommendation(
    rec: Recommendation,
    *,
    config: ScanConfig | None,
) -> Recommendation | None:
    sources = list(rec.evidence_sources or _infer_sources(rec))
    visual_available = rec.visual_available or _lens_has_visual(rec.lens)
    produces = list(rec.produces)
    if visual_available and "visual" not in produces:
        produces.append("visual")

    score = rec.score
    if config is not None:
        allowed = set(config.active_recommendation_basis)
        if sources and not allowed.intersection(sources):
            return None
        weights = config.mode_source_weights
        if sources:
            score *= sum(weights.get(source, 1.0) for source in sources) / len(sources)
        if config.semantic_policy == "off" and sources == ["semantic"]:
            return None
        if config.visual_policy == "rich" and visual_available:
            score *= 1.06
        elif config.visual_policy == "none" and sources == ["visual"]:
            return None
    return replace(
        rec,
        score=round(float(min(score, 0.99)), 4),
        evidence_sources=sources,
        visual_available=visual_available,
        produces=produces,
    )


def _infer_sources(rec: Recommendation) -> list[EvidenceSource]:
    sources: set[EvidenceSource] = set()
    if rec.category in {"quality", "types"} or rec.lens.startswith("quality."):
        sources.update({"quality", "statistical"})
    if rec.category in {"distribution", "concentration", "categorical", "binary", "grain"}:
        sources.add("statistical")
    if rec.category == "binary" or rec.lens.startswith("binary.") or rec.lens.startswith("cleaning."):
        sources.add("cleaning")
    if rec.category == "performance" or rec.lens.startswith("footprint."):
        sources.add("performance")
    if rec.category == "time" or rec.lens.startswith("time."):
        sources.add("time")
    if rec.category == "modeling" or rec.lens.startswith("modeling."):
        sources.update({"model", "statistical"})
    if rec.category == "relationships" or rec.lens.startswith("relationships."):
        sources.add("relationship")
    if rec.category == "target" or rec.lens.startswith("target."):
        sources.add("target")
    if rec.lens == "target.importance":
        sources.add("model")
    if rec.lens in {"target.candidates", "grain.keys"}:
        sources.add("semantic")
    if _lens_has_visual(rec.lens):
        sources.add("visual")
    if not sources:
        sources.add("statistical")
    return sorted(sources)


def _lens_has_visual(lens: str) -> bool:
    return lens in {
        "quality.missingness",
        "target.candidates",
        "distribution.numeric",
        "categorical.value_counts",
        "binary.flags",
        "time.cadence",
        "target.balance",
        "target.associations",
        "target.best_splits",
        "target.importance",
        "concentration.lorenz",
        "relationships.correlation",
        "relationships.mixed_associations",
        "text.lengths",
    }
