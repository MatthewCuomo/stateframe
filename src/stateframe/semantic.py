"""Semantic type inference for early dataframe profiling."""

from __future__ import annotations

import pandas as pd
from pandas.api import types as pdt

from stateframe.binary import detect_binary_profile
from stateframe.models import SemanticTypeHypothesis
from stateframe.utils import (
    EMAIL_RE,
    URL_RE,
    is_amount_name,
    is_geo_name,
    is_identifier_name,
    is_outcome_name,
    is_percentage_name,
    is_postal_name,
    is_time_name,
    parse_success_ratio,
)


def infer_semantic_type(name: str, series: pd.Series, *, semantic_policy: str = "auto") -> str:
    hypotheses = infer_semantic_hypotheses(name, series, semantic_policy=semantic_policy)
    if not hypotheses:
        return "unknown"
    return hypotheses[0].semantic_type


def infer_semantic_hypotheses(
    name: str,
    series: pd.Series,
    *,
    semantic_policy: str = "auto",
) -> list[SemanticTypeHypothesis]:
    """Return ranked semantic type hypotheses with evidence.

    These are intentionally heuristic and evidence-based rather than one hard
    dtype mapping. The primary hypothesis is still exposed as
    ``ColumnProfile.semantic_type`` for simple downstream routing.
    """

    non_null = series.dropna()
    non_null_count = int(non_null.shape[0])
    row_count = int(series.shape[0])
    distinct_count = _safe_nunique(non_null)
    distinct_ratio = distinct_count / non_null_count if non_null_count else 0.0
    missing_ratio = 1 - non_null_count / row_count if row_count else 0.0
    hypotheses: list[SemanticTypeHypothesis] = []

    if non_null_count == 0:
        return [
            SemanticTypeHypothesis(
                "unknown",
                0.3,
                ["all values are missing"],
            )
        ]

    if distinct_count <= 1:
        hypotheses.append(
            SemanticTypeHypothesis(
                "constant",
                1.0,
                ["one or fewer distinct non-missing values"],
            )
        )

    if missing_ratio >= 0.95:
        hypotheses.append(
            SemanticTypeHypothesis(
                "mostly_missing",
                0.95,
                [f"missing ratio is {missing_ratio:.3f}"],
            )
        )

    binary_profile = detect_binary_profile(name, series)
    if binary_profile is not None:
        semantic = "nullable_binary" if binary_profile.kind != "clean_binary" else "binary"
        hypotheses.append(
            SemanticTypeHypothesis(
                semantic,
                binary_profile.confidence,
                binary_profile.evidence,
            )
        )

    if pdt.is_datetime64_any_dtype(series):
        hypotheses.append(
            SemanticTypeHypothesis("datetime", 0.99, ["pandas dtype is datetime-like"])
        )

    if pdt.is_bool_dtype(series):
        hypotheses.append(
            SemanticTypeHypothesis("boolean", 0.99, ["pandas dtype is boolean"])
        )

    if pdt.is_numeric_dtype(series):
        hypotheses.extend(
            _numeric_hypotheses(
                name,
                series,
                non_null,
                distinct_ratio,
                semantic_policy=semantic_policy,
            )
        )
    elif isinstance(series.dtype, pd.CategoricalDtype):
        hypotheses.append(
            SemanticTypeHypothesis("category", 0.94, ["pandas dtype is categorical"])
        )
    else:
        hypotheses.extend(
            _string_hypotheses(
                name,
                series,
                non_null,
                non_null_count,
                distinct_count,
                distinct_ratio,
                semantic_policy=semantic_policy,
            )
        )

    if semantic_policy != "off" and is_outcome_name(name):
        hypotheses.append(
            SemanticTypeHypothesis(
                "possible_target",
                0.66 if semantic_policy == "auto" else 0.44,
                ["column name resembles an outcome or label"],
            )
        )

    if not hypotheses:
        hypotheses.append(SemanticTypeHypothesis("unknown", 0.2, ["no rule matched"]))

    return _dedupe_hypotheses(hypotheses)


