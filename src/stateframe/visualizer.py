"""Declarative Plotly visual builder for stateframe.

The visualizer layer treats every chart as a replayable specification:
data bindings, filters, options, and renderer metadata are stored together so
web-created visuals can become durable ledger leaves.
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from stateframe.interactive.serialize import _json_safe
from stateframe.models import Profile


@dataclass(frozen=True)
class VisualSpec:
    """A declarative recipe for one Plotly visual."""

    kind: str
    fields: dict[str, Any] = field(default_factory=dict)
    filters: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    title: str = ""
    note: str = ""
    version: int = 1
    renderer: str = "plotly"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "renderer": self.renderer,
            "kind": self.kind,
            "title": self.title,
            "note": self.note,
            "fields": _json_safe(self.fields),
            "filters": _json_safe(self.filters),
            "options": _json_safe(self.options),
        }


def visual_catalog() -> dict[str, Any]:
    """Return the UI-readable registry of supported Plotly visuals."""

    return {
        "version": 1,
        "engine": "plotly",
        "plot_types": [_json_safe(definition) for definition in _VISUAL_DEFINITIONS],
        "filter_ops": [
            {"id": "not_empty", "label": "is not empty"},
            {"id": "empty", "label": "is empty"},
            {"id": "equals", "label": "equals"},
            {"id": "not_equals", "label": "does not equal"},
            {"id": "contains", "label": "contains"},
            {"id": "not_contains", "label": "does not contain"},
            {"id": "greater_equal", "label": ">="},
            {"id": "greater", "label": ">"},
            {"id": "less_equal", "label": "<="},
            {"id": "less", "label": "<"},
            {"id": "between", "label": "between"},
            {"id": "in", "label": "in list"},
        ],
    }


def normalize_visual_spec(spec: VisualSpec | dict[str, Any]) -> VisualSpec:
    """Coerce a user/widget spec dict into a ``VisualSpec``."""

    if isinstance(spec, VisualSpec):
        return spec
    if not isinstance(spec, dict):
        raise TypeError("Visual spec must be a VisualSpec or dict.")
    kind = str(spec.get("kind") or "histogram")
    if kind not in _DEFINITIONS_BY_ID:
        raise ValueError(f"Unknown visual kind: {kind}")
    return VisualSpec(
        kind=kind,
        title=str(spec.get("title") or ""),
        note=str(spec.get("note") or ""),
        fields={
            key: value
            for key, value in dict(spec.get("fields") or {}).items()
            if value is not None and value != "" and value != []
        },
        filters=list(spec.get("filters") or []),
        options=dict(spec.get("options") or {}),
        version=int(spec.get("version") or 1),
        renderer=str(spec.get("renderer") or "plotly"),
    )


def render_visual(
    data_or_profile: Any,
    spec: VisualSpec | dict[str, Any],
):
    """Render a Plotly figure from a DataFrame/Profile and visual spec."""

    from stateframe.api import scan

    profile = data_or_profile if isinstance(data_or_profile, Profile) else scan(data_or_profile)
    spec_obj = normalize_visual_spec(spec)
    return _render_plotly(profile.data, spec_obj)


def build_visual_artifact(
    profile: Profile,
    spec: VisualSpec | dict[str, Any],
    *,
    title: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Render a spec and return a ledger-ready artifact, summary, and code."""

    spec_obj = normalize_visual_spec(spec)
    definition = _DEFINITIONS_BY_ID[spec_obj.kind]
    frame = _apply_filters(profile.data, spec_obj.filters)
    figure = _render_plotly(frame, spec_obj)
    resolved_title = title or spec_obj.title or _default_title(definition, spec_obj)
    figure.update_layout(title=resolved_title)

    html = figure.to_html(
        include_plotlyjs=True,
        full_html=True,
        config={"responsive": True, "displaylogo": False},
    )
    artifact = {
        "kind": "plot",
        "format": "plotly_html",
        "engine": "plotly",
        "title": resolved_title,
        "plot_id": f"visual.{spec_obj.kind}",
        "plot_kind": spec_obj.kind,
        "visual_kind": spec_obj.kind,
        "visual_family": definition.get("family"),
        "spec": spec_obj.to_dict(),
        "html": html,
        "plotly_json": json.loads(figure.to_json()),
        "preview_data_url": _matplotlib_preview_data_url(frame, spec_obj, resolved_title),
        "description": definition.get("description", ""),
        "interpretation_hints": list(definition.get("hints") or []),
    }
    summary = {
        "artifact_kind": "plot",
        "engine": "plotly",
        "visual_kind": spec_obj.kind,
        "title": resolved_title,
        "row_count": int(frame.shape[0]),
        "source_row_count": int(profile.data.shape[0]),
        "column_count": int(frame.shape[1]),
        "fields": _json_safe(spec_obj.fields),
        "filter_count": len(spec_obj.filters),
    }
    return artifact, summary, _visual_code(spec_obj)


