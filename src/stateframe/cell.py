"""Cell capture and push helpers for notebook-native stateframe work."""

from __future__ import annotations

import ast
import contextlib
import io
import traceback
from pathlib import Path
from typing import Any

import pandas as pd


def cell(
    code: str,
    *,
    source: Any | None = None,
    parent: str | None = None,
    name: str | None = None,
    message: str | None = None,
    note: str | None = None,
    save: bool | None = None,
    save_path: str | Path | None = None,
    namespace: dict[str, Any] | None = None,
    output: str = "output",
    autosave_tree: bool = True,
):
    """Execute code and record its output under inferred ``sf.pull`` parents.

    This is the plain-Python equivalent of ``%%sf_cell``. If the code assigns
    one or more variables from ``sf.pull(...)``, stateframe uses those pulled
    dataframe contexts as dependency edges. A dataframe named by ``output`` is
    saved as a branch; other visible outputs are captured as a code leaf.
    """

    return run_cell(
        code,
        source=source,
        parent=parent,
        name=name,
        message=message,
        note=note,
        save=save,
        save_path=save_path,
        namespace=namespace,
        output=output,
        autosave_tree=autosave_tree,
    )


def run_cell(
    code: str,
    *,
    source: Any | None = None,
    parent: str | None = None,
    name: str | None = None,
    message: str | None = None,
    note: str | None = None,
    save: bool | None = None,
    save_path: str | Path | None = None,
    namespace: dict[str, Any] | None = None,
    output: str = "output",
    autosave_tree: bool = True,
):
    """Execute and record a stateframe-aware code cell."""

    from stateframe.leaf import (
        _collect_previews,
        _matplotlib_figure_numbers,
        record_leaf,
    )

    ns = namespace if namespace is not None else {}
    _ensure_default_namespace(ns)
    try:
        from stateframe.pull import clear_pull_contexts

        clear_pull_contexts()
    except Exception:
        pass
    before_locals = {key: id(value) for key, value in ns.items()}
    before_figures = _matplotlib_figure_numbers()
    stdout = io.StringIO()
    stderr = io.StringIO()
    exc_info: tuple[Any, BaseException, Any] | None = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(code, ns, ns)
        except BaseException as exc:  # pragma: no cover - re-raised below
            exc_info = (type(exc), exc, exc.__traceback__)
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    previews = _collect_previews(
        ns,
        before_locals=before_locals,
        before_figures=before_figures,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )
    if exc_info is not None:
        _record_failed_cell(
            code,
            previews=previews,
            source=source,
            parent=parent,
            name=name,
            message=message,
            note=note,
            save=save,
            save_path=save_path,
            autosave_tree=autosave_tree,
        )
        raise exc_info[1]

    dependencies = _cell_dependencies(code, ns)
    try:
        from stateframe.pull import clear_pull_contexts

        clear_pull_contexts()
    except Exception:
        pass
    profile, parent_id = _resolve_target(source, parent, dependencies)
    metadata_dependencies = _clean_dependencies(dependencies)
    output_value = ns.get(output)
    replay_code = _strip_pull_assignments(code)
    title = name or _auto_cell_name(output_value, metadata_dependencies)

    if isinstance(output_value, pd.DataFrame) or hasattr(output_value, "to_pandas"):
        from stateframe.branch import BranchRecorder

        recorder = BranchRecorder(
            profile=profile,
            parent_id=parent_id,
            source=source,
            autosave_tree=autosave_tree,
            default_code=replay_code,
            default_message=message,
            default_note=note,
        )
        entry = recorder.save_data(
            output_value,
            name=title,
            message=message,
            note=note,
            code=replay_code,
            operation="cell.transform",
            dependencies=metadata_dependencies,
            cell={
                "kind": "stateframe_cell",
                "captured_code": str(code).strip(),
                "replay_code": replay_code,
                "output_variable": output,
                "dependency_count": len(metadata_dependencies),
            },
        )
        if save:
            _save_entry_data(profile, entry, title)
        if previews:
            record_leaf(
                profile,
                parent_id=entry.id,
                code=str(code),
                previews=previews,
                name=f"{title} cell output",
                message=message,
                note=note,
                save=save,
                save_path=save_path,
                autosave_tree=autosave_tree,
                dependencies=metadata_dependencies,
                parent_label=title,
            )
        return entry

    return record_leaf(
        profile,
        parent_id=parent_id,
        code=str(code),
        previews=previews,
        name=title,
        message=message,
        note=note,
        save=save,
        save_path=save_path,
        autosave_tree=autosave_tree,
        dependencies=metadata_dependencies,
        parent_label=parent,
    )


