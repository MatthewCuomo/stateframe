import numpy as np
import pandas as pd

import stateframe as sf
from stateframe.lens_registry import get_lens_spec


def test_footprint_plan_previews_and_applies_safe_dtype_changes():
    df = pd.DataFrame(
        {
            "city": ["Miami", "Miami", "Tampa", "Tampa", "Miami"] * 20,
            "small_int": pd.Series([1, 2, 3, 4, 5] * 20, dtype="int64"),
            "whole_float": pd.Series([1.0, 2.0, np.nan, 4.0, 5.0] * 20, dtype="float64"),
            "precise_float": pd.Series([1.25, 2.5, 3.75, 4.0, 5.125] * 20, dtype="float64"),
        }
    )
    scan = sf.scan(df)

    plan = scan.footprint_plan()
    preview = plan.preview()

    assert not preview.empty
    assert {"city", "small_int", "whole_float"}.issubset(set(preview["column"]))
    assert plan.summary()["savings_bytes"] > 0

    optimized = plan.apply()

    assert str(optimized["city"].dtype) == "category"
    assert str(optimized["small_int"].dtype) in {"int8", "uint8"}
    assert str(optimized["whole_float"].dtype) in {"Int8", "UInt8"}
    assert optimized.memory_usage(deep=True).sum() < df.memory_usage(deep=True).sum()


def test_footprint_lens_and_public_helper():
    df = pd.DataFrame(
        {
            "segment": ["a", "b", "a", "b"] * 10,
            "amount": pd.Series([100, 200, 300, 400] * 10, dtype="int64"),
        }
    )
    scan = sf.scan(df)

    lens = scan.run("footprint.optimize")

    assert lens.id == "footprint.optimize"
    assert lens.data["action_count"] >= 1
    assert lens.data["savings_bytes"] > 0
    assert get_lens_spec("memory.optimize").id == "footprint.optimize"
    assert any(rec.lens == "footprint.optimize" for rec in scan.recommendations())

    optimized = sf.optimize_footprint(df)
    assert optimized.memory_usage(deep=True).sum() < df.memory_usage(deep=True).sum()