def validate_visual_spec(
    spec: VisualSpec | dict[str, Any],
    columns: list[str],
) -> list[str]:
    """Return validation messages for missing/unknown visual bindings."""

    spec_obj = normalize_visual_spec(spec)
    definition = _DEFINITIONS_BY_ID[spec_obj.kind]
    known = set(columns)
    messages: list[str] = []
    for field_def in definition.get("fields", []):
        slot = field_def["slot"]
        value = spec_obj.fields.get(slot)
        if field_def.get("required") and not value:
            messages.append(f"{field_def['label']} is required.")
        for column in _field_values(value):
            if column not in known:
                messages.append(f"Unknown column for {field_def['label']}: {column}")
    for filter_spec in spec_obj.filters:
        column = filter_spec.get("column")
        if column and column not in known:
            messages.append(f"Unknown filter column: {column}")
    return messages


def _render_plotly(frame: pd.DataFrame, spec: VisualSpec):
    import plotly.express as px

    definition = _DEFINITIONS_BY_ID[spec.kind]
    fields = spec.fields
    options = _resolved_options(spec)
    data = _apply_filters(frame, spec.filters)
    x = _field_value(fields.get("x"))
    y = _field_value(fields.get("y"))
    color = _field_value(fields.get("color"))
    size = _field_value(fields.get("size"))
    facet = _field_value(fields.get("facet"))
    hover = _field_values(fields.get("hover"))
    title = spec.title or _default_title(definition, spec)

    common = {
        "title": title,
        "template": options.get("template") or "plotly_white",
        "height": _int_option(options.get("height"), 520),
    }
    if color:
        common["color"] = color
    if facet:
        common["facet_col"] = facet
    if hover:
        common["hover_data"] = hover

    kind = spec.kind
    if kind == "histogram":
        fig = px.histogram(
            data,
            x=x,
            nbins=_int_option(options.get("nbins"), 40),
            histnorm=options.get("histnorm") or None,
            marginal=options.get("marginal") or None,
            barmode=options.get("barmode") or "overlay",
            **common,
        )
    elif kind == "box":
        fig = px.box(data, x=x, y=y, points=options.get("points") or False, **common)
    elif kind == "violin":
        fig = px.violin(data, x=x, y=y, box=bool(options.get("box")), points=options.get("points") or False, **common)
    elif kind == "ecdf":
        fig = px.ecdf(data, x=x, ecdfnorm=options.get("ecdfnorm") or None, **common)
    elif kind == "scatter":
        fig = px.scatter(
            data,
            x=x,
            y=y,
            size=size,
            opacity=_float_option(options.get("opacity"), 0.85),
            trendline=(options.get("trendline") or None),
            **common,
        )
    elif kind == "line":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, options=options)
        fig = px.line(plot_data, x=x, y=_resolved_y(y, options), markers=bool(options.get("markers")), **common)
    elif kind == "area":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, options=options)
        fig = px.area(plot_data, x=x, y=_resolved_y(y, options), **common)
    elif kind == "bar":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, options=options)
        fig = px.bar(
            plot_data,
            x=x,
            y=_resolved_y(y, options),
            barmode=options.get("barmode") or "group",
            orientation=options.get("orientation") or "v",
            **common,
        )
    elif kind == "pie":
        names = _field_value(fields.get("names")) or x
        values = _field_value(fields.get("values")) or y
        plot_data, resolved_values = _prepare_pie_data(data, names, values, options)
        fig = px.pie(plot_data, names=names, values=resolved_values, hole=_float_option(options.get("hole"), 0.0), **common)
    elif kind == "heatmap":
        fig = _heatmap_figure(data, x=x, y=y, z=_field_value(fields.get("z")), options=options, title=title)
    elif kind == "treemap":
        path = _field_values(fields.get("path"))
        if not path and x:
            path = [x]
        values = _field_value(fields.get("values")) or y
        fig = px.treemap(data, path=path, values=values, color=color, **common)
    elif kind == "scatter_matrix":
        dimensions = _field_values(fields.get("dimensions")) or _numeric_columns(data)[:4]
        fig = px.scatter_matrix(data, dimensions=dimensions, color=color, **common)
    elif kind == "missingness":
        missing = (
            data.isna()
            .mean()
            .rename("missing_ratio")
            .reset_index()
            .rename(columns={"index": "column"})
            .sort_values("missing_ratio", ascending=False)
        )
        if _int_option(options.get("top_n"), 0) > 0:
            missing = missing.head(_int_option(options.get("top_n"), 0))
        fig = px.bar(missing, x="missing_ratio", y="column", orientation="h", **common)
        fig.update_yaxes(autorange="reversed")
    else:  # pragma: no cover - registry keeps this closed.
        raise ValueError(f"Unknown visual kind: {kind}")

    _apply_layout_options(fig, options)
    return fig


