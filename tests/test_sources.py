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
