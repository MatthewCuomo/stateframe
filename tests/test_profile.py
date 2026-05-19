import pandas as pd

import stateframe as sf


def test_profile_builds_summary_issues_and_recommendations():
    df = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 3],
            "revenue": [0.0, 10.0, 1000.0, None],
            "segment": ["a", "a", "a", "b"],
            "event_ts": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-10", "2026-01-10"]
            ),
        }
    )

    profile = sf.profile(df)

    assert profile.summary()["row_count"] == 4
    assert profile.summary()["column_count"] == 4
    assert profile.column("revenue").semantic_type == "amount"
    assert any(issue.id == "time.duplicate_timestamps" for issue in profile.issues())
    assert any(rec.lens == "time.cadence" for rec in profile.recommendations())


def test_core_lenses_run():
    df = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4],
            "revenue": [1.0, 2.0, 3.0, 100.0],
            "event_ts": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]
            ),
        }
    )

    profile = sf.profile(df)

    cadence = profile.run("time.cadence", column="event_ts")
    concentration = profile.run("concentration.lorenz", column="revenue")
    keys = profile.run("grain.keys")
    corr = profile.run("relationships.correlation")

    assert cadence.data["non_null_count"] == 4
    assert concentration.data["top_10pct_share"] > 0
    assert keys.data["row_count"] == 4
    assert "revenue" in corr.data["columns"]


def test_target_balance_recommendation_and_lens():
    df = pd.DataFrame(
        {
            "feature_a": [1, 2, 3, 4, 5],
            "feature_b": [5, 4, 3, 2, 1],
            "churned": [0, 0, 0, 0, 1],
        }
    )

    profile = sf.profile(df, target="churned", goal="modeling")

    assert any(rec.lens == "target.balance" for rec in profile.recommendations())
    balance = profile.run("target.balance")
    assert balance.data["column"] == "churned"
    assert balance.data["total"] == 5

