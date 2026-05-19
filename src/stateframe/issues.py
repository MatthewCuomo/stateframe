"""Issue generation from profile facts."""

from __future__ import annotations

import pandas as pd

from stateframe.models import ColumnProfile, DatasetSummary, Issue


SEVERITY_ORDER = {"error": 3, "warning": 2, "info": 1}


def build_issues(
    df: pd.DataFrame,
    summary: DatasetSummary,
    columns: dict[str, ColumnProfile],
    *,
    target: str | None = None,
) -> list[Issue]:
    issues: list[Issue] = []

    if len(set(df.columns)) != len(df.columns):
        issues.append(
            Issue(
                id="schema.duplicate_column_names",
                title="Dataset has duplicate column names",
                severity="error",
                confidence=1.0,
                category="schema",
                why_it_matters="Duplicate names make column-level analysis ambiguous.",
                suggested_action="Rename duplicate columns before deeper EDA.",
                method="pandas.columns",
            )
        )

    if summary.duplicate_rows:
        ratio = summary.duplicate_rows / summary.row_count if summary.row_count else 0.0
        issues.append(
            Issue(
                id="rows.duplicates",
                title=f"{summary.duplicate_rows} duplicate rows found",
                severity="warning" if ratio >= 0.01 else "info",
                confidence=1.0,
                category="quality",
                why_it_matters="Duplicate rows can inflate counts, totals, and model confidence.",
                suggested_action="Inspect duplicate rows and confirm whether they are expected.",
                method="pandas.DataFrame.duplicated",
            )
        )

    for column in columns.values():
        _missingness_issue(column, issues)
        _constant_issue(column, issues)
        _near_constant_issue(column, issues)
        _semantic_issue(column, issues)
        _binary_issue(column, issues)
        _numeric_issues(column, issues)
        _datetime_issues(column, issues)
        _categorical_issues(column, issues)

    if target and target in columns:
        _target_issues(columns[target], issues)

    return sorted(
        issues,
        key=lambda issue: (SEVERITY_ORDER[issue.severity], issue.confidence),
        reverse=True,
    )


