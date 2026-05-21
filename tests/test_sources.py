import pandas as pd

import stateframe as sf


def test_function_data_source_query_starts_saved_tree(tmp_path):
    sf.sources.clear()
    sf.workspace.configure(root=tmp_path, name="query sources")

    def run_query(query, params=None, **_kwargs):
        assert "customers" in query
        assert params == {"start": "2025-01-01"}
        return pd.DataFrame(
            {
                "customer_id": [1, 2],
                "signup_date": ["2025-01-02", "2025-01-03"],
                "churn": ["No", "Yes"],
            }
        )

    sf.sources.register("warehouse", run_query, display_name="Warehouse")
    scan = sf.query(
        "warehouse",
        "select * from customers where signup_date >= :start",
        params={"start": "2025-01-01"},
        name="customers_2025",
        target="churn",
        save_tree=True,
    )

    assert scan.summary()["row_count"] == 2
    assert scan.source["kind"] == "query"
    assert scan.source["source_id"] == "warehouse"
    assert scan.source["source_name"] == "Warehouse"
    assert scan.source["query_stored"] is True
    assert scan.source["params"] == {"start": "2025-01-01"}
    assert scan.target_profile is not None
    assert any(tree["tree_name"] == "customers_2025" for tree in sf.workspace.list_trees())
    tree_payload = sf.workspace.current().load_tree(scan.tree_id)
    root_entry = tree_payload["profile"]["ledger"]["entries"][0]
    snapshots = [
        artifact
        for artifact in root_entry["artifacts"]
        if artifact["kind"] == "data_snapshot" and artifact["format"] == "parquet"
    ]
    assert snapshots
    snapshot_path = sf.workspace.current().resolve_path(snapshots[0]["path"])
    assert snapshot_path.exists()
    pulled = sf.pull(root_entry["id"], tree=scan.tree_id)
    assert list(pulled["customer_id"]) == [1, 2]

    sf.sources.clear()


def test_query_saved_tree_can_skip_result_snapshot(tmp_path):
    sf.sources.clear()
    sf.workspace.configure(root=tmp_path, name="query without snapshot")

    sf.sources.register(
        "warehouse",
        lambda query, params=None, **_kwargs: pd.DataFrame({"x": [1, 2]}),
    )
    scan = sf.query(
        "warehouse",
        "select * from customers",
        name="customers",
        save_tree=True,
        save_result=False,
    )

    tree_payload = sf.workspace.current().load_tree(scan.tree_id)
    root_entry = tree_payload["profile"]["ledger"]["entries"][0]

    assert root_entry["artifacts"] == []

    sf.sources.clear()


def test_query_source_can_omit_sensitive_query_and_params(tmp_path):
    sf.sources.clear()
    sf.workspace.configure(root=tmp_path, name="sensitive query")

    sf.sources.register(
        "secure",
        lambda query, params=None, **kwargs: sf.QueryResult(
            data=pd.DataFrame({"x": [1]}),
            metadata={"safe_note": "ran through private provider"},
        ),
    )

    scan = sf.query(
        "secure",
        "select * from private.table where token = :token",
        params={"token": "secret"},
        store_query=False,
        store_params=False,
    )

    assert scan.source["query"] is None
    assert scan.source["query_stored"] is False
    assert scan.source["params"] is None
    assert scan.source["params_stored"] is False
    assert scan.source["param_names"] == ["token"]
    assert scan.source["metadata"] == {"safe_note": "ran through private provider"}

    sf.sources.clear()


def test_custom_data_source_lists_objects_and_previews():
    sf.sources.clear()

    class DemoSource(sf.DataSource):
        def __init__(self):
            super().__init__("demo", display_name="Demo")

        def list_objects(self, path=None):
            return [sf.DataObject(name="orders", path="analytics.orders")]

        def preview(self, query, params=None, limit=100, **kwargs):
            return sf.QueryResult(data=pd.DataFrame({"x": [1]}), metadata={"limit": limit})

        def execute(self, query, params=None, **kwargs):
            return sf.QueryResult(data=pd.DataFrame({"x": [1, 2]}))

    sf.sources.register(DemoSource())

    assert sf.sources.list_sources()[0]["id"] == "demo"
    assert sf.sources.list_objects("demo")[0]["path"] == "analytics.orders"
    preview = sf.sources.preview("demo", "select * from analytics.orders", limit=1)
    assert preview.data.shape == (1, 1)
    assert preview.source["preview_limit"] == 1

    sf.sources.clear()


def test_saved_source_connection_auto_imports_for_query(tmp_path):
    sf.sources.clear()
    sf.workspace.configure(root=tmp_path, name="saved sources")
    sf.workspace.init()
    source_file = tmp_path / "company_query_source.py"
    source_file.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "import stateframe as sf",
                "",
                "def register():",
                "    def run_query(query, params=None, **kwargs):",
                "        assert 'sales' in query",
                "        return sf.QueryResult(",
                "            data=pd.DataFrame({'sale_id': [1, 2], 'amount': [10.0, 15.0]}),",
                "            metadata={'system': 'company-data'},",
                "        )",
                "    return sf.sources.register(",
                "        'company_warehouse',",
                "        run_query,",
                "        display_name='Company warehouse',",
                "        description='Internal query source',",
                "    )",
            ]
        ),
        encoding="utf-8",
    )

    saved = sf.sources.save_connection(
        "company_warehouse",
        "company_query_source.py:register",
        display_name="Company warehouse",
        description="Internal query source",
        store_params=False,
        register_now=False,
    )
    assert saved["id"] == "company_warehouse"

    sf.sources.clear()
    scan = sf.query(
        "company_warehouse",
        "select * from sales",
        name="sales_query",
        save_tree=True,
    )

    assert scan.summary()["row_count"] == 2
    assert scan.source["source_id"] == "company_warehouse"
    assert scan.source["metadata"] == {"system": "company-data"}
    assert sf.sources.list_connections()[0]["registered"] is True
    assert any(tree["tree_name"] == "sales_query" for tree in sf.workspace.list_trees())

    from stateframe.interactive.web import build_web_payload

    payload = build_web_payload(sf.workspace.current(), height=500, title=None)
    assert payload["source_connections"][0]["id"] == "company_warehouse"
    assert payload["sources"][0]["id"] == "company_warehouse"

    sf.sources.clear()