def push(
    output: Any,
    *,
    name: str | None = None,
    message: str | None = None,
    note: str | None = None,
    parents: Any | list[Any] | tuple[Any, ...] | None = None,
    source: Any | None = None,
    code: str | bool | None = None,
    save: bool = False,
    autosave_tree: bool = True,
    **params: Any,
):
    """Record an object under the most recent pulled stateframe input.

    DataFrames become state branches. Other objects become artifact leaves.
    When ``parents`` is omitted, stateframe uses recent ``sf.pull(...)`` calls
    as dependency edges and clears that small in-process pull stack after save.
    """

    from stateframe.branch import BranchRecorder, _capture_current_cell
    from stateframe.pull import clear_pull_contexts, recent_pull_contexts

    recent_contexts = [
        _dependency_from_pull_context(item)
        for item in recent_pull_contexts()
        if isinstance(item, dict)
    ]
    dependencies = _dependencies_from_parents(parents)
    if not dependencies and isinstance(output, pd.DataFrame):
        context = output.attrs.get("_stateframe")
        if isinstance(context, dict):
            dependencies = _matching_recent_dependencies(context, recent_contexts) or [
                {
                    **dict(context),
                    "source": "output.attrs",
                    "_frame": output,
                }
            ]
    if not dependencies:
        dependencies = recent_contexts
    dependencies = [item for item in dependencies if item]
    profile, parent_id = _resolve_target(source, None, dependencies)
    metadata_dependencies = _clean_dependencies(dependencies)
    code_text = _capture_current_cell() if code is True else (str(code).strip() if code else "")
    recorder = BranchRecorder(
        profile=profile,
        parent_id=parent_id,
        source=source,
        autosave_tree=autosave_tree,
        default_code=code_text,
        default_message=message,
        default_note=note,
    )
    entry = recorder.save(
        output,
        name=name,
        message=message,
        note=note,
        code=code_text,
        dependencies=metadata_dependencies,
        **params,
    )
    if save and getattr(entry, "state_id", None):
        _save_entry_data(profile, entry, name or getattr(entry, "title", "pushed_state"))
    clear_pull_contexts()
    return entry


def _record_failed_cell(
    code: str,
    *,
    previews: list[dict[str, Any]],
    source: Any | None,
    parent: str | None,
    name: str | None,
    message: str | None,
    note: str | None,
    save: bool | None,
    save_path: str | Path | None,
    autosave_tree: bool,
) -> None:
    try:
        from stateframe.leaf import record_leaf

        profile, parent_id = _resolve_target(source, parent, [])
        record_leaf(
            profile,
            parent_id=parent_id,
            code=code,
            previews=previews,
            name=name or "Failed stateframe cell",
            message=message,
            note=note,
            save=save,
            save_path=save_path,
            autosave_tree=autosave_tree,
        )
    except Exception:
        pass


def _ensure_default_namespace(namespace: dict[str, Any]) -> None:
    try:
        import stateframe as sf

        namespace.setdefault("sf", sf)
    except Exception:
        pass
    namespace.setdefault("pd", pd)
    try:
        import numpy as np

        namespace.setdefault("np", np)
    except Exception:
        pass


def _resolve_target(
    source: Any | None,
    parent: str | None,
    dependencies: list[dict[str, Any]],
):
    if source is not None or parent is not None:
        from stateframe.leaf import _resolve_profile_and_parent

        return _resolve_profile_and_parent(source, parent)

    first = dependencies[0] if dependencies else {}
    frame = first.get("_frame")
    if isinstance(frame, pd.DataFrame):
        from stateframe.branch import _resolve_profile_and_parent

        profile, resolved_parent, _factory = _resolve_profile_and_parent(
            frame,
            first.get("entry_id") or first.get("reference"),
        )
        return profile, resolved_parent

    from stateframe.leaf import _default_profile

    profile = _default_profile()
    parent_id = profile.ledger.active_entry_id if getattr(profile, "ledger", None) is not None else None
    return profile, parent_id


