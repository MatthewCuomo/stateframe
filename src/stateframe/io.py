"""Lightweight input coercion helpers."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


def describe_source(
    data: Any,
    *,
    source_path: str | Path | None = None,
    reader_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return lightweight, JSON-safe source metadata for a scan input."""

    if source_path is not None:
        source = source_from_path(source_path, reader_params=reader_params)
        if isinstance(data, pd.DataFrame):
            source["input_kind"] = "dataframe"
            source["input_rows"] = int(data.shape[0])
            source["input_columns"] = int(data.shape[1])
        return source

    if isinstance(data, pd.DataFrame):
        return {
            "kind": "dataframe",
            "class": "pandas.DataFrame",
            "rows": int(data.shape[0]),
            "columns": int(data.shape[1]),
            "attrs": {str(key): str(value) for key, value in data.attrs.items()},
            "replayable": False,
            "replay_note": "In-memory DataFrame inputs require a materialized data save for restore.",
        }

    if isinstance(data, (str, Path)):
        return source_from_path(data, reader_params=reader_params)

    return {
        "kind": "object",
        "class": type(data).__name__,
        "module": type(data).__module__,
        "has_to_pandas": hasattr(data, "to_pandas"),
        "replayable": False,
        "replay_note": "Object inputs require caller code or a materialized data save for restore.",
    }


def source_from_path(
    path: str | Path,
    *,
    reader_params: dict[str, Any] | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an editable, replayable source record for a local file path."""

    source_path = Path(path).expanduser()
    resolved_path = _resolve_table_path(source_path)
    exists = resolved_path.exists()
    stat = resolved_path.stat() if exists else None
    display_path, path_root = _display_source_path(resolved_path, source_path)
    history = list((previous or {}).get("path_history", []) or [])
    old_path = (previous or {}).get("path")
    if old_path and str(old_path) != display_path:
        history.append(str(old_path))
    return {
        "kind": "file",
        "path": display_path,
        "path_root": path_root,
        "absolute_path": str(resolved_path),
        "exists": exists,
        "suffixes": [suffix.lower() for suffix in resolved_path.suffixes],
        "size_bytes": int(stat.st_size) if stat else None,
        "modified_time": stat.st_mtime if stat else None,
        "replayable": exists,
        "reader": "stateframe.io.read_table",
        "reader_params": dict(reader_params or {}),
        "path_editable": True,
        "path_history": history,
    }


def coerce_dataframe(
    data: Any,
    *,
    reader_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Return a pandas DataFrame for common eager inputs and local files."""

    if isinstance(data, pd.DataFrame):
        return data

    if hasattr(data, "to_pandas"):
        converted = data.to_pandas()
        if isinstance(converted, pd.DataFrame):
            return converted

    if isinstance(data, (str, Path)):
        return read_table(data, **dict(reader_params or {}))

    raise TypeError(
        "stateframe currently expects a pandas DataFrame, a to_pandas() object, "
        "or a supported local file path."
    )


def read_table(path: str | Path, **reader_params: Any) -> pd.DataFrame:
    """Read a supported local data file into pandas.

    This is deliberately small and pragmatic for the bootstrap phase. It lets
    the new testing corpus be scanned directly file-by-file without introducing
    a larger backend layer yet.
    """

    path = _resolve_table_path(Path(path).expanduser())
    if not path.exists():
        raise FileNotFoundError(path)

    suffixes = [suffix.lower() for suffix in path.suffixes]
    suffix = suffixes[-1] if suffixes else ""
    compound = "".join(suffixes[-2:])

    if suffix in {".csv", ".gz"} and (suffix == ".csv" or compound == ".csv.gz"):
        return _read_delimited(path, header=reader_params.pop("header", "infer"), **reader_params)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t", **reader_params)
    if suffix in {".data", ".names"}:
        return _read_delimited(path, header=reader_params.pop("header", None), **reader_params)
    if suffix in {".txt"}:
        return _read_delimited(path, header=reader_params.pop("header", "infer"), **reader_params)
    if suffix == ".parquet":
        return pd.read_parquet(path, **reader_params)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, **reader_params)
    if suffix in {".json", ".geojson"}:
        return _read_json_like(path)
    if suffix == ".zip":
        return _read_zip_table(path)

    raise ValueError(f"Unsupported input path type: {path}")


