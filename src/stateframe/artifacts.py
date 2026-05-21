"""Helpers for replayable stateframe artifact leaves."""

from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from stateframe.models import PlotResult, Profile


def build_plot_artifact(
    profile: Profile,
    *,
    kind: str = "column",
    column: str | None = None,
    target: str | None = None,
    title: str | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Render a plot and return an artifact payload, summary, and replay code."""

    from stateframe.visuals import plot

    plot_params = dict(params or {})
    result = plot(
        profile,
        kind,
        column=column,
        target=target,
        as_result=True,
        **plot_params,
    )
    if not isinstance(result, PlotResult):
        raise TypeError("stateframe plot renderers must return PlotResult when as_result=True.")

    data_url = figure_data_url(result.figure)
    resolved_title = title or result.title
    spec = {
        "kind": kind,
        "column": column,
        "target": target,
        "params": plot_params,
    }
    artifact = {
        "kind": "plot",
        "format": "png",
        "title": resolved_title,
        "plot_id": result.id,
        "plot_kind": kind,
        "source_lens": result.source_lens,
        "spec": spec,
        "preview_data_url": data_url,
        "description": result.description,
        "interpretation_hints": list(result.interpretation_hints),
    }
    summary = {
        "artifact_kind": "plot",
        "plot_kind": kind,
        "plot_id": result.id,
        "title": resolved_title,
        "column": column,
        "target": target,
        "row_count": int(profile.data.shape[0]),
        "column_count": int(profile.data.shape[1]),
    }
    code = _plot_code(kind, column=column, target=target, params=plot_params)
    return artifact, summary, code


def figure_data_url(figure: Any) -> str:
    """Encode a matplotlib-like figure as a PNG data URL."""

    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=120, bbox_inches="tight")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def image_file_data_url(path: str | Path) -> str:
    """Return an image file as a data URL for widget previews."""

    input_path = Path(path)
    suffix = input_path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    return f"data:image/{mime};base64," + base64.b64encode(input_path.read_bytes()).decode("ascii")


def plotly_figure_payload(
    figure: Any,
    *,
    kind: str = "plot",
    name: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Return a replayable artifact payload for a Plotly figure."""

    plotly_json = plotly_figure_json(figure)
    resolved_title = title or name or _plotly_title(plotly_json) or "Plot"
    return {
        "kind": kind,
        "name": name or resolved_title,
        "title": resolved_title,
        "object_type": _object_type(figure),
        "format": "plotly_html",
        "engine": "plotly",
        "html": plotly_html(figure),
        "plotly_json": plotly_json,
        "preview_data_url": plotly_preview_data_url(figure, plotly_json=plotly_json),
    }


def plotly_figure_json(figure: Any) -> dict[str, Any]:
    """Serialize a Plotly figure to JSON-safe ``data``/``layout`` metadata."""

    try:
        import plotly.io as pio

        return json.loads(pio.to_json(figure))
    except Exception:
        try:
            from stateframe.interactive.serialize import _json_safe

            return _json_safe(figure.to_plotly_json())
        except Exception:
            return {"data": [], "layout": {}}


def plotly_html(figure: Any, *, full_html: bool = False) -> str:
    """Render a Plotly figure as embeddable HTML fallback."""

    try:
        import plotly.io as pio

        return pio.to_html(
            figure,
            full_html=full_html,
            include_plotlyjs=True,
            config={"responsive": True, "displaylogo": False},
        )
    except Exception:
        return ""


def plotly_preview_data_url(
    figure: Any,
    *,
    plotly_json: dict[str, Any] | None = None,
) -> str:
    """Return a PNG thumbnail for Plotly figures.

    Kaleido is used when available. A small matplotlib rendering is used as a
    dependency-light fallback so saved Plotly leaves still have tree thumbnails.
    """

    try:
        import plotly.io as pio

        image = pio.to_image(figure, format="png", scale=1)
        return "data:image/png;base64," + base64.b64encode(image).decode("ascii")
    except Exception:
        return _plotly_matplotlib_preview_data_url(
            plotly_json if plotly_json is not None else plotly_figure_json(figure)
        )


def persist_artifact_files(
    artifact: dict[str, Any],
    *,
    profile: Profile | None,
    entry_label: str,
    base_path: str | Path | None = None,
) -> dict[str, Any]:
    """Persist inline artifact payloads into the workspace save folder.

    The returned artifact keeps lightweight previews for the UI but adds durable
    paths for reloads after kernel restarts.
    """

    from stateframe import workspace

    current_workspace = workspace.current()
    root = Path(base_path) if base_path is not None else current_workspace.root / "stateframe_saves"
    tree_id = current_workspace.tree_id_for_profile(profile) if profile is not None else "floating"
    output_dir = root / _slug(tree_id) / _slug(entry_label)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = dict(artifact)
    saved_files: list[dict[str, Any]] = []

    if result.get("preview_data_url", "").startswith("data:image/"):
        image_path = output_dir / "preview.png"
        _write_data_url(result["preview_data_url"], image_path)
        saved_files.append(_file_record(current_workspace.root, image_path, kind="preview", format="png"))

    if result.get("html"):
        html_path = output_dir / "visual.html"
        html_path.write_text(str(result["html"]), encoding="utf-8")
        result["html_path"] = _display_path(current_workspace.root, html_path)
        saved_files.append(_file_record(current_workspace.root, html_path, kind="plotly", format="html"))

    if result.get("plotly_json") is not None:
        json_path = output_dir / "visual.plotly.json"
        json_path.write_text(
            json.dumps(result.get("plotly_json"), indent=2, default=str),
            encoding="utf-8",
        )
        result["json_path"] = _display_path(current_workspace.root, json_path)
        saved_files.append(_file_record(current_workspace.root, json_path, kind="plotly", format="json"))

    for index, preview in enumerate(result.get("previews") or [], start=1):
        if not isinstance(preview, dict):
            continue
        prefix = f"preview_{index:02d}"
        if preview.get("kind") == "terminal":
            text = "\n".join(
                part for part in [preview.get("stdout") or "", preview.get("stderr") or ""]
                if part
            )
            if text:
                text_path = output_dir / f"{prefix}_terminal.txt"
                text_path.write_text(text, encoding="utf-8")
                preview["path"] = _display_path(current_workspace.root, text_path)
                saved_files.append(_file_record(current_workspace.root, text_path, kind="terminal", format="text"))
        elif preview.get("kind") in {"image", "matplotlib"} and str(preview.get("preview_data_url") or "").startswith("data:image/"):
            image_path = output_dir / f"{prefix}.png"
            _write_data_url(str(preview["preview_data_url"]), image_path)
            preview["path"] = _display_path(current_workspace.root, image_path)
            saved_files.append(_file_record(current_workspace.root, image_path, kind="preview", format="png"))
        elif preview.get("kind") == "plotly":
            if str(preview.get("preview_data_url") or "").startswith("data:image/"):
                image_path = output_dir / f"{prefix}.png"
                _write_data_url(str(preview["preview_data_url"]), image_path)
                preview["path"] = _display_path(current_workspace.root, image_path)
                saved_files.append(_file_record(current_workspace.root, image_path, kind="preview", format="png"))
            html = preview.get("html")
            if html:
                html_path = output_dir / f"{prefix}.html"
                html_path.write_text(str(html), encoding="utf-8")
                preview["html_path"] = _display_path(current_workspace.root, html_path)
                saved_files.append(_file_record(current_workspace.root, html_path, kind="plotly", format="html"))
            if preview.get("plotly_json") is not None:
                json_path = output_dir / f"{prefix}.plotly.json"
                json_path.write_text(
                    json.dumps(preview.get("plotly_json"), indent=2, default=str),
                    encoding="utf-8",
                )
                preview["json_path"] = _display_path(current_workspace.root, json_path)
                saved_files.append(_file_record(current_workspace.root, json_path, kind="plotly", format="json"))
        elif preview.get("kind") == "dataframe" and preview.get("parquet_payload") is not None:
            frame = preview.pop("parquet_payload")
            parquet_path = output_dir / f"{prefix}.parquet"
            frame.to_parquet(parquet_path, index=True)
            preview["path"] = _display_path(current_workspace.root, parquet_path)
            saved_files.append(_file_record(current_workspace.root, parquet_path, kind="dataframe", format="parquet"))

    if result.get("code"):
        code_path = output_dir / "leaf.py"
        code_path.write_text(str(result["code"]), encoding="utf-8")
        result["code_path"] = _display_path(current_workspace.root, code_path)
        saved_files.append(_file_record(current_workspace.root, code_path, kind="code", format="python"))

    manifest = {
        "kind": "stateframe_artifact_manifest",
        "artifact_kind": result.get("kind"),
        "title": result.get("title"),
        "files": saved_files,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    saved_files.append(_file_record(current_workspace.root, manifest_path, kind="manifest", format="json"))

    result["saved"] = True
    result["save_dir"] = _display_path(current_workspace.root, output_dir)
    result["saved_files"] = saved_files
    return result


def _plot_code(
    kind: str,
    *,
    column: str | None,
    target: str | None,
    params: dict[str, Any],
) -> str:
    args = [repr(kind)]
    if column is not None:
        args.append(f"column={column!r}")
    if target is not None:
        args.append(f"target={target!r}")
    for key, value in params.items():
        args.append(f"{key}={value!r}")
    return f"plot = sf.plot(df, {', '.join(args)})"


def _write_data_url(data_url: str, path: Path) -> None:
    _, encoded = data_url.split(",", 1)
    path.write_bytes(base64.b64decode(encoded))


def _plotly_matplotlib_preview_data_url(plotly_json: dict[str, Any]) -> str:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return ""

    try:
        fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=120)
        title = _plotly_title(plotly_json) or "Interactive Plotly preview"
        drawn = False
        for trace in list(plotly_json.get("data") or [])[:6]:
            if not isinstance(trace, dict):
                continue
            if _draw_plotly_trace(ax, trace):
                drawn = True
        if not drawn:
            ax.text(0.5, 0.5, title, ha="center", va="center", fontsize=13, color="#334155")
            ax.set_axis_off()
        else:
            ax.set_title(title)
            ax.grid(True, color="#e5e7eb", linewidth=0.7)
            if len(plotly_json.get("data") or []) > 1:
                ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        buffer = BytesIO()
        fig.savefig(buffer, format="png", facecolor="white", bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return ""


def _draw_plotly_trace(ax: Any, trace: dict[str, Any]) -> bool:
    trace_type = str(trace.get("type") or "scatter")
    name = str(trace.get("name") or "") or None
    x = _plotly_values(trace.get("x"))
    y = _plotly_values(trace.get("y"))
    if trace_type in {"scatter", "scattergl"}:
        if not y:
            return False
        if not x:
            x = list(range(len(y)))
        mode = str(trace.get("mode") or "lines")
        if "lines" in mode:
            ax.plot(x, y, marker="o" if "markers" in mode else None, linewidth=1.7, label=name)
        else:
            ax.scatter(x, y, s=24, alpha=0.85, label=name)
        return True
    if trace_type == "bar":
        if not y:
            return False
        if not x:
            x = list(range(len(y)))
        if trace.get("orientation") == "h":
            ax.barh([str(item) for item in y], x, alpha=0.82, label=name)
        else:
            ax.bar([str(item) for item in x], y, alpha=0.82, label=name)
            ax.tick_params(axis="x", rotation=35)
        return True
    if trace_type == "histogram":
        values = _plotly_values(trace.get("x") or trace.get("y"))
        numeric = _numeric_values(values)
        if numeric:
            ax.hist(numeric, bins=min(40, max(8, int(len(numeric) ** 0.5))), alpha=0.82, label=name)
        elif values:
            counts: dict[str, int] = {}
            for value in values:
                key = str(value)
                counts[key] = counts.get(key, 0) + 1
            labels = list(counts)[:20]
            ax.bar(labels, [counts[label] for label in labels], alpha=0.82, label=name)
            ax.tick_params(axis="x", rotation=35)
        return bool(values)
    if trace_type == "pie":
        labels = [str(item) for item in _plotly_values(trace.get("labels"))]
        values = _numeric_values(_plotly_values(trace.get("values")))
        if labels and values:
            ax.pie(values[: len(labels)], labels=labels[: len(values)], autopct="%1.0f%%")
            return True
    if trace_type == "heatmap":
        z = trace.get("z")
        if isinstance(z, list) and z:
            ax.imshow(z, aspect="auto")
            return True
    return False


def _plotly_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _numeric_values(values: list[Any]) -> list[float]:
    result: list[float] = []
    for value in values:
        try:
            result.append(float(value))
        except (TypeError, ValueError):
            continue
    return result


def _plotly_title(plotly_json: dict[str, Any]) -> str:
    layout = plotly_json.get("layout") if isinstance(plotly_json, dict) else {}
    title = layout.get("title") if isinstance(layout, dict) else None
    if isinstance(title, dict):
        return str(title.get("text") or "")
    if title:
        return str(title)
    return ""


def _file_record(root: Path, path: Path, *, kind: str, format: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "format": format,
        "path": _display_path(root, path),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


def _display_path(root: Path, path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _slug(value: Any) -> str:
    text = str(value or "stateframe").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text or "stateframe"


def _object_type(value: Any) -> str:
    cls = value.__class__
    return f"{cls.__module__}.{cls.__name__}"


__all__ = [
    "build_plot_artifact",
    "figure_data_url",
    "image_file_data_url",
    "plotly_figure_json",
    "plotly_figure_payload",
    "plotly_html",
    "plotly_preview_data_url",
    "persist_artifact_files",
]
