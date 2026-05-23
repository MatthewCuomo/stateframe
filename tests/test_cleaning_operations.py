import pandas as pd

import stateframe as sf


def test_cleaning_plan_surfaces_rich_operation_controls_and_reviews():
    df = pd.DataFrame(
        {
            "listed_flag": ["Y", "N", "Yes", None, "missing"],
            "pool_flag": [1, None, 1, None, 1],
            "price": ["100000", "120000", "9999999", "N/A", "130000"],
            "sold_date": ["2025-01-01", "01/05/2025", "Feb 1 2025", "missing", "2025/03/01"],
            "city": ["Miami", " miami ", "MIAMI", "Tampa", "TAMPA"],
            "latitude": [25.76, 26.1, 120.0, 91.0, 27.0],
            "longitude": [-80.19, -81.0, 25.7, -181.0, -82.0],
        }
    )

    scan = sf.scan(df)
    plan = scan.cleaning_plan()
    preview = plan.preview()
    operation_preview = plan.operation_preview()
    actions = set(preview["action"])

    assert {
        "binary_mapping",
        "binary_mapping_review",
        "parse_numeric",
        "parse_datetime",
        "numeric_outlier_review",
        "geo_coordinate_review",
        "category_value_review",
    }.issubset(actions)
    assert "catalog" in operation_preview
    assert any(item["id"] == "binary_mapping" for item in operation_preview["catalog"])
    assert preview["controls"].map(bool).all()
    assert preview["affected_rows"].notna().any()

    date_action = next(action for action in plan.actions if action.column == "sold_date" and action.action == "parse_datetime")
    assert date_action.preview["mixed_formats"] is True
    assert date_action.preview["format_clusters"]

    ambiguous = next(action for action in plan.actions if action.column == "pool_flag" and action.action == "binary_mapping_review")
    assert ambiguous.action == "binary_mapping_review"
    assert ambiguous.applies_by_default is False


def test_cleaning_plan_surfaces_and_applies_column_rename_review():
    df = pd.DataFrame({"Sale Price": [100], "Owner Name": ["Ada"], "123 Bad %": [1]})
    scan = sf.scan(df)

    plan = scan.cleaning_plan()
    action = next(item for item in plan.actions if item.action == "column_rename_review")
    assert action.preview["rename_count"] == 3
    assert any(item["id"] == "column_rename_review" for item in plan.operation_catalog())

    renamed = plan.apply(
        action_ids=[action.to_dict()["id"]],
        action_control_values={
            action.to_dict()["id"]: {
                "treatment": "apply",
                "case": "lower",
                "separator": "_",
                "remove_punctuation": True,
            }
        },
    )
    assert renamed.columns.tolist() == ["sale_price", "owner_name", "col_123_bad"]


def test_cleaning_plan_presets_apply_rename_after_type_conversions():
    df = pd.DataFrame(
        {
            "Sold Date": ["2025-01-01", "01/05/2025", "missing", "2025/03/01"],
            "List Price": ["100000", "120000", "N/A", "130000"],
            "Listed Flag": ["Y", "N", None, "Yes"],
        }
    )

    scan = sf.scan(df)
    plan = scan.cleaning_plan()
    preview = plan.operation_preview()
    presets = {preset["id"]: preset for preset in preview["presets"]}

    assert {"safe_defaults", "type_prep", "analysis_ready", "power_review", "audit_all"}.issubset(presets)
    assert presets["analysis_ready"]["actionControlValues"]["column_rename_review:__columns__"]["treatment"] == "apply"

    cleaned = plan.apply(
        action_ids=presets["analysis_ready"]["selectedActionIds"],
        action_control_values=presets["analysis_ready"]["actionControlValues"],
    )

    assert cleaned.columns.tolist() == ["sold_date", "list_price", "listed_flag"]
    assert pd.api.types.is_datetime64_any_dtype(cleaned["sold_date"])
    assert pd.api.types.is_numeric_dtype(cleaned["list_price"])
    assert str(cleaned["listed_flag"].dtype) == "Int64"