def _numeric_hypotheses(
    name: str,
    series: pd.Series,
    non_null: pd.Series,
    distinct_ratio: float,
    *,
    semantic_policy: str,
) -> list[SemanticTypeHypothesis]:
    hypotheses: list[SemanticTypeHypothesis] = []
    distinct_count = _safe_nunique(non_null)

    if semantic_policy != "off" and is_identifier_name(name) and distinct_ratio > 0.75:
        hypotheses.append(
            SemanticTypeHypothesis(
                "identifier",
                (0.94 if distinct_ratio > 0.95 else 0.82)
                if semantic_policy == "auto"
                else (0.82 if distinct_ratio > 0.95 else 0.62),
                ["name looks identifier-like", f"distinct ratio is {distinct_ratio:.3f}"],
            )
        )
    elif distinct_ratio > 0.995 and distinct_count >= 20:
        hypotheses.append(
            SemanticTypeHypothesis(
                "identifier",
                0.74,
                ["nearly every non-missing value is unique"],
            )
        )

    if semantic_policy != "off" and is_amount_name(name):
        hypotheses.append(
            SemanticTypeHypothesis(
                "amount",
                0.88 if semantic_policy == "auto" else 0.62,
                ["column name suggests money, amount, price, cost, or total"],
            )
        )

    if semantic_policy != "off" and is_percentage_name(name):
        hypotheses.append(
            SemanticTypeHypothesis(
                "percentage",
                0.82 if semantic_policy == "auto" else 0.6,
                ["column name suggests percent, rate, ratio, or share"],
            )
        )

    if semantic_policy != "off" and is_postal_name(name):
        hypotheses.append(
            SemanticTypeHypothesis(
                "postal_code",
                0.86 if semantic_policy == "auto" else 0.65,
                ["column name suggests a postal or zip code"],
            )
        )

    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if not numeric.empty:
        integer_like = float(((numeric % 1) == 0).mean())
        min_value = float(numeric.min())
        max_value = float(numeric.max())
        if integer_like > 0.98 and distinct_count <= 25 and distinct_ratio < 0.2:
            hypotheses.append(
                SemanticTypeHypothesis(
                    "numeric_discrete",
                    0.78,
                    ["integer-like values with low cardinality"],
                )
            )
        if semantic_policy != "off" and min_value >= 0 and is_amount_name(name):
            hypotheses.append(
                SemanticTypeHypothesis(
                    "nonnegative_amount",
                    0.72,
                    ["amount-like name and nonnegative values"],
                )
            )
        if semantic_policy != "off" and min_value >= 0 and max_value <= 1 and is_percentage_name(name):
            hypotheses.append(
                SemanticTypeHypothesis(
                    "proportion",
                    0.8,
                    ["values are bounded between 0 and 1"],
                )
            )
        if semantic_policy != "off" and is_geo_name(name):
            in_coordinate_range = (
                ("lat" in name.lower() and -90 <= min_value <= max_value <= 90)
                or (("lon" in name.lower() or "lng" in name.lower() or "long" in name.lower()) and -180 <= min_value <= max_value <= 180)
                or (-180 <= min_value <= max_value <= 180)
            )
            hypotheses.append(
                SemanticTypeHypothesis(
                    "geographic",
                    0.84 if in_coordinate_range and semantic_policy == "auto" else 0.62,
                    ["column name suggests latitude, longitude, or coordinates"],
                )
            )

    if not any(h.semantic_type in {"identifier", "amount", "percentage", "postal_code", "geographic"} for h in hypotheses):
        hypotheses.append(
            SemanticTypeHypothesis(
                "numeric",
                0.72,
                ["pandas dtype is numeric"],
            )
        )

    return hypotheses


