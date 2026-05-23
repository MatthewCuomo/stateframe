import pandas as pd
import pytest

import stateframe as sf


def test_visualizer_supports_date_buckets_data_ranges_and_sorting():
    df = pd.DataFrame(
        {
            "order_date": pd.date_range("2025-01-01", periods=90, freq="D"),
            "amount": range(90),
        }
    )

    figure = sf.visualize(
        df,
        {
            "kind": "line",
            "fields": {"x": "order_date", "y": "amount"},
            "options": {
                "aggregation": "sum",
                "date_bucket": "month",
                "x_data_min": "2025-02-01",
                "sort_x": "descending",
            },
        },
    )

    x_values = list(figure.data[0].x)
    assert len(x_values) == 2
    assert pd.Timestamp(x_values[0]) > pd.Timestamp(x_values[-1])
    assert pd.Timestamp(x_values[-1]) == pd.Timestamp("2025-02-01")


def test_visualizer_supports_value_filters_and_axis_transforms():
    df = pd.DataFrame({"x": [1, 10, 100, 1000], "y": [2, 4, 8, 16]})

    figure = sf.visualize(
        df,
        {
            "kind": "scatter",
            "fields": {"x": "x", "y": "y"},
            "options": {"x_data_min": "10", "x_transform": "log"},
        },
    )

    assert len(figure.data[0].x) == 3


def test_visualizer_supports_histogram_quantile_bins_and_grouped_other():
    histogram = sf.visualize(
        pd.DataFrame({"price": range(100)}),
        {
            "kind": "histogram",
            "fields": {"x": "price"},
            "options": {"bin_method": "quantile", "quantile_bins": 4},
        },
    )
    assert len(set(histogram.data[0].x)) == 4

    pie = sf.visualize(
        pd.DataFrame({"county": list("AAAAABBBBCCCDDE")}),
        {
            "kind": "pie",
            "fields": {"names": "county"},
            "options": {"top_n": 2, "top_n_mode": "other"},
        },
    )
    assert set(pie.data[0].labels) == {"A", "B", "Other"}
    assert list(pie.data[0].values) == [5, 4, 6]


def test_visualizer_supports_binning_numeric_x_for_distribution_comparison():
    df = pd.DataFrame({"age": range(20, 60), "price": [value * 1000 for value in range(40)]})

    figure = sf.visualize(
        df,
        {
            "kind": "box",
            "fields": {"x": "age", "y": "price"},
            "options": {"x_bin_method": "quantile", "x_bin_count": 4},
        },
    )

    assert len(set(figure.data[0].x)) == 4


def test_visualizer_supports_rolling_and_cumulative_line_values():
    df = pd.DataFrame({"day": [1, 2, 3, 4, 5], "amount": [1, 2, 3, 4, 5]})

    rolling = sf.visualize(
        df,
        {
            "kind": "line",
            "fields": {"x": "day", "y": "amount"},
            "options": {"rolling_window": 3, "rolling_stat": "mean"},
        },
    )
    assert list(rolling.data[0].y) == [1, 1.5, 2, 3, 4]

    cumulative = sf.visualize(
        df,
        {
            "kind": "line",
            "fields": {"x": "day", "y": "amount"},
            "options": {"cumulative": True},
        },
    )
    assert list(cumulative.data[0].y) == [1, 3, 6, 10, 15]


def test_visualizer_supports_share_transforms_and_value_sorting():
    df = pd.DataFrame({"segment": ["A", "A", "B", "C"], "amount": [10, 30, 40, 20]})

    figure = sf.visualize(
        df,
        {
            "kind": "bar",
            "fields": {"x": "segment", "y": "amount"},
            "options": {"aggregation": "sum", "value_transform": "percent_total", "sort_by": "y_descending"},
        },
    )

    assert list(figure.data[0].x) == ["A", "B", "C"]
    assert sum(figure.data[0].y) == 100
    assert list(figure.data[0].y) == [40, 40, 20]


def test_visualizer_supports_percent_within_color_group():
    df = pd.DataFrame(
        {
            "segment": ["A", "B", "A", "B"],
            "region": ["East", "East", "West", "West"],
            "amount": [25, 75, 40, 60],
        }
    )

    figure = sf.visualize(
        df,
        {
            "kind": "bar",
            "fields": {"x": "segment", "y": "amount", "color": "region"},
            "options": {"aggregation": "sum", "value_transform": "percent_group"},
        },
    )

    for trace in figure.data:
        assert sum(trace.y) == 100


def test_visualizer_supports_missing_category_labels_sampling_and_deduping():
    df = pd.DataFrame({"county": ["A", "A", None, "", "B", "B", "B"]})

    figure = sf.visualize(
        df,
        {
            "kind": "pie",
            "fields": {"names": "county"},
            "options": {
                "include_missing_category": True,
                "missing_category_label": "No county",
                "dedupe_rows": True,
                "sort_by": "y_descending",
            },
        },
    )

    assert set(figure.data[0].labels) == {"A", "B", "No county"}
    assert list(figure.data[0].values) == [1, 1, 1]