def test_cleaning_plan_applies_safe_defaults_and_optional_outlier_treatments():
    df = pd.DataFrame(
        {
            "listed_flag": ["Y", "N", "Yes", None, "missing"],
            "price": ["100000", "120000", "9999999", "N/A", "130000"],
            "sold_date": ["2025-01-01", "01/05/2025", "Feb 1 2025", "missing", "2025/03/01"],
        }
    )

    scan = sf.scan(df)
    cleaned = scan.cleaning_plan(binary_null_policy="treat_as_false").apply()

    assert str(cleaned["listed_flag"].dtype) == "Int64"
    assert cleaned["listed_flag"].tolist() == [1, 0, 1, 0, 0]
    assert pd.api.types.is_numeric_dtype(cleaned["price"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned["sold_date"])

    clipped = scan.cleaning_plan().apply(outlier_policy="clip")
    assert clipped["price"].max() < 9_999_999

    entry_count = len(scan.ledger.entries)
    result = scan.apply_cleaning(record=True, outlier_policy="flag")
    assert "price_is_outlier" in result.columns
    assert len(scan.ledger.entries) == entry_count + 1
    assert scan.ledger.entries[-1].operation == "cleaning.apply"
    assert scan.ledger.entries[-1].summary["action_count"] >= 1


def test_cleaning_plan_accepts_per_action_control_overrides():
    df = pd.DataFrame(
        {
            "amount": ["1000", "2000", "3000", "N/A"],
            "city": ["Miami", " miami ", "Tampa", "TAMPA"],
            "latitude": [120.0, 25.76, 26.0, 27.0],
            "longitude": [30.0, -80.19, -81.0, -82.0],
        }
    )

    scan = sf.scan(df)
    plan = scan.cleaning_plan()
    amount_action = next(action for action in plan.actions if action.column == "amount" and action.action == "parse_numeric")
    city_action = next(action for action in plan.actions if action.column == "city" and action.action == "category_value_review")
    geo_action = next(action for action in plan.actions if action.action == "geo_coordinate_review" and "," in action.column)

    amount_id = amount_action.to_dict()["id"]
    parsed = plan.apply(
        action_ids=[amount_id],
        action_control_values={amount_id: {"remove_commas": True, "invalid_policy": "coerce"}},
    )
    assert parsed["amount"].dropna().tolist() == [1000, 2000, 3000]

    city_id = city_action.to_dict()["id"]
    mapped = plan.apply(
        action_ids=[city_id],
        action_control_values={city_id: {"mapping": {"miami": "Miami"}, "casefold": True, "strip": True}},
    )
    assert mapped["city"].tolist()[:2] == ["Miami", "Miami"]

    geo_id = geo_action.to_dict()["id"]
    swapped = plan.apply(action_ids=[geo_id], action_control_values={geo_id: {"treatment": "swap_likely"}})
    assert swapped.loc[0, "latitude"] == 30.0
    assert swapped.loc[0, "longitude"] == 120.0


def test_cleaning_plan_reviews_missing_values_and_duplicate_rows():
    df = pd.DataFrame(
        {
            "listing_id": [1, 1, 2, 3],
            "price": [100_000.0, 100_000.0, None, 130_000.0],
            "city": ["A", "A", None, "B"],
        }
    )

    scan = sf.scan(df)
    plan = scan.cleaning_plan()
    actions = {(action.column, action.action): action for action in plan.actions}

    assert ("__rows__", "duplicate_row_review") in actions
    assert ("price", "missing_value_review") in actions
    assert ("city", "missing_value_review") in actions
    assert any(item["id"] == "missing_value_review" for item in plan.operation_catalog())
    assert any(item["id"] == "duplicate_row_review" for item in plan.operation_catalog())

    price_id = actions[("price", "missing_value_review")].to_dict()["id"]
    imputed = plan.apply(
        action_ids=[price_id],
        action_control_values={price_id: {"treatment": "fill_median", "add_indicator": True}},
    )
    assert imputed["price"].tolist() == [100_000.0, 100_000.0, 100_000.0, 130_000.0]
    assert imputed["price_was_missing"].tolist() == [0, 0, 1, 0]

    city_id = actions[("city", "missing_value_review")].to_dict()["id"]
    labeled = plan.apply(
        action_ids=[city_id],
        action_control_values={city_id: {"treatment": "fill_missing_label"}},
    )
    assert labeled["city"].tolist() == ["A", "A", "Missing", "B"]

    duplicate_id = actions[("__rows__", "duplicate_row_review")].to_dict()["id"]
    deduped = plan.apply(
        action_ids=[duplicate_id],
        action_control_values={duplicate_id: {"treatment": "drop", "keep": "first"}},
    )
    assert deduped.shape[0] == 3
