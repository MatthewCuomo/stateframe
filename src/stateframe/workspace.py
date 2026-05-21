"""Workspace-level persistence for stateframe trees and the project web."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class WorkspaceConfig:
    root: Path | None = None
    name: str | None = None
    metadata_dir: Path | None = None
    tree_dir: Path | None = None
    data_dir: Path | None = None
    artifact_dir: Path | None = None
    autosave_web: bool = True


class WorkspaceDiscoveryError(FileNotFoundError):
    """Raised when no stateframe workspace can be found above a path."""


@dataclass(frozen=True)
class WorkspaceResult:
    path: Path
    kind: str
    metadata: dict[str, Any]

    def __str__(self) -> str:
        return str(self.path)


_CONFIG = WorkspaceConfig()


def configure(
    *,
    root: str | Path | None = None,
    name: str | None = None,
    metadata_dir: str | Path | None = None,
    tree_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    autosave_web: bool | None = None,
) -> "Workspace":
    """Configure the active stateframe workspace.

    The workspace is the durable project-level memory. By default it lives in
    ``.stateframe`` under the current working directory and contains a web index,
    per-dataset tree metadata, and optional materialized data checkpoints.
    """

    if root is not None:
        _CONFIG.root = Path(root)
    if name is not None:
        _CONFIG.name = str(name)
    if metadata_dir is not None:
        _CONFIG.metadata_dir = Path(metadata_dir)
    if tree_dir is not None:
        _CONFIG.tree_dir = Path(tree_dir)
    if data_dir is not None:
        _CONFIG.data_dir = Path(data_dir)
    if artifact_dir is not None:
        _CONFIG.artifact_dir = Path(artifact_dir)
    if autosave_web is not None:
        _CONFIG.autosave_web = bool(autosave_web)
    return current()


def connect(
    start: str | Path | None = None,
    *,
    root: str | Path | None = None,
    name: str | None = None,
    create: bool = False,
) -> "Workspace":
    """Connect to an existing workspace by searching upward like Git.

    Use ``configure(root=...)`` once at the main project folder. Later, from any
    notebook under that folder, call ``connect()`` and stateframe will find the
    nearest ``.stateframe/workspace.json`` above the current directory.
    """

    if root is not None:
        workspace_root = Path(root).expanduser().resolve()
        _connect_to_root(workspace_root, name=name)
        workspace = current()
        if create:
            workspace.init()
        elif not workspace.workspace_path.exists():
            raise WorkspaceDiscoveryError(
                f"No stateframe workspace exists at {workspace.workspace_path}. "
                "Run stateframe.workspace.configure(root=..., name=...) and "
                "stateframe.workspace.init() first, or call connect(create=True)."
            )
        return workspace

    discovered = discover(start)
    _connect_to_root(discovered, name=name)
    return current()


def discover(start: str | Path | None = None) -> Path:
    """Return the nearest parent directory containing ``.stateframe`` metadata."""

    start_path = Path(start).expanduser() if start is not None else Path.cwd()
    current_path = start_path.resolve()
    if current_path.is_file():
        current_path = current_path.parent
    for candidate in [current_path, *current_path.parents]:
        if (candidate / ".stateframe" / "workspace.json").exists():
            return candidate
    raise WorkspaceDiscoveryError(
        f"No stateframe workspace found above {current_path}. "
        "Initialize one at the project root with "
        "stateframe.workspace.configure(root=..., name=...) and "
        "stateframe.workspace.init()."
    )


def connect_web(
    start: str | Path | None = None,
    *,
    height: int = 640,
    title: str | None = None,
):
    """Connect to the nearest workspace and open its web widget."""

    return connect(start=start).web_view(height=height, title=title)


def current() -> "Workspace":
    """Return the active workspace object."""

    return Workspace(_CONFIG)


def init(
    *,
    root: str | Path | None = None,
    name: str | None = None,
) -> WorkspaceResult:
    """Create workspace metadata files and directories if needed."""

    workspace = configure(root=root, name=name) if root is not None or name is not None else current()
    return workspace.init()


def settings() -> dict[str, Any]:
    """Return resolved workspace settings without requiring a write."""

    return current().settings()


def web() -> dict[str, Any]:
    """Return the persistent project web index."""

    return current().web()


def list_trees() -> list[dict[str, Any]]:
    """Return all known trees in the active workspace."""

    return current().list_trees()


def list_files(
    path: str | Path | None = None,
    *,
    include_hidden: bool = False,
    max_entries: int = 500,
    purpose: str = "open",
) -> dict[str, Any]:
    """List one directory under the active workspace root."""

    return current().list_files(
        path,
        include_hidden=include_hidden,
        max_entries=max_entries,
        purpose=purpose,
    )


def file_info(path: str | Path) -> dict[str, Any]:
    """Return metadata for one file or directory under the active workspace."""

    return current().file_info(path)


def validate_save_path(
    path: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate a future save path under the active workspace root."""

    return current().validate_save_path(path, overwrite=overwrite)


