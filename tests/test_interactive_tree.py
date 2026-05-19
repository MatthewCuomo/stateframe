import pandas as pd
import pytest

import stateframe as sf
from stateframe.interactive.serialize import build_ledger_payload, initial_ledger_state
from stateframe.interactive.tree import LedgerTreeDependencyError


def test_ledger_payload_tracks_tree_states_and_active_path():
    df = pd.DataFrame(
        {
            "amount": [1, 2, 3, 100],
            "segment": ["a", "a", "b", "b"],
        }
    )
    scan = sf.scan(df)
    scan.run("distribution.numeric", column="amount")
    scan.record_state(
        df.assign(amount_log=[0.0, 0.69, 1.10, 4.61]),
        title="Add log amount",
        operation="features.amount_log",
    )

    payload = build_ledger_payload(scan, height=700, title="Project Tree")
    ledger = payload["ledger"]

    assert payload["title"] == "Project Tree"
    assert payload["view"]["height"] == 700
    assert ledger["stats"]["entry_count"] == 3
    assert ledger["stats"]["state_count"] == 2
    assert ledger["stats"]["kind_counts"]["scan"] == 1
    assert ledger["stats"]["kind_counts"]["lens"] == 1
    assert ledger["stats"]["kind_counts"]["state"] == 1
    assert ledger["active_path"][0]["kind"] == "scan"
    assert ledger["active_path"][-1]["operation"] == "features.amount_log"

    entries = ledger["entries"]
    state_entry = next(entry for entry in entries if entry["kind"] == "state")
    assert state_entry["has_state"] is True
    assert state_entry["state"]["row_count"] == 4
    assert state_entry["path"][0]["kind"] == "scan"
    assert state_entry["path"][-1]["id"] == state_entry["id"]


def test_initial_ledger_state_selects_active_entry():
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3]}))
    scan.run("distribution.numeric", column="x")

    payload = build_ledger_payload(scan)
    state = initial_ledger_state(payload)

    assert state["selectedEntryId"] == payload["ledger"]["active_entry_id"]
    assert state["kindFilter"] == "all"
    assert state["showOnlyStateful"] is False


def test_tree_view_api_reports_missing_interactive_extra_when_not_installed():
    try:
        import anywidget  # noqa: F401
    except ModuleNotFoundError:
        with pytest.raises(LedgerTreeDependencyError):
            sf.tree_view(pd.DataFrame({"x": [1, 2]}))
