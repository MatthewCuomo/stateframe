"""Durable save helpers for stateframe workspace trees."""

from __future__ import annotations

import json
import os
import re
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api import types as pdt

from stateframe.models import Profile


_PROFILE_REFS: list[weakref.ReferenceType[Profile]] = []


@dataclass
class SaveConfig:
    root: Path | None = None
    tree_dir: Path | None = None
    data_dir: Path | None = None
    session_name: str | None = None


@dataclass(frozen=True)
class SaveResult:
    path: Path
    kind: str
    session_name: str
    metadata: dict[str, Any]

    def __str__(self) -> str:
        return str(self.path)


_CONFIG = SaveConfig()


def configure(
    *,
    root: str | Path | None = None,
    tree_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    session_name: str | None = None,
) -> SaveConfig:
    """Configure default save locations for the current workspace."""

    if root is not None:
        _CONFIG.root = Path(root)
    if tree_dir is not None:
        _CONFIG.tree_dir = Path(tree_dir)
    if data_dir is not None:
        _CONFIG.data_dir = Path(data_dir)
    if session_name is not None:
        _CONFIG.session_name = _slug(session_name)
    try:
        from stateframe import workspace

        workspace.configure(
            root=root,
            name=session_name,
            tree_dir=tree_dir,
            data_dir=data_dir,
        )
    except Exception:
        pass
    return _CONFIG


def settings() -> dict[str, Any]:
    """Return the resolved save settings without writing files."""

    from stateframe import workspace

    workspace_settings = workspace.settings()
    session_name = _session_name()
    return {
        "session_name": session_name,
        "root": workspace_settings["root"],
        "tree_dir": workspace_settings["tree_dir"],
        "data_dir": workspace_settings["data_dir"],
        "workspace": workspace_settings,
    }


def register_profile(profile: Profile) -> Profile:
    """Register a profile as part of the current workspace web."""

    _prune_registry()
    for ref in _PROFILE_REFS:
        if ref() is profile:
            _register_workspace_profile(profile)
            return profile
    _PROFILE_REFS.append(weakref.ref(profile))
    _register_workspace_profile(profile)
    return profile


def registered_profiles() -> list[Profile]:
    """Return live profiles registered in this Python process."""

    _prune_registry()
    return [profile for ref in _PROFILE_REFS if (profile := ref()) is not None]


def tree(
    *items: Any,
    path: str | Path | None = None,
    session_name: str | None = None,
    include_data: bool = False,
) -> SaveResult:
    """Save ledger/tree metadata for one or more profiles.

    When no items are provided, all live profiles created by ``sf.scan`` or
    ``sf.profile`` in this Python process are saved into the current workspace.
    Dataframe values are not embedded unless ``include_data=True``; use
    ``save.data(...)`` for Parquet checkpoints.
    """

    from stateframe import workspace

    if session_name:
        workspace.configure(name=session_name)
    current_workspace = workspace.current()
    session = current_workspace.name
    profiles = _profiles_from_items(items) if items else registered_profiles()
    if not profiles:
        raise ValueError("No stateframe profiles are available to save.")

    if path is not None and len(profiles) != 1:
        raise ValueError("A custom tree path can only be used when saving one profile.")

    results = [
        _save_one_tree(
            profile,
            workspace=current_workspace,
            path=path,
            include_data=include_data,
        )
        for profile in profiles
    ]
    if len(results) == 1:
        return results[0]

    return SaveResult(
        path=current_workspace.web_path,
        kind="web",
        session_name=session,
        metadata={
            "profile_count": len(profiles),
            "tree_paths": [str(result.path) for result in results],
            "entry_count": sum(int(result.metadata.get("entry_count", 0)) for result in results),
        },
    )