def test_visualizer_supports_axis_reversal_reference_lines_and_bands():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [5, 10, 15]})

    figure = sf.visualize(
        df,
        {
            "kind": "scatter",
            "fields": {"x": "x", "y": "y"},
            "options": {
                "reverse_y": True,
                "y_reference": 10,
                "x_reference": 2,
                "y_band_min": 7,
                "y_band_max": 13,
                "y_stat_reference": "mean",
            },
        },
    )

    assert figure.layout.yaxis.autorange == "reversed"
    assert len(figure.layout.shapes) >= 4


def test_visual_catalog_surfaces_broad_control_groups():
    catalog = sf.visual_catalog()
    bar = next(item for item in catalog["plot_types"] if item["id"] == "bar")
    control_ids = {
        control["id"]
        for group in bar["option_groups"]
        for control in group["controls"]
    }
    aggregation = next(
        control
        for group in bar["option_groups"]
        for control in group["controls"]
        if control["id"] == "aggregation"
    )
    aggregation_choices = {choice["value"] for choice in aggregation["choices"]}

    assert {"value_transform", "sort_by", "y_reference", "reverse_y", "color_sequence", "show_value_labels", "x_rangeslider"} <= control_ids
    assert {"weighted_mean", "p90", "p95"} <= aggregation_choices


def test_visualizer_supports_weighted_and_percentile_aggregations():
    df = pd.DataFrame(
        {
            "segment": ["A", "A", "B", "B"],
            "price": [10, 20, 100, 200],
            "weight": [1, 3, 1, 1],
        }
    )

    weighted = sf.visualize(
        df,
        {
            "kind": "bar",
            "fields": {"x": "segment", "y": "price", "weight": "weight"},
            "options": {"aggregation": "weighted_mean", "sort_by": "x_ascending"},
        },
    )
    assert list(weighted.data[0].y) == [17.5, 150.0]

    percentile = sf.visualize(
        df,
        {
            "kind": "bar",
            "fields": {"x": "segment", "y": "price"},
            "options": {"aggregation": "p90", "sort_by": "x_ascending"},
        },
    )
    assert list(percentile.data[0].y) == [19.0, 190.0]


def test_visualizer_supports_labels_range_slider_and_facet_axis_controls():
    df = pd.DataFrame(
        {
            "day": pd.date_range("2025-01-01", periods=4),
            "amount": [10, 20, 30, 40],
            "region": ["East", "East", "West", "West"],
        }
    )

    figure = sf.visualize(
        df,
        {
            "kind": "bar",
            "fields": {"x": "day", "y": "amount", "facet": "region"},
            "options": {
                "aggregation": "sum",
                "show_value_labels": True,
                "label_template": "%{y:.0f}",
                "x_rangeslider": True,
                "facet_col_wrap": 1,
                "facet_shared_y": False,
            },
        },
    )

    assert figure.data[0].texttemplate == "%{y:.0f}"
    assert figure.layout.xaxis.rangeslider.visible is True
    assert figure.layout.yaxis.matches is None


def test_visualizer_supports_density_strip_and_hierarchy_families():
    df = pd.DataFrame(
        {
            "segment": ["A", "A", "B", "B", "C"],
            "region": ["East", "West", "East", "West", "East"],
            "x": [1, 2, 3, 4, 5],
            "y": [2, 3, 3, 5, 8],
            "amount": [10, 20, 30, 40, 50],
        }
    )

    strip = sf.visualize(df, {"kind": "strip", "fields": {"x": "segment", "y": "amount", "color": "region"}})
    assert strip.data

    heatmap = sf.visualize(
        df,
        {
            "kind": "density_heatmap",
            "fields": {"x": "x", "y": "y"},
            "options": {"nbinsx": 3, "nbinsy": 3},
        },
    )
    assert heatmap.data[0].type == "histogram2d"

    contour = sf.visualize(
        df,
        {
            "kind": "density_contour",
            "fields": {"x": "x", "y": "y"},
            "options": {"nbinsx": 3, "nbinsy": 3},
        },
    )
    assert contour.data[0].type == "histogram2dcontour"

    sunburst = sf.visualize(
        df,
        {"kind": "sunburst", "fields": {"path": ["region", "segment"], "values": "amount"}},
    )
    assert sunburst.data[0].type == "sunburst"


