"""Run the project pipeline from the frozen raw snapshot to processed output.

Examples
--------
python main.py
python main.py --sources kaust
python main.py --no-tech-filter

A partial-source run never overwrites the shared ``final.csv``. It writes a
source-specific output such as ``final_kaust.csv`` instead.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src import clean, extract, transform
from src.config import get_paths, load_config, year_range
from src.schema import SCHEMA_COLUMNS, failures_by_rule, validate_dataset

SOURCES = ["kaust", "kfupm", "ksu"]


def build_kaust(config, paths, min_year, max_year) -> pd.DataFrame:
    """Clean KAUST repository + Crossref inputs and return one frame."""
    repository_settings = config["sources"]["kaust_repository"]
    repository = clean.clean_kaust_repository(
        extract.read_kaust_repository(paths.raw / repository_settings["file"]),
        year=int(repository_settings["year"]),
        university=repository_settings["university"],
        source_label=repository_settings["source_label"],
    )
    repository.to_csv(paths.interim / repository_settings["cleaned"], index=False)
    print(f"  KAUST repository cleaned : {len(repository):>6}")

    crossref_settings = config["sources"]["kaust_crossref"]
    crossref_paths = list(paths.raw.glob(crossref_settings["pattern"]))
    if not crossref_paths:
        raise FileNotFoundError(
            f"No Crossref files match {crossref_settings['pattern']} under {paths.raw}"
        )

    crossref = clean.clean_kaust_crossref(
        extract.read_crossref_pages(crossref_paths),
        university=crossref_settings["university"],
        source_label=crossref_settings["source_label"],
        min_year=int(crossref_settings.get("from_year", min_year)),
        max_year=int(crossref_settings.get("until_year", max_year)),
    )
    crossref.to_csv(paths.interim / crossref_settings["cleaned"], index=False)
    print(f"  KAUST Crossref cleaned   : {len(crossref):>6}")

    return pd.concat([repository, crossref], ignore_index=True)


def build_kfupm(config, paths, min_year, max_year) -> pd.DataFrame:
    """Clean the KFUPM Pure harvest without pre-dropping missing DOI rows."""
    settings = config["sources"]["kfupm_pure"]
    raw_directory = paths.raw / settings["directory"]

    cleaned = clean.clean_kfupm_pure(
        extract.read_kfupm_pure(raw_directory),
        department=settings["department"],
        university=settings["university"],
        source_label=settings["source_label"],
        min_year=min_year,
        max_year=max_year,
        excluded_genres=settings.get("excluded_genres"),
    )
    cleaned.to_csv(paths.interim / settings["cleaned"], index=False)
    print(f"  KFUPM Pure cleaned       : {len(cleaned):>6}")
    return cleaned


def _read_ksu_source(paths, settings: dict, year: int) -> tuple[pd.DataFrame, Path, int]:
    """Read one KSU year, repairing the known 2025 JSON defect when configured."""
    raw_path = paths.raw / settings["files"][year]

    try:
        return extract.read_ksu_year(raw_path, year), raw_path, 0
    except json.JSONDecodeError:
        repaired_name = settings.get("repaired_files", {}).get(year)
        if not repaired_name:
            raise

        repaired_path = paths.interim / repaired_name
        repaired_path, repair_count = extract.repair_ksu_json(raw_path, repaired_path)
        return extract.read_ksu_year(repaired_path, year), repaired_path, repair_count


def build_ksu(config, paths, min_year, max_year) -> pd.DataFrame:
    """Clean all KSU records and separately preserve technology-match evidence.

    Technology matching is calculated from the raw source columns because KSU
    carries useful Author Keywords that are not part of the shared schema.
    The full cleaned dataset is still sent to validation; filtering is applied
    only after validation in the join/transform stage.
    """
    settings = config["sources"]["ksu"]
    tech_settings = config.get("technology_filter", {})

    cleaned_frames: list[pd.DataFrame] = []
    review_frames: list[pd.DataFrame] = []
    selected_provenance: list[dict] = []

    for year_key, _filename in settings["files"].items():
        year = int(year_key)
        raw, input_path, repair_count = _read_ksu_source(paths, settings, year)

        if repair_count:
            print(f"  KSU {year} JSON repairs   : {repair_count:>6}")

        _selected_raw, matches = transform.filter_raw_records(
            raw,
            fields=tech_settings.get("ksu_fields", ["Article Title", "Author Keywords"]),
            terms=tech_settings.get("terms"),
            excluded_phrases=tech_settings.get("excluded_phrases"),
        )

        research_ids = pd.Series(
            [f"KSU_{year}_{index}" for index in raw["source_row_index"]],
            index=raw.index,
            dtype="string",
        )
        selected = matches.map(bool)

        review = pd.DataFrame(
            {
                "research_id": research_ids,
                "university": settings["university"],
                "title": raw.get("Article Title", pd.Series(pd.NA, index=raw.index)),
                "matched_terms": matches.map("; ".join),
                "selected": selected,
            },
            index=raw.index,
        )
        review_frames.append(review.reset_index(drop=True))

        for idx in raw.index[selected]:
            selected_provenance.append(
                {
                    "research_id": research_ids.loc[idx],
                    "source_file_year": year,
                    "source_row_index": int(raw.loc[idx, "source_row_index"]),
                    "input_file": str(input_path.relative_to(paths.root)),
                    "source_url": settings["dataset_url"].format(year=year),
                    "publication_year_basis": "KSU annual dataset year",
                    "url_basis": "Annual dataset download URL",
                    "tech_matched_terms": matches.loc[idx],
                }
            )

        cleaned_frames.append(
            clean.clean_ksu(
                raw,
                year=year,
                dataset_url=settings["dataset_url"],
                university=settings["university"],
                source_label=settings["source_label"],
            )
        )

    cleaned = pd.concat(cleaned_frames, ignore_index=True)

    review_file = paths.interim / settings.get("technology_review", "KSU_technology_review.csv")
    pd.concat(review_frames, ignore_index=True).to_csv(review_file, index=False)

    (paths.interim / "ksu_provenance.json").write_text(
        json.dumps(selected_provenance, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    enrichment_file = paths.interim / settings.get("manual_enrichment", "")
    if enrichment_file.is_file():
        cleaned, log = clean.apply_manual_enrichment(cleaned, enrichment_file)
        if log:
            print(f"  KSU reviewed enrichment  : {len(log):>6} records")

    cleaned.to_csv(paths.interim / settings["cleaned"], index=False)
    print(f"  KSU cleaned              : {len(cleaned):>6}")
    return cleaned


BUILDERS = {
    "kaust": build_kaust,
    "kfupm": build_kfupm,
    "ksu": build_ksu,
}


def apply_team_technology_filter(
    combined: pd.DataFrame,
    config: dict,
    paths,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply one team filter after validation, with KSU raw-keyword evidence."""
    tech_settings = config.get("technology_filter", {})
    ksu_code = config["sources"]["ksu"]["university"]

    is_ksu = combined["university"].eq(ksu_code)
    non_ksu = combined.loc[~is_ksu]

    non_selected, _non_excluded, non_review = transform.filter_technology(
        non_ksu,
        fields=tech_settings.get("fields", ["title", "abstract"]),
        terms=tech_settings.get("terms"),
        excluded_phrases=tech_settings.get("excluded_phrases"),
    )

    selected_ids = set(non_selected["research_id"].astype(str))
    review_parts = [non_review]

    if is_ksu.any():
        ksu_settings = config["sources"]["ksu"]
        review_path = paths.interim / ksu_settings.get(
            "technology_review", "KSU_technology_review.csv"
        )
        if not review_path.is_file():
            raise FileNotFoundError(f"KSU technology review not found: {review_path}")

        raw_review = pd.read_csv(review_path, dtype={"research_id": "string"})
        raw_review["selected"] = raw_review["selected"].astype("boolean")

        ksu_validated = combined.loc[is_ksu, ["research_id", "university", "title"]]
        ksu_review = ksu_validated.merge(
            raw_review[["research_id", "matched_terms", "selected"]],
            on="research_id",
            how="left",
            validate="one_to_one",
        )

        if ksu_review["selected"].isna().any():
            missing = int(ksu_review["selected"].isna().sum())
            raise ValueError(f"{missing} validated KSU records are missing technology-review evidence")

        selected_ids.update(
            ksu_review.loc[ksu_review["selected"].fillna(False), "research_id"].astype(str)
        )
        review_parts.append(ksu_review)

    keep = combined["research_id"].astype(str).isin(selected_ids)
    selected = combined.loc[keep].copy()
    excluded = combined.loc[~keep].copy()

    review = pd.concat(review_parts, ignore_index=True)
    review = review.set_index("research_id").reindex(combined["research_id"]).reset_index()
    review["selected"] = review["selected"].astype(bool)

    return selected, excluded, review


