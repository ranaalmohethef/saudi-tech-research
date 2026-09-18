"""The common schema and the validation rules agreed by the team.

Both notebooks and ``main.py`` import :func:`validate_dataset`, so every
source is judged by exactly the same rules and the accepted/rejected counts
can be compared across universities.
"""

from __future__ import annotations

import pandas as pd

SCHEMA_COLUMNS = [
    "research_id",
    "university",
    "title",
    "authors",
    "publication_year",
    "publication_date",
    "abstract",
    "research_field",
    "tech_category",
    "journal",
    "doi",
    "url",
    "source",
]

# Fields a record cannot be accepted without.
REQUIRED_FIELDS = [
    "research_id",
    "university",
    "title",
    "authors",
    "publication_year",
    "doi",
    "url",
    "source",
]

OPTIONAL_FIELDS = [
    column for column in SCHEMA_COLUMNS if column not in REQUIRED_FIELDS
]

# Text that means "no value" even though the cell is not empty.
MISSING_MARKERS = {"", "n/a", "na", "nan", "none", "null"}

DOI_FORMAT = r"^10\.\d{4,9}/\S+$"
URL_FORMAT = r"^https?://"
DATE_FORMAT = r"\d{4}-\d{2}-\d{2}"


def schema_table() -> pd.DataFrame:
    """Return the schema as a table (used for the README and the notebooks)."""
    rules = {
        "research_id": "Non-empty, unique",
        "university": "Must match the source's university",
        "title": "Non-empty",
        "authors": "Non-empty",
        "publication_year": "Integer inside the project year range",
        "publication_date": "Valid YYYY-MM-DD when available",
        "abstract": "Text when available",
        "research_field": "Text when available",
        "tech_category": "Assigned later in the project",
        "journal": "Text when available",
        "doi": "Required, bare DOI format 10.xxxx/...",
        "url": "Must start with http:// or https://",
        "source": "Name of the source system",
    }

    return pd.DataFrame(
        [
            {
                "column": column,
                "nullable": column in OPTIONAL_FIELDS,
                "rule": rules[column],
            }
            for column in SCHEMA_COLUMNS
        ]
    )


def is_missing(series: pd.Series) -> pd.Series:
    """True where the value is null, empty, or a missing marker such as ``n/a``."""
    text = series.astype("string").str.strip().str.casefold()
    return series.isna() | text.isin(MISSING_MARKERS)


def validate_dataset(frame: pd.DataFrame, allowed_university: str,
                     min_year: int, max_year: int
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a cleaned dataset into accepted and rejected records.

    Rejected rows keep every original value plus a ``validation_error`` column
    listing every rule they failed, so nothing is silently dropped.
    """
    result = frame.copy()
    errors = pd.Series("", index=result.index, dtype="string")

    for column in REQUIRED_FIELDS:
        errors.loc[is_missing(result[column])] += f"{column} is missing; "

    errors.loc[result["university"] != allowed_university] += "invalid university; "

    years = pd.to_numeric(result["publication_year"], errors="coerce")
    errors.loc[years.isna() | ~years.between(min_year, max_year)] += (
        "invalid publication year; "
    )

    invalid_url = ~result["url"].astype("string").str.match(URL_FORMAT, na=False)
    errors.loc[invalid_url] += "invalid URL; "

    doi_present = ~is_missing(result["doi"])
    invalid_doi = doi_present & ~result["doi"].astype("string").str.match(
        DOI_FORMAT, case=False, na=False
    )
    errors.loc[invalid_doi] += "invalid DOI; "

    date_text = result["publication_date"].astype("string").str.strip()
    date_present = ~is_missing(result["publication_date"])
    parsed_dates = pd.to_datetime(date_text, format="%Y-%m-%d", errors="coerce")
    invalid_date = date_present & (
        ~date_text.str.fullmatch(DATE_FORMAT, na=False) | parsed_dates.isna()
    )
    errors.loc[invalid_date] += "invalid publication date; "

    errors.loc[result["research_id"].duplicated(keep=False)] += "duplicate research_id; "

    result["validation_error"] = errors.str.rstrip("; ")

    validated = result[result["validation_error"] == ""].copy()
    rejected = result[result["validation_error"] != ""].copy()

    return validated, rejected


def failures_by_rule(rejected: pd.DataFrame) -> pd.DataFrame:
    """Count how many records failed each individual rule."""
    if rejected.empty:
        return pd.DataFrame(columns=["rule", "records"])

    counts = (
        rejected["validation_error"]
        .str.split("; ")
        .explode()
        .value_counts()
        .rename_axis("rule")
        .reset_index(name="records")
    )
    return counts
