"""Shared helpers for cross-platform path and ratio handling."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


def project_root() -> Path:
    """Return the repository root from the package location."""
    return Path(__file__).resolve().parents[2]


def data_path(*parts: str) -> Path:
    """Build a path under the repository data directory."""
    return project_root().joinpath("data", *parts)


def output_path(*parts: str) -> Path:
    """Build a path under the repository output directory."""
    return project_root().joinpath("output", *parts)


def safe_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    """Guard divide-by-zero so percentage columns remain numeric."""
    numer = pd.to_numeric(numer, errors="coerce").fillna(0.0)
    denom = pd.to_numeric(denom, errors="coerce").fillna(0.0)
    return numer.div(denom.where(denom != 0)).fillna(0.0)


def autoscale_rate_axis_range(*value_groups: object) -> list[float] | None:
    """Return a padded axis range around the currently visible rate values."""
    numeric_values: list[float] = []
    for value_group in value_groups:
        if value_group is None:
            continue
        if isinstance(value_group, pd.Series):
            values = value_group
        else:
            try:
                values = pd.Series(list(value_group))  # type: ignore[arg-type]
            except TypeError:
                values = pd.Series([value_group])
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        numeric_values.extend(
            float(value)
            for value in numeric
            if math.isfinite(float(value))
        )

    if not numeric_values:
        return None

    low = min(numeric_values)
    high = max(numeric_values)
    span = high - low
    padding = max(span * 0.08, 0.02)
    if span == 0:
        padding = max(padding, 0.03)

    axis_low = low - padding
    axis_high = high + padding
    if low >= 0:
        axis_low = max(0.0, axis_low)
    if high <= 1:
        axis_high = min(1.0, axis_high)

    if axis_high - axis_low < 0.05:
        midpoint = (axis_low + axis_high) / 2
        axis_low = midpoint - 0.025
        axis_high = midpoint + 0.025
        if low >= 0:
            axis_low = max(0.0, axis_low)
        if high <= 1:
            axis_high = min(1.0, axis_high)

    return [axis_low, axis_high]


def match_sequence_axis_range(point_count: int) -> list[float] | None:
    """Pad match-order axes to the rows included in the visible chart."""
    if point_count <= 0:
        return None
    return [0.5, point_count + 0.5]
