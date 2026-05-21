import pandas as pd
import pytest

import stateframe as sf
from stateframe.leaf import run_leaf_cell


def test_leaf_context_records_stdout_dataframe_and_saved_outputs(tmp_path):
    sf.workspace.configure(root=tmp_path, name="leaf test")
    scan = sf.scan(
        pd.DataFrame(
            {
                "city": ["Jupiter", "Dade"],
                "price": [500_000, 420_000],
            }
        ),
        name="realestate",
    )
    branch = scan.record_state(
        scan.data[scan.data["city"] == "Jupiter"],
        title="Jupiter",
        operation="test.filter",
    )

    recorder = sf.leaf(scan, parent="Jupiter", name="Jupiter print", save=True)
    with recorder:
        print("Jupiter price distribution")
        result = pd.DataFrame({"metric": ["rows"], "value": [1]})

    entry = recorder.entry
    artifact = entry.artifacts[0]

    assert entry.kind == "code_leaf"
    assert entry.parent_id == branch.id
    assert artifact["kind"] == "code_leaf"
    assert artifact["saved"] is True
    assert "stateframe_saves" in artifact["save_dir"]
    assert any(preview["kind"] == "terminal" for preview in artifact["previews"])
    assert any(preview["kind"] == "dataframe" for preview in artifact["previews"])
    assert any(file["format"] == "parquet" for file in artifact["saved_files"])
    assert (tmp_path / "stateframe_saves").exists()


def test_leaf_cell_magic_runner_injects_parent_dataframe(tmp_path):
    sf.workspace.configure(root=tmp_path, name="leaf cell")
    scan = sf.scan(pd.DataFrame({"city": ["Jupiter", "Dade"], "price": [1, 2]}), name="homes")
    branch = scan.record_state(
        scan.data[scan.data["city"] == "Jupiter"],
        title="Jupiter",
        operation="test.filter",
    )

    entry = run_leaf_cell(
        "print(df['city'].iloc[0])\nanswer = int(df['price'].iloc[0])",
        source=scan,
        parent="Jupiter",
        name="Cell leaf",
        namespace={},
    )

    assert entry.parent_id == branch.id
    assert entry.title == "Cell leaf"
    assert entry.artifacts[0]["previews"][0]["stdout"].strip() == "Jupiter"


def test_ipython_leaf_magic_can_be_registered(tmp_path):
    pytest.importorskip("IPython")
    from IPython.core.interactiveshell import InteractiveShell

    sf.workspace.configure(root=tmp_path, name="leaf magic")
    shell = InteractiveShell.instance()
    scan = sf.scan(pd.DataFrame({"x": [1, 2]}), name="numbers")
    shell.user_ns["scan"] = scan
    sf.register_ipython_magics(shell)

    entry = shell.run_cell_magic(
        "sf_leaf",
        '--source scan --name "Magic leaf"',
        "print('magic works')",
    )

    assert entry.kind == "code_leaf"
    assert entry.title == "Magic leaf"
    assert entry.artifacts[0]["previews"][0]["stdout"].strip() == "magic works"

    import matplotlib

    matplotlib.use("Agg", force=True)


def test_leaf_records_plotly_json_html_and_thumbnail(tmp_path):
    px = pytest.importorskip("plotly.express")

    sf.workspace.configure(root=tmp_path, name="leaf plotly")
    scan = sf.scan(pd.DataFrame({"x": [1, 2, 3], "y": [4, 1, 5]}), name="points")

    entry = run_leaf_cell(
        "fig = px.scatter(df, x='x', y='y', title='Live scatter')",
        source=scan,
        name="Plotly leaf",
        save=True,
        namespace={"px": px},
    )
    artifact = entry.artifacts[0]
    preview = next(item for item in artifact["previews"] if item["kind"] == "plotly")

    assert preview["format"] == "plotly_html"
    assert preview["engine"] == "plotly"
    assert preview["plotly_json"]["data"]
    assert preview["html"]
    assert preview["preview_data_url"].startswith("data:image/png;base64,")
    assert any(file["kind"] == "plotly" and file["format"] == "html" for file in artifact["saved_files"])
    assert any(file["kind"] == "plotly" and file["format"] == "json" for file in artifact["saved_files"])
    assert any(file["kind"] == "preview" and file["format"] == "png" for file in artifact["saved_files"])
