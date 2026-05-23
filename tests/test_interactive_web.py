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
    root_entry = profile.ledger.get(profile.ledger.root_entry_id)
    assert any(
        artifact.get("kind") == "data_snapshot" and artifact.get("format") == "parquet"
        for artifact in root_entry.artifacts
    )
    assert any(tree["tree_name"] == "events" for tree in web.payload["trees"])


def test_web_scan_file_does_not_register_failed_save(tmp_path, monkeypatch):
    pytest.importorskip("anywidget")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "events.csv"
    pd.DataFrame({"x": [1, 2], "label": ["a", "b"]}).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web failed file scan")
    sf.workspace.init()

    from stateframe.models import Profile

    def fail_save_data(self, *args, **kwargs):
        raise RuntimeError("save failed")

    monkeypatch.setattr(Profile, "save_data", fail_save_data)

    web = sf.web()
    with pytest.raises(RuntimeError, match="save failed"):
        web.scan_file("data/events.csv")

    web.refresh()
    assert not any(tree["tree_name"] == "events" for tree in web.payload["trees"])


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
    assert opened["payload"]["suggestions"]
    assert all("spec" in item for item in opened["payload"]["suggestions"])
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

    average_spec = {
        "kind": "bar",
        "title": "Average segment sales",
        "fields": {
            "x": column_ids["segment"],
            "y": column_ids["amount"],
        },
        "field_options": {"y": {"stat": "mean"}},
    }
    average_preview = web.render_visualizer(average_spec)
    assert average_preview["spec"]["field_options"]["y"]["stat"] == "mean"
    assert average_preview["plotly_json"]["layout"]["yaxis"]["title"]["text"] == "Mean of amount"

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
    assert f"sf.pull({entry.id!r})" in saved["code"]
    assert "visual_artifact(data, spec)" in saved["code"]
    assert "visual_artifact(scan, spec)" not in saved["code"]

    entries = web.payload["trees"][0]["tree_detail"]["entries"]
    saved_payload = next(item for item in entries if item["id"] == saved["id"])
    assert saved_payload["parent_id"] == entry.id
    assert saved_payload["artifacts"][0]["format"] == "plotly_html"
    assert saved_payload["artifacts"][0]["plotly_json"]["data"]


