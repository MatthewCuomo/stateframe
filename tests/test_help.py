import stateframe as sf


def test_help_returns_quick_start_text():
    guide = sf.help()

    assert isinstance(guide, str)
    assert "Stateframe quick start:" in guide
    assert 'sf.workspace.configure(root="PATH_TO_PROJECT_ROOT", name="my-project")' in guide
    assert "web = sf.web(height=720)" in guide
    assert "scan.save_tree()" in guide
    assert "df = web.pull()" in guide


def test_help_renders_as_markdown_code_block():
    guide = sf.help()

    assert guide._repr_markdown_().startswith("```text\nStateframe quick start:")


def test_help_getdata_explains_custom_query_sources():
    guide = sf.help_getdata()

    assert isinstance(guide, str)
    assert "Stateframe Get Data and query-source setup:" in guide
    assert "sf.sources.register" in guide
    assert "sf.sources.save_connection" in guide
    assert "sf.query" in guide
    assert "company_query_source.py:register" in guide
    assert "Adapt your existing data entry point" in guide
    assert "does not stream partial rows" in guide
    assert "store_query=False" in guide


def test_help_namespace_supports_get_data():
    guide = sf.help.get_data()

    assert isinstance(guide, str)
    assert "Get Data -> Query Data" in guide
    assert "auto-import" in guide


def test_help_tree_workflow_explains_pull_and_add():
    guide = sf.help.tree_workflow()

    assert isinstance(guide, str)
    assert "Stateframe tree pull/add workflow:" in guide
    assert 'sf.pull("state-entry_abc123")' in guide
    assert "sf.branch(web)" in guide
    assert "custom.save_data" in guide
    assert "custom.save_plot" in guide
    assert "%%sf_leaf" in guide


def test_help_tree_aliases():
    assert sf.help.pull_tree() == sf.help.tree_workflow()
    assert sf.help_tree() == sf.help.tree_workflow()