def data(
    item: Any,
    *,
    entry_id: str | None = None,
    state_id: str | None = None,
    name: str | None = None,
    path: str | Path | None = None,
    session_name: str | None = None,
    also_save_tree: bool = True,
    compression: str = "snappy",
) -> SaveResult:
    """Save a dataframe state as Parquet and attach it to the ledger."""

    from stateframe import workspace

    if session_name:
        workspace.configure(name=session_name)
    current_workspace = workspace.current()
    session = current_workspace.name
    frame, profile, resolved_entry_id, resolved_state_id = _frame_from_item(
        item,
        entry_id=entry_id,
        state_id=state_id,
    )
    label = name or resolved_state_id or resolved_entry_id or "data"
    output_path = Path(path) if path is not None else _data_path(
        profile=profile,
        label=label,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_metadata = _write_frame_parquet(
        frame,
        output_path,
        index=True,
        compression=compression,
    )

    sidecar = output_path.with_suffix(output_path.suffix + ".json")
    metadata = {
        "kind": "data",
        "format": "parquet",
        "path": str(output_path),
        "session_name": session,
        "saved_at": _now(),
        "profile_id": profile.profile_id if profile is not None else None,
        "dataset_name": profile.dataset_name if profile is not None else None,
        "entry_id": resolved_entry_id,
        "state_id": resolved_state_id,
        "row_count": int(frame.shape[0]),
        "column_count": int(frame.shape[1]),
        "columns": [str(column) for column in frame.columns],
        "compression": compression,
        **parquet_metadata,
    }
    sidecar.write_text(
        json.dumps(metadata, indent=2, default=_json_default),
        encoding="utf-8",
    )

    if profile is not None and profile.ledger is not None and (resolved_entry_id or resolved_state_id):
        profile.ledger.attach_state_artifact(
            resolved_state_id or resolved_entry_id or "",
            {
                "kind": "data_snapshot",
                "format": "parquet",
                "path": str(output_path),
                "metadata_path": str(sidecar),
                "saved_at": metadata["saved_at"],
                "row_count": metadata["row_count"],
                "column_count": metadata["column_count"],
            },
        )
        if also_save_tree:
            tree(profile, session_name=session)

    if profile is not None:
        current_workspace.register_profile(profile, data_path=output_path)

    return SaveResult(
        path=output_path,
        kind="data",
        session_name=session,
        metadata=metadata,
    )


def load_tree(
    path: str | Path | None = None,
    *,
    tree: str | None = None,
    session_name: str | None = None,
) -> dict[str, Any]:
    """Load saved tree metadata."""

    if path is None:
        from stateframe import workspace

        return workspace.load_tree(tree or session_name)
    input_path = Path(path)
    return json.loads(input_path.read_text(encoding="utf-8"))


def load_data(path: str | Path) -> pd.DataFrame:
    """Load a saved Parquet data checkpoint."""

    return pd.read_parquet(path)


def _write_frame_parquet(
    frame: pd.DataFrame,
    path: Path,
    *,
    index: bool,
    compression: str | None = "snappy",
) -> dict[str, Any]:
    """Write a dataframe snapshot, retrying mixed object columns as strings.

    Raw CSVs often contain mostly-text columns where a few values were inferred
    as numbers. PyArrow rejects those mixed Python object columns. The original
    in-memory frame is left untouched; only the persisted snapshot is normalized.
    """

    try:
        frame.to_parquet(path, index=index, compression=compression)
        return {}
    except (TypeError, ValueError, OverflowError) as exc:
        safe_frame, coercions = _stringify_object_columns_for_parquet(frame)
        if not coercions:
            raise
        try:
            safe_frame.to_parquet(path, index=index, compression=compression)
        except Exception:
            raise exc
        return {
            "parquet_coercions": coercions,
            "parquet_coercion_reason": "Mixed object columns were normalized to nullable strings for Parquet compatibility.",
        }


def _stringify_object_columns_for_parquet(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    safe_frame = frame.copy(deep=False)
    coercions: list[dict[str, Any]] = []
    for column in safe_frame.columns:
        series = safe_frame[column]
        if not pdt.is_object_dtype(series.dtype):
            continue
        safe_frame[column] = series.map(_parquet_string_value).astype("string")
        coercions.append(
            {
                "column": str(column),
                "from_dtype": str(series.dtype),
                "to_dtype": "string",
            }
        )
    return safe_frame, coercions


def _parquet_string_value(value: Any) -> str | None:
    if _is_missing_scalar(value):
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _is_missing_scalar(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if missing is pd.NA:
        return True
    if isinstance(missing, bool):
        return bool(missing)
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _profiles_from_items(items: tuple[Any, ...]) -> list[Profile]:
    profiles: list[Profile] = []
    seen: set[int] = set()
    for item in items:
        profile = _profile_from_item(item)
        if profile is not None and id(profile) not in seen:
            seen.add(id(profile))
            profiles.append(profile)
    return profiles


def _profile_from_item(item: Any) -> Profile | None:
    if isinstance(item, Profile):
        return item
    if hasattr(item, "record_profile") and isinstance(item.record_profile, Profile):
        return item.record_profile
    if hasattr(item, "profile") and isinstance(item.profile, Profile):
        return item.profile
    return None


def _frame_from_item(
    item: Any,
    *,
    entry_id: str | None,
    state_id: str | None,
) -> tuple[pd.DataFrame, Profile | None, str | None, str | None]:
    if isinstance(item, pd.DataFrame):
        return item, None, None, None

    profile = _profile_from_item(item)
    if profile is None:
        raise TypeError("save.data expects a Profile, tree/viewer object, or pandas DataFrame.")

    selected_entry_id = None
    if entry_id is None and state_id is None and hasattr(item, "selected_entry_id"):
        selected_entry_id = item.selected_entry_id()
    resolved = state_id or entry_id or selected_entry_id
    if resolved is None and profile.ledger is not None:
        resolved = profile.ledger.active_entry_id
    if resolved is None:
        raise ValueError("No ledger state is available to save.")

    frame = profile.checkout(resolved)
    resolved_entry_id = resolved
    resolved_state_id = None
    if profile.ledger is not None:
        if resolved in profile.ledger.states:
            resolved_state_id = resolved
            resolved_entry_id = profile.ledger.states[resolved].entry_id
        else:
            entry = profile.ledger.get(resolved)
            resolved_entry_id = entry.id
            resolved_state_id = entry.state_id
    return frame, profile, resolved_entry_id, resolved_state_id


def _save_one_tree(
    profile: Profile,
    *,
    workspace: Any,
    path: str | Path | None,
    include_data: bool,
) -> SaveResult:
    output_path = Path(path) if path is not None else workspace.tree_path_for_profile(profile)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _tree_payload(profile, workspace=workspace, include_data=include_data)
    output_path.write_text(
        json.dumps(payload, indent=2, default=_json_default),
        encoding="utf-8",
    )
    workspace.register_profile(profile, tree_path=output_path)
    return SaveResult(
        path=output_path,
        kind="tree",
        session_name=workspace.name,
        metadata={
            "tree_id": payload["tree_id"],
            "tree_name": payload["tree_name"],
            "profile_count": 1,
            "entry_count": len(profile.ledger.entries) if profile.ledger else 0,
        },
    )


def _tree_payload(
    profile: Profile,
    *,
    workspace: Any,
    include_data: bool,
) -> dict[str, Any]:
    profile_payload = {
        "profile_id": profile.profile_id,
        "dataset_name": profile.dataset_name,
        "tree_name": profile.tree_name,
        "source": dict(profile.source),
        "profile": profile.to_dict(),
        "ledger": (
            profile.ledger.to_dict(include_states=True, include_data=include_data)
            if profile.ledger is not None
            else None
        ),
    }
    return {
        "version": 2,
        "kind": "stateframe_tree",
        "saved_at": _now(),
        "workspace": workspace.settings(),
        "tree_id": workspace.tree_id_for_profile(profile),
        "tree_name": profile.tree_name or profile.dataset_name or profile.profile_id,
        "dataset_name": profile.dataset_name,
        "profile_id": profile.profile_id,
        "cwd": str(Path.cwd()),
        "settings": settings(),
        "profile": profile_payload,
        "profiles": [profile_payload],
    }


def _data_path(
    *,
    profile: Profile | None,
    label: str,
) -> Path:
    from stateframe import workspace

    return workspace.current().data_path_for_profile(profile, label)


def _register_workspace_profile(profile: Profile) -> None:
    try:
        from stateframe import workspace

        workspace.register_profile(profile)
    except Exception:
        pass


def _root() -> Path:
    return _CONFIG.root or Path.cwd()


def _tree_dir(session_name: str) -> Path:
    base = _CONFIG.tree_dir or (_root() / ".stateframe")
    return Path(base) / session_name


def _data_dir(session_name: str) -> Path:
    base = _CONFIG.data_dir or (_root() / ".stateframe")
    return Path(base) / session_name / "data"


def _session_name() -> str:
    configured = _CONFIG.session_name or os.environ.get("STATEFRAME_SESSION_NAME")
    if configured:
        return _slug(configured)
    return _slug(_notebook_name() or Path.cwd().name or "stateframe_session")


def _notebook_name() -> str | None:
    env_name = os.environ.get("STATEFRAME_NOTEBOOK_NAME")
    if env_name:
        return Path(env_name).stem
    try:
        from IPython import get_ipython

        shell = get_ipython()
        if shell is not None:
            for key in ["__vsc_ipynb_file__", "__session__", "__notebook_path__"]:
                value = shell.user_ns.get(key)
                if value:
                    return Path(str(value)).stem
    except Exception:
        return None
    return None


def _slug(value: Any) -> str:
    text = str(value or "stateframe_session").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text or "stateframe_session"


def _prune_registry() -> None:
    _PROFILE_REFS[:] = [ref for ref in _PROFILE_REFS if ref() is not None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)
