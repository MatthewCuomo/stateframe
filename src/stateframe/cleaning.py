"""Previewable cleaning plans built from a stateframe scan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from stateframe.binary import MISSING_LIKE_VALUES
from stateframe.models import Profile
from stateframe.transforms import unify_binary_flags


@dataclass(frozen=True)
class TransformAction:
    column: str
    action: str
    confidence: float
    risk: str
    before_dtype: str
    after_dtype: str | None = None
    preview: dict[str, Any] = field(default_factory=dict)
    reversible: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "action": self.action,
            "confidence": self.confidence,
            "risk": self.risk,
            "before_dtype": self.before_dtype,
            "after_dtype": self.after_dtype,
            "preview": dict(self.preview),
            "reversible": self.reversible,
            "reason": self.reason,
        }


@dataclass
class CleaningPlan:
    profile: Profile = field(repr=False)
    actions: list[TransformAction] = field(default_factory=list)
    binary_null_policy: str = "preserve"

    def preview(self) -> pd.DataFrame:
        return pd.DataFrame([action.to_dict() for action in self.actions])

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "binary_null_policy": self.binary_null_policy,
        }

    def apply(
        self,
        data: pd.DataFrame | None = None,
        *,
        binary_null_policy: str | None = None,
        numeric_coerce: bool = True,
        datetime_parse: bool = True,
        standardize_missing_like: bool = True,
        trim_strings: bool = True,
    ) -> pd.DataFrame:
        result = (self.profile.data if data is None else data).copy()
        null_policy = binary_null_policy or self.binary_null_policy

        for action in self.actions:
            if action.column not in result.columns:
                continue
            if action.action == "missing_like_to_null" and standardize_missing_like:
                result[action.column] = _missing_like_to_null(result[action.column])
            elif action.action == "trim_strings" and trim_strings:
                result[action.column] = result[action.column].astype("string").str.strip()
            elif action.action == "parse_numeric" and numeric_coerce:
                result[action.column] = _parse_numeric(result[action.column])
            elif action.action == "parse_datetime" and datetime_parse:
                result[action.column] = pd.to_datetime(result[action.column], errors="coerce")
            elif action.action == "binary_mapping":
                binary = self.profile.binary_flags().get(action.column)
                if binary is not None and not binary.ambiguous:
                    result = unify_binary_flags(
                        result,
                        mappings={action.column: dict(binary.suggested_mapping)},
                        columns=[action.column],
                        null_policy=null_policy,
                    )
        return result


def build_cleaning_plan(
    profile: Profile,
    *,
    binary_null_policy: str = "preserve",
    include_string_trim: bool = True,
) -> CleaningPlan:
    actions: list[TransformAction] = []

    for column in profile.column_profiles.values():
        if column.value_profile and column.value_profile.missing_like_values:
            actions.append(
                TransformAction(
                    column=column.name,
                    action="missing_like_to_null",
                    confidence=0.95,
                    risk="low",
                    before_dtype=column.dtype,
                    after_dtype=column.dtype,
                    reversible=False,
                    reason="column contains strings that conventionally encode missing values",
                    preview={
                        "tokens": dict(column.value_profile.missing_like_values),
                        "semantic_null_count": column.value_profile.semantic_null_count,
                    },
                )
            )

        if column.semantic_type == "numeric-like":
            actions.append(
                TransformAction(
                    column=column.name,
                    action="parse_numeric",
                    confidence=float(column.metrics.get("numeric_parse_ratio") or 0.0),
                    risk="medium",
                    before_dtype=column.dtype,
                    after_dtype="float64",
                    reversible=False,
                    reason="most non-missing values parse as numeric",
                    preview={
                        "parse_ratio": column.metrics.get("numeric_parse_ratio"),
                        "invalid_after_parse": _invalid_numeric_count(profile.data[column.name]),
                    },
                )
            )

        if column.semantic_type == "datetime-like":
            actions.append(
                TransformAction(
                    column=column.name,
                    action="parse_datetime",
                    confidence=float(column.metrics.get("datetime_parse_ratio") or column.semantic_confidence),
                    risk="medium",
                    before_dtype=column.dtype,
                    after_dtype="datetime64[ns]",
                    reversible=False,
                    reason="values parse as datetimes",
                    preview={
                        "parse_ratio": column.metrics.get("datetime_parse_ratio"),
                        "invalid_after_parse": int(pd.to_datetime(profile.data[column.name], errors="coerce").isna().sum()),
                    },
                )
            )

        if column.binary_profile is not None and not column.binary_profile.ambiguous:
            actions.append(
                TransformAction(
                    column=column.name,
                    action="binary_mapping",
                    confidence=column.binary_profile.confidence,
                    risk="low",
                    before_dtype=column.dtype,
                    after_dtype="Int64",
                    reversible=False,
                    reason="binary-like values have a high-confidence standard mapping",
                    preview={
                        "mapping": dict(column.binary_profile.suggested_mapping),
                        "null_policy": binary_null_policy,
                    },
                )
            )

        if include_string_trim and column.semantic_type in {"category", "string", "text"}:
            whitespace_count = _whitespace_count(profile.data[column.name])
            if whitespace_count:
                actions.append(
                    TransformAction(
                        column=column.name,
                        action="trim_strings",
                        confidence=0.9,
                        risk="low",
                        before_dtype=column.dtype,
                        after_dtype="string",
                        reversible=False,
                        reason="some string values have leading or trailing whitespace",
                        preview={"affected_rows": whitespace_count},
                    )
                )

    return CleaningPlan(
        profile=profile,
        actions=_dedupe_actions(actions),
        binary_null_policy=binary_null_policy,
    )


def _parse_numeric(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _missing_like_to_null(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.lower()
    return series.mask(text.isin(MISSING_LIKE_VALUES))


def _invalid_numeric_count(series: pd.Series) -> int:
    text = series.dropna().astype("string").str.strip().str.lower()
    semantic_values = series.dropna()[~text.isin(MISSING_LIKE_VALUES)]
    if semantic_values.empty:
        return 0
    return int(_parse_numeric(semantic_values).isna().sum())


def _whitespace_count(series: pd.Series) -> int:
    non_null = series.dropna().astype("string")
    return int((non_null != non_null.str.strip()).sum())


def _dedupe_actions(actions: list[TransformAction]) -> list[TransformAction]:
    seen: set[tuple[str, str]] = set()
    result: list[TransformAction] = []
    for action in actions:
        key = (action.column, action.action)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result
