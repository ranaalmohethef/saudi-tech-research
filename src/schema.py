"""Common schema and validation rules for the project.

Every included university is validated with the same rules. Validation is
structural: it checks required values, formats, year/date consistency, and
identifier uniqueness. It does not prove that a DOI belongs to a title or that
a record is truly technology-related.
"""

from __future__ import annotations

from urllib.parse import urlsplit

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

OPTIONAL_FIELDS = [column for column in SCHEMA_COLUMNS if column not in REQUIRED_FIELDS]

MISSING_MARKERS = {
    "",
    "n/a",
    "na",
    "nan",
    "none",
    "null",
    "<na>",
    "nat",
}

DOI_FORMAT = r"^10\.\d{4,9}/\S+$"
DATE_FORMAT = r"\d{4}-\d{2}-\d{2}"


def schema_table() -> pd.DataFrame:
    """Return the agreed schema as a table for notebooks and documentation."""
    rules = {
        "research_id": "Non-empty and unique",
        "university": "Must match the source university",
        "title": "Non-empty research title",
        "authors": "Non-empty author information",
        "publication_year": "Whole year inside the project range",
        "publication_date": "Valid YYYY-MM-DD when available; same year as publication_year",
        "abstract": "Text when available",
        "research_field": "Text when available",
        "tech_category": "Technology category when assigned",
        "journal": "Journal or venue when available",
        "doi": "Required bare DOI: 10.xxxx/...",
        "url": "Valid HTTP or HTTPS URL",
        "source": "Non-empty source identifier",
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
    """Return True for nulls, blanks, and textual missing-value markers."""
    text = series.astype("string").str.strip().str.casefold()
    return series.isna() | text.isin(MISSING_MARKERS)


def is_valid_url(value) -> bool:
    """Return True only for a complete HTTP(S) URL with a hostname."""
    if value is None or pd.isna(value):
        return False

    text = str(value).strip()
    if not text or any(character.isspace() for character in text):
        return False

    try:
        parts = urlsplit(text)
    except (TypeError, ValueError):
        return False

    return parts.scheme.casefold() in {"http", "https"} and bool(parts.hostname)


def validate_dataset(
    frame: pd.DataFrame,
    allowed_university: str,
    min_year: int,
    max_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a cleaned dataset into accepted and rejected records.

    Rejected rows keep every original value plus ``validation_error`` listing
    every failed rule. A missing required field is therefore reported rather
    than silently removed during cleaning.
    """
    missing_columns = [column for column in SCHEMA_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Dataset is missing schema columns: {missing_columns}")

    result = frame.copy()
    errors = pd.Series("", index=result.index, dtype="string")

    for column in REQUIRED_FIELDS:
        errors.loc[is_missing(result[column])] += f"{column} is missing; "

    university_present = ~is_missing(result["university"])
    invalid_university = university_present & result["university"].astype("string").str.strip().ne(
        allowed_university
    )
    errors.loc[invalid_university] += "invalid university; "

    years = pd.to_numeric(result["publication_year"], errors="coerce")
    whole_year = years.notna() & years.mod(1).eq(0)
    invalid_year = ~whole_year | ~years.between(min_year, max_year)
    errors.loc[invalid_year] += "invalid publication year; "

    url_present = ~is_missing(result["url"])
    invalid_url = url_present & ~result["url"].map(is_valid_url)
    errors.loc[invalid_url] += "invalid URL; "

    doi_present = ~is_missing(result["doi"])
    invalid_doi = doi_present & ~result["doi"].astype("string").str.match(
        DOI_FORMAT, case=False, na=False
    )
    errors.loc[invalid_doi] += "invalid DOI; "

    date_text = result["publication_date"].astype("string").str.strip()
    date_present = ~is_missing(result["publication_date"])
    parsed_dates = pd.to_datetime(date_text, format="%Y-%m-%d", errors="coerce")
    valid_date_format = date_text.str.fullmatch(DATE_FORMAT, na=False)
    invalid_date = date_present & (~valid_date_format | parsed_dates.isna())
    errors.loc[invalid_date] += "invalid publication date; "

    comparable_date = date_present & ~invalid_date & whole_year
    date_year_mismatch = comparable_date & parsed_dates.dt.year.ne(years)
    errors.loc[date_year_mismatch] += "publication date/year mismatch; "

    errors.loc[result["research_id"].duplicated(keep=False)] += "duplicate research_id; "

    result["validation_error"] = errors.str.rstrip("; ")

    validated = result[result["validation_error"] == ""].copy()
    rejected = result[result["validation_error"] != ""].copy()

    return validated, rejected


def failures_by_rule(rejected: pd.DataFrame) -> pd.DataFrame:
    """Count how many records failed each individual validation rule."""
    if rejected.empty:
        return pd.DataFrame(columns=["rule", "records"])

    return (
        rejected["validation_error"]
        .str.split("; ")
        .explode()
        .value_counts()
        .rename_axis("rule")
        .reset_index(name="records")
    )
