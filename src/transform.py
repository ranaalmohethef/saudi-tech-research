"""Transformation: technology filter, join across universities, derived columns.

This is the single implementation of the technology filter. The notebooks and
``main.py`` both call :func:`filter_technology`, so the team cannot end up with
two different keyword rules.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from src.schema import SCHEMA_COLUMNS

# Keywords also live in config.yaml; this list is the fallback default.
TECHNOLOGY_TERMS = [
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "neural networks", "multilayer perceptron",
    "random forest", "computer vision", "natural language processing",
    "large language model", "large language models", "generative ai",
    "cybersecurity", "cyber security", "information security",
    "intrusion detection", "cryptography", "blockchain",
    "software engineering", "internet of things", "iot",
    "cloud computing", "edge computing",
    "wireless network", "wireless networks",
    "robotics", "robot", "robots",
    "data mining", "big data", "computer science",
    "ann modeling", "ann modelling",
]

# "Computer vision syndrome" is an eye condition, not computer vision research.
EXCLUDED_PHRASES = ["computer vision syndrome"]

DASHES = r"[-\u2010\u2011\u2012\u2013\u2014\u2212_]+"


def normalize_text(value) -> str:
    """Lowercase the text and normalize dashes, spaces and excluded phrases."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""

    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(DASHES, " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    for phrase in EXCLUDED_PHRASES:
        text = re.sub(rf"(?<!\w){re.escape(phrase)}(?!\w)", " ", text)

    return text


def build_patterns(terms: list[str] | None = None) -> dict[str, re.Pattern]:
    """Compile one whole-word pattern per term.

    Whole-word matching is what stops ``iot`` matching "riot" and ``ai``-style
    fragments matching inside unrelated words.
    """
    return {
        term: re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")
        for term in (terms or TECHNOLOGY_TERMS)
    }


def find_matches(record, fields: list[str] | None = None,
                 patterns: dict[str, re.Pattern] | None = None) -> list[str]:
    """Return every technology term found in the record's searchable fields."""
    fields = fields or ["title", "abstract"]
    patterns = patterns or build_patterns()

    haystack = " | ".join(normalize_text(record.get(field)) for field in fields)
    return [term for term, pattern in patterns.items() if pattern.search(haystack)]


def filter_technology(frame: pd.DataFrame, fields: list[str] | None = None,
                      terms: list[str] | None = None
                      ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split a dataset into technology candidates and the rest.

    Returns ``(selected, excluded, review)``. ``review`` lists every record
    with the terms it matched, so the filter can be checked by hand instead of
    being trusted blindly.
    """
    fields = fields or ["title", "abstract"]
    patterns = build_patterns(terms)

    matches = frame.apply(
        lambda row: find_matches(row, fields=fields, patterns=patterns), axis=1
    )
    if matches.empty:
        matches = pd.Series([], dtype="object", index=frame.index)

    keep = matches.map(bool)

    review = frame[["research_id", "university", "title"]].copy()
    review["matched_terms"] = matches.map("; ".join)
    review["selected"] = keep

    return frame[keep].copy(), frame[~keep].copy(), review


def filter_raw_records(frame: pd.DataFrame, fields: list[str],
                       terms: list[str] | None = None
                       ) -> tuple[pd.DataFrame, pd.Series]:
    """Apply the technology filter to raw columns, before the schema mapping.

    Some sources keep the useful text outside the common schema: KSU publishes
    author keywords but no abstract, so its scope filter has to run on the raw
    fields. The row order is preserved, because the KSU ``research_id``
    contains the record's position in the annual file.

    Returns the selected rows and the matched terms for every input row.
    """
    patterns = build_patterns(terms)

    matches = frame.apply(
        lambda row: find_matches(row, fields=fields, patterns=patterns), axis=1
    )
    if matches.empty:
        matches = pd.Series([], dtype="object", index=frame.index)

    return frame[matches.map(bool)].copy(), matches


def combine_sources(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Row-wise join of validated datasets that already share the schema.

    The join key is ``research_id``: it must stay unique after the join, so a
    clash raises instead of being silently deduplicated.
    """
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=SCHEMA_COLUMNS)

    combined = pd.concat(
        [frame[SCHEMA_COLUMNS] for frame in frames], ignore_index=True
    )

    duplicates = combined["research_id"].duplicated().sum()
    if duplicates:
        raise ValueError(f"{duplicates} duplicate research_id values after the join")

    return combined


def shared_doi_report(frame: pd.DataFrame) -> pd.DataFrame:
    """List DOIs that appear under more than one university.

    A co-authored paper legitimately appears in two university datasets. The
    records are kept; this report exists so the duplication is visible and the
    team can decide how to count it.
    """
    present = frame[frame["doi"].notna()]
    counts = present.groupby("doi")["university"].nunique()
    shared = counts[counts > 1].index

    return (
        present[present["doi"].isin(shared)]
        [["doi", "university", "research_id", "title", "publication_year"]]
        .sort_values(["doi", "university"])
        .reset_index(drop=True)
    )


def apply_transformations(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the agreed derived columns.

    * R1 ``publication_year`` as a nullable integer
    * R2 ``has_doi`` flag
    * R3 ``abstract_word_count``
    """
    result = frame.copy()

    result["publication_year"] = pd.to_numeric(
        result["publication_year"], errors="coerce"
    ).astype("Int64")

    result["has_doi"] = result["doi"].notna() & result["doi"].astype(
        "string"
    ).str.strip().ne("")

    result["abstract_word_count"] = (
        result["abstract"].fillna("").astype("string").str.split().str.len()
    )

    return result


def transformation_rules() -> pd.DataFrame:
    """Document the transformation rules for the README and the notebooks."""
    return pd.DataFrame(
        [
            ["R1", "Convert publication_year to a nullable integer",
             "publication_year", "publication_year"],
            ["R2", "Flag whether a DOI is available", "doi", "has_doi"],
            ["R3", "Count the words in each abstract", "abstract",
             "abstract_word_count"],
            ["R4", "Keep records matching a technology keyword (whole words)",
             "title, abstract", "filtered rows"],
        ],
        columns=["rule_id", "description", "input_columns", "output_column"],
    )
