from importlib.metadata import version
from pathlib import Path

import stateframe


def test_package_version_matches_public_module_version():
    assert version("stateframe") == stateframe.__version__


def test_interactive_assets_are_present():
    asset_dir = Path(stateframe.__file__).parent / "interactive" / "assets"

    assert (asset_dir / "viewer.js").exists()
    assert (asset_dir / "viewer.css").exists()
    assert (asset_dir / "ledger_tree.js").exists()
    assert (asset_dir / "ledger_tree.css").exists()
    assert (asset_dir / "workspace_web.js").exists()
    assert (asset_dir / "workspace_web.css").exists()


def test_release_scaffolding_exists():
    root = Path(__file__).resolve().parents[1]

    assert (root / "LICENSE").exists()
    assert (root / "MANIFEST.in").exists()
    assert (root / ".github" / "workflows" / "ci.yml").exists()
    assert (root / ".github" / "workflows" / "publish.yml").exists()