def _apply_filters(frame: pd.DataFrame, filters: list[dict[str, Any]]) -> pd.DataFrame:
    result = frame
    for filter_spec in filters or []:
        column = filter_spec.get("column")
        if not column or column not in result.columns:
            continue
        op = str(filter_spec.get("op") or "contains")
        raw = result[column]
        value = filter_spec.get("value")
        value2 = filter_spec.get("value2")
        text = raw.astype("string")
        if op == "not_empty":
            mask = raw.notna() & (text.str.len().fillna(0) > 0)
        elif op == "empty":
            mask = raw.isna() | (text.str.len().fillna(0) == 0)
        elif op == "equals":
            mask = text.str.lower() == str(value).lower()
        elif op == "not_equals":
            mask = text.str.lower() != str(value).lower()
        elif op == "contains":
            mask = text.str.contains(str(value), case=False, na=False, regex=False)
        elif op == "not_contains":
            mask = ~text.str.contains(str(value), case=False, na=False, regex=False)
        elif op in {"greater", "greater_equal", "less", "less_equal", "between"}:
            comparable = _comparable_series(raw, value)
            left = _comparable_value(value, comparable)
            right = _comparable_value(value2, comparable)
            if op == "greater":
                mask = comparable > left
            elif op == "greater_equal":
                mask = comparable >= left
            elif op == "less":
                mask = comparable < left
            elif op == "less_equal":
                mask = comparable <= left
            else:
                mask = (comparable >= left) & (comparable <= right)
        elif op == "in":
            choices = [item.strip().lower() for item in str(value or "").split(",") if item.strip()]
            mask = text.str.lower().isin(choices)
        else:
            continue
        result = result[mask.fillna(False)]
    return result


def _prepare_xy_aggregation(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    facet: str | None,
    options: dict[str, Any],
) -> pd.DataFrame:
    if not x:
        return data
    aggregation = str(options.get("aggregation") or "none")
    if aggregation == "none" and y:
        return _top_n(data, x, options)
    group_cols = list(dict.fromkeys(col for col in [x, color, facet] if col and col in data.columns))
    if not group_cols:
        return data
    if aggregation == "none":
        aggregation = "count"
    if aggregation == "count" or not y:
        result = data.groupby(group_cols, dropna=False).size().reset_index(name="value")
        options["_resolved_y"] = "value"
    else:
        result = data.groupby(group_cols, dropna=False)[y].agg(aggregation).reset_index()
        options["_resolved_y"] = y
    return _top_n(result, x, options)


def _prepare_pie_data(
    data: pd.DataFrame,
    names: str | None,
    values: str | None,
    options: dict[str, Any],
) -> tuple[pd.DataFrame, str | None]:
    if not names:
        return data, values
    if values and values in data.columns:
        aggregation = str(options.get("aggregation") or "sum")
        result = data.groupby(names, dropna=False)[values].agg(aggregation).reset_index()
        return _top_n(result, names, options), values
    result = data.groupby(names, dropna=False).size().reset_index(name="value")
    return _top_n(result, names, options), "value"


