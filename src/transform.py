"""Join, technology filtering, and derived transformation rules."""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from src.schema import SCHEMA_COLUMNS

TECHNOLOGY_TERMS = [
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural network",
    "neural networks",
    "multilayer perceptron",
    "random forest",
    "computer vision",
    "natural language processing",
    "large language model",
    "large language models",
    "generative ai",
    "cybersecurity",
    "cyber security",
    "information security",
    "intrusion detection",
    "cryptography",
    "blockchain",
    "software engineering",
    "internet of things",
    "iot",
    "cloud computing",
    "edge computing",
    "wireless network",
    "wireless networks",
    "robotics",
    "robot",
    "robots",
    "data mining",
    "big data",
    "computer science",
    "ann modeling",
    "ann modelling",
]

EXCLUDED_PHRASES = ["computer vision syndrome"]
DASHES = r"[-\u2010\u2011\u2012\u2013\u2014\u2212_]+"


def normalize_text(value, excluded_phrases: list[str] | None = None) -> str:
    """Normalize case, dashes, whitespace, and known false-positive phrases."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""

    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(DASHES, " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    phrases = EXCLUDED_PHRASES if excluded_phrases is None else excluded_phrases
    for phrase in phrases:
        normalized_phrase = unicodedata.normalize("NFKC", str(phrase)).casefold()
        normalized_phrase = re.sub(DASHES, " ", normalized_phrase)
        normalized_phrase = re.sub(r"\s+", " ", normalized_phrase).strip()
        text = re.sub(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def build_patterns(terms: list[str] | None = None) -> dict[str, re.Pattern]:
    """Compile whole-word patterns so fragments such as ``iot`` in ``riot`` do not match."""
    output: dict[str, re.Pattern] = {}
    for term in terms or TECHNOLOGY_TERMS:
        normalized = normalize_text(term, excluded_phrases=[])
        output[normalized] = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")
    return output


def find_matches(
    record,
    fields: list[str] | None = None,
    patterns: dict[str, re.Pattern] | None = None,
    excluded_phrases: list[str] | None = None,
) -> list[str]:
    """Return all technology terms found in the requested fields."""
    fields = fields or ["title", "abstract"]
    patterns = patterns or build_patterns()

    searchable_values = [
        normalize_text(record.get(field), excluded_phrases=excluded_phrases)
        for field in fields
    ]

    matches = []
    for term, pattern in patterns.items():
        if any(pattern.search(value) for value in searchable_values):
            matches.append(term)
    return matches


def filter_technology(
    frame: pd.DataFrame,
    fields: list[str] | None = None,
    terms: list[str] | None = None,
    excluded_phrases: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split schema-shaped records into technology candidates and non-matches."""
    fields = fields or ["title", "abstract"]
    patterns = build_patterns(terms)

    matches = frame.apply(
        lambda row: find_matches(
            row,
            fields=fields,
            patterns=patterns,
            excluded_phrases=excluded_phrases,
        ),
        axis=1,
    )
    if matches.empty:
        matches = pd.Series([], dtype="object", index=frame.index)

    keep = matches.map(bool)

    review = frame[["research_id", "university", "title"]].copy()
    review["matched_terms"] = matches.map("; ".join)
    review["selected"] = keep

    return frame[keep].copy(), frame[~keep].copy(), review


def filter_raw_records(
    frame: pd.DataFrame,
    fields: list[str],
    terms: list[str] | None = None,
    excluded_phrases: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Apply the shared technology matcher to raw source columns."""
    patterns = build_patterns(terms)

    matches = frame.apply(
        lambda row: find_matches(
            row,
            fields=fields,
            patterns=patterns,
            excluded_phrases=excluded_phrases,
        ),
        axis=1,
    )
    if matches.empty:
        matches = pd.Series([], dtype="object", index=frame.index)

    return frame[matches.map(bool)].copy(), matches


def combine_sources(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Stack validated datasets after enforcing the common schema."""
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=SCHEMA_COLUMNS)

    missing_by_frame = [
        [column for column in SCHEMA_COLUMNS if column not in frame.columns]
        for frame in frames
    ]
    if any(missing_by_frame):
        raise ValueError(f"Cannot combine frames with missing schema columns: {missing_by_frame}")

    combined = pd.concat([frame[SCHEMA_COLUMNS] for frame in frames], ignore_index=True)

    duplicates = combined["research_id"].duplicated(keep=False)
    if duplicates.any():
        duplicate_count = int(duplicates.sum())
        raise ValueError(f"{duplicate_count} rows have duplicate research_id values after the join")

    return combined


def shared_doi_report(frame: pd.DataFrame) -> pd.DataFrame:
    """List DOI values that occur under more than one university."""
    present = frame[frame["doi"].notna()].copy()
    counts = present.groupby("doi")["university"].nunique()
    shared = counts[counts > 1].index

    return (
        present[present["doi"].isin(shared)][
            ["doi", "university", "research_id", "title", "publication_year"]
        ]
        .sort_values(["doi", "university"])
        .reset_index(drop=True)
    )


def apply_transformations(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the agreed derived columns R1-R3."""
    result = frame.copy()

    result["publication_year"] = pd.to_numeric(
        result["publication_year"], errors="coerce"
    ).astype("Int64")

    result["has_doi"] = result["doi"].notna() & result["doi"].astype("string").str.strip().ne("")

    result["abstract_word_count"] = (
        result["abstract"].fillna("").astype("string").str.split().str.len().astype("Int64")
    )

    return result


def transformation_rules() -> pd.DataFrame:
    """Return the transformation-rule table used by the notebooks/README."""
    return pd.DataFrame(
        [
            ["R1", "Convert publication_year to a nullable integer", "publication_year", "publication_year"],
            ["R2", "Flag whether a DOI is available", "doi", "has_doi"],
            ["R3", "Count the words in each abstract", "abstract", "abstract_word_count"],
            [
                "R4",
                "Keep records matching a technology keyword using whole-word matching",
                "title, abstract, source-specific author keywords",
                "filtered rows",
            ],
        ],
        columns=["rule_id", "description", "input_columns", "output_column"],
    )