def _string_hypotheses(
    name: str,
    series: pd.Series,
    non_null: pd.Series,
    non_null_count: int,
    distinct_count: int,
    distinct_ratio: float,
    *,
    semantic_policy: str,
) -> list[SemanticTypeHypothesis]:
    hypotheses: list[SemanticTypeHypothesis] = []

    if semantic_policy != "off" and is_identifier_name(name) and distinct_ratio > 0.75:
        hypotheses.append(
            SemanticTypeHypothesis(
                "identifier",
                (0.94 if distinct_ratio > 0.95 else 0.82)
                if semantic_policy == "auto"
                else (0.82 if distinct_ratio > 0.95 else 0.62),
                ["name looks identifier-like", f"distinct ratio is {distinct_ratio:.3f}"],
            )
        )

    datetime_parse_ratio = parse_success_ratio(series, "datetime")
    if semantic_policy != "off" and is_time_name(name) and datetime_parse_ratio >= 0.75:
        hypotheses.append(
            SemanticTypeHypothesis(
                "datetime-like",
                min(0.98, 0.55 + datetime_parse_ratio * 0.45)
                if semantic_policy == "auto"
                else min(0.78, 0.38 + datetime_parse_ratio * 0.35),
                ["name looks time-like", f"datetime parse ratio is {datetime_parse_ratio:.3f}"],
            )
        )
    elif datetime_parse_ratio >= 0.92:
        hypotheses.append(
            SemanticTypeHypothesis(
                "datetime-like",
                min(0.88, 0.38 + datetime_parse_ratio * 0.45),
                [f"datetime parse ratio is {datetime_parse_ratio:.3f}"],
            )
        )

    numeric_parse = parse_success_ratio(series, "numeric")
    if numeric_parse >= 0.9:
        hypotheses.append(
            SemanticTypeHypothesis(
                "numeric-like",
                min(0.98, 0.5 + numeric_parse * 0.45),
                [f"numeric parse ratio is {numeric_parse:.3f}"],
            )
        )

    if semantic_policy != "off" and is_amount_name(name) and numeric_parse >= 0.75:
        hypotheses.append(
            SemanticTypeHypothesis(
                "amount",
                0.76 if semantic_policy == "auto" else 0.58,
                ["amount-like name and most values parse as numeric"],
            )
        )

    if semantic_policy != "off" and is_postal_name(name):
        hypotheses.append(
            SemanticTypeHypothesis(
                "postal_code",
                0.82 if semantic_policy == "auto" else 0.58,
                ["column name suggests a postal or zip code"],
            )
        )

    sample = non_null.astype("string").head(1000)
    if not sample.empty:
        email_ratio = float(sample.map(lambda value: bool(EMAIL_RE.match(str(value)))).mean())
        if email_ratio >= 0.75:
            hypotheses.append(
                SemanticTypeHypothesis(
                    "email",
                    min(0.98, 0.5 + email_ratio * 0.45),
                    [f"email pattern ratio is {email_ratio:.3f}"],
                )
            )

        url_ratio = float(sample.map(lambda value: bool(URL_RE.match(str(value)))).mean())
        if url_ratio >= 0.75:
            hypotheses.append(
                SemanticTypeHypothesis(
                    "url",
                    min(0.98, 0.5 + url_ratio * 0.45),
                    [f"url pattern ratio is {url_ratio:.3f}"],
                )
            )

        avg_length = float(sample.str.len().mean())
        max_length = int(sample.str.len().max())
        if parse_success_ratio(series, "json") >= 0.8:
            hypotheses.append(
                SemanticTypeHypothesis(
                    "json-like",
                    0.86,
                    ["most sampled strings start like JSON objects or arrays"],
                )
            )
        if avg_length > 50 or max_length > 500:
            hypotheses.append(
                SemanticTypeHypothesis(
                    "text",
                    0.82,
                    [f"average string length is {avg_length:.1f}"],
                )
            )

    if semantic_policy != "off" and is_geo_name(name):
        hypotheses.append(
            SemanticTypeHypothesis(
                "geographic",
                0.72 if semantic_policy == "auto" else 0.54,
                ["column name suggests latitude, longitude, coordinates, city, state, or country"],
            )
        )

    if distinct_count <= 50 or distinct_ratio <= 0.2:
        hypotheses.append(
            SemanticTypeHypothesis(
                "category",
                0.82,
                [
                    f"{distinct_count} distinct values",
                    f"distinct ratio is {distinct_ratio:.3f}",
                ],
            )
        )
    elif distinct_count >= 50 and distinct_ratio >= 0.5:
        hypotheses.append(
            SemanticTypeHypothesis(
                "string",
                0.62,
                ["high-cardinality string values"],
            )
        )
    else:
        hypotheses.append(
            SemanticTypeHypothesis(
                "string",
                0.52,
                ["object/string dtype with no stronger semantic match"],
            )
        )

    return hypotheses


def _safe_nunique(series: pd.Series) -> int:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return 0


def _dedupe_hypotheses(
    hypotheses: list[SemanticTypeHypothesis],
) -> list[SemanticTypeHypothesis]:
    best: dict[str, SemanticTypeHypothesis] = {}
    for hypothesis in hypotheses:
        current = best.get(hypothesis.semantic_type)
        if current is None or hypothesis.confidence > current.confidence:
            best[hypothesis.semantic_type] = hypothesis
    return sorted(best.values(), key=lambda item: item.confidence, reverse=True)
