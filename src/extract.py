"""Extraction: read the raw source files exactly as they were downloaded.

Nothing in this module changes values. Reading is separated from cleaning so
that the raw layer stays reproducible: the functions below only parse files
that already live under ``data/raw`` (KFUPM 2025 is read from ``data/interim``
because the downloaded JSON needed a documented repair).

The two ``fetch_*`` helpers are the network calls used by
``notebooks/01_extract.ipynb``; ``main.py`` never calls them, so the pipeline
can be re-run offline from the saved raw files.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

MODS = "{http://www.loc.gov/mods/v3}"
OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}


# --------------------------------------------------------------------------
# KAUST repository export (CSV)
# --------------------------------------------------------------------------
def read_kaust_repository(path: Path) -> pd.DataFrame:
    """Read the KAUST repository CSV export with every column as text."""
    return pd.read_csv(path, dtype="string")


# --------------------------------------------------------------------------
# Crossref (JSON pages)
# --------------------------------------------------------------------------
def read_crossref_pages(paths: list[Path]) -> pd.DataFrame:
    """Flatten the ``message.items`` array of every saved Crossref page."""
    records: list[dict] = []

    for path in sorted(paths):
        with open(path, "r", encoding="utf-8") as handle:
            page = json.load(handle)
        records.extend(page["message"]["items"])

    return pd.json_normalize(records)


def fetch_crossref(ror_id: str, from_year: int, until_year: int,
                   mailto: str, rows: int = 100,
                   output_dir: Path | None = None) -> list[dict]:
    """Download Crossref works for one ROR affiliation (cursor paging).

    Used by the extract notebook. Each page can be saved unchanged to
    ``output_dir`` so the raw layer stays reproducible.
    """
    base = "https://api.crossref.org/works"
    cursor = "*"
    page = 1
    items: list[dict] = []

    while True:
        params = {
            "filter": (
                f"ror-id:{ror_id},"
                f"from-pub-date:{from_year}-01-01,"
                f"until-pub-date:{until_year}-12-31"
            ),
            "rows": rows,
            "cursor": cursor,
            "mailto": mailto,
        }
        response = requests.get(base, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()

        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"crossref_page_{page}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

        batch = payload["message"]["items"]
        items.extend(batch)

        cursor = payload["message"].get("next-cursor")
        if not batch or not cursor:
            return items

        page += 1
        time.sleep(1)


# --------------------------------------------------------------------------
# KFUPM Pure (OAI-PMH / MODS XML)
# --------------------------------------------------------------------------
def _mods_text(element) -> str | None:
    """Return an element's text with whitespace collapsed."""
    if element is None:
        return None
    value = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
    return value or None


def parse_pure_record(mods) -> dict:
    """Convert one MODS record into a flat dictionary (no filtering here)."""
    identifiers: dict[str, str | None] = {}
    for identifier in mods.findall(f"{MODS}identifier"):
        identifiers.setdefault(identifier.get("type"), _mods_text(identifier))

    title_info = next(
        (t for t in mods.findall(f"{MODS}titleInfo") if t.get("type") is None), None
    )
    title = _mods_text(title_info.find(f"{MODS}title")) if title_info is not None else None
    subtitle = _mods_text(title_info.find(f"{MODS}subTitle")) if title_info is not None else None
    if title and subtitle:
        title = f"{title}: {subtitle}"

    authors = []
    for name in mods.findall(f"{MODS}name[@type='personal']"):
        given = " ".join(
            filter(None, (_mods_text(p) for p in name.findall(f"{MODS}namePart[@type='given']")))
        )
        family = " ".join(
            filter(None, (_mods_text(p) for p in name.findall(f"{MODS}namePart[@type='family']")))
        )
        full_name = f"{given} {family}".strip() or _mods_text(name.find(f"{MODS}namePart"))
        if full_name:
            authors.append(full_name)

    organisational_units = [
        _mods_text(part)
        for name in mods.findall(f"{MODS}name[@type='corporate']")
        for part in name.findall(f"{MODS}namePart")
    ]

    topics = [_mods_text(topic) for topic in mods.findall(f".//{MODS}subject/{MODS}topic")]

    url = identifiers.get("uri")
    if not (url and url.startswith(("http://", "https://"))):
        url = _mods_text(mods.find(f".//{MODS}location/{MODS}url"))

    return {
        "uuid": identifiers.get("pure/uuid"),
        "title": title,
        "authors": "; ".join(authors) or None,
        "date_issued": _mods_text(mods.find(f".//{MODS}originInfo/{MODS}dateIssued")),
        "abstract": _mods_text(mods.find(f"{MODS}abstract")),
        "topics": "; ".join(topic for topic in topics if topic) or None,
        "journal": _mods_text(
            mods.find(f"{MODS}relatedItem[@type='host']/{MODS}titleInfo/{MODS}title")
        ),
        "doi_raw": identifiers.get("doi"),
        "url": url,
        "genre": _mods_text(mods.find(f"{MODS}genre")),
        "organisational_units": organisational_units,
    }


def read_kfupm_pure(directory: Path) -> pd.DataFrame:
    """Read every harvested OAI-PMH page and return one row per record."""
    rows = [
        parse_pure_record(mods)
        for path in sorted(Path(directory).glob("*.xml"))
        for mods in ET.parse(path).getroot().iter(f"{MODS}mods")
    ]
    return pd.DataFrame(rows)


def fetch_pure_pages(base_url: str, year: int, output_dir: Path,
                     metadata_prefix: str = "mods", pause: float = 1.5) -> int:
    """Harvest one year set from an OAI-PMH endpoint, saving raw XML pages."""
    output_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "verb": "ListRecords",
        "metadataPrefix": metadata_prefix,
        "set": f"publications:year{year}",
    }
    page = 0

    while True:
        response = requests.get(base_url, params=params, timeout=120)
        response.raise_for_status()
        (output_dir / f"year{year}_page{page:04d}.xml").write_bytes(response.content)

        token = ET.fromstring(response.content).find(".//oai:resumptionToken", OAI_NS)
        if token is None or not (token.text or "").strip():
            return page + 1

        page += 1
        params = {"verb": "ListRecords", "resumptionToken": token.text.strip()}
        time.sleep(pause)


# --------------------------------------------------------------------------
# KSU annual open-data files (JSON)
# --------------------------------------------------------------------------
def read_ksu_year(path: Path, year: int) -> pd.DataFrame:
    """Read one KSU annual JSON file and keep the original row order.

    ``source_row_index`` is the record's position in the annual file. It is
    part of the KSU ``research_id``, so it must never be re-sorted.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    records = json.loads(text)

    frame = pd.DataFrame(records)
    frame["source_file_year"] = year
    frame["source_row_index"] = range(len(frame))
    return frame
