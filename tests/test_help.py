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
