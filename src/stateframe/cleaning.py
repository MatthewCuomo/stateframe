"""Previewable cleaning plans built from a stateframe scan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from stateframe.binary import MISSING_LIKE_VALUES
from stateframe.models import Profile
from stateframe.operations import all_operation_specs, get_operation_spec
from stateframe.transforms import clean_column_name, clean_numeric_outliers, rename_columns, unify_binary_flags


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
    family: str = "cleaning"
    title: str = ""
    controls: list[dict[str, Any]] = field(default_factory=list)
    control_values: dict[str, Any] = field(default_factory=dict)
    affected_rows: int | None = None
    examples: list[dict[str, Any]] = field(default_factory=list)
    applies_by_default: bool = True

    def to_dict(self) -> dict[str, Any]:
        spec = get_operation_spec(self.action)
        controls = self.controls
        if not controls and spec is not None:
            controls = [control.to_dict() for control in spec.controls]
        action_id = _action_id(self)
        return {
            "id": action_id,
            "column": self.column,
            "action": self.action,
            "operation_id": self.action,
            "family": self.family,
            "title": self.title or (spec.title if spec is not None else self.action.replace("_", " ").title()),
            "confidence": self.confidence,
            "risk": self.risk,
            "before_dtype": self.before_dtype,
            "after_dtype": self.after_dtype,
            "preview": dict(self.preview),
            "reversible": self.reversible,
            "reason": self.reason,
            "controls": controls,
            "control_values": dict(self.control_values),
            "affected_rows": self.affected_rows,
            "examples": list(self.examples),
            "applies_by_default": self.applies_by_default,
            "spec": spec.to_dict() if spec is not None else None,
        }


@dataclass
class CleaningPlan:
    profile: Profile = field(repr=False)
    actions: list[TransformAction] = field(default_factory=list)
    binary_null_policy: str = "preserve"
    settings: dict[str, Any] = field(default_factory=dict)

    def preview(self) -> pd.DataFrame:
        return pd.DataFrame([action.to_dict() for action in self.actions])

    def summary(self) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        affected_columns: list[str] = []
        for action in self.actions:
            by_action[action.action] = by_action.get(action.action, 0) + 1
            by_risk[action.risk] = by_risk.get(action.risk, 0) + 1
            if action.column not in affected_columns:
                affected_columns.append(action.column)
        return {
            "action_count": len(self.actions),
            "affected_columns": affected_columns,
            "affected_column_count": len(affected_columns),
            "by_action": by_action,
            "by_risk": by_risk,
            "binary_null_policy": self.binary_null_policy,
            "settings": dict(self.settings),
        }

    def operation_catalog(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in all_operation_specs(family="cleaning")]

    def operation_preview(self) -> dict[str, Any]:
        actions = [action.to_dict() for action in self.actions]
        return {
            **self.summary(),
            "catalog": self.operation_catalog(),
            "actions": actions,
            "presets": _cleaning_presets(actions),
        }

    def to_dict(self) -> dict[str, Any]:
        actions = [action.to_dict() for action in self.actions]
        return {
            **self.summary(),
            "actions": actions,
            "binary_null_policy": self.binary_null_policy,
            "catalog": self.operation_catalog(),
            "presets": _cleaning_presets(actions),
        }

    def apply(
        self,
        data: pd.DataFrame | None = None,
        *,
        binary_null_policy: str | None = None,
        binary_output: str = "int",
        apply_ambiguous_binary: bool = False,
        numeric_coerce: bool = True,
        datetime_parse: bool = True,
        datetime_dayfirst: bool = False,
        datetime_yearfirst: bool = False,
        standardize_missing_like: bool = True,
        trim_strings: bool = True,
        outlier_policy: str = "skip",
        outlier_method: str = "iqr",
        actions: list[str] | None = None,
        action_ids: list[str] | None = None,
        action_control_values: dict[str, dict[str, Any]] | None = None,
    ) -> pd.DataFrame:
        result = (self.profile.data if data is None else data).copy()
        null_policy = binary_null_policy or self.binary_null_policy
        selected_actions = set(actions) if actions is not None else None
        selected_action_ids = set(action_ids) if action_ids is not None else None
        pending_rename_controls: dict[str, Any] | None = None

        for action in self.actions:
            if selected_actions is not None and action.action not in selected_actions:
                continue
            if selected_action_ids is not None and _action_id(action) not in selected_action_ids:
                continue
            if not _action_columns_exist(action, result):
                continue
            controls = _action_controls(action, action_control_values)
            if action.action == "column_rename_review":
                if str(controls.get("treatment") or "inspect") == "apply":
                    pending_rename_controls = controls
                continue
            elif action.action == "missing_like_to_null" and standardize_missing_like:
                result[action.column] = _missing_like_to_null(
                    result[action.column],
                    tokens=_lines(controls.get("tokens")),
                )
            elif action.action == "missing_value_review":
                result = _apply_missing_treatment(result, action.column, controls)
            elif action.action == "duplicate_row_review":
                result = _apply_duplicate_treatment(result, controls)
            elif action.action == "trim_strings" and trim_strings:
                if _bool_control(controls.get("strip"), True):
                    result[action.column] = result[action.column].astype("string").str.strip()
            elif action.action == "parse_numeric" and numeric_coerce:
                result[action.column] = _parse_numeric(
                    result[action.column],
                    remove_commas=_bool_control(controls.get("remove_commas"), True),
                    remove_currency=_bool_control(controls.get("remove_currency"), True),
                    percent_mode=str(controls.get("percent_mode") or "strip_symbol"),
                    invalid_policy=str(controls.get("invalid_policy") or "coerce"),
                )
            elif action.action == "parse_datetime" and datetime_parse:
                result[action.column] = _parse_datetime(
                    result[action.column],
                    dayfirst=_bool_control(controls.get("dayfirst"), datetime_dayfirst),
                    yearfirst=_bool_control(controls.get("yearfirst"), datetime_yearfirst),
                    invalid_policy=str(controls.get("invalid_policy") or "coerce"),
                )
            elif action.action == "binary_mapping":
                binary = self.profile.binary_flags().get(action.column)
                if binary is not None and not binary.ambiguous:
                    overrides = _action_override(action, action_control_values)
                    mapping = _coerce_mapping(controls.get("mapping")) or dict(binary.suggested_mapping)
                    result = unify_binary_flags(
                        result,
                        mappings={action.column: mapping},
                        columns=[action.column],
                        null_policy=str(overrides.get("null_policy") or null_policy),
                        to=str(overrides.get("output") or binary_output),
                    )
            elif action.action == "binary_mapping_review" and apply_ambiguous_binary:
                binary = self.profile.binary_flags().get(action.column)
                if binary is not None:
                    overrides = _action_override(action, action_control_values)
                    mapping = _coerce_mapping(controls.get("mapping")) or dict(binary.suggested_mapping)
                    result = unify_binary_flags(
                        result,
                        mappings={action.column: mapping},
                        columns=[action.column],
                        null_policy=str(overrides.get("null_policy") or null_policy),
                        to=str(overrides.get("output") or binary_output),
                    )
            elif action.action == "category_value_review":
                mapping = _coerce_mapping(controls.get("mapping"))
                if mapping:
                    from stateframe.transforms import map_values

                    result = map_values(
                        result,
                        {action.column: mapping},
                        case_sensitive=not _bool_control(controls.get("casefold"), True),
                        strip=_bool_control(controls.get("strip"), True),
                    )
            elif action.action == "numeric_outlier_review":
                treatment = str(controls.get("treatment") or outlier_policy)
                if treatment in {"inspect", "skip"} and outlier_policy != "skip":
                    treatment = outlier_policy
                if treatment in {"skip", "inspect"}:
                    continue
                result = clean_numeric_outliers(
                    result,
                    {
                        action.column: {
                            "method": controls.get("method") or outlier_method,
                            "treatment": treatment,
                            "lower_quantile": controls.get("lower_quantile", 0.01),
                            "upper_quantile": controls.get("upper_quantile", 0.99),
                            "threshold": controls.get("threshold", 3.0),
                        }
                    },
                )
            elif action.action == "geo_coordinate_review":
                result = _apply_geo_treatment(result, action, str(controls.get("treatment") or "inspect"))
        if pending_rename_controls is not None:
            result = rename_columns(
                result,
                mapping=_coerce_mapping(pending_rename_controls.get("mapping")),
                case=str(pending_rename_controls.get("case") or "lower"),
                separator=str(
                    pending_rename_controls.get("separator")
                    if pending_rename_controls.get("separator") is not None
                    else "_"
                ),
                remove_punctuation=_bool_control(pending_rename_controls.get("remove_punctuation"), True),
                collapse=_bool_control(pending_rename_controls.get("collapse"), True),
                prefix_if_digit=str(pending_rename_controls.get("prefix_if_digit") or "col_"),
                errors="ignore",
            )
        return result


def build_cleaning_plan(
    profile: Profile,
    *,
    binary_null_policy: str = "preserve",
    include_string_trim: bool = True,
    include_outliers: bool = True,
    include_geo: bool = True,
    include_category_variants: bool = True,
) -> CleaningPlan:
    actions: list[TransformAction] = []

    rename_preview = _column_rename_preview(profile.data)
    if rename_preview["rename_count"]:
        actions.append(
            TransformAction(
                column="__columns__",
                action="column_rename_review",
                confidence=0.88,
                risk="low",
                before_dtype="columns",
                after_dtype="columns",
                reversible=True,
                reason="some column names contain spaces, punctuation, casing, or duplicate-normalized forms that can make code and formulas awkward",
                affected_rows=None,
                applies_by_default=False,
                control_values={
                    "treatment": "inspect",
                    "case": "lower",
                    "separator": "_",
                    "remove_punctuation": True,
                    "collapse": True,
                    "prefix_if_digit": "col_",
                    "mapping": rename_preview["mapping_text"],
                },
                preview=rename_preview,
            )
        )

    duplicate_rows = profile.summary_data.duplicate_rows
    if duplicate_rows:
        duplicate_mask = profile.data.duplicated(keep=False)
        actions.append(
            TransformAction(
                column="__rows__",
                action="duplicate_row_review",
                confidence=0.94,
                risk="medium",
                before_dtype="rows",
                after_dtype="rows",
                reversible=False,
                reason="dataset contains repeated full rows",
                affected_rows=int(duplicate_rows),
                applies_by_default=False,
                control_values={"treatment": "inspect", "keep": "first", "subset": ""},
                preview={
                    "duplicate_row_count": int(duplicate_rows),
                    "duplicate_group_row_count": int(duplicate_mask.sum()),
                    "duplicate_ratio": duplicate_rows / profile.summary_data.row_count if profile.summary_data.row_count else 0.0,
                    "subset": "all columns",
                },
                examples=_duplicate_examples(profile.data, duplicate_mask),
            )
        )

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
                    affected_rows=column.value_profile.semantic_null_count - column.missing_count,
                    control_values={
                        "tokens": "\n".join(sorted(column.value_profile.missing_like_values)),
                        "replacement": "null",
                    },
                    preview={
                        "tokens": dict(column.value_profile.missing_like_values),
                        "semantic_null_count": column.value_profile.semantic_null_count,
                        "raw_null_count": column.missing_count,
                        "semantic_null_delta": column.value_profile.semantic_null_count - column.missing_count,
                    },
                    examples=_row_examples(profile.data, column.name, _missing_like_mask(profile.data[column.name])),
                )
            )

        if column.missing_count > 0:
            actions.append(
                TransformAction(
                    column=column.name,
                    action="missing_value_review",
                    confidence=0.8,
                    risk="medium",
                    before_dtype=column.dtype,
                    after_dtype=column.dtype,
                    reversible=False,
                    reason="column contains true null values that may need an explicit treatment",
                    affected_rows=column.missing_count,
                    applies_by_default=False,
                    control_values={
                        "treatment": "inspect",
                        "fill_value": "",
                        "add_indicator": False,
                        "indicator_suffix": "_was_missing",
                    },
                    preview={
                        "missing_count": column.missing_count,
                        "missing_ratio": column.missing_ratio,
                        "non_null_count": column.non_null_count,
                        "semantic_type": column.semantic_type,
                        "suggested_treatments": _missing_treatment_suggestions(column.semantic_type),
                    },
                    examples=_row_examples(profile.data, column.name, profile.data[column.name].isna()),
                )
            )

        if column.semantic_type == "numeric-like":
            invalid_mask = _invalid_numeric_mask(profile.data[column.name])
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
                    affected_rows=int(profile.data[column.name].notna().sum()),
                    control_values={
                        "remove_commas": True,
                        "remove_currency": True,
                        "percent_mode": "strip_symbol",
                        "invalid_policy": "coerce",
                    },
                    preview={
                        "parse_ratio": column.metrics.get("numeric_parse_ratio"),
                        "invalid_after_parse": int(invalid_mask.sum()),
                        "examples_that_fail": _values_for_mask(profile.data[column.name], invalid_mask),
                    },
                    examples=_row_examples(profile.data, column.name, invalid_mask),
                )
            )

        if column.semantic_type == "datetime-like":
            invalid_mask = _invalid_datetime_mask(profile.data[column.name])
            format_clusters = _datetime_format_clusters(profile.data[column.name])
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
                    affected_rows=int(profile.data[column.name].notna().sum()),
                    control_values={
                        "dayfirst": False,
                        "yearfirst": False,
                        "invalid_policy": "coerce",
                    },
                    preview={
                        "parse_ratio": column.metrics.get("datetime_parse_ratio"),
                        "invalid_after_parse": int(invalid_mask.sum()),
                        "format_clusters": format_clusters,
                        "mixed_formats": len(format_clusters) > 1,
                        "examples_that_fail": _values_for_mask(profile.data[column.name], invalid_mask),
                    },
                    examples=_row_examples(profile.data, column.name, invalid_mask),
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
                    affected_rows=int(profile.data[column.name].notna().sum()),
                    control_values={
                        "output": "int",
                        "null_policy": binary_null_policy,
                        "mapping": dict(column.binary_profile.suggested_mapping),
                    },
                    preview={
                        "mapping": dict(column.binary_profile.suggested_mapping),
                        "null_policy": binary_null_policy,
                        "normalized_values": list(column.binary_profile.normalized_values),
                    },
                )
            )
        elif column.binary_profile is not None and column.binary_profile.ambiguous:
            actions.append(
                TransformAction(
                    column=column.name,
                    action="binary_mapping_review",
                    confidence=column.binary_profile.confidence,
                    risk="medium",
                    before_dtype=column.dtype,
                    after_dtype="Int64",
                    reversible=False,
                    reason="binary-like values need confirmation before conversion",
                    affected_rows=int(profile.data[column.name].notna().sum()),
                    applies_by_default=False,
                    control_values={
                        "output": "int",
                        "null_policy": column.binary_profile.null_policy,
                        "mapping": dict(column.binary_profile.suggested_mapping),
                    },
                    preview={
                        "mapping": dict(column.binary_profile.suggested_mapping),
                        "null_policy": column.binary_profile.null_policy,
                        "kind": column.binary_profile.kind,
                        "evidence": list(column.binary_profile.evidence),
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
                        affected_rows=whitespace_count,
                        control_values={"strip": True},
                        preview={"affected_rows": whitespace_count},
                        examples=_row_examples(
                            profile.data,
                            column.name,
                            _whitespace_mask(profile.data[column.name]),
                        ),
                    )
                )

        if include_category_variants and column.semantic_type in {"category", "string"}:
            variants = _category_variants(profile.data[column.name])
            if variants:
                actions.append(
                    TransformAction(
                        column=column.name,
                        action="category_value_review",
                        confidence=0.72,
                        risk="low",
                        before_dtype=column.dtype,
                        after_dtype=column.dtype,
                        reversible=False,
                        reason="some category labels only differ by case or whitespace",
                        affected_rows=sum(item["row_count"] for item in variants),
                        applies_by_default=False,
                        control_values={"casefold": True, "strip": True, "mapping": {}},
                        preview={"variant_groups": variants},
                    )
                )

        if include_outliers and column.semantic_type in {
            "numeric",
            "amount",
            "numeric-like",
            "percentage",
            "proportion",
            "numeric_discrete",
        }:
            outlier_preview = _outlier_preview(profile.data[column.name], column.metrics)
            if outlier_preview["outlier_count"] > 0:
                outlier_mask = outlier_preview.pop("mask")
                actions.append(
                    TransformAction(
                        column=column.name,
                        action="numeric_outlier_review",
                        confidence=outlier_preview["confidence"],
                        risk="medium",
                        before_dtype=column.dtype,
                        after_dtype=column.dtype,
                        reversible=False,
                        reason="numeric values include rows outside robust distribution bounds",
                        affected_rows=outlier_preview["outlier_count"],
                        applies_by_default=False,
                        control_values={
                            "method": "iqr",
                            "treatment": "inspect",
                            "lower_quantile": 0.01,
                            "upper_quantile": 0.99,
                            "threshold": 3.0,
                        },
                        preview=outlier_preview,
                        examples=_row_examples(profile.data, column.name, outlier_mask),
                    )
                )

    if include_geo:
        actions.extend(_geo_actions(profile))

    return CleaningPlan(
        profile=profile,
        actions=_dedupe_actions(actions),
        binary_null_policy=binary_null_policy,
        settings={
            "include_string_trim": include_string_trim,
            "include_outliers": include_outliers,
            "include_geo": include_geo,
            "include_category_variants": include_category_variants,
        },
    )


def _cleaning_presets(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return UI-ready cleaning modes built from the suggested action set."""

    if not actions:
        return []

    ids = {str(action.get("id")) for action in actions if action.get("id")}
    defaults = [
        str(action["id"])
        for action in actions
        if action.get("id") and action.get("applies_by_default") is not False
    ]
    type_actions = {
        "missing_like_to_null",
        "trim_strings",
        "parse_numeric",
        "parse_datetime",
        "binary_mapping",
    }
    type_ready = [
        str(action["id"])
        for action in actions
        if action.get("id") and action.get("action") in type_actions
    ]
    rename_ids = [
        str(action["id"])
        for action in actions
        if action.get("id") and action.get("action") == "column_rename_review"
    ]
    outlier_ids = [
        str(action["id"])
        for action in actions
        if action.get("id") and action.get("action") == "numeric_outlier_review"
    ]
    review_ids = [str(action["id"]) for action in actions if action.get("id")]

    rename_controls = {
        action_id: {"treatment": "apply"}
        for action_id in rename_ids
        if action_id in ids
    }
    outlier_flag_controls = {
        action_id: {"treatment": "flag"}
        for action_id in outlier_ids
        if action_id in ids
    }

    presets = [
        {
            "id": "safe_defaults",
            "label": "Safe",
            "description": "Apply high-confidence conversions while leaving review-only decisions untouched.",
            "selectedActionIds": defaults,
            "actionControlValues": {},
            "options": {
                "binaryNullPolicy": "preserve",
                "binaryOutput": "int",
                "applyAmbiguousBinary": False,
                "outlierPolicy": "skip",
                "outlierMethod": "iqr",
            },
        },
        {
            "id": "type_prep",
            "label": "Type Prep",
            "description": "Normalize missing-like tokens, parse dates and numbers, trim strings, and map confident binary flags.",
            "selectedActionIds": _ordered_unique(type_ready),
            "actionControlValues": {},
            "options": {
                "binaryNullPolicy": "preserve",
                "binaryOutput": "int",
                "applyAmbiguousBinary": False,
                "outlierPolicy": "skip",
                "outlierMethod": "iqr",
            },
        },
        {
            "id": "analysis_ready",
            "label": "Analysis Ready",
            "description": "Type-prep the data and apply cleaned column names so downstream code is easier to write.",
            "selectedActionIds": _ordered_unique([*rename_ids, *type_ready]),
            "actionControlValues": rename_controls,
            "options": {
                "binaryNullPolicy": "preserve",
                "binaryOutput": "int",
                "applyAmbiguousBinary": False,
                "outlierPolicy": "skip",
                "outlierMethod": "iqr",
            },
        },
        {
            "id": "power_review",
            "label": "Power Review",
            "description": "Analysis-ready cleaning plus non-destructive outlier flags for QA and modeling review.",
            "selectedActionIds": _ordered_unique([*rename_ids, *type_ready, *outlier_ids]),
            "actionControlValues": {**rename_controls, **outlier_flag_controls},
            "options": {
                "binaryNullPolicy": "preserve",
                "binaryOutput": "int",
                "applyAmbiguousBinary": False,
                "outlierPolicy": "flag",
                "outlierMethod": "iqr",
            },
        },
        {
            "id": "audit_all",
            "label": "Audit All",
            "description": "Select every detected issue for inspection before choosing treatments.",
            "selectedActionIds": review_ids,
            "actionControlValues": {},
            "options": {
                "binaryNullPolicy": "preserve",
                "binaryOutput": "int",
                "applyAmbiguousBinary": False,
                "outlierPolicy": "skip",
                "outlierMethod": "iqr",
            },
        },
    ]
    return [
        {
            **preset,
            "selectedActionIds": [action_id for action_id in preset["selectedActionIds"] if action_id in ids],
            "actionControlValues": {
                action_id: values
                for action_id, values in preset["actionControlValues"].items()
                if action_id in ids
            },
            "selectedActionCount": sum(1 for action_id in preset["selectedActionIds"] if action_id in ids),
        }
        for preset in presets
        if any(action_id in ids for action_id in preset["selectedActionIds"])
    ]


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _parse_numeric(
    series: pd.Series,
    *,
    remove_commas: bool = True,
    remove_currency: bool = True,
    percent_mode: str = "strip_symbol",
    invalid_policy: str = "coerce",
) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    if remove_commas:
        cleaned = cleaned.str.replace(",", "", regex=False)
    if remove_currency:
        for symbol in ["$", "£", "€", "¥"]:
            cleaned = cleaned.str.replace(symbol, "", regex=False)
    had_percent = cleaned.str.contains("%", regex=False, na=False)
    cleaned = cleaned.str.replace("%", "", regex=False)
    parsed = pd.to_numeric(cleaned, errors="coerce")
    if percent_mode == "divide_by_100":
        parsed = parsed.where(~had_percent, parsed / 100)
    if invalid_policy == "preserve":
        valid = parsed.notna() | series.isna()
        return parsed.astype("object").where(valid, series)
    return parsed


