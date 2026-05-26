import pandas as pd
import pytest

import stateframe as sf
from stateframe.lens_registry import get_lens_spec


def _classification_frame(rows: int = 80) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal": list(range(rows)),
            "season": [value % 4 for value in range(rows)],
            "segment": ["A", "B", "C", "A"] * (rows // 4),
            "target": [1 if value >= rows // 2 else 0 for value in range(rows)],
        }
    )


def test_modeling_experiment_runs_random_forest_with_shap_observability():
    scan = sf.scan(_classification_frame(), target="target", goal="modeling")

    result = scan.modeling_experiment(
        {
            "estimator": "random_forest",
            "validation": {"strategy": "holdout_and_cv", "cv_folds": 3},
            "explanation": {"enabled": True, "method": "auto", "max_rows": 20},
        }
    )

    payload = result.to_dict()
    assert result.task == "binary_classification"
    assert result.metrics["accuracy"] >= 0
    assert payload["holdout"]["confusion_matrix"]
    assert payload["holdout"]["classification_report"]
    assert payload["holdout"]["curves"]["precision_recall"]
    assert payload["holdout"]["curves"]["roc"]
    assert payload["cross_validation"]["enabled"] is True
    assert payload["assessment"]["primary_metric"]["key"] in {"roc_auc", "f1", "accuracy"}
    assert payload["explanation"]["method"] == "shap"
    assert payload["explanation"]["top_features"]
    assert payload["explanation"]["beeswarm"]
    assert payload["explanation"]["records"][0]["top_contributions"]


def test_modeling_experiment_supports_knn_grid_search_regression():
    df = pd.DataFrame(
        {
            "sqft": [800 + value * 25 for value in range(40)],
            "beds": [1 + value % 4 for value in range(40)],
            "city": ["A", "B"] * 20,
            "price": [150_000 + value * 8_000 for value in range(40)],
        }
    )
    scan = sf.scan(df, target="price", goal="modeling")

    result = sf.modeling_experiment(
        scan,
        {
            "task": "regression",
            "estimator": "knn",
            "search": {"enabled": True, "param_grid": {"n_neighbors": [2, 3]}, "cv_folds": 3},
            "validation": {"strategy": "cross_validation", "cv_folds": 3},
            "explanation": {"enabled": True, "method": "permutation", "max_rows": 10},
        },
    )

    assert result.search["enabled"] is True
    assert result.search["best_params"]["n_neighbors"] in {2, 3}
    assert "mae" in result.metrics
    assert result.cross_validation["enabled"] is True
    assert result.explanation["top_features"]


def test_modeling_experiment_supports_row_sampling_and_regression_residuals():
    rows = 90
    df = pd.DataFrame(
        {
            "sqft": [850 + value * 18 for value in range(rows)],
            "beds": [1 + value % 4 for value in range(rows)],
            "segment": ["A", "B", "C"] * 30,
            "price": [180_000 + value * 5_500 for value in range(rows)],
        }
    )
    scan = sf.scan(df, target="price", goal="modeling")

    result = scan.modeling_experiment(
        {
            "task": "regression",
            "estimator": "linear",
            "estimator_params": {"alpha": None},
            "sample": {"enabled": True, "max_rows": 30, "random_state": 7},
            "explanation": {"enabled": False},
        }
    )

    assert result.row_count == 30
    assert result.spec.sample["max_rows"] == 30
    assert any("sample" in warning for warning in result.warnings)
    assert "residual" in result.predictions[0]
    assert "median_absolute_error" in result.metrics
    assert result.holdout["residual_summary"]["p90_absolute_error"] is not None
    assert result.holdout["worst_predictions"]
    assert result.holdout["residual_bins"]
    assert result.holdout["prediction_audit"][0]["record"]["price"] is not None
    assert result.assessment["primary_metric"]["key"] == "r2"


def test_modeling_comparison_ranks_named_regression_candidates():
    rows = 72
    df = pd.DataFrame(
        {
            "sqft": [850 + value * 18 for value in range(rows)],
            "beds": [1 + value % 4 for value in range(rows)],
            "city": ["A", "B", "C"] * 24,
            "price": [180_000 + value * 5_500 + (value % 4) * 2_000 for value in range(rows)],
        }
    )
    scan = sf.scan(df, target="price", goal="modeling")

    suite = sf.modeling_comparison(
        scan,
        {
            "task": "regression",
            "features": ["sqft", "beds", "city"],
            "sample": {"enabled": True, "max_rows": 60, "random_state": 11},
            "explanation": {"enabled": False},
        },
        candidates=[
            {"id": "linear_base", "label": "Linear base", "estimator": "linear", "estimator_params": {"alpha": 1.0}},
            {"id": "poly2", "label": "Polynomial degree 2", "estimator": "polynomial", "estimator_params": {"degree": 2, "alpha": 1.0}},
            {"id": "forest_small", "label": "Forest small", "estimator": "random_forest", "estimator_params": {"n_estimators": 20, "min_samples_leaf": 2}},
        ],
    )
    payload = suite.to_dict()

    assert len(suite.runs) == 3
    assert payload["comparison"]["champion_id"]
    assert [row["rank"] for row in payload["comparison"]["rows"] if row["status"] == "ok"] == [1, 2, 3]
    assert any(run["estimator"] == "polynomial" for run in payload["runs"])
    polynomial_run = next(run for run in suite.runs if run.estimator == "polynomial")
    assert any(row["transform"] == "polynomial_feature" for row in polynomial_run.preprocessing["feature_lineage"])


