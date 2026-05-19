"""Structured insight generation from issues and scan facts."""

from __future__ import annotations

from stateframe.models import (
    ColumnProfile,
    DatasetSummary,
    Insight,
    Issue,
    TargetCandidate,
    TargetProfile,
    TimeCandidate,
)


def build_insights(
    summary: DatasetSummary,
    columns: dict[str, ColumnProfile],
    issues: list[Issue],
    *,
    target_candidates: list[TargetCandidate],
    target_profile: TargetProfile | None,
    time_candidates: list[TimeCandidate],
) -> list[Insight]:
    insights: list[Insight] = []

    if summary.duplicate_rows:
        ratio = summary.duplicate_rows / summary.row_count if summary.row_count else 0.0
        insights.append(
            Insight(
                id="dataset.duplicate_rows",
                category="data_quality",
                severity="warning" if ratio >= 0.01 else "info",
                confidence=1.0,
                message=f"{summary.duplicate_rows} duplicate rows were found.",
                evidence={"duplicate_rows": summary.duplicate_rows, "duplicate_row_ratio": ratio},
                recommendations=["quality.duplicates", "grain.keys"],
            )
        )

    if summary.missing_cell_ratio > 0:
        insights.append(
            Insight(
                id="dataset.missing_cells",
                category="missingness",
                severity="warning" if summary.missing_cell_ratio >= 0.2 else "info",
                confidence=1.0,
                message=f"{summary.missing_cell_ratio:.1%} of cells are missing.",
                evidence={
                    "missing_cells": summary.missing_cells,
                    "missing_cell_ratio": summary.missing_cell_ratio,
                },
                recommendations=["quality.missingness"],
            )
        )

    for issue in issues:
        insights.append(
            Insight(
                id=f"issue.{issue.id}",
                category=issue.category,
                severity=issue.severity,
                confidence=issue.confidence,
                columns=issue.columns,
                message=issue.title,
                evidence={"method": issue.method, "why_it_matters": issue.why_it_matters},
                recommendations=[issue.suggested_action] if issue.suggested_action else [],
                source_issue_id=issue.id,
            )
        )

    for column in columns.values():
        if column.binary_profile is not None:
            severity = (
                "warning"
                if column.binary_profile.ambiguous
                and column.binary_profile.kind != "binary_categorical"
                else "info"
            )
            insights.append(
                Insight(
                    id=f"binary.{column.name}",
                    category="binary",
                    severity=severity,
                    confidence=column.binary_profile.confidence,
                    columns=[column.name],
                    message=f"{column.name} looks like {column.binary_profile.kind}.",
                    evidence=column.binary_profile.to_dict(),
                    recommendations=["binary.flags", "unify_binary_flags"],
                )
            )
        if column.metrics.get("semantic_null_count", 0) > column.missing_count:
            insights.append(
                Insight(
                    id=f"missingness.semantic_nulls.{column.name}",
                    category="missingness",
                    severity="info",
                    confidence=0.9,
                    columns=[column.name],
                    message=f"{column.name} contains missing-like string values.",
                    evidence={
                        "raw_missing": column.missing_count,
                        "semantic_missing": column.metrics.get("semantic_null_count"),
                        "missing_like_values": column.metrics.get("missing_like_values"),
                    },
                    recommendations=["quality.type_coercion", "quality.missingness"],
                )
            )

    if target_profile is not None:
        insights.append(
            Insight(
                id=f"target.selected.{target_profile.column}",
                category="target",
                severity="info",
                confidence=target_profile.confidence,
                columns=[target_profile.column],
                message=f"{target_profile.column} is being treated as the target for {target_profile.task}.",
                evidence=target_profile.to_dict(),
                recommendations=["target.balance", "target.associations"],
            )
        )
    elif target_candidates:
        best = target_candidates[0]
        insights.append(
            Insight(
                id=f"target.candidate.{best.column}",
                category="target",
                severity="info",
                confidence=best.confidence,
                columns=[best.column],
                message=f"{best.column} is the strongest target candidate.",
                evidence=best.to_dict(),
                recommendations=["confirm_target", "target.balance"],
            )
        )

    if time_candidates:
        best_time = time_candidates[0]
        insights.append(
            Insight(
                id=f"time.candidate.{best_time.column}",
                category="time",
                severity="info",
                confidence=best_time.confidence,
                columns=[best_time.column],
                message=f"{best_time.column} is the strongest time-column candidate.",
                evidence=best_time.to_dict(),
                recommendations=["time.cadence", "time.records_over_time"],
            )
        )

    return _dedupe(insights)


def _dedupe(insights: list[Insight]) -> list[Insight]:
    best: dict[str, Insight] = {}
    for insight in insights:
        existing = best.get(insight.id)
        if existing is None or insight.confidence > existing.confidence:
            best[insight.id] = insight
    severity_rank = {"error": 3, "warning": 2, "info": 1}
    return sorted(
        best.values(),
        key=lambda insight: (severity_rank[insight.severity], insight.confidence),
        reverse=True,
    )
