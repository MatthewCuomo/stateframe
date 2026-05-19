import json

import pandas as pd

import stateframe as sf


def test_save_tree_writes_session_metadata_for_profiles(tmp_path):
    sf.save.configure(root=tmp_path, session_name="analysis notebook")
    sales = sf.scan(pd.DataFrame({"price": [100, 200, 300]}), name="sales")
    weather = sf.scan(pd.DataFrame({"temp": [70, 75, 80]}), name="weather")

    result = sf.save.tree(sales, weather)
    web = json.loads(result.path.read_text(encoding="utf-8"))
    payload = sf.save.load_tree(tree="sales")

    assert result.path == tmp_path / ".stateframe" / "web.json"
    assert result.kind == "web"
    assert web["kind"] == "stateframe_web"
    assert sorted(tree["tree_name"] for tree in web["trees"]) == ["sales", "weather"]
    assert payload["kind"] == "stateframe_tree"
    assert payload["tree_name"] == "sales"
    assert payload["workspace"]["name"] == "analysis notebook"
    assert [profile["dataset_name"] for profile in payload["profiles"]] == ["sales"]
    assert payload["profile"]["source"]["kind"] == "dataframe"
    assert payload["profile"]["ledger"]["entries"][0]["kind"] == "scan"


def test_save_data_writes_parquet_and_attaches_artifact(tmp_path):
    sf.save.configure(root=tmp_path, session_name="data notebook")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]}), name="features")
    entry = scan.record_state(
        pd.DataFrame({"x": [1, 2], "y": [10, 20]}),
        title="Filtered features",
        operation="test.filter",
    )

    result = sf.save.data(scan, entry_id=entry.id, name="filtered_features")
    loaded = sf.save.load_data(result.path)
    tree_payload = sf.save.load_tree(tree="features")
    updated_entry = scan.ledger.get(entry.id)

    assert result.path.exists()
    assert result.path.name == "filtered_features.parquet"
    assert result.path.parent.parent == tmp_path / ".stateframe" / "data"
    assert loaded[["x", "y"]].reset_index(drop=True).equals(pd.DataFrame({"x": [1, 2], "y": [10, 20]}))
    assert updated_entry.artifacts[0]["kind"] == "data_snapshot"
    assert updated_entry.artifacts[0]["format"] == "parquet"
    assert tree_payload["profile"]["ledger"]["entries"][-1]["artifacts"]


def test_profile_save_shortcuts(tmp_path):
    sf.save.configure(root=tmp_path, session_name="shortcut notebook")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="shortcut")

    tree_result = scan.save_tree()
    data_result = scan.save_data(name="active_state")

    assert tree_result.path.exists()
    assert data_result.path.exists()
