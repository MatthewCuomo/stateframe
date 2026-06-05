from importlib.metadata import version
from pathlib import Path

import stateframe


def test_package_version_matches_public_module_version():
    assert version("stateframe") == stateframe.__version__


def test_interactive_assets_are_present():
    asset_dir = Path(stateframe.__file__).parent / "interactive" / "assets"

    assert (asset_dir / "viewer_decom.js").exists()
    assert (asset_dir / "viewer_decom.css").exists()
    assert (asset_dir / "ledger_tree_decom.js").exists()
    assert (asset_dir / "ledger_tree_decom.css").exists()
    assert (asset_dir / "workspace_web.js").exists()
    assert (asset_dir / "workspace_web.css").exists()

    workspace_js = (asset_dir / "workspace_web.js").read_text(encoding="utf-8")
    workspace_css = (asset_dir / "workspace_web.css").read_text(encoding="utf-8")
    assert "renderPlotlyHtmlFrame" in workspace_js
    assert "renderEntryThumbnail" in workspace_js
    assert "plotly_json" in workspace_js
    assert "assignVisualColumnToField" in workspace_js
    assert "wireVisualColumnPointerDrag" in workspace_js
    assert "renderVisualChannelGuardrail" in workspace_js
    assert "renderVisualHealthPanel" in workspace_js
    assert "visualHealthChecks" in workspace_js
    assert "visualColumnMatchesQuery" in workspace_js
    assert "visual-column-query" in workspace_js
    assert "Visual Health" in workspace_js
    assert "color_top_n" in workspace_js
    assert "Sample 10k" in workspace_js
    assert "document.elementFromPoint" in workspace_js
    assert "application/x-stateframe-column-id" in workspace_js
    assert "stateframe-web-visual-field-dropzone" in workspace_js
    assert "item.draggable = true" in workspace_js
    assert "is-drop-target" in workspace_css
    assert "stateframe-web-visual-health" in workspace_css
    assert "stateframe-web-visual-column-tools" in workspace_css


def test_release_scaffolding_exists():
    root = Path(__file__).resolve().parents[1]

    assert (root / "LICENSE").exists()
    assert (root / "MANIFEST.in").exists()
    assert (root / ".github" / "workflows" / "ci.yml").exists()
    assert (root / ".github" / "workflows" / "publish.yml").exists()
