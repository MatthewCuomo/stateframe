import pandas as pd

import stateframe as sf


def test_scan_starts_ledger_and_lens_runs_append_entries():
    df = pd.DataFrame(
        {
            "amount": [1, 2, 3, 100],
            "segment": ["a", "a", "b", "b"],
        }
    )
    scan = sf.scan(df)

    assert scan.ledger is not None
    assert len(scan.ledger.entries) == 1
    root = scan.ledger.entries[0]
    assert root.kind == "scan"
    assert root.state_id is not None
    assert root.options

    result = scan.run("distribution.numeric", column="amount")

    assert result.id == "distribution.numeric"
    assert len(scan.ledger.entries) == 2
    entry = scan.ledger.entries[-1]
    assert entry.kind == "lens"
    assert entry.parent_id == root.id
    assert entry.operation == "distribution.numeric"
    assert entry.columns == ["amount"]
    assert scan.ledger.path() == [root, entry]


def test_ledger_state_checkpoints_and_checkout():
    df = pd.DataFrame({"x": [1, 2, 3], "group": ["a", "a", "b"]})
    scan = sf.scan(df)

    changed = df.assign(y=[10, 20, 30])
    entry = scan.record_state(
        changed,
        title="Added y",
        operation="feature.add_y",
        note="Feature branch for y.",
    )
    checked_out = scan.checkout(entry.id)

    assert checked_out.equals(changed)
    assert scan.ledger.active_entry_id == entry.id
    assert scan.ledger.get(entry.id).state_id is not None
    assert scan.ledger.get(entry.id).note == "Feature branch for y."
    assert scan.ledger.to_dict(include_states=True)["states"]


def test_profile_records_notes_and_can_activate_branch_points():
    df = pd.DataFrame({"x": [1, 2, 3], "group": ["a", "a", "b"]})
    scan = sf.scan(df)
    root_id = scan.ledger.active_entry_id

    note = scan.record_note("Decision", "Use this branch for group-level checks.")
    scan.activate(root_id)
    scan.run("distribution.numeric", column="x")

    assert note.kind == "note"
    assert scan.ledger.active_entry_id != note.id
    assert scan.ledger_path(note.id)[-1] == note
    tree = scan.ledger_tree()
    assert tree[0]["children"][0]["kind"] == "note"


def test_record_state_can_attach_to_explicit_parent():
    df = pd.DataFrame({"x": [1, 2, 3]})
    scan = sf.scan(df)
    root_id = scan.ledger.active_entry_id

    first = scan.record_state(
        df.assign(y=[2, 4, 6]),
        title="First branch",
        operation="feature.first",
    )
    second = scan.record_state(
        df.assign(z=[3, 6, 9]),
        title="Second branch from root",
        operation="feature.second",
        parent_id=root_id,
    )

    assert first.parent_id == root_id
    assert second.parent_id == root_id
    assert {child.id for child in scan.ledger.children(root_id)} == {first.id, second.id}


def test_record_state_can_store_next_options():
    df = pd.DataFrame({"x": [1, 2, 3]})
    scan = sf.scan(df)

    entry = scan.record_state(
        df,
        title="Named state",
        operation="state.named",
        options=[
            {
                "id": "distribution.numeric.x",
                "title": "Profile x",
                "lens": "distribution.numeric",
                "score": 0.9,
            }
        ],
    )

    assert scan.ledger.get(entry.id).options[0]["lens"] == "distribution.numeric"


def test_ledger_records_profile_transforms_and_exports_markdown():
    df = pd.DataFrame(
        {
            "city": ["Miami", "Miami", "Tampa", "Tampa"] * 10,
            "value": pd.Series([1, 2, 3, 4] * 10, dtype="int64"),
        }
    )
    scan = sf.scan(df)

    optimized = scan.optimize_footprint()

    assert optimized.memory_usage(deep=True).sum() < df.memory_usage(deep=True).sum()
    assert scan.ledger.entries[-1].operation == "footprint.optimize.apply"
    assert scan.checkout(scan.ledger.entries[-1].id).equals(optimized)

    markdown = scan.ledger_report()
    assert "stateframe Lens Ledger" in markdown
    assert "Optimize dataframe footprint" in markdown
