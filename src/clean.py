"""Cleaning: turn each raw source into the 13-column common schema.

The generic helpers at the top are shared by every source. The ``clean_*``
functions below apply the source-specific decisions that are documented in the
notebooks (date handling, deduplication, KFUPM department filter, KSU year
rule). No function invents a value: a missing month or day stays missing,
except for the KAUST repository rule documented in ``parse_partial_date``.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd

from src.schema import SCHEMA_COLUMNS

DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
DOI_PREFIX_PATTERN = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE
)


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------
def snake_case_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to snake_case (``Publication Date`` -> ``publication_date``)."""
    result = frame.copy()
    result.columns = (
        result.columns.str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return result


def strip_and_blank_to_na(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim every text column and turn empty strings into missing values."""
    result = frame.copy()

    for column in result.columns:
        if pd.api.types.is_string_dtype(result[column]) or result[column].dtype == object:
            result[column] = result[column].astype("string").str.strip()

    return result.replace(r"^\s*$", pd.NA, regex=True)


def clean_markup(value) -> str | pd.NA:
    """Remove HTML/JATS tags and collapse whitespace (Crossref abstracts)."""
    if pd.isna(value):
        return pd.NA

    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\\n", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or pd.NA


def normalize_doi(value) -> str | pd.NA:
    """Return the bare lowercase DOI (``10.xxxx/...``) or missing.

    Handles ``https://doi.org/...``, ``http://dx.doi.org/...`` and ``doi:``
    prefixes, and drops a trailing full stop.
    """
    if value is None or pd.isna(value):
        return pd.NA

    text = DOI_PREFIX_PATTERN.sub("", str(value).strip())
    match = DOI_PATTERN.search(text)
    if not match:
        return pd.NA

    return match.group(0).rstrip(".").lower()


def parse_partial_date(value, complete_only: bool = False):
    """Parse a date that may be ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``.

    ``complete_only=True`` (KFUPM rule) keeps only full calendar dates and
    returns ``None`` for anything shorter. ``complete_only=False`` (KAUST
    repository rule) completes a partial date with the first month/day, which
    is what the original pandas cleaning did; the choice is documented in the
    notebook so the reader knows the day was not in the source.
    """
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return _to_date(text, "%Y-%m-%d")

    if complete_only:
        return None

    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
        return _to_date(text, "%Y-%m-%d")
    if re.fullmatch(r"\d{4}-\d{1,2}", text):
        return _to_date(text, "%Y-%m")
    if re.fullmatch(r"\d{4}", text):
        return _to_date(text, "%Y")
    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        return _to_date(text[:10], "%Y-%m-%d")

    return None


def _to_date(text: str, fmt: str):
    parsed = pd.to_datetime(text, format=fmt, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def format_date(value) -> str | pd.NA:
    """Format a date object as ``YYYY-MM-DD`` text, or missing."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NA
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def completeness_score(frame: pd.DataFrame) -> pd.Series:
    """Count the populated fields of each row (used to pick the best duplicate)."""
    return frame.notna().sum(axis=1)


def deduplicate(frame: pd.DataFrame, subset: list[str],
                prefer: list[str]) -> pd.DataFrame:
    """Keep one row per ``subset`` group, preferring the rows sorted first.

    ``prefer`` lists the columns to sort by in descending order (for example
    completeness, then the most recently modified record).
    """
    ordered = frame.sort_values(prefer, ascending=[False] * len(prefer))
    return ordered.drop_duplicates(subset=subset, keep="first")


def to_schema(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the frame with exactly the 13 schema columns, in order."""
    result = frame.copy()

    for column in SCHEMA_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    return result[SCHEMA_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------
# KAUST repository export
# --------------------------------------------------------------------------
def clean_kaust_repository(raw: pd.DataFrame, year: int,
                           university: str = "KAUST",
                           source_label: str = "KAUST Repository") -> pd.DataFrame:
    """Clean the KAUST repository CSV and map it to the common schema."""
    frame = strip_and_blank_to_na(snake_case_columns(raw))

    frame["parsed_date"] = frame["publication_date"].map(parse_partial_date)
    frame["parsed_year"] = frame["parsed_date"].map(
        lambda value: value.year if value is not None else pd.NA
    )
    frame = frame[frame["parsed_year"] == year].copy()

    frame["doi"] = frame["doi"].map(normalize_doi)

    # A record without a DOI can only be matched by its repository handle.
    frame["dedup_key"] = [
        handle if pd.isna(doi) else f"{doi}|{title}|{kind}|{date}"
        for doi, handle, title, kind, date in zip(
            frame["doi"], frame["handle"], frame["title"],
            frame["type"], frame["parsed_date"]
        )
    ]
    frame["completeness"] = completeness_score(
        frame.drop(columns=["parsed_date", "parsed_year", "dedup_key"])
    )
    frame = deduplicate(
        frame, subset=["dedup_key"], prefer=["completeness", "metadata_last_modified"]
    )

    frame["research_id"] = frame["handle"]
    frame["university"] = university
    frame["publication_year"] = frame["parsed_year"].astype("Int64")
    frame["publication_date"] = frame["parsed_date"].map(format_date)
    frame["research_field"] = pd.NA
    frame["tech_category"] = pd.NA
    frame["url"] = frame["handle"]
    frame["source"] = source_label

    return to_schema(frame)


# --------------------------------------------------------------------------
# Crossref
# --------------------------------------------------------------------------
def _crossref_authors(authors) -> str | pd.NA:
    if not isinstance(authors, list):
        return pd.NA

    names = [
        f"{author.get('given', '')} {author.get('family', '')}".strip()
        for author in authors
    ]
    names = [name for name in names if name]
    return "; ".join(names) if names else pd.NA


def _first_item(value):
    return value[0] if isinstance(value, list) and value else pd.NA


def _crossref_date(date_parts):
    """Return ``(year, full_date)``; the date stays missing unless Y-M-D is given."""
    if not isinstance(date_parts, list) or not date_parts:
        return pd.NA, pd.NA

    parts = date_parts[0]
    year = parts[0] if len(parts) >= 1 else pd.NA

    if len(parts) >= 3:
        return year, f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
    return year, pd.NA


def clean_kaust_crossref(raw: pd.DataFrame, university: str = "KAUST",
                         source_label: str = "Crossref") -> pd.DataFrame:
    """Clean the flattened Crossref records and map them to the common schema."""
    frame = pd.DataFrame(index=raw.index)

    dates = raw["published.date-parts"].map(_crossref_date)
    frame["publication_year"] = pd.array(
        [value[0] for value in dates], dtype="Int64"
    )
    frame["publication_date"] = [value[1] for value in dates]

    frame["title"] = raw["title"].map(_first_item).map(clean_markup)
    frame["authors"] = raw["author"].map(_crossref_authors)
    frame["journal"] = raw["container-title"].map(_first_item)
    frame["abstract"] = raw["abstract"].map(clean_markup) if "abstract" in raw else pd.NA

    frame["doi"] = raw["DOI"].map(normalize_doi)
    frame["url"] = raw["URL"].astype("string").str.strip()
    frame["research_id"] = frame["doi"]
    frame["university"] = university
    frame["research_field"] = pd.NA
    frame["tech_category"] = pd.NA
    frame["source"] = source_label

    return to_schema(frame)


# --------------------------------------------------------------------------
# KFUPM Pure
# --------------------------------------------------------------------------
def clean_kfupm_pure(raw: pd.DataFrame, department: str, university: str,
                     source_label: str, min_year: int, max_year: int,
                     excluded_genres: list[str] | None = None,
                     require_doi: bool = True) -> pd.DataFrame:
    """Keep one department's Pure records and map them to the common schema.

    The department is read from the Pure organisational unit
    (``name type="corporate"``), never from the free-text affiliation, which
    also contains departments of other universities.
    """
    excluded_genres = excluded_genres or []

    frame = raw[
        raw["organisational_units"].map(lambda units: department in (units or []))
    ].copy()

    frame["research_id"] = "KFUPM_" + frame["uuid"].astype("string")
    frame = frame.drop_duplicates("research_id")

    frame["university"] = university
    frame["publication_year"] = pd.array(
        [
            int(value[:4]) if isinstance(value, str) and value[:4].isdigit() else pd.NA
            for value in frame["date_issued"]
        ],
        dtype="Int64",
    )
    frame["publication_date"] = frame["date_issued"].map(
        lambda value: format_date(parse_partial_date(value, complete_only=True))
    )
    frame["research_field"] = frame["topics"]
    frame["tech_category"] = pd.NA
    frame["doi"] = frame["doi_raw"].map(normalize_doi)
    frame["source"] = source_label

    frame = frame[frame["publication_year"].between(min_year, max_year)]
    if require_doi:
        frame = frame[frame["doi"].notna()]
    if excluded_genres:
        frame = frame[~frame["genre"].isin(excluded_genres)]

    return to_schema(frame)


# --------------------------------------------------------------------------
# KSU annual open data
# --------------------------------------------------------------------------
def clean_ksu(raw: pd.DataFrame, year: int, dataset_url: str,
              university: str = "KSU", source_label: str = "KSU") -> pd.DataFrame:
    """Map KSU records to the common schema.

    Two documented KSU rules:

    * ``publication_year`` is the year of the annual dataset file, because the
      records themselves carry no date.
    * ``url`` is the annual dataset download link, not a per-paper page. The
      KSU files do not publish one.
    """
    frame = pd.DataFrame(index=raw.index)

    def text(column: str) -> pd.Series:
        if column not in raw.columns:
            return pd.Series(pd.NA, index=raw.index, dtype="string")
        return raw[column].astype("string").str.strip().replace("", pd.NA)

    frame["research_id"] = [
        f"KSU_{year}_{index}" for index in raw["source_row_index"]
    ]
    frame["university"] = university
    frame["title"] = text("Article Title")
    frame["authors"] = text("Authors")
    frame["publication_year"] = pd.array([year] * len(raw), dtype="Int64")
    frame["publication_date"] = pd.NA
    frame["abstract"] = text("Abstract")
    frame["research_field"] = pd.NA
    frame["tech_category"] = pd.NA
    frame["journal"] = text("Source Title")
    frame["doi"] = text("DOI").map(normalize_doi)
    frame["url"] = dataset_url.format(year=year)
    frame["source"] = source_label

    return to_schema(frame)


def apply_manual_enrichment(frame: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Fill reviewed DOIs and abstracts from a curated enrichment file.

    Only missing values are filled; an existing value is never overwritten and
    a conflicting DOI raises an error. Returns the enriched frame and a log of
    what was changed, so the enrichment stays auditable.
    """
    result = frame.copy()
    log: list[dict] = []

    decisions = json.loads(Path(path).read_text(encoding="utf-8"))

    for decision in decisions:
        matches = result.index[result["research_id"] == decision["research_id"]]
        if len(matches) == 0:
            continue

        row = matches[0]
        added: list[str] = []

        doi = normalize_doi(decision.get("doi"))
        if not pd.isna(doi):
            current = result.at[row, "doi"]
            if pd.isna(current):
                result.at[row, "doi"] = doi
                added.append("doi")
            elif str(current).lower() != doi:
                raise ValueError(
                    f"Conflicting DOI for {decision['research_id']}: {current} != {doi}"
                )

        abstract = decision.get("abstract")
        if abstract and pd.isna(result.at[row, "abstract"]):
            result.at[row, "abstract"] = abstract
            added.append("abstract")

        if added:
            log.append({
                "research_id": decision["research_id"],
                "fields_added": added,
                "evidence": decision.get("evidence"),
            })

    return result, log
