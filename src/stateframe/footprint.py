"""Memory-footprint optimization plans for pandas DataFrames."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from pandas.api import types as pdt

from stateframe.models import Profile


INT_RANGES: tuple[tuple[str, type[np.integer]], ...] = (
    ("int8", np.int8),
    ("int16", np.int16),
    ("int32", np.int32),
    ("int64", np.int64),
)
UINT_RANGES: tuple[tuple[str, type[np.integer]], ...] = (
    ("uint8", np.uint8),
    ("uint16", np.uint16),
    ("uint32", np.uint32),
    ("uint64", np.uint64),
)


@dataclass(frozen=True)
class FootprintAction:
    """One dtype change recommended by a footprint optimization plan."""

    column: str
    action: str
    before_dtype: str
    after_dtype: str
    before_bytes: int
    after_bytes: int
    savings_bytes: int
    savings_ratio: float
    confidence: float
    risk: str
    reason: str = ""
    preview: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "action": self.action,
            "before_dtype": self.before_dtype,
            "after_dtype": self.after_dtype,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "savings_bytes": self.savings_bytes,
            "savings_ratio": self.savings_ratio,
            "confidence": self.confidence,
            "risk": self.risk,
            "reason": self.reason,
            "preview": dict(self.preview),
        }


@dataclass
class FootprintPlan:
    """Previewable memory-footprint optimization plan."""

    data: pd.DataFrame = field(repr=False)
    actions: list[FootprintAction] = field(default_factory=list)
    before_bytes: int = 0
    after_bytes: int = 0
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def savings_bytes(self) -> int:
        return max(0, self.before_bytes - self.after_bytes)

    @property
    def savings_ratio(self) -> float:
        if self.before_bytes == 0:
            return 0.0
        return self.savings_bytes / self.before_bytes

    def preview(self) -> pd.DataFrame:
        """Return a tabular preview of dtype changes and estimated savings."""

        return pd.DataFrame([action.to_dict() for action in self.actions])

    def summary(self) -> dict[str, Any]:
        return {
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "savings_bytes": self.savings_bytes,
            "savings_ratio": self.savings_ratio,
            "action_count": len(self.actions),
            "settings": dict(self.settings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "actions": [action.to_dict() for action in self.actions],
        }

    def apply(
        self,
        data: pd.DataFrame | None = None,
        *,
        strict: bool = False,
    ) -> pd.DataFrame:
        """Return a copy with safe dtype optimizations applied.

        If ``data`` differs from the frame used to build the plan, integer and
        float downcasts are revalidated before applying. Unsafe actions are
        skipped by default or raise when ``strict=True``.
        """

        result = (self.data if data is None else data).copy()
        for action in self.actions:
            if action.column not in result.columns:
                continue
            try:
                result[action.column] = _apply_action(result[action.column], action)
            except (OverflowError, TypeError, ValueError) as exc:
                if strict:
                    raise ValueError(
                        f"Cannot safely apply {action.action} to {action.column}"
                    ) from exc
        return result


def build_footprint_plan(
    data_or_profile: pd.DataFrame | Profile,
    *,
    category_max_ratio: float = 0.5,
    category_max_unique: int = 50_000,
    min_savings_bytes: int = 128,
    min_savings_ratio: float = 0.05,
    downcast_ints: bool = True,
    downcast_floats: bool = True,
    float_rtol: float = 1e-6,
    float_atol: float = 1e-9,
    float_to_int: bool = True,
) -> FootprintPlan:
    """Build a conservative dtype optimization plan."""

    if isinstance(data_or_profile, Profile):
        df = data_or_profile.data
        profile = data_or_profile
    else:
        df = data_or_profile
        profile = None

    before_bytes = _dataframe_memory(df)
    actions: list[FootprintAction] = []
    projected = before_bytes

    for column_name in df.columns:
        name = str(column_name)
        series = df[column_name]
        semantic_type = None
        if profile is not None:
            column_profile = profile.column_profiles.get(column_name) or profile.column_profiles.get(name)
            semantic_type = column_profile.semantic_type if column_profile else None

        candidates: list[FootprintAction] = []
        if _category_candidate(series, semantic_type, category_max_ratio, category_max_unique):
            action = _category_action(name, series)
            if action is not None:
                candidates.append(action)

        if isinstance(series.dtype, pd.CategoricalDtype):
            action = _compact_category_action(name, series)
            if action is not None:
                candidates.append(action)

        if downcast_ints and pdt.is_integer_dtype(series.dtype):
            action = _integer_downcast_action(name, series)
            if action is not None:
                candidates.append(action)

        if pdt.is_float_dtype(series.dtype):
            if float_to_int:
                action = _float_to_integer_action(name, series)
                if action is not None:
                    candidates.append(action)
            if downcast_floats:
                action = _float_downcast_action(
                    name,
                    series,
                    rtol=float_rtol,
                    atol=float_atol,
                )
                if action is not None:
                    candidates.append(action)

        best = _best_action(candidates, min_savings_bytes, min_savings_ratio)
        if best is not None:
            actions.append(best)
            projected -= best.savings_bytes

    return FootprintPlan(
        data=df,
        actions=actions,
        before_bytes=before_bytes,
        after_bytes=max(0, projected),
        settings={
            "category_max_ratio": category_max_ratio,
            "category_max_unique": category_max_unique,
            "min_savings_bytes": min_savings_bytes,
            "min_savings_ratio": min_savings_ratio,
            "downcast_ints": downcast_ints,
            "downcast_floats": downcast_floats,
            "float_rtol": float_rtol,
            "float_atol": float_atol,
            "float_to_int": float_to_int,
        },
    )


def optimize_footprint(
    data: pd.DataFrame | Profile,
    **kwargs: Any,
) -> pd.DataFrame:
    """Return a copy of ``data`` with conservative memory optimizations applied."""

    plan = build_footprint_plan(data, **kwargs)
    return plan.apply()


def _category_candidate(
    series: pd.Series,
    semantic_type: str | None,
    max_ratio: float,
    max_unique: int,
) -> bool:
    if isinstance(series.dtype, pd.CategoricalDtype):
        return False
    if not (pdt.is_object_dtype(series.dtype) or pdt.is_string_dtype(series.dtype)):
        return False
    if semantic_type in {"identifier", "text", "json-like", "datetime-like", "numeric-like"}:
        return False
    row_count = int(series.shape[0])
    if row_count == 0:
        return False
    unique_count = int(series.nunique(dropna=True))
    if unique_count == 0:
        return False
    return unique_count <= max_unique and unique_count / row_count <= max_ratio


def _category_action(column: str, series: pd.Series) -> FootprintAction | None:
    converted = series.astype("category")
    return _make_action(
        column,
        series,
        converted,
        action="to_category",
        confidence=0.9,
        risk="low",
        reason="low-cardinality string/object column can use pandas category storage",
        preview={
            "unique_count": int(series.nunique(dropna=True)),
            "unique_ratio": _safe_ratio(series.nunique(dropna=True), series.shape[0]),
        },
    )


def _compact_category_action(column: str, series: pd.Series) -> FootprintAction | None:
    converted = series.cat.remove_unused_categories()
    if len(converted.cat.categories) == len(series.cat.categories):
        return None
    return _make_action(
        column,
        series,
        converted,
        action="compact_category",
        confidence=0.95,
        risk="low",
        reason="category dtype has unused categories that can be removed",
        preview={
            "before_categories": int(len(series.cat.categories)),
            "after_categories": int(len(converted.cat.categories)),
        },
    )


def _integer_downcast_action(column: str, series: pd.Series) -> FootprintAction | None:
    target = _smallest_integer_dtype(series)
    if target is None or str(series.dtype) == target:
        return None
    converted = _safe_integer_cast(series, target)
    return _make_action(
        column,
        series,
        converted,
        action="downcast_integer",
        confidence=0.98,
        risk="low",
        reason="integer min/max fit a smaller integer dtype",
        preview=_range_preview(series),
    )


def _float_to_integer_action(column: str, series: pd.Series) -> FootprintAction | None:
    values = series.dropna()
    if values.empty:
        return None
    finite = values[np.isfinite(values)]
    if finite.shape[0] != values.shape[0]:
        return None
    if not np.all(np.equal(np.mod(finite.to_numpy(dtype=float), 1), 0)):
        return None
    target = _smallest_integer_dtype(series)
    if target is None:
        return None
    converted = _safe_integer_cast(series, target)
    return _make_action(
        column,
        series,
        converted,
        action="float_to_integer",
        confidence=0.92,
        risk="medium",
        reason="all non-missing float values are whole numbers and fit an integer dtype",
        preview=_range_preview(series),
    )


def _float_downcast_action(
    column: str,
    series: pd.Series,
    *,
    rtol: float,
    atol: float,
) -> FootprintAction | None:
    if str(series.dtype) == "float32":
        return None
    values = series.dropna()
    if values.empty:
        return None
    finite = values[np.isfinite(values)]
    if finite.shape[0] != values.shape[0]:
        return None
    converted = series.astype("float32")
    original = series.dropna().astype("float64").to_numpy()
    roundtrip = converted.dropna().astype("float64").to_numpy()
    if not np.allclose(original, roundtrip, rtol=rtol, atol=atol):
        return None
    return _make_action(
        column,
        series,
        converted,
        action="downcast_float",
        confidence=0.86,
        risk="medium",
        reason="float64 values round-trip through float32 within configured tolerance",
        preview={**_range_preview(series), "rtol": rtol, "atol": atol},
    )


def _best_action(
    candidates: list[FootprintAction],
    min_savings_bytes: int,
    min_savings_ratio: float,
) -> FootprintAction | None:
    candidates = [
        action
        for action in candidates
        if action.savings_bytes >= min_savings_bytes
        and action.savings_ratio >= min_savings_ratio
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda action: (action.savings_bytes, action.confidence))


def _make_action(
    column: str,
    before: pd.Series,
    after: pd.Series,
    *,
    action: str,
    confidence: float,
    risk: str,
    reason: str,
    preview: dict[str, Any],
) -> FootprintAction | None:
    before_bytes = _series_memory(before)
    after_bytes = _series_memory(after)
    savings = before_bytes - after_bytes
    if savings <= 0:
        return None
    return FootprintAction(
        column=column,
        action=action,
        before_dtype=str(before.dtype),
        after_dtype=str(after.dtype),
        before_bytes=before_bytes,
        after_bytes=after_bytes,
        savings_bytes=savings,
        savings_ratio=savings / before_bytes if before_bytes else 0.0,
        confidence=confidence,
        risk=risk,
        reason=reason,
        preview=preview,
    )


def _apply_action(series: pd.Series, action: FootprintAction) -> pd.Series:
    if action.action == "to_category":
        return series.astype("category")
    if action.action == "compact_category":
        if not isinstance(series.dtype, pd.CategoricalDtype):
            return series
        return series.cat.remove_unused_categories()
    if action.action in {"downcast_integer", "float_to_integer"}:
        return _safe_integer_cast(series, action.after_dtype)
    if action.action == "downcast_float":
        converted = series.astype(action.after_dtype)
        original = series.dropna().astype("float64").to_numpy()
        roundtrip = converted.dropna().astype("float64").to_numpy()
        if not np.allclose(original, roundtrip, rtol=1e-6, atol=1e-9):
            raise ValueError("float downcast does not round-trip within tolerance")
        return converted
    return series


def _smallest_integer_dtype(series: pd.Series) -> str | None:
    values = series.dropna()
    if values.empty:
        return None
    finite = values[np.isfinite(values.astype("float64"))]
    if finite.shape[0] != values.shape[0]:
        return None
    min_value = int(finite.min())
    max_value = int(finite.max())
    nullable = bool(series.isna().any()) or str(series.dtype).startswith(("Int", "UInt"))
    ranges = UINT_RANGES if min_value >= 0 else INT_RANGES
    for dtype_name, dtype in ranges:
        info = np.iinfo(dtype)
        if info.min <= min_value and max_value <= info.max:
            return _nullable_dtype_name(dtype_name) if nullable else dtype_name
    return "UInt64" if nullable and min_value >= 0 else ("Int64" if nullable else None)


def _safe_integer_cast(series: pd.Series, target: str) -> pd.Series:
    if target.lower().startswith("u"):
        info = np.iinfo(getattr(np, target.lower()))
    else:
        numpy_name = target.lower()
        info = np.iinfo(getattr(np, numpy_name))
    values = series.dropna()
    if not values.empty:
        finite = values[np.isfinite(values.astype("float64"))]
        if finite.shape[0] != values.shape[0]:
            raise ValueError("non-finite values cannot be integer downcast")
        if not np.all(np.equal(np.mod(finite.to_numpy(dtype=float), 1), 0)):
            raise ValueError("non-integer values cannot be integer downcast")
        min_value = int(finite.min())
        max_value = int(finite.max())
        if min_value < info.min or max_value > info.max:
            raise OverflowError("values do not fit target integer dtype")
    return series.astype(target)


def _nullable_dtype_name(dtype_name: str) -> str:
    if dtype_name.startswith("uint"):
        return "UInt" + dtype_name[4:]
    if dtype_name.startswith("int"):
        return "Int" + dtype_name[3:]
    return dtype_name


def _dataframe_memory(df: pd.DataFrame) -> int:
    return int(df.memory_usage(deep=True).sum())


def _series_memory(series: pd.Series) -> int:
    return int(series.memory_usage(index=False, deep=True))


def _safe_ratio(numerator: Any, denominator: Any) -> float:
    denominator = int(denominator)
    if denominator == 0:
        return 0.0
    return float(numerator) / denominator


def _range_preview(series: pd.Series) -> dict[str, Any]:
    values = series.dropna()
    if values.empty:
        return {"min": None, "max": None, "missing_count": int(series.isna().sum())}
    return {
        "min": _jsonish(values.min()),
        "max": _jsonish(values.max()),
        "missing_count": int(series.isna().sum()),
    }


def _jsonish(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value