def test_visualizer_supports_geo_and_multivariate_families():
    geo = pd.DataFrame(
        {
            "city": ["New York", "Chicago", "Los Angeles"],
            "lat": [40.7128, 41.8781, 34.0522],
            "lon": [-74.006, -87.6298, -118.2437],
            "amount": [100, 80, 90],
            "region": ["East", "Midwest", "West"],
        }
    )
    geo_fig = sf.visualize(
        geo,
        {
            "kind": "geo_scatter",
            "fields": {"lat": "lat", "lon": "lon", "size": "amount", "color": "region", "text": "city"},
            "options": {"scope": "usa", "projection": "albers usa"},
        },
    )
    assert geo_fig.data[0].type == "scattergeo"
    assert sorted(float(value) for trace in geo_fig.data for value in trace.lat) == [34.0522, 40.7128, 41.8781]

    states = pd.DataFrame({"state": ["NY", "IL", "CA"], "amount": [100, 80, 90]})
    choropleth = sf.visualize(
        states,
        {
            "kind": "choropleth",
            "fields": {"locations": "state", "values": "amount"},
        },
    )
    assert choropleth.data[0].type == "choropleth"

    multivariate = pd.DataFrame(
        {
            "price": [100, 200, 300],
            "sqft": [900, 1200, 1600],
            "beds": [2, 3, 4],
            "county": ["A", "B", "A"],
            "status": ["new", "sold", "new"],
        }
    )
    parallel = sf.visualize(
        multivariate,
        {"kind": "parallel_coordinates", "fields": {"dimensions": ["price", "sqft", "beds"]}},
    )
    assert parallel.data[0].type == "parcoords"

    categories = sf.visualize(
        multivariate,
        {"kind": "parallel_categories", "fields": {"dimensions": ["county", "status"]}},
    )
    assert categories.data[0].type == "parcats"


def test_visual_catalog_surfaces_new_visual_families_and_bindings():
    catalog = sf.visual_catalog()
    kinds = {item["id"] for item in catalog["plot_types"]}

    assert {
        "strip",
        "density_heatmap",
        "density_contour",
        "sunburst",
        "geo_scatter",
        "choropleth",
        "parallel_coordinates",
        "parallel_categories",
        "concentration_curve",
        "pareto",
        "lollipop",
        "slope",
        "bump_chart",
        "waterfall",
        "funnel",
        "radar",
        "qq_plot",
        "autocorrelation",
        "calendar_heatmap",
        "correlation_heatmap",
        "pca_scatter",
    } <= kinds
    geo = next(item for item in catalog["plot_types"] if item["id"] == "geo_scatter")
    assert {"lat", "lon", "size", "text"} <= {field["slot"] for field in geo["fields"]}
    bar = next(item for item in catalog["plot_types"] if item["id"] == "bar")
    aggregation = next(control for group in bar["option_groups"] for control in group["controls"] if control["id"] == "aggregation")
    custom = next(control for group in bar["option_groups"] for control in group["controls"] if control["id"] == "custom_kwargs")
    assert aggregation["level"] == "basic"
    assert custom["level"] == "expert"


def test_visualizer_supports_concentration_pareto_and_process_charts():
    df = pd.DataFrame(
        {
            "segment": ["A", "B", "C", "D"],
            "amount": [50, 30, 15, 5],
            "change": [100, -25, 40, -10],
        }
    )

    concentration = sf.visualize(
        df,
        {"kind": "concentration_curve", "fields": {"values": "amount"}},
    )
    assert len(concentration.data) >= 2
    assert list(concentration.data[0].y)[-1] == 1

    pareto = sf.visualize(
        df,
        {"kind": "pareto", "fields": {"x": "segment", "y": "amount"}, "options": {"aggregation": "sum"}},
    )
    assert pareto.data[0].type == "bar"
    assert pareto.data[1].type == "scatter"

    waterfall = sf.visualize(
        df,
        {"kind": "waterfall", "fields": {"x": "segment", "y": "change"}, "options": {"waterfall_total": True}},
    )
    assert waterfall.data[0].type == "waterfall"

    funnel = sf.visualize(
        df,
        {"kind": "funnel", "fields": {"x": "segment", "y": "amount"}},
    )
    assert funnel.data[0].type == "funnel"


def test_visualizer_supports_radar_qq_and_autocorrelation():
    df = pd.DataFrame({"metric": ["speed", "quality", "cost"], "score": [8, 6, 4], "series": [1, 2, 3]})

    radar = sf.visualize(df, {"kind": "radar", "fields": {"theta": "metric", "r": "score"}})
    assert radar.data[0].type == "scatterpolar"

    qq = sf.visualize(df, {"kind": "qq_plot", "fields": {"values": "score"}})
    assert qq.data[0].type == "scatter"

    acf = sf.visualize(pd.DataFrame({"series": range(20)}), {"kind": "autocorrelation", "fields": {"y": "series"}, "options": {"max_lag": 5}})
    assert acf.data[0].type == "bar"
    assert len(acf.data[0].x) == 5


