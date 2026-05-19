"""Target, task, time-column, and suggested-config inference."""

from __future__ import annotations

import pandas as pd

from stateframe.config import ScanConfig, SuggestedConfig
from stateframe.models import (
    ColumnProfile,
    TargetCandidate,
    TargetProfile,
    TaskInference,
    TimeCandidate,
)
from stateframe.utils import clean_metric, is_outcome_name, is_time_name


def infer_target_candidates(
    columns: dict[str, ColumnProfile],
    *,
    explicit_target: str | None = None,
    config: ScanConfig | None = None,
) -> list[TargetCandidate]:
    candidates: list[TargetCandidate] = []
    column_names = list(columns)
    semantic_policy = config.semantic_policy if config is not None else "auto"
    for index, column in enumerate(columns.values()):
        if column.semantic_type in {"identifier", "datetime", "datetime-like", "mostly_missing"}:
            continue
        name_is_outcome = semantic_policy != "off" and is_outcome_name(column.name)
        is_last_column = index == len(column_names) - 1
        score = 0.05
        evidence: list[str] = []

        if explicit_target and column.name == explicit_target:
            score += 0.85
            evidence.append("target was provided by user")

        if name_is_outcome:
            score += 0.45 if semantic_policy == "auto" else 0.18
            evidence.append("name resembles a target/outcome/label")

        if is_last_column:
            score += 0.08
            evidence.append("column is last in the dataframe")

        if column.binary_profile is not None or column.semantic_type in {"binary", "nullable_binary", "boolean"}:
            score += 0.18 if (name_is_outcome or is_last_column or explicit_target == column.name) else 0.04
            evidence.append("binary-like values")
        elif column.distinct_count <= 20 and column.distinct_ratio < 0.2:
            score += 0.12 if (name_is_outcome or is_last_column) else 0.02
            evidence.append("low-cardinality categorical/discrete values")
        elif column.semantic_type in {"numeric", "amount"}:
            score += 0.18 if name_is_outcome else 0.05
            evidence.append("numeric with potential regression target shape")

        if column.missing_ratio <= 0.05:
            score += 0.10
            evidence.append("low missingness")
        elif column.missing_ratio >= 0.5:
            score -= 0.25
            evidence.append("high missingness reduces target plausibility")

        if column.semantic_type in {"identifier", "email", "url", "postal_code"}:
            score -= 0.35
            evidence.append("identifier/contact/code-like semantic type")

        task = infer_task_for_column(column)
        confidence = max(0.0, min(score, 0.99))
        if confidence >= 0.28 or explicit_target == column.name:
            candidates.append(
                TargetCandidate(
                    column=column.name,
                    inferred_task=task,
                    confidence=confidence,
                    evidence=evidence,
                )
            )

    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def infer_task_for_column(column: ColumnProfile) -> str:
    if column.binary_profile is not None or column.semantic_type in {"binary", "nullable_binary", "boolean"}:
        return "binary_classification"
    if column.semantic_type in {"category", "string"} and column.distinct_count <= 20:
        return "multiclass_classification"
    if column.semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion"}:
        if column.distinct_count <= 20 and column.distinct_ratio < 0.2:
            return "multiclass_classification"
        return "regression"
    return "unknown"


def build_target_profile(
    df: pd.DataFrame,
    columns: dict[str, ColumnProfile],
    candidates: list[TargetCandidate],
    *,
    explicit_target: str | None = None,
    config: ScanConfig,
) -> TargetProfile | None:
    selected: TargetCandidate | None = None
    if explicit_target and explicit_target in columns:
        selected = next(
            (candidate for candidate in candidates if candidate.column == explicit_target),
            None,
        )
        if selected is None:
            column = columns[explicit_target]
            selected = TargetCandidate(
                column=explicit_target,
                inferred_task=infer_task_for_column(column),
                confidence=0.99,
                evidence=["target was provided by user"],
            )
    elif candidates and candidates[0].confidence >= config.target_auto_select_threshold:
        selected = candidates[0]

    if selected is None:
        return None

    counts = df[selected.column].value_counts(dropna=False).head(25)
    total = int(counts.sum())
    value_counts = [
        {
            "value": clean_metric(value),
            "count": int(count),
            "ratio": int(count) / total if total else 0.0,
        }
        for value, count in counts.items()
    ]
    imbalance_ratio = value_counts[0]["ratio"] if value_counts else None
    source = "user" if explicit_target == selected.column else "inferred"
    return TargetProfile(
        column=selected.column,
        task=selected.inferred_task,
        source=source,
        confidence=selected.confidence,
        value_counts=value_counts,
        imbalance_ratio=imbalance_ratio,
        evidence=selected.evidence,
    )


