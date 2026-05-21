import pandas as pd
import pytest

import stateframe as sf
from stateframe.interactive.web import build_web_payload
from stateframe.interactive.web import initial_web_state
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
    assert initial_web_state(widget_payload)["panelWidths"]["webLeft"] == 340
    assert initial_web_state(widget_payload)["saveMode"] is False


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


def test_web_embedded_viewer_has_lineage_and_can_save_plot_leaf(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "events.csv"
    pd.DataFrame(
        {
            "event_time": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "amount": [10.0, 20.0, 30.0],
            "segment": ["a", "b", "a"],
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web plot leaf")
    scan = sf.scan_path("events.csv", name="events")
    entry = scan.record_state(
        scan.data[scan.data["segment"] == "a"],
        title="Segment A",
        operation="test.filter",
    )
    scan.save_data(entry_id=entry.id, name="segment_a")

    web = sf.web()
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": entry.id,
    }
    viewer = web.open_selected_viewer()
    plot_entry = web.save_embedded_plot_leaf(
        kind="distribution.numeric",
        column="amount",
        title="Amount distribution",
    )

    assert [item["title"] for item in viewer["payload"]["lineage"]["entries"]][-1] == "Segment A"
    assert plot_entry.kind == "plot"
    assert plot_entry.parent_id == entry.id
    assert plot_entry.artifacts[0]["kind"] == "plot"
    assert plot_entry.artifacts[0]["preview_data_url"].startswith("data:image/png;base64,")
    assert plot_entry.summary["column"] == "amount"

    entries = web.payload["trees"][0]["tree_detail"]["entries"]
    parent_payload = next(item for item in entries if item["id"] == entry.id)
    plot_payload = next(item for item in entries if item["id"] == plot_entry.id)
    assert plot_entry.id in parent_payload["children_ids"]
    assert plot_payload["parent_id"] == entry.id
    assert plot_payload["kind"] == "plot"

    web.state = {
        **web.current_state(),
        "selectedEntryId": plot_entry.id,
        "viewMode": "leaf",
    }
    note = "## Readout\n\n**Amount** is concentrated in segment A."
    updated = web.save_selected_entry_note(note)
    assert updated["note"] == note
    assert web.state["viewMode"] == "leaf"

    entries = web.payload["trees"][0]["tree_detail"]["entries"]
    assert next(item for item in entries if item["id"] == plot_entry.id)["note"] == note
    saved_tree = sf.workspace.current().load_tree(web.payload["trees"][0]["tree_id"])
    saved_entries = saved_tree["profile"]["ledger"]["entries"]
    assert next(item for item in saved_entries if item["id"] == plot_entry.id)["note"] == note


def test_web_visualizer_renders_and_saves_plotly_leaf(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "sales.csv"
    pd.DataFrame(
        {
            "order_date": pd.date_range("2025-01-01", periods=6),
            "amount": [12, 18, 24, 33, 40, 55],
            "segment": ["a", "a", "b", "b", "c", "c"],
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web visualizer")
    scan = sf.scan_path("sales.csv", name="sales")
    entry = scan.record_state(
        scan.data[scan.data["amount"] >= 18],
        title="Qualified sales",
        operation="test.filter",
    )
    scan.save_data(entry_id=entry.id, name="qualified_sales")

    web = sf.web()
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": entry.id,
    }
    opened = web.open_visualizer()
    assert opened["payload"]["catalog"]["engine"] == "plotly"
    assert any(item["id"] == "scatter" for item in opened["payload"]["catalog"]["plot_types"])
    column_ids = {
        column["source_name"]: column["id"]
        for column in opened["payload"]["columns"]
    }

    spec = {
        "kind": "bar",
        "title": "Segment sales",
        "fields": {
            "x": column_ids["segment"],
            "y": column_ids["amount"],
            "color": column_ids["segment"],
        },
        "options": {"aggregation": "sum"},
        "filters": [{"column": column_ids["amount"], "op": "greater_equal", "value": "18"}],
    }
    preview = web.render_visualizer(spec)
    assert preview["format"] == "plotly_html"
    assert preview["engine"] == "plotly"
    assert "plotly" in preview["html"].lower()
    assert preview["plotly_json"]["data"]
    assert preview["preview_data_url"].startswith("data:image/png;base64,")

    scatter_spec = {
        "kind": "scatter",
        "title": "Sales scatter",
        "fields": {
            "x": column_ids["order_date"],
            "y": column_ids["amount"],
        },
    }
    scatter_preview = web.render_visualizer(scatter_spec)
    assert scatter_preview["preview_data_url"].startswith("data:image/png;base64,")

    line_spec = {
        "kind": "line",
        "title": "Sales line",
        "fields": {
            "x": column_ids["order_date"],
            "y": column_ids["amount"],
        },
    }
    line_preview = web.render_visualizer(line_spec)
    assert line_preview["preview_data_url"].startswith("data:image/png;base64,")

    saved = web.render_visualizer(spec, save=True, note="## Visual note")
    assert saved["kind"] == "plot"
    assert saved["parent_id"] == entry.id
    assert saved["note"] == "## Visual note"
    assert saved["artifacts"][0]["spec"]["kind"] == "bar"
    assert saved["artifacts"][0]["spec"]["fields"]["x"] == "segment"
    assert saved["artifacts"][0]["spec"]["fields"]["y"] == "amount"
    assert saved["artifacts"][0]["spec"]["filters"][0]["column"] == "amount"

    entries = web.payload["trees"][0]["tree_detail"]["entries"]
    saved_payload = next(item for item in entries if item["id"] == saved["id"])
    assert saved_payload["parent_id"] == entry.id
    assert saved_payload["artifacts"][0]["format"] == "plotly_html"
    assert saved_payload["artifacts"][0]["plotly_json"]["data"]


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