def test_visualizer_supports_lollipop_slope_bump_and_calendar_heatmap():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=28),
            "period": ["Before"] * 14 + ["After"] * 14,
            "segment": ["A", "B", "C", "D"] * 7,
            "amount": [10, 15, 8, 12, 11, 17, 7, 15, 14, 12, 18, 10, 20, 13] * 2,
        }
    )

    lollipop = sf.visualize(df, {"kind": "lollipop", "fields": {"x": "segment", "y": "amount"}, "options": {"aggregation": "sum"}})
    assert len(lollipop.data) >= 2

    slope = sf.visualize(df, {"kind": "slope", "fields": {"x": "period", "y": "amount", "color": "segment"}, "options": {"aggregation": "sum"}})
    assert slope.data

    bump = sf.visualize(df, {"kind": "bump_chart", "fields": {"x": "period", "y": "amount", "color": "segment"}, "options": {"aggregation": "sum"}})
    assert bump.layout.yaxis.autorange == "reversed"

    calendar = sf.visualize(df, {"kind": "calendar_heatmap", "fields": {"date": "date", "values": "amount"}, "options": {"calendar_aggregation": "sum"}})
    assert calendar.data[0].type == "heatmap"


def test_visualizer_supports_correlation_heatmap_and_pca_scatter():
    df = pd.DataFrame(
        {
            "x1": [1, 2, 3, 4, 5, 6],
            "x2": [2, 4, 6, 8, 10, 12],
            "x3": [6, 5, 4, 3, 2, 1],
            "group": ["A", "A", "B", "B", "C", "C"],
        }
    )

    corr = sf.visualize(
        df,
        {
            "kind": "correlation_heatmap",
            "fields": {"dimensions": ["x1", "x2", "x3"]},
            "options": {"corr_method": "pearson", "corr_text": True},
        },
    )
    assert corr.data[0].type == "heatmap"

    pca = sf.visualize(
        df,
        {
            "kind": "pca_scatter",
            "fields": {"dimensions": ["x1", "x2", "x3"], "color": "group"},
        },
    )
    assert pca.data[0].type == "scatter"


def test_visualizer_suggests_replayable_specs_from_profile():
    df = pd.DataFrame(
        {
            "sold_date": pd.date_range("2025-01-01", periods=120, freq="D"),
            "price": [200_000 + value * 1_000 for value in range(120)],
            "sqft": [900 + value * 5 for value in range(120)],
            "county": ["A", "B", "C", "A"] * 30,
            "latitude": [40.0, 41.0, 42.0, 43.0] * 30,
            "longitude": [-74.0, -75.0, -76.0, -77.0] * 30,
            "notes": [None if value % 10 == 0 else "ok" for value in range(120)],
        }
    )
    scan = sf.scan(df, time="sold_date")

    suggestions = scan.visual_recommendations(limit=20)
    kinds = {item.spec.kind for item in suggestions}
    specs = [item.to_dict()["spec"] for item in suggestions]

    assert {"missingness", "line", "bar", "scatter", "geo_scatter"} <= kinds
    assert all(spec["kind"] and isinstance(spec["fields"], dict) for spec in specs)
    assert suggestions == sorted(suggestions, key=lambda item: item.score, reverse=True)


def test_visualizer_rejects_missing_required_geo_bindings():
    df = pd.DataFrame({"latitude": [26.1, 26.2], "price": [1, 2]})

    with pytest.raises(ValueError, match="Longitude is required"):
        sf.visualize(df, {"kind": "geo_scatter", "fields": {"lat": "latitude"}})


def test_visualizer_geo_suggestions_bind_coordinates_and_sample_large_data():
    rows = 6_000
    df = pd.DataFrame(
        {
            "geo_lat": [26.0 + (value % 100) * 0.001 for value in range(rows)],
            "geo_lon": [-80.0 - (value % 100) * 0.001 for value in range(rows)],
            "county": ["A", "B", "C"] * (rows // 3),
            "sold_price": [250_000 + value for value in range(rows)],
        }
    )
    scan = sf.scan(df)

    geo = next(item for item in scan.visual_recommendations(limit=10) if item.spec.kind == "geo_scatter")

    assert geo.spec.fields["lat"] == "geo_lat"
    assert geo.spec.fields["lon"] == "geo_lon"
    assert geo.spec.options["sample_rows"] == 5_000

    figure = sf.visualize(scan, geo.spec.to_dict())
    rendered_points = sum(len(getattr(trace, "lat", [])) for trace in figure.data)
    assert rendered_points <= 5_000


def test_suggest_visuals_public_api_accepts_dataframe():
    df = pd.DataFrame({"category": ["a", "b", "a"], "amount": [1, 2, 3]})

    suggestions = sf.suggest_visuals(df, limit=4)

    assert suggestions
    assert suggestions[0].spec.kind in {item["id"] for item in sf.visual_catalog()["plot_types"]}