def _missingness_issue(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.missing_ratio >= 0.95:
        issues.append(
            Issue(
                id="missingness.mostly_missing",
                title=f"{column.name} is mostly missing",
                severity="warning",
                confidence=1.0,
                category="missingness",
                columns=[column.name],
                why_it_matters="Mostly missing columns often carry little direct signal and may need special handling.",
                suggested_action="Decide whether to drop it, impute it, or keep a missingness indicator.",
                method="isna.mean",
            )
        )
    elif column.missing_ratio >= 0.5:
        issues.append(
            Issue(
                id="missingness.high_missingness",
                title=f"{column.name} has high missingness",
                severity="warning",
                confidence=1.0,
                category="missingness",
                columns=[column.name],
                why_it_matters="High missingness can bias summaries and downstream models.",
                suggested_action="Profile missingness by group, time, or related columns.",
                method="isna.mean",
            )
        )


def _constant_issue(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.non_null_count > 0 and column.distinct_count <= 1:
        issues.append(
            Issue(
                id="distribution.constant",
                title=f"{column.name} is constant",
                severity="info",
                confidence=1.0,
                category="distribution",
                columns=[column.name],
                why_it_matters="Constant columns usually do not help EDA or modeling.",
                suggested_action="Consider dropping it unless the constant value has business meaning.",
                method="nunique",
            )
        )


def _near_constant_issue(column: ColumnProfile, issues: list[Issue]) -> None:
    top_ratio = column.metrics.get("top_ratio")
    if column.distinct_count > 1 and top_ratio is not None and top_ratio >= 0.98:
        issues.append(
            Issue(
                id="distribution.near_constant",
                title=f"{column.name} is near-constant",
                severity="info",
                confidence=0.9,
                category="distribution",
                columns=[column.name],
                why_it_matters="Near-constant columns often add noise and can hide rare but important cases.",
                suggested_action="Inspect the rare values before dropping or recoding.",
                method="value_counts",
            )
        )


def _semantic_issue(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.semantic_type == "numeric-like":
        issues.append(
            Issue(
                id="type.numeric_like_string",
                title=f"{column.name} looks numeric but is stored as {column.dtype}",
                severity="info",
                confidence=0.9,
                category="types",
                columns=[column.name],
                why_it_matters="String-stored numbers can break numeric summaries and sorting.",
                suggested_action="Consider parsing it to a numeric dtype.",
                method="pd.to_numeric sample parse",
            )
        )
    elif column.semantic_type == "datetime-like":
        issues.append(
            Issue(
                id="type.datetime_like_string",
                title=f"{column.name} looks datetime-like but is stored as {column.dtype}",
                severity="info",
                confidence=0.85,
                category="types",
                columns=[column.name],
                why_it_matters="String-stored timestamps can hide cadence, gap, and freshness issues.",
                suggested_action="Consider parsing it to a datetime dtype.",
                method="pd.to_datetime sample parse",
            )
        )
    if column.metrics.get("semantic_null_count", 0) > column.missing_count:
        issues.append(
            Issue(
                id="missingness.missing_like_strings",
                title=f"{column.name} has missing-like string values",
                severity="info",
                confidence=0.9,
                category="missingness",
                columns=[column.name],
                why_it_matters="Strings such as blank, NA, unknown, or ? can hide missingness from ordinary null checks.",
                suggested_action="Treat missing-like strings as nulls before deeper analysis.",
                method="missing-like token scan",
            )
        )


def _binary_issue(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.binary_profile is None:
        return
    if column.binary_profile.kind == "binary_categorical":
        issues.append(
            Issue(
                id="binary.two_category_categorical",
                title=f"{column.name} has two observed categories",
                severity="info",
                confidence=column.binary_profile.confidence,
                category="binary",
                columns=[column.name],
                why_it_matters="Two-category columns can be useful, but they are not always true yes/no flags.",
                suggested_action="Inspect category meaning before applying a 0/1 mapping.",
                method="binary value normalization",
            )
        )
        return
    if column.binary_profile.ambiguous:
        issues.append(
            Issue(
                id="binary.ambiguous_mapping",
                title=f"{column.name} has an ambiguous binary mapping",
                severity="warning",
                confidence=column.binary_profile.confidence,
                category="binary",
                columns=[column.name],
                why_it_matters="Binary-like values such as 1/null may mean false-by-absence or unknown missingness.",
                suggested_action="Confirm the intended mapping before converting this flag.",
                method="binary value normalization",
            )
        )
    else:
        issues.append(
            Issue(
                id="binary.detected",
                title=f"{column.name} looks like a binary flag",
                severity="info",
                confidence=column.binary_profile.confidence,
                category="binary",
                columns=[column.name],
                why_it_matters="Binary flags often deserve proportion checks, target-rate checks, and consistent encoding.",
                suggested_action="Review or apply the suggested binary mapping.",
                method="binary value normalization",
            )
        )


def _numeric_issues(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.semantic_type not in {
        "numeric",
        "amount",
        "numeric-like",
        "percentage",
        "proportion",
        "identifier",
    }:
        return

    top_share = column.metrics.get("top_1pct_share")
    if top_share is not None and top_share >= 0.5 and column.semantic_type != "identifier":
        issues.append(
            Issue(
                id="concentration.top_1pct_dominates",
                title=f"{column.name} is highly concentrated",
                severity="warning",
                confidence=0.8,
                category="concentration",
                columns=[column.name],
                why_it_matters="A few rows may dominate totals, means, and business interpretation.",
                suggested_action="Run a Lorenz or Pareto concentration lens.",
                method="top 1 percent share",
            )
        )

    zero_ratio = column.metrics.get("zero_ratio")
    if zero_ratio is not None and zero_ratio >= 0.8:
        issues.append(
            Issue(
                id="distribution.zero_inflated",
                title=f"{column.name} has many zero values",
                severity="info",
                confidence=0.85,
                category="distribution",
                columns=[column.name],
                why_it_matters="Zero-heavy variables often need separate zero vs non-zero analysis.",
                suggested_action="Inspect zero rates by group or time.",
                method="zero ratio",
            )
        )

    outlier_ratio = column.metrics.get("iqr_outlier_ratio")
    if outlier_ratio is not None and outlier_ratio >= 0.05:
        issues.append(
            Issue(
                id="distribution.iqr_outliers",
                title=f"{column.name} has many IQR outliers",
                severity="info",
                confidence=0.75,
                category="distribution",
                columns=[column.name],
                why_it_matters="Outliers can dominate scale-sensitive summaries and plots.",
                suggested_action="Inspect the distribution tail and row examples.",
                method="IQR fences",
            )
        )


def _datetime_issues(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.semantic_type not in {"datetime", "datetime-like"}:
        return
    duplicates = column.metrics.get("duplicate_timestamp_count")
    if duplicates:
        issues.append(
            Issue(
                id="time.duplicate_timestamps",
                title=f"{column.name} has duplicate timestamps",
                severity="info",
                confidence=0.85,
                category="time",
                columns=[column.name],
                why_it_matters="Duplicate timestamps can be normal for event logs but risky for single-series data.",
                suggested_action="Run cadence analysis, optionally grouped by entity.",
                method="duplicated timestamps",
            )
        )


def _categorical_issues(column: ColumnProfile, issues: list[Issue]) -> None:
    if column.semantic_type not in {"category", "string", "identifier", "email", "url", "postal_code"}:
        return
    if column.semantic_type == "identifier":
        return
    if column.distinct_count >= 50 and column.distinct_ratio >= 0.5:
        issues.append(
            Issue(
                id="categorical.high_cardinality",
                title=f"{column.name} has high cardinality",
                severity="info",
                confidence=0.8,
                category="categorical",
                columns=[column.name],
                why_it_matters="High-cardinality categories can make plots noisy and modeling encodings risky.",
                suggested_action="Inspect rare categories and consider grouping or hashing strategies.",
                method="nunique ratio",
            )
        )


def _target_issues(column: ColumnProfile, issues: list[Issue]) -> None:
    top_ratio = column.metrics.get("top_ratio")
    if top_ratio is not None and top_ratio >= 0.9:
        issues.append(
            Issue(
                id="target.imbalance",
                title=f"Target {column.name} is highly imbalanced",
                severity="warning",
                confidence=0.9,
                category="target",
                columns=[column.name],
                why_it_matters="Severe target imbalance can make accuracy misleading and hide rare classes.",
                suggested_action="Use target-aware EDA and metrics that respect class imbalance.",
                method="target value_counts",
            )
        )
