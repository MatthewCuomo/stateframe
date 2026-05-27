import pandas as pd
import pytest

import stateframe as sf


@pytest.fixture(autouse=True)
def _reset_workspace_after_test(tmp_path):
    yield
    sf.sources.clear()
    sf.workspace.configure(root=tmp_path / "reset", name="reset")
    sf.workspace.init()


def test_flow_can_be_saved_from_cell_path_and_run_on_new_dataframe(tmp_path):
    sf.workspace.configure(root=tmp_path, name="flow dataframe")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    root_entry = scan.ledger.active_entry_id
    scan.save_data(entry_id=root_entry, name="root")

    entry = sf.cell(
        f"""
df = sf.pull({root_entry!r})
output = df.assign(y=df["x"] * 10)
""",
        name="Scale x",
        namespace={"sf": sf},
    )

    flow = sf.flow.from_tree("numbers", name="scale flow", entry_id=entry.id)
    result = flow.run(pd.DataFrame({"x": [4, 5]}), name="new numbers")

    assert flow.name == "scale flow"
    assert len(flow.steps) == 1
    assert result.final_entry is not None
    pd.testing.assert_frame_equal(
        result.data.reset_index(drop=True),
        pd.DataFrame({"x": [4, 5], "y": [40, 50]}),
    )
    assert sf.flow.list_flows()[0]["name"] == "scale flow"


def test_flow_reruns_query_root_with_new_params(tmp_path):
    sf.sources.clear()
    sf.workspace.configure(root=tmp_path, name="flow query")

    def run_query(query, params=None, **_kwargs):
        meter = params["meter"]
        return pd.DataFrame({"meter": [meter, meter], "value": [1, 2]})

    sf.sources.register("meter_db", run_query)
    scan = sf.query(
        "meter_db",
        "select * from meter_reads where meter = :meter",
        params={"meter": "A"},
        name="meter A",
        save_tree=True,
    )
    root_entry = scan.ledger.active_entry_id

    entry = sf.cell(
        f"""
df = sf.pull({root_entry!r})
output = df.assign(value_x2=df["value"] * 2)
""",
        name="Meter transform",
        namespace={"sf": sf},
    )
    flow = sf.flow.from_tree("meter A", name="meter inspection", entry_id=entry.id)
    result = flow.run(params={"meter": "B"}, name="meter B")

    assert result.profile.source["params"] == {"meter": "B"}
    assert result.data["meter"].tolist() == ["B", "B"]
    assert result.data["value_x2"].tolist() == [2, 4]
    sf.sources.clear()


def test_flow_payload_is_exposed_on_workspace_web(tmp_path):
    pytest.importorskip("anywidget")

    sf.workspace.configure(root=tmp_path, name="flow web")
    scan = sf.scan(pd.DataFrame({"x": [1]}), name="numbers")
    root_entry = scan.ledger.active_entry_id
    scan.save_data(entry_id=root_entry, name="root")
    flow = sf.flow.from_tree(scan, name="empty path", entry_id=root_entry)

    web = sf.web()

    assert any(item["id"] == flow.id for item in web.payload["flows"])
