import pandas as pd
import pytest

import stateframe as sf
from stateframe.interactive.serialize import (
    apply_view_state,
    build_viewer_payload,
    summarize_draft_state,
    summarize_view_state,
    view_state_signature,
)
from stateframe.interactive.viewer import InteractiveDependencyError


def test_viewer_payload_includes_rows_columns_and_column_intelligence():
    df = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4],
            "signup_date": ["2024-01-01", "2024-01-02", "2024-01-10", None],
            "churn": ["No", "No", "Yes", "No"],
            "total_charges": ["10.00", "20.00", "30.00", "40.00"],
        }
    )

    profile = sf.scan(df, target="churn")
    payload = build_viewer_payload(profile, max_rows=3, height=500, title="Customers")

    assert payload["title"] == "Customers"
    assert payload["view"]["height"] == 500
    assert payload["view"]["displayed_row_count"] == 3
    assert payload["view"]["truncated"] is True
    assert len(payload["rows"]) == 3
    assert payload["ledger"]["entries"][0]["kind"] == "scan"
    assert [column["display_name"] for column in payload["columns"]] == list(df.columns)

    charges = next(column for column in payload["columns"] if column["display_name"] == "total_charges")
    assert charges["semantic_type"] == "numeric-like"
    assert charges["histogram"] is not None

    churn = next(column for column in payload["columns"] if column["display_name"] == "churn")
    assert churn["binary_profile"] is not None
    assert any(rec["lens"] == "target.balance" for rec in churn["recommendations"])


def test_viewer_payload_keeps_cleaning_plan_opt_in():
    df = pd.DataFrame(
        {
            "flag": ["Yes", "No", None],
            "amount": [10, None, 30],
        }
    )
    profile = sf.scan(df)

    payload = build_viewer_payload(profile)
    payload_with_cleaning = build_viewer_payload(profile, include_cleaning=True)

    assert "cleaning" not in payload
    assert payload_with_cleaning["cleaning"]["actions"]


def test_apply_view_state_filters_sorts_and_reorders_dataframe():
    df = pd.DataFrame(
        {
            "name": ["Ada", "Grace", "Alan", "Katherine"],
            "score": [10, 30, 20, 40],
            "team": ["red", "blue", "red", "blue"],
        }
    )
    profile = sf.scan(df)
    payload = build_viewer_payload(profile)
    ids = {column["display_name"]: column["id"] for column in payload["columns"]}

    state = {
        "columnOrder": [ids["score"], ids["name"], ids["team"]],
        "hiddenColumnIds": [ids["team"]],
        "sorts": [{"id": ids["score"], "direction": "desc"}],
        "filters": {ids["team"]: {"kind": "text", "mode": "contains", "value": "red"}},
        "globalSearch": "",
        "selectedColumnId": ids["score"],
        "showIndex": True,
        "widths": {},
    }

    result = apply_view_state(df, payload, state)

    assert list(result.columns) == ["score", "name"]
    assert result["name"].tolist() == ["Alan", "Ada"]


def test_view_state_summary_uses_column_names_for_ledger_metadata():
    df = pd.DataFrame(
        {
            "name": ["Ada", "Grace", "Alan", "Katherine"],
            "score": [10, 30, 20, 40],
            "team": ["red", "blue", "red", "blue"],
        }
    )
    profile = sf.scan(df)
    payload = build_viewer_payload(profile)
    ids = {column["display_name"]: column["id"] for column in payload["columns"]}

    state = {
        "columnOrder": [ids["score"], ids["name"], ids["team"]],
        "hiddenColumnIds": [ids["team"]],
        "sorts": [{"id": ids["score"], "direction": "desc"}],
        "filters": {ids["team"]: {"kind": "text", "mode": "equals", "value": "red"}},
        "globalSearch": "",
        "selectedColumnId": ids["score"],
        "showIndex": True,
        "widths": {},
    }

    result = apply_view_state(df, payload, state)
    summary = summarize_view_state(payload, state, result)
    signature = view_state_signature(payload, state)

    assert summary["row_count"] == 2
    assert summary["column_count"] == 2
    assert summary["column_order"] == ["score", "name", "team"]
    assert summary["hidden_columns"] == ["team"]
    assert summary["sorts"] == [{"column": "score", "direction": "desc"}]
    assert summary["filters"] == {"team": {"kind": "text", "mode": "equals", "value": "red"}}
    assert summary["selected_column"] == "score"
    assert "team" in signature


def test_draft_summary_surfaces_unsaved_viewer_changes():
    df = pd.DataFrame({"name": ["Ada", "Grace"], "team": ["red", "blue"]})
    profile = sf.scan(df)
    payload = build_viewer_payload(profile)
    ids = {column["display_name"]: column["id"] for column in payload["columns"]}
    state = {
        "columnOrder": [ids["team"], ids["name"]],
        "hiddenColumnIds": [ids["team"]],
        "sorts": [{"id": ids["name"], "direction": "asc"}],
        "filters": {ids["team"]: {"kind": "text", "mode": "equals", "value": "red"}},
        "globalSearch": "ada",
        "selectedColumnId": ids["name"],
        "showIndex": True,
        "widths": {},
    }

    summary = summarize_draft_state(payload, state)

    labels = {item["kind"]: item["label"] for item in summary["pills"]}
    assert summary["has_changes"] is True
    assert labels["filters"] == "1 filter"
    assert labels["search"] == "search: ada"
    assert labels["hidden_columns"] == "1 offloaded"
    assert labels["column_order"] == "reordered columns"


def test_view_launches_shared_web_viewer_surface():
    pytest.importorskip("anywidget")
    from stateframe.interactive.web import WorkspaceWebViewer

    viewer = sf.view(pd.DataFrame({"x": [1, 2, 3]}), name="numbers", max_rows=2)

    assert isinstance(viewer, WorkspaceWebViewer)
    assert viewer.state["viewMode"] == "viewer"
    assert viewer.payload["trees"][0]["tree_name"] == "numbers"
    assert viewer.viewer["status"] == "ready"
    assert viewer.viewer["payload"]["view"]["displayed_row_count"] == 2


def test_view_api_reports_missing_interactive_extra_when_not_installed():
    try:
        import anywidget  # noqa: F401
    except ModuleNotFoundError:
        with pytest.raises(InteractiveDependencyError):
            sf.view(pd.DataFrame({"x": [1, 2]}))
