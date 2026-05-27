"""Notebook-friendly code leaf capture for stateframe."""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import linecache
import re
import shlex
import textwrap
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from stateframe.models import Profile


_SAVE_MODE = False


def save_mode(enabled: bool = True) -> bool:
    """Toggle default durable saving for newly recorded leaves."""

    global _SAVE_MODE
    _SAVE_MODE = bool(enabled)
    return _SAVE_MODE


def is_save_mode() -> bool:
    """Return whether newly recorded leaves save outputs by default."""

    return _SAVE_MODE


def leaf(
    source: Any | None = None,
    *,
    parent: str | None = None,
    name: str | None = None,
    message: str | None = None,
    note: str | None = None,
    code: str | None = None,
    save: bool | None = None,
    save_path: str | Path | None = None,
    standalone: bool = False,
    autosave_tree: bool = True,
) -> "LeafRecorder":
    """Create a context manager that records arbitrary user code as a leaf.

    In notebooks, ``%%sf_leaf`` is usually the cleanest way to capture a whole
    code cell. In regular Python, use this as ``with sf.leaf(...):``.
    """

    if isinstance(source, str) and parent is None:
        parent = source
        source = None
    profile, parent_id = _resolve_profile_and_parent(source, parent)
    return LeafRecorder(
        profile=profile,
        parent_id=parent_id,
        parent_label=parent,
        name=name,
        message=message,
        note=note,
        code=code,
        save=save,
        save_path=save_path,
        standalone=standalone,
        autosave_tree=autosave_tree,
    )


