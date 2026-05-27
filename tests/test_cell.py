import pandas as pd
import pytest

import stateframe as sf


@pytest.fixture(autouse=True)
def _reset_workspace_after_test(tmp_path):
    yield
    sf.workspace.configure(root=tmp_path / "reset", name="reset")
    sf.workspace.init()


def test_sf_cell_infers_parent_from_pull_and_saves_output_branch(tmp_path):
    sf.workspace.configure(root=tmp_path, name="cell capture")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    root_entry = scan.ledger.active_entry_id
    scan.save_data(entry_id=root_entry, name="root")

    entry = sf.cell(
        f"""
df = sf.pull({root_entry!r})
output = df.assign(y=df["x"] * 2)
""",
        name="Double x",
        save=True,
        namespace={"sf": sf},
    )

    assert entry.operation == "cell.transform"
    assert entry.parent_id == root_entry
    assert entry.code == 'output = df.assign(y=df["x"] * 2)'
    assert entry.params["cell"]["captured_code"]
    assert entry.params["cell"]["replay_code"] == entry.code
    assert entry.params["dependencies"][0]["entry_id"] == root_entry
    assert entry.params["dependencies"][0]["variable"] == "df"

    payload = sf.workspace.current().load_tree(scan.tree_id)
    saved_entry = next(item for item in payload["profile"]["ledger"]["entries"] if item["id"] == entry.id)
    assert any(artifact["kind"] == "data_snapshot" for artifact in saved_entry["artifacts"])


def test_sf_cell_records_multiple_pull_dependencies(tmp_path):
    sf.workspace.configure(root=tmp_path, name="multi cell capture")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    first = scan.record_state(pd.DataFrame({"x": [1]}), title="First", operation="state.test")
    second = scan.record_state(pd.DataFrame({"x": [2]}), title="Second", operation="state.test")
    scan.save_data(entry_id=first.id, name="first")
    scan.save_data(entry_id=second.id, name="second")

    entry = sf.cell(
        f"""
left = sf.pull({first.id!r})
right = sf.pull({second.id!r})
output = pd.concat([left, right], ignore_index=True)
""",
        name="Combine pulls",
        namespace={"sf": sf, "pd": pd},
    )

    dependencies = entry.params["dependencies"]
    assert entry.parent_id == first.id
    assert [item["entry_id"] for item in dependencies] == [first.id, second.id]
    assert [item["variable"] for item in dependencies] == ["left", "right"]


def test_push_uses_recent_pull_context_as_parent(tmp_path):
    sf.workspace.configure(root=tmp_path, name="push capture")
    scan = sf.scan(pd.DataFrame({"x": [1, 2]}), name="numbers")
    root_entry = scan.ledger.active_entry_id
    scan.save_data(entry_id=root_entry, name="root")

    df = sf.pull(root_entry)
    output = df.assign(y=df["x"] + 1)
    entry = sf.push(output, name="Plus one", save=True)

    assert entry.parent_id == root_entry
    assert entry.params["dependencies"][0]["entry_id"] == root_entry
    pd.testing.assert_frame_equal(
        sf.pull(entry.id).reset_index(drop=True),
        pd.DataFrame({"x": [1, 2], "y": [2, 3]}),
    )
