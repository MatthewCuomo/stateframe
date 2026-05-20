import pandas as pd
import pytest

import stateframe as sf
from stateframe.interactive.web import build_web_payload
from stateframe.interactive.web import WorkspaceWebDependencyError


def test_web_payload_lists_workspace_trees(tmp_path):
    sf.workspace.configure(root=tmp_path, name="web test")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    scan.save_tree()

    payload = sf.web_payload()
    widget_payload = build_web_payload(sf.workspace.current(), height=500, title=None)

    assert payload["kind"] == "stateframe_web"
    assert payload["tree_count"] == 1
    assert payload["trees"][0]["tree_name"] == "numbers"
    assert widget_payload["trees"][0]["tree_detail"]["entries"][0]["kind"] == "scan"


def test_web_view_can_pull_selected_snapshot(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="web checkout")
    raw = pd.DataFrame({"x": [1, 2, 3], "county": ["A", "B", "B"]})
    scan = sf.scan(raw, name="numbers")
    branch_data = raw[raw["county"] == "B"]
    entry = scan.record_state(
        branch_data,
        title="County B",
        operation="test.filter",
        note="Filtered to county B.",
    )
    scan.save_data(entry_id=entry.id, name="county_b")

    web = sf.web()
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": entry.id,
    }

    restored = web.pull_selected()
    pd.testing.assert_frame_equal(
        restored.reset_index(drop=True),
        branch_data.reset_index(drop=True),
    )
    branch_viewer = web.view_selected()
    assert branch_viewer.ledger_parent_id == entry.id
    assert branch_viewer.record_profile.tree_id == web.payload["trees"][0]["tree_id"]


def test_web_view_browses_and_scans_workspace_files(tmp_path):
    pytest.importorskip("anywidget")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "events.csv"
    pd.DataFrame({"x": [1, 2], "label": ["a", "b"]}).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web file browser")
    sf.workspace.init()

    web = sf.web()
    listing = web.browse_files("data")
    profile = web.scan_file("data/events.csv")
    web.refresh()

    assert listing["entries"][0]["name"] == "events.csv"
    assert listing["entries"][0]["can_scan"] is True
    assert profile.source["path"] == str(source.relative_to(tmp_path))
    assert any(tree["tree_name"] == "events" for tree in web.payload["trees"])


def test_web_view_explains_missing_snapshot_for_dataframe_source(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="web missing snapshot")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    scan.save_tree()

    web = sf.web()

    with pytest.raises(ValueError, match="no materialized data snapshot"):
        web.pull_selected()


def test_web_view_api_reports_missing_interactive_extra_when_not_installed(tmp_path):
    try:
        import anywidget  # noqa: F401
    except ModuleNotFoundError:
        sf.workspace.configure(root=tmp_path, name="missing web deps")
        with pytest.raises(WorkspaceWebDependencyError):
            sf.web()
