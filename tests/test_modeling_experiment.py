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
