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


_ROW_LEVEL_RENDER_LIMITS = {
    "geo_scatter": 5_000,
    "scatter": 10_000,
    "strip": 10_000,
    "scatter_matrix": 3_000,
    "parallel_coordinates": 3_000,
    "parallel_categories": 5_000,
    "pca_scatter": 5_000,
    "box": 20_000,
    "violin": 20_000,
}


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


@dataclass(frozen=True)
class VisualRecommendation:
    """A scored, replayable chart suggestion for a profiled dataframe."""

    id: str
    title: str
    reason: str
    score: float
    spec: VisualSpec
    family: str = ""
    columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "reason": self.reason,
            "score": float(self.score),
            "family": self.family,
            "columns": list(self.columns),
            "spec": self.spec.to_dict(),
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


def visual_recommendations(
    data_or_profile: Any,
    *,
    limit: int = 18,
) -> list[VisualRecommendation]:
    """Suggest replayable visual specs from scan metadata and column roles."""

    from stateframe.api import scan

    profile = data_or_profile if isinstance(data_or_profile, Profile) else scan(data_or_profile)
    builder = _VisualRecommendationBuilder(profile)
    return builder.build(limit=limit)


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
    _raise_for_visual_validation(spec_obj, profile.data)
    spec_obj = _safe_render_spec(profile.data, spec_obj)
    return _render_plotly(profile.data, spec_obj)


