"""Shared helpers for cross-platform path and ratio handling."""

from __future__ import annotations

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
