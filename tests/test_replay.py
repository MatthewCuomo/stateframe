import pandas as pd
import pytest

import stateframe as sf
from stateframe.replay import ReplayError, replay_tree_state


def test_replay_tree_state_from_editable_source_path(tmp_path):
    sf.workspace.configure(root=tmp_path, name="replay test")
    source_path = tmp_path / "realestate.csv"
    raw = pd.DataFrame(
        {
            "county": ["Palm Beach", "Palm Beach", "Martin"],
            "city": ["Jupiter", "Boca Raton", "Stuart"],
            "price": [500_000, 450_000, 375_000],
            "agent": ["A", "B", "C"],
        }
    )
    raw.to_csv(source_path, index=False)

    scan = sf.scan(raw, name="realestate", source_path=source_path)
    county = raw[raw["county"] == "Palm Beach"]
    county_entry = scan.record_state(
        county,
        title="Pull viewer state as County Palm Beach",
        operation="viewer.pull",
        viewer_summary={
            "source": "interactive_dataframe_viewer",
            "filters": {
                "county": {
                    "kind": "text",
                    "mode": "equals",
                    "value": "Palm Beach",
                }
            },
            "sorts": [],
            "hidden_columns": [],
            "column_order": list(raw.columns),
            "global_search": "",
        },
    )
    jupiter = county[county["city"] == "Jupiter"][["city", "county", "price"]]
    jupiter_entry = scan.record_state(
        jupiter,
        title="Pull viewer state as Jupiter in Palm Beach County",
        operation="viewer.pull",
        parent_id=county_entry.id,
        viewer_summary={
            "source": "interactive_dataframe_viewer",
            "filters": {
                "city": {
                    "kind": "text",
                    "mode": "equals",
                    "value": "Jupiter",
                }
            },
            "sorts": [],
            "hidden_columns": ["agent"],
            "column_order": ["city", "county", "price", "agent"],
            "global_search": "",
        },
    )
    scan.save_tree()

    payload = sf.workspace.load_tree("realestate")
    restored = replay_tree_state(
        payload,
        workspace=sf.workspace.current(),
        entry_id=jupiter_entry.id,
    )

    pd.testing.assert_frame_equal(
        restored.reset_index(drop=True),
        jupiter.reset_index(drop=True),
    )


def test_update_tree_source_path_allows_replay_after_file_moves(tmp_path):
    sf.workspace.configure(root=tmp_path, name="moved source")
    original_path = tmp_path / "old.csv"
    moved_path = tmp_path / "new.csv"
    raw = pd.DataFrame({"x": [1, 2, 3], "label": ["a", "b", "b"]})
    raw.to_csv(original_path, index=False)

    scan = sf.scan(raw, name="events")
    entry = scan.record_state(
        raw[raw["label"] == "b"],
        title="Label b",
        operation="viewer.pull",
        viewer_summary={
            "source": "interactive_dataframe_viewer",
            "filters": {
                "label": {"kind": "text", "mode": "equals", "value": "b"}
            },
            "sorts": [],
            "hidden_columns": [],
            "column_order": ["x", "label"],
            "global_search": "",
        },
    )
    scan.save_tree()
    raw.to_csv(moved_path, index=False)

    updated = scan.set_source_path(moved_path)
    payload = sf.workspace.load_tree("events")
    restored = replay_tree_state(
        payload,
        workspace=sf.workspace.current(),
        entry_id=entry.id,
    )

    assert updated["source"]["path"] == "new.csv"
    assert updated["source"]["path_root"] == "workspace"
    assert restored["label"].tolist() == ["b", "b"]


def test_replay_requires_replayable_source_for_dataframe_only_tree(tmp_path):
    sf.workspace.configure(root=tmp_path, name="not replayable")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}), name="numbers")
    scan.save_tree()

    with pytest.raises(ReplayError, match="not file-backed"):
        replay_tree_state(
            sf.workspace.load_tree("numbers"),
            workspace=sf.workspace.current(),
        )


def test_replay_uses_saved_reader_params(tmp_path):
    sf.workspace.configure(root=tmp_path, name="reader params")
    source_path = tmp_path / "events.csv"
    raw = pd.DataFrame({"x": [1, 2, 3, 4], "label": ["a", "b", "b", "b"]})
    raw.to_csv(source_path, index=False)

    scan = sf.scan_path(source_path, name="events", reader_params={"nrows": 2})
    entry = scan.record_state(
        pd.DataFrame({"x": [2], "label": ["b"]}, index=[1]),
        title="Label b",
        operation="viewer.pull",
        viewer_summary={
            "source": "interactive_dataframe_viewer",
            "filters": {
                "label": {"kind": "text", "mode": "equals", "value": "b"}
            },
            "sorts": [],
            "hidden_columns": [],
            "column_order": ["x", "label"],
            "global_search": "",
        },
    )
    scan.save_tree()

    restored = replay_tree_state(
        sf.workspace.load_tree("events"),
        workspace=sf.workspace.current(),
        entry_id=entry.id,
    )

    assert restored["x"].tolist() == [2]