def _read_json_like(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict) and "features" in payload and isinstance(payload["features"], list):
        rows = []
        for feature in payload["features"]:
            properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
            geometry = feature.get("geometry", {}) if isinstance(feature, dict) else {}
            row = dict(properties)
            row["geometry_type"] = geometry.get("type") if isinstance(geometry, dict) else None
            coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
            if isinstance(coords, list) and len(coords) >= 2:
                row["longitude"] = coords[0]
                row["latitude"] = coords[1]
                if len(coords) >= 3:
                    row["elevation_or_depth"] = coords[2]
            rows.append(row)
        return pd.DataFrame(rows)

    if isinstance(payload, dict) and "results" in payload and isinstance(payload["results"], list):
        return pd.json_normalize(payload["results"])

    if isinstance(payload, list):
        return pd.json_normalize(payload)

    if isinstance(payload, dict):
        return pd.json_normalize(payload)

    raise ValueError(f"Cannot normalize JSON payload from {path}")


def _read_zip_table(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        names = [
            name
            for name in zf.namelist()
            if not name.endswith("/")
            and Path(name).suffix.lower() in {".csv", ".txt", ".data", ".tsv"}
        ]
        if not names:
            return pd.DataFrame(
                [
                    {
                        "member": name,
                        "compressed_size": info.compress_size,
                        "file_size": info.file_size,
                    }
                    for name in zf.namelist()
                    for info in [zf.getinfo(name)]
                    if not name.endswith("/")
                ]
            )

        preferred = sorted(names, key=lambda name: (Path(name).suffix.lower() != ".csv", name))[0]
        with zf.open(preferred) as f:
            suffix = Path(preferred).suffix.lower()
            if suffix == ".tsv":
                df = pd.read_csv(f, sep="\t")
            elif suffix in {".data", ".txt"}:
                df = _read_delimited(f, filename=preferred, header=None if suffix == ".data" else "infer")
            else:
                df = _read_delimited(f, filename=preferred, header="infer")
        df.attrs["stateframe_zip_member"] = preferred
        return df


def _read_delimited(
    source: str | Path | Any,
    *,
    filename: str | None = None,
    header: int | str | None = "infer",
    **read_csv_kwargs: Any,
) -> pd.DataFrame:
    sample = _peek_text(source)
    sep = _sniff_separator(sample)
    kwargs: dict[str, Any] = {"header": header, **read_csv_kwargs}
    if sep == r"\s+":
        kwargs["sep"] = sep
    else:
        kwargs["sep"] = sep
    try:
        return pd.read_csv(source, **kwargs)
    except pd.errors.ParserError:
        if filename and Path(filename).suffix.lower() == ".data":
            return pd.read_csv(source, header=None, sep=r"\s+", engine="python")
        raise


def _peek_text(source: str | Path | Any, size: int = 8192) -> str:
    if isinstance(source, (str, Path)):
        with Path(source).open("rb") as f:
            data = f.read(size)
        return data.decode("utf-8", errors="replace")

    position = None
    try:
        position = source.tell()
    except Exception:
        position = None
    data = source.read(size)
    if position is not None:
        source.seek(position)
    else:
        source = BytesIO(data)
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def _sniff_separator(sample: str) -> str:
    first_lines = [line for line in sample.splitlines()[:10] if line.strip()]
    joined = "\n".join(first_lines)
    semicolons = joined.count(";")
    commas = joined.count(",")
    tabs = joined.count("\t")
    if tabs and (commas or semicolons) and tabs >= commas and tabs >= semicolons:
        return "\t"
    if semicolons and semicolons >= commas:
        return ";"
    if commas:
        return ","
    return r"\s+"


def _resolve_table_path(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    if path.exists():
        return path.resolve()

    workspace_root = _current_workspace_root()
    if workspace_root is not None:
        workspace_candidate = (workspace_root / path).resolve()
        if workspace_candidate.exists():
            return workspace_candidate
    return path.resolve()


def _display_source_path(resolved_path: Path, original_path: Path) -> tuple[str, str]:
    workspace_root = _current_workspace_root()
    if workspace_root is not None:
        try:
            return str(resolved_path.relative_to(workspace_root)), "workspace"
        except ValueError:
            pass
    if original_path.is_absolute():
        return str(resolved_path), "absolute"
    return str(original_path), "current_working_directory"


def _current_workspace_root() -> Path | None:
    try:
        from stateframe import workspace

        return workspace.current().root
    except Exception:
        return None
