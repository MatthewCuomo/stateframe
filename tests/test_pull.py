import pandas as pd
import pytest

import stateframe as sf
from stateframe.pull import PulledOutput


def test_pull_saved_dataframe_state_by_entry_id(tmp_path):
    sf.workspace.configure(root=tmp_path, name="pull data")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3], "label": ["a", "b", "c"]}), name="features")
    entry = scan.record_state(
        pd.DataFrame({"x": [2, 3], "label": ["b", "c"]}),
        title="Filtered features",
        operation="test.filter",
    )
    scan.save_data(entry_id=entry.id, name="filtered_features")

    pulled = sf.pull(entry.id)

    assert list(pulled["x"]) == [2, 3]
    assert pulled.attrs["_stateframe"]["entry_id"] == entry.id


def test_pull_saved_plot_leaf_returns_renderable_output(tmp_path):
    sf.workspace.configure(root=tmp_path, name="pull output")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="plots")
    entry = scan.record_artifact(
        title="Tiny plot",
        kind="plot",
        operation="test.plot",
        artifact={
            "kind": "plot",
            "format": "plotly_html",
            "title": "Tiny plot",
            "html": "<html><body><div id='plot'>live plot</div></body></html>",
            "preview_data_url": "data:image/png;base64,abc",
        },
        summary={"artifact_kind": "plot"},
    )
    scan.save_tree()

    pulled = sf.pull(entry.id)

    assert isinstance(pulled, PulledOutput)
    assert pulled.reference_code == f"sf.pull('{entry.id}')"
    assert "live plot" in pulled._repr_html_()
    assert "iframe" in pulled._repr_html_()


def test_pull_uses_active_web_selection(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="pull selected")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="selected")
    entry = scan.record_state(
        pd.DataFrame({"x": [1, 3]}),
        title="Odd rows",
        operation="test.filter",
    )
    scan.save_data(entry_id=entry.id, name="odd_rows")
    web = sf.web()
    web.state = {
        **web.current_state(),
        "selectedTreeId": web.payload["trees"][0]["tree_id"],
        "selectedEntryId": entry.id,
    }

    pulled = sf.pull()

    assert list(pulled["x"]) == [1, 3]
