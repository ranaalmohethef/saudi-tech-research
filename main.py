"""Run the whole pipeline from the raw files to data/processed/final.csv.

    python main.py                 # every source
    python main.py --sources kaust # one or more sources
    python main.py --no-tech-filter

The extraction step is not repeated here: the raw files under ``data/raw`` are
the frozen snapshot the project works from. Re-downloading them is done in
``notebooks/01_extract.ipynb`` and in the KFUPM Pure notebook.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from src import clean, extract, transform
from src.config import get_paths, load_config, year_range
from src.schema import SCHEMA_COLUMNS, failures_by_rule, validate_dataset

SOURCES = ["kaust", "kfupm", "ksu"]


def build_kaust(config, paths, min_year, max_year) -> pd.DataFrame:
    """Clean both KAUST inputs (repository export + Crossref) and merge them."""
    settings = config["sources"]["kaust_repository"]
    repository = clean.clean_kaust_repository(
        extract.read_kaust_repository(paths.raw / settings["file"]),
        year=int(settings["year"]),
        university=settings["university"],
        source_label=settings["source_label"],
    )
    repository.to_csv(paths.interim / settings["cleaned"], index=False)
    print(f"  KAUST repository cleaned : {len(repository):>6}")

    crossref_settings = config["sources"]["kaust_crossref"]
    crossref = clean.clean_kaust_crossref(
        extract.read_crossref_pages(list(paths.raw.glob(crossref_settings["pattern"]))),
        university=crossref_settings["university"],
        source_label=crossref_settings["source_label"],
    )
    crossref.to_csv(paths.interim / crossref_settings["cleaned"], index=False)
    print(f"  KAUST Crossref cleaned   : {len(crossref):>6}")

    return pd.concat([repository, crossref], ignore_index=True)


def build_kfupm(config, paths, min_year, max_year) -> pd.DataFrame:
    """Clean the KFUPM Pure harvest (Computer Engineering only)."""
    settings = config["sources"]["kfupm_pure"]

    cleaned = clean.clean_kfupm_pure(
        extract.read_kfupm_pure(paths.raw / settings["directory"]),
        department=settings["department"],
        university=settings["university"],
        source_label=settings["source_label"],
        min_year=min_year,
        max_year=max_year,
        excluded_genres=settings.get("excluded_genres"),
        require_doi=bool(settings.get("require_doi", True)),
    )
    cleaned.to_csv(paths.interim / settings["cleaned"], index=False)
    print(f"  KFUPM Pure cleaned       : {len(cleaned):>6}")
    return cleaned


def build_ksu(config, paths, min_year, max_year,
              apply_tech_filter: bool = True) -> pd.DataFrame:
    """Clean the three KSU annual files and apply the reviewed enrichment.

    The technology filter runs here, on the raw columns, because KSU publishes
    author keywords but no abstract: after the schema mapping those keywords
    are gone. The matched terms are written to a provenance file instead of
    being stored as a verified classification.
    """
    settings = config["sources"]["ksu"]
    tech_settings = config.get("technology_filter", {})
    frames, provenance = [], []

    for year, filename in settings["files"].items():
        path = paths.raw / filename
        if not path.exists():                     # the repaired 2025 file
            path = paths.interim / filename

        raw = extract.read_ksu_year(path, int(year))

        if apply_tech_filter:
            raw, matches = transform.filter_raw_records(
                raw,
                fields=tech_settings.get("ksu_fields", ["Article Title", "Author Keywords"]),
                terms=tech_settings.get("terms"),
            )
            provenance.extend(
                {
                    "research_id": f"KSU_{year}_{index}",
                    "source_file_year": int(year),
                    "source_row_index": int(index),
                    "input_file": str(path.relative_to(paths.root)),
                    "source_url": settings["dataset_url"].format(year=year),
                    "publication_year_basis": "KSU annual dataset year",
                    "url_basis": "Annual dataset download URL",
                    "tech_matched_terms": matches.loc[position],
                }
                for position, index in zip(raw.index, raw["source_row_index"])
            )

        frames.append(
            clean.clean_ksu(
                raw,
                year=int(year),
                dataset_url=settings["dataset_url"],
                university=settings["university"],
                source_label=settings["source_label"],
            )
        )

    cleaned = pd.concat(frames, ignore_index=True)

    if provenance:
        (paths.interim / "ksu_provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    enrichment_file = paths.interim / settings.get("manual_enrichment", "")
    if enrichment_file.is_file():
        cleaned, log = clean.apply_manual_enrichment(cleaned, enrichment_file)
        if log:
            print(f"  KSU reviewed enrichment  : {len(log):>6} records")

    cleaned.to_csv(paths.interim / settings["cleaned"], index=False)
    print(f"  KSU cleaned              : {len(cleaned):>6}")
    return cleaned


BUILDERS = {"kaust": build_kaust, "kfupm": build_kfupm, "ksu": build_ksu}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the research data pipeline")
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=SOURCES)
    parser.add_argument("--no-tech-filter", action="store_true",
                        help="skip the technology keyword filter")
    args = parser.parse_args()

    config = load_config()
    paths = get_paths(config).ensure()
    min_year, max_year = year_range(config)
    tech_settings = config.get("technology_filter", {})

    print(f"Project root: {paths.root}")
    print(f"Year range  : {min_year}-{max_year}\n")

    print("1. Clean")
    cleaned = {}
    for name in args.sources:
        if name == "ksu":
            cleaned[name] = build_ksu(config, paths, min_year, max_year,
                                      apply_tech_filter=not args.no_tech_filter)
        else:
            cleaned[name] = BUILDERS[name](config, paths, min_year, max_year)

    print("\n2. Validate")
    validated_frames, summary = [], []

    for name, frame in cleaned.items():
        university = frame["university"].iloc[0] if len(frame) else ""
        validated, rejected = validate_dataset(frame, university, min_year, max_year)

        prefix = name.upper()
        validated[SCHEMA_COLUMNS].to_csv(
            paths.interim / f"{prefix}_validated.csv", index=False)
        rejected.to_csv(paths.interim / f"{prefix}_rejected.csv", index=False)

        validated_frames.append(validated[SCHEMA_COLUMNS])
        summary.append({
            "source": prefix,
            "cleaned": len(frame),
            "validated": len(validated),
            "rejected": len(rejected),
        })
        print(f"  {prefix:<6} accepted {len(validated):>6} | rejected {len(rejected):>6}")

        if len(rejected):
            failures_by_rule(rejected).to_csv(
                paths.interim / f"{prefix}_failures_by_rule.csv", index=False)

    print("\n3. Join and transform")
    combined = transform.combine_sources(validated_frames)
    print(f"  Joined records           : {len(combined):>6}")

    shared = transform.shared_doi_report(combined)
    shared.to_csv(paths.processed / "shared_doi_review.csv", index=False)
    print(f"  DOIs shared across unis  : {shared['doi'].nunique():>6}")

    if args.no_tech_filter:
        selected = combined
    else:
        # KSU was already filtered on its raw keyword fields; filtering it
        # again on title+abstract would drop records for a missing abstract.
        already_filtered = combined["university"] == config["sources"]["ksu"]["university"]
        candidates, excluded, review = transform.filter_technology(
            combined[~already_filtered],
            fields=tech_settings.get("fields", ["title", "abstract"]),
            terms=tech_settings.get("terms"),
        )
        selected = pd.concat(
            [candidates, combined[already_filtered]], ignore_index=True
        )
        filter_dir = paths.processed / "technology_filter"
        filter_dir.mkdir(parents=True, exist_ok=True)
        review.to_csv(filter_dir / "filter_review.csv", index=False)
        excluded.to_csv(filter_dir / "no_keyword_match.csv", index=False)
        print(f"  Technology candidates    : {len(selected):>6}")
        print(f"  No keyword match         : {len(excluded):>6}")

    final = transform.apply_transformations(selected)
    final.to_csv(paths.processed / "final.csv", index=False)

    pd.DataFrame(summary).to_csv(paths.interim / "validation_summary.csv", index=False)

    print("\n4. Result")
    print(f"  data/processed/final.csv : {len(final)} rows, {len(final.columns)} columns")
    print(final.groupby("university").size().to_string())

    (paths.processed / "run_summary.json").write_text(
        json.dumps(
            {
                "sources": summary,
                "joined": len(combined),
                "final_rows": int(len(final)),
                "year_range": [min_year, max_year],
                "technology_filter": not args.no_tech_filter,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
