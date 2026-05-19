# Release Guide

This guide keeps `stateframe` releases repeatable.

## One-Time Setup

1. Create the public GitHub repository:

   ```powershell
   gh repo create MatthewCuomo/stateframe --public --source=. --remote=origin
   ```

2. Create accounts:

   - PyPI: https://pypi.org/
   - TestPyPI: https://test.pypi.org/

3. Configure trusted publishing.

   In PyPI and TestPyPI, add a trusted publisher for:

   - Owner: `MatthewCuomo`
   - Repository: `stateframe`
   - Workflow for PyPI: `publish.yml`
   - Environment for PyPI: `pypi`
   - Workflow for TestPyPI: `publish-testpypi.yml`
   - Environment for TestPyPI: `testpypi`

4. In GitHub repository settings, create environments named `pypi` and
   `testpypi`. Add required reviewers if you want an approval step before
   publishing.

## Important Repository Hygiene

Keep local datasets, notebook scratch output, and workspace metadata out of the
public repository. The package build is protected by `MANIFEST.in`, but GitHub
still receives anything committed to Git history.

## Pre-Release Checklist

1. Update the version in:

   - `pyproject.toml`
   - `src/stateframe/__init__.py`

2. Update `CHANGELOG.md`.

3. Run:

   ```powershell
   python -m pip install -e ".[dev,ml]"
   python -m pytest
   python -m build
   python -m twine check dist/*
   ```

4. Verify the built source distribution does not include local testing data:

   ```powershell
   tar -tf dist/stateframe-*.tar.gz | Select-String "testing/"
   ```

   The command should produce no dataset entries.

## TestPyPI Release

1. Push to GitHub.
2. Open GitHub Actions.
3. Run `Publish to TestPyPI` manually.
4. Test install in a fresh environment:

   ```powershell
   python -m venv .test-venv
   .\.test-venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple stateframe
   ```

## PyPI Release

1. Create a GitHub release for the version, for example `v0.2.0`.
2. Publishing the GitHub release triggers `Publish to PyPI`.
3. Test the public install:

   ```powershell
   python -m venv .release-venv
   .\.release-venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install stateframe
   ```

## Quick Smoke Test

```python
import pandas as pd
import stateframe as sf

df = pd.DataFrame({"x": [1, 2, 3], "label": ["no", "yes", "no"]})
scan = sf.scan(df, target="label")
viewer = scan.view()
viewer
```