def register_profile(profile: Any) -> dict[str, Any]:
    """Register or refresh a profile in the workspace web index."""

    return current().register_profile(profile)


def rename_tree(tree: Any, name: str) -> dict[str, Any]:
    """Rename a workspace tree by profile, tree id, or current tree name."""

    return current().rename_tree(tree, name)


def delete_tree(tree: Any, *, delete_files: bool = False) -> dict[str, Any]:
    """Remove a tree from the workspace web index.

    By default this removes the tree from the web and leaves saved data/artifact
    files on disk. Pass ``delete_files=True`` to also remove stateframe-owned
    tree metadata and data snapshot directories.
    """

    return current().delete_tree(tree, delete_files=delete_files)


def delete_tree_entries(tree: Any, entry_ids: list[str] | tuple[str, ...] | set[str]) -> dict[str, Any]:
    """Delete branch/leaf entries from a saved tree.

    Deleting a branch also deletes its descendants. The root scan entry cannot
    be deleted through this helper; delete the whole tree instead.
    """

    return current().delete_tree_entries(tree, entry_ids)


def update_tree_source_path(
    tree: Any,
    path: str | Path,
    *,
    reader_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a tree's replayable base data path."""

    return current().update_tree_source_path(
        tree,
        path,
        reader_params=reader_params,
    )


def set_tree_source_path(
    tree: Any,
    path: str | Path,
    *,
    reader_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Alias for ``update_tree_source_path``."""

    return update_tree_source_path(tree, path, reader_params=reader_params)


def load_tree(tree: str | None = None) -> dict[str, Any]:
    """Load a saved tree by id/name, or return the web when no tree is given."""

    if tree is None:
        return web()
    return current().load_tree(tree)


class Workspace:
    """Durable project memory for all stateframe dataset trees."""

    def __init__(self, config: WorkspaceConfig) -> None:
        self._config = config

    @property
    def root(self) -> Path:
        configured = self._config.root or os.environ.get("STATEFRAME_WORKSPACE_ROOT")
        return Path(configured).expanduser().resolve() if configured else Path.cwd().resolve()

    @property
    def name(self) -> str:
        configured = self._config.name or os.environ.get("STATEFRAME_WORKSPACE_NAME")
        return str(configured or self.root.name or "stateframe_workspace")

    @property
    def metadata_dir(self) -> Path:
        configured = self._config.metadata_dir or os.environ.get("STATEFRAME_METADATA_DIR")
        base = Path(configured) if configured else Path(".stateframe")
        return _resolve_under_root(self.root, base)

    @property
    def trees_dir(self) -> Path:
        configured = self._config.tree_dir or os.environ.get("STATEFRAME_TREE_DIR")
        return _resolve_under_root(self.root, Path(configured)) if configured else self.metadata_dir / "trees"

    @property
    def data_dir(self) -> Path:
        configured = self._config.data_dir or os.environ.get("STATEFRAME_DATA_DIR")
        return _resolve_under_root(self.root, Path(configured)) if configured else self.metadata_dir / "data"

    @property
    def artifact_dir(self) -> Path:
        configured = self._config.artifact_dir or os.environ.get("STATEFRAME_ARTIFACT_DIR")
        return _resolve_under_root(self.root, Path(configured)) if configured else self.metadata_dir / "artifacts"

    @property
    def workspace_path(self) -> Path:
        return self.metadata_dir / "workspace.json"

    @property
    def web_path(self) -> Path:
        return self.metadata_dir / "web.json"

    @property
    def sources_path(self) -> Path:
        return self.metadata_dir / "sources.json"

    @property
    def autosave_web(self) -> bool:
        return bool(self._config.autosave_web)

    def resolve_path(self, path: str | Path) -> Path:
        """Resolve a workspace-relative or absolute path."""

        return _resolve_under_root(self.root, Path(path))

    def web_view(self, *, height: int = 640, title: str | None = None):
        """Open this workspace's web widget."""

        from stateframe.interactive import web_view

        return web_view(height=height, title=title)

    def open_web(self, *, height: int = 640, title: str | None = None):
        """Alias for ``web_view``."""

        return self.web_view(height=height, title=title)

    def init(self) -> WorkspaceResult:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.trees_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        workspace_payload = self._workspace_payload()
        self.workspace_path.write_text(
            json.dumps(workspace_payload, indent=2, default=_json_default),
            encoding="utf-8",
        )
        if not self.web_path.exists():
            self._write_web(self._empty_web())
        return WorkspaceResult(
            path=self.workspace_path,
            kind="workspace",
            metadata={
                "name": self.name,
                "root": str(self.root),
                "web_path": str(self.web_path),
            },
        )

    def settings(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "root": str(self.root),
            "metadata_dir": str(self.metadata_dir),
            "workspace_path": str(self.workspace_path),
            "web_path": str(self.web_path),
            "sources_path": str(self.sources_path),
            "tree_dir": str(self.trees_dir),
            "data_dir": str(self.data_dir),
            "artifact_dir": str(self.artifact_dir),
            "autosave_web": self.autosave_web,
        }

    def web(self) -> dict[str, Any]:
        if not self.web_path.exists():
            self.init()
        return json.loads(self.web_path.read_text(encoding="utf-8"))

    def list_trees(self) -> list[dict[str, Any]]:
        return list(self.web().get("trees", []))

    def list_files(
        self,
        path: str | Path | None = None,
        *,
        include_hidden: bool = False,
        max_entries: int = 500,
        purpose: str = "open",
    ) -> dict[str, Any]:
        """List one directory under this workspace root for UI file picking."""

        from stateframe.files import list_workspace_files

        return list_workspace_files(
            self,
            path,
            include_hidden=include_hidden,
            max_entries=max_entries,
            purpose=purpose,  # type: ignore[arg-type]
        )

    def file_info(self, path: str | Path) -> dict[str, Any]:
        """Return metadata for one file or directory under this workspace root."""

        from stateframe.files import file_info as workspace_file_info

        return workspace_file_info(self, path).to_dict()

    def validate_save_path(
        self,
        path: str | Path,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Validate a future save path under this workspace root."""

        from stateframe.files import validate_save_path

        return validate_save_path(self, path, overwrite=overwrite)

    def register_profile(
        self,
        profile: Any,
        *,
        tree_path: str | Path | None = None,
        data_path: str | Path | None = None,
    ) -> dict[str, Any]:
        if not self.autosave_web:
            return self._tree_record(profile, tree_path=tree_path, data_path=data_path)
        self.init()
        web_payload = self.web()
        records = list(web_payload.get("trees", []))
        record = self._tree_record(profile, tree_path=tree_path, data_path=data_path)
        existing = next(
            (item for item in records if item.get("tree_id") == record["tree_id"]),
            None,
        )
        if existing is not None:
            record["created_at"] = existing.get("created_at") or record["created_at"]
            record["tree_name"] = existing.get("tree_name") or record["tree_name"]
            record["tree_path"] = record.get("tree_path") or existing.get("tree_path")
            record["data_snapshots"] = _merge_snapshots(
                existing.get("data_snapshots", []),
                record.get("data_snapshots", []),
            )
            records = [
                record if item.get("tree_id") == record["tree_id"] else item
                for item in records
            ]
        else:
            record["tree_name"] = _unique_tree_name(records, record["tree_name"])
            if hasattr(profile, "tree_name"):
                profile.tree_name = record["tree_name"]
            records.append(record)
        if hasattr(profile, "__dict__"):
            profile.tree_id = record["tree_id"]
        web_payload["trees"] = sorted(records, key=lambda item: item.get("tree_name", ""))
        web_payload["updated_at"] = _now()
        web_payload["tree_count"] = len(records)
        self._write_web(web_payload)
        return record

    def rename_tree(self, tree: Any, name: str) -> dict[str, Any]:
        """Rename a tree while preserving its stable tree id and paths."""

        self.init()
        web_payload = self.web()
        records = list(web_payload.get("trees", []))
        tree_id = self.tree_id_for_profile(tree) if hasattr(tree, "profile_id") else str(tree)
        target_index = None
        for index, record in enumerate(records):
            if tree_id in {
                str(record.get("tree_id")),
                str(record.get("tree_name")),
                str(record.get("dataset_name")),
            }:
                target_index = index
                break
        if target_index is None:
            raise KeyError(f"Unknown stateframe tree: {tree_id}")

        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Tree name cannot be empty.")
        for index, record in enumerate(records):
            if index != target_index and record.get("tree_name") == clean_name:
                raise ValueError(f"Tree name already exists: {clean_name}")

        updated = {**records[target_index], "tree_name": clean_name, "updated_at": _now()}
        records[target_index] = updated
        web_payload["trees"] = sorted(records, key=lambda item: item.get("tree_name", ""))
        web_payload["updated_at"] = _now()
        self._write_web(web_payload)

        tree_path = updated.get("tree_path")
        if tree_path:
            path = _resolve_under_root(self.root, Path(tree_path))
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["tree_name"] = clean_name
                payload["updated_at"] = _now()
                path.write_text(
                    json.dumps(payload, indent=2, default=_json_default),
                    encoding="utf-8",
                )
        if hasattr(tree, "tree_name"):
            tree.tree_name = clean_name
        return updated

    def delete_tree(self, tree: Any, *, delete_files: bool = False) -> dict[str, Any]:
        """Remove a tree from the workspace web index."""

        self.init()
        web_payload = self.web()
        records = list(web_payload.get("trees", []))
        tree_id = self.tree_id_for_profile(tree) if hasattr(tree, "profile_id") else str(tree)
        target = None
        remaining = []
        for record in records:
            identifiers = {
                str(record.get("tree_id")),
                str(record.get("tree_name")),
                str(record.get("dataset_name")),
            }
            if tree_id in identifiers:
                target = record
            else:
                remaining.append(record)
        if target is None:
            raise KeyError(f"Unknown stateframe tree: {tree_id}")

        web_payload["trees"] = sorted(remaining, key=lambda item: item.get("tree_name", ""))
        web_payload["updated_at"] = _now()
        web_payload["tree_count"] = len(remaining)
        self._write_web(web_payload)

        removed_paths: list[str] = []
        if delete_files:
            removed_paths = self._delete_tree_owned_files(target)

        return {
            "tree_id": target.get("tree_id"),
            "tree_name": target.get("tree_name"),
            "deleted": True,
            "delete_files": bool(delete_files),
            "removed_paths": removed_paths,
        }

    def delete_tree_entries(
        self,
        tree: Any,
        entry_ids: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, Any]:
        """Delete entries from a saved tree and refresh the web index record."""

        self.init()
        record = self.resolve_tree(
            self.tree_id_for_profile(tree) if hasattr(tree, "profile_id") else str(tree)
        )
        tree_path = record.get("tree_path")
        if not tree_path:
            raise FileNotFoundError(f"No saved tree path is known for {tree!r}.")
        saved_path = _resolve_under_root(self.root, Path(tree_path))
        payload = json.loads(saved_path.read_text(encoding="utf-8"))
        result = _delete_entries_from_tree_payload(payload, [str(entry_id) for entry_id in entry_ids])
        payload["saved_at"] = _now()
        saved_path.write_text(
            json.dumps(payload, indent=2, default=_json_default),
            encoding="utf-8",
        )
        updated_record = self._refresh_record_from_tree_payload(record, payload)
        return {
            **result,
            "tree_id": updated_record.get("tree_id"),
            "tree_name": updated_record.get("tree_name"),
        }

    def update_tree_source_path(
        self,
        tree: Any,
        path: str | Path,
        *,
        reader_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update the editable base data path for a saved tree."""

        from stateframe.io import source_from_path

        self.init()
        web_payload = self.web()
        records = list(web_payload.get("trees", []))
        tree_id = self.tree_id_for_profile(tree) if hasattr(tree, "profile_id") else str(tree)
        target_index = None
        for index, record in enumerate(records):
            if tree_id in {
                str(record.get("tree_id")),
                str(record.get("tree_name")),
                str(record.get("dataset_name")),
            }:
                target_index = index
                break
        if target_index is None:
            raise KeyError(f"Unknown stateframe tree: {tree_id}")

        existing = records[target_index]
        source = source_from_path(
            path,
            reader_params=reader_params,
            previous=existing.get("source") if isinstance(existing.get("source"), dict) else None,
        )
        source["replay_note"] = "Base data path is editable; update it if the source file moves."
        updated = {
            **existing,
            "source": source,
            "updated_at": _now(),
        }
        records[target_index] = updated
        web_payload["trees"] = sorted(records, key=lambda item: item.get("tree_name", ""))
        web_payload["updated_at"] = _now()
        self._write_web(web_payload)

        tree_path = updated.get("tree_path")
        if tree_path:
            saved_path = _resolve_under_root(self.root, Path(tree_path))
            if saved_path.exists():
                payload = json.loads(saved_path.read_text(encoding="utf-8"))
                payload["updated_at"] = _now()
                if isinstance(payload.get("profile"), dict):
                    payload["profile"]["source"] = source
                if isinstance(payload.get("profiles"), list):
                    for profile_payload in payload["profiles"]:
                        if isinstance(profile_payload, dict):
                            profile_payload["source"] = source
                saved_path.write_text(
                    json.dumps(payload, indent=2, default=_json_default),
                    encoding="utf-8",
                )
        if hasattr(tree, "source"):
            tree.source = dict(source)
        return updated

    def tree_id_for_profile(self, profile: Any) -> str:
        explicit = getattr(profile, "tree_id", None) or getattr(profile, "workspace_tree_id", None)
        if explicit:
            return str(explicit)
        name = getattr(profile, "dataset_name", None) or getattr(profile, "profile_id", None) or "dataset"
        return f"{_slug(name)}-{source_fingerprint(profile)[:10]}"

    def tree_path_for_profile(self, profile: Any) -> Path:
        return self.trees_dir / self.tree_id_for_profile(profile) / "tree.json"

    def data_path_for_profile(self, profile: Any | None, label: str) -> Path:
        tree_id = self.tree_id_for_profile(profile) if profile is not None else "ad_hoc"
        return self.data_dir / tree_id / f"{_slug(label)}.parquet"

    def load_tree(self, tree: str) -> dict[str, Any]:
        record = self.resolve_tree(tree)
        path = record.get("tree_path")
        if not path:
            raise FileNotFoundError(f"No saved tree path is known for {tree!r}.")
        tree_path = _resolve_under_root(self.root, Path(path))
        return json.loads(tree_path.read_text(encoding="utf-8"))

    def resolve_tree(self, tree: str) -> dict[str, Any]:
        trees = self.list_trees()
        if not trees:
            raise KeyError(f"No trees are registered in workspace {self.name!r}.")
        candidates = [
            record
            for record in trees
            if tree
            in {
                str(record.get("tree_id")),
                str(record.get("tree_name")),
                str(record.get("dataset_name")),
                _slug(record.get("tree_name")),
                _slug(record.get("dataset_name")),
            }
        ]
        if not candidates:
            raise KeyError(f"Unknown stateframe tree: {tree}")
        if len(candidates) > 1:
            ids = ", ".join(str(record.get("tree_id")) for record in candidates)
            raise ValueError(f"Tree name {tree!r} is ambiguous. Use one of: {ids}")
        return candidates[0]

    def _workspace_payload(self) -> dict[str, Any]:
        existing = {}
        if self.workspace_path.exists():
            try:
                existing = json.loads(self.workspace_path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        return {
            "version": 1,
            "kind": "stateframe_workspace",
            "name": self.name,
            "root": str(self.root),
            "created_at": existing.get("created_at") or _now(),
            "updated_at": _now(),
            "paths": {
                "metadata_dir": _display_path(self.root, self.metadata_dir),
                "web": _display_path(self.root, self.web_path),
                "trees": _display_path(self.root, self.trees_dir),
                "data": _display_path(self.root, self.data_dir),
                "artifacts": _display_path(self.root, self.artifact_dir),
            },
        }

    def _empty_web(self) -> dict[str, Any]:
        return {
            "version": 1,
            "kind": "stateframe_web",
            "workspace": {
                "name": self.name,
                "root": str(self.root),
                "workspace_path": _display_path(self.root, self.workspace_path),
            },
            "created_at": _now(),
            "updated_at": _now(),
            "tree_count": 0,
            "trees": [],
        }

    def _write_web(self, payload: dict[str, Any]) -> None:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.web_path.write_text(
            json.dumps(payload, indent=2, default=_json_default),
            encoding="utf-8",
        )

    def _tree_record(
        self,
        profile: Any,
        *,
        tree_path: str | Path | None,
        data_path: str | Path | None,
    ) -> dict[str, Any]:
        ledger = getattr(profile, "ledger", None)
        tree_id = self.tree_id_for_profile(profile)
        tree_name = getattr(profile, "tree_name", None) or getattr(profile, "dataset_name", None) or tree_id
        source = dict(getattr(profile, "source", {}) or {})
        summary = _summary(profile)
        snapshots = []
        if data_path is not None:
            snapshots.append(
                {
                    "path": _display_path(self.root, Path(data_path)),
                    "saved_at": _now(),
                }
            )
        return {
            "tree_id": tree_id,
            "tree_name": str(tree_name),
            "dataset_name": getattr(profile, "dataset_name", None),
            "profile_id": getattr(profile, "profile_id", None),
            "source_fingerprint": source_fingerprint(profile),
            "source": source,
            "target": getattr(profile, "target", None),
            "time": getattr(profile, "time", None),
            "summary": summary,
            "entry_count": len(getattr(ledger, "entries", []) or []),
            "state_count": len(getattr(ledger, "states", {}) or {}),
            "root_entry_id": getattr(ledger, "root_entry_id", None),
            "active_entry_id": getattr(ledger, "active_entry_id", None),
            "tree_path": _display_path(self.root, Path(tree_path)) if tree_path else None,
            "data_dir": _display_path(self.root, self.data_dir / tree_id),
            "data_snapshots": snapshots,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _refresh_record_from_tree_payload(
        self,
        record: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        web_payload = self.web()
        records = list(web_payload.get("trees", []))
        tree_id = str(record.get("tree_id"))
        ledger = _saved_ledger_payload(payload)
        states = ledger.get("states") if isinstance(ledger.get("states"), dict) else {}
        entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
        updated = {
            **record,
            "tree_name": payload.get("tree_name") or record.get("tree_name"),
            "dataset_name": payload.get("dataset_name") or record.get("dataset_name"),
            "entry_count": len(entries),
            "state_count": len(states),
            "root_entry_id": ledger.get("root_entry_id"),
            "active_entry_id": ledger.get("active_entry_id"),
            "updated_at": _now(),
        }
        replaced = False
        for index, item in enumerate(records):
            if str(item.get("tree_id")) == tree_id:
                records[index] = updated
                replaced = True
                break
        if not replaced:
            records.append(updated)
        web_payload["trees"] = sorted(records, key=lambda item: item.get("tree_name", ""))
        web_payload["updated_at"] = _now()
        web_payload["tree_count"] = len(records)
        self._write_web(web_payload)
        return updated

    def _delete_tree_owned_files(self, record: dict[str, Any]) -> list[str]:
        removed: list[str] = []
        tree_path = record.get("tree_path")
        if tree_path:
            path = _resolve_under_root(self.root, Path(tree_path))
            if _is_relative_to(path, self.trees_dir) and path.exists():
                parent = path.parent
                if path.is_file():
                    path.unlink()
                    removed.append(_display_path(self.root, path))
                if parent.exists() and _is_relative_to(parent, self.trees_dir):
                    shutil.rmtree(parent)
                    removed.append(_display_path(self.root, parent))
        data_dir = record.get("data_dir")
        if data_dir:
            path = _resolve_under_root(self.root, Path(data_dir))
            if _is_relative_to(path, self.data_dir) and path.exists():
                shutil.rmtree(path)
                removed.append(_display_path(self.root, path))
        return removed


def _delete_entries_from_tree_payload(payload: dict[str, Any], entry_ids: list[str]) -> dict[str, Any]:
    targets = {str(entry_id) for entry_id in entry_ids if str(entry_id).strip()}
    if not targets:
        raise ValueError("No tree entries were selected for deletion.")

    ledgers = _ledger_payloads(payload)
    if not ledgers:
        raise ValueError("Saved tree has no ledger entries.")

    deleted: set[str] = set()
    active_entry_id: str | None = None
    for ledger in ledgers:
        result = _delete_entries_from_ledger(ledger, targets)
        deleted.update(result["deleted_entry_ids"])
        active_entry_id = result["active_entry_id"] or active_entry_id

    if not deleted:
        missing = ", ".join(sorted(targets))
        raise KeyError(f"Unknown tree entries: {missing}")

    return {
        "deleted_entry_ids": sorted(deleted),
        "deleted_entry_count": len(deleted),
        "active_entry_id": active_entry_id,
    }


def _delete_entries_from_ledger(ledger: dict[str, Any], targets: set[str]) -> dict[str, Any]:
    entries = [entry for entry in ledger.get("entries", []) or [] if isinstance(entry, dict)]
    by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    matched = targets.intersection(by_id)
    if not matched:
        return {"deleted_entry_ids": set(), "active_entry_id": ledger.get("active_entry_id")}

    root_id = str(ledger.get("root_entry_id") or entries[0].get("id") if entries else "")
    if root_id in matched:
        raise ValueError("The root scan entry cannot be deleted. Delete the whole tree instead.")

    children: dict[str, list[str]] = {}
    for entry in entries:
        parent_id = entry.get("parent_id")
        if parent_id:
            children.setdefault(str(parent_id), []).append(str(entry.get("id")))

    deleted = set(matched)
    stack = list(matched)
    while stack:
        current = stack.pop()
        for child_id in children.get(current, []):
            if child_id not in deleted:
                deleted.add(child_id)
                stack.append(child_id)

    remaining_entries = [entry for entry in entries if str(entry.get("id")) not in deleted]
    remaining_ids = {str(entry.get("id")) for entry in remaining_entries if entry.get("id")}
    states = ledger.get("states") if isinstance(ledger.get("states"), dict) else {}
    remaining_states = {
        state_id: state
        for state_id, state in states.items()
        if not (isinstance(state, dict) and str(state.get("entry_id")) in deleted)
    }

    active = str(ledger.get("active_entry_id") or "") or None
    if active in deleted or active not in remaining_ids:
        active = _nearest_surviving_parent(active, by_id, deleted, remaining_ids) or root_id
    if active not in remaining_ids:
        active = next(iter(remaining_ids), None)

    ledger["entries"] = remaining_entries
    ledger["states"] = remaining_states
    ledger["active_entry_id"] = active
    ledger["root_entry_id"] = root_id if root_id in remaining_ids else active
    ledger["tree"] = _entry_tree(remaining_entries)
    return {"deleted_entry_ids": deleted, "active_entry_id": active}


def _nearest_surviving_parent(
    entry_id: str | None,
    by_id: dict[str, dict[str, Any]],
    deleted: set[str],
    remaining_ids: set[str],
) -> str | None:
    current = str(entry_id or "")
    seen: set[str] = set()
    while current and current in by_id and current not in seen:
        seen.add(current)
        parent_id = by_id[current].get("parent_id")
        if not parent_id:
            return None
        parent = str(parent_id)
        if parent in remaining_ids and parent not in deleted:
            return parent
        current = parent
    return None


def _entry_tree(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    entry_ids = {str(entry.get("id")) for entry in entries if entry.get("id")}
    for entry in entries:
        parent_id = entry.get("parent_id")
        parent = str(parent_id) if parent_id and str(parent_id) in entry_ids else None
        by_parent.setdefault(parent, []).append(entry)

    def build(parent_id: str | None) -> list[dict[str, Any]]:
        nodes = []
        for entry in by_parent.get(parent_id, []):
            nodes.append({**entry, "children": build(str(entry.get("id")))})
        return nodes

    return build(None)


def _ledger_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ledgers: list[dict[str, Any]] = []
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    ledger = profile.get("ledger") if isinstance(profile.get("ledger"), dict) else None
    if ledger is not None:
        ledgers.append(ledger)
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    for profile_payload in profiles:
        if not isinstance(profile_payload, dict):
            continue
        ledger = profile_payload.get("ledger") if isinstance(profile_payload.get("ledger"), dict) else None
        if ledger is not None and all(id(ledger) != id(item) for item in ledgers):
            ledgers.append(ledger)
    return ledgers


def _saved_ledger_payload(payload: dict[str, Any]) -> dict[str, Any]:
    ledgers = _ledger_payloads(payload)
    return ledgers[0] if ledgers else {"entries": [], "states": {}, "root_entry_id": None, "active_entry_id": None}


def source_fingerprint(profile: Any) -> str:
    explicit = getattr(profile, "source_fingerprint", None) or getattr(
        profile,
        "workspace_source_fingerprint",
        None,
    )
    if explicit:
        return str(explicit)
    source = getattr(profile, "source", {}) or {}
    summary = _summary(profile)
    payload = {
        "dataset_name": getattr(profile, "dataset_name", None),
        "source": source,
        "shape": {
            "rows": summary.get("row_count"),
            "columns": summary.get("column_count"),
        },
        "columns": _columns(profile),
    }
    text = json.dumps(payload, sort_keys=True, default=_json_default)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary(profile: Any) -> dict[str, Any]:
    preserved = getattr(profile, "workspace_summary", None) or getattr(profile, "_stateframe_workspace_summary", None)
    if isinstance(preserved, dict):
        return preserved
    try:
        result = profile.summary()
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return {}


def _columns(profile: Any) -> list[str]:
    columns = getattr(profile, "column_profiles", {}) or {}
    return [str(name) for name in columns]


def _merge_snapshots(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for item in [*existing, *incoming]:
        path = str(item.get("path", ""))
        if path:
            by_path[path] = item
    return list(by_path.values())


def _unique_tree_name(records: list[dict[str, Any]], name: str) -> str:
    existing = {str(record.get("tree_name")) for record in records}
    if name not in existing:
        return name
    index = 2
    while f"{name} {index}" in existing:
        index += 1
    return f"{name} {index}"


def _connect_to_root(root: Path, *, name: str | None) -> None:
    _CONFIG.root = root
    _CONFIG.metadata_dir = None
    _CONFIG.tree_dir = None
    _CONFIG.data_dir = None
    _CONFIG.artifact_dir = None
    _CONFIG.name = name or _workspace_name_from_root(root)


def _workspace_name_from_root(root: Path) -> str | None:
    path = root / ".stateframe" / "workspace.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    name = payload.get("name")
    return str(name) if name else None


def _resolve_under_root(root: Path, path: Path) -> Path:
    expanded = path.expanduser()
    return expanded.resolve() if expanded.is_absolute() else (root / expanded).resolve()


def _display_path(root: Path, path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _slug(value: Any) -> str:
    text = str(value or "stateframe").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text or "stateframe"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)