def test_modeling_experiment_names_datetime_features_after_preprocessing():
    rows = 48
    df = pd.DataFrame(
        {
            "sold_date": pd.date_range("2024-01-01", periods=rows, freq="7D"),
            "sqft": [900 + value * 20 for value in range(rows)],
            "price": [200_000 + value * 6_000 for value in range(rows)],
        }
    )
    scan = sf.scan(df, target="price", goal="modeling")

    result = scan.modeling_experiment(
        {
            "task": "regression",
            "estimator": "random_forest",
            "explanation": {"enabled": True, "method": "model_importance"},
        }
    )

    feature_names = [row["feature"] for row in result.feature_importance]
    assert any(name.startswith("sold_date_") for name in feature_names)
    assert not any(name.startswith("datetime_") for name in feature_names)


def test_modeling_experiment_filters_manual_leakage_and_records_lineage():
    rows = 60
    df = pd.DataFrame(
        {
            "sold_price": [200_000 + value * 7_500 for value in range(rows)],
            "sold_price_per_sqft": [220 + value for value in range(rows)],
            "sqft": [900 + value * 20 for value in range(rows)],
            "county": ["A", "B", "C"] * 20,
            "sold_date": pd.date_range("2025-01-01", periods=rows, freq="D"),
        }
    )
    scan = sf.scan(df, target="sold_price", goal="modeling")

    result = scan.modeling_experiment(
        {
            "task": "regression",
            "estimator": "random_forest",
            "features": ["sqft", "county", "sold_date", "sold_price_per_sqft"],
            "explanation": {"enabled": True, "method": "model_importance"},
        }
    )

    assert any("target-derived selected feature" in warning for warning in result.warnings)
    assert "sold_price_per_sqft" not in result.preprocessing["feature_roles"]
    lineage = result.preprocessing["feature_lineage"]
    assert any(row["source_column"] == "sold_date" and row["transform"] == "date_features" for row in lineage)
    assert any(row["source_column"] == "county" and row["transform"] == "encoded_category" for row in lineage)
    assert result.explanation["source_features"]


def test_modeling_artifact_persists_result_model_and_lineage(tmp_path):
    sf.workspace.configure(root=tmp_path, name="model artifact")
    df = pd.DataFrame(
        {
            "sqft": [800 + value * 30 for value in range(40)],
            "city": ["A", "B"] * 20,
            "price": [150_000 + value * 9_000 for value in range(40)],
        }
    )
    scan = sf.scan(df, target="price", goal="modeling")

    artifact, summary, code = sf.modeling_artifact(
        scan,
        {
            "task": "regression",
            "estimator": "linear",
            "explanation": {"enabled": True, "method": "model_importance"},
        },
    )

    saved_kinds = {item["kind"] for item in artifact["saved_files"]}
    assert artifact["kind"] == "model"
    assert artifact["saved"] is True
    assert {"model_result", "model_pipeline", "feature_lineage", "manifest"} <= saved_kinds
    assert summary["artifact_kind"] == "model"
    assert "sf.modeling_experiment" in code


def test_modeling_experiment_supports_xgboost_when_available():
    pytest.importorskip("xgboost")
    scan = sf.scan(_classification_frame(), target="target", goal="modeling")

    result = sf.modeling_experiment(
        scan,
        {
            "estimator": "xgboost",
            "estimator_params": {"n_estimators": 10, "max_depth": 2},
            "explanation": {"enabled": True, "method": "model_importance"},
        },
    )

    assert result.estimator == "xgboost"
    assert "accuracy" in result.metrics
    assert result.feature_importance


def test_modeling_experiment_supports_clustering():
    df = pd.DataFrame(
        {
            "x": [0, 1, 0, 1, 8, 9, 8, 9],
            "y": [0, 0, 1, 1, 8, 8, 9, 9],
            "group": ["A", "A", "A", "A", "B", "B", "B", "B"],
        }
    )
    scan = sf.scan(df, goal="modeling")

    result = scan.modeling_experiment(
        {
            "task": "clustering",
            "estimator": "kmeans",
            "clustering": {"n_clusters": 2},
        }
    )

    assert result.task == "clustering"
    assert result.metrics["cluster_count"] == 2
    assert result.explanation["method"] == "cluster_profile"
    assert result.assessment["rating"] in {"strong", "promising", "exploratory", "needs_review"}


def test_modeling_catalog_and_lens_are_registered():
    catalog = sf.modeling_catalog()
    scan = sf.scan(_classification_frame(), target="target", goal="modeling")

    lens = scan.run(
        "modeling.experiment",
        spec={"estimator": "random_forest", "explanation": {"method": "model_importance"}},
    )

    assert any(item["id"] == "random_forest" for item in catalog["estimators"])
    assert get_lens_spec("model.train").id == "modeling.experiment"
    assert lens.data["estimator"] == "random_forest"


def test_target_best_splits_lens_uses_entropy_or_variance_gain():
    df = pd.DataFrame(
        {
            "score": [1, 2, 3, 4, 8, 9, 10, 11],
            "segment": ["low", "low", "low", "mid", "high", "high", "high", "mid"],
            "target": [0, 0, 0, 0, 1, 1, 1, 1],
        }
    )
    scan = sf.scan(df, target="target", goal="modeling")

    result = scan.run("target.best_splits", min_leaf=2)

    assert result.data["criterion"] == "entropy_information_gain"
    assert result.data["splits"]
    assert result.data["splits"][0]["gain"] > 0
    assert get_lens_spec("entropy.splits").id == "target.best_splits"
