import numpy as np
import pandas as pd

import stateframe as sf


def test_public_mapping_imputation_encoding_scaling_and_date_helpers():
    df = pd.DataFrame(
        {
            "segment": ["A", " b ", "C", "C"],
            "amount": [10.0, np.nan, 30.0, 40.0],
            "sqft": [2.0, 4.0, 5.0, 10.0],
            "sold_date": ["2025-01-01", "2025-02-03", None, "2025-04-05"],
        }
    )

    mapped = sf.map_values(df, {"segment": {"a": "Alpha", "b": "Beta"}}, case_sensitive=False)
    assert mapped["segment"].tolist()[:2] == ["Alpha", "Beta"]

    nulled = sf.map_values(mapped, {"segment": {"C": None}})
    assert nulled["segment"].isna().sum() == 2

    imputed = sf.impute_missing(
        mapped,
        strategies={"amount": {"strategy": "median"}},
        add_indicators=True,
    )
    assert imputed["amount"].isna().sum() == 0
    assert imputed["amount_was_imputed"].tolist() == [0, 1, 0, 0]

    encoded = sf.one_hot_encode(imputed, ["segment"], max_categories=2)
    assert "segment_Alpha" in encoded.columns
    assert "segment_Other" in encoded.columns
    assert "segment" not in encoded.columns

    scaled = sf.scale_numeric(encoded, ["amount"], method="minmax")
    assert scaled["amount"].min() == 0
    assert scaled["amount"].max() == 1

    dated = sf.add_date_features(scaled, ["sold_date"], features=["year", "quarter", "is_weekend"])
    assert {"sold_date_year", "sold_date_quarter", "sold_date_is_weekend"}.issubset(dated.columns)

    ratioed = sf.add_ratio(dated, "amount", "sqft", "amount_per_sqft")
    assert "amount_per_sqft" in ratioed.columns


def test_public_column_rename_helpers_support_mass_and_manual_rules():
    df = pd.DataFrame(
        {
            "Sale Price": [1],
            "Owner Name": ["A"],
            "123 Weird %": [2],
            "Sale-Price": [3],
        }
    )

    cleaned = sf.clean_column_names(df)
    assert cleaned.columns.tolist() == ["sale_price", "owner_name", "col_123_weird", "sale_price_2"]

    compact = sf.clean_column_names(df, separator="")
    assert "saleprice" in compact.columns
    assert "ownername" in compact.columns

    manual = sf.rename_columns(df, {"Owner Name": "seller"}, columns=["Sale Price"], separator="_", case="lower")
    assert "seller" in manual.columns
    assert "sale_price" in manual.columns
    assert "123 Weird %" in manual.columns


def test_numeric_outlier_helper_flags_nulls_clips_and_drops():
    df = pd.DataFrame({"x": [10, 11, 12, 13, 10_000], "y": [1, 2, 3, 4, 5]})

    flagged = sf.clean_numeric_outliers(df, {"x": {"method": "iqr", "treatment": "flag"}})
    assert flagged["x_is_outlier"].tolist() == [0, 0, 0, 0, 1]

    nulled = sf.clean_numeric_outliers(df, {"x": {"method": "iqr", "treatment": "null"}})
    assert pd.isna(nulled.loc[4, "x"])

    clipped = sf.clean_numeric_outliers(df, {"x": {"method": "iqr", "treatment": "clip"}})
    assert clipped.loc[4, "x"] < 10_000

    dropped = sf.clean_numeric_outliers(df, {"x": {"method": "iqr", "treatment": "drop"}})
    assert dropped.shape[0] == 4