def _output_suffix(selected_sources: list[str], no_tech_filter: bool = False) -> str:
    suffix = "" if set(selected_sources) == set(SOURCES) else "_" + "_".join(selected_sources)
    if no_tech_filter:
        suffix += "_no_tech_filter"
    return suffix


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the research data pipeline")
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=SOURCES)
    parser.add_argument(
        "--no-tech-filter",
        action="store_true",
        help="skip the technology keyword filter",
    )
    args = parser.parse_args()

    config = load_config()
    paths = get_paths(config).ensure()
    min_year, max_year = year_range(config)

    print(f"Project root: {paths.root}")
    print(f"Year range  : {min_year}-{max_year}\n")

    print("1. Clean")
    cleaned: dict[str, pd.DataFrame] = {}
    for name in args.sources:
        cleaned[name] = BUILDERS[name](config, paths, min_year, max_year)

    print("\n2. Validate")
    validated_by_source: dict[str, pd.DataFrame] = {}
    summary: list[dict] = []

    for name, frame in cleaned.items():
        expected_university = config["sources"][
            "kaust_repository" if name == "kaust" else (
                "kfupm_pure" if name == "kfupm" else "ksu"
            )
        ]["university"]

        validated, rejected = validate_dataset(
            frame,
            expected_university,
            min_year,
            max_year,
        )

        prefix = name.upper()
        validated[SCHEMA_COLUMNS].to_csv(
            paths.interim / f"{prefix}_validated.csv", index=False
        )
        rejected.to_csv(paths.interim / f"{prefix}_rejected.csv", index=False)
        failures_by_rule(rejected).to_csv(
            paths.interim / f"{prefix}_failures_by_rule.csv", index=False
        )

        validated_by_source[name] = validated[SCHEMA_COLUMNS]
        summary.append(
            {
                "source": prefix,
                "cleaned": len(frame),
                "validated": len(validated),
                "rejected": len(rejected),
            }
        )
        print(f"  {prefix:<6} accepted {len(validated):>6} | rejected {len(rejected):>6}")

    print("\n3. Join and transform")
    combined = transform.combine_sources(list(validated_by_source.values()))
    print(f"  Joined validated records : {len(combined):>6}")

    suffix = _output_suffix(args.sources, no_tech_filter=args.no_tech_filter)
    if args.no_tech_filter:
        selected = combined.copy()
        excluded = combined.iloc[0:0].copy()
        review = pd.DataFrame(
            {
                "research_id": combined["research_id"],
                "university": combined["university"],
                "title": combined["title"],
                "matched_terms": "",
                "selected": True,
            }
        )
    else:
        selected, excluded, review = apply_team_technology_filter(
            combined,
            config,
            paths,
        )
        print(f"  Technology candidates    : {len(selected):>6}")
        print(f"  No keyword match         : {len(excluded):>6}")


    shared = transform.shared_doi_report(selected)
    shared_path = paths.processed / f"shared_doi_review{suffix}.csv"
    shared.to_csv(shared_path, index=False)
    print(f"  DOIs shared across unis  : {shared['doi'].nunique():>6}")

    final = transform.apply_transformations(selected)

    final_path = paths.processed / f"final{suffix}.csv"
    final.to_csv(final_path, index=False)

    filter_dir = paths.processed / "technology_filter"
    filter_dir.mkdir(parents=True, exist_ok=True)
    review.to_csv(filter_dir / f"filter_review{suffix}.csv", index=False)
    excluded.to_csv(filter_dir / f"no_keyword_match{suffix}.csv", index=False)

    pd.DataFrame(summary).to_csv(
        paths.interim / f"validation_summary{suffix}.csv", index=False
    )

    print("\n4. Result")
    print(f"  {final_path.relative_to(paths.root)} : {len(final)} rows, {len(final.columns)} columns")
    if not final.empty:
        print(final.groupby("university").size().to_string())

    run_summary = {
        "sources": summary,
        "joined_validated": int(len(combined)),
        "final_rows": int(len(final)),
        "excluded_by_technology_filter": int(len(excluded)),
        "year_range": [min_year, max_year],
        "technology_filter": not args.no_tech_filter,
        "output_file": str(final_path.relative_to(paths.root)),
    }
    (paths.processed / f"run_summary{suffix}.json").write_text(
        json.dumps(run_summary, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
