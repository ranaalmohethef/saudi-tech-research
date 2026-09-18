"""Profiling: describe a dataset before and after cleaning.

The notebooks use these helpers for the data-quality section; the numbers they
print are the ones quoted in the README and the requirements workbook.
"""

from __future__ import annotations

import pandas as pd

from src.schema import REQUIRED_FIELDS, is_missing


def profile_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per column: dtype, missing count/percent, unique values, sample."""
    rows = []

    for column in frame.columns:
        values = frame[column]
        populated = values.dropna()

        try:
            unique_count = int(values.nunique(dropna=True))
        except TypeError:          # unhashable values such as lists
            unique_count = pd.NA

        rows.append({
            "column": column,
            "dtype": str(values.dtype),
            "null_count": int(values.isna().sum()),
            "null_percent": round(float(values.isna().mean() * 100), 2),
            "unique_count": unique_count,
            "sample_value": str(populated.iloc[0])[:100] if not populated.empty else None,
        })

    return pd.DataFrame(rows)


def missing_report(frame: pd.DataFrame) -> pd.DataFrame:
    """Missing percentage per schema column, counting markers such as ``n/a``."""
    rows = [
        {
            "column": column,
            "missing": int(is_missing(frame[column]).sum()),
            "missing_percent": round(float(is_missing(frame[column]).mean() * 100), 2),
            "required": column in REQUIRED_FIELDS,
        }
        for column in frame.columns
    ]
    return pd.DataFrame(rows)


def duplicate_report(frame: pd.DataFrame, subsets: list[list[str]]) -> pd.DataFrame:
    """Count duplicates for each combination of columns."""
    rows = []

    for subset in subsets:
        present = frame.dropna(subset=subset)
        rows.append({
            "columns": ", ".join(subset),
            "duplicate_rows": int(present.duplicated(subset=subset).sum()),
        })

    return pd.DataFrame(rows)


def year_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    """Records per publication year, sorted by year."""
    counts = (
        frame["publication_year"]
        .value_counts(dropna=False)
        .sort_index()
        .rename_axis("publication_year")
        .reset_index(name="records")
    )
    return counts