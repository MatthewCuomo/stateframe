"""Binary flag detection and normalization helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from stateframe.models import BinaryProfile
from stateframe.utils import clean_metric


TRUE_VALUES = {
    "1",
    "true",
    "t",
    "yes",
    "y",
    "active",
    "enabled",
    "on",
    "success",
    "pass",
    "passed",
    "positive",
}

FALSE_VALUES = {
    "0",
    "false",
    "f",
    "no",
    "n",
    "inactive",
    "disabled",
    "off",
    "failure",
    "fail",
    "failed",
    "negative",
}

MISSING_LIKE_VALUES = {
    "",
    " ",
    "na",
    "n/a",
    "nan",
    "none",
    "null",
    "nil",
    "missing",
    "unknown",
    "?",
    "-",
    "--",
}

FLAG_NAME_HINTS = ("is_", "has_", "had_", "can_", "should_", "flag", "indicator", "opt_in")


def normalize_binary_value(value: Any) -> str:
    if pd.isna(value):
        return "missing"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            if float(value) == 1.0:
                return "true"
            if float(value) == 0.0:
                return "false"
        except (TypeError, ValueError):
            pass
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return "true"
    if text in FALSE_VALUES:
        return "false"
    if text in MISSING_LIKE_VALUES:
        return "missing"
    return "other"


def looks_missing_like(value: Any) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip().lower() in MISSING_LIKE_VALUES


def missing_like_counts(series: pd.Series) -> dict[str, int]:
    if series.empty:
        return {}
    counts: dict[str, int] = {}
    for value in series.dropna():
        text = str(value)
        if text.strip().lower() in MISSING_LIKE_VALUES:
            counts[text] = counts.get(text, 0) + 1
    return counts


def detect_binary_profile(name: str, series: pd.Series) -> BinaryProfile | None:
    """Infer whether a column behaves like a binary flag.

    The function is intentionally conservative with positive-only nullable
    flags because ``1/null`` can mean either false-by-absence or unknown.
    """

    if series.shape[0] == 0:
        return None

    counts = series.value_counts(dropna=False)
    if counts.shape[0] > 5:
        return None

    raw_values = [clean_metric(value) for value in counts.index.tolist()]
    normalized = [normalize_binary_value(value) for value in counts.index.tolist()]
    normalized_set = set(normalized)
    evidence = [
        f"observed values: {raw_values}",
        f"normalized values: {sorted(normalized_set)}",
    ]

    mapping: dict[Any, Any] = {}
    for value in counts.index.tolist():
        normalized_value = normalize_binary_value(value)
        if normalized_value == "true":
            mapping[clean_metric(value)] = 1
        elif normalized_value == "false":
            mapping[clean_metric(value)] = 0
        elif normalized_value == "missing":
            mapping[clean_metric(value)] = None

    name_lower = name.lower()
    name_has_flag_hint = any(hint in name_lower for hint in FLAG_NAME_HINTS)
    if name_has_flag_hint:
        evidence.append("name contains a common flag hint")

    if normalized_set <= {"true", "false"} and {"true", "false"} <= normalized_set:
        return BinaryProfile(
            kind="clean_binary",
            confidence=0.98,
            values=raw_values,
            normalized_values=sorted(normalized_set),
            suggested_mapping=mapping,
            evidence=evidence,
        )

    if normalized_set <= {"true", "false", "missing"} and {"true", "false"} <= normalized_set:
        return BinaryProfile(
            kind="nullable_binary",
            confidence=0.94,
            values=raw_values,
            normalized_values=sorted(normalized_set),
            suggested_mapping=mapping,
            evidence=evidence,
        )

    if normalized_set <= {"true", "missing"} and "true" in normalized_set:
        confidence = 0.78 if name_has_flag_hint else 0.64
        return BinaryProfile(
            kind="positive_only_nullable_flag",
            confidence=confidence,
            values=raw_values,
            normalized_values=sorted(normalized_set),
            suggested_mapping=mapping,
            null_policy="preserve",
            ambiguous=True,
            evidence=evidence
            + ["null may mean false, unknown, or not collected; preserve by default"],
        )

    non_missing_norm = {value for value in normalized_set if value != "missing"}
    non_missing_count = sum(1 for value in normalized if value != "missing")
    if len(non_missing_norm) == 1 and non_missing_count > 0 and counts.shape[0] <= 2:
        return BinaryProfile(
            kind="single_observed_binary_state",
            confidence=0.55,
            values=raw_values,
            normalized_values=sorted(normalized_set),
            suggested_mapping=mapping,
            null_policy="preserve",
            ambiguous=True,
            evidence=evidence + ["only one non-missing binary state was observed"],
        )

    non_missing_values = [value for value in counts.index.tolist() if not looks_missing_like(value)]
    if len(non_missing_values) == 2:
        kind = "binary_flag" if name_has_flag_hint else "binary_categorical"
        confidence = 0.82 if name_has_flag_hint else 0.72
        fallback_mapping = {
            clean_metric(non_missing_values[0]): 0,
            clean_metric(non_missing_values[1]): 1,
        }
        return BinaryProfile(
            kind=kind,
            confidence=confidence,
            values=raw_values,
            normalized_values=sorted(normalized_set),
            suggested_mapping=fallback_mapping,
            ambiguous=not name_has_flag_hint,
            evidence=evidence + ["exactly two non-missing values were observed"],
        )

    return None
