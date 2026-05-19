"""Core data models for scans, profiles, insights, recommendations, and lenses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal
from uuid import uuid4

from stateframe.config import EvidenceSource, SuggestedConfig

Severity = Literal["info", "warning", "error"]
Cost = Literal["metadata-only", "cheap", "low", "medium", "high", "expensive"]
ExactnessMode = Literal["exact", "approximate", "sampled", "metadata", "inferred"]


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


@dataclass(frozen=True)
class DatasetSummary:
    row_count: int
    column_count: int
    memory_bytes: int
    missing_cells: int
    missing_cell_ratio: float
    duplicate_rows: int | None
    columns_by_type: dict[str, int]
    backend: str = "pandas"
    scan_mode: str = "standard"
    sample_used: bool = False
    sample_size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "memory_bytes": self.memory_bytes,
            "missing_cells": self.missing_cells,
            "missing_cell_ratio": self.missing_cell_ratio,
            "duplicate_rows": self.duplicate_rows,
            "columns_by_type": dict(self.columns_by_type),
            "backend": self.backend,
            "scan_mode": self.scan_mode,
            "sample_used": self.sample_used,
            "sample_size": self.sample_size,
        }


@dataclass(frozen=True)
class ValueProfile:
    unique_count: int
    unique_ratio: float
    raw_null_count: int
    raw_null_ratio: float
    semantic_null_count: int
    semantic_null_ratio: float
    top_values: list[dict[str, Any]] = field(default_factory=list)
    rare_value_count: int = 0
    rare_value_ratio: float = 0.0
    dominant_value: Any = None
    dominant_value_ratio: float = 0.0
    entropy: float | None = None
    normalized_entropy: float | None = None
    missing_like_values: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unique_count": self.unique_count,
            "unique_ratio": self.unique_ratio,
            "raw_null_count": self.raw_null_count,
            "raw_null_ratio": self.raw_null_ratio,
            "semantic_null_count": self.semantic_null_count,
            "semantic_null_ratio": self.semantic_null_ratio,
            "top_values": list(self.top_values),
            "rare_value_count": self.rare_value_count,
            "rare_value_ratio": self.rare_value_ratio,
            "dominant_value": self.dominant_value,
            "dominant_value_ratio": self.dominant_value_ratio,
            "entropy": self.entropy,
            "normalized_entropy": self.normalized_entropy,
            "missing_like_values": dict(self.missing_like_values),
        }


@dataclass(frozen=True)
class SemanticTypeHypothesis:
    semantic_type: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_type": self.semantic_type,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class BinaryProfile:
    kind: str
    confidence: float
    values: list[Any] = field(default_factory=list)
    normalized_values: list[str] = field(default_factory=list)
    suggested_mapping: dict[Any, Any] = field(default_factory=dict)
    null_policy: str = "preserve"
    ambiguous: bool = False
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "values": list(self.values),
            "normalized_values": list(self.normalized_values),
            "suggested_mapping": dict(self.suggested_mapping),
            "null_policy": self.null_policy,
            "ambiguous": self.ambiguous,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    semantic_type: str
    non_null_count: int
    missing_count: int
    missing_ratio: float
    distinct_count: int
    distinct_ratio: float
    metrics: dict[str, Any] = field(default_factory=dict)
    top_values: list[dict[str, Any]] = field(default_factory=list)
    role: str = "feature"
    semantic_confidence: float = 0.5
    semantic_hypotheses: list[SemanticTypeHypothesis] = field(default_factory=list)
    value_profile: ValueProfile | None = None
    binary_profile: BinaryProfile | None = None
    quality: dict[str, Any] = field(default_factory=dict)
    examples: list[Any] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "semantic_type": self.semantic_type,
            "non_null_count": self.non_null_count,
            "missing_count": self.missing_count,
            "missing_ratio": self.missing_ratio,
            "distinct_count": self.distinct_count,
            "distinct_ratio": self.distinct_ratio,
            "metrics": dict(self.metrics),
            "top_values": list(self.top_values),
            "role": self.role,
            "semantic_confidence": self.semantic_confidence,
            "semantic_hypotheses": [
                hypothesis.to_dict() for hypothesis in self.semantic_hypotheses
            ],
            "value_profile": self.value_profile.to_dict() if self.value_profile else None,
            "binary_profile": self.binary_profile.to_dict() if self.binary_profile else None,
            "quality": dict(self.quality),
            "examples": list(self.examples),
            "recommended_actions": list(self.recommended_actions),
        }

    def semantic_types(self) -> list[SemanticTypeHypothesis]:
        return sorted(
            self.semantic_hypotheses,
            key=lambda hypothesis: hypothesis.confidence,
            reverse=True,
        )


@dataclass(frozen=True)
class Issue:
    id: str
    title: str
    severity: Severity
    confidence: float
    category: str
    columns: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    suggested_action: str = ""
    method: str = ""
    exact: bool = True
    evidence_sources: list[EvidenceSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "category": self.category,
            "columns": list(self.columns),
            "why_it_matters": self.why_it_matters,
            "suggested_action": self.suggested_action,
            "method": self.method,
            "exact": self.exact,
            "evidence_sources": list(self.evidence_sources),
        }


@dataclass(frozen=True)
class Insight:
    id: str
    category: str
    severity: Severity
    confidence: float
    columns: list[str] = field(default_factory=list)
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    source_issue_id: str | None = None
    evidence_sources: list[EvidenceSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "columns": list(self.columns),
            "message": self.message,
            "evidence": dict(self.evidence),
            "recommendations": list(self.recommendations),
            "source_issue_id": self.source_issue_id,
            "evidence_sources": list(self.evidence_sources),
        }


@dataclass(frozen=True)
class TargetCandidate:
    column: str
    inferred_task: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "inferred_task": self.inferred_task,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class TargetProfile:
    column: str
    task: str
    source: str
    confidence: float
    value_counts: list[dict[str, Any]] = field(default_factory=list)
    imbalance_ratio: float | None = None
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "task": self.task,
            "source": self.source,
            "confidence": self.confidence,
            "value_counts": list(self.value_counts),
            "imbalance_ratio": self.imbalance_ratio,
            "evidence": list(self.evidence),
        }

    def summary(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True)
class TaskInference:
    task: str
    confidence: float
    target: str | None = None
    evidence: list[str] = field(default_factory=list)
    supporting_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "confidence": self.confidence,
            "target": self.target,
            "evidence": list(self.evidence),
            "supporting_columns": list(self.supporting_columns),
        }


@dataclass(frozen=True)
class TimeCandidate:
    column: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    min_timestamp: Any = None
    max_timestamp: Any = None
    span_days: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "min_timestamp": self.min_timestamp,
            "max_timestamp": self.max_timestamp,
            "span_days": self.span_days,
        }


@dataclass(frozen=True)
class EvidenceFact:
    id: str
    subject: str
    value: Any
    mode: ExactnessMode
    method: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_sources: list[EvidenceSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "value": self.value,
            "mode": self.mode,
            "method": self.method,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
            "evidence_sources": list(self.evidence_sources),
        }


@dataclass(frozen=True)
class ShapeHypothesis:
    id: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    recommended_lenses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "recommended_lenses": list(self.recommended_lenses),
        }


@dataclass(frozen=True)
class Recommendation:
    id: str
    title: str
    lens: str
    score: float
    confidence: float
    cost: Cost
    category: str
    columns: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    why_it_matters: str = ""
    code: str = ""
    expected_value: str = ""
    produces: list[str] = field(default_factory=list)
    visual_available: bool = False
    source_metrics: dict[str, Any] = field(default_factory=dict)
    mode: ExactnessMode = "inferred"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "lens": self.lens,
            "score": self.score,
            "confidence": self.confidence,
            "cost": self.cost,
            "category": self.category,
            "columns": list(self.columns),
            "evidence": list(self.evidence),
            "evidence_sources": list(self.evidence_sources),
            "why_it_matters": self.why_it_matters,
            "code": self.code,
            "expected_value": self.expected_value,
            "produces": list(self.produces),
            "visual_available": self.visual_available,
            "source_metrics": dict(self.source_metrics),
            "mode": self.mode,
        }


class RecommendationList:
    """Small convenience wrapper around ranked recommendations."""

    def __init__(self, recommendations: Iterable[Recommendation]):
        self._items = sorted(
            list(recommendations),
            key=lambda rec: (rec.score, rec.confidence),
            reverse=True,
        )

    def __iter__(self) -> Iterator[Recommendation]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int | slice) -> Recommendation | list[Recommendation]:
        return self._items[index]

    def top(self, n: int = 5) -> list[Recommendation]:
        return self._items[:n]

    def by_category(self, category: str) -> "RecommendationList":
        return RecommendationList(rec for rec in self._items if rec.category == category)

    def by_source(
        self,
        sources: str | Iterable[str],
        *,
        match: str = "any",
    ) -> "RecommendationList":
        wanted = {sources} if isinstance(sources, str) else set(sources)
        if match == "all":
            return RecommendationList(
                rec for rec in self._items if wanted.issubset(set(rec.evidence_sources))
            )
        return RecommendationList(
            rec for rec in self._items if wanted.intersection(rec.evidence_sources)
        )

    def exclude_sources(self, sources: str | Iterable[str]) -> "RecommendationList":
        unwanted = {sources} if isinstance(sources, str) else set(sources)
        return RecommendationList(
            rec for rec in self._items if not unwanted.intersection(rec.evidence_sources)
        )

    def with_visuals(self, visual: bool = True) -> "RecommendationList":
        return RecommendationList(
            rec for rec in self._items if rec.visual_available is visual
        )

    def by_cost(self, max_cost: Cost) -> "RecommendationList":
        order = {
            "metadata-only": 0,
            "cheap": 1,
            "low": 2,
            "medium": 3,
            "high": 4,
            "expensive": 5,
        }
        max_rank = order[max_cost]
        return RecommendationList(
            rec for rec in self._items if order.get(rec.cost, 99) <= max_rank
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [rec.to_dict() for rec in self._items]

    def to_markdown(self) -> str:
        lines = [
            "| Recommendation | Lens | Sources | Cost | Why |",
            "| --- | --- | --- | --- | --- |",
        ]
        for rec in self._items:
            why = rec.why_it_matters.replace("|", "\\|")
            sources = ", ".join(rec.evidence_sources)
            lines.append(f"| {rec.title} | `{rec.lens}` | {sources} | {rec.cost} | {why} |")
        return "\n".join(lines)

    def _repr_markdown_(self) -> str:
        return self.to_markdown()


@dataclass(frozen=True)
class LensResult:
    id: str
    title: str
    data: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    plots: list["PlotResult"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "data": self.data,
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": [rec.to_dict() for rec in self.recommendations],
            "plots": [plot.to_dict(include_figure=False) for plot in self.plots],
        }

    def plot(self, **kwargs: Any):
        from stateframe.visuals import plot_lens_result

        return plot_lens_result(self, **kwargs)


@dataclass
class PlotResult:
    id: str
    title: str
    figure: Any = field(repr=False)
    data: Any = None
    description: str = ""
    interpretation_hints: list[str] = field(default_factory=list)
    source_lens: str | None = None

    def save(self, path: str | Path, **kwargs: Any) -> str:
        self.figure.savefig(path, bbox_inches="tight", **kwargs)
        return str(path)

    def to_dict(self, *, include_figure: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "interpretation_hints": list(self.interpretation_hints),
            "source_lens": self.source_lens,
            "data": self.data,
        }
        if include_figure:
            result["figure"] = self.figure
        return result


@dataclass
class Profile:
    summary_data: DatasetSummary
    column_profiles: dict[str, ColumnProfile]
    issue_list: list[Issue]
    recommendation_list: RecommendationList
    shape_hypotheses: list[ShapeHypothesis]
    data: Any = field(repr=False)
    target: str | None = None
    time: str | None = None
    goal: str = "first-look"
    mode: str = "standard"
    guidance: str = "guided"
    semantic_policy: str = "auto"
    visual_policy: str = "rich"
    explanation_level: str = "standard"
    recommendation_basis: list[str] = field(default_factory=list)
    insight_list: list[Insight] = field(default_factory=list)
    target_candidate_list: list[TargetCandidate] = field(default_factory=list)
    target_profile: TargetProfile | None = None
    task_inference: TaskInference | None = None
    time_candidate_list: list[TimeCandidate] = field(default_factory=list)
    suggested_config_data: SuggestedConfig | None = None
    facts: dict[str, EvidenceFact] = field(default_factory=dict)
    lens_results: dict[str, LensResult] = field(default_factory=dict)
    ledger: Any = field(default=None, repr=False)
    profile_id: str = field(default_factory=lambda: f"profile-{uuid4().hex[:10]}")
    dataset_name: str | None = None
    tree_name: str | None = None
    source: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return self.summary_data.to_dict()

    def columns(self) -> list[dict[str, Any]]:
        return [profile.to_dict() for profile in self.column_profiles.values()]

    def column(self, name: str) -> ColumnProfile:
        return self.column_profiles[name]

    def issues(
        self,
        *,
        severity: Severity | None = None,
        category: str | None = None,
        columns: list[str] | None = None,
    ) -> list[Issue]:
        issues = self.issue_list
        if severity is not None:
            issues = [issue for issue in issues if issue.severity == severity]
        if category is not None:
            issues = [issue for issue in issues if issue.category == category]
        if columns is not None:
            wanted = set(columns)
            issues = [issue for issue in issues if wanted.intersection(issue.columns)]
        return issues

    def insights(
        self,
        *,
        severity: Severity | None = None,
        category: str | None = None,
        columns: list[str] | None = None,
    ) -> list[Insight]:
        insights = self.insight_list
        if severity is not None:
            insights = [insight for insight in insights if insight.severity == severity]
        if category is not None:
            insights = [insight for insight in insights if insight.category == category]
        if columns is not None:
            wanted = set(columns)
            insights = [
                insight for insight in insights if wanted.intersection(insight.columns)
            ]
        severity_rank = {"error": 3, "warning": 2, "info": 1}
        return sorted(
            insights,
            key=lambda insight: (severity_rank[insight.severity], insight.confidence),
            reverse=True,
        )

    def target_candidates(self) -> list[TargetCandidate]:
        return sorted(
            self.target_candidate_list,
            key=lambda candidate: candidate.confidence,
            reverse=True,
        )

    def time_candidates(self) -> list[TimeCandidate]:
        return sorted(
            self.time_candidate_list,
            key=lambda candidate: candidate.confidence,
            reverse=True,
        )

    def binary_flags(self) -> dict[str, BinaryProfile]:
        return {
            column.name: column.binary_profile
            for column in self.column_profiles.values()
            if column.binary_profile is not None
        }

    def assumptions(self) -> list[str]:
        if self.suggested_config_data is None:
            return []
        return list(self.suggested_config_data.assumptions)

    def use_suggested(self, *, risk: str | None = None) -> SuggestedConfig:
        if self.suggested_config_data is None:
            return SuggestedConfig(risk="conservative")
        if risk is None or risk == self.suggested_config_data.risk:
            return self.suggested_config_data
        return SuggestedConfig(
            target=self.suggested_config_data.target,
            task=self.suggested_config_data.task,
            time_column=self.suggested_config_data.time_column,
            id_columns=list(self.suggested_config_data.id_columns),
            ignore_columns=list(self.suggested_config_data.ignore_columns),
            binary_mappings=dict(self.suggested_config_data.binary_mappings),
            ambiguous_binary_flags=list(self.suggested_config_data.ambiguous_binary_flags),
            numeric_conversions=dict(self.suggested_config_data.numeric_conversions),
            datetime_conversions=dict(self.suggested_config_data.datetime_conversions),
            recommended_checks=list(self.suggested_config_data.recommended_checks),
            assumptions=list(self.suggested_config_data.assumptions),
            risk=risk,  # type: ignore[arg-type]
        )

    @property
    def suggested_config(self) -> SuggestedConfig | None:
        return self.suggested_config_data

    @property
    def task(self) -> TaskInference | None:
        return self.task_inference

    def options(self) -> dict[str, list[str]]:
        return {
            family: [lens.id for lens in self.lenses(family=family)]
            for family in sorted({lens.family for lens in self.lenses()})
        }

    def lenses(self, *, family: str | None = None) -> list[Any]:
        from stateframe.lens_registry import available_lenses

        return available_lenses(self, family=family)

    def rubric(self, *, limit: int = 8) -> str:
        """Return a guided EDA rubric for the current scan."""

        summary = self.summary()
        lines = [
            "# stateframe Guided EDA Rubric",
            "",
            "## 1. Start With The Shape",
            f"- Rows: {summary['row_count']:,}",
            f"- Columns: {summary['column_count']:,}",
            f"- Missing cells: {summary['missing_cell_ratio']:.1%}",
        ]
        if summary.get("sample_used"):
            lines.append(f"- Scan is based on a sample of {summary['sample_size']:,} rows.")
        lines.extend(
            [
                "",
                "Likely dataset shapes:",
            ]
        )
        for shape in self.shapes()[:5]:
            evidence = "; ".join(shape.evidence[:2])
            lines.append(f"- `{shape.id}` ({shape.confidence:.2f}) - {evidence}")

        lines.extend(["", "## 2. Confirm The Roles"])
        if self.target_profile:
            lines.append(
                f"- Target selected: `{self.target_profile.column}` for `{self.target_profile.task}`."
            )
        elif self.target_candidate_list:
            lines.append("- No target was selected automatically. Possible targets to confirm:")
            for candidate in self.target_candidates()[:5]:
                lines.append(
                    f"  - `{candidate.column}` -> `{candidate.inferred_task}` ({candidate.confidence:.2f})"
                )
        else:
            lines.append("- No strong target candidate found. Continue with targetless EDA.")

        if self.time_candidate_list:
            lines.append("- Possible time axes:")
            for candidate in self.time_candidates()[:5]:
                lines.append(f"  - `{candidate.column}` ({candidate.confidence:.2f})")
        if self.binary_flags():
            ambiguous = [
                name
                for name, binary in self.binary_flags().items()
                if binary.ambiguous
            ]
            lines.append(f"- Binary-like columns detected: {len(self.binary_flags())}")
            if ambiguous:
                lines.append(f"- Ambiguous binary mappings to confirm: {', '.join(f'`{name}`' for name in ambiguous)}")

        lines.extend(["", "## 3. Inspect The First Risks"])
        for insight in self.insights()[:limit]:
            cols = ", ".join(f"`{column}`" for column in insight.columns) if insight.columns else "dataset"
            lines.append(f"- **{insight.severity}** {cols}: {insight.message}")

        lines.extend(["", "## 4. Run The Next Best Visuals"])
        lines.append("Start with:")
        lines.append("- `scan.plot_overview()`")
        lines.append("- `scan.plot_recommendation(1)`")
        lines.append("- `scan.plot_recommendations(n=4)`")
        lines.append("")
        lines.append("Top recommendations:")
        for index, rec in enumerate(self.recommendations().top(limit), start=1):
            cols = ", ".join(f"`{column}`" for column in rec.columns) if rec.columns else "dataset"
            lines.append(
                f"{index}. `{rec.lens}` on {cols} - {rec.title} ({rec.cost}, score {rec.score:.2f})"
            )

        lines.extend(["", "## 5. Make A Simple Selection"])
        if self.target_candidate_list and not self.target_profile:
            best = self.target_candidates()[0]
            lines.append(
                f"- To continue target-aware EDA, try: `target_scan = sf.scan(df, target=\"{best.column}\", sample_size=50_000)`"
            )
        if self.time_candidate_list and not self.time:
            best_time = self.time_candidates()[0]
            lines.append(
                f"- To pin the time axis, try: `sf.scan(df, time=\"{best_time.column}\", sample_size=50_000)`"
            )
        return "\n".join(lines)

    def _repr_markdown_(self) -> str:
        return self.rubric(limit=6)

    def print_rubric(self, *, limit: int = 8) -> None:
        print(self.rubric(limit=limit))

    def plot_overview(self, **kwargs: Any):
        from stateframe.visuals import plot_overview

        return plot_overview(self, **kwargs)

    def plot_missingness(self, *, limit: int = 25, **kwargs: Any):
        from stateframe.visuals import plot_missingness

        return plot_missingness(self, limit=limit, **kwargs)

    def plot_target_candidates(self, *, limit: int = 10, **kwargs: Any):
        from stateframe.visuals import plot_target_candidates

        return plot_target_candidates(self, limit=limit, **kwargs)

    def plot_column(self, column: str, **kwargs: Any):
        from stateframe.visuals import plot_column

        return plot_column(self, column, **kwargs)

    def plot_recommendation(self, recommendation: int | str | Recommendation = 1, **kwargs: Any):
        from stateframe.visuals import plot_recommendation

        return plot_recommendation(self, recommendation, **kwargs)

    def plot_recommendations(self, *, n: int = 4, **kwargs: Any):
        from stateframe.visuals import plot_recommendations

        return plot_recommendations(self, n=n, **kwargs)

    def view(
        self,
        *,
        max_rows: int = 25_000,
        height: int = 640,
        theme: str = "auto",
        title: str | None = None,
    ):
        """Render this profile in the interactive dataframe explorer."""

        from stateframe.interactive import view

        return view(
            self,
            max_rows=max_rows,
            height=height,
            theme=theme,
            title=title,
        )

    def ledger_view(
        self,
        *,
        height: int = 640,
        title: str | None = None,
    ):
        """Render the scan's ledger as a standalone notebook tree."""

        from stateframe.interactive import ledger_view

        return ledger_view(
            self,
            height=height,
            title=title,
        )

    def tree_view(
        self,
        *,
        height: int = 640,
        title: str | None = None,
    ):
        """Alias for ``ledger_view``."""

        return self.ledger_view(
            height=height,
            title=title,
        )

    def recommendations(
        self,
        *,
        max_cost: Cost | None = None,
        category: str | None = None,
        source: str | None = None,
        sources: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_sources: list[str] | tuple[str, ...] | set[str] | str | None = None,
        visual: bool | None = None,
        limit: int | None = None,
    ) -> RecommendationList:
        recs = self.recommendation_list
        if max_cost is not None:
            recs = recs.by_cost(max_cost)
        if category is not None:
            recs = recs.by_category(category)
        if source is not None:
            recs = recs.by_source(source)
        if sources is not None:
            recs = recs.by_source(sources)
        if exclude_sources is not None:
            recs = recs.exclude_sources(exclude_sources)
        if visual is not None:
            recs = recs.with_visuals(visual)
        if limit is not None:
            recs = RecommendationList(recs.top(limit))
        return recs

    def shapes(self) -> list[ShapeHypothesis]:
        return sorted(
            self.shape_hypotheses,
            key=lambda shape: shape.confidence,
            reverse=True,
        )

    def run(
        self,
        lens_id: str,
        *,
        ledger_parent: str | None = None,
        **params: Any,
    ) -> LensResult:
        from stateframe.lenses import run_lens

        result = run_lens(self, lens_id, **params)
        self.lens_results[result.id] = result
        if self.ledger is not None:
            self.ledger.record_lens(
                self,
                lens_id=result.id,
                params=params,
                result=result,
                parent_id=ledger_parent,
            )
        return result

    def with_target(self, target: str, **kwargs: Any) -> "Profile":
        from stateframe.config import ScanConfig
        from stateframe.profile import build_profile

        config = kwargs.pop(
            "config",
            ScanConfig.from_mode(
                self.mode,
                guidance=self.guidance,  # type: ignore[arg-type]
                semantic_policy=self.semantic_policy,  # type: ignore[arg-type]
                recommendation_basis=list(self.recommendation_basis),  # type: ignore[arg-type]
                visual_policy=self.visual_policy,  # type: ignore[arg-type]
                explanation_level=self.explanation_level,  # type: ignore[arg-type]
            ),
        )
        return build_profile(
            self.data,
            target=target,
            time=self.time,
            goal=self.goal,
            mode=self.mode,
            config=config,
            **kwargs,
        )

    def with_time(self, time: str, **kwargs: Any) -> "Profile":
        from stateframe.config import ScanConfig
        from stateframe.profile import build_profile

        config = kwargs.pop(
            "config",
            ScanConfig.from_mode(
                self.mode,
                guidance=self.guidance,  # type: ignore[arg-type]
                semantic_policy=self.semantic_policy,  # type: ignore[arg-type]
                recommendation_basis=list(self.recommendation_basis),  # type: ignore[arg-type]
                visual_policy=self.visual_policy,  # type: ignore[arg-type]
                explanation_level=self.explanation_level,  # type: ignore[arg-type]
            ),
        )
        return build_profile(
            self.data,
            target=self.target,
            time=time,
            goal=self.goal,
            mode=self.mode,
            config=config,
            **kwargs,
        )

    def cleaning_plan(self, **kwargs: Any):
        from stateframe.cleaning import build_cleaning_plan

        return build_cleaning_plan(self, **kwargs)

    def apply_cleaning(
        self,
        *,
        record: bool = True,
        title: str = "Apply cleaning plan",
        **kwargs: Any,
    ):
        plan = self.cleaning_plan()
        result = plan.apply(**kwargs)
        if record and self.ledger is not None:
            self.ledger.record_state(
                result,
                title=title,
                operation="cleaning.apply",
                params=kwargs,
                summary={
                    "action_count": len(plan.actions),
                    "row_count": int(result.shape[0]),
                    "column_count": int(result.shape[1]),
                },
            )
        return result

    def footprint_plan(self, **kwargs: Any):
        from stateframe.footprint import build_footprint_plan

        return build_footprint_plan(self, **kwargs)

    def optimize_footprint(
        self,
        *,
        record: bool = True,
        title: str = "Optimize dataframe footprint",
        **kwargs: Any,
    ):
        plan = self.footprint_plan(**kwargs)
        result = plan.apply()
        if record and self.ledger is not None:
            self.ledger.record_state(
                result,
                title=title,
                operation="footprint.optimize.apply",
                params=kwargs,
                summary=plan.summary(),
            )
        return result

    def record_state(
        self,
        data: Any,
        *,
        title: str,
        operation: str = "state.checkpoint",
        parent_id: str | None = None,
        copy_data: bool = True,
        options: list[dict[str, Any]] | None = None,
        code: str = "",
        note: str = "",
        **kwargs: Any,
    ):
        if self.ledger is None:
            from stateframe.ledger import LensLedger

            self.ledger = LensLedger.start(self)
        return self.ledger.record_state(
            data,
            title=title,
            operation=operation,
            parent_id=parent_id,
            copy_data=copy_data,
            options=options,
            code=code,
            note=note,
            params=kwargs,
        )

    def record_artifact(
        self,
        *,
        title: str,
        kind: str = "artifact",
        operation: str | None = None,
        parent_id: str | None = None,
        artifact: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        code: str = "",
        note: str = "",
        **kwargs: Any,
    ):
        """Attach a non-dataframe output, such as a plot or report, to the ledger."""

        if self.ledger is None:
            from stateframe.ledger import LensLedger

            self.ledger = LensLedger.start(self)
        return self.ledger.record_artifact(
            title=title,
            kind=kind,
            operation=operation,
            parent_id=parent_id,
            artifact=artifact,
            params=kwargs,
            summary=summary,
            metrics=metrics,
            code=code,
            note=note,
        )

    def checkout(self, entry_or_state_id: str):
        if self.ledger is None:
            raise ValueError("This profile does not have a ledger.")
        return self.ledger.checkout(entry_or_state_id)

    def activate(self, entry_id: str):
        """Make an existing ledger entry the active branch point."""

        if self.ledger is None:
            raise ValueError("This profile does not have a ledger.")
        return self.ledger.activate(entry_id)

    def record_note(
        self,
        title: str,
        note: str,
        *,
        parent_id: str | None = None,
    ):
        """Attach a human interpretation note to the ledger tree."""

        if self.ledger is None:
            from stateframe.ledger import LensLedger

            self.ledger = LensLedger.start(self)
        return self.ledger.record_note(
            title,
            note,
            parent_id=parent_id,
        )

    def ledger_path(self, entry_id: str | None = None) -> list[Any]:
        if self.ledger is None:
            return []
        return self.ledger.path(entry_id)

    def ledger_tree(self) -> list[dict[str, Any]]:
        if self.ledger is None:
            return []
        return self.ledger.tree()

    def ledger_report(self, path: str | Path | None = None) -> str:
        if self.ledger is None:
            return "# stateframe Lens Ledger\n\nNo ledger is attached to this profile."
        return self.ledger.to_markdown(path)

    def save_tree(self, **kwargs: Any):
        from stateframe import save

        return save.tree(self, **kwargs)

    def save_data(self, **kwargs: Any):
        from stateframe import save

        return save.data(self, **kwargs)

    def rename_tree(self, name: str):
        """Rename this profile's workspace tree without changing its stable id."""

        self.tree_name = str(name)
        from stateframe import workspace

        return workspace.current().rename_tree(self, name)

    def set_source_path(
        self,
        path: str | Path,
        *,
        reader_params: dict[str, Any] | None = None,
    ):
        """Set or update this tree's replayable base data path."""

        from stateframe import workspace
        from stateframe.io import source_from_path

        current_workspace = workspace.current()
        if not getattr(self, "tree_id", None):
            self.tree_id = current_workspace.tree_id_for_profile(self)
        self.source = source_from_path(
            path,
            reader_params=reader_params,
            previous=self.source,
        )
        try:
            return current_workspace.update_tree_source_path(
                self,
                path,
                reader_params=reader_params,
            )
        except KeyError:
            return current_workspace.register_profile(self)

    def run_recommended(
        self,
        *,
        limit: int = 3,
        max_cost: Cost = "medium",
    ) -> list[LensResult]:
        results = []
        for recommendation in self.recommendations(max_cost=max_cost).top(limit):
            params = {}
            if recommendation.columns:
                first_column = recommendation.columns[0]
                if recommendation.lens.startswith("time."):
                    params["column"] = first_column
                elif recommendation.lens.startswith("concentration."):
                    params["column"] = first_column
                elif recommendation.lens.startswith("distribution."):
                    params["column"] = first_column
                elif recommendation.lens.startswith("categorical."):
                    params["column"] = first_column
            results.append(self.run(recommendation.lens, **params))
        return results

    def run_top_recommendations(
        self,
        *,
        n: int = 3,
        max_cost: Cost = "medium",
    ) -> list[LensResult]:
        return self.run_recommended(limit=n, max_cost=max_cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "columns": self.columns(),
            "issues": [issue.to_dict() for issue in self.issue_list],
            "insights": [insight.to_dict() for insight in self.insight_list],
            "recommendations": self.recommendation_list.to_list(),
            "shapes": [shape.to_dict() for shape in self.shapes()],
            "target_candidates": [
                candidate.to_dict() for candidate in self.target_candidates()
            ],
            "target_profile": self.target_profile.to_dict() if self.target_profile else None,
            "task": self.task_inference.to_dict() if self.task_inference else None,
            "time_candidates": [
                candidate.to_dict() for candidate in self.time_candidates()
            ],
            "suggested_config": (
                self.suggested_config_data.to_dict()
                if self.suggested_config_data
                else None
            ),
            "facts": {fact_id: fact.to_dict() for fact_id, fact in self.facts.items()},
            "profile_id": self.profile_id,
            "dataset_name": self.dataset_name,
            "tree_name": self.tree_name,
            "source": dict(self.source),
            "target": self.target,
            "time": self.time,
            "goal": self.goal,
            "mode": self.mode,
            "guidance": self.guidance,
            "semantic_policy": self.semantic_policy,
            "visual_policy": self.visual_policy,
            "explanation_level": self.explanation_level,
            "recommendation_basis": list(self.recommendation_basis),
        }

    def to_json(self, path: str | Path | None = None, *, indent: int = 2) -> str:
        text = json.dumps(self.to_dict(), indent=indent, default=_json_default)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def to_markdown(self) -> str:
        summary = self.summary()
        lines = [
            "# stateframe Profile",
            "",
            f"- Rows: {summary['row_count']}",
            f"- Columns: {summary['column_count']}",
            f"- Missing cell ratio: {summary['missing_cell_ratio']:.3f}",
        ]
        if self.target_profile:
            lines.append(
                f"- Target: {self.target_profile.column} ({self.target_profile.task}, confidence {self.target_profile.confidence:.2f})"
            )
        elif self.target_candidate_list:
            best = self.target_candidates()[0]
            lines.append(
                f"- Likely target: {best.column} ({best.inferred_task}, confidence {best.confidence:.2f})"
            )
        if self.time_candidate_list:
            best_time = self.time_candidates()[0]
            lines.append(
                f"- Likely time column: {best_time.column} (confidence {best_time.confidence:.2f})"
            )

        lines.extend(["", "## Inferred Shapes"])
        for shape in self.shapes()[:5]:
            lines.append(f"- `{shape.id}` confidence {shape.confidence:.2f}")

        lines.extend(["", "## Top Insights"])
        for insight in self.insights()[:10]:
            cols = ", ".join(insight.columns) if insight.columns else "dataset"
            lines.append(
                f"- **{insight.severity}** `{insight.id}` on {cols}: {insight.message}"
            )

        lines.extend(["", "## Top Issues"])
        for issue in self.issue_list[:10]:
            cols = ", ".join(issue.columns) if issue.columns else "dataset"
            lines.append(f"- **{issue.severity}** `{issue.id}` on {cols}: {issue.title}")
        lines.extend(["", "## Recommended Next Lenses", self.recommendation_list.to_markdown()])
        return "\n".join(lines)
