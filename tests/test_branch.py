import pandas as pd
import pytest

import stateframe as sf
from stateframe.replay import replay_tree_state


def test_custom_branch_records_replayable_dataframe_state(tmp_path):
    sf.workspace.configure(root=tmp_path, name="custom branches")
    source_path = tmp_path / "sales.csv"
    raw = pd.DataFrame(
        {
            "city": ["Jupiter", "Miami", "Jupiter"],
            "price": [400_000, 500_000, 650_000],
            "sqft": [2000, 2500, 2600],
        }
    )
    raw.to_csv(source_path, index=False)

    scan = sf.scan_path(str(source_path), name="sales")
    root_id = scan.ledger.active_entry_id
    recorder = sf.branch(scan)
    input_frame = recorder.input()
    result = input_frame[input_frame["city"] == "Jupiter"].copy()
    result["price_per_sqft"] = result["price"] / result["sqft"]

    code = """
output = df[df["city"] == "Jupiter"].copy()
output["price_per_sqft"] = output["price"] / output["sqft"]
"""
    entry = recorder.save_data(
        result,
        name="Jupiter price features",
        message="Filtered Jupiter and added price per sqft.",
        code=code,
    )

    assert input_frame.attrs["_stateframe"]["entry_id"] == root_id
    assert entry.parent_id == root_id
    assert entry.operation == "custom.transform"
    assert entry.code == code.strip()
    assert entry.params["custom"]["replayable"] is True

    payload = sf.save.load_tree(tree="sales")
    saved_entry = next(item for item in payload["profile"]["ledger"]["entries"] if item["id"] == entry.id)
    assert saved_entry["code"] == code.strip()

    replayed = replay_tree_state(
        payload,
        workspace=sf.workspace.current(),
        entry_id=entry.id,
    )
    pd.testing.assert_frame_equal(
        replayed.reset_index(drop=True),
        result.reset_index(drop=True),
    )


def test_custom_branch_records_plot_artifact_under_parent_state(tmp_path):
    sf.workspace.configure(root=tmp_path, name="custom artifacts")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    root_id = scan.ledger.active_entry_id
    root_state_id = scan.ledger.get(root_id).state_id

    entry = sf.branch(scan).save_plot(
        {"format": "plotly", "path": "plots/x_hist.html"},
        name="x histogram",
        message="Histogram for x.",
        code="artifact = px.histogram(df, x='x')",
    )

    assert entry.parent_id == root_id
    assert entry.kind == "plot"
    assert entry.operation == "custom.plot"
    assert entry.state_id == root_state_id
    assert entry.artifacts[0]["path"] == "plots/x_hist.html"
    assert entry.params["custom"]["kind"] == "python_artifact"


def test_custom_branch_records_plotly_figure_as_live_artifact(tmp_path):
    px = pytest.importorskip("plotly.express")

    sf.workspace.configure(root=tmp_path, name="custom plotly artifacts")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3], "y": [3, 1, 4]}), name="numbers")
    figure = px.line(scan.data, x="x", y="y", title="Live line")

    entry = sf.branch(scan).save_plot(figure, name="line")
    artifact = entry.artifacts[0]

    assert artifact["format"] == "plotly_html"
    assert artifact["engine"] == "plotly"
    assert artifact["plotly_json"]["data"]
    assert artifact["html"]
    assert artifact["preview_data_url"].startswith("data:image/png;base64,")


def test_viewer_save_branch_request_records_state(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="viewer branch button")
    scan = sf.scan(pd.DataFrame({"city": ["A", "B"], "value": [1, 2]}), name="cities")
    viewer = scan.view()

    viewer.branch_request = {
        "nonce": "save-1",
        "name": "Saved From UI",
        "message": "Saved through the widget button.",
    }

    entry = viewer.last_checkpoint_entry()
    assert entry is not None
    assert entry.operation == "viewer.save_branch"
    assert entry.params["output_name"] == "Saved From UI"
    assert viewer.branch_status["status"] == "saved"
    assert sf.workspace.current().tree_path_for_profile(scan).exists()