@dataclass
class LeafRecorder:
    """Capture a block of Python work and save it as a code leaf."""

    profile: Profile
    parent_id: str | None
    parent_label: str | None = None
    name: str | None = None
    message: str | None = None
    note: str | None = None
    code: str | None = None
    save: bool | None = None
    save_path: str | Path | None = None
    standalone: bool = False
    autosave_tree: bool = True
    entry: Any = None
    stdout: io.StringIO = field(default_factory=io.StringIO, init=False)
    stderr: io.StringIO = field(default_factory=io.StringIO, init=False)
    _stdout_cm: Any = field(default=None, init=False, repr=False)
    _stderr_cm: Any = field(default=None, init=False, repr=False)
    _frame: Any = field(default=None, init=False, repr=False)
    _namespace_override: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _start_lineno: int | None = field(default=None, init=False, repr=False)
    _before_locals: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _before_figures: set[int] = field(default_factory=set, init=False, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Return the parent dataframe for code that wants an explicit input."""

        if self.parent_id is None:
            raise ValueError("This leaf has no parent dataframe state.")
        return self.profile.checkout(self.parent_id)

    def __enter__(self) -> "LeafRecorder":
        caller = inspect.currentframe().f_back
        self._frame = caller
        self._start_lineno = caller.f_lineno if caller is not None else None
        namespace = self._namespace_override if self._namespace_override is not None else (
            caller.f_locals if caller is not None else {}
        )
        self._before_locals = {
            key: id(value)
            for key, value in namespace.items()
        }
        self._before_figures = _matplotlib_figure_numbers()
        self._stdout_cm = contextlib.redirect_stdout(self.stdout)
        self._stderr_cm = contextlib.redirect_stderr(self.stderr)
        self._stdout_cm.__enter__()
        self._stderr_cm.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        if exc is not None:
            traceback.print_exception(exc_type, exc, tb, file=self.stderr)
        self._stderr_cm.__exit__(exc_type, exc, tb)
        self._stdout_cm.__exit__(exc_type, exc, tb)
        code_text = self.code or _extract_with_block_code(self._frame, self._start_lineno)
        namespace = self._namespace_override if self._namespace_override is not None else (
            self._frame.f_locals if self._frame is not None else {}
        )
        previews = _collect_previews(
            namespace,
            before_locals=self._before_locals,
            before_figures=self._before_figures,
            stdout=self.stdout.getvalue(),
            stderr=self.stderr.getvalue(),
        )
        self.entry = record_leaf(
            self.profile,
            parent_id=self.parent_id,
            code=code_text,
            previews=previews,
            name=self.name,
            message=self.message,
            note=self.note,
            save=self.save,
            save_path=self.save_path,
            standalone=self.standalone,
            autosave_tree=self.autosave_tree,
            parent_label=self.parent_label,
        )
        return False


def record_leaf(
    profile: Profile,
    *,
    parent_id: str | None,
    code: str,
    previews: list[dict[str, Any]],
    name: str | None = None,
    message: str | None = None,
    note: str | None = None,
    save: bool | None = None,
    save_path: str | Path | None = None,
    standalone: bool = False,
    autosave_tree: bool = True,
    parent_label: str | None = None,
    dependencies: list[dict[str, Any]] | None = None,
) -> Any:
    """Record an already-executed code leaf under a profile ledger."""

    title = name or _auto_name(code, previews)
    save_outputs = _SAVE_MODE if save is None else bool(save)
    dependency_edges = list(dependencies or [])
    artifact = {
        "kind": "code_leaf",
        "format": "stateframe.code_leaf.v1",
        "title": title,
        "code": code.strip(),
        "previews": previews,
        "dependency": (
            "standalone"
            if standalone
            else (f"{len(dependency_edges)} inputs" if len(dependency_edges) > 1 else "branch")
        ),
        "dependencies": dependency_edges,
        "parent_entry_id": parent_id,
        "parent_label": parent_label,
        "saved": False,
    }
    if save_outputs:
        from stateframe.artifacts import persist_artifact_files

        artifact = persist_artifact_files(
            artifact,
            profile=profile,
            entry_label=title,
            base_path=save_path,
        )
    artifact["previews"] = _strip_runtime_payloads(artifact.get("previews") or [])
    entry = profile.record_artifact(
        title=title,
        kind="code_leaf",
        operation="leaf.code",
        parent_id=parent_id,
        artifact=artifact,
        summary={
            "artifact_kind": "code_leaf",
            "output_name": title,
            "preview_count": len(previews),
            "has_stdout": any(preview.get("stdout") for preview in previews),
            "has_stderr": any(preview.get("stderr") for preview in previews),
            "saved": bool(artifact.get("saved")),
            "dependency": artifact["dependency"],
            "dependency_count": len(dependency_edges),
        },
        code=code.strip(),
        note=note or message or "",
        message=message,
        leaf={
            "kind": "code",
            "replayable": bool(code.strip()),
            "standalone": bool(standalone),
            "saved": bool(artifact.get("saved")),
        },
        dependencies=dependency_edges,
    )
    if autosave_tree:
        profile.save_tree()
    return entry


def run_leaf_cell(
    cell: str,
    *,
    source: Any | None = None,
    parent: str | None = None,
    name: str | None = None,
    message: str | None = None,
    save: bool | None = None,
    save_path: str | Path | None = None,
    standalone: bool = False,
    namespace: dict[str, Any] | None = None,
) -> Any:
    """Execute and record a cell body as a code leaf."""

    recorder = leaf(
        source,
        parent=parent,
        name=name,
        message=message,
        code=cell,
        save=save,
        save_path=save_path,
        standalone=standalone,
    )
    ns = namespace if namespace is not None else {}
    if not standalone and "df" not in ns and recorder.parent_id is not None:
        ns["df"] = recorder.df
    recorder._namespace_override = ns
    with recorder:
        exec(cell, ns, ns)
    return recorder.entry


def register_ipython_magics(ipython: Any | None = None) -> None:
    """Register ``%%sf_leaf`` and ``%%sf_cell`` in an IPython/Jupyter shell."""

    if ipython is None:
        from IPython import get_ipython

        ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("No active IPython shell is available.")

    def sf_leaf(line: str, cell: str) -> Any:
        args = _parse_magic_args(line)
        source = ipython.user_ns.get(args.source) if args.source else None
        return run_leaf_cell(
            cell,
            source=source,
            parent=args.parent,
            name=args.name,
            message=args.message,
            save=args.save,
            save_path=args.save_at,
            standalone=args.standalone,
            namespace=ipython.user_ns,
        )

    def sf_cell(line: str, cell: str) -> Any:
        args = _parse_cell_magic_args(line)
        source = ipython.user_ns.get(args.source) if args.source else None
        from stateframe.cell import run_cell

        return run_cell(
            cell,
            source=source,
            parent=args.parent,
            name=args.name,
            message=args.message,
            save=args.save,
            save_path=args.save_at,
            namespace=ipython.user_ns,
            output=args.output,
        )

    ipython.register_magic_function(sf_leaf, magic_kind="cell", magic_name="sf_leaf")
    ipython.register_magic_function(sf_cell, magic_kind="cell", magic_name="sf_cell")


def _parse_magic_args(line: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="%%sf_leaf", add_help=False)
    parser.add_argument("--parent")
    parser.add_argument("--name")
    parser.add_argument("--message")
    parser.add_argument("--source")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--save-at")
    parser.add_argument("--standalone", action="store_true")
    return parser.parse_args(shlex.split(line or ""))


def _parse_cell_magic_args(line: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="%%sf_cell", add_help=False)
    parser.add_argument("--parent")
    parser.add_argument("--name")
    parser.add_argument("--message")
    parser.add_argument("--source")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--save-at")
    parser.add_argument("--output", default="output")
    return parser.parse_args(shlex.split(line or ""))


def _resolve_profile_and_parent(source: Any | None, parent: str | None) -> tuple[Profile, str | None]:
    if source is None:
        source = _default_profile()
    if isinstance(source, Profile):
        profile = source
        if profile.ledger is None:
            from stateframe.ledger import LensLedger

            profile.ledger = LensLedger.start(profile)
        return profile, _resolve_parent_id(profile, parent)
    if hasattr(source, "selected_profile") and hasattr(source, "selected_entry_id"):
        profile = source.selected_profile()
        selected = parent or source.selected_entry_id()
        return profile, _resolve_parent_id(profile, selected)
    if hasattr(source, "record_profile") and isinstance(source.record_profile, Profile):
        profile = source.record_profile
        selected = parent or getattr(source, "ledger_parent_id", None)
        return profile, _resolve_parent_id(profile, selected)
    if isinstance(source, pd.DataFrame):
        from stateframe.branch import _resolve_profile_and_parent as branch_resolve

        profile, selected, _factory = branch_resolve(source, parent)
        return profile, _resolve_parent_id(profile, selected)
    raise TypeError("sf.leaf(...) needs a Profile, web/tree/viewer object, or stateframe-tracked DataFrame.")


def _default_profile() -> Profile:
    from stateframe.save import registered_profiles

    profiles = registered_profiles()
    if not profiles:
        raise ValueError(
            "No active stateframe profile is available. Pass a scan/web/viewer "
            "object to sf.leaf(...), or create one first with sf.scan(...)."
        )
    return profiles[-1]


def _resolve_parent_id(profile: Profile, parent: str | None) -> str | None:
    ledger = profile.ledger
    if ledger is None:
        return None
    if parent is None:
        return ledger.active_entry_id
    wanted = str(parent).strip()
    by_id = {entry.id: entry for entry in ledger.entries}
    if wanted in by_id:
        return wanted
    lowered = wanted.lower()
    exact = [
        entry
        for entry in ledger.entries
        if lowered
        in {
            str(entry.title or "").lower(),
            str(entry.operation or "").lower(),
            str(entry.params.get("output_name", "")).lower(),
            str((entry.params.get("custom") or {}).get("output_name", "")).lower()
            if isinstance(entry.params.get("custom"), dict)
            else "",
        }
    ]
    if len(exact) == 1:
        return exact[0].id
    contains = [
        entry
        for entry in ledger.entries
        if lowered in str(entry.title or "").lower()
    ]
    if len(contains) == 1:
        return contains[0].id
    if len(exact) > 1 or len(contains) > 1:
        raise ValueError(f"Branch name {parent!r} is ambiguous. Use an entry id.")
    raise ValueError(f"No branch named {parent!r} exists in this stateframe tree.")


def _collect_previews(
    namespace: dict[str, Any],
    *,
    before_locals: dict[str, int],
    before_figures: set[int],
    stdout: str,
    stderr: str,
) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    if stdout or stderr:
        previews.append({
            "kind": "terminal",
            "stdout": stdout,
            "stderr": stderr,
        })
    previews.extend(_matplotlib_previews(before_figures))
    previews.extend(_namespace_previews(namespace, before_locals))
    return previews


def _strip_runtime_payloads(previews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for preview in previews:
        clean = dict(preview)
        clean.pop("parquet_payload", None)
        result.append(clean)
    return result


def _namespace_previews(namespace: dict[str, Any], before_locals: dict[str, int]) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    seen: set[int] = set()
    for name, value in namespace.items():
        if name.startswith("_") or before_locals.get(name) == id(value) or id(value) in seen:
            continue
        seen.add(id(value))
        preview = _preview_value(name, value)
        if preview is not None:
            previews.append(preview)
        if len(previews) >= 8:
            break
    return previews


def _preview_value(name: str, value: Any) -> dict[str, Any] | None:
    if isinstance(value, pd.DataFrame):
        return {
            "kind": "dataframe",
            "name": name,
            "row_count": int(value.shape[0]),
            "column_count": int(value.shape[1]),
            "columns": [str(column) for column in value.columns],
            "rows": value.head(20).to_dict(orient="records"),
            "parquet_payload": value,
        }
    if hasattr(value, "to_plotly_json"):
        from stateframe.artifacts import plotly_figure_payload

        payload = plotly_figure_payload(value, kind="plotly", name=name)
        preview = {
            **payload,
            "kind": "plotly",
            "name": name,
        }
        return preview
    if _is_matplotlib_figure(value):
        from stateframe.artifacts import figure_data_url

        return {
            "kind": "matplotlib",
            "name": name,
            "preview_data_url": figure_data_url(value),
        }
    if _is_small_scalar(value):
        return {
            "kind": "repr",
            "name": name,
            "repr": repr(value),
        }
    return None


def _matplotlib_previews(before_figures: set[int]) -> list[dict[str, Any]]:
    try:
        import matplotlib.pyplot as plt
        from stateframe.artifacts import figure_data_url

        previews = []
        for number in sorted(set(plt.get_fignums()) - before_figures):
            figure = plt.figure(number)
            previews.append({
                "kind": "matplotlib",
                "name": f"figure_{number}",
                "preview_data_url": figure_data_url(figure),
            })
        return previews
    except Exception:
        return []


def _matplotlib_figure_numbers() -> set[int]:
    try:
        import matplotlib.pyplot as plt

        return set(plt.get_fignums())
    except Exception:
        return set()


def _plotly_html(value: Any) -> str:
    from stateframe.artifacts import plotly_html

    return plotly_html(value)


def _plotly_static_image(value: Any) -> str:
    from stateframe.artifacts import plotly_preview_data_url

    return plotly_preview_data_url(value)


def _is_matplotlib_figure(value: Any) -> bool:
    try:
        from matplotlib.figure import Figure

        return isinstance(value, Figure)
    except Exception:
        return False


def _is_small_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _extract_with_block_code(frame: Any, start_lineno: int | None) -> str:
    if frame is None or start_lineno is None:
        return ""
    lines = linecache.getlines(frame.f_code.co_filename)
    if not lines:
        return ""
    start = max(start_lineno - 1, 0)
    if start >= len(lines):
        return ""
    first = lines[start]
    base_indent = len(first) - len(first.lstrip())
    body: list[str] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped and indent <= base_indent:
            break
        body.append(line)
    return textwrap.dedent("".join(body)).strip()


def _auto_name(code: str, previews: list[dict[str, Any]]) -> str:
    text = code.strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")), "")
    plot = next((preview for preview in previews if preview.get("kind") in {"plotly", "matplotlib"}), None)
    if plot is not None:
        column = _first_quoted_arg(first_line, "x") or _first_quoted_arg(first_line, "y")
        if "histogram" in first_line.lower() and column:
            return f"Histogram of {column}"
        if column:
            return f"Plot of {column}"
        return "Plot leaf"
    if any(preview.get("kind") == "dataframe" for preview in previews):
        return "Dataframe leaf"
    if any(preview.get("kind") == "terminal" and preview.get("stdout") for preview in previews):
        return "Printed analysis"
    if first_line:
        return "Code leaf: " + first_line[:48]
    return "Code leaf"


def _first_quoted_arg(line: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*['\"]([^'\"]+)['\"]", line)
    return match.group(1) if match else None


__all__ = [
    "LeafRecorder",
    "is_save_mode",
    "leaf",
    "record_leaf",
    "register_ipython_magics",
    "run_leaf_cell",
    "save_mode",
]
