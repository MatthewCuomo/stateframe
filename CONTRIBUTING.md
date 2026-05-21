# Contributing

Thanks for helping make `stateframe` better.

## Local Setup

```powershell
git clone https://github.com/MatthewCuomo/stateframe.git
cd stateframe
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,interactive,ml]"
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,interactive,ml]"
```

## Test

```powershell
python -m pytest
```

## Interactive Widgets

- Use `docs/ui_best_practices.md` as the checklist for shared widget layout,
  redraw, scroll, and artifact-display behavior.
- Any text input that writes to synced widget state on `input` must use a stable
  `data-focus-key` and the local focus/caret restore helper. These widgets
  redraw after state sync, so missing focus keys make the first typed character
  feel like it breaks or recreates the text box.
- For high-frequency text input such as search, prefer a small local draft plus
  a debounce before writing synced state.

## Build

```powershell
python -m build
python -m twine check dist/*
```

The source distribution intentionally excludes the local `testing/` data corpus.
Keep large datasets out of Git; use tiny fixtures under `tests/` for automated
tests and keep large local data in ignored corpus folders.

## Release Discipline

- Update `pyproject.toml` and `src/stateframe/__init__.py` together.
- Update `CHANGELOG.md`.
- Run tests and package checks locally before tagging or creating a GitHub
  release.
- Prefer adding tests with every new lens, semantic inference rule, transform,
  or interactive viewer behavior.