def _heatmap_figure(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    z: str | None,
    options: dict[str, Any],
    title: str,
):
    import plotly.express as px

    height = _int_option(options.get("height"), 520)
    template = options.get("template") or "plotly_white"
    if x and y:
        if z and z in data.columns:
            aggregation = str(options.get("aggregation") or "mean")
            matrix = data.pivot_table(index=y, columns=x, values=z, aggfunc=aggregation)
        else:
            matrix = data.pivot_table(index=y, columns=x, aggfunc="size", fill_value=0)
        return px.imshow(matrix, aspect="auto", color_continuous_scale=options.get("color_scale") or "Viridis", title=title, height=height, template=template)
    numeric = data[_numeric_columns(data)]
    corr = numeric.corr() if numeric.shape[1] >= 2 else pd.DataFrame()
    return px.imshow(corr, aspect="auto", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, title=title, height=height, template=template)


def _top_n(data: pd.DataFrame, column: str, options: dict[str, Any]) -> pd.DataFrame:
    top_n = _int_option(options.get("top_n"), 0)
    if top_n <= 0 or column not in data.columns:
        return data
    counts = data[column].value_counts(dropna=False).head(top_n).index
    return data[data[column].isin(counts)]


def _apply_layout_options(fig: Any, options: dict[str, Any]) -> None:
    width = _int_option(options.get("width"), 0)
    if width > 0:
        fig.update_layout(width=width)
    fig.update_layout(
        showlegend=options.get("show_legend") is not False,
        margin={
            "l": _int_option(options.get("margin_l"), 60),
            "r": _int_option(options.get("margin_r"), 24),
            "t": _int_option(options.get("margin_t"), 70),
            "b": _int_option(options.get("margin_b"), 56),
        },
    )
    if options.get("log_x"):
        fig.update_xaxes(type="log")
    if options.get("log_y"):
        fig.update_yaxes(type="log")
    if options.get("x_label"):
        fig.update_xaxes(title=str(options["x_label"]))
    if options.get("y_label"):
        fig.update_yaxes(title=str(options["y_label"]))
    y_min = options.get("y_min")
    y_max = options.get("y_max")
    if y_min not in {None, ""} or y_max not in {None, ""}:
        fig.update_yaxes(range=[_optional_float(y_min), _optional_float(y_max)])
    x_min = options.get("x_min")
    x_max = options.get("x_max")
    if x_min not in {None, ""} or x_max not in {None, ""}:
        fig.update_xaxes(range=[_optional_float(x_min), _optional_float(x_max)])
    if options.get("custom_kwargs"):
        try:
            fig.update_layout(**json.loads(str(options["custom_kwargs"])))
        except Exception:
            pass


