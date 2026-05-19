from pathlib import Path

import pandas as pd

import stateframe as sf


def test_scan_infers_targets_time_binary_flags_and_suggested_config():
    df = pd.DataFrame(
        {
            "customer_id": [101, 102, 103, 104],
            "signup_date": ["2024-01-01", "2024-01-03", "2024-01-04", "2024-01-10"],
            "churn": ["No", "No", "Yes", "No"],
            "email_opt_in": ["Y", "N", "Y", None],
            "has_discount": [1, None, 1, None],
            "total_charges": ["10.50", " ", "30.00", "40.00"],
            "notes": [
                "short note",
                "customer asked for a longer explanation about their plan",
                "another note",
                "follow-up text",
            ],
        }
    )

    scan = sf.scan(df, target="churn")

    assert scan.target_profile is not None
    assert scan.target_profile.column == "churn"
    assert scan.task is not None
    assert scan.task.task == "binary_classification"
    assert scan.time_candidates()[0].column == "signup_date"
    assert "email_opt_in" in scan.binary_flags()
    assert "has_discount" in scan.binary_flags()
    assert scan.binary_flags()["has_discount"].ambiguous is True
    assert scan.column("total_charges").semantic_type == "numeric-like"
    assert scan.suggested_config is not None
    assert "total_charges" in scan.suggested_config.numeric_conversions
    assert "email_opt_in" in scan.suggested_config.binary_mappings
    assert "has_discount" in scan.suggested_config.ambiguous_binary_flags
    assert any(rec.lens == "target.associations" for rec in scan.recommendations())


def test_binary_unification_uses_scan_mapping():
    df = pd.DataFrame({"flag": ["Y", "N", None]})
    scan = sf.scan(df)

    converted = sf.unify_binary_flags(df, scan=scan, columns=["flag"])

    assert str(converted["flag"].dtype) == "Int64"
    assert converted["flag"].iloc[0] == 1
    assert converted["flag"].iloc[1] == 0
    assert pd.isna(converted["flag"].iloc[2])


def test_scan_reads_local_csv_path(tmp_path: Path):
    path = tmp_path / "events.csv"
    pd.DataFrame(
        {
            "event_time": ["2024-01-01", "2024-01-02"],
            "amount": [10.0, 20.0],
            "label": [0, 1],
        }
    ).to_csv(path, index=False)

    scan = sf.scan(path, target="label")

    assert scan.summary()["row_count"] == 2
    assert scan.target_profile is not None
    assert scan.target_profile.task == "binary_classification"
    assert scan.time_candidates()[0].column == "event_time"
