"""Small helpers shared across the first implementation."""

from __future__ import annotations

from typing import Any

import math
import re
import warnings

import numpy as np
import pandas as pd


ID_NAME_RE = re.compile(r"(^id$|_id$|^id_|uuid|guid|key$|_key$)", re.IGNORECASE)
TIME_NAME_RE = re.compile(r"(date|time|timestamp|_ts$|created|updated)", re.IGNORECASE)
AMOUNT_NAME_RE = re.compile(
    r"(amount|revenue|sales|price|cost|spend|charge|payment|total|balance)",
    re.IGNORECASE,
)
PERCENTAGE_NAME_RE = re.compile(
    r"(percent|percentage|pct|rate|ratio|share|probability|score)",
    re.IGNORECASE,
)
OUTCOME_NAME_RE = re.compile(
    r"(target|label|outcome|class|churn|default|fraud|converted|conversion|response|sold_price|sale_price|sale_amount|days_on_market|^dom$|^y$)",
    re.IGNORECASE,
)
POSTAL_NAME_RE = re.compile(r"(zip|zipcode|postal|postcode)", re.IGNORECASE)
GEO_NAME_RE = re.compile(
    r"(lat|latitude|lon|lng|longitude|geo|coord|city|state|country|county|tract)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None


def clean_metric(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if pd.isna(value) if not isinstance(value, (list, tuple, dict)) else False:
        return None
    return value


def clean_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: clean_metric(value) for key, value in metrics.items()}


def is_identifier_name(name: str) -> bool:
    return bool(ID_NAME_RE.search(name))


def is_time_name(name: str) -> bool:
    return bool(TIME_NAME_RE.search(name))


def is_amount_name(name: str) -> bool:
    return bool(AMOUNT_NAME_RE.search(name))


def is_percentage_name(name: str) -> bool:
    return bool(PERCENTAGE_NAME_RE.search(name))


def is_outcome_name(name: str) -> bool:
    return bool(OUTCOME_NAME_RE.search(name))


def is_postal_name(name: str) -> bool:
    return bool(POSTAL_NAME_RE.search(name))


def is_geo_name(name: str) -> bool:
    return bool(GEO_NAME_RE.search(name))


def parse_success_ratio(series: pd.Series, parser: str) -> float:
    non_null = series.dropna()
    if non_null.empty:
        return 0.0
    sample = non_null.astype("string").head(1000)
    missing_tokens = {"", " ", "na", "n/a", "nan", "none", "null", "missing", "unknown", "?", "-", "--"}
    semantic_missing = sample.str.strip().str.lower().isin(missing_tokens)
    parse_sample = sample[~semantic_missing]
    if parse_sample.empty:
        return 0.0
    if parser == "numeric":
        parsed = pd.to_numeric(parse_sample, errors="coerce")
    elif parser == "datetime":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(parse_sample, errors="coerce", format="mixed")
    elif parser == "boolean":
        lowered = parse_sample.str.lower().str.strip()
        parsed = lowered.isin({"true", "false", "yes", "no", "0", "1", "y", "n"})
        return float(parsed.mean())
    elif parser == "json":
        stripped = parse_sample.str.strip()
        parsed = stripped.str.startswith("{") | stripped.str.startswith("[")
        return float(parsed.mean())
    else:
        raise ValueError(f"Unknown parser: {parser}")
    return float(parsed.notna().mean())