def _cell_dependencies(code: str, namespace: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for assignment in _pull_assignments(code):
        for variable in assignment["variables"]:
            value = namespace.get(variable)
            if not isinstance(value, pd.DataFrame):
                continue
            context = value.attrs.get("_stateframe")
            if not isinstance(context, dict):
                continue
            dependency = {
                **dict(context),
                "variable": variable,
                "reference": assignment.get("reference"),
                "source": "sf.pull",
                "_frame": value,
            }
            key = (str(dependency.get("tree_id") or ""), str(dependency.get("entry_id") or ""))
            if key not in seen:
                seen.add(key)
                dependencies.append(dependency)
    return dependencies


def _dependencies_from_parents(parents: Any | list[Any] | tuple[Any, ...] | None) -> list[dict[str, Any]]:
    if parents is None:
        return []
    values = list(parents) if isinstance(parents, (list, tuple, set)) else [parents]
    dependencies: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, pd.DataFrame):
            context = value.attrs.get("_stateframe")
            if isinstance(context, dict):
                dependencies.append(
                    {
                        **dict(context),
                        "source": "parent",
                        "_frame": value,
                    }
                )
        elif isinstance(value, dict):
            dependencies.append(dict(value))
    return dependencies


def _dependency_from_pull_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(context),
        "source": "sf.pull",
    }


def _matching_recent_dependencies(
    context: dict[str, Any],
    recent_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tree_id = str(context.get("tree_id") or "")
    entry_id = str(context.get("entry_id") or "")
    return [
        item
        for item in recent_contexts
        if str(item.get("tree_id") or "") == tree_id
        and str(item.get("entry_id") or "") == entry_id
    ]


def _clean_dependencies(dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in dependencies:
        clean = {
            key: value
            for key, value in item.items()
            if not key.startswith("_") and value is not None and value != ""
        }
        key = (
            str(clean.get("tree_id") or ""),
            str(clean.get("entry_id") or ""),
            str(clean.get("variable") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _pull_assignments(code: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    assignments: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        value = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if value is None or not _is_pull_call(value):
            continue
        assignments.append(
            {
                "lineno": getattr(node, "lineno", None),
                "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", None)),
                "variables": _target_names(targets),
                "reference": _pull_reference(value),
            }
        )
    return assignments


def _strip_pull_assignments(code: str) -> str:
    assignments = _pull_assignments(code)
    if not assignments:
        return str(code).strip()
    remove_lines: set[int] = set()
    for assignment in assignments:
        start = assignment.get("lineno")
        end = assignment.get("end_lineno") or start
        if isinstance(start, int) and isinstance(end, int):
            remove_lines.update(range(start, end + 1))
    lines = str(code).splitlines()
    kept = [
        line
        for index, line in enumerate(lines, start=1)
        if index not in remove_lines
    ]
    return "\n".join(kept).strip()


def _is_pull_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "pull"
    if isinstance(func, ast.Attribute) and func.attr == "pull":
        value = func.value
        return isinstance(value, ast.Name) and value.id in {"sf", "stateframe"}
    return False


def _pull_reference(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _target_names(targets: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.extend(_target_names(list(target.elts)))
    return names


def _save_entry_data(profile: Any, entry: Any, name: str | None) -> None:
    try:
        from stateframe import save as save_api

        save_api.data(
            profile,
            entry_id=entry.id,
            name=name or entry.title,
            also_save_tree=False,
        )
        profile.save_tree()
    except Exception:
        if hasattr(profile, "save_tree"):
            profile.save_tree()


def _auto_cell_name(output_value: Any, dependencies: list[dict[str, Any]]) -> str:
    if isinstance(output_value, pd.DataFrame) or hasattr(output_value, "to_pandas"):
        return "Cell dataframe output"
    if dependencies:
        return "Stateframe code cell"
    return "Code cell"


__all__ = [
    "cell",
    "push",
    "run_cell",
]
