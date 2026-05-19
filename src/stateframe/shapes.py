"""Dataset shape inference."""

from __future__ import annotations

import pandas as pd

from stateframe.models import ColumnProfile, ShapeHypothesis


def infer_shapes(
    df: pd.DataFrame,
    columns: dict[str, ColumnProfile],
    *,
    target: str | None = None,
    time: str | None = None,
) -> list[ShapeHypothesis]:
    row_count = int(df.shape[0])
    column_count = int(df.shape[1])
    semantic_counts: dict[str, int] = {}
    for column in columns.values():
        semantic_counts[column.semantic_type] = semantic_counts.get(column.semantic_type, 0) + 1

    datetime_columns = [
        column.name
        for column in columns.values()
        if column.semantic_type in {"datetime", "datetime-like"}
    ]
    numeric_columns = [
        column.name
        for column in columns.values()
        if column.semantic_type in {"numeric", "amount", "numeric-like", "percentage", "proportion"}
    ]
    id_columns = [
        column.name
        for column in columns.values()
        if column.semantic_type == "identifier"
    ]
    text_columns = [column.name for column in columns.values() if column.semantic_type == "text"]
    geo_columns = [
        column.name
        for column in columns.values()
        if column.semantic_type in {"geographic", "postal_code"}
        or column.name.lower() in {"lat", "latitude", "lon", "lng", "longitude"}
    ]
    nested_columns = [
        column.name for column in columns.values() if column.semantic_type == "json-like"
    ]
    amount_columns = [
        column.name for column in columns.values() if column.semantic_type == "amount"
    ]

    shapes: list[ShapeHypothesis] = [
        ShapeHypothesis(
            id="dataframe",
            confidence=1.0,
            evidence=[f"{row_count} rows x {column_count} columns"],
            recommended_lenses=["quality.missingness", "grain.keys"],
        )
    ]

    if datetime_columns and numeric_columns:
        shapes.append(
            ShapeHypothesis(
                id="time_series",
                confidence=0.72 if len(datetime_columns) == 1 else 0.62,
                evidence=[
                    f"datetime columns: {', '.join(datetime_columns[:3])}",
                    f"numeric measure columns: {', '.join(numeric_columns[:3])}",
                ],
                recommended_lenses=["time.cadence", "time.gaps", "time.seasonality"],
            )
        )

    if datetime_columns and id_columns:
        shapes.append(
            ShapeHypothesis(
                id="event_log",
                confidence=0.82,
                evidence=[
                    f"timestamp-like columns: {', '.join(datetime_columns[:3])}",
                    f"identifier-like columns: {', '.join(id_columns[:3])}",
                ],
                recommended_lenses=["grain.keys", "time.cadence", "entity.activity"],
            )
        )

    if datetime_columns and amount_columns:
        shapes.append(
            ShapeHypothesis(
                id="transaction_table",
                confidence=0.72,
                evidence=[
                    f"time columns: {', '.join(datetime_columns[:3])}",
                    f"amount-like columns: {', '.join(amount_columns[:3])}",
                ],
                recommended_lenses=[
                    "concentration.lorenz",
                    "distribution.numeric",
                    "grain.keys",
                ],
            )
        )

    if target and target in columns:
        shapes.append(
            ShapeHypothesis(
                id="targeted_modeling_table",
                confidence=0.85,
                evidence=[f"target column provided: {target}"],
                recommended_lenses=[
                    "target.balance",
                    "target.leakage",
                    "relationships.correlation",
                ],
            )
        )

    if column_count >= 10 and len(numeric_columns) / max(column_count, 1) >= 0.5:
        shapes.append(
            ShapeHypothesis(
                id="feature_matrix",
                confidence=0.72,
                evidence=[
                    f"{len(numeric_columns)} of {column_count} columns are numeric-like measures"
                ],
                recommended_lenses=[
                    "features.readiness",
                    "relationships.correlation",
                    "quality.sparsity",
                ],
            )
        )

    if column_count > max(row_count, 1) or (
        column_count >= 20 and any(column.missing_ratio > 0.5 for column in columns.values())
    ):
        shapes.append(
            ShapeHypothesis(
                id="wide_sparse_matrix",
                confidence=0.68,
                evidence=["wide shape or high missingness across many columns"],
                recommended_lenses=["quality.sparsity", "missingness.blocks"],
            )
        )

    if text_columns:
        shapes.append(
            ShapeHypothesis(
                id="text_corpus",
                confidence=0.65,
                evidence=[f"text-heavy columns: {', '.join(text_columns[:3])}"],
                recommended_lenses=["text.lengths", "text.near_duplicates"],
            )
        )

    if geo_columns:
        shapes.append(
            ShapeHypothesis(
                id="geospatial_points",
                confidence=0.66,
                evidence=[f"geographic columns: {', '.join(geo_columns[:5])}"],
                recommended_lenses=["geo.coordinate_validity", "geo.bounds"],
            )
        )

    if nested_columns:
        shapes.append(
            ShapeHypothesis(
                id="nested_records",
                confidence=0.7,
                evidence=[f"json-like columns: {', '.join(nested_columns[:3])}"],
                recommended_lenses=["nested.schema_paths", "nested.array_lengths"],
            )
        )

    return shapes
