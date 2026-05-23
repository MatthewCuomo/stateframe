"""Previewable modeling-readiness plans."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from stateframe.models import Profile
from stateframe.operations import all_operation_specs, get_operation_spec
from stateframe.transforms import add_date_features, add_missing_indicators, add_ratio, impute_missing, one_hot_encode, scale_numeric


_NUMERIC_FEATURE_TYPES = {"numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"}
_SCALABLE_FEATURE_TYPES = {"numeric", "amount", "numeric-like", "percentage", "proportion"}
_CATEGORICAL_FEATURE_TYPES = {"category", "string", "binary", "nullable_binary", "boolean"}


@dataclass(frozen=True)
class ModelingAction:
    """One modeling-prep recommendation."""

    column: str
    action: str
    confidence: float
    risk: str
    reason: str
    preview: dict[str, Any] = field(default_factory=dict)
    controls: list[dict[str, Any]] = field(default_factory=list)
    control_values: dict[str, Any] = field(default_factory=dict)
    applies_by_default: bool = True

    def to_dict(self) -> dict[str, Any]:
        spec = get_operation_spec(self.action)
        controls = self.controls or ([control.to_dict() for control in spec.controls] if spec is not None else [])
        return {
            "id": _action_id(self),
            "column": self.column,
            "action": self.action,
            "operation_id": self.action,
            "family": "modeling",
            "title": spec.title if spec is not None else self.action.replace("_", " ").title(),
            "confidence": self.confidence,
            "risk": self.risk,
            "reason": self.reason,
            "preview": dict(self.preview),
            "controls": controls,
            "control_values": dict(self.control_values),
            "applies_by_default": self.applies_by_default,
            "spec": spec.to_dict() if spec is not None else None,
        }


@dataclass
class ModelingPlan:
    """A simple feature-prep plan derived from a stateframe profile."""

    profile: Profile = field(repr=False)
    actions: list[ModelingAction] = field(default_factory=list)
    target: str | None = None
    task: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    def preview(self) -> pd.DataFrame:
        return pd.DataFrame([action.to_dict() for action in self.actions])

    def summary(self) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        for action in self.actions:
            by_action[action.action] = by_action.get(action.action, 0) + 1
        return {
            "action_count": len(self.actions),
            "target": self.target,
            "task": self.task,
            "by_action": by_action,
            "settings": dict(self.settings),
        }

    def operation_catalog(self) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in all_operation_specs(family="modeling")]

    def operation_preview(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "catalog": self.operation_catalog(),
            "actions": [action.to_dict() for action in self.actions],
        }

    def to_dict(self) -> dict[str, Any]:
        return self.operation_preview()

    def apply(
        self,
        data: pd.DataFrame | None = None,
        *,
        action_ids: list[str] | None = None,
        include_target: bool = True,
        impute: bool = True,
        encode: bool = True,
        add_indicators: bool = True,
        date_features: bool = True,
        drop_identifiers: bool = True,
        scale: str | None = None,
        max_categories: int = 20,
        action_control_values: dict[str, dict[str, Any]] | None = None,
    ) -> pd.DataFrame:
        """Return a prepared feature frame using selected/default actions."""

        result = (self.profile.data if data is None else data).copy()
        selected = set(action_ids) if action_ids is not None else {
            _action_id(action) for action in self.actions if action.applies_by_default
        }
        target = self.target if include_target else None
        selected_actions = [action for action in self.actions if _action_id(action) in selected]

        drop_columns = [
            action.column
            for action in selected_actions
            if action.action in {"modeling.drop_identifier", "modeling.drop_constant"}
            and action.column in result.columns
            and action.column != target
            and (drop_identifiers or action.action == "modeling.drop_constant")
        ]
        if drop_columns:
            result = result.drop(columns=list(dict.fromkeys(drop_columns)))

        impute_actions = [
            action
            for action in selected_actions
            if action.action == "modeling.impute_missing"
            and action.column in result.columns
            and action.column != target
        ]
        if impute and impute_actions:
            strategies: dict[str, dict[str, Any]] = {}
            indicator_columns = []
            for action in impute_actions:
                controls = _action_controls(action, action_control_values)
                strategy = controls.get("strategy") or "median"
                strategies[action.column] = {
                    "strategy": strategy,
                    "fill_value": controls.get("fill_value"),
                    "groupby": controls.get("groupby"),
                }
                if _bool_control(controls.get("add_indicator"), True):
                    indicator_columns.append(action.column)
            if add_indicators and indicator_columns:
                result = add_missing_indicators(result, indicator_columns, suffix="_was_imputed")
            result = impute_missing(result, strategies=strategies)

        ratio_actions = [
            action
            for action in selected_actions
            if action.action == "modeling.add_ratio_feature"
        ]
        for action in ratio_actions:
            controls = _action_controls(action, action_control_values)
            numerator = str(controls.get("numerator") or action.preview.get("numerator") or "").strip()
            denominator = str(controls.get("denominator") or action.preview.get("denominator") or "").strip()
            output = str(controls.get("output") or action.preview.get("output") or f"{numerator}_per_{denominator}").strip()
            if numerator and denominator and output and numerator in result.columns and denominator in result.columns:
                result = add_ratio(
                    result,
                    numerator,
                    denominator,
                    output,
                    zero_policy=str(controls.get("zero_policy") or "null"),
                )

        date_columns = [
            action.column
            for action in selected_actions
            if action.action == "modeling.add_date_features"
            and action.column in result.columns
            and action.column != target
        ]
        if date_features and date_columns:
            for action in [
                action
                for action in selected_actions
                if action.action == "modeling.add_date_features"
                and action.column in result.columns
                and action.column != target
            ]:
                controls = _action_controls(action, action_control_values)
                result = add_date_features(
                    result,
                    [action.column],
                    features=_feature_list(controls.get("features")),
                    drop_original=_bool_control(controls.get("drop_original"), False),
                )

        encode_actions = [
            action
            for action in selected_actions
            if action.action == "modeling.encode_one_hot"
            and action.column in result.columns
            and action.column != target
        ]
        if encode and encode_actions:
            for action in encode_actions:
                controls = _action_controls(action, action_control_values)
                result = one_hot_encode(
                    result,
                    [action.column],
                    max_categories=int(controls.get("max_categories", max_categories) or max_categories),
                    drop_first=_bool_control(controls.get("drop_first"), False),
                    dummy_na=_bool_control(controls.get("dummy_na"), False),
                )

        scale_actions = [
            action
            for action in self.actions
            if action.action == "modeling.scale_numeric"
            and action.column in result.columns
            and action.column != target
        ]
        selected_scale_actions = [action for action in scale_actions if _action_id(action) in selected]
        if scale and scale != "none":
            scale_columns = [action.column for action in scale_actions]
            scale_method = scale
        elif selected_scale_actions:
            scale_columns = [action.column for action in selected_scale_actions]
            scale_method = _action_controls(selected_scale_actions[0], action_control_values).get("method") or "standard"
        else:
            scale_columns = []
            scale_method = "none"
        if scale_columns and scale_method != "none":
            result = scale_numeric(result, list(dict.fromkeys(scale_columns)), method=scale_method)
        return result


@dataclass(frozen=True)
class ModelingExperimentSpec:
    """Replayable model training, validation, tuning, and explanation settings."""

    target: str | None = None
    task: str = "auto"
    features: list[str] | None = None
    estimator: str = "random_forest"
    estimator_params: dict[str, Any] = field(default_factory=dict)
    split: dict[str, Any] = field(default_factory=lambda: {"test_size": 0.25, "random_state": 42, "shuffle": True, "stratify": True})
    validation: dict[str, Any] = field(default_factory=lambda: {"strategy": "holdout", "cv_folds": 5, "scoring": "auto"})
    preprocessing: dict[str, Any] = field(default_factory=lambda: {
        "numeric_imputer": "median",
        "categorical_imputer": "most_frequent",
        "encoder": "onehot",
        "scaler": "auto",
        "max_categories": 30,
        "drop_identifiers": True,
    })
    search: dict[str, Any] = field(default_factory=lambda: {"enabled": False, "method": "grid", "param_grid": {}, "cv_folds": 3, "scoring": "auto"})
    explanation: dict[str, Any] = field(default_factory=lambda: {"enabled": True, "method": "auto", "max_rows": 100})
    sample: dict[str, Any] = field(default_factory=lambda: {"enabled": False, "max_rows": None, "random_state": 42})
    clustering: dict[str, Any] = field(default_factory=lambda: {"n_clusters": 3})
    random_state: int = 42

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "task": self.task,
            "features": list(self.features) if self.features is not None else None,
            "estimator": self.estimator,
            "estimator_params": dict(self.estimator_params),
            "split": dict(self.split),
            "validation": dict(self.validation),
            "preprocessing": dict(self.preprocessing),
            "search": dict(self.search),
            "explanation": dict(self.explanation),
            "sample": dict(self.sample),
            "clustering": dict(self.clustering),
            "random_state": self.random_state,
        }


@dataclass(frozen=True)
class ModelingExperimentResult:
    """Serializable model experiment result for notebooks, lenses, and web UI."""

    spec: ModelingExperimentSpec
    task: str
    estimator: str
    row_count: int
    feature_count: int
    target: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    holdout: dict[str, Any] = field(default_factory=dict)
    cross_validation: dict[str, Any] = field(default_factory=dict)
    search: dict[str, Any] = field(default_factory=dict)
    feature_importance: list[dict[str, Any]] = field(default_factory=list)
    explanation: dict[str, Any] = field(default_factory=dict)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    preprocessing: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "task": self.task,
            "estimator": self.estimator,
            "target": self.target,
            "row_count": int(self.row_count),
            "feature_count": int(self.feature_count),
            "metrics": _json_ready(self.metrics),
            "holdout": _json_ready(self.holdout),
            "cross_validation": _json_ready(self.cross_validation),
            "search": _json_ready(self.search),
            "feature_importance": _json_ready(self.feature_importance),
            "explanation": _json_ready(self.explanation),
            "predictions": _json_ready(self.predictions),
            "preprocessing": _json_ready(self.preprocessing),
            "warnings": list(self.warnings),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "estimator": self.estimator,
            "target": self.target,
            "row_count": self.row_count,
            "feature_count": self.feature_count,
            "metrics": self.metrics,
            "best_params": self.search.get("best_params"),
            "explanation_method": self.explanation.get("method"),
        }


def modeling_experiment_catalog() -> dict[str, Any]:
    """Return UI-readable model families, split controls, tuning, and explainability options."""

    return {
        "version": 1,
        "tasks": [
            {"id": "auto", "label": "Auto"},
            {"id": "regression", "label": "Regression"},
            {"id": "binary_classification", "label": "Binary classification"},
            {"id": "multiclass_classification", "label": "Multiclass classification"},
            {"id": "clustering", "label": "Clustering"},
        ],
        "estimators": [
            {"id": "random_forest", "label": "Random forest", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": False},
            {"id": "xgboost", "label": "XGBoost", "tasks": ["regression", "binary_classification", "multiclass_classification"], "optional": True, "scaling": False},
            {"id": "knn", "label": "K-nearest neighbors", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": True},
            {"id": "linear", "label": "Linear / logistic", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": True},
            {"id": "kmeans", "label": "K-means", "tasks": ["clustering"], "scaling": True},
            {"id": "agglomerative", "label": "Agglomerative clustering", "tasks": ["clustering"], "scaling": True},
            {"id": "dbscan", "label": "DBSCAN", "tasks": ["clustering"], "scaling": True},
        ],
        "split": {
            "test_size": {"kind": "number", "default": 0.25, "min": 0.05, "max": 0.6},
            "random_state": {"kind": "number", "default": 42},
            "shuffle": {"kind": "checkbox", "default": True},
            "stratify": {"kind": "checkbox", "default": True},
        },
        "validation": {
            "strategies": [
                {"id": "holdout", "label": "Holdout"},
                {"id": "cross_validation", "label": "Cross-validation"},
                {"id": "holdout_and_cv", "label": "Holdout + CV"},
            ],
            "cv_folds": {"kind": "number", "default": 5},
        },
        "preprocessing": {
            "encoders": [
                {"id": "onehot", "label": "One-hot"},
                {"id": "ordinal", "label": "Ordinal"},
            ],
            "scalers": [
                {"id": "auto", "label": "Auto"},
                {"id": "none", "label": "None"},
                {"id": "standard", "label": "Standard"},
                {"id": "minmax", "label": "Min/max"},
                {"id": "robust", "label": "Robust"},
            ],
            "numeric_imputers": ["median", "mean", "most_frequent", "constant"],
            "categorical_imputers": ["most_frequent", "constant"],
        },
        "search": {
            "methods": [{"id": "grid", "label": "Grid search"}],
            "default_grids": _default_param_grids(),
        },
        "explanation": {
            "methods": [
                {"id": "auto", "label": "SHAP if available, otherwise permutation"},
                {"id": "shap", "label": "SHAP"},
                {"id": "permutation", "label": "Permutation"},
                {"id": "model_importance", "label": "Model native"},
            ]
        },
    }


def default_modeling_experiment_spec(profile: Profile, **overrides: Any) -> ModelingExperimentSpec:
    """Build a conservative default experiment spec from profile roles."""

    target = overrides.pop("target", None) or profile.target
    task = overrides.pop("task", "auto")
    if task == "auto":
        task = _infer_experiment_task(profile, target)
    estimator = overrides.pop("estimator", None)
    if estimator is None:
        estimator = "kmeans" if task == "clustering" else "random_forest"
    spec = ModelingExperimentSpec(
        target=target,
        task=task,
        estimator=estimator,
        random_state=int(overrides.pop("random_state", 42)),
    )
    if overrides:
        data = spec.to_dict()
        for key, value in overrides.items():
            if key in data and isinstance(data[key], dict) and isinstance(value, dict):
                data[key] = {**data[key], **value}
            elif key in data:
                data[key] = value
        return normalize_modeling_experiment_spec(data)
    return spec


def normalize_modeling_experiment_spec(spec: ModelingExperimentSpec | dict[str, Any] | None, profile: Profile | None = None) -> ModelingExperimentSpec:
    if isinstance(spec, ModelingExperimentSpec):
        return spec
    raw = dict(spec or {})
    if profile is not None:
        default = default_modeling_experiment_spec(profile).to_dict()
    else:
        default = ModelingExperimentSpec().to_dict()
    merged = {**default, **raw}
    for key in ["estimator_params", "split", "validation", "preprocessing", "search", "explanation", "sample", "clustering"]:
        merged[key] = {**dict(default.get(key) or {}), **dict(raw.get(key) or {})}
    features = merged.get("features")
    if features is not None:
        features = [str(item) for item in features if item not in {None, ""}]
    return ModelingExperimentSpec(
        target=merged.get("target"),
        task=str(merged.get("task") or "auto"),
        features=features,
        estimator=str(merged.get("estimator") or "random_forest"),
        estimator_params=dict(merged.get("estimator_params") or {}),
        split=dict(merged.get("split") or {}),
        validation=dict(merged.get("validation") or {}),
        preprocessing=dict(merged.get("preprocessing") or {}),
        search=dict(merged.get("search") or {}),
        explanation=dict(merged.get("explanation") or {}),
        sample=dict(merged.get("sample") or {}),
        clustering=dict(merged.get("clustering") or {}),
        random_state=int(merged.get("random_state") or 42),
    )


def run_modeling_experiment(
    profile: Profile,
    spec: ModelingExperimentSpec | dict[str, Any] | None = None,
    **overrides: Any,
) -> ModelingExperimentResult:
    """Run a replayable supervised or clustering modeling experiment."""

    base = normalize_modeling_experiment_spec(spec, profile)
    if overrides:
        merged = base.to_dict()
        for key, value in overrides.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            elif key in merged:
                merged[key] = value
        base = normalize_modeling_experiment_spec(merged, profile)
    task = _infer_experiment_task(profile, base.target) if base.task == "auto" else base.task
    if task == "clustering":
        return _run_clustering_experiment(profile, base)
    if not base.target:
        raise ValueError("A target column is required for supervised modeling experiments.")
    if base.target not in profile.data.columns:
        raise ValueError(f"Unknown target column: {base.target}")
    return _run_supervised_experiment(profile, base, task=task)


def build_modeling_plan(
    profile: Profile,
    *,
    max_categories: int = 20,
    include_scaling: bool = True,
) -> ModelingPlan:
    actions: list[ModelingAction] = []
    target = profile.target
    task = profile.target_profile.task if profile.target_profile else profile.task_inference.task if profile.task_inference else None

    if target and target in profile.column_profiles:
        target_profile = profile.column(target)
        actions.append(
            ModelingAction(
                column=target,
                action="modeling.review_target",
                confidence=profile.target_profile.confidence if profile.target_profile else 0.7,
                risk="low",
                reason="a confirmed target unlocks target-aware modeling prep",
                preview={
                    "task": task,
                    "missing_ratio": target_profile.missing_ratio,
                    "distinct_count": target_profile.distinct_count,
                    "top_ratio": target_profile.metrics.get("top_ratio"),
                },
                applies_by_default=False,
            )
        )

    for column in profile.column_profiles.values():
        if column.name == target:
            continue
        if column.semantic_type == "identifier":
            actions.append(
                ModelingAction(
                    column=column.name,
                    action="modeling.drop_identifier",
                    confidence=column.semantic_confidence,
                    risk="low",
                    reason="identifier-like columns usually memorize rows rather than generalize",
                    preview={"distinct_ratio": column.distinct_ratio, "role": column.role},
                )
            )
            continue
        if column.semantic_type in {"constant", "mostly_missing"}:
            actions.append(
                ModelingAction(
                    column=column.name,
                    action="modeling.drop_constant",
                    confidence=0.95,
                    risk="low",
                    reason="constant or mostly-missing columns rarely help model features directly",
                    preview={"missing_ratio": column.missing_ratio, "distinct_count": column.distinct_count},
                )
            )
            continue

        if column.missing_ratio > 0:
            numeric = column.semantic_type in _NUMERIC_FEATURE_TYPES
            actions.append(
                ModelingAction(
                    column=column.name,
                    action="modeling.impute_missing",
                    confidence=0.76,
                    risk="medium",
                    reason="model features need an explicit missing-value strategy",
                    preview={"missing_count": column.missing_count, "missing_ratio": column.missing_ratio},
                    control_values={
                        "strategy": "median" if numeric else "mode",
                        "add_indicator": True,
                    },
                )
            )

        if column.semantic_type in _CATEGORICAL_FEATURE_TYPES and column.distinct_count <= max_categories:
            actions.append(
                ModelingAction(
                    column=column.name,
                    action="modeling.encode_one_hot",
                    confidence=0.78,
                    risk="medium",
                    reason="low-cardinality categories can be represented as indicator columns",
                    preview={"distinct_count": column.distinct_count, "top_values": column.top_values[:5]},
                    control_values={"max_categories": max_categories, "drop_first": False, "dummy_na": False},
                )
            )

        if column.semantic_type in {"datetime", "datetime-like"}:
            actions.append(
                ModelingAction(
                    column=column.name,
                    action="modeling.add_date_features",
                    confidence=0.82,
                    risk="low",
                    reason="datetime columns usually need derived calendar features for tabular models",
                    preview={
                        "min": column.metrics.get("min"),
                        "max": column.metrics.get("max"),
                        "span_days": column.metrics.get("span_days"),
                    },
                    control_values={"features": "year\nquarter\nmonth\nweekday\nis_weekend", "drop_original": False},
                )
            )

        if include_scaling and column.semantic_type in _SCALABLE_FEATURE_TYPES:
            actions.append(
                ModelingAction(
                    column=column.name,
                    action="modeling.scale_numeric",
                    confidence=0.66,
                    risk="low",
                    reason="some model families benefit from numeric features on comparable scales",
                    preview={"min": column.metrics.get("min"), "max": column.metrics.get("max"), "std": column.metrics.get("std")},
                    control_values={"method": "standard"},
                    applies_by_default=False,
                )
            )

    actions.extend(_ratio_actions(profile, target=target))

    return ModelingPlan(
        profile=profile,
        actions=_dedupe_actions(actions),
        target=target,
        task=task,
        settings={"max_categories": max_categories, "include_scaling": include_scaling},
    )


def _dedupe_actions(actions: list[ModelingAction]) -> list[ModelingAction]:
    seen: set[tuple[str, str]] = set()
    result = []
    for action in actions:
        key = (action.column, action.action)
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result


def _ratio_actions(profile: Profile, *, target: str | None, limit: int = 8) -> list[ModelingAction]:
    numeric_columns = [
        column
        for column in profile.column_profiles.values()
        if column.name != target and column.semantic_type in _SCALABLE_FEATURE_TYPES | {"numeric_discrete"}
    ]
    numerators = [
        column
        for column in numeric_columns
        if column.semantic_type == "amount" or _name_contains(column.name, ["price", "value", "amount", "revenue", "sales", "cost", "tax", "income", "rent"])
    ]
    denominators = [
        column
        for column in numeric_columns
        if _name_contains(column.name, ["sqft", "square", "area", "acre", "lot", "unit", "count", "room", "bed", "bath", "size"])
        and column.metrics.get("zero_ratio", 0) != 1
    ]
    actions: list[ModelingAction] = []
    seen: set[tuple[str, str]] = set()
    for numerator in numerators:
        for denominator in denominators:
            if numerator.name == denominator.name or (numerator.name, denominator.name) in seen:
                continue
            seen.add((numerator.name, denominator.name))
            output = _safe_feature_name(f"{numerator.name}_per_{denominator.name}")
            actions.append(
                ModelingAction(
                    column=output,
                    action="modeling.add_ratio_feature",
                    confidence=0.64,
                    risk="low",
                    reason=f"{numerator.name} normalized by {denominator.name} may be more comparable across rows",
                    preview={
                        "numerator": numerator.name,
                        "denominator": denominator.name,
                        "output": output,
                        "numerator_type": numerator.semantic_type,
                        "denominator_type": denominator.semantic_type,
                    },
                    control_values={
                        "numerator": numerator.name,
                        "denominator": denominator.name,
                        "output": output,
                        "zero_policy": "null",
                    },
                    applies_by_default=False,
                )
            )
            if len(actions) >= limit:
                return actions
    return actions


def _action_id(action: ModelingAction) -> str:
    return f"{action.action}:{action.column}"


def _name_contains(name: str, needles: list[str]) -> bool:
    lowered = name.lower()
    return any(needle in lowered for needle in needles)


def _safe_feature_name(name: str) -> str:
    result = []
    previous_underscore = False
    for char in name:
        if char.isalnum():
            result.append(char.lower())
            previous_underscore = False
        elif not previous_underscore:
            result.append("_")
            previous_underscore = True
    return "".join(result).strip("_") or "ratio_feature"


def _action_controls(
    action: ModelingAction,
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    values = dict(action.control_values)
    if overrides:
        values.update(dict(overrides.get(_action_id(action)) or {}))
    return values


def _bool_control(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _feature_list(value: Any) -> list[str]:
    if value is None:
        return ["year", "quarter", "month", "weekday", "is_weekend"]
    if isinstance(value, str):
        parts = value.replace(",", "\n").splitlines()
    else:
        parts = list(value)
    return [str(part).strip() for part in parts if str(part).strip()]


def _run_supervised_experiment(
    profile: Profile,
    spec: ModelingExperimentSpec,
    *,
    task: str,
) -> ModelingExperimentResult:
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        mean_absolute_error,
        mean_squared_error,
        precision_score,
        precision_recall_curve,
        r2_score,
        recall_score,
        roc_curve,
        roc_auc_score,
    )
    from sklearn.model_selection import GridSearchCV, cross_validate, train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder

    warnings: list[str] = []
    frame = _sample_modeling_frame(profile.data, spec, warnings=warnings).copy()
    target = str(spec.target)
    y_raw = frame[target]
    keep = y_raw.notna()
    frame = frame.loc[keep].copy()
    y_raw = y_raw.loc[keep]
    X_raw, feature_roles = _select_feature_frame(profile, spec, exclude_target=target, warnings=warnings)
    X_raw = X_raw.loc[frame.index]
    if X_raw.empty:
        raise ValueError("No usable feature columns were found for modeling.")

    is_classification = task in {"binary_classification", "multiclass_classification"}
    label_encoder = None
    if is_classification:
        label_encoder = LabelEncoder()
        y = pd.Series(label_encoder.fit_transform(y_raw.astype("string")), index=y_raw.index, name=target)
        class_labels = [str(item) for item in label_encoder.classes_]
    else:
        y = pd.to_numeric(y_raw, errors="coerce")
        keep_y = y.notna()
        X_raw = X_raw.loc[keep_y]
        y = y.loc[keep_y]
        class_labels = []

    estimator = _build_estimator(spec.estimator, task=task, random_state=spec.random_state, params=spec.estimator_params)
    preprocessor, preprocessing_summary = _build_preprocessor(X_raw, feature_roles, spec, estimator_id=spec.estimator)
    pipeline = Pipeline([("preprocess", preprocessor), ("model", estimator)])

    split = dict(spec.split or {})
    test_size = _float_setting(split.get("test_size"), 0.25)
    random_state = int(split.get("random_state", spec.random_state) or spec.random_state)
    shuffle = _bool_setting(split.get("shuffle"), True)
    stratify = None
    if is_classification and _bool_setting(split.get("stratify"), True):
        counts = y.value_counts()
        if len(counts) > 1 and int(counts.min()) >= 2:
            stratify = y
        else:
            warnings.append("Stratified split skipped because at least one class has fewer than two rows.")
    X_train, X_test, y_train, y_test = train_test_split(
        X_raw,
        y,
        test_size=test_size,
        random_state=random_state,
        shuffle=shuffle,
        stratify=stratify,
    )

    search_summary: dict[str, Any] = {"enabled": False}
    fitted = pipeline
    if _bool_setting((spec.search or {}).get("enabled"), False):
        grid = _normalize_param_grid((spec.search or {}).get("param_grid") or _default_param_grid(spec.estimator, task))
        if grid:
            scoring = _resolve_scoring((spec.search or {}).get("scoring"), task)
            cv = _cv_splitter(task, y_train, int((spec.search or {}).get("cv_folds") or 3), random_state)
            search = GridSearchCV(
                pipeline,
                grid,
                scoring=scoring,
                cv=cv,
                n_jobs=-1,
                error_score="raise",
            )
            search.fit(X_train, y_train)
            fitted = search.best_estimator_
            search_summary = {
                "enabled": True,
                "method": str((spec.search or {}).get("method") or "grid"),
                "scoring": scoring,
                "best_score": _clean_metric(search.best_score_),
                "best_params": _unprefix_params(search.best_params_),
                "candidate_count": int(len(search.cv_results_.get("params", []))),
            }
        else:
            warnings.append("Grid search was enabled but no parameter grid was provided.")
    else:
        fitted.fit(X_train, y_train)

    predictions = fitted.predict(X_test)
    proba = _predict_proba_safe(fitted, X_test)
    holdout = _supervised_metrics(
        y_test,
        predictions,
        proba,
        task=task,
        class_labels=class_labels,
        accuracy_score=accuracy_score,
        f1_score=f1_score,
        precision_score=precision_score,
        recall_score=recall_score,
        roc_auc_score=roc_auc_score,
        classification_report=classification_report,
        precision_recall_curve=precision_recall_curve,
        roc_curve=roc_curve,
        confusion_matrix=confusion_matrix,
        mean_absolute_error=mean_absolute_error,
        mean_squared_error=mean_squared_error,
        r2_score=r2_score,
    )

    cv_summary: dict[str, Any] = {"enabled": False}
    validation = dict(spec.validation or {})
    if str(validation.get("strategy") or "holdout") in {"cross_validation", "holdout_and_cv"}:
        scoring = _cv_scoring(task, validation.get("scoring"))
        cv = _cv_splitter(task, y, int(validation.get("cv_folds") or 5), random_state)
        cv_result = cross_validate(
            fitted if search_summary.get("enabled") else pipeline,
            X_raw,
            y,
            cv=cv,
            scoring=scoring,
            n_jobs=-1,
            error_score="raise",
        )
        cv_summary = _summarize_cv(cv_result)

    feature_names = _feature_names(fitted, X_raw)
    model = fitted.named_steps["model"]
    transformed_test = _transformed_frame(fitted, X_test, feature_names)
    feature_importance = _model_importance(model, feature_names)
    explanation = _explain_model(
        fitted,
        transformed_test,
        y_test,
        task=task,
        method=str((spec.explanation or {}).get("method") or "auto"),
        enabled=_bool_setting((spec.explanation or {}).get("enabled"), True),
        max_rows=int((spec.explanation or {}).get("max_rows") or 100),
        fallback_importance=feature_importance,
        warnings=warnings,
    )

    prediction_rows = _prediction_sample(
        X_test,
        y_test,
        predictions,
        proba,
        class_labels=class_labels,
        limit=25,
    )
    metrics = dict(holdout.get("metrics") or {})
    return ModelingExperimentResult(
        spec=spec,
        task=task,
        estimator=spec.estimator,
        target=target,
        row_count=int(X_raw.shape[0]),
        feature_count=int(len(feature_names)),
        metrics=metrics,
        holdout=holdout,
        cross_validation=cv_summary,
        search=search_summary,
        feature_importance=feature_importance,
        explanation=explanation,
        predictions=prediction_rows,
        preprocessing={**preprocessing_summary, "feature_roles": feature_roles},
        warnings=warnings,
    )


def _run_clustering_experiment(profile: Profile, spec: ModelingExperimentSpec) -> ModelingExperimentResult:
    from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
    from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
    from sklearn.pipeline import Pipeline

    warnings: list[str] = []
    sample_frame = _sample_modeling_frame(profile.data, spec, warnings=warnings)
    X_raw, feature_roles = _select_feature_frame(profile, spec, exclude_target=None, warnings=warnings)
    X_raw = X_raw.loc[sample_frame.index]
    if X_raw.empty:
        raise ValueError("No usable feature columns were found for clustering.")
    preprocessor, preprocessing_summary = _build_preprocessor(X_raw, feature_roles, spec, estimator_id=spec.estimator, force_scaling=True)
    estimator_id = spec.estimator
    if estimator_id == "agglomerative":
        estimator = AgglomerativeClustering(n_clusters=int((spec.clustering or {}).get("n_clusters") or 3))
    elif estimator_id == "dbscan":
        estimator = DBSCAN(
            eps=_float_setting((spec.clustering or {}).get("eps"), 0.5),
            min_samples=int((spec.clustering or {}).get("min_samples") or 5),
        )
    else:
        estimator_id = "kmeans"
        estimator = KMeans(
            n_clusters=int((spec.clustering or {}).get("n_clusters") or 3),
            n_init="auto",
            random_state=spec.random_state,
        )
    pipeline = Pipeline([("preprocess", preprocessor), ("model", estimator)])
    labels = pipeline.fit_predict(X_raw)
    feature_names = _feature_names(pipeline, X_raw)
    transformed = _transformed_frame(pipeline, X_raw, feature_names)
    label_series = pd.Series(labels, index=X_raw.index, name="cluster")
    cluster_sizes = label_series.value_counts(dropna=False).sort_index().to_dict()
    metrics: dict[str, Any] = {
        "cluster_count": int(label_series.nunique(dropna=False)),
        "cluster_sizes": {str(key): int(value) for key, value in cluster_sizes.items()},
    }
    non_noise = label_series != -1
    if label_series[non_noise].nunique() >= 2 and transformed.loc[non_noise].shape[0] > label_series[non_noise].nunique():
        metrics["silhouette"] = _clean_metric(silhouette_score(transformed.loc[non_noise], label_series.loc[non_noise]))
        metrics["calinski_harabasz"] = _clean_metric(calinski_harabasz_score(transformed.loc[non_noise], label_series.loc[non_noise]))
        metrics["davies_bouldin"] = _clean_metric(davies_bouldin_score(transformed.loc[non_noise], label_series.loc[non_noise]))
    if hasattr(pipeline.named_steps["model"], "inertia_"):
        metrics["inertia"] = _clean_metric(pipeline.named_steps["model"].inertia_)
    importance = _cluster_profile_importance(transformed, label_series)
    predictions = [{"index": _json_ready(index), "cluster": int(label)} for index, label in label_series.head(50).items()]
    return ModelingExperimentResult(
        spec=spec,
        task="clustering",
        estimator=estimator_id,
        target=None,
        row_count=int(X_raw.shape[0]),
        feature_count=int(len(feature_names)),
        metrics=metrics,
        holdout={},
        cross_validation={"enabled": False},
        search={"enabled": False},
        feature_importance=importance,
        explanation={
            "enabled": True,
            "method": "cluster_profile",
            "top_features": importance[:20],
            "notes": ["Cluster observability is based on between-cluster mean separation per transformed feature."],
        },
        predictions=predictions,
        preprocessing={**preprocessing_summary, "feature_roles": feature_roles},
        warnings=warnings,
    )


def _sample_modeling_frame(data: pd.DataFrame, spec: ModelingExperimentSpec, *, warnings: list[str]) -> pd.DataFrame:
    sample = dict(spec.sample or {})
    max_rows = _int_setting(sample.get("max_rows"), 0)
    enabled = _bool_setting(sample.get("enabled"), max_rows > 0)
    if not enabled or max_rows <= 0 or len(data) <= max_rows:
        return data
    random_state = _int_setting(sample.get("random_state"), spec.random_state)
    warnings.append(f"Modeled a reproducible sample of {max_rows:,} rows from {len(data):,}.")
    return data.sample(n=max_rows, random_state=random_state)


def _select_feature_frame(
    profile: Profile,
    spec: ModelingExperimentSpec,
    *,
    exclude_target: str | None,
    warnings: list[str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    data = profile.data
    requested = [column for column in (spec.features or []) if column in data.columns and column != exclude_target]
    if requested:
        columns = requested
    else:
        columns = []
        for name, column in profile.column_profiles.items():
            if name == exclude_target:
                continue
            if _looks_like_target_leakage(name, exclude_target):
                warnings.append(f"Skipped likely target-derived feature column: {name}")
                continue
            if _bool_setting((spec.preprocessing or {}).get("drop_identifiers"), True) and column.semantic_type == "identifier":
                continue
            if column.semantic_type in {"constant", "mostly_missing", "text", "json-like"}:
                continue
            columns.append(name)
    roles: dict[str, str] = {}
    kept: list[str] = []
    for name in columns:
        if name not in data.columns:
            continue
        role = _feature_role(profile.column_profiles.get(name), data[name])
        if role == "drop":
            warnings.append(f"Skipped unsupported feature column: {name}")
            continue
        roles[name] = role
        kept.append(name)
    return data[kept].copy(), roles


def _feature_role(column: Any, series: pd.Series) -> str:
    semantic = getattr(column, "semantic_type", "")
    if semantic in _NUMERIC_FEATURE_TYPES or pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if semantic in {"datetime", "datetime-like"} or pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if semantic in _CATEGORICAL_FEATURE_TYPES or pd.api.types.is_bool_dtype(series) or pd.api.types.is_object_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype):
        return "categorical"
    return "drop"


def _looks_like_target_leakage(name: str, target: str | None) -> bool:
    if not target:
        return False
    lowered_name = str(name).lower()
    lowered_target = str(target).lower()
    compact_name = "".join(char for char in lowered_name if char.isalnum())
    compact_target = "".join(char for char in lowered_target if char.isalnum())
    if compact_target and compact_target in compact_name:
        return True
    if "price" in lowered_target and ("price_per" in lowered_name or "per_price" in lowered_name):
        return True
    return False


def _build_preprocessor(
    X: pd.DataFrame,
    feature_roles: dict[str, str],
    spec: ModelingExperimentSpec,
    *,
    estimator_id: str,
    force_scaling: bool = False,
):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer, MinMaxScaler, OneHotEncoder, OrdinalEncoder, RobustScaler, StandardScaler

    numeric_columns = [column for column, role in feature_roles.items() if role == "numeric"]
    categorical_columns = [column for column, role in feature_roles.items() if role == "categorical"]
    datetime_columns = [column for column, role in feature_roles.items() if role == "datetime"]
    transformers = []
    preprocessing = dict(spec.preprocessing or {})
    scaler_name = str(preprocessing.get("scaler") or "auto")
    if scaler_name == "auto":
        scaler_name = "standard" if force_scaling or estimator_id in {"knn", "linear", "kmeans", "agglomerative", "dbscan"} else "none"
    numeric_steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy=str(preprocessing.get("numeric_imputer") or "median")))]
    scaler = _scaler(scaler_name)
    if scaler is not None:
        numeric_steps.append(("scaler", scaler))
    if numeric_columns:
        transformers.append(("numeric", Pipeline(numeric_steps), numeric_columns))
    if datetime_columns:
        datetime_steps: list[tuple[str, Any]] = [
            ("calendar", FunctionTransformer(_datetime_features, validate=False, feature_names_out=_datetime_feature_names)),
            ("imputer", SimpleImputer(strategy="median")),
        ]
        if scaler is not None:
            datetime_steps.append(("scaler", _scaler(scaler_name)))
        transformers.append(("datetime", Pipeline(datetime_steps), datetime_columns))
    if categorical_columns:
        encoder = str(preprocessing.get("encoder") or "onehot")
        cat_imputer = SimpleImputer(
            strategy="constant" if str(preprocessing.get("categorical_imputer") or "most_frequent") == "constant" else "most_frequent",
            fill_value="Missing",
        )
        if encoder == "ordinal":
            cat_encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1)
        else:
            cat_encoder = OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=False,
                max_categories=int(preprocessing.get("max_categories") or 30),
            )
        transformers.append(("categorical", Pipeline([("imputer", cat_imputer), ("encoder", cat_encoder)]), categorical_columns))
    return ColumnTransformer(transformers=transformers, remainder="drop", verbose_feature_names_out=False), {
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "datetime_columns": datetime_columns,
        "encoder": str(preprocessing.get("encoder") or "onehot"),
        "scaler": scaler_name,
    }


def _build_estimator(estimator_id: str, *, task: str, random_state: int, params: dict[str, Any]):
    is_classification = task in {"binary_classification", "multiclass_classification"}
    params = dict(params or {})
    if estimator_id == "xgboost":
        try:
            from xgboost import XGBClassifier, XGBRegressor
        except Exception as exc:  # pragma: no cover - depends on optional install.
            raise ImportError("XGBoost is not installed; choose another estimator or install xgboost.") from exc
        defaults = {"n_estimators": 80, "max_depth": 4, "learning_rate": 0.08, "subsample": 0.9, "colsample_bytree": 0.9, "random_state": random_state}
        if is_classification:
            return XGBClassifier(**{**defaults, "eval_metric": "logloss", **params})
        return XGBRegressor(**{**defaults, "objective": "reg:squarederror", **params})
    if estimator_id == "knn":
        from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor

        defaults = {"n_neighbors": 5, "weights": "uniform"}
        return (KNeighborsClassifier if is_classification else KNeighborsRegressor)(**{**defaults, **params})
    if estimator_id == "linear":
        if is_classification:
            from sklearn.linear_model import LogisticRegression

            return LogisticRegression(max_iter=1000, random_state=random_state, **params)
        from sklearn.linear_model import Ridge

        return Ridge(random_state=random_state, **params)
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

    defaults = {"n_estimators": 160, "min_samples_leaf": 2, "random_state": random_state, "n_jobs": -1}
    return (RandomForestClassifier if is_classification else RandomForestRegressor)(**{**defaults, **params})


def _supervised_metrics(y_true: pd.Series, predictions: Any, proba: Any, *, task: str, class_labels: list[str], **metric_funcs: Any) -> dict[str, Any]:
    is_classification = task in {"binary_classification", "multiclass_classification"}
    if is_classification:
        average = "binary" if task == "binary_classification" and len(set(y_true)) <= 2 else "weighted"
        metrics = {
            "accuracy": _clean_metric(metric_funcs["accuracy_score"](y_true, predictions)),
            "f1": _clean_metric(metric_funcs["f1_score"](y_true, predictions, average=average, zero_division=0)),
            "precision": _clean_metric(metric_funcs["precision_score"](y_true, predictions, average=average, zero_division=0)),
            "recall": _clean_metric(metric_funcs["recall_score"](y_true, predictions, average=average, zero_division=0)),
        }
        if proba is not None and len(set(y_true)) > 1:
            try:
                if task == "binary_classification" and proba.shape[1] >= 2:
                    metrics["roc_auc"] = _clean_metric(metric_funcs["roc_auc_score"](y_true, proba[:, 1]))
                elif proba.shape[1] > 2:
                    metrics["roc_auc_ovr"] = _clean_metric(metric_funcs["roc_auc_score"](y_true, proba, multi_class="ovr"))
            except Exception:
                pass
        matrix = metric_funcs["confusion_matrix"](y_true, predictions)
        report = metric_funcs["classification_report"](
            y_true,
            predictions,
            target_names=class_labels if class_labels and len(class_labels) == len(set(y_true) | set(predictions)) else None,
            output_dict=True,
            zero_division=0,
        )
        curves: dict[str, Any] = {}
        if proba is not None and task == "binary_classification" and proba.shape[1] >= 2 and len(set(y_true)) > 1:
            precision, recall, pr_thresholds = metric_funcs["precision_recall_curve"](y_true, proba[:, 1])
            fpr, tpr, roc_thresholds = metric_funcs["roc_curve"](y_true, proba[:, 1])
            curves = {
                "precision_recall": _curve_rows(
                    {"precision": precision, "recall": recall},
                    thresholds=pr_thresholds,
                    threshold_name="threshold",
                ),
                "roc": _curve_rows(
                    {"fpr": fpr, "tpr": tpr},
                    thresholds=roc_thresholds,
                    threshold_name="threshold",
                ),
            }
        return {
            "metrics": metrics,
            "classification_report": _json_ready(report),
            "confusion_matrix": matrix.tolist(),
            "class_labels": class_labels,
            "curves": curves,
        }
    mae = metric_funcs["mean_absolute_error"](y_true, predictions)
    mse = metric_funcs["mean_squared_error"](y_true, predictions)
    metrics = {
        "mae": _clean_metric(mae),
        "rmse": _clean_metric(float(np.sqrt(mse))),
        "r2": _clean_metric(metric_funcs["r2_score"](y_true, predictions)),
    }
    return {"metrics": metrics}


def _predict_proba_safe(model: Any, X: pd.DataFrame) -> Any:
    if not hasattr(model, "predict_proba"):
        return None
    try:
        return model.predict_proba(X)
    except Exception:
        return None


def _curve_rows(series: dict[str, Any], *, thresholds: Any, threshold_name: str) -> list[dict[str, Any]]:
    length = max(len(values) for values in series.values()) if series else 0
    threshold_values = list(thresholds)
    rows = []
    for index in range(length):
        row = {name: _clean_metric(values[index]) for name, values in series.items() if index < len(values)}
        row[threshold_name] = _clean_metric(threshold_values[index]) if index < len(threshold_values) else None
        rows.append(row)
    return rows


def _cv_scoring(task: str, requested: Any) -> list[str]:
    if requested and requested != "auto":
        return [str(requested)]
    if task in {"binary_classification", "multiclass_classification"}:
        return ["accuracy", "f1_weighted"]
    return ["neg_mean_absolute_error", "r2"]


def _resolve_scoring(requested: Any, task: str) -> str:
    if requested and requested != "auto":
        return str(requested)
    return "accuracy" if task in {"binary_classification", "multiclass_classification"} else "neg_mean_absolute_error"


def _cv_splitter(task: str, y: pd.Series, folds: int, random_state: int):
    from sklearn.model_selection import KFold, StratifiedKFold

    folds = max(2, min(int(folds or 5), int(y.shape[0])))
    if task in {"binary_classification", "multiclass_classification"} and y.nunique() > 1 and y.value_counts().min() >= folds:
        return StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_state)
    return KFold(n_splits=folds, shuffle=True, random_state=random_state)


def _summarize_cv(cv_result: dict[str, Any]) -> dict[str, Any]:
    scores = {}
    for key, values in cv_result.items():
        if not key.startswith("test_"):
            continue
        name = key.removeprefix("test_")
        arr = np.asarray(values, dtype=float)
        scores[name] = {"mean": _clean_metric(np.nanmean(arr)), "std": _clean_metric(np.nanstd(arr)), "folds": [_clean_metric(value) for value in arr]}
    return {"enabled": True, "scores": scores}


def _feature_names(pipeline: Any, X: pd.DataFrame) -> list[str]:
    preprocessor = pipeline.named_steps.get("preprocess")
    width = 0
    try:
        transformed = preprocessor.transform(X.head(2))
        width = int(transformed.shape[1])
    except Exception:
        width = 0
    names: list[str] = []
    for args in ((list(X.columns),), ()):
        try:
            names = [str(name) for name in preprocessor.get_feature_names_out(*args)]
            if not width or len(names) == width:
                return names
        except Exception:
            continue
    names = _column_transformer_feature_names(preprocessor, X)
    if not width or len(names) == width:
        return names
    return [f"feature_{index}" for index in range(width)]


def _column_transformer_feature_names(preprocessor: Any, X: pd.DataFrame) -> list[str]:
    names: list[str] = []
    transformers = getattr(preprocessor, "transformers_", []) or []
    for index, item in enumerate(transformers):
        if len(item) < 3:
            continue
        transformer_name, transformer, columns = item[:3]
        if transformer == "drop":
            continue
        input_names = _column_selection_names(X, columns)
        if transformer == "passthrough":
            names.extend(input_names)
            continue
        try:
            output_names = transformer.get_feature_names_out(input_names)
            names.extend(str(name) for name in output_names)
            continue
        except Exception:
            pass
        width = _transformer_width(transformer, X, input_names)
        if width == len(input_names):
            names.extend(input_names)
        elif len(input_names) == 1:
            names.extend(f"{input_names[0]}_{offset}" for offset in range(width))
        else:
            names.extend(f"{transformer_name}_{offset}" for offset in range(width))
    return names


def _column_selection_names(X: pd.DataFrame, columns: Any) -> list[str]:
    if isinstance(columns, slice):
        return [str(column) for column in X.columns[columns]]
    if isinstance(columns, (list, tuple, pd.Index, np.ndarray)):
        values = list(columns)
        if values and all(isinstance(value, (bool, np.bool_)) for value in values):
            return [str(column) for column, keep in zip(X.columns, values) if keep]
        return [str(X.columns[int(value)]) if isinstance(value, (int, np.integer)) else str(value) for value in values]
    if columns is None:
        return []
    if isinstance(columns, (int, np.integer)):
        return [str(X.columns[int(columns)])]
    return [str(columns)]


def _transformer_width(transformer: Any, X: pd.DataFrame, input_names: list[str]) -> int:
    if not input_names:
        return 0
    try:
        transformed = transformer.transform(X[input_names].head(2))
        return int(transformed.shape[1])
    except Exception:
        return len(input_names)


def _transformed_frame(pipeline: Any, X: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    transformed = pipeline.named_steps["preprocess"].transform(X)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    return pd.DataFrame(transformed, columns=feature_names, index=X.index)


def _model_importance(model: Any, feature_names: list[str]) -> list[dict[str, Any]]:
    values = None
    if hasattr(model, "feature_importances_"):
        values = getattr(model, "feature_importances_")
    elif hasattr(model, "coef_"):
        coef = np.asarray(getattr(model, "coef_"))
        values = np.mean(np.abs(coef), axis=0) if coef.ndim > 1 else np.abs(coef)
    if values is None:
        return []
    rows = [
        {"feature": str(feature), "importance": _clean_metric(value)}
        for feature, value in zip(feature_names, np.asarray(values, dtype=float))
    ]
    return sorted(rows, key=lambda row: abs(float(row.get("importance") or 0)), reverse=True)[:50]


def _explain_model(
    pipeline: Any,
    transformed: pd.DataFrame,
    y_test: pd.Series,
    *,
    task: str,
    method: str,
    enabled: bool,
    max_rows: int,
    fallback_importance: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "method": "disabled", "top_features": fallback_importance[:20]}
    sample = transformed.head(max(1, min(max_rows, transformed.shape[0])))
    model = pipeline.named_steps["model"]
    if method in {"auto", "shap"}:
        try:
            import shap

            explainer = shap.Explainer(model, sample)
            values = explainer(sample)
            payload = _shap_payload(values, sample)
            return {
                "enabled": True,
                "method": "shap",
                "sample_rows": int(sample.shape[0]),
                **payload,
            }
        except Exception as exc:
            if method == "shap":
                warnings.append(f"SHAP failed: {exc}")
            else:
                warnings.append(f"SHAP auto explanation fell back: {exc}")
    if method in {"auto", "permutation"}:
        try:
            from sklearn.inspection import permutation_importance

            result = permutation_importance(
                pipeline.named_steps["model"],
                sample.to_numpy(),
                y_test.loc[sample.index],
                n_repeats=5,
                random_state=0,
                n_jobs=-1,
            )
            rows = [
                {"feature": feature, "permutation_importance": _clean_metric(value)}
                for feature, value in zip(sample.columns, result.importances_mean)
            ]
            rows = sorted(rows, key=lambda row: abs(float(row.get("permutation_importance") or 0)), reverse=True)[:50]
            return {"enabled": True, "method": "permutation", "sample_rows": int(sample.shape[0]), "top_features": rows}
        except Exception as exc:
            warnings.append(f"Permutation explanation failed: {exc}")
    return {"enabled": True, "method": "model_importance", "top_features": fallback_importance[:20]}


def _cluster_profile_importance(X: pd.DataFrame, labels: pd.Series) -> list[dict[str, Any]]:
    if X.empty:
        return []
    overall = X.mean(axis=0)
    rows = []
    for feature in X.columns:
        means = X.groupby(labels)[feature].mean()
        score = float((means - overall[feature]).abs().mean()) if not means.empty else 0.0
        rows.append({"feature": str(feature), "cluster_separation": _clean_metric(score)})
    return sorted(rows, key=lambda row: float(row.get("cluster_separation") or 0), reverse=True)[:50]


def _shap_payload(values: Any, sample: pd.DataFrame) -> dict[str, Any]:
    raw_values = np.asarray(values.values)
    output_index = None
    if raw_values.ndim == 3:
        output_index = 1 if raw_values.shape[2] > 1 else 0
        signed_values = raw_values[:, :, output_index]
        ranking_values = np.nanmean(np.abs(raw_values), axis=2)
    else:
        signed_values = raw_values
        ranking_values = np.abs(raw_values)
    means = np.nanmean(np.abs(ranking_values), axis=0)
    top_features = [
        {"feature": feature, "mean_abs_shap": _clean_metric(value)}
        for feature, value in zip(sample.columns, means)
    ]
    top_features = sorted(top_features, key=lambda row: float(row.get("mean_abs_shap") or 0), reverse=True)[:50]
    top_feature_names = [row["feature"] for row in top_features[:15]]
    feature_index = {feature: idx for idx, feature in enumerate(sample.columns)}
    beeswarm = []
    for row_position, (row_index, row) in enumerate(sample.iterrows()):
        for feature in top_feature_names:
            idx = feature_index[feature]
            beeswarm.append(
                {
                    "index": _json_ready(row_index),
                    "feature": feature,
                    "feature_value": _json_ready(row.iloc[idx]),
                    "shap_value": _clean_metric(signed_values[row_position, idx]),
                }
            )
    base_values = np.asarray(getattr(values, "base_values", np.array([])))
    if base_values.ndim == 2:
        selected_base = base_values[:, output_index or 0]
    elif base_values.ndim == 1:
        selected_base = base_values
    else:
        selected_base = np.full(sample.shape[0], np.nan)
    records = []
    for row_position, (row_index, row) in enumerate(sample.iterrows()):
        contributions = []
        for idx, feature in enumerate(sample.columns):
            shap_value = signed_values[row_position, idx]
            contributions.append(
                {
                    "feature": feature,
                    "feature_value": _json_ready(row.iloc[idx]),
                    "shap_value": _clean_metric(shap_value),
                    "direction": "positive" if shap_value >= 0 else "negative",
                }
            )
        contributions = sorted(contributions, key=lambda item: abs(float(item.get("shap_value") or 0)), reverse=True)[:12]
        base_value = selected_base[row_position] if row_position < len(selected_base) else None
        records.append(
            {
                "index": _json_ready(row_index),
                "base_value": _clean_metric(base_value),
                "shap_sum": _clean_metric(np.nansum(signed_values[row_position, :])),
                "top_contributions": contributions,
            }
        )
    return {
        "top_features": top_features,
        "beeswarm": beeswarm,
        "records": records,
        "output_index": output_index,
        "notes": ["SHAP values are computed on the transformed feature space used by the estimator."],
    }


def _prediction_sample(X_test: pd.DataFrame, y_test: pd.Series, predictions: Any, proba: Any, *, class_labels: list[str], limit: int) -> list[dict[str, Any]]:
    rows = []
    for offset, (index, actual) in enumerate(y_test.head(limit).items()):
        prediction = predictions[offset]
        row = {"index": _json_ready(index), "actual": _json_ready(actual), "prediction": _json_ready(prediction)}
        try:
            residual = float(prediction) - float(actual)
            if np.isfinite(residual):
                row["residual"] = _clean_metric(residual)
                row["absolute_error"] = _clean_metric(abs(residual))
        except Exception:
            pass
        if proba is not None:
            probabilities = proba[offset]
            row["probabilities"] = {
                class_labels[i] if i < len(class_labels) else str(i): _clean_metric(value)
                for i, value in enumerate(probabilities)
            }
        rows.append(row)
    return rows


def _datetime_features(frame: Any) -> np.ndarray:
    data = pd.DataFrame(frame).copy()
    parts = []
    for column in data.columns:
        try:
            values = pd.to_datetime(data[column], errors="coerce", format="mixed")
        except TypeError:
            values = pd.to_datetime(data[column], errors="coerce")
        parts.append(pd.DataFrame({
            f"{column}_year": values.dt.year,
            f"{column}_month": values.dt.month,
            f"{column}_day": values.dt.day,
            f"{column}_weekday": values.dt.weekday,
        }, index=data.index))
    return pd.concat(parts, axis=1).to_numpy(dtype=float) if parts else np.empty((len(data), 0))


def _datetime_feature_names(transformer: Any, input_features: Any = None) -> np.ndarray:
    features = list(input_features or [])
    names = []
    for feature in features:
        names.extend([f"{feature}_year", f"{feature}_month", f"{feature}_day", f"{feature}_weekday"])
    return np.asarray(names, dtype=object)


def _scaler(name: str) -> Any:
    if name == "standard":
        from sklearn.preprocessing import StandardScaler

        return StandardScaler()
    if name == "minmax":
        from sklearn.preprocessing import MinMaxScaler

        return MinMaxScaler()
    if name == "robust":
        from sklearn.preprocessing import RobustScaler

        return RobustScaler()
    return None


def _default_param_grids() -> dict[str, dict[str, list[Any]]]:
    return {
        "random_forest": {"n_estimators": [80, 160], "max_depth": [None, 6], "min_samples_leaf": [1, 3]},
        "xgboost": {"n_estimators": [60, 120], "max_depth": [3, 5], "learning_rate": [0.05, 0.1]},
        "knn": {"n_neighbors": [3, 5, 9], "weights": ["uniform", "distance"]},
        "linear": {"alpha": [0.1, 1.0, 10.0], "C": [0.3, 1.0, 3.0]},
    }


def _default_param_grid(estimator: str, task: str) -> dict[str, list[Any]]:
    if estimator == "linear" and task in {"binary_classification", "multiclass_classification"}:
        return {"C": [0.3, 1.0, 3.0]}
    if estimator == "linear":
        return {"alpha": [0.1, 1.0, 10.0]}
    return _default_param_grids().get(estimator, {})


def _normalize_param_grid(grid: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key, value in dict(grid or {}).items():
        prefixed = key if key.startswith("model__") else f"model__{key}"
        normalized[prefixed] = value if isinstance(value, list) else [value]
    return normalized


def _unprefix_params(params: dict[str, Any]) -> dict[str, Any]:
    return {str(key).removeprefix("model__"): _json_ready(value) for key, value in dict(params or {}).items()}


def _infer_experiment_task(profile: Profile, target: str | None) -> str:
    if not target:
        return "clustering"
    if profile.target_profile and profile.target_profile.column == target:
        return profile.target_profile.task
    if target in profile.column_profiles:
        column = profile.column(target)
        if column.semantic_type in _NUMERIC_FEATURE_TYPES and column.distinct_count > 10:
            return "regression"
        if column.distinct_count <= 2:
            return "binary_classification"
    return "multiclass_classification"


def _float_setting(value: Any, default: float) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _int_setting(value: Any, default: int) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except Exception:
        return default


def _bool_setting(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _clean_metric(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if not np.isfinite(value):
            return None
        return round(value, 6)
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_ready(item) for item in value.tolist()]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_ready(value.item())
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


__all__ = [
    "ModelingAction",
    "ModelingExperimentResult",
    "ModelingExperimentSpec",
    "ModelingPlan",
    "build_modeling_plan",
    "default_modeling_experiment_spec",
    "modeling_experiment_catalog",
    "normalize_modeling_experiment_spec",
    "run_modeling_experiment",
]
