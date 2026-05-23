"""Safe transformation helpers suggested by scans."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stateframe.config import SuggestedConfig
from stateframe.models import Profile


def rename_columns(
    data: pd.DataFrame,
    mapping: dict[Any, Any] | None = None,
    *,
    columns: list[str] | None = None,
    case: str = "preserve",
    separator: str | None = None,
    remove_punctuation: bool = False,
    strip: bool = True,
    collapse: bool = True,
    prefix_if_digit: str = "col_",
    prefix: str = "",
    suffix: str = "",
    uniquify: bool = True,
    errors: str = "raise",
) -> pd.DataFrame:
    """Return a copy with manual and/or rule-based column renames.

    ``mapping`` handles selected manual renames. The rule options can then be
    applied to all columns or a selected subset. Use ``separator="_"`` for
    snake-ish names, ``separator=""`` for compact names, or leave it ``None``
    to preserve existing internal spacing.
    """

    result = data.copy()
    rename_map = dict(mapping or {})
    if errors not in {"raise", "ignore"}:
        raise ValueError("errors must be raise or ignore")
    if errors == "raise":
        missing = [column for column in rename_map if column not in result.columns]
        if missing:
            raise KeyError(missing[0])

    selected = set(columns) if columns is not None else set(result.columns)
    if columns is not None and errors == "raise":
        missing = [column for column in columns if column not in result.columns]
        if missing:
            raise KeyError(missing[0])

    proposed: list[str] = []
    for column in result.columns:
        if column in rename_map:
            name = str(rename_map[column])
        else:
            name = str(column)
        if column in selected or column in rename_map:
            name = clean_column_name(
                name,
                case=case,
                separator=separator,
                remove_punctuation=remove_punctuation,
                strip=strip,
                collapse=collapse,
                prefix_if_digit=prefix_if_digit,
            )
            name = f"{prefix}{name}{suffix}"
        proposed.append(name)
    result.columns = _unique_names(proposed) if uniquify else proposed
    return result


def clean_column_names(
    data: pd.DataFrame,
    *,
    case: str = "lower",
    separator: str = "_",
    remove_punctuation: bool = True,
    strip: bool = True,
    collapse: bool = True,
    prefix_if_digit: str = "col_",
    mapping: dict[Any, Any] | None = None,
    columns: list[str] | None = None,
    uniquify: bool = True,
) -> pd.DataFrame:
    """Return a copy with analysis-friendly column names.

    This is a friendly mass-rename wrapper around :func:`rename_columns`.
    """

    return rename_columns(
        data,
        mapping=mapping,
        columns=columns,
        case=case,
        separator=separator,
        remove_punctuation=remove_punctuation,
        strip=strip,
        collapse=collapse,
        prefix_if_digit=prefix_if_digit,
        uniquify=uniquify,
    )


def clean_column_name(
    name: Any,
    *,
    case: str = "lower",
    separator: str | None = "_",
    remove_punctuation: bool = True,
    strip: bool = True,
    collapse: bool = True,
    prefix_if_digit: str = "col_",
) -> str:
    """Normalize one column name with the same rules used by mass renaming."""

    import re

    text = str(name)
    if strip:
        text = text.strip()
    if remove_punctuation:
        text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    if separator is not None:
        text = re.sub(r"\s+", separator, text)
    if collapse and separator:
        escaped = re.escape(separator)
        text = re.sub(f"{escaped}+", separator, text).strip(separator)
    if case == "lower":
        text = text.lower()
    elif case == "upper":
        text = text.upper()
    elif case == "title":
        text = text.title()
    elif case == "preserve":
        pass
    else:
        raise ValueError("case must be preserve, lower, upper, or title")
    if prefix_if_digit and text[:1].isdigit():
        text = f"{prefix_if_digit}{text}"
    return text or "column"


def unify_binary_flags(
    data: pd.DataFrame,
    *,
    scan: Profile | None = None,
    columns: list[str] | None = None,
    mappings: dict[str, dict[Any, Any]] | None = None,
    to: str = "int",
    null_policy: str = "preserve",
) -> pd.DataFrame:
    """Return a copy with binary-like columns consistently mapped.

    Parameters
    ----------
    data:
        Source DataFrame.
    scan:
        Optional stateframe profile/scan with detected binary mappings.
    columns:
        Optional subset of columns to transform.
    mappings:
        Explicit mappings override scan-inferred mappings.
    to:
        ``"int"``, ``"bool_nullable"``, ``"bool"``, ``"yes_no"``, or ``"yn"``.
    null_policy:
        ``"preserve"``, ``"treat_as_false"``, ``"treat_as_true"``,
        ``"false_to_null"``, or ``"true_to_null"``.
    """

    result = data.copy()
    inferred: dict[str, dict[Any, Any]] = {}
    if scan is not None:
        for name, binary_profile in scan.binary_flags().items():
            if not binary_profile.ambiguous:
                inferred[name] = dict(binary_profile.suggested_mapping)
    if mappings:
        inferred.update(mappings)

    selected = columns or list(inferred)
    for column in selected:
        if column not in result.columns:
            raise KeyError(column)
        mapping = inferred.get(column)
        if mapping is None:
            raise ValueError(
                f"No binary mapping known for {column}. Provide mappings=... or pass a scan with a detected mapping."
            )
        mapped = result[column].map(mapping)
        if null_policy == "treat_as_false":
            mapped = mapped.fillna(0)
        elif null_policy == "treat_as_true":
            mapped = mapped.fillna(1)
        elif null_policy == "false_to_null":
            mapped = mapped.mask(mapped == 0)
        elif null_policy == "true_to_null":
            mapped = mapped.mask(mapped == 1)
        elif null_policy != "preserve":
            raise ValueError(
                "null_policy must be preserve, treat_as_false, treat_as_true, false_to_null, or true_to_null"
            )
        result[column] = _format_binary(mapped, to=to)
    return result


def apply_suggested_conversions(
    data: pd.DataFrame,
    suggested: SuggestedConfig | Profile,
) -> pd.DataFrame:
    """Apply conservative type conversions from a suggested config or scan."""

    config = suggested.use_suggested() if isinstance(suggested, Profile) else suggested
    result = data.copy()
    for column in config.numeric_conversions:
        if column in result:
            cleaned = (
                result[column]
                .astype("string")
                .str.strip()
                .str.replace(",", "", regex=False)
                .str.replace("$", "", regex=False)
                .str.replace("%", "", regex=False)
            )
            result[column] = pd.to_numeric(cleaned, errors="coerce")
    for column in config.datetime_conversions:
        if column in result:
            result[column] = pd.to_datetime(result[column], errors="coerce")
    if config.binary_mappings:
        result = unify_binary_flags(result, mappings=config.binary_mappings, to="int")
    return result


def map_values(
    data: pd.DataFrame,
    mappings: dict[str, dict[Any, Any]],
    *,
    default: str | Any = "preserve",
    case_sensitive: bool = True,
    strip: bool = True,
) -> pd.DataFrame:
    """Return a copy with explicit value maps applied column by column.

    ``default="preserve"`` keeps values not present in the mapping. Use
    ``default=None`` or any scalar to assign a fallback value.
    """

    result = data.copy()
    for column, mapping in mappings.items():
        if column not in result.columns:
            raise KeyError(column)
        if case_sensitive and not strip:
            keys = result[column]
            mapped = keys.map(mapping)
            matched = keys.isin(list(mapping.keys()))
        else:
            normalized_mapping = {
                _normalize_map_key(key, case_sensitive=case_sensitive, strip=strip): value
                for key, value in mapping.items()
            }
            keys = result[column].map(
                lambda value: _normalize_map_key(value, case_sensitive=case_sensitive, strip=strip)
            )
            mapped = keys.map(normalized_mapping)
            matched = keys.isin(list(normalized_mapping.keys()))
        if default == "preserve":
            result[column] = mapped.where(matched, result[column])
        else:
            result[column] = mapped.where(matched, default)
    return result


def add_missing_indicators(
    data: pd.DataFrame,
    columns: list[str] | None = None,
    *,
    suffix: str = "_was_missing",
) -> pd.DataFrame:
    """Add boolean indicator columns showing where selected values were missing."""

    result = data.copy()
    selected = columns or [str(column) for column in result.columns if result[column].isna().any()]
    for column in selected:
        if column not in result.columns:
            raise KeyError(column)
        result[f"{column}{suffix}"] = result[column].isna().astype("int8")
    return result


def impute_missing(
    data: pd.DataFrame,
    strategies: dict[str, str | dict[str, Any]] | None = None,
    *,
    columns: list[str] | None = None,
    strategy: str = "median",
    fill_value: Any = None,
    add_indicators: bool = False,
    indicator_suffix: str = "_was_imputed",
) -> pd.DataFrame:
    """Impute missing values with simple, replayable strategies.

    Strategies can be passed globally or per column. Per-column dictionaries may
    include ``strategy``, ``fill_value``, and ``groupby``.
    """

    result = data.copy()
    selected = columns or list(strategies or {}) or [str(column) for column in result.columns if result[column].isna().any()]
    if add_indicators:
        for column in selected:
            if column in result.columns:
                result[f"{column}{indicator_suffix}"] = result[column].isna().astype("int8")
    for column in selected:
        if column not in result.columns:
            raise KeyError(column)
        spec = strategies.get(column) if strategies else None
        if isinstance(spec, dict):
            column_strategy = str(spec.get("strategy") or strategy)
            column_fill = spec.get("fill_value", fill_value)
            groupby = spec.get("groupby")
        else:
            column_strategy = str(spec or strategy)
            column_fill = fill_value
            groupby = None
        if groupby:
            if groupby not in result.columns:
                raise KeyError(groupby)
            result[column] = result.groupby(groupby, dropna=False)[column].transform(
                lambda values: values.fillna(_impute_value(values, column_strategy, column_fill))
            )
            if result[column].isna().any():
                result[column] = result[column].fillna(_impute_value(result[column], column_strategy, column_fill))
        else:
            result[column] = result[column].fillna(_impute_value(result[column], column_strategy, column_fill))
    return result


def one_hot_encode(
    data: pd.DataFrame,
    columns: list[str],
    *,
    drop_first: bool = False,
    dummy_na: bool = False,
    max_categories: int | None = None,
    other_label: str = "Other",
    dtype: str = "int8",
) -> pd.DataFrame:
    """One-hot encode selected categorical columns with optional rare grouping."""

    result = data.copy()
    encoded_parts: list[pd.DataFrame] = []
    for column in columns:
        if column not in result.columns:
            raise KeyError(column)
        values = result[column].astype("string")
        if max_categories is not None and max_categories > 0:
            top = values.value_counts(dropna=True).head(max_categories).index
            values = values.where(values.isin(top) | values.isna(), other_label)
        dummies = pd.get_dummies(values, prefix=column, dummy_na=dummy_na, drop_first=drop_first, dtype=dtype)
        encoded_parts.append(dummies)
        result = result.drop(columns=[column])
    if encoded_parts:
        result = pd.concat([result, *encoded_parts], axis=1)
    return result


def scale_numeric(
    data: pd.DataFrame,
    columns: list[str] | None = None,
    *,
    method: str = "standard",
) -> pd.DataFrame:
    """Scale numeric columns using standard, min-max, robust, or max-abs scaling."""

    result = data.copy()
    selected = columns or [str(column) for column in result.select_dtypes(include=["number"]).columns]
    for column in selected:
        if column not in result.columns:
            raise KeyError(column)
        values = pd.to_numeric(result[column], errors="coerce").astype("float64")
        if method == "standard":
            center = values.mean()
            scale = values.std(ddof=0)
        elif method == "minmax":
            center = values.min()
            scale = values.max() - values.min()
        elif method == "robust":
            center = values.median()
            scale = values.quantile(0.75) - values.quantile(0.25)
        elif method == "maxabs":
            center = 0
            scale = values.abs().max()
        else:
            raise ValueError("method must be standard, minmax, robust, or maxabs")
        result[column] = (values - center) / scale if scale and not pd.isna(scale) else 0.0
    return result


def add_date_features(
    data: pd.DataFrame,
    columns: list[str],
    *,
    features: list[str] | None = None,
    drop_original: bool = False,
) -> pd.DataFrame:
    """Expand datetime-like columns into common modeling/analysis features."""

    result = data.copy()
    selected_features = features or ["year", "quarter", "month", "day", "weekday", "is_weekend"]
    for column in columns:
        if column not in result.columns:
            raise KeyError(column)
        values = pd.to_datetime(result[column], errors="coerce", format="mixed")
        for feature in selected_features:
            name = f"{column}_{feature}"
            if feature == "year":
                result[name] = values.dt.year.astype("Int64")
            elif feature == "quarter":
                result[name] = values.dt.quarter.astype("Int64")
            elif feature == "month":
                result[name] = values.dt.month.astype("Int64")
            elif feature == "day":
                result[name] = values.dt.day.astype("Int64")
            elif feature == "weekday":
                result[name] = values.dt.weekday.astype("Int64")
            elif feature == "is_weekend":
                result[name] = values.dt.weekday.isin([5, 6]).astype("int8")
            elif feature == "hour":
                result[name] = values.dt.hour.astype("Int64")
            elif feature == "date":
                result[name] = values.dt.date
            else:
                raise ValueError(f"Unknown date feature: {feature}")
        if drop_original:
            result = result.drop(columns=[column])
    return result


def add_ratio(
    data: pd.DataFrame,
    numerator: str,
    denominator: str,
    output: str,
    *,
    zero_policy: str = "null",
) -> pd.DataFrame:
    """Add a safe ratio column from two numeric inputs."""

    if numerator not in data.columns:
        raise KeyError(numerator)
    if denominator not in data.columns:
        raise KeyError(denominator)
    result = data.copy()
    left = pd.to_numeric(result[numerator], errors="coerce")
    right = pd.to_numeric(result[denominator], errors="coerce")
    ratio = left / right.replace(0, np.nan)
    if zero_policy == "zero":
        ratio = ratio.fillna(0)
    elif zero_policy != "null":
        raise ValueError("zero_policy must be null or zero")
    result[output] = ratio
    return result


def clean_numeric_outliers(
    data: pd.DataFrame,
    rules: dict[str, dict[str, Any] | str],
) -> pd.DataFrame:
    """Apply simple numeric outlier treatments column by column.

    Supported treatments are ``inspect``/skip, ``flag``, ``null``, ``clip``, and
    ``drop``. Supported methods are ``iqr``, ``zscore``, ``modified_zscore``, and
    ``percentile``.
    """

    result = data.copy()
    drop_mask = pd.Series(False, index=result.index)
    for column, raw_rule in rules.items():
        if column not in result.columns:
            raise KeyError(column)
        rule = {"treatment": raw_rule} if isinstance(raw_rule, str) else dict(raw_rule)
        treatment = str(rule.get("treatment") or "inspect")
        if treatment in {"inspect", "skip"}:
            continue
        values = pd.to_numeric(result[column], errors="coerce").astype("float64")
        lower, upper = _outlier_bounds(values, rule)
        mask = _outlier_mask(values, lower, upper)
        if treatment == "flag":
            result[f"{column}_is_outlier"] = mask.fillna(False).astype("int8")
        elif treatment == "null":
            result[column] = result[column].mask(mask)
        elif treatment == "clip":
            result[column] = values.clip(lower=lower, upper=upper)
        elif treatment == "drop":
            drop_mask = drop_mask | mask.fillna(False)
        else:
            raise ValueError("outlier treatment must be inspect, flag, null, clip, or drop")
    if drop_mask.any():
        result = result.loc[~drop_mask].copy()
    return result


def _format_binary(values: pd.Series, *, to: str) -> pd.Series:
    if to == "int":
        return values.astype("Int64")
    if to == "bool_nullable":
        return values.map({1: True, 0: False}).astype("boolean")
    if to == "bool":
        if values.isna().any():
            raise ValueError("Cannot convert to non-nullable bool while nulls are present.")
        return values.astype(bool)
    if to == "yes_no":
        return values.map({1: "Yes", 0: "No"})
    if to == "yn":
        return values.map({1: "Y", 0: "N"})
    raise ValueError("to must be one of int, bool_nullable, bool, yes_no, or yn")


def _unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in names:
        base = name or "column"
        count = seen.get(base, 0)
        result.append(base if count == 0 else f"{base}_{count + 1}")
        seen[base] = count + 1
    return result


def _normalize_map_key(value: Any, *, case_sensitive: bool, strip: bool) -> Any:
    if pd.isna(value):
        return value
    text = str(value)
    if strip:
        text = text.strip()
    if not case_sensitive:
        text = text.casefold()
    return text


def _impute_value(series: pd.Series, strategy: str, fill_value: Any) -> Any:
    if strategy == "constant":
        return fill_value
    if strategy == "mean":
        return pd.to_numeric(series, errors="coerce").mean()
    if strategy == "median":
        return pd.to_numeric(series, errors="coerce").median()
    if strategy == "mode":
        modes = series.mode(dropna=True)
        return modes.iloc[0] if not modes.empty else fill_value
    if strategy == "zero":
        return 0
    if strategy == "missing":
        return "Missing"
    raise ValueError("strategy must be constant, mean, median, mode, zero, missing")


def _outlier_bounds(values: pd.Series, rule: dict[str, Any]) -> tuple[float | None, float | None]:
    method = str(rule.get("method") or "iqr")
    finite = values[np.isfinite(values)].dropna()
    if finite.empty:
        return None, None
    if method == "iqr":
        multiplier = float(rule.get("multiplier", 1.5))
        q1 = finite.quantile(0.25)
        q3 = finite.quantile(0.75)
        iqr = q3 - q1
        return float(q1 - multiplier * iqr), float(q3 + multiplier * iqr)
    if method == "zscore":
        threshold = float(rule.get("threshold", 3.0))
        mean = finite.mean()
        std = finite.std(ddof=0)
        if not std:
            return None, None
        return float(mean - threshold * std), float(mean + threshold * std)
    if method == "modified_zscore":
        threshold = float(rule.get("threshold", 3.5))
        median = finite.median()
        mad = (finite - median).abs().median()
        if not mad:
            return None, None
        scale = threshold * mad / 0.6745
        return float(median - scale), float(median + scale)
    if method == "percentile":
        lower_q = float(rule.get("lower_quantile", 0.01))
        upper_q = float(rule.get("upper_quantile", 0.99))
        return float(finite.quantile(lower_q)), float(finite.quantile(upper_q))
    raise ValueError("outlier method must be iqr, zscore, modified_zscore, or percentile")


def _outlier_mask(values: pd.Series, lower: float | None, upper: float | None) -> pd.Series:
    mask = pd.Series(False, index=values.index)
    if lower is not None:
        mask = mask | values.lt(lower)
    if upper is not None:
        mask = mask | values.gt(upper)
    return mask.fillna(False)
