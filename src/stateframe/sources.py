"""Pluggable data sources for stateframe "Get Data" workflows.

Stateframe owns a small provider contract; users own the connection details for
their company systems. A provider executes a query and returns a DataFrame-like
object plus lineage metadata that can become the root source for a scan tree.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol


QueryParams = Mapping[str, Any] | None
QueryHandler = Callable[..., Any]


class DataSourceError(RuntimeError):
    """Raised when a registered data source cannot satisfy a request."""


@dataclass(frozen=True)
class DataObject:
    """A browseable table, schema, folder, or queryable object."""

    name: str
    path: str
    kind: str = "table"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "description": self.description,
            "metadata": _json_safe(self.metadata),
        }


@dataclass
class QueryResult:
    """Result returned by a data source query."""

    data: Any
    source: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    name: str | None = None


class DataSource:
    """Base class for query-capable data sources.

    Subclasses only need to implement ``execute``. They may also implement
    ``preview`` and ``list_objects`` for richer UI experiences.
    """

    id: str = ""
    display_name: str = ""
    description: str = ""

    def __init__(
        self,
        source_id: str | None = None,
        *,
        display_name: str | None = None,
        description: str | None = None,
    ) -> None:
        if source_id is not None:
            self.id = source_id
        if display_name is not None:
            self.display_name = display_name
        if description is not None:
            self.description = description

    def capabilities(self) -> dict[str, Any]:
        return {
            "query": True,
            "preview": type(self).preview is not DataSource.preview,
            "list_objects": type(self).list_objects is not DataSource.list_objects,
            "params": True,
            "replay": True,
        }

    def list_objects(self, path: str | None = None) -> list[DataObject]:
        raise DataSourceError(f"{self.id} does not support object browsing.")

    def preview(
        self,
        query: str,
        params: QueryParams = None,
        *,
        limit: int = 100,
        **kwargs: Any,
    ) -> QueryResult:
        raise DataSourceError(f"{self.id} does not support query preview.")

    def execute(
        self,
        query: str,
        params: QueryParams = None,
        **kwargs: Any,
    ) -> QueryResult:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name or self.id,
            "description": self.description,
            "capabilities": _json_safe(self.capabilities()),
            "class": type(self).__name__,
            "module": type(self).__module__,
        }


class FunctionDataSource(DataSource):
    """Small adapter for registering a plain Python query function."""

    def __init__(
        self,
        source_id: str,
        handler: QueryHandler,
        *,
        display_name: str | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__(
            source_id,
            display_name=display_name or source_id,
            description=description,
        )
        self.handler = handler

    def execute(
        self,
        query: str,
        params: QueryParams = None,
        **kwargs: Any,
    ) -> QueryResult:
        result = self.handler(query, params=params, **kwargs)
        return _coerce_query_result(result)


class SourceLike(Protocol):
    id: str

    def execute(
        self,
        query: str,
        params: QueryParams = None,
        **kwargs: Any,
    ) -> QueryResult: ...


_REGISTRY: dict[str, DataSource] = {}
_IMPORT_STATUS: dict[str, dict[str, Any]] = {}
_AUTO_REGISTERING = False


def register(
    source: DataSource | str,
    provider: DataSource | QueryHandler | None = None,
    *,
    display_name: str | None = None,
    description: str | None = None,
    replace: bool = True,
) -> DataSource:
    """Register a source provider.

    Examples
    --------
    ``sf.sources.register(MyWarehouseSource())``

    ``sf.sources.register("warehouse", run_query_function)``
    """

    if isinstance(source, str):
        if provider is None:
            raise TypeError("register(source_id, provider) requires a provider.")
        if isinstance(provider, DataSource):
            provider.id = provider.id or source
            if provider.id != source:
                raise ValueError(
                    f"Provider id {provider.id!r} does not match registration id {source!r}."
                )
            instance = provider
        elif callable(provider):
            instance = FunctionDataSource(
                source,
                provider,
                display_name=display_name,
                description=description,
            )
        else:
            raise TypeError("provider must be a DataSource or callable.")
    elif isinstance(source, DataSource):
        if provider is not None:
            raise TypeError("provider is only valid when source is a string id.")
        instance = source
    else:
        raise TypeError("source must be a DataSource or source id string.")

    source_id = _clean_source_id(instance.id)
    instance.id = source_id
    if not replace and source_id in _REGISTRY:
        raise ValueError(f"Data source already registered: {source_id}")
    _REGISTRY[source_id] = instance
    return instance


def unregister(source_id: str) -> None:
    """Remove a registered data source."""

    _REGISTRY.pop(source_id, None)


def clear() -> None:
    """Remove all registered data sources."""

    _REGISTRY.clear()
    _IMPORT_STATUS.clear()


def get(source_id: str) -> DataSource:
    """Return a registered data source by id."""

    clean_id = _clean_source_id(source_id)
    if clean_id not in _REGISTRY:
        auto_register_connections(source_id=clean_id, raise_errors=False)
    try:
        return _REGISTRY[clean_id]
    except KeyError as exc:
        status = _IMPORT_STATUS.get(clean_id) or {}
        suffix = f" Last import error: {status.get('error')}" if status.get("error") else ""
        raise KeyError(f"Unknown stateframe data source: {source_id}.{suffix}") from exc


def list_sources(*, auto_register: bool = True) -> list[dict[str, Any]]:
    """Return registered sources for UI dropdowns and diagnostics."""

    if auto_register:
        auto_register_connections(raise_errors=False)
    return [source.to_dict() for source in _REGISTRY.values()]


def save_connection(
    source_id: str,
    import_path: str,
    *,
    display_name: str | None = None,
    description: str = "",
    enabled: bool = True,
    store_query: bool = True,
    store_params: bool = True,
    replace: bool = True,
    register_now: bool = True,
) -> dict[str, Any]:
    """Persist a workspace query-source connection profile.

    The connection stores only non-secret wiring. ``import_path`` should point
    to a Python function that registers the source, for example
    ``"company_query_source.py:register"`` or
    ``"company_query_source:register"``.
    """

    clean_id = _clean_source_id(source_id)
    path = str(import_path or "").strip()
    if not path:
        raise ValueError("Connection import path cannot be empty.")
    existing = {item["id"]: item for item in load_connections()}
    if clean_id in existing and not replace:
        raise ValueError(f"Data source connection already exists: {clean_id}")
    created_at = existing.get(clean_id, {}).get("created_at") or _now()
    record = {
        "id": clean_id,
        "display_name": display_name or existing.get(clean_id, {}).get("display_name") or clean_id,
        "description": description,
        "import_path": path,
        "enabled": bool(enabled),
        "store_query": bool(store_query),
        "store_params": bool(store_params),
        "created_at": created_at,
        "updated_at": _now(),
    }
    existing[clean_id] = _json_safe(record)
    _write_connections(list(existing.values()))
    if register_now and enabled:
        try:
            register_connection(record, raise_errors=True)
        except Exception as exc:
            _IMPORT_STATUS[clean_id] = {
                "status": "error",
                "error": str(exc),
                "imported_at": _now(),
            }
            raise
    return {**record, **(_IMPORT_STATUS.get(clean_id) or {})}


def delete_connection(source_id: str, *, unregister_source: bool = False) -> None:
    """Delete a saved connection profile from the active workspace."""

    clean_id = _clean_source_id(source_id)
    records = [item for item in load_connections() if item.get("id") != clean_id]
    _write_connections(records)
    _IMPORT_STATUS.pop(clean_id, None)
    if unregister_source:
        unregister(clean_id)


def load_connections() -> list[dict[str, Any]]:
    """Load saved workspace connection profiles without importing them."""

    path = _connections_path(init=False)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataSourceError(f"Could not read stateframe source connections: {path}") from exc
    records = payload.get("connections") if isinstance(payload, dict) else []
    if not isinstance(records, list):
        return []
    return [_normalize_connection_record(item) for item in records if isinstance(item, dict)]


def list_connections(*, auto_register: bool = False) -> list[dict[str, Any]]:
    """Return saved connections enriched with import/registry status."""

    if auto_register:
        auto_register_connections(raise_errors=False)
    result = []
    for record in load_connections():
        source_id = record["id"]
        status = _IMPORT_STATUS.get(source_id) or {}
        registered = source_id in _REGISTRY
        source = _REGISTRY.get(source_id)
        result.append(
            _json_safe(
                {
                    **record,
                    "registered": registered,
                    "status": "registered" if registered else status.get("status", "not_loaded"),
                    "error": status.get("error", ""),
                    "source": source.to_dict() if source is not None else None,
                }
            )
        )
    return result


def register_connection(
    connection: str | Mapping[str, Any],
    *,
    raise_errors: bool = True,
) -> DataSource | None:
    """Import and run one saved connection profile."""

    record = _connection_record(connection)
    source_id = record["id"]
    if not record.get("enabled", True):
        _IMPORT_STATUS[source_id] = {"status": "disabled", "error": "", "imported_at": _now()}
        return _REGISTRY.get(source_id)
    try:
        before = set(_REGISTRY)
        target = _load_import_target(str(record.get("import_path") or ""))
        returned = target() if callable(target) else None
        if isinstance(returned, DataSource):
            register(returned)
        elif isinstance(returned, tuple):
            for item in returned:
                if isinstance(item, DataSource):
                    register(item)
        if source_id not in _REGISTRY and source_id in before:
            pass
        if source_id not in _REGISTRY:
            raise DataSourceError(
                f"Connection {source_id!r} imported {record.get('import_path')!r}, "
                "but no source with that id was registered. The import target should "
                "call sf.sources.register(...) or return a sf.DataSource."
            )
        _IMPORT_STATUS[source_id] = {
            "status": "registered",
            "error": "",
            "imported_at": _now(),
        }
        return _REGISTRY[source_id]
    except Exception as exc:
        _IMPORT_STATUS[source_id] = {
            "status": "error",
            "error": str(exc),
            "imported_at": _now(),
        }
        if raise_errors:
            raise
        return None


def auto_register_connections(
    *,
    source_id: str | None = None,
    raise_errors: bool = False,
) -> list[dict[str, Any]]:
    """Import enabled workspace connections into the in-memory registry."""

    global _AUTO_REGISTERING
    if _AUTO_REGISTERING:
        return []
    _AUTO_REGISTERING = True
    try:
        records = load_connections()
        if source_id is not None:
            clean_id = _clean_source_id(source_id)
            records = [item for item in records if item.get("id") == clean_id]
        statuses = []
        for record in records:
            try:
                provider = register_connection(record, raise_errors=raise_errors)
                status = {
                    "id": record["id"],
                    "status": "registered" if provider is not None else (_IMPORT_STATUS.get(record["id"], {}).get("status") or "not_loaded"),
                    "error": (_IMPORT_STATUS.get(record["id"], {}) or {}).get("error", ""),
                }
            except Exception as exc:
                if raise_errors:
                    raise
                status = {"id": record["id"], "status": "error", "error": str(exc)}
            statuses.append(status)
        return statuses
    finally:
        _AUTO_REGISTERING = False


def query(
    source: str | DataSource,
    statement: str,
    *,
    params: QueryParams = None,
    store_query: bool = True,
    store_params: bool = True,
    **kwargs: Any,
) -> QueryResult:
    """Execute a query through a registered source and attach lineage."""

    provider = get(source) if isinstance(source, str) else source
    raw_result = provider.execute(statement, params=params, **kwargs)
    result = _coerce_query_result(raw_result)
    result.source = _query_source_metadata(
        provider,
        statement,
        params=params,
        result=result,
        store_query=store_query,
        store_params=store_params,
    )
    return result


def preview(
    source: str | DataSource,
    statement: str,
    *,
    params: QueryParams = None,
    limit: int = 100,
    store_query: bool = True,
    store_params: bool = True,
    **kwargs: Any,
) -> QueryResult:
    """Preview a query through a source that supports preview."""

    provider = get(source) if isinstance(source, str) else source
    raw_result = provider.preview(statement, params=params, limit=limit, **kwargs)
    result = _coerce_query_result(raw_result)
    result.source = _query_source_metadata(
        provider,
        statement,
        params=params,
        result=result,
        store_query=store_query,
        store_params=store_params,
        preview_limit=limit,
    )
    return result


def list_objects(source: str | DataSource, path: str | None = None) -> list[dict[str, Any]]:
    """List browseable objects for a source, when supported."""

    provider = get(source) if isinstance(source, str) else source
    return [item.to_dict() for item in provider.list_objects(path)]


def _coerce_query_result(value: Any) -> QueryResult:
    if isinstance(value, QueryResult):
        return value
    return QueryResult(data=value)


def _query_source_metadata(
    provider: DataSource,
    statement: str,
    *,
    params: QueryParams,
    result: QueryResult,
    store_query: bool,
    store_params: bool,
    preview_limit: int | None = None,
) -> dict[str, Any]:
    params_dict = dict(params or {})
    metadata = {
        "kind": "query",
        "source_id": provider.id,
        "source_name": provider.display_name or provider.id,
        "provider_class": type(provider).__name__,
        "provider_module": type(provider).__module__,
        "executed_at": _now(),
        "query": statement if store_query else None,
        "query_stored": bool(store_query),
        "params": _json_safe(params_dict) if store_params else None,
        "params_stored": bool(store_params),
        "param_names": sorted(str(key) for key in params_dict),
        "query_fingerprint": _query_fingerprint(provider.id, statement, params_dict),
        "replayable": bool(store_query and provider.capabilities().get("replay", True)),
        "capabilities": _json_safe(provider.capabilities()),
        "metadata": _json_safe(result.metadata),
    }
    if preview_limit is not None:
        metadata["preview_limit"] = int(preview_limit)
    metadata.update(_json_safe(result.source))
    return metadata


def _query_fingerprint(source_id: str, statement: str, params: Mapping[str, Any]) -> str:
    payload = {
        "source_id": source_id,
        "query": statement,
        "params": _json_safe(dict(params)),
    }
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_source_id(value: str) -> str:
    source_id = str(value or "").strip()
    if not source_id:
        raise ValueError("Data source id cannot be empty.")
    if any(char.isspace() for char in source_id):
        raise ValueError("Data source id cannot contain whitespace.")
    return source_id


def _normalize_connection_record(record: Mapping[str, Any]) -> dict[str, Any]:
    source_id = _clean_source_id(str(record.get("id") or record.get("source_id") or ""))
    return {
        "id": source_id,
        "display_name": str(record.get("display_name") or source_id),
        "description": str(record.get("description") or ""),
        "import_path": str(record.get("import_path") or ""),
        "enabled": record.get("enabled") is not False,
        "store_query": record.get("store_query") is not False,
        "store_params": record.get("store_params") is not False,
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
    }


def _connection_record(connection: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(connection, str):
        clean_id = _clean_source_id(connection)
        for record in load_connections():
            if record.get("id") == clean_id:
                return record
        raise KeyError(f"Unknown stateframe source connection: {connection}")
    return _normalize_connection_record(connection)


def _connections_path(*, init: bool) -> Path:
    from stateframe import workspace

    current = workspace.current()
    if init:
        current.init()
    return current.sources_path


def _write_connections(records: list[dict[str, Any]]) -> None:
    path = _connections_path(init=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "kind": "stateframe_source_connections",
        "updated_at": _now(),
        "connections": sorted(
            [_json_safe(_normalize_connection_record(record)) for record in records],
            key=lambda item: item.get("id", ""),
        ),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _load_import_target(import_path: str) -> Callable[..., Any] | None:
    path = str(import_path or "").strip()
    if not path:
        raise ValueError("Connection import path cannot be empty.")
    module_ref, _, attr = path.partition(":")
    module = _import_connection_module(module_ref)
    if not attr:
        return None
    target: Any = module
    for part in attr.split("."):
        target = getattr(target, part)
    if not callable(target):
        raise TypeError(f"Import target is not callable: {import_path}")
    return target


def _import_connection_module(module_ref: str):
    ref = str(module_ref or "").strip()
    if not ref:
        raise ValueError("Connection import path is missing a module or file path.")
    from stateframe import workspace

    root = workspace.current().root
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    candidate = Path(ref).expanduser()
    is_path_like = (
        ref.endswith(".py")
        or "/" in ref
        or "\\" in ref
        or candidate.exists()
        or (root / candidate).exists()
    )
    if not is_path_like:
        return importlib.import_module(ref)
    resolved = candidate if candidate.is_absolute() else root / candidate
    resolved = resolved.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Connection import file does not exist: {resolved}")
    digest = hashlib.sha256(f"{resolved}:{resolved.stat().st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    module_name = f"stateframe_user_source_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import connection file: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "DataObject",
    "DataSource",
    "DataSourceError",
    "FunctionDataSource",
    "QueryResult",
    "auto_register_connections",
    "clear",
    "delete_connection",
    "get",
    "list_connections",
    "list_objects",
    "list_sources",
    "load_connections",
    "preview",
    "query",
    "register",
    "register_connection",
    "save_connection",
    "unregister",
]
