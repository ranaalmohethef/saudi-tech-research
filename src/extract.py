"""Read the frozen raw source files and provide optional download helpers."""

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


def read_kaust_repository(path: Path) -> pd.DataFrame:
    """Read the KAUST repository CSV with every column as text."""
    return pd.read_csv(path, dtype="string")


def read_crossref_pages(paths: list[Path]) -> pd.DataFrame:
    """Flatten ``message.items`` from saved Crossref pages."""
    records: list[dict] = []

    for path in sorted(paths):
        with open(path, "r", encoding="utf-8") as handle:
            page = json.load(handle)
        records.extend(page["message"]["items"])

    return pd.json_normalize(records)


def fetch_crossref(
    ror_id: str,
    from_year: int,
    until_year: int,
    mailto: str | None = None,
    rows: int = 100,
    output_dir: Path | None = None,
) -> list[dict]:
    """Download Crossref works for one ROR affiliation using cursor paging."""
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
        }
        if mailto:
            params["mailto"] = mailto

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


def _mods_text(element) -> str | None:
    if element is None:
        return None
    value = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
    return value or None


def parse_pure_record(mods) -> dict:
    """Convert one MODS record into a flat dictionary without filtering."""
    identifiers: dict[str, str | None] = {}
    for identifier in mods.findall(f"{MODS}identifier"):
        identifiers.setdefault(identifier.get("type"), _mods_text(identifier))

    title_info = next(
        (item for item in mods.findall(f"{MODS}titleInfo") if item.get("type") is None),
        None,
    )
    title = _mods_text(title_info.find(f"{MODS}title")) if title_info is not None else None
    subtitle = (
        _mods_text(title_info.find(f"{MODS}subTitle")) if title_info is not None else None
    )
    if title and subtitle:
        title = f"{title}: {subtitle}"

    authors = []
    for name in mods.findall(f"{MODS}name[@type='personal']"):
        given = " ".join(
            filter(
                None,
                (_mods_text(part) for part in name.findall(f"{MODS}namePart[@type='given']")),
            )
        )
        family = " ".join(
            filter(
                None,
                (_mods_text(part) for part in name.findall(f"{MODS}namePart[@type='family']")),
            )
        )
        full_name = f"{given} {family}".strip() or _mods_text(name.find(f"{MODS}namePart"))
        if full_name:
            authors.append(full_name)

    organisational_units = [
        _mods_text(part)
        for name in mods.findall(f"{MODS}name[@type='corporate']")
        for part in name.findall(f"{MODS}namePart")
        if _mods_text(part)
    ]

    topics = [
        _mods_text(topic)
        for topic in mods.findall(f".//{MODS}subject/{MODS}topic")
        if _mods_text(topic)
    ]

    url = identifiers.get("uri")
    if not (url and url.startswith(("http://", "https://"))):
        url = _mods_text(mods.find(f".//{MODS}location/{MODS}url"))

    return {
        "uuid": identifiers.get("pure/uuid"),
        "title": title,
        "authors": "; ".join(authors) or None,
        "date_issued": _mods_text(mods.find(f".//{MODS}originInfo/{MODS}dateIssued")),
        "abstract": _mods_text(mods.find(f"{MODS}abstract")),
        "topics": "; ".join(topics) or None,
        "journal": _mods_text(
            mods.find(f"{MODS}relatedItem[@type='host']/{MODS}titleInfo/{MODS}title")
        ),
        "doi_raw": identifiers.get("doi"),
        "url": url,
        "genre": _mods_text(mods.find(f"{MODS}genre")),
        "organisational_units": organisational_units,
    }


def read_kfupm_pure(directory: Path) -> pd.DataFrame:
    """Read every harvested Pure OAI-PMH page."""
    rows = [
        parse_pure_record(mods)
        for path in sorted(Path(directory).glob("*.xml"))
        for mods in ET.parse(path).getroot().iter(f"{MODS}mods")
    ]
    return pd.DataFrame(rows)


def fetch_pure_pages(
    base_url: str,
    year: int,
    output_dir: Path,
    metadata_prefix: str = "mods",
    pause: float = 1.5,
) -> int:
    """Harvest one year set from an OAI-PMH endpoint and save raw XML pages."""
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


def read_ksu_year(path: Path, year: int) -> pd.DataFrame:
    """Read one KSU annual JSON file and preserve its original row order."""
    text = Path(path).read_text(encoding="utf-8-sig")
    records = json.loads(text)

    frame = pd.DataFrame(records)
    frame["source_file_year"] = year
    frame["source_row_index"] = range(len(frame))
    return frame


def repair_ksu_json(source_path: Path, output_path: Path) -> tuple[Path, int]:
    """Repair the known backslash+literal-tab defect in the KSU 2025 JSON.

    The raw file remains unchanged. The repaired copy is written to interim.
    Only the invalid sequence ``backslash + literal tab`` is escaped so JSON
    parsing succeeds while preserving both character values.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    text = source_path.read_text(encoding="utf-8-sig")

    try:
        json.loads(text)
        repaired = text
        repair_count = 0
    except json.JSONDecodeError:
        bad_sequence = "\\\t"  # one backslash followed by a literal tab
        replacement = "\\\\\\t"  # JSON text for a literal backslash + tab
        repair_count = text.count(bad_sequence)
        repaired = text.replace(bad_sequence, replacement)
        json.loads(repaired)  # fail loudly if another corruption still exists

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(repaired, encoding="utf-8")
    return output_path, repair_count