def build_visual_artifact(
    profile: Profile,
    spec: VisualSpec | dict[str, Any],
    *,
    title: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Render a spec and return a ledger-ready artifact, summary, and code."""

    spec_obj = normalize_visual_spec(spec)
    _raise_for_visual_validation(spec_obj, profile.data)
    spec_obj = _safe_render_spec(profile.data, spec_obj)
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
        "sample_rows": int(spec_obj.options.get("sample_rows") or 0),
        "sample_method": str(spec_obj.options.get("sample_method") or ""),
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


def _raise_for_visual_validation(spec: VisualSpec, frame: pd.DataFrame) -> None:
    messages = validate_visual_spec(spec, [str(column) for column in frame.columns])
    if spec.kind == "geo_scatter":
        lat = _field_value(spec.fields.get("lat"))
        lon = _field_value(spec.fields.get("lon"))
        for label, column, low, high in [
            ("Latitude", lat, -90, 90),
            ("Longitude", lon, -180, 180),
        ]:
            if not column or column not in frame.columns:
                continue
            values = pd.to_numeric(frame[column], errors="coerce")
            valid = values.dropna()
            if valid.empty:
                messages.append(f"{label} must contain numeric coordinate values.")
            elif valid.between(low, high).mean() < 0.8:
                messages.append(f"{label} values do not look like valid coordinates.")
    if messages:
        raise ValueError("Invalid visual spec: " + "; ".join(messages))


def _safe_render_spec(frame: pd.DataFrame, spec: VisualSpec) -> VisualSpec:
    """Bound row-level visuals so notebook renders stay interactive."""

    limit = _ROW_LEVEL_RENDER_LIMITS.get(spec.kind)
    if not limit or len(frame) <= limit:
        return spec
    options = dict(spec.options or {})
    requested = _int_option(options.get("sample_rows"), 0)
    if requested > 0:
        return spec
    options["sample_rows"] = limit
    options.setdefault("sample_method", "random")
    options.setdefault("sample_seed", 42)
    return VisualSpec(
        kind=spec.kind,
        fields=dict(spec.fields),
        filters=list(spec.filters),
        options=options,
        title=spec.title,
        note=spec.note,
        version=spec.version,
        renderer=spec.renderer,
    )


class _VisualRecommendationBuilder:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.columns = list(profile.column_profiles.values())
        self.recommendations: list[VisualRecommendation] = []
        self._seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

    def build(self, *, limit: int) -> list[VisualRecommendation]:
        self._missingness()
        self._geo()
        self._time_series()
        self._single_column()
        self._category_numeric()
        self._numeric_pairs()
        self._hierarchies()
        self._multivariate()
        ranked = sorted(self.recommendations, key=lambda item: item.score, reverse=True)
        return ranked[: max(1, limit)]

    @property
    def numeric(self) -> list[Any]:
        return [column for column in self.columns if _visual_numeric_column(column)]

    @property
    def categorical(self) -> list[Any]:
        return [column for column in self.columns if _visual_categorical_column(column)]

    @property
    def datetime(self) -> list[Any]:
        return [column for column in self.columns if _visual_datetime_semantic(column.semantic_type)]

    def _add(
        self,
        *,
        kind: str,
        title: str,
        reason: str,
        score: float,
        fields: dict[str, Any],
        options: dict[str, Any] | None = None,
        family: str = "",
        columns: list[str] | None = None,
    ) -> None:
        key = (kind, tuple(sorted((slot, str(value)) for slot, value in fields.items())))
        if key in self._seen:
            return
        self._seen.add(key)
        spec = VisualSpec(kind=kind, title=title, fields=fields, options=options or {})
        self.recommendations.append(
            VisualRecommendation(
                id=f"visual.{kind}.{len(self.recommendations) + 1}",
                title=title,
                reason=reason,
                score=min(1.0, max(0.0, score)),
                spec=spec,
                family=family or _DEFINITIONS_BY_ID.get(kind, {}).get("family", ""),
                columns=columns or _field_values_from_mapping(fields),
            )
        )

    def _missingness(self) -> None:
        if self.profile.summary_data.missing_cells <= 0:
            return
        self._add(
            kind="missingness",
            title="Missingness by column",
            reason="Some cells are missing; this shows where missingness is concentrated.",
            score=0.92,
            fields={},
            options={"top_n": 30},
            family="Quality",
            columns=[],
        )

    def _single_column(self) -> None:
        for column in self.numeric[:6]:
            histogram_options = {
                "marginal": "box",
                "nbins": 40,
                **_outlier_aware_histogram_options(self.profile.data, column.name),
            }
            self._add(
                kind="histogram",
                title=f"{column.name} distribution",
                reason=f"{column.name} is numeric; inspect spread, skew, and tails.",
                score=0.82 if column.semantic_type == "amount" else 0.74,
                fields={"x": column.name},
                options=histogram_options,
                family="Distribution",
                columns=[column.name],
            )
            if column.semantic_type in {"amount", "nonnegative_amount"} or _measure_sums_well(column.semantic_type):
                self._add(
                    kind="concentration_curve",
                    title=f"{column.name} concentration",
                    reason=f"{column.name} can be inspected for cumulative concentration and 80/20 effects.",
                    score=0.71,
                    fields={"values": column.name},
                    options={"concentration_sort": "descending", "show_equality_line": True},
                    family="Concentration",
                    columns=[column.name],
                )
        for column in self.categorical[:6]:
            if column.distinct_count <= 1:
                continue
            self._add(
                kind="bar",
                title=f"{column.name} counts",
                reason=f"{column.name} is categorical; compare the most common values.",
                score=0.78,
                fields={"x": column.name},
                options={"aggregation": "count", "top_n": 20, "top_n_mode": "other", "sort_by": "y_descending"},
                family="Comparison",
                columns=[column.name],
            )

    def _time_series(self) -> None:
        if not self.datetime:
            return
        time = self.profile.time or self.datetime[0].name
        measures = self._preferred_measures()[:4] or self.numeric[:4]
        for measure in measures:
            bucket = _date_bucket_for_profile(self.profile.data, time)
            self._add(
                kind="line",
                title=f"{measure.name} over {time}",
                reason="A date-like column and numeric measure support a trend view.",
                score=0.9 if self.profile.time == time else 0.84,
                fields={"x": time, "y": measure.name},
                options={"aggregation": "sum" if _measure_sums_well(measure.semantic_type) else "mean", "date_bucket": bucket, "markers": False},
                family="Time and sequence",
                columns=[time, measure.name],
            )
            self._add(
                kind="calendar_heatmap",
                title=f"{measure.name} calendar intensity",
                reason="A date-like column and numeric measure support day-level calendar intensity analysis.",
                score=0.72,
                fields={"date": time, "values": measure.name},
                options={"calendar_aggregation": "sum" if _measure_sums_well(measure.semantic_type) else "mean"},
                family="Time and sequence",
                columns=[time, measure.name],
            )
        if self.categorical and measures:
            category = self._low_cardinality_categories(max_unique=12)[:1]
            if category:
                measure = measures[0]
                self._add(
                    kind="area",
                    title=f"{measure.name} over {time} by {category[0].name}",
                    reason="A time axis, measure, and low-cardinality category support a composition trend.",
                    score=0.78,
                    fields={"x": time, "y": measure.name, "color": category[0].name},
                    options={"aggregation": "sum" if _measure_sums_well(measure.semantic_type) else "mean", "date_bucket": _date_bucket_for_profile(self.profile.data, time)},
                    family="Time and sequence",
                    columns=[time, measure.name, category[0].name],
                )
                self._add(
                    kind="bump_chart",
                    title=f"{category[0].name} rank over {time}",
                    reason="A time axis, category, and measure can show rank movement as a bump chart.",
                    score=0.69,
                    fields={"x": time, "y": measure.name, "color": category[0].name},
                    options={"aggregation": "sum" if _measure_sums_well(measure.semantic_type) else "mean", "date_bucket": _date_bucket_for_profile(self.profile.data, time)},
                    family="Comparison",
                    columns=[time, measure.name, category[0].name],
                )

    def _category_numeric(self) -> None:
        categories = self._low_cardinality_categories(max_unique=40)[:5]
        measures = self._preferred_measures()[:5] or self.numeric[:5]
        for category in categories:
            for measure in measures[:2]:
                if category.name == measure.name:
                    continue
                aggregation = "sum" if _measure_sums_well(measure.semantic_type) else "mean"
                self._add(
                    kind="bar",
                    title=f"{measure.name} by {category.name}",
                    reason="A category and measure support an aggregate comparison.",
                    score=0.84,
                    fields={"x": category.name, "y": measure.name},
                    options={"aggregation": aggregation, "top_n": 20, "top_n_mode": "other", "sort_by": "y_descending", "show_value_labels": True},
                    family="Comparison",
                    columns=[category.name, measure.name],
                )
                self._add(
                    kind="lollipop",
                    title=f"{measure.name} lollipop by {category.name}",
                    reason="A lollipop chart gives a lean ranked comparison for category values.",
                    score=0.76,
                    fields={"x": category.name, "y": measure.name},
                    options={"aggregation": aggregation, "top_n": 20, "sort_by": "y_descending"},
                    family="Comparison",
                    columns=[category.name, measure.name],
                )
                self._add(
                    kind="pareto",
                    title=f"{measure.name} Pareto by {category.name}",
                    reason="A Pareto view shows which categories drive cumulative contribution.",
                    score=0.79,
                    fields={"x": category.name, "y": measure.name},
                    options={"aggregation": aggregation, "pareto_threshold": 80},
                    family="Comparison",
                    columns=[category.name, measure.name],
                )
                self._add(
                    kind="box",
                    title=f"{measure.name} spread by {category.name}",
                    reason="Compare distribution and outliers across category groups.",
                    score=0.76,
                    fields={"x": category.name, "y": measure.name},
                    options={"points": "outliers", "top_n": 20, "top_n_mode": "other"},
                    family="Distribution",
                    columns=[category.name, measure.name],
                )

    def _numeric_pairs(self) -> None:
        numeric = self.numeric[:8]
        if len(numeric) >= 2:
            dimensions = [column.name for column in numeric[: min(10, len(numeric))]]
            self._add(
                kind="correlation_heatmap",
                title="Numeric correlation heatmap",
                reason="Several numeric columns can be scanned together for linear or monotonic relationships.",
                score=0.78,
                fields={"dimensions": dimensions},
                options={"corr_method": "pearson", "corr_text": True},
                family="Matrix",
                columns=dimensions,
            )
        for left_index, left in enumerate(numeric):
            for right in numeric[left_index + 1 : left_index + 3]:
                self._add(
                    kind="scatter",
                    title=f"{left.name} vs {right.name}",
                    reason="Two numeric columns can reveal relationship, clustering, and outliers.",
                    score=0.8,
                    fields={"x": left.name, "y": right.name},
                    options={
                        "opacity": 0.65 if len(self.profile.data) > 10_000 else 0.75,
                        "trendline": "ols" if 3 <= len(self.profile.data) <= 10_000 else "",
                        **({"sample_rows": 10_000, "sample_method": "random", "sample_seed": 42} if len(self.profile.data) > 10_000 else {}),
                    },
                    family="Relationship",
                    columns=[left.name, right.name],
                )
                if self.profile.summary_data.row_count >= 200:
                    self._add(
                        kind="density_heatmap",
                        title=f"{left.name} vs {right.name} density",
                        reason="Many rows are present; a density view reduces overplotting.",
                        score=0.74,
                        fields={"x": left.name, "y": right.name},
                        options={"nbinsx": 40, "nbinsy": 40},
                        family="Relationship",
                        columns=[left.name, right.name],
                    )

    def _hierarchies(self) -> None:
        categories = self._low_cardinality_categories(max_unique=30)
        measures = self._preferred_measures()
        if len(categories) < 2:
            return
        fields = {"path": [categories[0].name, categories[1].name]}
        columns = [categories[0].name, categories[1].name]
        if measures:
            fields["values"] = measures[0].name
            columns.append(measures[0].name)
        self._add(
            kind="treemap",
            title=f"{' / '.join(fields['path'])} composition",
            reason="Two categorical levels can be read as a hierarchy or nested composition.",
            score=0.73,
            fields=fields,
            options={"top_n": 30},
            family="Composition",
            columns=columns,
        )
        self._add(
            kind="sunburst",
            title=f"{' / '.join(fields['path'])} sunburst",
            reason="Nested categories can also be inspected as a radial hierarchy.",
            score=0.68,
            fields=fields,
            options={"top_n": 30},
            family="Composition",
            columns=columns,
        )

    def _geo(self) -> None:
        lat = next((column for column in self.columns if _is_latitude_name(column.name)), None)
        lon = next((column for column in self.columns if _is_longitude_name(column.name)), None)
        if lat and lon:
            fields = {"lat": lat.name, "lon": lon.name}
            measures = self._preferred_measures()
            categories = self._low_cardinality_categories(max_unique=12)
            if measures:
                fields["size"] = measures[0].name
            if categories:
                fields["color"] = categories[0].name
            self._add(
                kind="geo_scatter",
                title="Geographic points",
                reason="Latitude and longitude columns support a map view.",
                score=0.9,
                fields=fields,
                options={
                    "scope": "usa" if _looks_us_geo(self.profile.data, lat.name, lon.name) else "",
                    "projection": "albers usa" if _looks_us_geo(self.profile.data, lat.name, lon.name) else "natural earth",
                    **({"sample_rows": 5_000, "sample_method": "random", "sample_seed": 42} if len(self.profile.data) > 5_000 else {}),
                },
                family="Geographic",
                columns=_field_values_from_mapping(fields),
            )
        locations = [
            column
            for column in self.columns
            if (column.semantic_type in {"postal_code", "geographic"} or _is_location_name(column.name))
            and not _is_latitude_name(column.name)
            and not _is_longitude_name(column.name)
        ]
        measures = self._preferred_measures()
        if locations and measures:
            self._add(
                kind="choropleth",
                title=f"{measures[0].name} by {locations[0].name}",
                reason="A location-like code and numeric measure support a choropleth.",
                score=0.72,
                fields={"locations": locations[0].name, "values": measures[0].name},
                options=_choropleth_options(locations[0].name),
                family="Geographic",
                columns=[locations[0].name, measures[0].name],
            )

    def _multivariate(self) -> None:
        if len(self.numeric) >= 3:
            dimensions = [column.name for column in self.numeric[: min(6, len(self.numeric))]]
            self._add(
                kind="pca_scatter",
                title="PCA feature projection",
                reason="Three or more numeric columns can be projected into two dimensions for multivariate structure.",
                score=0.72,
                fields={"dimensions": dimensions},
                options={"pca_scale": True},
                family="Multivariate",
                columns=dimensions,
            )
            self._add(
                kind="parallel_coordinates",
                title="Numeric feature profile",
                reason="Several numeric columns can be compared in one multivariate view.",
                score=0.7,
                fields={"dimensions": dimensions},
                options={},
                family="Multivariate",
                columns=dimensions,
            )
        cats = self._low_cardinality_categories(max_unique=20)
        if len(cats) >= 2:
            dimensions = [column.name for column in cats[: min(5, len(cats))]]
            self._add(
                kind="parallel_categories",
                title="Categorical flow",
                reason="Several categorical columns can be inspected as paths through combinations.",
                score=0.67,
                fields={"dimensions": dimensions},
                options={},
                family="Multivariate",
                columns=dimensions,
            )

    def _preferred_measures(self) -> list[Any]:
        measures = [
            column
            for column in self.numeric
            if column.semantic_type in {"amount", "nonnegative_amount", "percentage", "proportion"}
        ]
        return measures or self.numeric

    def _low_cardinality_categories(self, *, max_unique: int) -> list[Any]:
        return [
            column
            for column in self.categorical
            if 1 < column.distinct_count <= max_unique
        ]


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
    symbol = _field_value(fields.get("symbol"))
    weight = _field_value(fields.get("weight"))
    facet = _field_value(fields.get("facet"))
    facet_row = _field_value(fields.get("facet_row"))
    text = _field_value(fields.get("text"))
    error_x = _field_value(fields.get("error_x"))
    error_y = _field_value(fields.get("error_y"))
    hover = _field_values(fields.get("hover"))
    data = _apply_data_options(data, x=x, y=y, options=options)
    layout_data = data
    layout_x = x
    layout_y = y
    title = spec.title or _default_title(definition, spec)

    common = {
        "title": title,
        "template": options.get("template") or "plotly_white",
        "height": _int_option(options.get("height"), 520),
    }
    if color:
        common["color"] = color
    color_sequence = _plotly_color_sequence(px, options.get("color_sequence"))
    if color_sequence:
        common["color_discrete_sequence"] = color_sequence
    if options.get("continuous_color_scale"):
        common["color_continuous_scale"] = options.get("continuous_color_scale")
    if facet:
        common["facet_col"] = facet
        facet_wrap = _int_option(options.get("facet_col_wrap"), 0)
        if facet_wrap > 0:
            common["facet_col_wrap"] = facet_wrap
    if facet_row:
        common["facet_row"] = facet_row
    if symbol:
        common["symbol"] = symbol
    if hover:
        common["hover_data"] = hover
    common_without_color = {key: value for key, value in common.items() if key != "color"}

    kind = spec.kind
    if kind == "histogram":
        histogram_data, histogram_x = _prepare_histogram_axis(data, x, options)
        layout_data = histogram_data
        layout_x = histogram_x
        layout_y = None
        fig = px.histogram(
            histogram_data,
            x=histogram_x,
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
            text=text,
            error_x=error_x,
            error_y=error_y,
            **common,
        )
    elif kind == "strip":
        fig = px.strip(
            data,
            x=x,
            y=y,
            stripmode=options.get("stripmode") or "overlay",
            hover_name=text,
            **common,
        )
    elif kind == "density_heatmap":
        fig = px.density_heatmap(
            data,
            x=x,
            y=y,
            z=_field_value(fields.get("z")),
            nbinsx=_int_option(options.get("nbinsx"), 0) or None,
            nbinsy=_int_option(options.get("nbinsy"), 0) or None,
            histfunc=options.get("histfunc") or None,
            histnorm=options.get("histnorm2d") or None,
            marginal_x=options.get("marginal_x") or None,
            marginal_y=options.get("marginal_y") or None,
            **common,
        )
    elif kind == "density_contour":
        fig = px.density_contour(
            data,
            x=x,
            y=y,
            z=_field_value(fields.get("z")),
            nbinsx=_int_option(options.get("nbinsx"), 0) or None,
            nbinsy=_int_option(options.get("nbinsy"), 0) or None,
            histfunc=options.get("histfunc") or None,
            histnorm=options.get("histnorm2d") or None,
            marginal_x=options.get("marginal_x") or None,
            marginal_y=options.get("marginal_y") or None,
            **common,
        )
    elif kind == "line":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, weight=weight, options=options)
        plot_data = _apply_series_window(plot_data, x=x, y=_resolved_y(y, options), color=color, facet=facet, options=options)
        layout_data = plot_data
        layout_y = _resolved_y(y, options)
        fig = px.line(
            plot_data,
            x=x,
            y=_resolved_y(y, options),
            markers=bool(options.get("markers")),
            line_shape=options.get("line_shape") or "linear",
            text=text,
            error_x=error_x,
            error_y=error_y,
            **common,
        )
    elif kind == "area":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, weight=weight, options=options)
        plot_data = _apply_series_window(plot_data, x=x, y=_resolved_y(y, options), color=color, facet=facet, options=options)
        layout_data = plot_data
        layout_y = _resolved_y(y, options)
        fig = px.area(plot_data, x=x, y=_resolved_y(y, options), **common)
    elif kind == "bar":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, weight=weight, options=options)
        layout_data = plot_data
        layout_y = _resolved_y(y, options)
        fig = px.bar(
            plot_data,
            x=x,
            y=_resolved_y(y, options),
            barmode=options.get("barmode") or "group",
            orientation=options.get("orientation") or "v",
            text=text,
            error_x=error_x,
            error_y=error_y,
            **common,
        )
    elif kind == "lollipop":
        fig, plot_data, resolved_y = _lollipop_figure(data, x=x, y=y, color=color, weight=weight, options=options, title=title, common=common)
        layout_data = plot_data
        layout_y = resolved_y
    elif kind == "slope":
        plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=facet, weight=weight, options=options)
        plot_data = _sort_visual_data(plot_data, x=x, y=_resolved_y(y, options), options={**options, "sort_by": options.get("sort_by") or "x_ascending"})
        layout_data = plot_data
        layout_y = _resolved_y(y, options)
        fig = px.line(plot_data, x=x, y=_resolved_y(y, options), markers=True, line_shape=options.get("line_shape") or "linear", text=text, **common)
    elif kind == "bump_chart":
        fig, plot_data = _bump_chart_figure(data, x=x, y=y, color=color, weight=weight, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = x
        layout_y = "rank"
    elif kind == "pareto":
        fig, plot_data, resolved_y = _pareto_figure(data, x=x, y=y, color=color, options=options, title=title, common=common)
        layout_data = plot_data
        layout_y = resolved_y
    elif kind == "concentration_curve":
        values = _field_value(fields.get("values")) or y or x
        group = _field_value(fields.get("group")) or color
        fig, plot_data = _concentration_figure(data, values=values, group=group, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = "cumulative_share_rows"
        layout_y = "cumulative_share_value"
    elif kind == "waterfall":
        fig, plot_data, resolved_y = _waterfall_figure(data, x=x, y=y, options=options, title=title, common=common)
        layout_data = plot_data
        layout_y = resolved_y
    elif kind == "funnel":
        fig, plot_data, resolved_y = _funnel_figure(data, x=x, y=y, color=color, options=options, title=title, common=common)
        layout_data = plot_data
        layout_y = resolved_y
    elif kind == "radar":
        theta = _field_value(fields.get("theta")) or x
        radius = _field_value(fields.get("r")) or y
        fig, plot_data, resolved_y = _radar_figure(data, theta=theta, radius=radius, color=color, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = theta
        layout_y = resolved_y
    elif kind == "qq_plot":
        values = _field_value(fields.get("values")) or x
        fig, plot_data = _qq_figure(data, values=values, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = "theoretical_quantile"
        layout_y = "sample_quantile"
    elif kind == "autocorrelation":
        values = y or x
        fig, plot_data = _autocorrelation_figure(data, values=values, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = "lag"
        layout_y = "autocorrelation"
    elif kind == "calendar_heatmap":
        date = _field_value(fields.get("date")) or x
        values = _field_value(fields.get("values")) or y
        fig, plot_data = _calendar_heatmap_figure(data, date=date, values=values, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = "week"
        layout_y = "weekday"
    elif kind == "pie":
        names = _field_value(fields.get("names")) or x
        values = _field_value(fields.get("values")) or y
        data = _label_missing_category(data, names, options)
        if options.get("dedupe_rows"):
            data = data.drop_duplicates()
        if names:
            data = _group_top_categories(data, names, options)
        plot_data, resolved_values = _prepare_pie_data(data, names, values, options)
        layout_data = plot_data
        layout_x = names
        layout_y = resolved_values
        fig = px.pie(plot_data, names=names, values=resolved_values, hole=_float_option(options.get("hole"), 0.0), **common)
    elif kind == "heatmap":
        fig = _heatmap_figure(data, x=x, y=y, z=_field_value(fields.get("z")), options=options, title=title)
    elif kind == "correlation_heatmap":
        dimensions = _field_values(fields.get("dimensions")) or _numeric_columns(data)
        fig, plot_data = _correlation_heatmap_figure(data, dimensions=dimensions, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = "column"
        layout_y = "row"
    elif kind == "pca_scatter":
        dimensions = _field_values(fields.get("dimensions")) or _numeric_columns(data)
        fig, plot_data = _pca_scatter_figure(data, dimensions=dimensions, color=color, options=options, title=title, common=common)
        layout_data = plot_data
        layout_x = "PC1"
        layout_y = "PC2"
    elif kind == "treemap":
        path = _field_values(fields.get("path"))
        if not path and x:
            path = [x]
        values = _field_value(fields.get("values")) or y
        fig = px.treemap(data, path=path, values=values, color=color, **common_without_color)
    elif kind == "sunburst":
        path = _field_values(fields.get("path"))
        if not path and x:
            path = [x]
        values = _field_value(fields.get("values")) or y
        fig = px.sunburst(data, path=path, values=values, color=color, **common_without_color)
    elif kind == "geo_scatter":
        lat = _field_value(fields.get("lat"))
        lon = _field_value(fields.get("lon"))
        fig = px.scatter_geo(
            data,
            lat=lat,
            lon=lon,
            color=color,
            size=size,
            hover_name=text,
            hover_data=hover or None,
            projection=options.get("projection") or "natural earth",
            scope=options.get("scope") or None,
            title=title,
            template=common["template"],
            height=common["height"],
            color_discrete_sequence=common.get("color_discrete_sequence"),
            color_continuous_scale=common.get("color_continuous_scale"),
        )
    elif kind == "choropleth":
        locations = _field_value(fields.get("locations"))
        values = _field_value(fields.get("values")) or y
        fig = px.choropleth(
            data,
            locations=locations,
            color=values,
            hover_name=text,
            hover_data=hover or None,
            locationmode=options.get("locationmode") or "USA-states",
            scope=options.get("scope") or "usa",
            title=title,
            template=common["template"],
            height=common["height"],
            color_continuous_scale=common.get("color_continuous_scale") or "Viridis",
        )
    elif kind == "scatter_matrix":
        dimensions = _field_values(fields.get("dimensions")) or _numeric_columns(data)[:4]
        fig = px.scatter_matrix(data, dimensions=dimensions, color=color, **common_without_color)
    elif kind == "parallel_coordinates":
        dimensions = _field_values(fields.get("dimensions")) or _numeric_columns(data)[:6]
        fig = px.parallel_coordinates(
            data,
            dimensions=dimensions,
            color=color,
            title=title,
            height=common["height"],
            color_continuous_scale=common.get("color_continuous_scale") or "Viridis",
        )
    elif kind == "parallel_categories":
        dimensions = _field_values(fields.get("dimensions")) or _categorical_columns(data)[:6]
        fig = px.parallel_categories(
            data,
            dimensions=dimensions,
            color=color,
            title=title,
            height=common["height"],
            color_continuous_scale=common.get("color_continuous_scale") or "Viridis",
        )
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
        layout_data = missing
        layout_x = "missing_ratio"
        layout_y = "column"
    else:  # pragma: no cover - registry keeps this closed.
        raise ValueError(f"Unknown visual kind: {kind}")

    _apply_trace_options(fig, options, kind=kind)
    _apply_layout_options(fig, options, data=layout_data, x=layout_x, y=layout_y)
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


def _apply_data_options(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    options: dict[str, Any],
) -> pd.DataFrame:
    result = data.copy()
    result = _filter_axis_range(
        result,
        x,
        min_value=options.get("x_data_min"),
        max_value=options.get("x_data_max"),
    )
    result = _filter_axis_range(
        result,
        y,
        min_value=options.get("y_data_min"),
        max_value=options.get("y_data_max"),
    )
    result = _transform_axis(result, x, options.get("x_transform"))
    result = _transform_axis(result, y, options.get("y_transform"))
    result = _bucket_datetime_axis(result, x, options.get("date_bucket"))
    result = _bin_numeric_axis(result, x, options)
    result = _label_missing_category(result, x, options)
    result = _group_top_categories(result, x, options)
    if options.get("dedupe_rows"):
        result = result.drop_duplicates()
    sample_rows = _int_option(options.get("sample_rows"), 0)
    if sample_rows > 0 and sample_rows < len(result):
        if str(options.get("sample_method") or "random") == "first":
            result = result.head(sample_rows)
        else:
            result = result.sample(n=sample_rows, random_state=_int_option(options.get("sample_seed"), 42))
    return _sort_visual_data(result, x=x, y=y, options=options)


def _prepare_xy_aggregation(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    facet: str | None,
    weight: str | None,
    options: dict[str, Any],
) -> pd.DataFrame:
    if not x:
        return data
    aggregation = str(options.get("aggregation") or "none")
    if aggregation == "none" and y:
        result = _top_n(data, x, options, value_column=y)
        result = _apply_value_transform(result, y=y, group_cols=[color, facet], options=options)
        return _sort_visual_data(result, x=x, y=y, options=options)
    group_cols = list(dict.fromkeys(col for col in [x, color, facet] if col and col in data.columns))
    if not group_cols:
        return data
    if aggregation == "none":
        aggregation = "count"
    if aggregation == "count" or not y:
        result = data.groupby(group_cols, dropna=False).size().reset_index(name="value")
        options["_resolved_y"] = "value"
    elif aggregation == "weighted_mean" and weight and weight in data.columns:
        result = _weighted_mean(data, group_cols=group_cols, y=y, weight=weight)
        options["_resolved_y"] = y
    elif aggregation in {"p25", "p75", "p90", "p95"}:
        quantile = {"p25": 0.25, "p75": 0.75, "p90": 0.9, "p95": 0.95}[aggregation]
        result = data.groupby(group_cols, dropna=False)[y].quantile(quantile).reset_index()
        options["_resolved_y"] = y
    else:
        result = data.groupby(group_cols, dropna=False)[y].agg(aggregation).reset_index()
        options["_resolved_y"] = y
    resolved_y = _resolved_y(y, options)
    result = _top_n(result, x, options, value_column=resolved_y)
    result = _apply_value_transform(result, y=resolved_y, group_cols=[color, facet], options=options)
    return _sort_visual_data(result, x=x, y=resolved_y, options=options)


def _apply_series_window(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    facet: str | None,
    options: dict[str, Any],
) -> pd.DataFrame:
    if not x or not y or x not in data.columns or y not in data.columns:
        return data
    window = _int_option(options.get("rolling_window"), 0)
    cumulative = bool(options.get("cumulative"))
    if window <= 1 and not cumulative:
        return data
    result = data.copy()
    group_cols = [column for column in [color, facet] if column and column in result.columns]
    sort_cols = [*group_cols, x]
    result = result.sort_values(sort_cols, na_position="last")
    values = pd.to_numeric(result[y], errors="coerce")
    if group_cols:
        grouped = values.groupby([result[column] for column in group_cols], dropna=False)
        if window > 1:
            stat = str(options.get("rolling_stat") or "mean")
            result[y] = grouped.transform(lambda series: _rolling_stat(series, window, stat))
        if cumulative:
            result[y] = pd.to_numeric(result[y], errors="coerce").groupby([result[column] for column in group_cols], dropna=False).cumsum()
    else:
        if window > 1:
            result[y] = _rolling_stat(values, window, str(options.get("rolling_stat") or "mean"))
        if cumulative:
            result[y] = pd.to_numeric(result[y], errors="coerce").cumsum()
    return result


def _rolling_stat(series: pd.Series, window: int, stat: str) -> pd.Series:
    rolling = series.rolling(window=window, min_periods=1)
    if stat == "sum":
        return rolling.sum()
    if stat == "median":
        return rolling.median()
    return rolling.mean()


def _filter_axis_range(
    data: pd.DataFrame,
    column: str | None,
    *,
    min_value: Any,
    max_value: Any,
) -> pd.DataFrame:
    if not column or column not in data.columns:
        return data
    if min_value in {None, ""} and max_value in {None, ""}:
        return data
    comparable = _comparable_series(data[column], min_value if min_value not in {None, ""} else max_value)
    mask = pd.Series(True, index=data.index)
    if min_value not in {None, ""}:
        mask = mask & (comparable >= _comparable_value(min_value, comparable))
    if max_value not in {None, ""}:
        mask = mask & (comparable <= _comparable_value(max_value, comparable))
    return data[mask.fillna(False)]


def _transform_axis(data: pd.DataFrame, column: str | None, transform: Any) -> pd.DataFrame:
    if not column or column not in data.columns:
        return data
    transform = str(transform or "none")
    if transform == "none":
        return data
    result = data.copy()
    values = pd.to_numeric(result[column], errors="coerce")
    if transform == "log":
        result[column] = np.log(values.where(values > 0))
    elif transform == "log1p":
        result[column] = np.log1p(values.where(values >= 0))
    elif transform == "sqrt":
        result[column] = np.sqrt(values.where(values >= 0))
    else:
        return data
    return result


def _bucket_datetime_axis(data: pd.DataFrame, column: str | None, bucket: Any) -> pd.DataFrame:
    if not column or column not in data.columns:
        return data
    bucket = str(bucket or "none")
    if bucket == "none":
        return data
    converted = pd.to_datetime(data[column], errors="coerce")
    if converted.notna().sum() < max(2, int(data[column].notna().sum() * 0.6)):
        return data
    result = data.copy()
    if bucket == "day":
        result[column] = converted.dt.floor("D")
    elif bucket == "week":
        result[column] = converted.dt.to_period("W").dt.start_time
    elif bucket == "month":
        result[column] = converted.dt.to_period("M").dt.start_time
    elif bucket == "quarter":
        result[column] = converted.dt.to_period("Q").dt.start_time
    elif bucket == "year":
        result[column] = converted.dt.to_period("Y").dt.start_time
    return result


def _group_top_categories(data: pd.DataFrame, column: str | None, options: dict[str, Any]) -> pd.DataFrame:
    if not column or column not in data.columns:
        return data
    if str(options.get("top_n_mode") or "filter") != "other":
        return data
    top_n = _int_option(options.get("top_n"), 0)
    if top_n <= 0:
        return data
    values = data[column]
    if pd.api.types.is_numeric_dtype(values) and values.nunique(dropna=True) > top_n * 3:
        return data
    counts = values.value_counts(dropna=False)
    if str(options.get("top_n_direction") or "top") == "bottom":
        top_values = counts.tail(top_n).index
    else:
        top_values = counts.head(top_n).index
    other_label = str(options.get("other_label") or "Other")
    result = data.copy()
    result[column] = result[column].where(result[column].isin(top_values), other_label)
    return result


def _label_missing_category(data: pd.DataFrame, column: str | None, options: dict[str, Any]) -> pd.DataFrame:
    if not options.get("include_missing_category") or not column or column not in data.columns:
        return data
    values = data[column]
    if pd.api.types.is_numeric_dtype(values) and str(options.get("x_bin_method") or "none") == "none":
        return data
    missing = values.isna() | values.astype("string").str.strip().isin([""])
    if not bool(missing.any()):
        return data
    result = data.copy()
    result[column] = result[column].astype("string").mask(missing, str(options.get("missing_category_label") or "Missing"))
    return result


def _prepare_histogram_axis(
    data: pd.DataFrame,
    column: str | None,
    options: dict[str, Any],
) -> tuple[pd.DataFrame, str | None]:
    if not column or column not in data.columns:
        return data, column
    method = str(options.get("bin_method") or "auto")
    if method in {"auto", "count"}:
        return data, column
    values = pd.to_numeric(data[column], errors="coerce")
    finite = values[np.isfinite(values)].dropna()
    if finite.empty:
        return data, column
    result = data.copy()
    target = _unique_column(result, f"{column}_bin")
    if method == "quantile":
        bins = max(2, _int_option(options.get("quantile_bins"), _int_option(options.get("nbins"), 10) or 10))
        try:
            labels = pd.qcut(values, q=bins, duplicates="drop")
        except ValueError:
            return data, column
    elif method == "width":
        width = _float_option(options.get("bin_width"), 0.0)
        if width <= 0:
            return data, column
        lower = np.floor(float(finite.min()) / width) * width
        upper = np.ceil(float(finite.max()) / width) * width
        edges = np.arange(lower, upper + width * 1.5, width)
        if len(edges) < 2:
            return data, column
        labels = pd.cut(values, bins=edges, include_lowest=True)
    else:
        return data, column
    result[target] = labels.astype("string").fillna("Missing")
    return result, target


def _bin_numeric_axis(data: pd.DataFrame, column: str | None, options: dict[str, Any]) -> pd.DataFrame:
    if not column or column not in data.columns:
        return data
    method = str(options.get("x_bin_method") or "none")
    if method == "none":
        return data
    values = pd.to_numeric(data[column], errors="coerce")
    finite = values[np.isfinite(values)].dropna()
    if finite.empty:
        return data
    result = data.copy()
    if method == "quantile":
        bins = max(2, _int_option(options.get("x_bin_count"), 4))
        try:
            labels = pd.qcut(values, q=bins, duplicates="drop")
        except ValueError:
            return data
    elif method == "width":
        width = _float_option(options.get("x_bin_width"), 0.0)
        if width <= 0:
            return data
        lower = np.floor(float(finite.min()) / width) * width
        upper = np.ceil(float(finite.max()) / width) * width
        edges = np.arange(lower, upper + width * 1.5, width)
        if len(edges) < 2:
            return data
        labels = pd.cut(values, bins=edges, include_lowest=True)
    else:
        return data
    result[column] = labels.astype("string").fillna("Missing")
    return result


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
        result = _top_n(result, names, options, value_column=values)
        result = _apply_value_transform(result, y=values, group_cols=[], options=options)
        return _sort_visual_data(result, x=names, y=values, options=options), values
    result = data.groupby(names, dropna=False).size().reset_index(name="value")
    result = _top_n(result, names, options, value_column="value")
    result = _apply_value_transform(result, y="value", group_cols=[], options=options)
    return _sort_visual_data(result, x=names, y="value", options=options), "value"


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


def _correlation_heatmap_figure(
    data: pd.DataFrame,
    *,
    dimensions: list[str],
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.express as px

    columns = [column for column in dimensions if column in data.columns]
    numeric = data[columns].apply(pd.to_numeric, errors="coerce") if columns else data[_numeric_columns(data)]
    if numeric.shape[1] < 2:
        matrix = pd.DataFrame()
    else:
        method = str(options.get("corr_method") or "pearson")
        matrix = numeric.corr(method=method)
        if options.get("corr_abs"):
            matrix = matrix.abs()
        if options.get("corr_triangle"):
            mask = np.triu(np.ones(matrix.shape, dtype=bool), k=1)
            matrix = matrix.mask(mask)
    plot_data = (
        matrix.reset_index().rename(columns={"index": "row"}).melt(id_vars="row", var_name="column", value_name="correlation")
        if not matrix.empty
        else pd.DataFrame(columns=["row", "column", "correlation"])
    )
    fig = px.imshow(
        matrix,
        aspect="auto",
        color_continuous_scale=options.get("continuous_color_scale") or "RdBu_r",
        zmin=0 if options.get("corr_abs") else -1,
        zmax=1,
        title=title,
        height=common.get("height"),
        template=common.get("template"),
        text_auto=".2f" if options.get("corr_text") else False,
    )
    return fig, plot_data


def _pca_scatter_figure(
    data: pd.DataFrame,
    *,
    dimensions: list[str],
    color: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.express as px

    columns = [column for column in dimensions if column in data.columns]
    numeric = data[columns].apply(pd.to_numeric, errors="coerce") if columns else data[_numeric_columns(data)]
    numeric = numeric.dropna(axis=1, how="all")
    if numeric.shape[1] < 2 or numeric.shape[0] < 2:
        return px.scatter(pd.DataFrame(), title=title), pd.DataFrame()
    filled = numeric.copy()
    for column in filled.columns:
        filled[column] = filled[column].fillna(filled[column].median() if filled[column].notna().any() else 0)
    values = filled.to_numpy(dtype=float)
    if options.get("pca_scale") is not False:
        center = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale == 0] = 1
        values = (values - center) / scale
    else:
        values = values - values.mean(axis=0)
    _, singular, vt = np.linalg.svd(values, full_matrices=False)
    components = values @ vt[:2].T
    explained = (singular**2) / max(1, values.shape[0] - 1)
    explained_ratio = explained / explained.sum() if explained.sum() else np.zeros_like(explained)
    plot_data = pd.DataFrame({"PC1": components[:, 0], "PC2": components[:, 1]}, index=filled.index)
    if color and color in data.columns:
        plot_data[color] = data.loc[filled.index, color].to_numpy()
    fig = px.scatter(
        plot_data,
        x="PC1",
        y="PC2",
        color=color if color in plot_data.columns else None,
        title=title,
        template=common.get("template"),
        height=common.get("height"),
        color_discrete_sequence=common.get("color_discrete_sequence"),
        color_continuous_scale=common.get("color_continuous_scale"),
    )
    fig.update_xaxes(title=f"PC1 ({explained_ratio[0] * 100:.1f}%)")
    fig.update_yaxes(title=f"PC2 ({explained_ratio[1] * 100:.1f}%)")
    return fig, plot_data


def _pareto_figure(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame, str]:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=None, weight=None, options={**options, "sort_by": "y_descending"})
    resolved_y = _resolved_y(y, options) or "value"
    if not x or x not in plot_data.columns or resolved_y not in plot_data.columns:
        return go.Figure(), plot_data, resolved_y
    values = pd.to_numeric(plot_data[resolved_y], errors="coerce").fillna(0)
    plot_data = plot_data.assign(_pareto_value=values).sort_values("_pareto_value", ascending=False)
    total = float(plot_data["_pareto_value"].sum())
    plot_data["cumulative_percent"] = plot_data["_pareto_value"].cumsum() / total * 100 if total else 0
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=plot_data[x].astype("string"), y=plot_data["_pareto_value"], name=resolved_y, secondary_y=False)
    fig.add_scatter(x=plot_data[x].astype("string"), y=plot_data["cumulative_percent"], mode="lines+markers", name="Cumulative %", secondary_y=True)
    threshold = _float_option(options.get("pareto_threshold"), 80.0)
    if threshold > 0:
        fig.add_hline(y=threshold, line_dash="dash", line_color="#dc2626", secondary_y=True)
    fig.update_layout(title=title, template=common.get("template"), height=common.get("height"))
    fig.update_yaxes(title_text=str(resolved_y), secondary_y=False)
    fig.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
    return fig, plot_data.drop(columns=["_pareto_value"]), resolved_y


def _concentration_figure(
    data: pd.DataFrame,
    *,
    values: str | None,
    group: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.graph_objects as go

    fig = go.Figure()
    frames: list[pd.DataFrame] = []
    if not values or values not in data.columns:
        return fig, pd.DataFrame()
    groups = [(None, data)] if not group or group not in data.columns else list(data.groupby(group, dropna=False))
    sort_order = str(options.get("concentration_sort") or "descending")
    for label, frame in groups:
        curve = _concentration_frame(frame[values], descending=sort_order != "ascending")
        if curve.empty:
            continue
        curve[group or "group"] = "All" if label is None else str(label)
        frames.append(curve)
        fig.add_scatter(
            x=curve["cumulative_share_rows"],
            y=curve["cumulative_share_value"],
            mode="lines",
            name="All" if label is None else str(label),
            hovertemplate="Rows %{x:.1%}<br>Value %{y:.1%}<extra></extra>",
        )
    if options.get("show_equality_line") is not False:
        fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", name="Equality", line={"dash": "dash", "color": "#64748b"})
    fig.update_layout(title=title, template=common.get("template"), height=common.get("height"), xaxis_title="Cumulative share of rows", yaxis_title="Cumulative share of value")
    return fig, pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _concentration_frame(series: pd.Series, *, descending: bool) -> pd.DataFrame:
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values >= 0]
    if values.empty:
        return pd.DataFrame()
    values = values.sort_values(ascending=not descending).reset_index(drop=True)
    total = float(values.sum())
    n = int(values.shape[0])
    return pd.DataFrame(
        {
            "cumulative_share_rows": np.arange(1, n + 1) / n,
            "cumulative_share_value": values.cumsum() / total if total else np.zeros(n),
            "value": values,
        }
    )


def _waterfall_figure(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame, str]:
    import plotly.graph_objects as go

    plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=None, facet=None, weight=None, options=options)
    resolved_y = _resolved_y(y, options) or "value"
    if not x or x not in plot_data.columns or resolved_y not in plot_data.columns:
        return go.Figure(), plot_data, resolved_y
    measure = ["relative"] * int(plot_data.shape[0])
    if options.get("waterfall_total"):
        total_label = str(options.get("waterfall_total_label") or "Total")
        total_row = pd.DataFrame({x: [total_label], resolved_y: [plot_data[resolved_y].sum()]})
        plot_data = pd.concat([plot_data, total_row], ignore_index=True)
        measure.append("total")
    fig = go.Figure(go.Waterfall(x=plot_data[x].astype("string"), y=pd.to_numeric(plot_data[resolved_y], errors="coerce"), measure=measure))
    fig.update_layout(title=title, template=common.get("template"), height=common.get("height"), yaxis_title=str(resolved_y))
    return fig, plot_data, resolved_y


def _lollipop_figure(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    weight: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame, str]:
    import plotly.graph_objects as go

    plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=None, weight=weight, options=options)
    resolved_y = _resolved_y(y, options) or "value"
    if not x or x not in plot_data.columns or resolved_y not in plot_data.columns:
        return go.Figure(), plot_data, resolved_y
    plot_data = _sort_visual_data(plot_data, x=x, y=resolved_y, options=options)
    baseline = _float_option(options.get("lollipop_baseline"), 0.0)
    axis_values = plot_data[x].astype("string").tolist()
    y_values = pd.to_numeric(plot_data[resolved_y], errors="coerce").fillna(0).tolist()
    fig = go.Figure()
    for axis, value in zip(axis_values, y_values):
        fig.add_trace(
            go.Scatter(
                x=[axis, axis],
                y=[baseline, value],
                mode="lines",
                line={"color": "rgba(100,116,139,0.45)", "width": 2},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    marker: dict[str, Any] = {"size": _int_option(options.get("marker_size"), 10)}
    if color and color in plot_data.columns:
        marker["color"] = plot_data[color]
    fig.add_trace(
        go.Scatter(
            x=axis_values,
            y=y_values,
            mode="markers+text" if options.get("show_value_labels") else "markers",
            marker=marker,
            text=[_clean_float(value) for value in y_values] if options.get("show_value_labels") else None,
            textposition="top center" if options.get("label_position") in {None, "", "auto"} else options.get("label_position"),
            name=str(resolved_y),
        )
    )
    fig.update_layout(title=title, template=common.get("template"), height=common.get("height"), yaxis_title=str(resolved_y))
    return fig, plot_data, resolved_y


def _funnel_figure(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame, str]:
    import plotly.express as px

    plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=None, weight=None, options=options)
    resolved_y = _resolved_y(y, options) or "value"
    fig = px.funnel(plot_data, x=resolved_y, y=x, color=color, title=title, template=common.get("template"), height=common.get("height"))
    return fig, plot_data, resolved_y


def _bump_chart_figure(
    data: pd.DataFrame,
    *,
    x: str | None,
    y: str | None,
    color: str | None,
    weight: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.express as px

    if not x or not color:
        raise ValueError("Bump chart requires an X field and a Color/entity field.")
    plot_data = _prepare_xy_aggregation(data, x=x, y=y, color=color, facet=None, weight=weight, options=options)
    resolved_y = _resolved_y(y, options) or "value"
    if resolved_y not in plot_data.columns:
        return px.line(pd.DataFrame(), title=title), plot_data
    ascending = str(options.get("rank_order") or "high_first") == "low_first"
    plot_data = plot_data.copy()
    plot_data["rank"] = plot_data.groupby(x, dropna=False)[resolved_y].rank(method="dense", ascending=ascending)
    plot_data = plot_data.sort_values([color, x])
    fig = px.line(
        plot_data,
        x=x,
        y="rank",
        color=color,
        markers=True,
        title=title,
        template=common.get("template"),
        height=common.get("height"),
        color_discrete_sequence=common.get("color_discrete_sequence"),
    )
    fig.update_yaxes(autorange="reversed", dtick=1, title="Rank")
    return fig, plot_data


def _radar_figure(
    data: pd.DataFrame,
    *,
    theta: str | None,
    radius: str | None,
    color: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame, str]:
    import plotly.express as px

    plot_data = _prepare_xy_aggregation(data, x=theta, y=radius, color=color, facet=None, weight=None, options=options)
    resolved_y = _resolved_y(radius, options) or "value"
    fig = px.line_polar(plot_data, r=resolved_y, theta=theta, color=color, line_close=True, title=title, template=common.get("template"), height=common.get("height"))
    if options.get("radar_fill") is not False:
        fig.update_traces(fill="toself")
    return fig, plot_data, resolved_y


def _qq_figure(
    data: pd.DataFrame,
    *,
    values: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.express as px
    from statistics import NormalDist

    if not values or values not in data.columns:
        return px.scatter(pd.DataFrame(), title=title), pd.DataFrame()
    observed = pd.to_numeric(data[values], errors="coerce").dropna().sort_values().reset_index(drop=True)
    if observed.empty:
        return px.scatter(pd.DataFrame(), title=title), pd.DataFrame()
    dist = NormalDist()
    n = int(observed.shape[0])
    theoretical = [dist.inv_cdf((i - 0.5) / n) for i in range(1, n + 1)]
    plot_data = pd.DataFrame({"theoretical_quantile": theoretical, "sample_quantile": observed})
    fig = px.scatter(plot_data, x="theoretical_quantile", y="sample_quantile", title=title, template=common.get("template"), height=common.get("height"))
    slope = float(observed.std()) if observed.shape[0] > 1 else 1.0
    intercept = float(observed.mean())
    line_y = [intercept + slope * min(theoretical), intercept + slope * max(theoretical)]
    fig.add_scatter(x=[min(theoretical), max(theoretical)], y=line_y, mode="lines", name="Normal reference", line={"dash": "dash"})
    return fig, plot_data


def _calendar_heatmap_figure(
    data: pd.DataFrame,
    *,
    date: str | None,
    values: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.graph_objects as go

    if not date or date not in data.columns:
        raise ValueError("Calendar heatmap requires a date field.")
    frame = data.copy()
    frame[date] = pd.to_datetime(frame[date], errors="coerce", format="mixed")
    frame = frame.dropna(subset=[date])
    if frame.empty:
        raise ValueError("Calendar heatmap has no parseable dates.")
    selected_year = _int_option(options.get("calendar_year"), 0)
    if selected_year:
        frame = frame[frame[date].dt.year == selected_year]
    if values and values in frame.columns:
        frame["_calendar_value"] = pd.to_numeric(frame[values], errors="coerce")
        aggregation = str(options.get("calendar_aggregation") or options.get("aggregation") or "sum")
        if aggregation in {"mean", "median", "min", "max"}:
            daily = getattr(frame.groupby(frame[date].dt.date)["_calendar_value"], aggregation)()
        else:
            daily = frame.groupby(frame[date].dt.date)["_calendar_value"].sum()
    else:
        daily = frame.groupby(frame[date].dt.date).size().rename("value")
    result = daily.rename("value").reset_index().rename(columns={date: "date", "index": "date"})
    result["date"] = pd.to_datetime(result["date"])
    iso = result["date"].dt.isocalendar()
    result["week"] = iso.week.astype(int)
    result["weekday_index"] = result["date"].dt.weekday
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    result["weekday"] = result["weekday_index"].map(dict(enumerate(labels)))
    pivot = result.pivot_table(index="weekday_index", columns="week", values="value", aggfunc="sum").reindex(range(7))
    text = (
        result.assign(label=result["date"].dt.strftime("%Y-%m-%d"))
        .pivot_table(index="weekday_index", columns="week", values="label", aggfunc="first")
        .reindex(range(7))
    )
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=pivot.to_numpy(),
                x=[str(column) for column in pivot.columns],
                y=labels,
                text=text.fillna("").to_numpy(),
                hovertemplate="Week %{x}<br>%{text}<br>Value %{z}<extra></extra>",
                colorscale=common.get("color_continuous_scale") or options.get("continuous_color_scale") or "Viridis",
                colorbar={"title": values or "Rows"},
            )
        ]
    )
    fig.update_layout(title=title, template=common.get("template"), height=common.get("height"), xaxis_title="ISO week", yaxis_title="Weekday")
    return fig, result


def _autocorrelation_figure(
    data: pd.DataFrame,
    *,
    values: str | None,
    options: dict[str, Any],
    title: str,
    common: dict[str, Any],
) -> tuple[Any, pd.DataFrame]:
    import plotly.express as px

    if not values or values not in data.columns:
        return px.bar(pd.DataFrame(), title=title), pd.DataFrame()
    series = pd.to_numeric(data[values], errors="coerce").dropna()
    max_lag = max(1, _int_option(options.get("max_lag"), min(30, max(1, int(series.shape[0] / 3)))))
    rows = [{"lag": lag, "autocorrelation": _clean_float(series.autocorr(lag=lag))} for lag in range(1, max_lag + 1)]
    plot_data = pd.DataFrame(rows).dropna()
    fig = px.bar(plot_data, x="lag", y="autocorrelation", title=title, template=common.get("template"), height=common.get("height"))
    fig.add_hline(y=0, line_color="#64748b")
    return fig, plot_data


def _top_n(data: pd.DataFrame, column: str, options: dict[str, Any], *, value_column: str | None = None) -> pd.DataFrame:
    top_n = _int_option(options.get("top_n"), 0)
    if top_n <= 0 or column not in data.columns:
        return data
    if str(options.get("top_n_mode") or "filter") == "other":
        return data
    direction = str(options.get("top_n_direction") or "top")
    if value_column and value_column in data.columns:
        values = pd.to_numeric(data[value_column], errors="coerce")
        if values.notna().any():
            scores = values.groupby(data[column], dropna=False).sum(min_count=1)
            selected = (scores.nsmallest(top_n) if direction == "bottom" else scores.nlargest(top_n)).index
            return data[data[column].isin(selected)]
    counts = data[column].value_counts(dropna=False)
    selected = (counts.tail(top_n) if direction == "bottom" else counts.head(top_n)).index
    return data[data[column].isin(selected)]


def _sort_x(data: pd.DataFrame, column: str, options: dict[str, Any]) -> pd.DataFrame:
    sort_x = str(options.get("sort_x") or "auto")
    if sort_x in {"ascending", "descending"} and column in data.columns:
        return data.sort_values(column, ascending=sort_x == "ascending", na_position="last")
    return data


def _sort_visual_data(data: pd.DataFrame, *, x: str | None, y: str | None, options: dict[str, Any]) -> pd.DataFrame:
    sort_by = str(options.get("sort_by") or "auto")
    if sort_by in {"x_ascending", "x_descending"} and x and x in data.columns:
        return data.sort_values(x, ascending=sort_by == "x_ascending", na_position="last")
    if sort_by in {"y_ascending", "y_descending"} and y and y in data.columns:
        values = pd.to_numeric(data[y], errors="coerce")
        result = data.assign(_stateframe_sort_value=values)
        result = result.sort_values("_stateframe_sort_value", ascending=sort_by == "y_ascending", na_position="last")
        return result.drop(columns=["_stateframe_sort_value"])
    if sort_by == "auto" and x:
        return _sort_x(data, x, options)
    return data


def _apply_trace_options(fig: Any, options: dict[str, Any], *, kind: str) -> None:
    if not options.get("show_value_labels"):
        return
    position = str(options.get("label_position") or "auto")
    template = str(options.get("label_template") or "")
    try:
        if kind == "pie":
            fig.update_traces(
                textinfo="label+percent",
                textposition=position,
                texttemplate=template or None,
            )
        elif kind in {"bar", "histogram"}:
            fig.update_traces(
                texttemplate=template or "%{y}",
                textposition=position,
            )
    except Exception:
        pass


def _apply_value_transform(
    data: pd.DataFrame,
    *,
    y: str | None,
    group_cols: list[str | None],
    options: dict[str, Any],
) -> pd.DataFrame:
    transform = str(options.get("value_transform") or "none")
    if transform == "none" or not y or y not in data.columns:
        return data
    values = pd.to_numeric(data[y], errors="coerce")
    if not values.notna().any():
        return data
    result = data.copy()
    if transform == "percent_total":
        denominator = float(values.sum())
        result[y] = values / denominator * 100 if denominator else np.nan
    elif transform == "percent_group":
        groups = [column for column in group_cols if column and column in result.columns]
        if not groups:
            denominator = float(values.sum())
            result[y] = values / denominator * 100 if denominator else np.nan
        else:
            denominators = values.groupby([result[column] for column in groups], dropna=False).transform("sum")
            result[y] = values.where(denominators != 0) / denominators.where(denominators != 0) * 100
    elif transform == "rank_desc":
        result[y] = values.rank(method="dense", ascending=False)
    elif transform == "rank_asc":
        result[y] = values.rank(method="dense", ascending=True)
    return result


def _weighted_mean(data: pd.DataFrame, *, group_cols: list[str], y: str, weight: str) -> pd.DataFrame:
    temp = data[group_cols].copy()
    temp["_stateframe_value"] = pd.to_numeric(data[y], errors="coerce")
    temp["_stateframe_weight"] = pd.to_numeric(data[weight], errors="coerce")
    valid = temp["_stateframe_value"].notna() & temp["_stateframe_weight"].notna() & (temp["_stateframe_weight"] != 0)
    temp = temp[valid].copy()
    if temp.empty:
        return data[group_cols].drop_duplicates().assign(**{y: np.nan})
    temp["_stateframe_weighted_value"] = temp["_stateframe_value"] * temp["_stateframe_weight"]
    grouped = (
        temp.groupby(group_cols, dropna=False)
        .agg(
            _stateframe_weighted_sum=("_stateframe_weighted_value", "sum"),
            _stateframe_weight_sum=("_stateframe_weight", "sum"),
        )
        .reset_index()
    )
    grouped[y] = grouped["_stateframe_weighted_sum"] / grouped["_stateframe_weight_sum"]
    return grouped.drop(columns=["_stateframe_weighted_sum", "_stateframe_weight_sum"])


def _apply_layout_options(
    fig: Any,
    options: dict[str, Any],
    *,
    data: pd.DataFrame | None = None,
    x: str | None = None,
    y: str | None = None,
) -> None:
    width = _int_option(options.get("width"), 0)
    if width > 0:
        fig.update_layout(width=width)
    hovermode = str(options.get("hovermode") or "")
    if hovermode:
        fig.update_layout(hovermode=hovermode)
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
        fig.update_yaxes(range=_axis_range(y_min, y_max, reversed_axis=bool(options.get("reverse_y"))))
    elif options.get("reverse_y"):
        fig.update_yaxes(autorange="reversed")
    x_min = options.get("x_min")
    x_max = options.get("x_max")
    if x_min not in {None, ""} or x_max not in {None, ""}:
        fig.update_xaxes(range=_axis_range(x_min, x_max, reversed_axis=bool(options.get("reverse_x"))))
    elif options.get("reverse_x"):
        fig.update_xaxes(autorange="reversed")
    x_tick_angle = _int_option(options.get("x_tick_angle"), 0)
    if x_tick_angle:
        fig.update_xaxes(tickangle=x_tick_angle)
    if options.get("x_tick_format"):
        fig.update_xaxes(tickformat=str(options["x_tick_format"]))
    if options.get("y_tick_format"):
        fig.update_yaxes(tickformat=str(options["y_tick_format"]))
    if options.get("x_rangeslider"):
        fig.update_xaxes(rangeslider={"visible": True})
    if options.get("facet_shared_x") is False:
        fig.update_xaxes(matches=None)
    if options.get("facet_shared_y") is False:
        fig.update_yaxes(matches=None)
    zero_line = str(options.get("zero_line") or "none")
    if zero_line in {"x", "both"}:
        fig.update_xaxes(zeroline=True, zerolinewidth=1, zerolinecolor="#64748b")
    if zero_line in {"y", "both"}:
        fig.update_yaxes(zeroline=True, zerolinewidth=1, zerolinecolor="#64748b")
    _apply_reference_options(fig, options, data=data, x=x, y=y)
    if options.get("custom_kwargs"):
        try:
            fig.update_layout(**json.loads(str(options["custom_kwargs"])))
        except Exception:
            pass


def _axis_range(min_value: Any, max_value: Any, *, reversed_axis: bool = False) -> list[Any]:
    bounds = [_axis_bound(min_value), _axis_bound(max_value)]
    return list(reversed(bounds)) if reversed_axis else bounds


def _axis_bound(value: Any) -> Any:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except Exception:
        parsed = pd.to_datetime(value, errors="coerce")
        if not pd.isna(parsed):
            return parsed.isoformat()
        return str(value)


def _apply_reference_options(
    fig: Any,
    options: dict[str, Any],
    *,
    data: pd.DataFrame | None,
    x: str | None,
    y: str | None,
) -> None:
    y_reference = _axis_bound(options.get("y_reference"))
    if y_reference is not None:
        _add_hline(fig, y_reference, options.get("y_reference_label"))
    x_reference = _axis_bound(options.get("x_reference"))
    if x_reference is not None:
        _add_vline(fig, x_reference, options.get("x_reference_label"))
    band_min = _axis_bound(options.get("y_band_min"))
    band_max = _axis_bound(options.get("y_band_max"))
    if band_min is not None and band_max is not None:
        _add_hrect(fig, band_min, band_max, options.get("y_band_label"))
    stat = str(options.get("y_stat_reference") or "none")
    if stat != "none" and data is not None and y and y in data.columns:
        values = pd.to_numeric(data[y], errors="coerce").dropna()
        if not values.empty:
            statistic = _series_statistic(values, stat)
            if statistic is not None and np.isfinite(statistic):
                label = str(options.get("y_stat_reference_label") or stat.replace("_", " ").title())
                _add_hline(fig, float(statistic), label)


def _series_statistic(values: pd.Series, stat: str) -> float | None:
    if stat == "mean":
        return float(values.mean())
    if stat == "median":
        return float(values.median())
    if stat == "min":
        return float(values.min())
    if stat == "max":
        return float(values.max())
    if stat == "p90":
        return float(values.quantile(0.9))
    if stat == "p95":
        return float(values.quantile(0.95))
    return None


def _add_hline(fig: Any, value: Any, label: Any = None) -> None:
    kwargs = {"y": value, "line_dash": "dash", "line_color": "#dc2626"}
    if label not in {None, ""}:
        kwargs["annotation_text"] = str(label)
        kwargs["annotation_position"] = "top right"
    try:
        fig.add_hline(**kwargs)
    except Exception:
        fig.add_shape(type="line", x0=0, x1=1, xref="paper", y0=value, y1=value, line={"dash": "dash", "color": "#dc2626"})


def _add_vline(fig: Any, value: Any, label: Any = None) -> None:
    kwargs = {"x": value, "line_dash": "dash", "line_color": "#2563eb"}
    if label not in {None, ""}:
        kwargs["annotation_text"] = str(label)
        kwargs["annotation_position"] = "top right"
    try:
        fig.add_vline(**kwargs)
    except Exception:
        fig.add_shape(type="line", y0=0, y1=1, yref="paper", x0=value, x1=value, line={"dash": "dash", "color": "#2563eb"})


def _add_hrect(fig: Any, y0: Any, y1: Any, label: Any = None) -> None:
    kwargs = {
        "y0": y0,
        "y1": y1,
        "line_width": 0,
        "fillcolor": "#f59e0b",
        "opacity": 0.16,
    }
    if label not in {None, ""}:
        kwargs["annotation_text"] = str(label)
        kwargs["annotation_position"] = "top left"
    try:
        fig.add_hrect(**kwargs)
    except Exception:
        fig.add_shape(type="rect", x0=0, x1=1, xref="paper", y0=y0, y1=y1, line={"width": 0}, fillcolor="#f59e0b", opacity=0.16)


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
            hist_data, hist_x = _prepare_histogram_axis(data, x, options)
            values = pd.to_numeric(hist_data[hist_x], errors="coerce") if hist_x in hist_data.columns else pd.Series(dtype=float)
            if values.notna().sum():
                ax.hist(values.dropna(), bins=_int_option(options.get("nbins"), 40), color="#2563eb", alpha=0.82)
            else:
                counts = hist_data[hist_x].astype("string").value_counts(dropna=False).head(_int_option(options.get("top_n"), 20) or 20)
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
            plot_data = _prepare_xy_aggregation(data, x=x, y=y if y and y in data.columns else None, color=color, facet=None, weight=None, options=options)
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


def _field_values_from_mapping(fields: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in fields.values():
        for item in _field_values(value):
            if item not in values:
                values.append(item)
    return values


def _visual_numeric_semantic(semantic_type: str) -> bool:
    return semantic_type in {
        "numeric",
        "amount",
        "nonnegative_amount",
        "numeric-like",
        "percentage",
        "proportion",
        "numeric_discrete",
    }


def _visual_categorical_semantic(semantic_type: str) -> bool:
    return semantic_type in {
        "category",
        "string",
        "postal_code",
        "geographic",
        "binary",
        "nullable_binary",
        "boolean",
    }


def _visual_datetime_semantic(semantic_type: str) -> bool:
    return semantic_type in {"datetime", "datetime-like"}


def _visual_numeric_column(column: Any) -> bool:
    if _visual_numeric_semantic(column.semantic_type):
        return True
    dtype = str(getattr(column, "dtype", "")).lower()
    if column.semantic_type == "identifier" and _is_identifier_like_name(column.name):
        return False
    return any(token in dtype for token in ["int", "float", "decimal", "double"])


def _visual_categorical_column(column: Any) -> bool:
    if _is_latitude_name(column.name) or _is_longitude_name(column.name):
        return False
    return _visual_categorical_semantic(column.semantic_type)


def _measure_sums_well(semantic_type: str) -> bool:
    return semantic_type in {"amount", "nonnegative_amount", "numeric", "numeric-like", "numeric_discrete"}


def _outlier_aware_histogram_options(data: pd.DataFrame, column: str) -> dict[str, Any]:
    if column not in data.columns:
        return {}
    values = pd.to_numeric(data[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 50:
        return {}
    q50 = float(values.quantile(0.50))
    q95 = float(values.quantile(0.95))
    q99 = float(values.quantile(0.99))
    maximum = float(values.max())
    if q50 <= 0 or q99 <= 0:
        return {}
    if maximum >= q99 * 5 or q99 >= q50 * 20 or q95 >= q50 * 10:
        return {
            "x_data_max": _clean_float(q99),
            "nbins": 50,
        }
    return {}


def _date_bucket_for_profile(data: pd.DataFrame, column: str) -> str:
    if column not in data.columns:
        return "none"
    try:
        converted = pd.to_datetime(data[column], errors="coerce", format="mixed")
    except TypeError:
        converted = pd.to_datetime(data[column], errors="coerce")
    converted = converted.dropna()
    if converted.empty:
        return "none"
    span_days = (converted.max() - converted.min()).days
    if span_days >= 730:
        return "month"
    if span_days >= 120:
        return "week"
    if span_days >= 45:
        return "day"
    return "none"


def _is_latitude_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"lat", "latitude"} or lowered.endswith("_lat") or "latitude" in lowered


def _is_longitude_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"lon", "lng", "long", "longitude"} or lowered.endswith(("_lon", "_lng", "_long")) or "longitude" in lowered


def _is_location_name(name: str) -> bool:
    lowered = name.lower()
    tokens = {"state", "country", "county", "city", "zip", "zipcode", "postal", "postcode"}
    return lowered in tokens or any(f"_{token}" in lowered or f"{token}_" in lowered for token in tokens)


def _is_identifier_like_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"id", "key", "uuid"} or lowered.endswith("_id") or lowered.endswith("_key") or "identifier" in lowered


def _looks_us_geo(data: pd.DataFrame, lat: str, lon: str) -> bool:
    if lat not in data.columns or lon not in data.columns:
        return False
    lat_values = pd.to_numeric(data[lat], errors="coerce").dropna()
    lon_values = pd.to_numeric(data[lon], errors="coerce").dropna()
    if lat_values.empty or lon_values.empty:
        return False
    lat_ok = lat_values.between(18, 72).mean()
    lon_ok = lon_values.between(-170, -60).mean()
    return bool(lat_ok >= 0.8 and lon_ok >= 0.8)


def _choropleth_options(location_column: str) -> dict[str, Any]:
    lowered = location_column.lower()
    if lowered in {"state", "state_code", "us_state"} or "state" in lowered:
        return {"scope": "usa", "locationmode": "USA-states"}
    if "country" in lowered:
        return {"scope": "world", "locationmode": "country names"}
    return {"scope": "usa", "locationmode": "USA-states"}


def _numeric_columns(data: pd.DataFrame) -> list[str]:
    return [str(column) for column in data.select_dtypes(include=[np.number]).columns]


def _categorical_columns(data: pd.DataFrame) -> list[str]:
    return [
        str(column)
        for column in data.columns
        if not pd.api.types.is_numeric_dtype(data[column]) and not pd.api.types.is_datetime64_any_dtype(data[column])
    ]


def _unique_column(data: pd.DataFrame, base: str) -> str:
    candidate = base
    suffix = 2
    while candidate in data.columns:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


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


def _clean_float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except Exception:
        return None


def _visual_code(spec: VisualSpec) -> str:
    return (
        "spec = "
        + repr(spec.to_dict())
        + "\n"
        + "data = sf.pull()\n"
        + "artifact, summary, code = sf.visual_artifact(data, spec)"
    )


def _plotly_color_sequence(px: Any, name: Any) -> list[str] | None:
    value = str(name or "")
    if not value:
        return None
    sequence = getattr(px.colors.qualitative, value, None)
    return list(sequence) if sequence else None


def _field(slot: str, label: str, *, required: bool = False, semantic: list[str] | None = None, multiple: bool = False) -> dict[str, Any]:
    return {
        "slot": slot,
        "label": label,
        "required": required,
        "semantic": semantic or [],
        "multiple": multiple,
    }


def _control(
    id: str,
    label: str,
    kind: str,
    *,
    default: Any = None,
    choices: list[tuple[str, str]] | None = None,
    help: str = "",
    level: str | None = None,
) -> dict[str, Any]:
    result = {"id": id, "label": label, "kind": kind, "help": help, "level": level or _control_level(id)}
    if default is not None:
        result["default"] = default
    if choices is not None:
        result["choices"] = [{"value": value, "label": label} for value, label in choices]
    return result


def _group(id: str, title: str, controls: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": id, "title": title, "controls": controls}


def _control_level(control_id: str) -> str:
    basic = {
        "aggregation",
        "value_transform",
        "top_n",
        "date_bucket",
        "sort_by",
        "sort_x",
        "bin_method",
        "nbins",
        "bin_width",
        "quantile_bins",
        "histnorm",
        "marginal",
        "barmode",
        "orientation",
        "points",
        "box",
        "stripmode",
        "ecdfnorm",
        "opacity",
        "trendline",
        "markers",
        "line_shape",
        "hole",
        "color_scale",
        "scope",
        "projection",
        "locationmode",
        "pareto_threshold",
        "waterfall_total",
        "radar_fill",
        "concentration_sort",
        "show_equality_line",
        "max_lag",
        "x_data_min",
        "x_data_max",
        "y_data_min",
        "y_data_max",
        "x_min",
        "x_max",
        "y_min",
        "y_max",
        "reverse_x",
        "reverse_y",
        "show_value_labels",
        "height",
        "template",
        "color_sequence",
        "continuous_color_scale",
        "show_legend",
    }
    expert = {
        "custom_kwargs",
        "margin_l",
        "margin_r",
        "margin_t",
        "margin_b",
        "label_template",
        "hovermode",
        "x_tick_format",
        "y_tick_format",
        "facet_shared_x",
        "facet_shared_y",
        "facet_col_wrap",
        "sample_seed",
        "other_label",
        "missing_category_label",
        "waterfall_total_label",
    }
    if control_id in basic:
        return "basic"
    if control_id in expert:
        return "expert"
    return "advanced"


_ENCODING_FIELDS = {
    "x": _field("x", "X", required=True),
    "y": _field("y", "Y"),
    "color": _field("color", "Color"),
    "size": _field("size", "Size"),
    "symbol": _field("symbol", "Symbol"),
    "weight": _field("weight", "Weight"),
    "facet": _field("facet", "Facet"),
    "facet_row": _field("facet_row", "Facet row"),
    "text": _field("text", "Text label"),
    "error_x": _field("error_x", "X error"),
    "error_y": _field("error_y", "Y error"),
    "lat": _field("lat", "Latitude", required=True, semantic=["latitude"]),
    "lon": _field("lon", "Longitude", required=True, semantic=["longitude"]),
    "locations": _field("locations", "Locations", required=True),
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
                ("std", "Standard deviation"),
                ("var", "Variance"),
                ("nunique", "Unique count"),
                ("weighted_mean", "Weighted mean"),
                ("p25", "P25"),
                ("p75", "P75"),
                ("p90", "P90"),
                ("p95", "P95"),
            ]),
            _control("value_transform", "Value transform", "select", default="none", choices=[
                ("none", "None"),
                ("percent_total", "Percent of total"),
                ("percent_group", "Percent within color/facet"),
                ("rank_desc", "Rank high to low"),
                ("rank_asc", "Rank low to high"),
            ]),
            _control("top_n", "Top N categories", "number", default=0),
            _control("top_n_direction", "Top/Bottom", "select", default="top", choices=[
                ("top", "Top"),
                ("bottom", "Bottom"),
            ]),
            _control("top_n_mode", "Top N mode", "select", default="filter", choices=[
                ("filter", "Filter others out"),
                ("other", "Group others"),
            ]),
            _control("other_label", "Other label", "text", default="Other"),
            _control("include_missing_category", "Show missing category", "checkbox", default=False),
            _control("missing_category_label", "Missing label", "text", default="Missing"),
            _control("dedupe_rows", "Dedupe rows", "checkbox", default=False),
            _control("sample_rows", "Sample rows", "number", default=0),
            _control("sample_method", "Sample method", "select", default="random", choices=[
                ("random", "Random"),
                ("first", "First rows"),
            ]),
            _control("sample_seed", "Sample seed", "number", default=42),
            _control("date_bucket", "Date bucket", "select", default="none", choices=[
                ("none", "None"),
                ("day", "Day"),
                ("week", "Week"),
                ("month", "Month"),
                ("quarter", "Quarter"),
                ("year", "Year"),
            ]),
            _control("x_bin_method", "X bins", "select", default="none", choices=[
                ("none", "None"),
                ("quantile", "Quantiles"),
                ("width", "Fixed width"),
            ]),
            _control("x_bin_count", "X bin count", "number", default=4),
            _control("x_bin_width", "X bin width", "number", default=0),
            _control("sort_x", "Sort X", "select", default="auto", choices=[
                ("auto", "Auto"),
                ("ascending", "Ascending"),
                ("descending", "Descending"),
            ]),
            _control("sort_by", "Sort by", "select", default="auto", choices=[
                ("auto", "Auto"),
                ("x_ascending", "X ascending"),
                ("x_descending", "X descending"),
                ("y_ascending", "Y ascending"),
                ("y_descending", "Y descending"),
            ]),
            _control("rolling_window", "Rolling window", "number", default=0),
            _control("rolling_stat", "Rolling stat", "select", default="mean", choices=[
                ("mean", "Mean"),
                ("sum", "Sum"),
                ("median", "Median"),
            ]),
            _control("cumulative", "Cumulative", "checkbox", default=False),
        ],
    ),
    _group(
        "axes",
        "Axes and scales",
        [
            _control("log_x", "Log X", "checkbox", default=False),
            _control("log_y", "Log Y", "checkbox", default=False),
            _control("x_transform", "X transform", "select", default="none", choices=[
                ("none", "None"),
                ("log", "Log"),
                ("log1p", "Log1p"),
                ("sqrt", "Square root"),
            ]),
            _control("y_transform", "Y transform", "select", default="none", choices=[
                ("none", "None"),
                ("log", "Log"),
                ("log1p", "Log1p"),
                ("sqrt", "Square root"),
            ]),
            _control("x_data_min", "X data min", "text"),
            _control("x_data_max", "X data max", "text"),
            _control("y_data_min", "Y data min", "text"),
            _control("y_data_max", "Y data max", "text"),
            _control("x_min", "X min", "text"),
            _control("x_max", "X max", "text"),
            _control("y_min", "Y min", "text"),
            _control("y_max", "Y max", "text"),
            _control("reverse_x", "Reverse X", "checkbox", default=False),
            _control("reverse_y", "Reverse Y", "checkbox", default=False),
            _control("zero_line", "Zero line", "select", default="none", choices=[
                ("none", "None"),
                ("x", "X"),
                ("y", "Y"),
                ("both", "Both"),
            ]),
            _control("x_tick_angle", "X tick angle", "number", default=0),
            _control("x_tick_format", "X tick format", "text"),
            _control("y_tick_format", "Y tick format", "text"),
            _control("x_rangeslider", "X range slider", "checkbox", default=False),
        ],
    ),
    _group(
        "references",
        "References",
        [
            _control("y_reference", "Y reference", "text"),
            _control("y_reference_label", "Y reference label", "text"),
            _control("x_reference", "X reference", "text"),
            _control("x_reference_label", "X reference label", "text"),
            _control("y_band_min", "Y band min", "text"),
            _control("y_band_max", "Y band max", "text"),
            _control("y_band_label", "Y band label", "text"),
            _control("y_stat_reference", "Y statistic line", "select", default="none", choices=[
                ("none", "None"),
                ("mean", "Mean"),
                ("median", "Median"),
                ("min", "Min"),
                ("max", "Max"),
                ("p90", "P90"),
                ("p95", "P95"),
            ]),
            _control("y_stat_reference_label", "Statistic label", "text"),
        ],
    ),
    _group(
        "labels",
        "Labels and hover",
        [
            _control("x_label", "X label", "text"),
            _control("y_label", "Y label", "text"),
            _control("show_value_labels", "Show value labels", "checkbox", default=False),
            _control("label_position", "Label position", "select", default="auto", choices=[
                ("auto", "Auto"),
                ("inside", "Inside"),
                ("outside", "Outside"),
            ]),
            _control("label_template", "Label template", "text"),
            _control("hovermode", "Hover mode", "select", default="", choices=[
                ("", "Default"),
                ("closest", "Closest"),
                ("x", "X"),
                ("x unified", "X unified"),
                ("y", "Y"),
                ("y unified", "Y unified"),
            ]),
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
            _control("color_sequence", "Color palette", "select", default="", choices=[
                ("", "Default"),
                ("Plotly", "Plotly"),
                ("D3", "D3"),
                ("Set2", "Set2"),
                ("Dark24", "Dark24"),
                ("Pastel", "Pastel"),
                ("Safe", "Safe"),
            ]),
            _control("continuous_color_scale", "Color scale", "select", default="", choices=[
                ("", "Default"),
                ("Viridis", "Viridis"),
                ("Cividis", "Cividis"),
                ("Blues", "Blues"),
                ("Magma", "Magma"),
                ("RdBu_r", "Red/Blue"),
            ]),
            _control("facet_col_wrap", "Facet wrap", "number", default=0),
            _control("facet_shared_x", "Facet shared X", "checkbox", default=True),
            _control("facet_shared_y", "Facet shared Y", "checkbox", default=True),
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
                _control("bin_method", "Bin method", "select", default="auto", choices=[
                    ("auto", "Plotly auto"),
                    ("count", "Fixed count"),
                    ("width", "Fixed width"),
                    ("quantile", "Quantiles"),
                ]),
                _control("nbins", "Bins", "number", default=40),
                _control("bin_width", "Bin width", "number", default=0),
                _control("quantile_bins", "Quantile bins", "number", default=10),
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
        "id": "strip",
        "title": "Strip Plot",
        "family": "Distribution",
        "description": "Raw points across categories for seeing spread, overlap, and small groups.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["facet_row"], _ENCODING_FIELDS["text"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("stripmode", "Strip mode", "select", default="overlay", choices=[("overlay", "Overlay"), ("group", "Group")])]), *_COMMON_GROUPS],
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
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["symbol"], _ENCODING_FIELDS["size"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["facet_row"], _ENCODING_FIELDS["text"], _ENCODING_FIELDS["error_x"], _ENCODING_FIELDS["error_y"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("opacity", "Opacity", "number", default=0.85), _control("trendline", "Trendline", "select", default="", choices=[("", "None"), ("ols", "OLS"), ("lowess", "LOWESS")])]), *_COMMON_GROUPS],
    },
    {
        "id": "density_heatmap",
        "title": "Density Heatmap",
        "family": "Relationship",
        "description": "2D binned density or aggregated intensity across two axes.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _field("z", "Value"), _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["facet_row"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("density", "Density", [
            _control("nbinsx", "X bins", "number", default=0),
            _control("nbinsy", "Y bins", "number", default=0),
            _control("histfunc", "Cell function", "select", default="", choices=[("", "Count"), ("sum", "Sum"), ("avg", "Average"), ("min", "Min"), ("max", "Max")]),
            _control("histnorm2d", "Normalize", "select", default="", choices=[("", "None"), ("probability", "Probability"), ("density", "Density"), ("probability density", "Probability density")]),
            _control("marginal_x", "X marginal", "select", default="", choices=[("", "None"), ("histogram", "Histogram"), ("rug", "Rug"), ("box", "Box"), ("violin", "Violin")]),
            _control("marginal_y", "Y marginal", "select", default="", choices=[("", "None"), ("histogram", "Histogram"), ("rug", "Rug"), ("box", "Box"), ("violin", "Violin")]),
        ]), *_COMMON_GROUPS],
    },
    {
        "id": "density_contour",
        "title": "Density Contour",
        "family": "Relationship",
        "description": "2D density contours for overlap and clusters.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _field("z", "Value"), _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["facet_row"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("density", "Density", [
            _control("nbinsx", "X bins", "number", default=0),
            _control("nbinsy", "Y bins", "number", default=0),
            _control("histfunc", "Cell function", "select", default="", choices=[("", "Count"), ("sum", "Sum"), ("avg", "Average"), ("min", "Min"), ("max", "Max")]),
            _control("histnorm2d", "Normalize", "select", default="", choices=[("", "None"), ("probability", "Probability"), ("density", "Density"), ("probability density", "Probability density")]),
            _control("marginal_x", "X marginal", "select", default="", choices=[("", "None"), ("histogram", "Histogram"), ("rug", "Rug"), ("box", "Box"), ("violin", "Violin")]),
            _control("marginal_y", "Y marginal", "select", default="", choices=[("", "None"), ("histogram", "Histogram"), ("rug", "Rug"), ("box", "Box"), ("violin", "Violin")]),
        ]), *_COMMON_GROUPS],
    },
    {
        "id": "line",
        "title": "Line",
        "family": "Time and sequence",
        "description": "Trend over time, sequence, or ordered values.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["weight"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["facet_row"], _ENCODING_FIELDS["text"], _ENCODING_FIELDS["error_x"], _ENCODING_FIELDS["error_y"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [
            _control("markers", "Markers", "checkbox", default=False),
            _control("line_shape", "Line shape", "select", default="linear", choices=[
                ("linear", "Linear"),
                ("spline", "Spline"),
                ("hv", "Step after"),
                ("vh", "Step before"),
                ("hvh", "Step middle"),
            ]),
        ]), *_COMMON_GROUPS],
    },
    {
        "id": "area",
        "title": "Area",
        "family": "Time and sequence",
        "description": "Filled trend or stacked quantity over an ordered axis.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["weight"], _ENCODING_FIELDS["facet"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "bar",
        "title": "Bar",
        "family": "Comparison",
        "description": "Counts or aggregated values by category.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["y"], _ENCODING_FIELDS["color"], _ENCODING_FIELDS["weight"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["facet_row"], _ENCODING_FIELDS["text"], _ENCODING_FIELDS["error_x"], _ENCODING_FIELDS["error_y"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("marks", "Marks", [_control("barmode", "Bar mode", "select", default="group", choices=[("group", "Group"), ("stack", "Stack"), ("relative", "Relative")]), _control("orientation", "Orientation", "select", default="v", choices=[("v", "Vertical"), ("h", "Horizontal")])]), *_COMMON_GROUPS],
    },
    {
        "id": "lollipop",
        "title": "Lollipop",
        "family": "Comparison",
        "description": "A compact bar alternative that emphasizes ranked category values with stems and markers.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["weight"]],
        "option_groups": [_group("marks", "Marks", [_control("lollipop_baseline", "Baseline", "number", default=0), _control("marker_size", "Marker size", "number", default=10)]), *_COMMON_GROUPS],
    },
    {
        "id": "slope",
        "title": "Slope Chart",
        "family": "Comparison",
        "description": "Before/after or period-to-period change for categories, segments, or entities.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, _ENCODING_FIELDS["color"], _ENCODING_FIELDS["facet"], _ENCODING_FIELDS["text"]],
        "option_groups": [_group("marks", "Marks", [_control("line_shape", "Line shape", "select", default="linear", choices=[("linear", "Linear"), ("spline", "Spline")])]), *_COMMON_GROUPS],
    },
    {
        "id": "bump_chart",
        "title": "Bump Chart",
        "family": "Comparison",
        "description": "Rank movement across time or ordered categories.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}, {**_ENCODING_FIELDS["color"], "required": True}, _ENCODING_FIELDS["weight"]],
        "option_groups": [_group("rank", "Rank", [_control("rank_order", "Rank order", "select", default="high_first", choices=[("high_first", "High value ranks first"), ("low_first", "Low value ranks first")])]), *_COMMON_GROUPS],
    },
    {
        "id": "pareto",
        "title": "Pareto",
        "family": "Comparison",
        "description": "Sorted bars with cumulative contribution line for 80/20 concentration checks.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["y"], _ENCODING_FIELDS["color"]],
        "option_groups": [_group("pareto", "Pareto", [_control("pareto_threshold", "Threshold %", "number", default=80)]), *_COMMON_GROUPS],
    },
    {
        "id": "waterfall",
        "title": "Waterfall",
        "family": "Comparison",
        "description": "Stepwise positive and negative contributions to a running total.",
        "fields": [_ENCODING_FIELDS["x"], {**_ENCODING_FIELDS["y"], "required": True}],
        "option_groups": [_group("waterfall", "Waterfall", [_control("waterfall_total", "Show total", "checkbox", default=True), _control("waterfall_total_label", "Total label", "text", default="Total")]), *_COMMON_GROUPS],
    },
    {
        "id": "funnel",
        "title": "Funnel",
        "family": "Process",
        "description": "Stage-by-stage counts or values for drop-off and conversion paths.",
        "fields": [_ENCODING_FIELDS["x"], _ENCODING_FIELDS["y"], _ENCODING_FIELDS["color"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "radar",
        "title": "Radar",
        "family": "Multivariate",
        "description": "Radial profile across comparable measures or categories.",
        "fields": [_field("theta", "Angle", required=True), _field("r", "Radius", required=True), _ENCODING_FIELDS["color"]],
        "option_groups": [_group("radar", "Radar", [_control("radar_fill", "Fill area", "checkbox", default=True)]), *_COMMON_GROUPS],
    },
    {
        "id": "concentration_curve",
        "title": "Concentration Curve",
        "family": "Concentration",
        "description": "Cumulative share of value across sorted rows, useful for Lorenz, 80/20, and concentration analysis.",
        "fields": [_field("values", "Values", required=True), _field("group", "Group")],
        "option_groups": [_group("concentration", "Concentration", [
            _control("concentration_sort", "Sort", "select", default="descending", choices=[("descending", "Largest first"), ("ascending", "Smallest first")]),
            _control("show_equality_line", "Equality line", "checkbox", default=True),
        ]), *_COMMON_GROUPS],
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
        "id": "correlation_heatmap",
        "title": "Correlation Heatmap",
        "family": "Matrix",
        "description": "Numeric correlation matrix with method, absolute-value, triangle, and annotation controls.",
        "fields": [_field("dimensions", "Dimensions", multiple=True)],
        "option_groups": [_group("correlation", "Correlation", [
            _control("corr_method", "Method", "select", default="pearson", choices=[("pearson", "Pearson"), ("spearman", "Spearman"), ("kendall", "Kendall")]),
            _control("corr_abs", "Absolute values", "checkbox", default=False),
            _control("corr_triangle", "Lower triangle only", "checkbox", default=False),
            _control("corr_text", "Show values", "checkbox", default=True),
        ]), *_COMMON_GROUPS],
    },
    {
        "id": "pca_scatter",
        "title": "PCA Scatter",
        "family": "Multivariate",
        "description": "Project many numeric columns into two principal components for multivariate clustering and separation checks.",
        "fields": [_field("dimensions", "Dimensions", multiple=True), _ENCODING_FIELDS["color"]],
        "option_groups": [_group("pca", "PCA", [_control("pca_scale", "Scale columns", "checkbox", default=True)]), *_COMMON_GROUPS],
    },
    {
        "id": "qq_plot",
        "title": "Q-Q Plot",
        "family": "Diagnostics",
        "description": "Sample quantiles against theoretical normal quantiles for distribution diagnostics.",
        "fields": [_field("values", "Values", required=True)],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "autocorrelation",
        "title": "Autocorrelation",
        "family": "Time and sequence",
        "description": "Correlation of a series with lagged versions of itself.",
        "fields": [{**_ENCODING_FIELDS["y"], "required": True}],
        "option_groups": [_group("lags", "Lags", [_control("max_lag", "Max lag", "number", default=30)]), *_COMMON_GROUPS],
    },
    {
        "id": "calendar_heatmap",
        "title": "Calendar Heatmap",
        "family": "Time and sequence",
        "description": "Day-level intensity across weeks and weekdays for activity, volume, or value.",
        "fields": [_field("date", "Date", required=True, semantic=["datetime"]), _field("values", "Values")],
        "option_groups": [_group("calendar", "Calendar", [_control("calendar_aggregation", "Daily aggregation", "select", default="sum", choices=[("sum", "Sum"), ("mean", "Mean"), ("median", "Median"), ("min", "Min"), ("max", "Max")]), _control("calendar_year", "Year filter", "number", default=0)]), *_COMMON_GROUPS],
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
        "id": "sunburst",
        "title": "Sunburst",
        "family": "Composition",
        "description": "Radial hierarchy and share of total by nested categories.",
        "fields": [_field("path", "Path columns", required=True, multiple=True), _field("values", "Values"), _ENCODING_FIELDS["color"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "geo_scatter",
        "title": "Geo Scatter",
        "family": "Geographic",
        "description": "Latitude/longitude points with color, size, labels, and hover fields.",
        "fields": [_ENCODING_FIELDS["lat"], _ENCODING_FIELDS["lon"], _ENCODING_FIELDS["color"], _ENCODING_FIELDS["size"], _ENCODING_FIELDS["text"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("map", "Map", [
            _control("scope", "Scope", "select", default="", choices=[("", "World"), ("usa", "USA"), ("north america", "North America"), ("europe", "Europe"), ("asia", "Asia"), ("africa", "Africa"), ("south america", "South America")]),
            _control("projection", "Projection", "select", default="natural earth", choices=[("natural earth", "Natural earth"), ("equirectangular", "Equirectangular"), ("orthographic", "Orthographic"), ("mercator", "Mercator"), ("albers usa", "Albers USA")]),
        ]), *_COMMON_GROUPS],
    },
    {
        "id": "choropleth",
        "title": "Choropleth",
        "family": "Geographic",
        "description": "Region-based color map for state, country, or location codes.",
        "fields": [_ENCODING_FIELDS["locations"], _field("values", "Values", required=True), _ENCODING_FIELDS["text"], _ENCODING_FIELDS["hover"]],
        "option_groups": [_group("map", "Map", [
            _control("scope", "Scope", "select", default="usa", choices=[("usa", "USA"), ("world", "World"), ("north america", "North America"), ("europe", "Europe"), ("asia", "Asia"), ("africa", "Africa"), ("south america", "South America")]),
            _control("locationmode", "Location mode", "select", default="USA-states", choices=[("USA-states", "USA states"), ("country names", "Country names"), ("ISO-3", "ISO-3")]),
        ]), *_COMMON_GROUPS],
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
        "id": "parallel_coordinates",
        "title": "Parallel Coordinates",
        "family": "Multivariate",
        "description": "Numeric multivariate profile across several columns.",
        "fields": [_field("dimensions", "Dimensions", multiple=True), _ENCODING_FIELDS["color"]],
        "option_groups": _COMMON_GROUPS,
    },
    {
        "id": "parallel_categories",
        "title": "Parallel Categories",
        "family": "Multivariate",
        "description": "Categorical path flow across several columns.",
        "fields": [_field("dimensions", "Dimensions", multiple=True)],
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
    "VisualRecommendation",
    "VisualSpec",
    "build_visual_artifact",
    "normalize_visual_spec",
    "render_visual",
    "validate_visual_spec",
    "visual_catalog",
    "visual_recommendations",
]