def test_web_visualizer_suggestions_use_widget_column_ids(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "properties.csv"
    pd.DataFrame(
        {
            "geo_lat": [26.1, 26.2, 26.3, 26.4],
            "geo_lon": [-80.1, -80.2, -80.3, -80.4],
            "original_list_price": [350000, 425000, 525000, 610000],
            "county": ["Palm Beach", "Palm Beach", "Broward", "Broward"],
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web visualizer geo suggestions")
    sf.scan_path("properties.csv", name="properties").save_tree()

    web = sf.web()
    opened = web.open_visualizer()
    column_ids = {
        column["source_name"]: column["id"]
        for column in opened["payload"]["columns"]
    }
    geo = next(
        item
        for item in opened["payload"]["suggestions"]
        if item["spec"]["kind"] == "geo_scatter"
    )

    assert geo["spec"]["fields"]["lat"] == column_ids["geo_lat"]
    assert geo["spec"]["fields"]["lon"] == column_ids["geo_lon"]
    assert geo["spec"]["fields"]["size"] == column_ids["original_list_price"]
    assert geo["spec"]["fields"]["color"] == column_ids["county"]

    preview = web.render_visualizer(geo["spec"])
    assert preview["format"] == "plotly_html"
    assert preview["plotly_json"]["data"]


def test_web_toolbar_visualizer_from_plot_leaf_uses_parent_state(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "sales.csv"
    pd.DataFrame({"segment": ["A", "B", "C"], "amount": [10, 20, 30]}).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web plot leaf parent")
    scan = sf.scan_path("sales.csv", name="sales")
    scan.save_data(name="root_snapshot", also_save_tree=True)
    root_entry = scan.ledger.root_entry_id
    plot_leaf = scan.record_artifact(
        title="Amount histogram",
        kind="plot",
        operation="visual.histogram",
        parent_id=root_entry,
        artifact={
            "kind": "plot",
            "title": "Amount histogram",
            "spec": {"kind": "histogram", "fields": {"x": "amount"}},
        },
    )
    scan.save_tree()

    web = sf.web()
    tree_id = web.payload["trees"][0]["tree_id"]
    web.state = {
        **web.current_state(),
        "selectedTreeId": tree_id,
        "selectedEntryId": plot_leaf.id,
    }

    web.command = {
        "nonce": "open-plot-leaf-visualizer",
        "action": "open_visualizer",
        "selectedTreeId": tree_id,
        "selectedEntryId": plot_leaf.id,
        "maxRows": 500,
    }

    assert web.command_status["status"] == "ready"
    assert web.visualizer["payload"]["context"]["entry_id"] == root_entry
    assert web.visualizer["payload"]["view"]["row_count"] == 3
    assert web.state["selectedEntryId"] == root_entry
    pulled = web.pull_selected()
    assert pulled["amount"].tolist() == [10, 20, 30]


def test_web_cleaning_workbench_opens_and_saves_branch(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "realestate.csv"
    pd.DataFrame(
        {
            "sold_date": ["2025-01-01", "01/05/2025", "missing"],
            "listed_flag": ["Y", "N", None],
            "price": ["100000", "250000", "N/A"],
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web cleaning")
    scan = sf.scan_path("realestate.csv", name="realestate")
    scan.save_data(name="root_snapshot", also_save_tree=True)

    web = sf.web()
    root_entry = web.payload["trees"][0]["root_entry_id"]
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": root_entry,
    }
    opened = web.open_cleaning()

    actions = opened["payload"]["cleaning"]["actions"]
    presets = opened["payload"]["cleaning"]["presets"]
    assert any(action["action"] == "parse_datetime" for action in actions)
    assert any(action["action"] == "binary_mapping" for action in actions)
    assert {"safe_defaults", "type_prep", "analysis_ready"}.issubset({preset["id"] for preset in presets})
    assert opened["state"]["activePreset"] == "safe_defaults"
    assert opened["state"]["selectedActionIds"]

    saved = web.apply_cleaning_workbench(
        {
            **opened["state"],
            "binaryNullPolicy": "treat_as_false",
            "actionControlValues": {
                action["id"]: {"invalid_policy": "coerce"}
                for action in actions
                if action["action"] in {"parse_numeric", "parse_datetime"}
            },
            "selectedActionIds": [
                action["id"]
                for action in actions
                if action["action"] in {"missing_like_to_null", "parse_datetime", "parse_numeric", "binary_mapping"}
            ],
        }
    )

    assert saved["kind"] == "state"
    assert saved["operation"] == "cleaning.workbench.apply"
    assert saved["parent_id"] == root_entry
    assert saved["summary"]["selected_action_count"] >= 1
    assert saved["summary"]["action_control_override_count"] >= 1
    assert saved["summary"]["active_preset"] == "safe_defaults"

    cleaned = web._cleaning_record_profile.checkout(saved["id"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned["sold_date"])
    assert str(cleaned["listed_flag"].dtype) == "Int64"
    assert cleaned["listed_flag"].tolist() == [1, 0, 0]

    entries = web.payload["trees"][0]["tree_detail"]["entries"]
    saved_payload = next(item for item in entries if item["id"] == saved["id"])
    assert saved_payload["operation"] == "cleaning.workbench.apply"
    assert saved_payload["has_snapshot"] is True

    reloaded = sf.web()
    reloaded.state = {
        **reloaded.current_state(),
        "selectedTreeId": reloaded.payload["trees"][0]["tree_id"],
        "selectedEntryId": saved["id"],
    }
    reloaded_cleaned = reloaded.pull_selected()
    assert reloaded_cleaned["listed_flag"].tolist() == [1, 0, 0]


def test_web_cleaning_workbench_analysis_ready_preset_renames_after_cleaning(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "realestate.csv"
    pd.DataFrame(
        {
            "Sold Date": ["2025-01-01", "01/05/2025", "missing", "2025/03/01"],
            "List Price": ["100000", "120000", "N/A", "130000"],
            "Listed Flag": ["Y", "N", None, "Yes"],
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web cleaning presets")
    scan = sf.scan_path("realestate.csv", name="realestate")
    scan.save_data(name="root_snapshot", also_save_tree=True)

    web = sf.web()
    root_entry = web.payload["trees"][0]["root_entry_id"]
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": root_entry,
    }
    opened = web.open_cleaning()
    preset = next(item for item in opened["payload"]["cleaning"]["presets"] if item["id"] == "analysis_ready")

    saved = web.apply_cleaning_workbench(
        {
            **opened["state"],
            **preset["options"],
            "activePreset": preset["id"],
            "selectedActionIds": preset["selectedActionIds"],
            "actionControlValues": preset["actionControlValues"],
        }
    )

    cleaned = web._cleaning_record_profile.checkout(saved["id"])
    assert saved["summary"]["active_preset"] == "analysis_ready"
    assert cleaned.columns.tolist() == ["sold_date", "list_price", "listed_flag"]
    assert pd.api.types.is_datetime64_any_dtype(cleaned["sold_date"])
    assert pd.api.types.is_numeric_dtype(cleaned["list_price"])
    assert str(cleaned["listed_flag"].dtype) == "Int64"


def test_web_modeling_workbench_opens_and_saves_branch(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "modeling.csv"
    pd.DataFrame(
        {
            "listing_id": [101, 102, 103, 104, 105, 106],
            "city": ["A", "B", "A", "C", "B", None],
            "sqft": [900, 1100, None, 1400, 1600, 1800],
            "sold_date": ["2025-01-01", "2025-02-01", "2025/03/01", None, "Apr 1 2025", "2025-05-01"],
            "sold": [1, 0, 1, 0, 1, 0],
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web modeling")
    scan = sf.scan_path("modeling.csv", name="modeling", target="sold", goal="modeling")
    scan.save_data(name="root_snapshot", also_save_tree=True)

    web = sf.web()
    root_entry = web.payload["trees"][0]["root_entry_id"]
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": root_entry,
    }
    opened = web.open_modeling()

    actions = opened["payload"]["modeling"]["actions"]
    assert any(action["action"] == "modeling.impute_missing" for action in actions)
    assert any(action["action"] == "modeling.encode_one_hot" for action in actions)
    assert opened["payload"]["experiment_catalog"]["estimators"]
    assert opened["payload"]["default_experiment"]["target"] == "sold"
    assert opened["state"]["selectedActionIds"]
    column_ids = {
        column["source_name"]: column["id"]
        for column in opened["payload"]["columns"]
    }

    experiment = web.run_modeling_experiment_workbench(
        {
            **opened["state"],
            "experiment": {
                **opened["state"]["experiment"],
                "target": column_ids["sold"],
                "features": [column_ids["city"], column_ids["sqft"], column_ids["sold_date"]],
                "estimator": "random_forest",
                "explanation": {"enabled": True, "method": "model_importance"},
            },
        }
    )
    assert experiment["task"] == "binary_classification"
    assert experiment["target"] == "sold"
    assert experiment["spec"]["features"] == ["city", "sqft", "sold_date"]
    assert experiment["metrics"]
    assert web.modeling["preview"]["kind"] == "modeling_experiment"

    city_impute = next(action for action in actions if action["column"] == "city" and action["action"] == "modeling.impute_missing")

    saved = web.apply_modeling_workbench(
        {
            **opened["state"],
            "scaleMethod": "standard",
            "actionControlValues": {
                city_impute["id"]: {"strategy": "constant", "fill_value": "Unknown", "add_indicator": True}
            },
        }
    )

    assert saved["kind"] == "state"
    assert saved["operation"] == "modeling.workbench.apply"
    assert saved["parent_id"] == root_entry
    assert saved["summary"]["selected_action_count"] >= 1
    assert saved["summary"]["action_control_override_count"] == 1

    prepared = web._modeling_record_profile.checkout(saved["id"])
    assert "listing_id" not in prepared.columns
    assert "city" not in prepared.columns
    assert "city_A" in prepared.columns
    assert "city_Unknown" in prepared.columns
    assert "sqft_was_imputed" in prepared.columns
    assert "sold" in prepared.columns

    entries = web.payload["trees"][0]["tree_detail"]["entries"]
    saved_payload = next(item for item in entries if item["id"] == saved["id"])
    assert saved_payload["operation"] == "modeling.workbench.apply"
    assert saved_payload["has_snapshot"] is True

    reloaded = sf.web()
    reloaded.state = {
        **reloaded.current_state(),
        "selectedTreeId": reloaded.payload["trees"][0]["tree_id"],
        "selectedEntryId": saved["id"],
    }
    reloaded_prepared = reloaded.pull_selected()
    assert "city_Unknown" in reloaded_prepared.columns


def test_web_modeling_apply_filters_target_derived_actions(tmp_path):
    pytest.importorskip("anywidget")

    source = tmp_path / "price_modeling.csv"
    pd.DataFrame(
        {
            "listing_id": [100 + value for value in range(12)],
            "sold_price": [200_000 + value * 12_000 for value in range(12)],
            "sqft_living": [900 + value * 80 for value in range(12)],
            "city": ["A", "B", "C"] * 4,
        }
    ).to_csv(source, index=False)

    sf.workspace.configure(root=tmp_path, name="web modeling leakage")
    scan = sf.scan_path("price_modeling.csv", name="price_modeling", goal="modeling")
    scan.save_data(name="root_snapshot", also_save_tree=True)

    web = sf.web()
    root_entry = web.payload["trees"][0]["root_entry_id"]
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": root_entry,
    }
    opened = web.open_modeling()
    actions = opened["payload"]["modeling"]["actions"]
    assert any(action["column"] == "sold_price_per_sqft_living" for action in actions)
    column_ids = {
        column["source_name"]: column["id"]
        for column in opened["payload"]["columns"]
    }

    saved = web.apply_modeling_workbench(
        {
            **opened["state"],
            "selectedActionIds": [action["id"] for action in actions],
            "experiment": {
                **opened["state"]["experiment"],
                "target": column_ids["sold_price"],
                "task": "regression",
            },
        }
    )

    prepared = web._modeling_record_profile.checkout(saved["id"])
    assert saved["summary"]["filtered_target_action_count"] >= 1
    assert "sold_price_per_sqft_living" not in prepared.columns


def test_web_command_selection_overrides_stale_widget_state(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="web command selection")
    raw = pd.DataFrame({"x": [1, 2, 3], "y": [5, 6, 7]})
    scan = sf.scan(raw, name="numbers")
    scan.save_data(name="root_snapshot", also_save_tree=True)
    root_entry = scan.ledger.root_entry_id
    branch = scan.record_state(raw.head(1), title="One row branch", parent_id=root_entry)
    scan.save_tree()

    web = sf.web()
    tree_id = web.payload["trees"][0]["tree_id"]
    web.state = {
        **web.current_state(),
        "selectedTreeId": tree_id,
        "selectedEntryId": branch.id,
    }

    web.command = {
        "nonce": "open-root-visualizer",
        "action": "open_visualizer",
        "selectedTreeId": tree_id,
        "selectedEntryId": root_entry,
        "maxRows": 500,
    }

    assert web.visualizer["payload"]["context"]["entry_id"] == root_entry
    assert web.visualizer["payload"]["view"]["row_count"] == 3


def test_web_frontend_message_dispatches_command_when_trait_sync_missing(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="web frontend message")
    raw = pd.DataFrame({"x": [1, 2, 3], "y": [5, 6, 7]})
    scan = sf.scan(raw, name="numbers")
    scan.save_data(name="root_snapshot", also_save_tree=True)
    root_entry = scan.ledger.root_entry_id

    web = sf.web()
    tree_id = web.payload["trees"][0]["tree_id"]
    frontend_state = {
        **web.current_state(),
        "selectedTreeId": tree_id,
        "selectedEntryId": root_entry,
        "viewMode": "visualizer",
    }

    web._handle_frontend_message(
        web,
        {
            "type": "stateframe_command",
            "state": frontend_state,
            "command": {
                "nonce": "frontend-message-open-visualizer",
                "action": "open_visualizer",
                "selectedTreeId": tree_id,
                "selectedEntryId": root_entry,
                "maxRows": 500,
            },
        },
    )

    assert web.command_status["status"] == "ready"
    assert web.command_status["message"] == "Visualizer loaded"
    assert web.visualizer["payload"]["context"]["entry_id"] == root_entry
    assert web.visualizer["payload"]["view"]["row_count"] == 3


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