def _matplotlib_preview_data_url(frame: pd.DataFrame, spec: VisualSpec, title: str) -> str:
    """Build a small static fallback so the UI is never a blank Plotly iframe."""

    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception:
        return ""

    try:
        options = _resolved_options(spec)
        data = frame
        x = _field_value(spec.fields.get("x"))
        y = _field_value(spec.fields.get("y"))
        color = _field_value(spec.fields.get("color"))
        fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=120)
        kind = spec.kind
        if kind == "histogram" and x and x in data.columns:
            values = pd.to_numeric(data[x], errors="coerce")
            if values.notna().sum():
                ax.hist(values.dropna(), bins=_int_option(options.get("nbins"), 40), color="#2563eb", alpha=0.82)
            else:
                counts = data[x].astype("string").value_counts(dropna=False).head(_int_option(options.get("top_n"), 20) or 20)
                ax.bar(counts.index.astype(str), counts.values, color="#2563eb", alpha=0.82)
                ax.tick_params(axis="x", rotation=35)
        elif kind in {"scatter", "line"} and x and y and x in data.columns and y in data.columns:
            plot_data = data[[x, y, *([color] if color and color in data.columns else [])]].dropna(subset=[x, y])
            plot_data = plot_data.sort_values(x)
            x_values = _matplotlib_axis_values(plot_data[x])
            y_values = pd.to_numeric(plot_data[y], errors="coerce")
            valid = y_values.notna()
            if color and color in plot_data.columns:
                for label, group in plot_data[valid].groupby(color, dropna=False):
                    gx = _matplotlib_axis_values(group[x])
                    gy = pd.to_numeric(group[y], errors="coerce")
                    if kind == "line":
                        ax.plot(gx, gy, marker="o" if options.get("markers") else None, linewidth=1.8, label=str(label))
                    else:
                        ax.scatter(gx, gy, s=24, alpha=_float_option(options.get("opacity"), 0.85), label=str(label))
                ax.legend(loc="best", fontsize=8)
            elif kind == "line":
                ax.plot(x_values[valid], y_values[valid], marker="o" if options.get("markers") else None, color="#2563eb", linewidth=1.8)
            else:
                ax.scatter(x_values[valid], y_values[valid], s=24, alpha=_float_option(options.get("opacity"), 0.85), color="#2563eb")
        elif kind in {"bar", "area"} and x and x in data.columns:
            plot_data = _prepare_xy_aggregation(data, x=x, y=y if y and y in data.columns else None, color=color, facet=None, options=options)
            resolved_y = _resolved_y(y, options) or "value"
            if resolved_y not in plot_data.columns:
                resolved_y = plot_data.select_dtypes(include=[np.number]).columns[0] if len(plot_data.select_dtypes(include=[np.number]).columns) else None
            if resolved_y:
                if kind == "area":
                    ax.fill_between(_matplotlib_axis_values(plot_data[x]), pd.to_numeric(plot_data[resolved_y], errors="coerce"), alpha=0.35, color="#2563eb")
                    ax.plot(_matplotlib_axis_values(plot_data[x]), pd.to_numeric(plot_data[resolved_y], errors="coerce"), color="#2563eb")
                else:
                    ax.bar(plot_data[x].astype(str), pd.to_numeric(plot_data[resolved_y], errors="coerce"), color="#2563eb", alpha=0.82)
                    ax.tick_params(axis="x", rotation=35)
        else:
            ax.text(0.5, 0.5, "Interactive Plotly preview", ha="center", va="center", fontsize=14, color="#334155")
            ax.set_axis_off()
        ax.set_title(title)
        if x:
            ax.set_xlabel(str(x))
        if y:
            ax.set_ylabel(str(y))
        ax.grid(True, color="#e5e7eb", linewidth=0.7)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", facecolor="white", bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return ""


def _matplotlib_axis_values(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    converted = pd.to_datetime(series, errors="coerce")
    if converted.notna().sum() >= max(2, int(series.notna().sum() * 0.7)):
        return converted
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() >= max(2, int(series.notna().sum() * 0.7)):
        return numeric
    return series.astype("string")


def _resolved_options(spec: VisualSpec) -> dict[str, Any]:
    definition = _DEFINITIONS_BY_ID[spec.kind]
    options: dict[str, Any] = {}
    for group in definition.get("option_groups", []):
        for control in group.get("controls", []):
            if "default" in control:
                options[control["id"]] = control["default"]
    options.update(spec.options or {})
    return options


def _default_title(definition: dict[str, Any], spec: VisualSpec) -> str:
    primary = _field_value(spec.fields.get("x")) or _field_value(spec.fields.get("y"))
    return f"{primary} {definition['title'].lower()}" if primary else definition["title"]


def _resolved_y(y: str | None, options: dict[str, Any]) -> str | None:
    return options.get("_resolved_y") or y


def _field_value(value: Any) -> str | None:
    values = _field_values(value)
    return values[0] if values else None


def _field_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item not in {None, ""}]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _numeric_columns(data: pd.DataFrame) -> list[str]:
    return [str(column) for column in data.select_dtypes(include=[np.number]).columns]


def _comparable_series(series: pd.Series, value: Any) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() or _looks_numeric(value):
        return numeric
    return series.astype("string")


def _comparable_value(value: Any, series: pd.Series) -> Any:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(value, errors="coerce")
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return str(value)


