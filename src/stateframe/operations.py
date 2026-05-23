"""Shared operation metadata for cleaning, transforms, visuals, and modeling prep.

The public library should expose simple buttons and controls, but the internal
shape needs to stay explicit enough to replay. These small dataclasses describe
what an operation can do, which controls the UI should render, and how risky the
default behavior is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ControlKind = Literal[
    "checkbox",
    "number",
    "select",
    "text",
    "textarea",
    "mapping",
    "column_select",
    "multi_column_select",
]


@dataclass(frozen=True)
class OperationControl:
    """One user-editable control for an operation."""

    id: str
    label: str
    kind: ControlKind
    default: Any = None
    choices: list[dict[str, Any]] = field(default_factory=list)
    help: str = ""
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "help": self.help,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.choices:
            result["choices"] = [dict(choice) for choice in self.choices]
        return result


@dataclass(frozen=True)
class OperationSpec:
    """UI- and replay-readable description of a supported operation."""

    id: str
    family: str
    title: str
    description: str = ""
    controls: list[OperationControl] = field(default_factory=list)
    default_risk: str = "low"
    reversible: bool = False
    produces: list[str] = field(default_factory=list)
    applies_to: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "title": self.title,
            "description": self.description,
            "controls": [control.to_dict() for control in self.controls],
            "default_risk": self.default_risk,
            "reversible": self.reversible,
            "produces": list(self.produces),
            "applies_to": list(self.applies_to),
            "evidence_required": list(self.evidence_required),
        }


_SPECS: dict[str, OperationSpec] = {}


def register_operation(spec: OperationSpec) -> OperationSpec:
    """Register an operation spec and return it for inline use."""

    _SPECS[spec.id] = spec
    return spec


def get_operation_spec(operation_id: str) -> OperationSpec | None:
    """Return an operation spec by id, if it is known."""

    return _SPECS.get(operation_id)


def all_operation_specs(*, family: str | None = None) -> list[OperationSpec]:
    """Return registered operation specs, optionally limited to one family."""

    specs = list(_SPECS.values())
    if family is not None:
        specs = [spec for spec in specs if spec.family == family]
    return sorted(specs, key=lambda spec: (spec.family, spec.id))


def _choice(value: Any, label: str) -> dict[str, Any]:
    return {"value": value, "label": label}


def _control(
    id: str,
    label: str,
    kind: ControlKind,
    *,
    default: Any = None,
    choices: list[tuple[Any, str]] | None = None,
    help: str = "",
    required: bool = False,
) -> OperationControl:
    return OperationControl(
        id=id,
        label=label,
        kind=kind,
        default=default,
        choices=[_choice(value, label) for value, label in choices or []],
        help=help,
        required=required,
    )


register_operation(
    OperationSpec(
        id="column_rename_review",
        family="cleaning",
        title="Rename columns",
        description="Clean many column names at once or manually rename selected columns.",
        controls=[
            _control("treatment", "Treatment", "select", default="inspect", choices=[
                ("inspect", "Inspect only"),
                ("apply", "Apply renames"),
            ]),
            _control("case", "Case", "select", default="lower", choices=[
                ("preserve", "Preserve"),
                ("lower", "Lowercase"),
                ("upper", "Uppercase"),
                ("title", "Title Case"),
            ]),
            _control("separator", "Space separator", "select", default="_", choices=[
                ("_", "Underscore"),
                ("", "No separator"),
                ("-", "Hyphen"),
                (".", "Dot"),
                (" ", "Space"),
            ]),
            _control("remove_punctuation", "Remove punctuation", "checkbox", default=True),
            _control("collapse", "Collapse repeated separators", "checkbox", default=True),
            _control("prefix_if_digit", "Prefix if starts with number", "text", default="col_"),
            _control("mapping", "Manual rename mapping", "mapping", help="Optional old => new pairs. These are applied before the naming rules."),
        ],
        default_risk="low",
        reversible=True,
        produces=["renamed_columns", "rename_mapping"],
        applies_to=["columns"],
    )
)

register_operation(
    OperationSpec(
        id="missing_like_to_null",
        family="cleaning",
        title="Treat missing-like values as null",
        description="Replace tokens such as NA, N/A, missing, blanks, and ? with real nulls.",
        controls=[
            _control("tokens", "Tokens", "textarea", help="One missing-like token per line."),
            _control("replacement", "Replacement", "select", default="null", choices=[("null", "Null")]),
        ],
        reversible=False,
        produces=["cleaned_column", "null_delta"],
        applies_to=["string", "category", "numeric-like", "datetime-like", "binary"],
        evidence_required=["missing_like_values"],
    )
)

register_operation(
    OperationSpec(
        id="missing_value_review",
        family="cleaning",
        title="Review missing values",
        description="Choose a treatment for true nulls in a column, including indicators, fills, directional fills, or dropping rows.",
        controls=[
            _control("treatment", "Treatment", "select", default="inspect", choices=[
                ("inspect", "Inspect only"),
                ("add_indicator", "Add missingness indicator"),
                ("fill_constant", "Fill with value"),
                ("fill_mean", "Fill numeric mean"),
                ("fill_median", "Fill numeric median"),
                ("fill_mode", "Fill most common value"),
                ("fill_missing_label", "Fill 'Missing' label"),
                ("forward_fill", "Forward fill"),
                ("back_fill", "Back fill"),
                ("drop_rows", "Drop rows"),
            ]),
            _control("fill_value", "Fill value", "text"),
            _control("add_indicator", "Add indicator too", "checkbox", default=False),
            _control("indicator_suffix", "Indicator suffix", "text", default="_was_missing"),
        ],
        default_risk="medium",
        reversible=False,
        produces=["cleaned_column", "indicator_column", "row_filter"],
        applies_to=["numeric", "amount", "category", "string", "datetime", "binary"],
        evidence_required=["missing_ratio"],
    )
)

register_operation(
    OperationSpec(
        id="duplicate_row_review",
        family="cleaning",
        title="Review duplicate rows",
        description="Detect duplicate rows and optionally drop repeated records.",
        controls=[
            _control("treatment", "Treatment", "select", default="inspect", choices=[
                ("inspect", "Inspect only"),
                ("drop", "Drop duplicates"),
            ]),
            _control("keep", "Keep", "select", default="first", choices=[
                ("first", "Keep first"),
                ("last", "Keep last"),
                ("false", "Drop all duplicated rows"),
            ]),
            _control("subset", "Subset columns", "multi_column_select", help="Optional newline- or comma-separated columns. Leave blank to compare full rows."),
        ],
        default_risk="medium",
        reversible=False,
        produces=["row_filter"],
        applies_to=["rows"],
        evidence_required=["duplicate_rows"],
    )
)

register_operation(
    OperationSpec(
        id="trim_strings",
        family="cleaning",
        title="Trim string whitespace",
        description="Remove leading and trailing whitespace from string values.",
        controls=[_control("strip", "Trim leading/trailing whitespace", "checkbox", default=True)],
        reversible=False,
        produces=["cleaned_column"],
        applies_to=["string", "category", "text"],
    )
)

register_operation(
    OperationSpec(
        id="parse_numeric",
        family="cleaning",
        title="Parse numeric-like values",
        description="Convert string-stored numbers, currency, commas, and percentages to numeric values.",
        controls=[
            _control("remove_commas", "Remove commas", "checkbox", default=True),
            _control("remove_currency", "Remove currency symbols", "checkbox", default=True),
            _control("percent_mode", "Percent handling", "select", default="strip_symbol", choices=[
                ("strip_symbol", "Strip percent sign"),
                ("divide_by_100", "Convert percent to proportion"),
            ]),
            _control("invalid_policy", "Invalid values", "select", default="coerce", choices=[
                ("coerce", "Set invalid values to null"),
                ("preserve", "Preserve original values"),
            ]),
        ],
        default_risk="medium",
        reversible=False,
        produces=["numeric_column", "parse_failures"],
        applies_to=["numeric-like", "amount", "percentage"],
        evidence_required=["numeric_parse_ratio"],
    )
)

register_operation(
    OperationSpec(
        id="parse_datetime",
        family="cleaning",
        title="Parse date/datetime values",
        description="Convert mixed date-like strings to pandas datetime values.",
        controls=[
            _control("dayfirst", "Day first", "checkbox", default=False),
            _control("yearfirst", "Year first", "checkbox", default=False),
            _control("timezone", "Timezone", "text", help="Optional timezone to localize or convert later."),
            _control("invalid_policy", "Invalid values", "select", default="coerce", choices=[
                ("coerce", "Set invalid values to null"),
                ("preserve", "Preserve original values"),
            ]),
        ],
        default_risk="medium",
        reversible=False,
        produces=["datetime_column", "parse_failures", "format_clusters"],
        applies_to=["datetime-like", "datetime"],
        evidence_required=["datetime_parse_ratio"],
    )
)

register_operation(
    OperationSpec(
        id="binary_mapping",
        family="cleaning",
        title="Unify binary flag",
        description="Map binary-like values to a consistent output convention.",
        controls=[
            _control("output", "Output", "select", default="int", choices=[
                ("int", "1 / 0"),
                ("bool_nullable", "True / False / null"),
                ("bool", "True / False"),
                ("yes_no", "Yes / No"),
                ("yn", "Y / N"),
            ]),
            _control("null_policy", "Null policy", "select", default="preserve", choices=[
                ("preserve", "Preserve nulls"),
                ("treat_as_false", "Treat nulls as false"),
                ("treat_as_true", "Treat nulls as true"),
                ("false_to_null", "Turn false/0 into null"),
                ("true_to_null", "Turn true/1 into null"),
            ]),
            _control("mapping", "Value mapping", "mapping", required=True),
        ],
        reversible=False,
        produces=["binary_column", "mapping_table"],
        applies_to=["binary", "nullable_binary", "boolean", "category"],
        evidence_required=["binary_profile"],
    )
)

register_operation(
    OperationSpec(
        id="binary_mapping_review",
        family="cleaning",
        title="Review ambiguous binary flag",
        description="Surface binary-like columns where null or single-state values need human confirmation.",
        controls=[
            _control("output", "Output", "select", default="int", choices=[
                ("int", "1 / 0"),
                ("bool_nullable", "True / False / null"),
                ("yes_no", "Yes / No"),
            ]),
            _control("null_policy", "Null policy", "select", default="preserve", choices=[
                ("preserve", "Preserve nulls"),
                ("treat_as_false", "Treat nulls as false"),
                ("treat_as_true", "Treat nulls as true"),
            ]),
            _control("mapping", "Value mapping", "mapping", required=True),
        ],
        default_risk="medium",
        reversible=False,
        produces=["mapping_table", "review_required"],
        applies_to=["nullable_binary", "category"],
        evidence_required=["binary_profile"],
    )
)

register_operation(
    OperationSpec(
        id="numeric_outlier_review",
        family="cleaning",
        title="Review numeric outliers",
        description="Detect rows beyond selected outlier bounds and choose whether to flag, null, clip, or drop them.",
        controls=[
            _control("method", "Method", "select", default="iqr", choices=[
                ("iqr", "IQR fences"),
                ("zscore", "Z-score"),
                ("modified_zscore", "Modified z-score"),
                ("percentile", "Percentile bounds"),
            ]),
            _control("treatment", "Treatment", "select", default="inspect", choices=[
                ("inspect", "Inspect only"),
                ("flag", "Add indicator column"),
                ("null", "Set outliers to null"),
                ("clip", "Clip to bounds"),
                ("drop", "Drop rows"),
            ]),
            _control("lower_quantile", "Lower quantile", "number", default=0.01),
            _control("upper_quantile", "Upper quantile", "number", default=0.99),
            _control("threshold", "Threshold", "number", default=3.0),
        ],
        default_risk="medium",
        reversible=False,
        produces=["row_flags", "cleaned_column", "row_filter"],
        applies_to=["numeric", "amount", "numeric-like", "percentage", "proportion"],
        evidence_required=["iqr_outlier_count"],
    )
)

register_operation(
    OperationSpec(
        id="geo_coordinate_review",
        family="cleaning",
        title="Review coordinate anomalies",
        description="Spot latitude/longitude values outside valid ranges and likely swapped coordinate pairs.",
        controls=[
            _control("treatment", "Treatment", "select", default="inspect", choices=[
                ("inspect", "Inspect only"),
                ("null_invalid", "Set invalid coordinates to null"),
                ("swap_likely", "Swap likely reversed lat/lon pairs"),
            ]),
        ],
        default_risk="medium",
        reversible=False,
        produces=["row_flags", "coordinate_review"],
        applies_to=["geographic", "numeric"],
        evidence_required=["coordinate_range"],
    )
)

register_operation(
    OperationSpec(
        id="category_value_review",
        family="cleaning",
        title="Review category variants",
        description="Spot category labels that only differ by case or whitespace before mapping values.",
        controls=[
            _control("casefold", "Ignore case", "checkbox", default=True),
            _control("strip", "Trim whitespace", "checkbox", default=True),
            _control("mapping", "Value mapping", "mapping"),
        ],
        reversible=False,
        produces=["mapping_suggestions"],
        applies_to=["category", "string"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.drop_identifier",
        family="modeling",
        title="Drop identifier-like column",
        description="Exclude ID-like columns from model features by default.",
        controls=[_control("drop", "Drop from feature frame", "checkbox", default=True)],
        reversible=True,
        produces=["feature_frame"],
        applies_to=["identifier"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.drop_constant",
        family="modeling",
        title="Drop constant column",
        description="Exclude constant or near-constant columns from model features.",
        controls=[_control("drop", "Drop from feature frame", "checkbox", default=True)],
        reversible=True,
        produces=["feature_frame"],
        applies_to=["constant", "mostly_missing"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.impute_missing",
        family="modeling",
        title="Impute missing values",
        description="Fill missing values using a simple strategy and optionally record an indicator.",
        controls=[
            _control("strategy", "Strategy", "select", default="median", choices=[
                ("median", "Median"),
                ("mean", "Mean"),
                ("mode", "Mode"),
                ("constant", "Constant"),
                ("missing", "Missing label"),
            ]),
            _control("fill_value", "Fill value", "text", help="Used when strategy is Constant, or when no mode is available."),
            _control("add_indicator", "Add missingness indicator", "checkbox", default=True),
        ],
        default_risk="medium",
        reversible=False,
        produces=["feature_frame", "indicator_column"],
        applies_to=["numeric", "amount", "category", "string", "binary"],
        evidence_required=["missing_ratio"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.encode_one_hot",
        family="modeling",
        title="One-hot encode categories",
        description="Convert low- to moderate-cardinality categories into indicator columns.",
        controls=[
            _control("max_categories", "Max categories", "number", default=20),
            _control("drop_first", "Drop first level", "checkbox", default=False),
            _control("dummy_na", "Encode missing level", "checkbox", default=False),
        ],
        default_risk="medium",
        reversible=False,
        produces=["feature_frame", "encoded_columns"],
        applies_to=["category", "string", "nullable_binary", "boolean"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.scale_numeric",
        family="modeling",
        title="Scale numeric features",
        description="Scale numeric features for models that are sensitive to feature magnitude.",
        controls=[
            _control("method", "Method", "select", default="standard", choices=[
                ("standard", "Standard"),
                ("minmax", "Min/max"),
                ("robust", "Robust"),
                ("maxabs", "Max abs"),
                ("none", "None"),
            ]),
        ],
        default_risk="low",
        reversible=False,
        produces=["feature_frame"],
        applies_to=["numeric", "amount", "percentage", "proportion"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.add_date_features",
        family="modeling",
        title="Add date features",
        description="Derive year, quarter, month, weekday, and weekend features from datetime columns.",
        controls=[
            _control("features", "Features", "textarea", default="year\nquarter\nmonth\nweekday\nis_weekend"),
            _control("drop_original", "Drop original date column", "checkbox", default=False),
        ],
        default_risk="low",
        reversible=False,
        produces=["feature_frame", "derived_columns"],
        applies_to=["datetime", "datetime-like"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.add_ratio_feature",
        family="modeling",
        title="Add ratio feature",
        description="Create a safe ratio feature such as price per square foot or revenue per unit.",
        controls=[
            _control("numerator", "Numerator", "column_select", required=True),
            _control("denominator", "Denominator", "column_select", required=True),
            _control("output", "Output column", "text", required=True),
            _control("zero_policy", "Zero denominator", "select", default="null", choices=[
                ("null", "Set ratio to null"),
                ("zero", "Set ratio to zero"),
            ]),
        ],
        default_risk="low",
        reversible=True,
        produces=["feature_frame", "derived_column"],
        applies_to=["numeric", "amount", "count"],
    )
)

register_operation(
    OperationSpec(
        id="modeling.review_target",
        family="modeling",
        title="Review target",
        description="Check target role, task type, imbalance, and missingness before modeling.",
        controls=[],
        default_risk="low",
        reversible=True,
        produces=["target_summary"],
        applies_to=["target"],
    )
)


__all__ = [
    "OperationControl",
    "OperationSpec",
    "all_operation_specs",
    "get_operation_spec",
    "register_operation",
]
