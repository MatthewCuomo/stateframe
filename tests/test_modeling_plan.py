import pandas as pd

import stateframe as sf
from stateframe.lens_registry import get_lens_spec


def _modeling_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_id": [101, 102, 103, 104, 105, 106],
            "city": ["A", "B", "A", "C", "B", None],
            "list_price": [100_000, 125_000, 130_000, 150_000, 175_000, 180_000],
            "sqft": [900, 1100, None, 1400, 1600, 1800],
            "sold_date": ["2025-01-01", "2025-02-01", "2025/03/01", None, "Apr 1 2025", "2025-05-01"],
            "constant": [1, 1, 1, 1, 1, 1],
            "sold": [1, 0, 1, 0, 1, 0],
        }
    )


def test_modeling_plan_previews_readiness_actions_and_applies_defaults():
    scan = sf.scan(_modeling_frame(), target="sold", goal="modeling")
    plan = scan.modeling_plan()

    preview = plan.preview()
    actions = set(preview["action"])
    assert {
        "modeling.review_target",
        "modeling.drop_identifier",
        "modeling.impute_missing",
        "modeling.encode_one_hot",
        "modeling.add_date_features",
        "modeling.drop_constant",
    }.issubset(actions)
    assert any(spec["id"] == "modeling.impute_missing" for spec in plan.operation_catalog())

    prepared = plan.apply()
    assert "listing_id" not in prepared.columns
    assert "constant" not in prepared.columns
    assert "city" not in prepared.columns
    assert "sold" in prepared.columns
    assert {"city_A", "city_B", "sqft_was_imputed", "sold_date_year"}.issubset(prepared.columns)
    assert prepared["sqft"].isna().sum() == 0


def test_modeling_plan_supports_selected_scaling_and_recording():
    scan = sf.scan(_modeling_frame(), target="sold", goal="modeling")
    plan = sf.modeling_plan(scan)
    scale_action = next(action for action in plan.actions if action.action == "modeling.scale_numeric")

    scaled = plan.apply(action_ids=[scale_action.to_dict()["id"]])
    assert abs(float(scaled[scale_action.column].mean())) < 1e-9
    assert "sold" in scaled.columns

    recorded = scan.apply_modeling_plan(record=True, scale="standard")
    assert recorded.shape[0] == scan.data.shape[0]
    assert scan.ledger is not None
    assert any(entry.operation == "modeling.prepare.apply" for entry in scan.ledger.entries)


def test_modeling_plan_accepts_per_action_control_overrides():
    scan = sf.scan(_modeling_frame(), target="sold", goal="modeling")
    plan = scan.modeling_plan()
    city_impute = next(action for action in plan.actions if action.column == "city" and action.action == "modeling.impute_missing")
    city_encode = next(action for action in plan.actions if action.column == "city" and action.action == "modeling.encode_one_hot")
    city_impute_id = city_impute.to_dict()["id"]
    city_encode_id = city_encode.to_dict()["id"]

    prepared = plan.apply(
        action_control_values={
            city_impute_id: {"strategy": "constant", "fill_value": "Unknown", "add_indicator": True},
            city_encode_id: {"dummy_na": False, "drop_first": False, "max_categories": 20},
        }
    )

    assert "city_Unknown" in prepared.columns
    assert prepared["city_Unknown"].tolist() == [0, 0, 0, 0, 0, 1]


def test_modeling_plan_suggests_optional_ratio_features():
    scan = sf.scan(_modeling_frame(), target="sold", goal="modeling")
    plan = scan.modeling_plan()
    ratio_action = next(action for action in plan.actions if action.action == "modeling.add_ratio_feature")
    ratio_id = ratio_action.to_dict()["id"]

    prepared = plan.apply(action_ids=[ratio_id])

    assert ratio_action.control_values["output"] in prepared.columns
    assert prepared.loc[0, ratio_action.control_values["output"]] == 100_000 / 900
    assert ratio_action.applies_by_default is False


def test_modeling_readiness_lens_and_recommendation_are_registered():
    scan = sf.scan(_modeling_frame(), target="sold", goal="modeling")

    result = scan.run("modeling.readiness")
    assert result.data["action_count"] >= 1
    assert get_lens_spec("modeling.plan").id == "modeling.readiness"
    assert any(rec.lens == "modeling.readiness" for rec in scan.recommendations())