def infer_task(
    columns: dict[str, ColumnProfile],
    target_profile: TargetProfile | None,
    *,
    explicit_task: str | None = None,
) -> TaskInference:
    if explicit_task:
        return TaskInference(
            task=explicit_task,
            confidence=1.0,
            target=target_profile.column if target_profile else None,
            evidence=["task was provided by user"],
        )
    if target_profile is not None:
        return TaskInference(
            task=target_profile.task,
            confidence=min(0.95, target_profile.confidence),
            target=target_profile.column,
            evidence=[f"task inferred from target {target_profile.column}"],
            supporting_columns=[
                column.name
                for column in columns.values()
                if column.name != target_profile.column and column.role == "feature"
            ][:10],
        )

    text_count = sum(1 for column in columns.values() if column.semantic_type == "text")
    datetime_count = sum(
        1
        for column in columns.values()
        if column.semantic_type in {"datetime", "datetime-like"}
    )
    if text_count:
        return TaskInference(
            task="text_exploration",
            confidence=0.64,
            evidence=[f"{text_count} text-heavy columns detected"],
        )
    if datetime_count:
        return TaskInference(
            task="time_aware_eda",
            confidence=0.62,
            evidence=[f"{datetime_count} time-like columns detected"],
        )
    return TaskInference(
        task="unsupervised_eda",
        confidence=0.55,
        evidence=["no target selected"],
    )


def infer_time_candidates(
    columns: dict[str, ColumnProfile],
    *,
    config: ScanConfig,
) -> list[TimeCandidate]:
    candidates: list[TimeCandidate] = []
    for column in columns.values():
        name_time_allowed = config.semantic_policy != "off" and is_time_name(column.name)
        if column.semantic_type not in {"datetime", "datetime-like"} and not name_time_allowed:
            continue
        confidence = 0.2
        evidence: list[str] = []
        if column.semantic_type == "datetime":
            confidence += 0.5
            evidence.append("datetime dtype")
        elif column.semantic_type == "datetime-like":
            confidence += 0.42
            evidence.append("datetime-like strings")
        if name_time_allowed:
            confidence += 0.18 if config.semantic_policy == "auto" else 0.08
            evidence.append("name looks time-like")
        if column.missing_ratio <= 0.1:
            confidence += 0.08
            evidence.append("low missingness")

        metrics = column.metrics
        candidates.append(
            TimeCandidate(
                column=column.name,
                confidence=max(0.0, min(confidence, 0.99)),
                evidence=evidence,
                min_timestamp=metrics.get("min"),
                max_timestamp=metrics.get("max"),
                span_days=metrics.get("span_days"),
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def build_suggested_config(
    columns: dict[str, ColumnProfile],
    target_profile: TargetProfile | None,
    task: TaskInference | None,
    time_candidates: list[TimeCandidate],
    *,
    config: ScanConfig,
) -> SuggestedConfig:
    id_columns = [column.name for column in columns.values() if column.semantic_type == "identifier"]
    ignore_columns = list(id_columns)
    binary_mappings = {}
    ambiguous_binary_flags = []
    numeric_conversions = {}
    datetime_conversions = {}
    checks = ["quality.missingness"]
    assumptions = []

    for column in columns.values():
        if column.binary_profile is not None:
            if column.binary_profile.ambiguous:
                ambiguous_binary_flags.append(column.name)
                assumptions.append(
                    f"{column.name} is an ambiguous binary-like column; nulls are preserved by default."
                )
            else:
                binary_mappings[column.name] = dict(column.binary_profile.suggested_mapping)
                assumptions.append(
                    f"{column.name} can be mapped as a binary flag with confidence {column.binary_profile.confidence:.2f}."
                )
        if (
            column.semantic_type == "numeric-like"
            or (column.semantic_type == "amount" and not _is_physical_numeric(column.dtype))
        ) and column.metrics.get("numeric_parse_ratio", 0) >= 0.9:
            numeric_conversions[column.name] = "coerce_to_numeric"
            assumptions.append(f"{column.name} appears numeric-like and can be parsed.")
        if column.semantic_type == "datetime-like":
            datetime_conversions[column.name] = "parse_datetime"
            assumptions.append(f"{column.name} appears datetime-like and can be parsed.")

    time_column = None
    if time_candidates and time_candidates[0].confidence >= config.time_auto_select_threshold:
        time_column = time_candidates[0].column
        checks.append("time.cadence")
        assumptions.append(
            f"{time_column} is the likely main time column with confidence {time_candidates[0].confidence:.2f}."
        )

    target = target_profile.column if target_profile else None
    task_name = task.task if task else None
    if target_profile:
        checks.append("target.balance")
        checks.append("target.associations")
        assumptions.append(
            f"{target_profile.column} is treated as target via {target_profile.source} selection."
        )

    if any(column.semantic_type in {"numeric", "amount"} for column in columns.values()):
        checks.append("distribution.numeric")
    if any(column.semantic_type in {"category", "string"} for column in columns.values()):
        checks.append("categorical.value_counts")
    if binary_mappings or ambiguous_binary_flags:
        checks.append("binary.flags")

    return SuggestedConfig(
        target=target,
        task=task_name,
        time_column=time_column,
        id_columns=id_columns,
        ignore_columns=ignore_columns,
        binary_mappings=binary_mappings,
        ambiguous_binary_flags=ambiguous_binary_flags,
        numeric_conversions=numeric_conversions,
        datetime_conversions=datetime_conversions,
        recommended_checks=_dedupe_keep_order(checks),
        assumptions=assumptions,
        risk=config.risk,
    )


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _is_physical_numeric(dtype: str) -> bool:
    lowered = dtype.lower()
    return any(token in lowered for token in ["int", "float", "double", "decimal"])
