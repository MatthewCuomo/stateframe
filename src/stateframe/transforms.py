"""Safe transformation helpers suggested by scans."""

from __future__ import annotations

from typing import Any

import pandas as pd

from stateframe.config import SuggestedConfig
from stateframe.models import Profile


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
        ``"preserve"``, ``"treat_as_false"``, or ``"treat_as_true"``.
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
        elif null_policy != "preserve":
            raise ValueError("null_policy must be preserve, treat_as_false, or treat_as_true")
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
