"""OpenAlex source: harvest and clean works for the additional universities.

One row represents **one university's participation in one paper**. A paper
co-authored by two included universities therefore appears once per university
with a distinct ``research_id``. Counting all Saudi papers means counting
unique ``doi`` values, not rows; ``transform.shared_doi_report`` lists the
overlaps.

``publication_date`` is always left empty: OpenAlex supplies an approximate
date (often the first of January) when the publisher only reported a year, and
the project does not store invented month/day values.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from src.clean import normalize_doi, to_schema
from src.schema import SCHEMA_COLUMNS

API_URL = "https://api.openalex.org/works"


def rebuild_abstract(inverted_index) -> str | None:
    """Rebuild abstract text from the OpenAlex inverted index."""
    if not isinstance(inverted_index, dict) or not inverted_index:
        return None

    positions = [
        (position, word)
        for word, spots in inverted_index.items()
        for position in (spots or [])
    ]
    return " ".join(word for _, word in sorted(positions)) or None


def build_filter(
    ror: str,
    from_date: str,
    to_date: str,
    field_id: str | None = None,
) -> str:
    """Return the OpenAlex ``filter`` value used for one university."""
    filters = [
        f"institutions.ror:{ror}",
        f"from_publication_date:{from_date}",
        f"to_publication_date:{to_date}",
        "has_doi:true",
    ]
    if field_id:
        filters.append(f"primary_topic.field.id:{field_id}")
    return ",".join(filters)


def fetch_openalex(
    ror: str,
    from_date: str,
    to_date: str,
    field_id: str | None = None,
    mailto: str | None = None,
    per_page: int = 200,
    pause: float = 0.5,
    output_path: Path | None = None,
) -> list[dict]:
    """Download every OpenAlex work for one institution using cursor paging."""
    query = build_filter(ror, from_date, to_date, field_id)
    cursor = "*"
    works: list[dict] = []

    while cursor:
        params = {"filter": query, "per-page": per_page, "cursor": cursor}
        if mailto:
            params["mailto"] = mailto

        response = requests.get(API_URL, params=params, timeout=120)
        response.raise_for_status()
        payload = response.json()

        batch = payload.get("results", [])
        works.extend(batch)

        cursor = payload.get("meta", {}).get("next_cursor")
        if not batch:
            break
        time.sleep(pause)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(works, ensure_ascii=False), encoding="utf-8")

    return works


def read_openalex(path: Path) -> list[dict]:
    """Read one saved OpenAlex snapshot file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _authors(work: dict) -> str | None:
    names = [
        (authorship.get("author") or {}).get("display_name")
        for authorship in work.get("authorships") or []
    ]
    names = [name for name in names if name]
    return "; ".join(names) or None


def clean_openalex(
    works: list[dict],
    university: str,
    ror: str,
    source_label: str,
    min_year: int,
    max_year: int,
) -> pd.DataFrame:
    """Map OpenAlex works to the shared schema for one university.

    Records with a missing title or DOI are kept so schema validation can
    report them; only the project year range is applied here.
    """
    rows = []

    for work in works:
        work_id = str(work.get("id") or "").rsplit("/", 1)[-1]
        location = work.get("primary_location") or {}
        venue = location.get("source") or {}
        topic = work.get("primary_topic") or {}

        rows.append(
            {
                "research_id": f"OA_{work_id}_{ror}" if work_id else pd.NA,
                "university": university,
                "title": work.get("title"),
                "authors": _authors(work),
                "publication_year": work.get("publication_year"),
                "publication_date": pd.NA,
                "abstract": rebuild_abstract(work.get("abstract_inverted_index")),
                "research_field": (topic.get("field") or {}).get("display_name"),
                "tech_category": pd.NA,
                "journal": venue.get("display_name"),
                "doi": normalize_doi(work.get("doi")),
                "url": work.get("id"),
                "source": source_label,
            }
        )

    frame = pd.DataFrame(rows, columns=SCHEMA_COLUMNS)

    years = pd.to_numeric(frame["publication_year"], errors="coerce").astype("Int64")
    frame["publication_year"] = years
    frame = frame[years.between(min_year, max_year).fillna(False)]
    frame = frame.drop_duplicates("research_id")

    return to_schema(frame)


def universities(config: dict) -> list[dict]:
    """Return the configured OpenAlex universities."""
    return list(config.get("sources", {}).get("openalex", {}).get("universities", []))


def university_codes(config: dict) -> list[str]:
    """Return only the university codes, in configuration order."""
    return [entry["code"] for entry in universities(config)]
