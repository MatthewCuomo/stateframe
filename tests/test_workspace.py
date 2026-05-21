import json
from pathlib import Path

import pandas as pd

import stateframe as sf
from stateframe.workspace import WorkspaceDiscoveryError


def test_workspace_registers_scan_with_dataframe_variable_name(tmp_path):
    sf.workspace.configure(root=tmp_path, name="workspace test")

    realestate = pd.DataFrame({"price": [100, 200], "county": ["A", "B"]})
    scan = sf.scan(realestate)
    web = sf.workspace.web()

    assert scan.dataset_name == "realestate"
    assert scan.tree_name == "realestate"
    assert (tmp_path / ".stateframe" / "workspace.json").exists()
    assert (tmp_path / ".stateframe" / "web.json").exists()
    assert web["kind"] == "stateframe_web"
    assert web["trees"][0]["tree_name"] == "realestate"
    assert web["trees"][0]["source"]["kind"] == "dataframe"


def test_workspace_saves_tree_by_stable_id_and_editable_name(tmp_path):
    sf.workspace.configure(root=tmp_path, name="rename test")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="raw_sales")

    result = scan.save_tree()
    renamed = scan.rename_tree("Real Estate Sales")
    web = sf.workspace.web()
    payload = json.loads(result.path.read_text(encoding="utf-8"))

    assert result.path.parent.name.startswith("raw_sales-")
    assert renamed["tree_name"] == "Real Estate Sales"
    assert web["trees"][0]["tree_name"] == "Real Estate Sales"
    assert web["trees"][0]["tree_id"] == payload["tree_id"]
    assert sf.workspace.load_tree("Real Estate Sales")["tree_name"] == "Real Estate Sales"


def test_workspace_enforces_unique_editable_tree_names(tmp_path):
    sf.workspace.configure(root=tmp_path, name="unique names")
    first = sf.scan(pd.DataFrame({"x": [1]}), name="dataset")
    second = sf.scan(pd.DataFrame({"x": [2], "y": [3]}), name="dataset")

    names = sorted(record["tree_name"] for record in sf.workspace.list_trees())

    assert names == ["dataset", "dataset 2"]
    try:
        second.rename_tree("dataset")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected duplicate tree name to fail")
    assert first.tree_name == "dataset"


def test_workspace_connect_discovers_parent_workspace(tmp_path):
    root = tmp_path / "science_base"
    nested = root / "pillar" / "notebooks" / "deep"
    nested.mkdir(parents=True)

    sf.workspace.configure(root=root, name="science base")
    sf.workspace.init()
    sf.workspace.configure(root=tmp_path / "other", name="other")

    connected = sf.workspace.connect(start=nested)

    assert connected.root == root.resolve()
    assert sf.workspace.settings()["name"] == "science base"
    assert sf.workspace.settings()["web_path"] == str(root / ".stateframe" / "web.json")


def test_workspace_connect_reports_missing_workspace(tmp_path):
    try:
        sf.workspace.connect(start=tmp_path / "missing" / "notebooks")
    except WorkspaceDiscoveryError as exc:
        assert "No stateframe workspace found" in str(exc)
    else:
        raise AssertionError("Expected workspace discovery to fail")


def test_scan_path_stores_workspace_relative_source_from_nested_notebook(tmp_path, monkeypatch):
    root = tmp_path / "science_base"
    data_dir = root / "realestate" / "data"
    nested = root / "realestate" / "notebooks" / "analysis"
    data_dir.mkdir(parents=True)
    nested.mkdir(parents=True)
    source_path = data_dir / "events.csv"
    pd.DataFrame({"x": [1, 2], "label": ["a", "b"]}).to_csv(source_path, index=False)

    sf.workspace.configure(root=root, name="science base")
    sf.workspace.init()
    monkeypatch.chdir(nested)

    scan = sf.scan_path("../../data/events.csv", name="events")

    assert scan.source["path_root"] == "workspace"
    assert scan.source["path"] == str(Path("realestate") / "data" / "events.csv")
    assert scan.source["absolute_path"] == str(source_path.resolve())


def test_workspace_file_browser_lists_supported_data_files(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (tmp_path / "outputs").mkdir()
    pd.DataFrame({"x": [1, 2]}).to_csv(data_dir / "events.csv", index=False)
    (data_dir / "notes.md").write_text("# notes", encoding="utf-8")
    (tmp_path / ".hidden.csv").write_text("x\n1\n", encoding="utf-8")

    sf.workspace.configure(root=tmp_path, name="file browser")

    root_listing = sf.workspace.list_files()
    data_listing = sf.workspace.list_files("data")
    save_path = sf.workspace.validate_save_path("outputs/plot.png")

    assert root_listing["current_path"] == "."
    assert "data" in {entry["name"] for entry in root_listing["entries"]}
    assert ".hidden.csv" not in {entry["name"] for entry in root_listing["entries"]}
    events = next(entry for entry in data_listing["entries"] if entry["name"] == "events.csv")
    notes = next(entry for entry in data_listing["entries"] if entry["name"] == "notes.md")
    assert events["can_scan"] is True
    assert events["data_kind"] == "csv"
    assert notes["can_scan"] is False
    assert save_path["path"] == "outputs/plot.png"


def test_workspace_file_browser_rejects_paths_outside_root(tmp_path):
    sf.workspace.configure(root=tmp_path, name="file browser safety")

    try:
        sf.workspace.list_files("..")
    except ValueError as exc:
        assert "outside the stateframe workspace root" in str(exc)
    else:
        raise AssertionError("Expected workspace path escape to fail")


def test_workspace_can_delete_branch_subtree_from_saved_tree(tmp_path):
    sf.workspace.configure(root=tmp_path, name="delete branches")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3], "group": ["a", "b", "b"]}), name="events")
    branch = scan.record_state(
        pd.DataFrame({"x": [2, 3], "group": ["b", "b"]}),
        title="Group B",
        operation="test.filter",
    )
    leaf = scan.record_artifact(
        title="Branch note",
        kind="report",
        parent_id=branch.id,
        artifact={"kind": "report", "format": "text", "text": "note"},
    )
    scan.save_tree()

    result = sf.workspace.delete_tree_entries(scan.tree_id, [branch.id])
    payload = sf.workspace.load_tree(scan.tree_id)
    ledger = payload["profile"]["ledger"]
    entry_ids = {entry["id"] for entry in ledger["entries"]}
    state_entry_ids = {state["entry_id"] for state in ledger["states"].values()}
    web_record = sf.workspace.current().resolve_tree(scan.tree_id)

    assert result["deleted_entry_count"] == 2
    assert branch.id not in entry_ids
    assert leaf.id not in entry_ids
    assert branch.id not in state_entry_ids
    assert ledger["root_entry_id"] in entry_ids
    assert ledger["active_entry_id"] == ledger["root_entry_id"]
    assert web_record["entry_count"] == 1


def test_workspace_delete_tree_removes_it_from_web_index(tmp_path):
    sf.workspace.configure(root=tmp_path, name="delete tree")
    scan = sf.scan(pd.DataFrame({"x": [1]}), name="temporary")
    tree_path = scan.save_tree().path

    result = sf.workspace.delete_tree(scan.tree_id)

    assert result["deleted"] is True
    assert sf.workspace.list_trees() == []
    assert tree_path.exists()
