import pandas as pd

import stateframe as sf
from stateframe.lens_registry import get_lens_spec
from stateframe.models import PlotResult


def test_guidance_modes_and_recommendation_source_filters():
    df = pd.DataFrame(
        {
            "record_id": [1, 2, 3, 4, 5, 6],
            "feature": [1, 2, 3, 4, 5, 6],
            "segment": ["a", "a", "b", "b", "c", "c"],
            "sold_price": [100, 110, 130, 140, 160, 170],
        }
    )

    guided = sf.scan(df, guidance="guided")
    expert = sf.scan(
        df,
        guidance="expert",
        semantic_policy="off",
        recommendation_basis=["statistical", "quality", "relationship"],
    )

    assert guided.guidance == "guided"
    assert expert.guidance == "expert"
    assert expert.semantic_policy == "off"
    assert all(
        set(rec.evidence_sources).intersection({"statistical", "quality", "relationship"})
        for rec in expert.recommendations()
    )
    assert len(guided.recommendations(source="visual").top(3)) > 0
    assert len(guided.recommendations(exclude_sources="semantic")) <= len(guided.recommendations())


def test_recommendations_point_to_registered_lenses():
    df = pd.DataFrame(
        {
            "amount": [1, 2, 3, 100],
            "category": ["x", "x", "y", "y"],
            "flag": ["Y", "N", "Y", "N"],
        }
    )
    scan = sf.scan(df)

    for recommendation in scan.recommendations().top(20):
        assert get_lens_spec(recommendation.lens).id == recommendation.lens


def test_plot_result_and_cleaning_plan():
    df = pd.DataFrame(
        {
            "amount": ["1.0", "2.5", " ", "4.0"],
            "flag": ["Y", "N", "Y", None],
            "label": [0, 0, 1, 1],
        }
    )
    scan = sf.scan(df, target="label")

    plot = scan.plot_recommendation(1, as_result=True)
    assert isinstance(plot, PlotResult)
    assert plot.figure is not None

    plan = scan.cleaning_plan()
    preview = plan.preview()
    assert not preview.empty
    assert {"parse_numeric", "binary_mapping"}.intersection(set(preview["action"]))
    cleaned = plan.apply()
    assert "amount" in cleaned.columns


def test_mixed_associations_and_target_importance_lenses():
    df = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6, 7, 8],
            "y": [2, 4, 6, 8, 10, 12, 14, 16],
            "group": ["a", "a", "a", "b", "b", "b", "b", "b"],
            "target": [1, 2, 3, 5, 8, 13, 21, 34],
        }
    )
    scan = sf.scan(df, target="target")

    mixed = scan.run("relationships.mixed_associations")
    assert mixed.data["associations"]
    assert mixed.data["associations"][0]["strength"] is not None

    importance = scan.run("target.importance", target="target")
    assert importance.data["target"] == "target"
    assert importance.data["feature_importance"]
