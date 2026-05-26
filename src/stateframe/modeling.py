"""Previewable modeling-readiness plans."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
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
    assessment: dict[str, Any] = field(default_factory=dict)
    holdout: dict[str, Any] = field(default_factory=dict)
    cross_validation: dict[str, Any] = field(default_factory=dict)
    search: dict[str, Any] = field(default_factory=dict)
    feature_importance: list[dict[str, Any]] = field(default_factory=list)
    explanation: dict[str, Any] = field(default_factory=dict)
    predictions: list[dict[str, Any]] = field(default_factory=list)
    preprocessing: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fitted_pipeline: Any | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "task": self.task,
            "estimator": self.estimator,
            "target": self.target,
            "row_count": int(self.row_count),
            "feature_count": int(self.feature_count),
            "metrics": _json_ready(self.metrics),
            "assessment": _json_ready(self.assessment),
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
            "assessment": self.assessment,
            "best_params": self.search.get("best_params"),
            "explanation_method": self.explanation.get("method"),
        }


@dataclass
class ModelingExperimentSuiteResult:
    """Serializable comparison of multiple named modeling experiment candidates."""

    base_spec: ModelingExperimentSpec
    runs: list[ModelingExperimentResult] = field(default_factory=list)
    comparison: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_spec": self.base_spec.to_dict(),
            "runs": [run.to_dict() for run in self.runs],
            "comparison": _json_ready(self.comparison),
            "errors": _json_ready(self.errors),
            "warnings": list(self.warnings),
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
            {"id": "baseline", "label": "Baseline", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": False},
            {"id": "random_forest", "label": "Random forest", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": False},
            {"id": "extra_trees", "label": "Extra trees", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": False},
            {"id": "gradient_boosting", "label": "Gradient boosting", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": False},
            {"id": "xgboost", "label": "XGBoost", "tasks": ["regression", "binary_classification", "multiclass_classification"], "optional": True, "scaling": False},
            {"id": "knn", "label": "K-nearest neighbors", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": True},
            {"id": "linear", "label": "Linear / logistic", "tasks": ["regression", "binary_classification", "multiclass_classification"], "scaling": True},
            {"id": "polynomial", "label": "Polynomial ridge", "tasks": ["regression"], "scaling": True},
            {"id": "kmeans", "label": "K-means", "tasks": ["clustering"], "scaling": True},
            {"id": "agglomerative", "label": "Agglomerative clustering", "tasks": ["clustering"], "scaling": True},
            {"id": "dbscan", "label": "DBSCAN", "tasks": ["clustering"], "scaling": True},
        ],
        "comparison_candidates": _default_comparison_candidate_catalog(),
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


def run_modeling_experiment_suite(
    profile: Profile,
    spec: ModelingExperimentSpec | dict[str, Any] | None = None,
    *,
    candidates: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> ModelingExperimentSuiteResult:
    """Run a set of named experiment candidates and rank their results."""

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
    selected_candidates = candidates or default_modeling_comparison_candidates(task)
    runs: list[ModelingExperimentResult] = []
    errors: list[dict[str, Any]] = []
    for position, candidate in enumerate(selected_candidates):
        candidate_payload = _normalize_experiment_candidate(candidate, position=position, task=task)
        candidate_spec = _candidate_experiment_spec(base, candidate_payload)
        try:
            result = run_modeling_experiment(profile, candidate_spec)
            result = replace(
                result,
                search={
                    **dict(result.search or {}),
                    "candidate_id": candidate_payload["id"],
                    "candidate_label": candidate_payload["label"],
                    "candidate_notes": candidate_payload.get("notes") or "",
                },
            )
            runs.append(result)
        except Exception as exc:
            errors.append(
                {
                    "candidate_id": candidate_payload["id"],
                    "candidate_label": candidate_payload["label"],
                    "estimator": candidate_payload.get("estimator"),
                    "error": str(exc),
                }
            )
    comparison = _modeling_comparison(runs, errors)
    warnings = []
    if not runs:
        warnings.append("No comparison candidates completed successfully.")
    if errors:
        warnings.append(f"{len(errors)} comparison candidate(s) failed.")
    return ModelingExperimentSuiteResult(
        base_spec=base,
        runs=runs,
        comparison=comparison,
        errors=errors,
        warnings=warnings,
    )


def build_modeling_artifact(
    result: ModelingExperimentResult,
    *,
    profile: Profile | None = None,
    entry_label: str | None = None,
    base_path: str | Path | None = None,
    persist_model: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Build a durable ledger-ready artifact for a modeling experiment."""

    artifact = _modeling_artifact_payload(result)
    if persist_model:
        artifact = _persist_modeling_artifact_files(
            artifact,
            result,
            profile=profile,
            entry_label=entry_label or artifact["title"],
            base_path=base_path,
        )
    summary = {
        "artifact_kind": "model",
        "task": result.task,
        "estimator": result.estimator,
        "target": result.target,
        "row_count": int(result.row_count),
        "feature_count": int(result.feature_count),
        "metrics": _json_ready(result.metrics),
        "primary_metric": _json_ready((result.assessment or {}).get("primary_metric")),
        "rating": (result.assessment or {}).get("rating"),
        "warning_count": len(result.warnings),
        "saved": bool(artifact.get("saved")),
    }
    return artifact, summary, _modeling_replay_code(result.spec)


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
    warnings.extend(_preflight_supervised_experiment(profile, spec, task=task, X=X_raw, y=y))

    estimator_id = _supervised_estimator_id(spec.estimator, warnings=warnings)
    estimator_params = _clean_estimator_params(spec.estimator_params)
    estimator = _build_estimator(estimator_id, task=task, random_state=spec.random_state, params=estimator_params)
    preprocessor, preprocessing_summary = _build_preprocessor(X_raw, feature_roles, spec, estimator_id=estimator_id)
    pipeline = _build_supervised_pipeline(
        preprocessor,
        estimator,
        estimator_id=estimator_id,
        estimator_params=estimator_params,
    )

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
        grid = _normalize_param_grid((spec.search or {}).get("param_grid") or _default_param_grid(estimator_id, task), estimator_id=estimator_id)
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
    holdout = {
        **holdout,
        "prediction_audit": _prediction_audit_records(
            frame,
            y_test,
            predictions,
            class_labels=class_labels,
            task=task,
            limit=12,
        ),
    }

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
    feature_lineage = _feature_lineage(feature_names, feature_roles)
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
    source_importance = _source_feature_importance(
        explanation.get("top_features") or feature_importance,
        feature_lineage,
    )
    if source_importance:
        explanation = {**explanation, "source_features": source_importance}

    prediction_rows = _prediction_sample(
        X_test,
        y_test,
        predictions,
        proba,
        class_labels=class_labels,
        limit=25,
    )
    metrics = dict(holdout.get("metrics") or {})
    assessment = _model_assessment(
        task=task,
        metrics=metrics,
        warnings=warnings,
        row_count=int(X_raw.shape[0]),
        feature_count=int(len(feature_names)),
        cross_validation=cv_summary,
        search=search_summary,
    )
    return ModelingExperimentResult(
        spec=spec,
        task=task,
        estimator=estimator_id,
        target=target,
        row_count=int(X_raw.shape[0]),
        feature_count=int(len(feature_names)),
        metrics=metrics,
        assessment=assessment,
        holdout=holdout,
        cross_validation=cv_summary,
        search=search_summary,
        feature_importance=feature_importance,
        explanation=explanation,
        predictions=prediction_rows,
        preprocessing={
            **preprocessing_summary,
            "feature_roles": feature_roles,
            "feature_lineage": feature_lineage,
            "source_feature_count": len({row["source_column"] for row in feature_lineage}),
        },
        warnings=warnings,
        fitted_pipeline=fitted,
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
    feature_lineage = _feature_lineage(feature_names, feature_roles)
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
    assessment = _model_assessment(
        task="clustering",
        metrics=metrics,
        warnings=warnings,
        row_count=int(X_raw.shape[0]),
        feature_count=int(len(feature_names)),
        cross_validation={"enabled": False},
        search={"enabled": False},
    )
    return ModelingExperimentResult(
        spec=spec,
        task="clustering",
        estimator=estimator_id,
        target=None,
        row_count=int(X_raw.shape[0]),
        feature_count=int(len(feature_names)),
        metrics=metrics,
        assessment=assessment,
        holdout={},
        cross_validation={"enabled": False},
        search={"enabled": False},
        feature_importance=importance,
        explanation={
            "enabled": True,
            "method": "cluster_profile",
            "top_features": importance[:20],
            "source_features": _source_feature_importance(importance, feature_lineage),
            "notes": ["Cluster observability is based on between-cluster mean separation per transformed feature."],
        },
        predictions=predictions,
        preprocessing={
            **preprocessing_summary,
            "feature_roles": feature_roles,
            "feature_lineage": feature_lineage,
            "source_feature_count": len({row["source_column"] for row in feature_lineage}),
        },
        warnings=warnings,
        fitted_pipeline=pipeline,
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
    manual_features = spec.features is not None
    requested = []
    missing_requested = []
    for column in spec.features or []:
        if column in {None, ""}:
            continue
        name = str(column)
        if name not in data.columns:
            missing_requested.append(name)
            continue
        if name == exclude_target:
            warnings.append(f"Skipped selected feature because it is the target column: {name}")
            continue
        if _looks_like_target_leakage(name, exclude_target) and not _bool_setting((spec.preprocessing or {}).get("allow_target_derived_features"), False):
            warnings.append(f"Skipped likely target-derived selected feature column: {name}")
            continue
        requested.append(name)
    if missing_requested:
        warnings.append("Skipped missing selected feature columns: " + ", ".join(missing_requested[:8]))
    if manual_features:
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


def _preflight_supervised_experiment(
    profile: Profile,
    spec: ModelingExperimentSpec,
    *,
    task: str,
    X: pd.DataFrame,
    y: pd.Series,
) -> list[str]:
    warnings: list[str] = []
    if X.empty:
        warnings.append("No usable features were available after feature filtering.")
        return warnings
    split = dict(spec.split or {})
    test_size = _float_setting(split.get("test_size"), 0.25)
    if test_size <= 0 or test_size >= 1:
        warnings.append(f"Test size {test_size} is outside (0, 1); sklearn may reject this split.")
    if X.shape[0] < 20:
        warnings.append(f"Only {X.shape[0]:,} labeled rows are available for this experiment.")
    if len(X.columns) > max(1, X.shape[0] * 2):
        warnings.append("Feature count is very high relative to row count; validation metrics may be unstable.")
    if spec.features:
        selected = [str(item) for item in spec.features if item not in {None, ""}]
        skipped = [item for item in selected if item not in X.columns]
        if skipped:
            warnings.append(f"{len(skipped)} selected feature(s) were not modeled after validation/filtering.")
    validation = dict(spec.validation or {})
    cv_folds = _int_setting(validation.get("cv_folds"), 5)
    if str(validation.get("strategy") or "holdout") in {"cross_validation", "holdout_and_cv"} and cv_folds > X.shape[0]:
        warnings.append(f"CV folds were requested as {cv_folds}, more than the available labeled rows.")
    if task in {"binary_classification", "multiclass_classification"}:
        counts = y.value_counts(dropna=False)
        if counts.shape[0] < 2:
            warnings.append("The target has fewer than two classes after dropping missing target rows.")
        elif int(counts.min()) < 2:
            warnings.append("At least one target class has fewer than two rows; stratified validation may be skipped.")
        imbalance = float(counts.max() / max(1, counts.sum())) if counts.sum() else 0.0
        if imbalance >= 0.9:
            warnings.append(f"The largest target class is {imbalance:.1%} of labeled rows; accuracy can be misleading.")
    target = spec.target
    if target and target in profile.data.columns:
        suspicious = [
            column
            for column in X.columns
            if _looks_like_target_leakage(str(column), str(target))
        ]
        if suspicious:
            warnings.append("Modeled features still include likely target-derived columns: " + ", ".join(suspicious[:8]))
    return warnings


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


def _build_supervised_pipeline(
    preprocessor: Any,
    estimator: Any,
    *,
    estimator_id: str,
    estimator_params: dict[str, Any],
):
    from sklearn.pipeline import Pipeline

    steps: list[tuple[str, Any]] = [("preprocess", preprocessor)]
    if estimator_id == "polynomial":
        from sklearn.preprocessing import PolynomialFeatures

        degree = max(2, min(4, _int_setting(estimator_params.get("degree"), 2)))
        steps.append(
            (
                "polynomial",
                PolynomialFeatures(
                    degree=degree,
                    include_bias=_bool_setting(estimator_params.get("include_bias"), False),
                    interaction_only=_bool_setting(estimator_params.get("interaction_only"), False),
                ),
            )
        )
    steps.append(("model", estimator))
    return Pipeline(steps)


def _supervised_estimator_id(estimator_id: str, *, warnings: list[str]) -> str:
    estimator_id = str(estimator_id or "random_forest")
    if estimator_id in {"baseline", "random_forest", "extra_trees", "gradient_boosting", "xgboost", "knn", "linear", "polynomial"}:
        return estimator_id
    warnings.append(f"Estimator {estimator_id} is not available for supervised modeling; using random_forest.")
    return "random_forest"


def _build_estimator(estimator_id: str, *, task: str, random_state: int, params: dict[str, Any]):
    is_classification = task in {"binary_classification", "multiclass_classification"}
    params = _clean_estimator_params(params)
    if estimator_id == "baseline":
        if is_classification:
            from sklearn.dummy import DummyClassifier

            return DummyClassifier(strategy=str(params.get("strategy") or "most_frequent"), random_state=random_state)
        from sklearn.dummy import DummyRegressor

        return DummyRegressor(strategy=str(params.get("strategy") or "mean"))
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
    if estimator_id == "polynomial":
        from sklearn.linear_model import Ridge

        ridge_params = {key: value for key, value in params.items() if key not in {"degree", "interaction_only", "include_bias", "order"}}
        return Ridge(random_state=random_state, **ridge_params)
    if estimator_id == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor

        defaults = {"n_estimators": 120, "learning_rate": 0.06, "max_depth": 3, "random_state": random_state}
        return (GradientBoostingClassifier if is_classification else GradientBoostingRegressor)(**{**defaults, **params})
    if estimator_id == "extra_trees":
        from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor

        defaults = {"n_estimators": 180, "min_samples_leaf": 2, "random_state": random_state, "n_jobs": -1}
        return (ExtraTreesClassifier if is_classification else ExtraTreesRegressor)(**{**defaults, **params})
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

    defaults = {"n_estimators": 160, "min_samples_leaf": 2, "random_state": random_state, "n_jobs": -1}
    return (RandomForestClassifier if is_classification else RandomForestRegressor)(**{**defaults, **params})


def _clean_estimator_params(params: dict[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in dict(params or {}).items():
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            coerced = _coerce_estimator_param(text)
            if coerced is None:
                continue
            cleaned[str(key)] = coerced
        else:
            cleaned[str(key)] = value
    return cleaned


def _coerce_estimator_param(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null"}:
        return None
    try:
        number = float(value)
    except Exception:
        return value
    return int(number) if number.is_integer() else number


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
    diagnostics = _regression_diagnostics(y_true, predictions)
    metrics = {
        "mae": _clean_metric(mae),
        "rmse": _clean_metric(float(np.sqrt(mse))),
        "r2": _clean_metric(metric_funcs["r2_score"](y_true, predictions)),
        "median_absolute_error": diagnostics["residual_summary"].get("median_absolute_error"),
        "bias_mean": diagnostics["residual_summary"].get("mean_residual"),
    }
    return {"metrics": metrics, **diagnostics}


def _regression_diagnostics(y_true: pd.Series, predictions: Any) -> dict[str, Any]:
    actual = pd.to_numeric(y_true, errors="coerce")
    predicted = pd.Series(predictions, index=y_true.index, name="prediction")
    predicted = pd.to_numeric(predicted, errors="coerce")
    frame = pd.DataFrame({"actual": actual, "prediction": predicted}).dropna()
    if frame.empty:
        return {"residual_summary": {}, "worst_predictions": [], "residual_bins": []}
    frame["residual"] = frame["prediction"] - frame["actual"]
    frame["absolute_error"] = frame["residual"].abs()
    non_zero = frame["actual"].abs() > 0
    frame["absolute_percentage_error"] = np.nan
    frame.loc[non_zero, "absolute_percentage_error"] = frame.loc[non_zero, "absolute_error"] / frame.loc[non_zero, "actual"].abs()
    residual = frame["residual"]
    absolute_error = frame["absolute_error"]
    summary = {
        "mean_residual": _clean_metric(residual.mean()),
        "median_residual": _clean_metric(residual.median()),
        "residual_std": _clean_metric(residual.std(ddof=0)),
        "median_absolute_error": _clean_metric(absolute_error.median()),
        "p90_absolute_error": _clean_metric(absolute_error.quantile(0.9)),
        "max_absolute_error": _clean_metric(absolute_error.max()),
        "mean_absolute_percentage_error": _clean_metric(frame["absolute_percentage_error"].mean()),
        "over_prediction_rate": _clean_metric((residual > 0).mean()),
        "within_10pct_rate": _clean_metric((frame["absolute_percentage_error"] <= 0.10).mean()) if non_zero.any() else None,
        "within_20pct_rate": _clean_metric((frame["absolute_percentage_error"] <= 0.20).mean()) if non_zero.any() else None,
    }
    bins = _residual_bins(residual, bin_count=12)
    worst = []
    for index, row in frame.sort_values("absolute_error", ascending=False).head(15).iterrows():
        worst.append(
            {
                "index": _json_ready(index),
                "actual": _clean_metric(row["actual"]),
                "prediction": _clean_metric(row["prediction"]),
                "residual": _clean_metric(row["residual"]),
                "absolute_error": _clean_metric(row["absolute_error"]),
                "absolute_percentage_error": _clean_metric(row["absolute_percentage_error"]),
            }
        )
    return {
        "residual_summary": summary,
        "worst_predictions": worst,
        "residual_bins": bins,
    }


def _residual_bins(values: pd.Series, *, bin_count: int) -> list[dict[str, Any]]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return []
    minimum = float(clean.min())
    maximum = float(clean.max())
    if minimum == maximum:
        return [{"start": _clean_metric(minimum), "end": _clean_metric(maximum), "count": int(clean.shape[0])}]
    counts, edges = np.histogram(clean.to_numpy(dtype=float), bins=max(2, int(bin_count)))
    return [
        {
            "start": _clean_metric(edges[index]),
            "end": _clean_metric(edges[index + 1]),
            "count": int(count),
        }
        for index, count in enumerate(counts)
    ]


def _prediction_audit_records(
    source_frame: pd.DataFrame,
    y_test: pd.Series,
    predictions: Any,
    *,
    class_labels: list[str],
    task: str,
    limit: int,
) -> list[dict[str, Any]]:
    prediction_series = pd.Series(predictions, index=y_test.index, name="prediction")
    rows = []
    if task == "regression":
        actual = pd.to_numeric(y_test, errors="coerce")
        predicted = pd.to_numeric(prediction_series, errors="coerce")
        audit = pd.DataFrame({"actual": actual, "prediction": predicted}).dropna()
        if audit.empty:
            return []
        audit["residual"] = audit["prediction"] - audit["actual"]
        audit["absolute_error"] = audit["residual"].abs()
        selected = audit.sort_values("absolute_error", ascending=False).head(limit)
        for index, row in selected.iterrows():
            rows.append(
                {
                    "index": _json_ready(index),
                    "actual": _clean_metric(row["actual"]),
                    "prediction": _clean_metric(row["prediction"]),
                    "residual": _clean_metric(row["residual"]),
                    "absolute_error": _clean_metric(row["absolute_error"]),
                    "record": _source_record(source_frame, index),
                }
            )
        return rows

    errors = prediction_series[prediction_series != y_test].head(limit)
    selected = errors if not errors.empty else prediction_series.head(limit)
    for index, prediction in selected.items():
        actual = y_test.loc[index]
        rows.append(
            {
                "index": _json_ready(index),
                "actual": _label_value(actual, class_labels),
                "prediction": _label_value(prediction, class_labels),
                "correct": bool(prediction == actual),
                "record": _source_record(source_frame, index),
            }
        )
    return rows


def _source_record(frame: pd.DataFrame, index: Any, *, limit: int = 40) -> dict[str, Any]:
    try:
        row = frame.loc[index]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
    except Exception:
        return {}
    values = row.to_dict() if hasattr(row, "to_dict") else {}
    return {str(key): _json_ready(value) for key, value in list(values.items())[:limit]}


def _model_assessment(
    *,
    task: str,
    metrics: dict[str, Any],
    warnings: list[str],
    row_count: int,
    feature_count: int,
    cross_validation: dict[str, Any],
    search: dict[str, Any],
) -> dict[str, Any]:
    primary_key = _primary_metric_key(task, metrics)
    primary_value = metrics.get(primary_key) if primary_key else None
    direction = "lower_is_better" if primary_key in {"mae", "rmse", "median_absolute_error", "bias_mean", "inertia", "davies_bouldin"} else "higher_is_better"
    rating = _model_rating(task, primary_key, primary_value)
    suggestions = _model_suggestions(
        task=task,
        metrics=metrics,
        warnings=warnings,
        row_count=row_count,
        feature_count=feature_count,
        cross_validation=cross_validation,
        search=search,
        rating=rating,
    )
    return {
        "rating": rating,
        "primary_metric": {
            "key": primary_key,
            "value": _clean_metric(primary_value),
            "direction": direction,
        },
        "summary": _model_assessment_summary(task, rating, primary_key, primary_value),
        "suggestions": suggestions,
        "warning_count": len(warnings or []),
    }


def _primary_metric_key(task: str, metrics: dict[str, Any]) -> str:
    preferred = {
        "regression": ["r2", "mae", "rmse"],
        "binary_classification": ["roc_auc", "f1", "accuracy"],
        "multiclass_classification": ["roc_auc_ovr", "f1", "accuracy"],
        "clustering": ["silhouette", "calinski_harabasz", "cluster_count"],
    }.get(task, [])
    for key in preferred:
        if metrics.get(key) is not None:
            return key
    return next((key for key, value in metrics.items() if not isinstance(value, (dict, list)) and value is not None), "")


def _model_rating(task: str, key: str, value: Any) -> str:
    try:
        score = float(value)
    except Exception:
        return "needs_review" if task != "clustering" else "exploratory"
    if task == "regression" and key == "r2":
        if score >= 0.75:
            return "strong"
        if score >= 0.4:
            return "promising"
        if score >= 0:
            return "weak"
        return "poor"
    if task in {"binary_classification", "multiclass_classification"}:
        if score >= 0.85:
            return "strong"
        if score >= 0.7:
            return "promising"
        if score >= 0.55:
            return "weak"
        return "poor"
    if task == "clustering" and key == "silhouette":
        if score >= 0.5:
            return "strong"
        if score >= 0.25:
            return "promising"
        return "exploratory"
    return "needs_review"


def _model_assessment_summary(task: str, rating: str, key: str, value: Any) -> str:
    metric = f"{key}={_clean_metric(value)}" if key else "no primary metric"
    if task == "clustering":
        return f"Cluster run is {rating}; review segment sizes and source-column separation ({metric})."
    return f"Model run is {rating}; use holdout diagnostics and feature lineage before trusting it ({metric})."


def _model_suggestions(
    *,
    task: str,
    metrics: dict[str, Any],
    warnings: list[str],
    row_count: int,
    feature_count: int,
    cross_validation: dict[str, Any],
    search: dict[str, Any],
    rating: str,
) -> list[str]:
    suggestions: list[str] = []
    if warnings:
        suggestions.append("Resolve or consciously accept the run warnings before treating the model as reliable.")
    if row_count < 200:
        suggestions.append("Use more labeled rows when possible; small holdouts can swing metrics heavily.")
    if feature_count > max(10, row_count):
        suggestions.append("Reduce or group sparse features; the transformed feature count is high for the available rows.")
    if task == "regression":
        r2 = _metric_number(metrics.get("r2"))
        if r2 is not None and r2 < 0.4:
            suggestions.append("Inspect residual records and try nonlinear/tree estimators, target transforms, or better location/time features.")
        bias = _metric_number(metrics.get("bias_mean"))
        if bias is not None and abs(bias) > 0:
            suggestions.append("Check the mean residual for systematic over- or under-prediction.")
    elif task in {"binary_classification", "multiclass_classification"}:
        f1 = _metric_number(metrics.get("f1"))
        if f1 is not None and f1 < 0.7:
            suggestions.append("Review confusion-matrix misses and consider class balance, thresholding, or stronger features.")
    elif task == "clustering":
        if metrics.get("silhouette") is None:
            suggestions.append("Try different cluster counts or DBSCAN settings; this run did not produce a stable separation metric.")
        suggestions.append("Profile each cluster against source columns before using labels downstream.")
    if not search.get("enabled") and rating in {"weak", "poor", "needs_review", "exploratory"}:
        suggestions.append("Run grid search or compare another estimator before saving this as the preferred model.")
    cv_scores = (cross_validation or {}).get("scores") or {}
    if cv_scores:
        suggestions.append("Compare holdout metrics with cross-validation means; large gaps are a sign of split sensitivity.")
    return suggestions[:6]


def _metric_number(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


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
    names = _preprocessor_feature_names(preprocessor, X)
    if "polynomial" in getattr(pipeline, "named_steps", {}):
        try:
            names = [str(name) for name in pipeline.named_steps["polynomial"].get_feature_names_out(names)]
        except Exception:
            pass
    width = _estimator_input_width(pipeline, X)
    if not width or len(names) == width:
        return names
    return [f"feature_{index}" for index in range(width)]


def _preprocessor_feature_names(preprocessor: Any, X: pd.DataFrame) -> list[str]:
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


def _estimator_input_width(pipeline: Any, X: pd.DataFrame) -> int:
    try:
        transformed = pipeline[:-1].transform(X.head(2))
        return int(transformed.shape[1])
    except Exception:
        try:
            transformed = pipeline.named_steps["preprocess"].transform(X.head(2))
            return int(transformed.shape[1])
        except Exception:
            return 0


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
        if str(transformer_name) == "datetime":
            date_names = [
                f"{name}_{part}"
                for name in input_names
                for part in ("year", "month", "day", "weekday")
            ]
            width = _transformer_width(transformer, X, input_names)
            if width == len(date_names):
                names.extend(date_names)
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
    try:
        transformed = pipeline[:-1].transform(X)
    except Exception:
        transformed = pipeline.named_steps["preprocess"].transform(X)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    return pd.DataFrame(transformed, columns=feature_names, index=X.index)


def _feature_lineage(feature_names: list[str], feature_roles: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    sources = sorted(feature_roles, key=len, reverse=True)
    for feature in feature_names:
        source = _source_for_transformed_feature(str(feature), sources)
        role = feature_roles.get(source, "derived")
        rows.append(
            {
                "feature": str(feature),
                "source_column": source,
                "role": role,
                "transform": _feature_transform_label(str(feature), source, role),
            }
        )
    return rows


def _source_for_transformed_feature(feature: str, sources: list[str]) -> str:
    if feature in sources:
        return feature
    for source in sources:
        if feature.startswith(f"{source}_") or feature.startswith(f"{source}="):
            return source
    compact_feature = "".join(char for char in feature.lower() if char.isalnum())
    for source in sources:
        compact_source = "".join(char for char in source.lower() if char.isalnum())
        if compact_source and compact_feature.startswith(compact_source):
            return source
    return feature


def _feature_transform_label(feature: str, source: str, role: str) -> str:
    if "^" in feature or " " in feature:
        return "polynomial_feature"
    if role == "datetime" and feature != source:
        return "date_features"
    if role == "categorical" and feature != source:
        return "encoded_category"
    if role == "numeric":
        return "numeric_pipeline"
    return role or "derived"


def _source_feature_importance(rows: list[dict[str, Any]], lineage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lineage_by_feature = {row["feature"]: row for row in lineage}
    totals: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        feature = str(row.get("feature") or "")
        if not feature:
            continue
        value = row.get("mean_abs_shap", row.get("permutation_importance", row.get("importance", row.get("cluster_separation", 0))))
        try:
            score = abs(float(value or 0))
        except Exception:
            score = 0.0
        source = lineage_by_feature.get(feature, {}).get("source_column") or feature
        item = totals.setdefault(str(source), {"source_column": str(source), "importance": 0.0, "feature_count": 0})
        item["importance"] += score
        item["feature_count"] += 1
    result = [
        {
            "source_column": source,
            "importance": _clean_metric(item["importance"]),
            "feature_count": int(item["feature_count"]),
        }
        for source, item in totals.items()
    ]
    return sorted(result, key=lambda item: float(item.get("importance") or 0), reverse=True)[:50]


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


def _modeling_artifact_payload(result: ModelingExperimentResult) -> dict[str, Any]:
    title = f"{result.estimator} {result.task}".strip()
    if result.target:
        title = f"{title} for {result.target}"
    payload = result.to_dict()
    return {
        "kind": "model",
        "artifact_kind": "modeling_experiment",
        "title": title,
        "task": result.task,
        "estimator": result.estimator,
        "target": result.target,
        "metrics": _json_ready(result.metrics),
        "assessment": _json_ready(result.assessment),
        "spec": payload.get("spec"),
        "result": payload,
        "warnings": list(result.warnings),
        "feature_lineage": _json_ready((result.preprocessing or {}).get("feature_lineage") or []),
    }


def _persist_modeling_artifact_files(
    artifact: dict[str, Any],
    result: ModelingExperimentResult,
    *,
    profile: Profile | None,
    entry_label: str,
    base_path: str | Path | None,
) -> dict[str, Any]:
    from stateframe import workspace

    current_workspace = workspace.current()
    root = Path(base_path) if base_path is not None else current_workspace.root / "stateframe_saves"
    tree_id = current_workspace.tree_id_for_profile(profile) if profile is not None else "floating"
    output_dir = root / _artifact_slug(tree_id) / _artifact_slug(entry_label)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[dict[str, Any]] = []
    payload = result.to_dict()
    result_path = output_dir / "model_result.json"
    result_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    saved_files.append(_artifact_file_record(current_workspace.root, result_path, kind="model_result", format="json"))

    predictions = pd.DataFrame(result.predictions or [])
    if not predictions.empty:
        predictions_path = output_dir / "prediction_sample.csv"
        predictions.to_csv(predictions_path, index=False)
        saved_files.append(_artifact_file_record(current_workspace.root, predictions_path, kind="predictions", format="csv"))

    lineage = pd.DataFrame((result.preprocessing or {}).get("feature_lineage") or [])
    if not lineage.empty:
        lineage_path = output_dir / "feature_lineage.csv"
        lineage.to_csv(lineage_path, index=False)
        saved_files.append(_artifact_file_record(current_workspace.root, lineage_path, kind="feature_lineage", format="csv"))

    if result.fitted_pipeline is not None:
        try:
            import joblib

            model_path = output_dir / "model.joblib"
            joblib.dump(result.fitted_pipeline, model_path)
            artifact["model_path"] = _display_artifact_path(current_workspace.root, model_path)
            saved_files.append(_artifact_file_record(current_workspace.root, model_path, kind="model_pipeline", format="joblib"))
        except Exception as exc:
            artifact.setdefault("persist_warnings", []).append(f"Model pipeline persistence failed: {exc}")

    manifest = {
        "kind": "stateframe_artifact_manifest",
        "artifact_kind": artifact.get("kind"),
        "title": artifact.get("title"),
        "files": saved_files,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    saved_files.append(_artifact_file_record(current_workspace.root, manifest_path, kind="manifest", format="json"))

    result_artifact = dict(artifact)
    result_artifact["saved"] = True
    result_artifact["save_dir"] = _display_artifact_path(current_workspace.root, output_dir)
    result_artifact["result_path"] = _display_artifact_path(current_workspace.root, result_path)
    result_artifact["saved_files"] = saved_files
    return result_artifact


def _modeling_replay_code(spec: ModelingExperimentSpec) -> str:
    return (
        "spec = "
        + repr(spec.to_dict())
        + "\n"
        + "result = sf.modeling_experiment(sf.pull(), spec)"
    )


def _artifact_slug(value: Any) -> str:
    text = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value or "").strip())
    text = "_".join(part for part in text.split("_") if part)
    return text[:80] or "artifact"


def _display_artifact_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def _artifact_file_record(root: Path, path: Path, *, kind: str, format: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "format": format,
        "path": _display_artifact_path(root, path),
        "bytes": int(path.stat().st_size) if path.exists() else 0,
    }


def _prediction_sample(X_test: pd.DataFrame, y_test: pd.Series, predictions: Any, proba: Any, *, class_labels: list[str], limit: int) -> list[dict[str, Any]]:
    rows = []
    for offset, (index, actual) in enumerate(y_test.head(limit).items()):
        prediction = predictions[offset]
        row = {
            "index": _json_ready(index),
            "actual": _label_value(actual, class_labels),
            "prediction": _label_value(prediction, class_labels),
        }
        if not class_labels:
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


def _label_value(value: Any, class_labels: list[str]) -> Any:
    if not class_labels:
        return _json_ready(value)
    try:
        index = int(value)
        if 0 <= index < len(class_labels):
            return class_labels[index]
    except Exception:
        pass
    return _json_ready(value)


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
        "baseline": {},
        "random_forest": {"n_estimators": [80, 160], "max_depth": [None, 6], "min_samples_leaf": [1, 3]},
        "extra_trees": {"n_estimators": [80, 160], "max_depth": [None, 8], "min_samples_leaf": [1, 3]},
        "gradient_boosting": {"n_estimators": [80, 160], "learning_rate": [0.04, 0.08], "max_depth": [2, 3]},
        "xgboost": {"n_estimators": [60, 120], "max_depth": [3, 5], "learning_rate": [0.05, 0.1]},
        "knn": {"n_neighbors": [3, 5, 9], "weights": ["uniform", "distance"]},
        "linear": {"alpha": [0.1, 1.0, 10.0], "C": [0.3, 1.0, 3.0]},
        "polynomial": {"degree": [2, 3], "alpha": [0.1, 1.0, 10.0]},
    }


def _default_param_grid(estimator: str, task: str) -> dict[str, list[Any]]:
    if estimator == "linear" and task in {"binary_classification", "multiclass_classification"}:
        return {"C": [0.3, 1.0, 3.0]}
    if estimator == "linear":
        return {"alpha": [0.1, 1.0, 10.0]}
    if estimator == "polynomial":
        return {"degree": [2, 3], "alpha": [0.1, 1.0, 10.0]}
    return _default_param_grids().get(estimator, {})


def _normalize_param_grid(grid: dict[str, Any], *, estimator_id: str | None = None) -> dict[str, Any]:
    normalized = {}
    for key, value in dict(grid or {}).items():
        if "__" in str(key):
            prefixed = str(key)
        elif estimator_id == "polynomial" and key in {"degree", "interaction_only", "include_bias", "order"}:
            prefixed = f"polynomial__{key}"
        else:
            prefixed = f"model__{key}"
        normalized[prefixed] = value if isinstance(value, list) else [value]
    return normalized


def _unprefix_params(params: dict[str, Any]) -> dict[str, Any]:
    return {str(key).removeprefix("model__").removeprefix("polynomial__"): _json_ready(value) for key, value in dict(params or {}).items()}


def _default_comparison_candidate_catalog() -> dict[str, list[dict[str, Any]]]:
    return {
        "regression": [
            {"id": "baseline_mean", "label": "Baseline mean", "estimator": "baseline", "estimator_params": {"strategy": "mean"}, "enabled_by_default": False},
            {"id": "linear_ridge", "label": "Linear ridge", "estimator": "linear", "estimator_params": {"alpha": 1.0}, "preprocessing": {"scaler": "standard"}},
            {"id": "polynomial_degree2", "label": "Polynomial ridge degree 2", "estimator": "polynomial", "estimator_params": {"degree": 2, "alpha": 1.0}, "preprocessing": {"scaler": "standard", "max_categories": 20}},
            {"id": "knn_7_distance", "label": "KNN distance k=7", "estimator": "knn", "estimator_params": {"n_neighbors": 7, "weights": "distance"}, "preprocessing": {"scaler": "standard"}},
            {"id": "random_forest_balanced", "label": "Random forest balanced", "estimator": "random_forest", "estimator_params": {"n_estimators": 160, "max_depth": 14, "min_samples_leaf": 3}},
            {"id": "random_forest_deep", "label": "Random forest deep", "estimator": "random_forest", "estimator_params": {"n_estimators": 220, "min_samples_leaf": 1}, "enabled_by_default": False},
            {"id": "extra_trees", "label": "Extra trees", "estimator": "extra_trees", "estimator_params": {"n_estimators": 180, "min_samples_leaf": 2}},
            {"id": "gradient_boosting", "label": "Gradient boosting", "estimator": "gradient_boosting", "estimator_params": {"n_estimators": 160, "learning_rate": 0.06, "max_depth": 3}},
            {"id": "xgboost_compact", "label": "XGBoost compact", "estimator": "xgboost", "estimator_params": {"n_estimators": 140, "max_depth": 4, "learning_rate": 0.06}, "enabled_by_default": False, "optional": True},
        ],
        "binary_classification": [
            {"id": "baseline_mode", "label": "Baseline mode", "estimator": "baseline", "estimator_params": {"strategy": "most_frequent"}, "enabled_by_default": False},
            {"id": "logistic", "label": "Logistic regression", "estimator": "linear", "estimator_params": {"C": 1.0}, "preprocessing": {"scaler": "standard"}},
            {"id": "knn_7_distance", "label": "KNN distance k=7", "estimator": "knn", "estimator_params": {"n_neighbors": 7, "weights": "distance"}, "preprocessing": {"scaler": "standard"}},
            {"id": "random_forest_balanced", "label": "Random forest balanced", "estimator": "random_forest", "estimator_params": {"n_estimators": 160, "max_depth": 12, "min_samples_leaf": 3}},
            {"id": "extra_trees", "label": "Extra trees", "estimator": "extra_trees", "estimator_params": {"n_estimators": 180, "min_samples_leaf": 2}},
            {"id": "gradient_boosting", "label": "Gradient boosting", "estimator": "gradient_boosting", "estimator_params": {"n_estimators": 120, "learning_rate": 0.06, "max_depth": 3}},
            {"id": "xgboost_compact", "label": "XGBoost compact", "estimator": "xgboost", "estimator_params": {"n_estimators": 120, "max_depth": 4, "learning_rate": 0.06}, "enabled_by_default": False, "optional": True},
        ],
        "multiclass_classification": [
            {"id": "baseline_mode", "label": "Baseline mode", "estimator": "baseline", "estimator_params": {"strategy": "most_frequent"}, "enabled_by_default": False},
            {"id": "logistic", "label": "Logistic regression", "estimator": "linear", "estimator_params": {"C": 1.0}, "preprocessing": {"scaler": "standard"}},
            {"id": "knn_7_distance", "label": "KNN distance k=7", "estimator": "knn", "estimator_params": {"n_neighbors": 7, "weights": "distance"}, "preprocessing": {"scaler": "standard"}},
            {"id": "random_forest_balanced", "label": "Random forest balanced", "estimator": "random_forest", "estimator_params": {"n_estimators": 160, "max_depth": 12, "min_samples_leaf": 3}},
            {"id": "extra_trees", "label": "Extra trees", "estimator": "extra_trees", "estimator_params": {"n_estimators": 180, "min_samples_leaf": 2}},
            {"id": "gradient_boosting", "label": "Gradient boosting", "estimator": "gradient_boosting", "estimator_params": {"n_estimators": 120, "learning_rate": 0.06, "max_depth": 3}},
            {"id": "xgboost_compact", "label": "XGBoost compact", "estimator": "xgboost", "estimator_params": {"n_estimators": 120, "max_depth": 4, "learning_rate": 0.06}, "enabled_by_default": False, "optional": True},
        ],
        "clustering": [
            {"id": "kmeans_3", "label": "K-means 3 clusters", "estimator": "kmeans", "clustering": {"n_clusters": 3}},
            {"id": "kmeans_5", "label": "K-means 5 clusters", "estimator": "kmeans", "clustering": {"n_clusters": 5}},
            {"id": "agglomerative_3", "label": "Agglomerative 3 clusters", "estimator": "agglomerative", "clustering": {"n_clusters": 3}, "enabled_by_default": False},
            {"id": "dbscan_default", "label": "DBSCAN default", "estimator": "dbscan", "clustering": {"eps": 0.5, "min_samples": 5}, "enabled_by_default": False},
        ],
    }


def default_modeling_comparison_candidates(task: str) -> list[dict[str, Any]]:
    """Return reusable named candidates for model comparison workflows."""

    catalog = _default_comparison_candidate_catalog()
    return [dict(item) for item in catalog.get(task) or catalog.get("regression") or []]


def _normalize_experiment_candidate(candidate: dict[str, Any], *, position: int, task: str) -> dict[str, Any]:
    raw = dict(candidate or {})
    estimator = str(raw.get("estimator") or (raw.get("spec") or {}).get("estimator") or ("kmeans" if task == "clustering" else "random_forest"))
    candidate_id = str(raw.get("id") or raw.get("candidate_id") or f"{estimator}_{position + 1}")
    label = str(raw.get("label") or raw.get("name") or candidate_id.replace("_", " ").title())
    return {
        **raw,
        "id": candidate_id,
        "label": label,
        "estimator": estimator,
        "position": position,
    }


def _candidate_experiment_spec(base: ModelingExperimentSpec, candidate: dict[str, Any]) -> ModelingExperimentSpec:
    data = base.to_dict()
    patch = dict(candidate.get("spec") or {})
    for key in ["estimator", "task", "target", "features", "random_state"]:
        if key in candidate:
            patch[key] = candidate[key]
    for key in ["estimator_params", "preprocessing", "search", "split", "validation", "sample", "clustering", "explanation"]:
        if key in candidate:
            patch[key] = {**dict(patch.get(key) or {}), **dict(candidate.get(key) or {})}
    for key, value in patch.items():
        if key in data and isinstance(data[key], dict) and isinstance(value, dict):
            data[key] = {**data[key], **value}
        elif key in data:
            data[key] = value
    return normalize_modeling_experiment_spec(data)


def _modeling_comparison(runs: list[ModelingExperimentResult], errors: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_comparison_row(run) for run in runs]
    for error in errors:
        rows.append(
            {
                "candidate_id": error.get("candidate_id"),
                "candidate_label": error.get("candidate_label"),
                "estimator": error.get("estimator"),
                "status": "error",
                "error": error.get("error"),
                "score": None,
                "rank": None,
            }
        )
    successful = [row for row in rows if row.get("status") == "ok"]
    successful.sort(key=lambda row: float(row.get("_score") if row.get("_score") is not None else -np.inf), reverse=True)
    champion_id = successful[0]["candidate_id"] if successful else None
    champion_metric = successful[0].get("primary_metric") if successful else {}
    champion_value = _metric_number((champion_metric or {}).get("value"))
    for rank, row in enumerate(successful, start=1):
        row["rank"] = rank
        metric_value = _metric_number((row.get("primary_metric") or {}).get("value"))
        if champion_value is not None and metric_value is not None:
            row["delta_from_champion"] = _clean_metric(metric_value - champion_value)
    for row in rows:
        row.pop("_score", None)
    error_rows = [row for row in rows if row.get("status") == "error"]
    rows = successful + error_rows
    metric_keys = sorted({key for run in runs for key, value in (run.metrics or {}).items() if not isinstance(value, (dict, list))})
    return {
        "rows": rows,
        "champion_id": champion_id,
        "champion_label": successful[0].get("candidate_label") if successful else None,
        "metric_keys": metric_keys,
        "run_count": len(runs),
        "error_count": len(errors),
    }


def _comparison_row(run: ModelingExperimentResult) -> dict[str, Any]:
    candidate_id = run.search.get("candidate_id") or run.estimator
    candidate_label = run.search.get("candidate_label") or str(candidate_id).replace("_", " ").title()
    primary = dict((run.assessment or {}).get("primary_metric") or {})
    score = _comparison_score(primary)
    return {
        "candidate_id": candidate_id,
        "candidate_label": candidate_label,
        "estimator": run.estimator,
        "task": run.task,
        "status": "ok",
        "rank": None,
        "row_count": int(run.row_count),
        "feature_count": int(run.feature_count),
        "metrics": _json_ready(run.metrics),
        "primary_metric": _json_ready(primary),
        "rating": (run.assessment or {}).get("rating"),
        "warning_count": len(run.warnings or []),
        "warnings": list(run.warnings or [])[:4],
        "best_params": _json_ready((run.search or {}).get("best_params")),
        "_score": score,
    }


def _comparison_score(primary: dict[str, Any]) -> float | None:
    value = _metric_number(primary.get("value"))
    if value is None:
        return None
    if primary.get("direction") == "lower_is_better":
        return -value
    return value


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
    "ModelingExperimentSuiteResult",
    "ModelingPlan",
    "build_modeling_plan",
    "build_modeling_artifact",
    "default_modeling_comparison_candidates",
    "default_modeling_experiment_spec",
    "modeling_experiment_catalog",
    "normalize_modeling_experiment_spec",
    "run_modeling_experiment",
    "run_modeling_experiment_suite",
]