def _looks_numeric(value: Any) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def _int_option(value: Any, default: int) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except Exception:
        return default


def _float_option(value: Any, default: float) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except Exception:
        return default


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _visual_code(spec: VisualSpec) -> str:
    return "spec = " + repr(spec.to_dict()) + "\nartifact, summary, code = sf.visual_artifact(scan, spec)"


def _field(slot: str, label: str, *, required: bool = False, semantic: list[str] | None = None, multiple: bool = False) -> dict[str, Any]:
    return {
        "slot": slot,
        "label": label,
        "required": required,
        "semantic": semantic or [],
        "multiple": multiple,
    }


def _control(id: str, label: str, kind: str, *, default: Any = None, choices: list[tuple[str, str]] | None = None, help: str = "") -> dict[str, Any]:
    result = {"id": id, "label": label, "kind": kind, "help": help}
    if default is not None:
        result["default"] = default
    if choices is not None:
        result["choices"] = [{"value": value, "label": label} for value, label in choices]
    return result


def _group(id: str, title: str, controls: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": id, "title": title, "controls": controls}


_ENCODING_FIELDS = {
    "x": _field("x", "X", required=True),
    "y": _field("y", "Y"),
    "color": _field("color", "Color"),
    "size": _field("size", "Size"),
    "facet": _field("facet", "Facet"),
    "hover": _field("hover", "Hover fields", multiple=True),
}


_COMMON_GROUPS = [
    _group(
        "data",
        "Data",
        [
            _control("aggregation", "Aggregation", "select", default="none", choices=[
                ("none", "None"),
                ("count", "Count rows"),
                ("sum", "Sum"),
                ("mean", "Mean"),
                ("median", "Median"),
                ("min", "Min"),
                ("max", "Max"),
            ]),
            _control("top_n", "Top N categories", "number", default=0),
        ],
    ),
    _group(
        "axes",
        "Axes and scales",
        [
            _control("log_x", "Log X", "checkbox", default=False),
            _control("log_y", "Log Y", "checkbox", default=False),
            _control("x_min", "X min", "text"),
            _control("x_max", "X max", "text"),
            _control("y_min", "Y min", "text"),
            _control("y_max", "Y max", "text"),
        ],
    ),
    _group(
        "labels",
        "Labels and hover",
        [
            _control("x_label", "X label", "text"),
            _control("y_label", "Y label", "text"),
        ],
    ),
    _group(
        "layout",
        "Layout",
        [
            _control("height", "Height", "number", default=520),
            _control("width", "Width", "number", default=0),
            _control("template", "Template", "select", default="plotly_white", choices=[
                ("plotly_white", "Plotly white"),
                ("plotly", "Plotly"),
                ("simple_white", "Simple white"),
                ("ggplot2", "ggplot2"),
                ("seaborn", "Seaborn"),
            ]),
            _control("show_legend", "Show legend", "checkbox", default=True),
            _control("margin_l", "Left margin", "number", default=60),
            _control("margin_r", "Right margin", "number", default=24),
            _control("margin_t", "Top margin", "number", default=70),
            _control("margin_b", "Bottom margin", "number", default=56),
        ],
    ),
    _group(
        "advanced",
        "Advanced Plotly layout",
        [
            _control("custom_kwargs", "Layout JSON", "textarea", help="Optional JSON passed to fig.update_layout()."),
        ],
    ),
]


_VISUAL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "histogram",
        "title": "Histogram",
        "family": "Distribution",
        "description": "Distribution of one numeric or categorical column.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["hover"]],
        "option_groups": [
            _group("marks", "Marks", [
                _control("nbins", "Bins", "number", default=40),
                _control("histnorm", "Normalize", "select", default="", choices=[("", "None"), ("probability", "Probability"), ("percent", "Percent"), ("density", "Density")]),
                _control("marginal", "Marginal", "select", default="", choices=[("", "None"), ("box", "Box"), ("violin", "Violin"), ("rug", "Rug")]),
                _control("barmode", "Bar mode", "select", default="overlay", choices=[("overlay", "Overlay"), ("group", "Group"), ("stack", "Stack")]),
            ]),
            *_COMMON_GROUPS,
        ],
        "hints": ["Use filters and clipping to inspect outliers without changing the saved source state."],
    },
    {
        "id": "box",
        "title": "Box Plot",
        "family": "Distribution",
        "description": "Compare numeric spread across categories.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("points", "Points", "select", default="", choices=[("", "None"), ("outliers", "Outliers"), ("all", "All")])]), *_COMMON_GROUPS],
    },
    {
        "id": "violin",
        "title": "Violin Plot",
        "family": "Distribution",
        "description": "Distribution shape and summary by category.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"]],
        "option_groups": [_group("marks", "Marks", [_control("box", "Show box", "checkbox", default=True), _control("points", "Points", "select", default="", choices=[("", "None"), ("all", "All")])]), *_COMMON_GROUPS],
    },
    {
        "id": "ecdf",
        "title": "ECDF",
        "family": "Distribution",
        "description": "Cumulative distribution for tail and threshold analysis.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"]],
        "option_groups": [_group("marks", "Marks", [_control("ecdfnorm", "Normalize", "select", default="", choices=[("", "None"), ("probability", "Probability"), ("percent", "Percent")])]), *_COMMON_GROUPS],
    },
    {
        "id": "scatter",
        "title": "Scatter",
        "family": "Relationship",
        "description": "Relationship between two measures.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["size"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("opacity", "Opacity", "number", default=0.85), _control("trendline", "Trendline", "select", default="", choices=[("", "None"), ("ols", "OLS"), ("lowess", "LOWESS")])]), *_COMMON_GROUPS],
    },
    {
        "id": "line",
        "title": "Line",
        "family": "Time and sequence",
        "description": "Trend over time, sequence, or ordered values.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("markers", "Markers", "checkbox", default=False)]), *_COMMON_GROUPS],
    },
    {
        "id": "area",
        "title": "Area",
        "family": "Time and sequence",
        "description": "Filled trend or stacked quantity over an ordered axis.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "bar",
        "title": "Bar",
        "family": "Comparison",
        "description": "Counts or aggregated values by category.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["y"], _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("barmode", "Bar mode", "select", default="group", choices=[("group", "Group"), ("stack", "Stack"), ("relative", "Relative")]), _control("orientation", "Orientation", "select", default="v", choices=[("v", "Vertical"), ("h", "Horizontal")])]), *_COMMON_GROUPS],
    },
    {
        "id": "pie",
        "title": "Pie / Donut",
        "family": "Composition",
        "description": "Share of total by category.",
        "fields": [_field("names", "Names", required=True), _field("values", "Values")],
        "option_groups": [_group("marks", "Marks", [_control("hole", "Donut hole", "number", default=0.0)]), *_COMMON_GROUPS],
    },
    {
        "id": "heatmap",
        "title": "Heatmap",
        "family": "Matrix",
        "description": "Correlation heatmap, count matrix, or aggregated pivot.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["y"], _field("z", "Value")],
        "option_groups": [_group("marks", "Marks", [_control("color_scale", "Color scale", "select", default="Viridis", choices=[("Viridis", "Viridis"), ("Blues", "Blues"), ("RdBu_r", "Red/Blue"), ("Magma", "Magma")])]), *_COMMON_GROUPS],
    },
    {
        "id": "treemap",
        "title": "Treemap",
        "family": "Composition",
        "description": "Nested composition by category path.",
        "fields": [_field("path", "Path columns", required=True, multiple=True), _field("values", "Values"), _ENCODING_FIELDS["color"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "scatter_matrix",
        "title": "Scatter Matrix",
        "family": "Relationship",
        "description": "Pairwise relationships across multiple numeric columns.",
        "fields": [_field("dimensions", "Dimensions", multiple=True), _ENCODING_FIELDS["color"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "missingness",
        "title": "Missingness",
        "family": "Quality",
        "description": "Missing-value rate by column.",
        "fields": [],
        "option_groups": _COMMON_GROUPS,
    },
]


_DEFINITIONS_BY_ID = {definition["id"]: definition for definition in _VISUAL_DEFINITIONS}


__all__ = [
    "VisualSpec",
    "build_visual_artifact",
    "normalize_visual_spec",
    "render_visual",
    "validate_visual_spec",
    "visual_catalog",
]
