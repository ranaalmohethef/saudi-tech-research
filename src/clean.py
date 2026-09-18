"""Cleaning functions that map raw sources to the shared 13-column schema.

Cleaning standardizes values but does not silently remove records because a
required field is missing. Required-field decisions belong to schema
validation so rejected records remain auditable.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd

from src.schema import MISSING_MARKERS, SCHEMA_COLUMNS

DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
DOI_PREFIX_PATTERN = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE
)


def snake_case_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to snake_case."""
    result = frame.copy()
    result.columns = (
        result.columns.str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return result


def strip_and_blank_to_na(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim text and convert blank/textual missing markers to ``pd.NA``."""
    result = frame.copy()

    for column in result.columns:
        if pd.api.types.is_string_dtype(result[column]) or result[column].dtype == object:
            result[column] = result[column].astype("string").str.strip()
            marker_mask = result[column].str.casefold().isin(MISSING_MARKERS)
            result.loc[marker_mask, column] = pd.NA

    return result


def clean_markup(value) -> str | pd.NA:
    """Remove HTML/JATS tags and collapse whitespace."""
    if value is None or pd.isna(value):
        return pd.NA

    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\\n", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or pd.NA


def normalize_doi(value) -> str | pd.NA:
    """Return a bare lowercase DOI or ``pd.NA`` when no DOI is present."""
    if value is None or pd.isna(value):
        return pd.NA

    text = DOI_PREFIX_PATTERN.sub("", str(value).strip())
    match = DOI_PATTERN.search(text)
    if not match:
        return pd.NA

    return match.group(0).rstrip(".").lower()


def parse_partial_date(value, complete_only: bool = True):
    """Return a date only when year, month, and day are known.

    The project does not invent a month or day. ``YYYY`` and ``YYYY-MM``
    therefore return ``None``. ISO timestamps are accepted because they still
    contain a complete calendar date.

    ``complete_only`` is retained for backward compatibility; partial dates
    are intentionally never completed even if callers pass ``False``.
    """
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
        return _to_date(text, "%Y-%m-%d")

    if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
        return _to_date(text[:10], "%Y-%m-%d")

    return None


def extract_year(value):
    """Extract a leading four-digit year without inventing a full date."""
    if value is None or pd.isna(value):
        return pd.NA

    match = re.match(r"^(\d{4})", str(value).strip())
    return int(match.group(1)) if match else pd.NA


def _to_date(text: str, fmt: str):
    parsed = pd.to_datetime(text, format=fmt, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def format_date(value) -> str | pd.NA:
    """Format a complete date as ``YYYY-MM-DD`` text."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NA
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def completeness_score(frame: pd.DataFrame) -> pd.Series:
    """Count populated fields per row."""
    return frame.notna().sum(axis=1)


def deduplicate(frame: pd.DataFrame, subset: list[str], prefer: list[str]) -> pd.DataFrame:
    """Keep one row per key, preferring more complete/newer rows."""
    ordered = frame.sort_values(prefer, ascending=[False] * len(prefer))
    return ordered.drop_duplicates(subset=subset, keep="first")


def to_schema(frame: pd.DataFrame) -> pd.DataFrame:
    """Return exactly the shared schema columns in the agreed order."""
    result = frame.copy()
    for column in SCHEMA_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result[SCHEMA_COLUMNS].reset_index(drop=True)


def clean_kaust_repository(
    raw: pd.DataFrame,
    year: int,
    university: str = "KAUST",
    source_label: str = "KAUST Repository",
) -> pd.DataFrame:
    """Clean the KAUST repository export for one target year."""
    frame = strip_and_blank_to_na(snake_case_columns(raw))

    frame["parsed_year"] = pd.array(frame["publication_date"].map(extract_year), dtype="Int64")
    frame["parsed_date"] = frame["publication_date"].map(parse_partial_date)
    frame = frame[frame["parsed_year"] == year].copy()

    frame["doi"] = frame["doi"].map(normalize_doi)

    frame["dedup_key"] = [
        handle if pd.isna(doi) else f"{doi}|{title}|{kind}|{date}"
        for doi, handle, title, kind, date in zip(
            frame["doi"],
            frame["handle"],
            frame["title"],
            frame["type"],
            frame["parsed_date"],
        )
    ]
    frame["completeness"] = completeness_score(
        frame.drop(columns=["parsed_date", "parsed_year", "dedup_key"])
    )
    frame = deduplicate(
        frame,
        subset=["dedup_key"],
        prefer=["completeness", "metadata_last_modified"],
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
    """Return ``(year, full_date)`` without completing partial dates."""
    if not isinstance(date_parts, list) or not date_parts:
        return pd.NA, pd.NA

    parts = date_parts[0]
    year = parts[0] if len(parts) >= 1 else pd.NA

    if len(parts) >= 3:
        try:
            date_value = pd.Timestamp(year=parts[0], month=parts[1], day=parts[2])
        except (TypeError, ValueError):
            return year, pd.NA
        return year, date_value.strftime("%Y-%m-%d")

    return year, pd.NA


def clean_kaust_crossref(
    raw: pd.DataFrame,
    university: str = "KAUST",
    source_label: str = "Crossref",
    min_year: int | None = None,
    max_year: int | None = None,
) -> pd.DataFrame:
    """Clean flattened Crossref records and map them to the common schema."""
    frame = pd.DataFrame(index=raw.index)

    dates = raw["published.date-parts"].map(_crossref_date)
    frame["publication_year"] = pd.array([value[0] for value in dates], dtype="Int64")
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

    if min_year is not None:
        frame = frame[frame["publication_year"] >= min_year]
    if max_year is not None:
        frame = frame[frame["publication_year"] <= max_year]

    return to_schema(frame)


def clean_kfupm_pure(
    raw: pd.DataFrame,
    department: str,
    university: str,
    source_label: str,
    min_year: int,
    max_year: int,
    excluded_genres: list[str] | None = None,
) -> pd.DataFrame:
    """Filter KFUPM Pure to the target department and map to the schema.

    Records missing DOI are kept here and are rejected later by schema
    validation. This preserves the audit trail instead of silently dropping
    required-field failures during cleaning.
    """
    excluded_genres = excluded_genres or []

    frame = raw[
        raw["organisational_units"].map(
            lambda units: isinstance(units, list) and department in units
        )
    ].copy()

    frame["research_id"] = "KFUPM_" + frame["uuid"].astype("string")
    frame = frame.drop_duplicates("research_id")

    frame["university"] = university
    frame["publication_year"] = pd.array(frame["date_issued"].map(extract_year), dtype="Int64")
    frame["publication_date"] = frame["date_issued"].map(
        lambda value: format_date(parse_partial_date(value))
    )
    frame["research_field"] = frame["topics"]
    frame["tech_category"] = pd.NA
    frame["doi"] = frame["doi_raw"].map(normalize_doi)
    frame["source"] = source_label

    frame = frame[frame["publication_year"].between(min_year, max_year)]
    if excluded_genres:
        frame = frame[~frame["genre"].isin(excluded_genres)]

    return to_schema(frame)


def clean_ksu(
    raw: pd.DataFrame,
    year: int,
    dataset_url: str,
    university: str = "KSU",
    source_label: str = "KSU",
) -> pd.DataFrame:
    """Map one KSU annual file to the common schema."""
    frame = pd.DataFrame(index=raw.index)

    def text(column: str) -> pd.Series:
        if column not in raw.columns:
            return pd.Series(pd.NA, index=raw.index, dtype="string")
        values = raw[column].astype("string").str.strip()
        return values.mask(values.str.casefold().isin(MISSING_MARKERS), pd.NA)

    frame["research_id"] = [f"KSU_{year}_{index}" for index in raw["source_row_index"]]
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


def apply_manual_enrichment(
    frame: pd.DataFrame,
    path: Path,
) -> tuple[pd.DataFrame, list[dict]]:
    """Fill only reviewed missing DOI/abstract values from a curated file."""
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
            log.append(
                {
                    "research_id": decision["research_id"],
                    "fields_added": added,
                    "evidence": decision.get("evidence"),
                }
            )

    return result, log