def _parse_datetime(
    series: pd.Series,
    *,
    dayfirst: bool = False,
    yearfirst: bool = False,
    invalid_policy: str = "coerce",
) -> pd.Series:
    parsed = pd.to_datetime(
        series,
        errors="coerce",
        dayfirst=dayfirst,
        yearfirst=yearfirst,
        format="mixed",
    )
    if invalid_policy == "preserve":
        valid = parsed.notna() | series.isna()
        return parsed.astype("object").where(valid, series)
    return parsed


def _missing_like_to_null(series: pd.Series, *, tokens: list[str] | None = None) -> pd.Series:
    missing_tokens = {str(token).strip().lower() for token in (tokens or MISSING_LIKE_VALUES)}
    text = series.astype("string").str.strip().str.lower()
    return series.mask(text.isin(missing_tokens))


def _missing_like_mask(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.lower()
    return series.notna() & text.isin(MISSING_LIKE_VALUES)


def _invalid_numeric_count(series: pd.Series) -> int:
    text = series.dropna().astype("string").str.strip().str.lower()
    semantic_values = series.dropna()[~text.isin(MISSING_LIKE_VALUES)]
    if semantic_values.empty:
        return 0
    return int(_parse_numeric(semantic_values).isna().sum())


def _invalid_numeric_mask(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.lower()
    semantic_values = series.notna() & ~text.isin(MISSING_LIKE_VALUES)
    parsed = _parse_numeric(series)
    return semantic_values & parsed.isna()


def _invalid_datetime_mask(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.lower()
    semantic_values = series.notna() & ~text.isin(MISSING_LIKE_VALUES)
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    return semantic_values & parsed.isna()


def _whitespace_count(series: pd.Series) -> int:
    non_null = series.dropna().astype("string")
    return int((non_null != non_null.str.strip()).sum())


def _whitespace_mask(series: pd.Series) -> pd.Series:
    non_null = series.astype("string")
    return series.notna() & (non_null != non_null.str.strip())


def _values_for_mask(series: pd.Series, mask: pd.Series, limit: int = 8) -> list[Any]:
    values = []
    for value in series[mask].head(limit).tolist():
        values.append(_jsonish(value))
    return values


def _row_examples(
    data: pd.DataFrame,
    column: str,
    mask: pd.Series | np.ndarray | list[bool],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    bool_mask = pd.Series(mask, index=data.index).fillna(False).astype(bool)
    rows = []
    for index, value in data.loc[bool_mask, column].head(limit).items():
        rows.append({"index": _jsonish(index), "value": _jsonish(value)})
    return rows


def _datetime_format_clusters(series: pd.Series, limit: int = 8) -> list[dict[str, Any]]:
    values = series.dropna().astype("string").str.strip()
    values = values[~values.str.lower().isin(MISSING_LIKE_VALUES)]
    if values.empty:
        return []
    patterns = values.map(_datetime_pattern)
    counts = patterns.value_counts().head(limit)
    result = []
    for pattern, count in counts.items():
        sample = values[patterns == pattern].head(3).tolist()
        result.append(
            {
                "pattern": str(pattern),
                "count": int(count),
                "examples": [_jsonish(value) for value in sample],
            }
        )
    return result


def _datetime_pattern(value: Any) -> str:
    text = str(value).strip()
    result = []
    previous = ""
    for char in text:
        if char.isdigit():
            token = "9"
        elif char.isalpha():
            token = "A"
        elif char.isspace():
            token = " "
        else:
            token = char
        if token == previous and token in {"9", "A"}:
            continue
        result.append(token)
        previous = token
    return "".join(result)


def _category_variants(series: pd.Series, limit: int = 10) -> list[dict[str, Any]]:
    values = series.dropna().astype("string")
    if values.empty:
        return []
    normalized = values.str.strip().str.casefold()
    result = []
    for key, group in values.groupby(normalized, dropna=True):
        originals = group.value_counts()
        if originals.shape[0] <= 1:
            continue
        result.append(
            {
                "normalized": str(key),
                "row_count": int(originals.sum()),
                "variants": [
                    {"value": _jsonish(value), "count": int(count)}
                    for value, count in originals.items()
                ],
            }
        )
    return sorted(result, key=lambda item: item["row_count"], reverse=True)[:limit]


def _column_rename_preview(data: pd.DataFrame, limit: int = 40) -> dict[str, Any]:
    raw_names = [str(column) for column in data.columns]
    suggested = [
        clean_column_name(
            column,
            case="lower",
            separator="_",
            remove_punctuation=True,
            collapse=True,
            prefix_if_digit="col_",
        )
        for column in raw_names
    ]
    suggested = _unique_name_preview(suggested)
    changes = [
        {"from": old, "to": new}
        for old, new in zip(raw_names, suggested)
        if old != new
    ]
    normalized_counts = pd.Series(suggested).value_counts()
    return {
        "column_count": len(raw_names),
        "rename_count": len(changes),
        "changes": changes[:limit],
        "truncated": len(changes) > limit,
        "duplicate_normalized_count": int((normalized_counts > 1).sum()),
        "mapping": {item["from"]: item["to"] for item in changes},
        "mapping_text": "\n".join(f"{item['from']} => {item['to']}" for item in changes),
        "styles": [
            {"label": "lower underscore", "case": "lower", "separator": "_"},
            {"label": "compact lowercase", "case": "lower", "separator": ""},
            {"label": "preserve case underscore", "case": "preserve", "separator": "_"},
            {"label": "upper underscore", "case": "upper", "separator": "_"},
        ],
    }


def _unique_name_preview(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        base = name or "column"
        count = seen.get(base, 0)
        result.append(base if count == 0 else f"{base}_{count + 1}")
        seen[base] = count + 1
    return result


def _outlier_preview(series: pd.Series, metrics: dict[str, Any]) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce")
    finite = values[np.isfinite(values)].dropna()
    if finite.empty:
        return {
            "method": "iqr",
            "outlier_count": 0,
            "outlier_ratio": 0.0,
            "lower_bound": None,
            "upper_bound": None,
            "confidence": 0.0,
            "mask": pd.Series(False, index=series.index),
        }
    q1 = finite.quantile(0.25)
    q3 = finite.quantile(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        mask = pd.Series(False, index=series.index)
        lower = upper = None
    else:
        lower = float(q1 - 1.5 * iqr)
        upper = float(q3 + 1.5 * iqr)
        mask = (values < lower) | (values > upper)
    count = int(mask.fillna(False).sum())
    ratio = count / int(finite.shape[0]) if finite.shape[0] else 0.0
    return {
        "method": "iqr",
        "outlier_count": count,
        "outlier_ratio": ratio,
        "lower_bound": lower,
        "upper_bound": upper,
        "iqr": _jsonish(metrics.get("iqr")),
        "p01": _jsonish(metrics.get("p01")),
        "p99": _jsonish(metrics.get("p99")),
        "confidence": 0.78 if ratio >= 0.05 else 0.66,
        "mask": mask.fillna(False),
    }


def _geo_actions(profile: Profile) -> list[TransformAction]:
    data = profile.data
    actions: list[TransformAction] = []
    lat_columns = [name for name in data.columns if _is_lat_name(str(name))]
    lon_columns = [name for name in data.columns if _is_lon_name(str(name))]
    paired = set()
    for lat in lat_columns:
        lon = _best_lon_pair(str(lat), [str(column) for column in lon_columns])
        if lon is None or lon not in data.columns:
            continue
        paired.add(lat)
        paired.add(lon)
        lat_values = pd.to_numeric(data[lat], errors="coerce")
        lon_values = pd.to_numeric(data[lon], errors="coerce")
        invalid = lat_values.abs().gt(90) | lon_values.abs().gt(180)
        swapped = lat_values.abs().le(180) & lat_values.abs().gt(90) & lon_values.abs().le(90)
        affected = invalid | swapped
        if affected.fillna(False).any():
            actions.append(
                TransformAction(
                    column=f"{lat},{lon}",
                    action="geo_coordinate_review",
                    confidence=0.72,
                    risk="medium",
                    before_dtype=f"{data[lat].dtype},{data[lon].dtype}",
                    after_dtype=None,
                    reversible=False,
                    reason="latitude/longitude pair has invalid ranges or likely swapped values",
                    affected_rows=int(affected.fillna(False).sum()),
                    applies_by_default=False,
                    control_values={"treatment": "inspect"},
                    preview={
                        "latitude": str(lat),
                        "longitude": str(lon),
                        "invalid_count": int(invalid.fillna(False).sum()),
                        "likely_swapped_count": int(swapped.fillna(False).sum()),
                        "lat_range": [float(lat_values.min(skipna=True)), float(lat_values.max(skipna=True))],
                        "lon_range": [float(lon_values.min(skipna=True)), float(lon_values.max(skipna=True))],
                    },
                    examples=_geo_examples(data, str(lat), str(lon), affected),
                )
            )
    for column in data.columns:
        name = str(column)
        if name in paired:
            continue
        if not (_is_lat_name(name) or _is_lon_name(name)):
            continue
        values = pd.to_numeric(data[column], errors="coerce")
        bound = 90 if _is_lat_name(name) else 180
        invalid = values.abs().gt(bound)
        if invalid.fillna(False).any():
            actions.append(
                TransformAction(
                    column=name,
                    action="geo_coordinate_review",
                    confidence=0.68,
                    risk="medium",
                    before_dtype=str(data[column].dtype),
                    after_dtype=str(data[column].dtype),
                    reversible=False,
                    reason="coordinate-like column has values outside valid range",
                    affected_rows=int(invalid.fillna(False).sum()),
                    applies_by_default=False,
                    control_values={"treatment": "inspect"},
                    preview={
                        "coordinate": name,
                        "valid_abs_bound": bound,
                        "invalid_count": int(invalid.fillna(False).sum()),
                        "range": [float(values.min(skipna=True)), float(values.max(skipna=True))],
                    },
                    examples=_row_examples(data, name, invalid),
                )
            )
    return actions


def _geo_examples(data: pd.DataFrame, lat: str, lon: str, mask: pd.Series, limit: int = 8) -> list[dict[str, Any]]:
    rows = []
    bool_mask = mask.fillna(False).astype(bool)
    for index, row in data.loc[bool_mask, [lat, lon]].head(limit).iterrows():
        rows.append({"index": _jsonish(index), lat: _jsonish(row[lat]), lon: _jsonish(row[lon])})
    return rows


def _is_lat_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"lat", "latitude"} or lowered.endswith("_lat") or "latitude" in lowered


def _is_lon_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"lon", "lng", "long", "longitude"} or lowered.endswith(("_lon", "_lng", "_long")) or "longitude" in lowered


def _best_lon_pair(lat: str, lon_columns: list[str]) -> str | None:
    if not lon_columns:
        return None
    lowered = lat.lower()
    candidates = [
        lowered.replace("latitude", "longitude"),
        lowered.replace("_lat", "_lon"),
        lowered.replace("lat", "lon"),
    ]
    for candidate in candidates:
        for lon in lon_columns:
            if lon.lower() == candidate:
                return lon
    return lon_columns[0]


def _apply_missing_treatment(data: pd.DataFrame, column: str, controls: dict[str, Any]) -> pd.DataFrame:
    treatment = str(controls.get("treatment") or "inspect")
    if treatment in {"inspect", "skip", ""} or column not in data.columns:
        return data
    result = data.copy()
    suffix = str(controls.get("indicator_suffix") or "_was_missing")
    if treatment == "add_indicator" or _bool_control(controls.get("add_indicator"), False):
        result[f"{column}{suffix}"] = result[column].isna().astype("int8")
    if treatment == "add_indicator":
        return result
    if treatment == "drop_rows":
        return result.loc[~result[column].isna()].copy()
    if treatment == "fill_constant":
        result[column] = result[column].fillna(controls.get("fill_value"))
    elif treatment == "fill_missing_label":
        result[column] = result[column].fillna("Missing")
    elif treatment == "fill_mean":
        numeric = pd.to_numeric(result[column], errors="coerce")
        result[column] = result[column].fillna(numeric.mean())
    elif treatment == "fill_median":
        numeric = pd.to_numeric(result[column], errors="coerce")
        result[column] = result[column].fillna(numeric.median())
    elif treatment == "fill_mode":
        modes = result[column].mode(dropna=True)
        if not modes.empty:
            result[column] = result[column].fillna(modes.iloc[0])
    elif treatment == "forward_fill":
        result[column] = result[column].ffill()
    elif treatment == "back_fill":
        result[column] = result[column].bfill()
    return result


def _apply_duplicate_treatment(data: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    if str(controls.get("treatment") or "inspect") != "drop":
        return data
    subset = _subset_columns(controls.get("subset"), data)
    keep_raw = str(controls.get("keep") or "first")
    keep: str | bool = False if keep_raw == "false" else keep_raw
    return data.drop_duplicates(subset=subset or None, keep=keep).copy()


def _subset_columns(value: Any, data: pd.DataFrame) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw = value.replace(",", "\n").splitlines()
    else:
        raw = list(value)
    columns = []
    for item in raw:
        column = str(item).strip()
        if column and column in data.columns:
            columns.append(column)
    return list(dict.fromkeys(columns))


def _missing_treatment_suggestions(semantic_type: str) -> list[str]:
    if semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"}:
        return ["inspect", "add_indicator", "fill_median", "fill_mean", "drop_rows"]
    if semantic_type in {"datetime", "datetime-like"}:
        return ["inspect", "add_indicator", "forward_fill", "back_fill", "drop_rows"]
    return ["inspect", "add_indicator", "fill_mode", "fill_missing_label", "drop_rows"]


def _duplicate_examples(data: pd.DataFrame, mask: pd.Series, limit: int = 8) -> list[dict[str, Any]]:
    rows = []
    bool_mask = mask.fillna(False).astype(bool)
    columns = [str(column) for column in data.columns[: min(5, data.shape[1])]]
    for index, row in data.loc[bool_mask, columns].head(limit).iterrows():
        item = {"index": _jsonish(index)}
        item.update({str(column): _jsonish(row[column]) for column in columns})
        rows.append(item)
    return rows


def _action_columns_exist(action: TransformAction, data: pd.DataFrame) -> bool:
    if action.action in {"duplicate_row_review", "column_rename_review"}:
        return True
    if action.action == "geo_coordinate_review" and "," in action.column:
        return all(column in data.columns for column in action.column.split(",", 1))
    return action.column in data.columns


def _action_controls(
    action: TransformAction,
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    values = dict(action.control_values)
    if overrides:
        values.update(dict(overrides.get(_action_id(action)) or {}))
    return values


def _action_override(
    action: TransformAction,
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    if not overrides:
        return {}
    return dict(overrides.get(_action_id(action)) or {})


def _lines(value: Any) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _bool_control(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _coerce_mapping(value: Any) -> dict[Any, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            import json

            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        mapping: dict[Any, Any] = {}
        for line in text.splitlines():
            if "=>" in line:
                left, right = line.split("=>", 1)
            elif ":" in line:
                left, right = line.split(":", 1)
            else:
                continue
            key = left.strip()
            raw_value = right.strip()
            mapping[key] = None if raw_value.lower() in {"null", "none", "na", "n/a"} else raw_value
        return mapping
    return {}


def _apply_geo_treatment(data: pd.DataFrame, action: TransformAction, treatment: str) -> pd.DataFrame:
    if treatment in {"inspect", "skip", ""}:
        return data
    result = data.copy()
    if "," in action.column:
        lat, lon = action.column.split(",", 1)
        if lat not in result.columns or lon not in result.columns:
            return data
        lat_values = pd.to_numeric(result[lat], errors="coerce")
        lon_values = pd.to_numeric(result[lon], errors="coerce")
        invalid = lat_values.abs().gt(90) | lon_values.abs().gt(180)
        swapped = lat_values.abs().le(180) & lat_values.abs().gt(90) & lon_values.abs().le(90)
        if treatment == "swap_likely":
            swap_mask = swapped.fillna(False)
            result.loc[swap_mask, [lat, lon]] = result.loc[swap_mask, [lon, lat]].to_numpy()
        elif treatment == "null_invalid":
            result.loc[invalid.fillna(False), [lat, lon]] = pd.NA
        return result
    if action.column not in result.columns:
        return data
    values = pd.to_numeric(result[action.column], errors="coerce")
    bound = 90 if _is_lat_name(action.column) else 180
    invalid = values.abs().gt(bound).fillna(False)
    if treatment == "null_invalid":
        result.loc[invalid, action.column] = pd.NA
    return result


def _jsonish(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _action_id(action: TransformAction) -> str:
    return f"{action.action}:{action.column}"


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
