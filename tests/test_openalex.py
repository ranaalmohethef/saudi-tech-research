"""Tests for the OpenAlex source."""

import json

import pandas as pd
import pytest

from src import openalex, transform
from src.schema import SCHEMA_COLUMNS, validate_dataset


def work(**overrides) -> dict:
    base = {
        "id": "https://openalex.org/W4319066461",
        "title": "Deep learning for network automation",
        "publication_year": 2025,
        "publication_date": "2025-01-01",
        "doi": "https://doi.org/10.1109/OJCOMS.2025.3554537",
        "abstract_inverted_index": {"Deep": [0], "learning": [1], "works": [2]},
        "authorships": [
            {"author": {"display_name": "Sadiq M. Sait"}},
            {"author": {"display_name": "A. Author"}},
        ],
        "primary_location": {"source": {"display_name": "IEEE OJCOMS"}},
        "primary_topic": {"field": {"display_name": "Computer Science"}},
    }
    base.update(overrides)
    return base


def clean(*works, university="KAU", ror="02ma4wv74"):
    return openalex.clean_openalex(
        list(works),
        university=university,
        ror=ror,
        source_label="OpenAlex API",
        min_year=2023,
        max_year=2026,
    )


def test_cleaned_record_matches_the_shared_schema():
    result = clean(work())
    row = result.iloc[0]

    assert list(result.columns) == SCHEMA_COLUMNS
    assert row["research_id"] == "OA_W4319066461_02ma4wv74"
    assert row["university"] == "KAU"
    assert row["authors"] == "Sadiq M. Sait; A. Author"
    assert row["publication_year"] == 2025
    assert row["doi"] == "10.1109/ojcoms.2025.3554537"
    assert row["url"] == "https://openalex.org/W4319066461"
    assert row["journal"] == "IEEE OJCOMS"
    assert row["abstract"] == "Deep learning works"
    assert row["source"] == "OpenAlex API"


def test_publication_date_is_never_taken_from_openalex():
    result = clean(work(publication_date="2025-01-01"))
    assert pd.isna(result.loc[0, "publication_date"])


def test_cleaned_records_pass_schema_validation():
    validated, rejected = validate_dataset(clean(work()), "KAU", 2023, 2026)
    assert len(validated) == 1
    assert rejected.empty


@pytest.mark.parametrize("year", [2022, 2027, None])
def test_records_outside_the_year_range_are_dropped(year):
    assert clean(work(publication_year=year)).empty


def test_records_missing_a_doi_or_title_are_kept_for_validation():
    result = clean(work(doi=None, title=None))
    assert len(result) == 1
    assert pd.isna(result.loc[0, "doi"])

    validated, rejected = validate_dataset(result, "KAU", 2023, 2026)
    assert validated.empty
    assert "doi is missing" in rejected.loc[0, "validation_error"]
    assert "title is missing" in rejected.loc[0, "validation_error"]


def test_missing_abstract_index_becomes_missing_value():
    assert openalex.rebuild_abstract(None) is None
    assert openalex.rebuild_abstract({}) is None
    assert pd.isna(clean(work(abstract_inverted_index=None)).loc[0, "abstract"])


def test_abstract_is_rebuilt_in_word_order():
    index = {"second": [1], "first": [0], "third": [2, 3]}
    assert openalex.rebuild_abstract(index) == "first second third third"


def test_the_same_paper_is_kept_once_per_university():
    shared = work()
    kau = clean(shared, university="KAU", ror="02ma4wv74")
    kku = clean(shared, university="KKU", ror="052kwzs30")

    combined = transform.combine_sources([kau, kku])

    assert len(combined) == 2
    assert combined["research_id"].is_unique
    assert combined["doi"].nunique() == 1

    report = transform.shared_doi_report(combined)
    assert len(report) == 2
    assert report["university"].tolist() == ["KAU", "KKU"]


def test_duplicate_works_inside_one_university_are_removed():
    assert len(clean(work(), work())) == 1


def test_filter_string_contains_every_scope_rule():
    query = openalex.build_filter("02ma4wv74", "2023-01-01", "2026-12-31", "fields/17")
    assert "institutions.ror:02ma4wv74" in query
    assert "from_publication_date:2023-01-01" in query
    assert "to_publication_date:2026-12-31" in query
    assert "has_doi:true" in query
    assert "primary_topic.field.id:fields/17" in query


def test_filter_string_can_omit_the_field_restriction():
    query = openalex.build_filter("02ma4wv74", "2023-01-01", "2026-12-31")
    assert "primary_topic.field.id" not in query


def test_snapshot_round_trip(tmp_path):
    path = tmp_path / "openalex_02ma4wv74.json"
    path.write_text(json.dumps([work()], ensure_ascii=False), encoding="utf-8")
    assert openalex.read_openalex(path)[0]["id"] == "https://openalex.org/W4319066461"


def test_empty_snapshot_returns_an_empty_schema_frame():
    result = clean()
    assert result.empty
    assert list(result.columns) == SCHEMA_COLUMNS


def test_university_codes_follow_configuration_order():
    config = {
        "sources": {
            "openalex": {
                "universities": [
                    {"code": "KAU", "ror": "02ma4wv74"},
                    {"code": "KKU", "ror": "052kwzs30"},
                ]
            }
        }
    }
    assert openalex.university_codes(config) == ["KAU", "KKU"]
