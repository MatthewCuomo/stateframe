"""Pluggable data sources for stateframe "Get Data" workflows.

Stateframe owns a small provider contract; users own the connection details for
their company systems. A provider executes a query and returns a DataFrame-like
object plus lineage metadata that can become the root source for a scan tree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


def get(source_id: str) -> DataSource:
    """Return a registered data source by id."""

    try:
        return _REGISTRY[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown stateframe data source: {source_id}") from exc


def list_sources() -> list[dict[str, Any]]:
    """Return registered sources for UI dropdowns and diagnostics."""

    return [source.to_dict() for source in _REGISTRY.values()]


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
    "clear",
    "get",
    "list_objects",
    "list_sources",
    "preview",
    "query",
    "register",
    "unregister",
]
