"""Workspace-scoped filesystem browsing helpers.

The file browser intentionally exposes a project workspace view instead of a
whole-machine file picker. Widget frontends can ask Python to list one folder at
a time, and every requested path is resolved under the configured workspace root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


FilePurpose = Literal["open", "save"]

SUPPORTED_DATA_SUFFIXES = {
    ".csv",
    ".csv.gz",
    ".data",
    ".geojson",
    ".json",
    ".parquet",
    ".tsv",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}


@dataclass(frozen=True)
class WorkspaceFile:
    """A JSON-friendly description of a workspace file or directory."""

    name: str
    path: str
    absolute_path: str
    kind: Literal["directory", "file"]
    suffix: str = ""
    suffixes: tuple[str, ...] = ()
    size_bytes: int | None = None
    modified_time: float | None = None
    hidden: bool = False
    data_kind: str | None = None
    is_supported_data: bool = False
    can_scan: bool = False
    can_save_here: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "absolute_path": self.absolute_path,
            "kind": self.kind,
            "suffix": self.suffix,
            "suffixes": list(self.suffixes),
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time,
            "hidden": self.hidden,
            "data_kind": self.data_kind,
            "is_supported_data": self.is_supported_data,
            "can_scan": self.can_scan,
            "can_save_here": self.can_save_here,
        }


def list_workspace_files(
    workspace: Any,
    path: str | Path | None = None,
    *,
    include_hidden: bool = False,
    max_entries: int = 500,
    purpose: FilePurpose = "open",
) -> dict[str, Any]:
    """List one workspace directory for a notebook/browser file picker."""

    root = workspace.root.resolve()
    current = resolve_workspace_path(workspace, path, must_exist=True)
    if current.is_file():
        current = current.parent
    if not current.is_dir():
        raise NotADirectoryError(current)

    entries: list[WorkspaceFile] = []
    child_count = 0
    for child in current.iterdir():
        child_count += 1
        if not include_hidden and _is_hidden(child):
            continue
        try:
            entry = file_info(workspace, child)
        except ValueError:
            continue
        entries.append(entry)

    entries = sorted(
        entries,
        key=lambda item: (item.kind != "directory", item.name.lower()),
    )
    truncated = len(entries) > max_entries
    if truncated:
        entries = entries[:max_entries]

    parent_path = None
    if current != root:
        parent_path = _display_path(root, current.parent)

    return {
        "version": 1,
        "kind": "workspace_files",
        "purpose": purpose,
        "workspace": {
            "name": workspace.name,
            "root": str(root),
        },
        "current_path": _display_path(root, current),
        "current_absolute_path": str(current),
        "parent_path": parent_path,
        "entries": [entry.to_dict() for entry in entries],
        "entry_count": len(entries),
        "total_child_count": child_count,
        "truncated": truncated,
        "include_hidden": bool(include_hidden),
        "max_entries": int(max_entries),
        "supported_data_suffixes": sorted(SUPPORTED_DATA_SUFFIXES),
    }


def file_info(workspace: Any, path: str | Path) -> WorkspaceFile:
    """Return metadata for a single workspace path."""

    root = workspace.root.resolve()
    resolved = resolve_workspace_path(workspace, path, must_exist=True)
    stat = resolved.stat()
    is_dir = resolved.is_dir()
    suffixes = tuple(suffix.lower() for suffix in resolved.suffixes)
    compound_suffix = "".join(suffixes[-2:]) if len(suffixes) >= 2 else ""
    suffix = compound_suffix if compound_suffix in SUPPORTED_DATA_SUFFIXES else (
        suffixes[-1] if suffixes else ""
    )
    data_kind = _data_kind(suffix)
    return WorkspaceFile(
        name=resolved.name or root.name,
        path=_display_path(root, resolved),
        absolute_path=str(resolved),
        kind="directory" if is_dir else "file",
        suffix=suffix,
        suffixes=suffixes,
        size_bytes=None if is_dir else int(stat.st_size),
        modified_time=stat.st_mtime,
        hidden=_is_hidden(resolved),
        data_kind=data_kind,
        is_supported_data=bool(data_kind),
        can_scan=bool(data_kind) and resolved.is_file(),
        can_save_here=is_dir,
    )


def validate_save_path(
    workspace: Any,
    path: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Resolve and validate a future artifact/data save location."""

    resolved = resolve_workspace_path(workspace, path, must_exist=False)
    exists = resolved.exists()
    if exists and resolved.is_dir():
        raise IsADirectoryError(resolved)
    if exists and not overwrite:
        raise FileExistsError(resolved)
    parent = resolved.parent
    if not parent.exists():
        raise FileNotFoundError(parent)
    if not parent.is_dir():
        raise NotADirectoryError(parent)
    root = workspace.root.resolve()
    return {
        "path": _display_path(root, resolved),
        "absolute_path": str(resolved),
        "parent_path": _display_path(root, parent),
        "exists": exists,
        "overwrite": bool(overwrite),
        "suffix": resolved.suffix.lower(),
        "can_save": True,
    }


def resolve_workspace_path(
    workspace: Any,
    path: str | Path | None = None,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve a path and ensure it remains inside ``workspace.root``."""

    root = workspace.root.resolve()
    if path is None or str(path).strip() in {"", ".", "/"}:
        resolved = root
    else:
        candidate = Path(path).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not _is_relative_to(resolved, root):
        raise ValueError(f"Path is outside the stateframe workspace root: {path}")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def _data_kind(suffix: str) -> str | None:
    if suffix not in SUPPORTED_DATA_SUFFIXES:
        return None
    if suffix in {".csv", ".csv.gz"}:
        return "csv"
    if suffix in {".tsv", ".data", ".txt"}:
        return "delimited"
    if suffix == ".parquet":
        return "parquet"
    if suffix in {".xlsx", ".xls"}:
        return "excel"
    if suffix in {".json", ".geojson"}:
        return "json"
    if suffix == ".zip":
        return "zip"
    return suffix.lstrip(".")


def _display_path(root: Path, path: Path) -> str:
    if path == root:
        return "."
    return path.relative_to(root).as_posix()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts if part not in {path.anchor, ""})

