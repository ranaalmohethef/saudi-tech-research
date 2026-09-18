"""Tests for the common schema and validation rules."""

import pandas as pd
import pytest

from src import schema


def record(**overrides) -> dict:
    base = {
        "research_id": "R1",
        "university": "KAUST",
        "title": "A title",
        "authors": "Author, A",
        "publication_year": 2024,
        "publication_date": "2024-01-15",
        "abstract": "Text",
        "research_field": None,
        "tech_category": None,
        "journal": "Journal",
        "doi": "10.1234/abc",
        "url": "https://example.org/1",
        "source": "Test",
    }
    base.update(overrides)
    return base


def frame(*records) -> pd.DataFrame:
    return pd.DataFrame(list(records), columns=schema.SCHEMA_COLUMNS)


def validate(*records, university="KAUST"):
    return schema.validate_dataset(frame(*records), university, 2023, 2026)


def test_complete_record_is_accepted():
    validated, rejected = validate(record())
    assert len(validated) == 1
    assert rejected.empty


@pytest.mark.parametrize(
    "field",
    ["research_id", "university", "title", "authors", "publication_year", "doi", "url", "source"],
)
def test_missing_required_field_rejects_record(field):
    validated, rejected = validate(record(**{field: None}))
    assert validated.empty
    assert f"{field} is missing" in rejected.loc[0, "validation_error"]


@pytest.mark.parametrize(
    "field",
    ["abstract", "publication_date", "research_field", "tech_category", "journal"],
)
def test_missing_optional_field_keeps_record(field):
    validated, rejected = validate(record(**{field: None}))
    assert len(validated) == 1
    assert rejected.empty


@pytest.mark.parametrize("marker", ["", "   ", "n/a", "N/A", "none", "NULL", "nan", "<NA>", "NaT"])
def test_missing_markers_count_as_missing(marker):
    validated, rejected = validate(record(doi=marker))
    assert validated.empty
    assert "doi is missing" in rejected.loc[0, "validation_error"]


@pytest.mark.parametrize("doi", ["https://doi.org/10.1234/abc", "abc", "10.12/x"])
def test_badly_formatted_doi_is_rejected(doi):
    validated, rejected = validate(record(doi=doi))
    assert validated.empty
    assert "invalid DOI" in rejected.loc[0, "validation_error"]


@pytest.mark.parametrize(
    "url",
    [
        "example.org",
        "ftp://example.org/x",
        "/local/path",
        "https://",
        "https:///path-only",
        "https://example.org/a path",
    ],
)
def test_url_must_be_complete_http_or_https(url):
    validated, rejected = validate(record(url=url))
    assert validated.empty
    assert "invalid URL" in rejected.loc[0, "validation_error"]


@pytest.mark.parametrize(
    "date, accepted",
    [
        ("2024-02-29", True),
        ("2024-02-30", False),
        ("2024-02", False),
        ("2024-04-11 00:00:00+00:00", False),
        (None, True),
    ],
)
def test_publication_date_must_be_real_calendar_date(date, accepted):
    validated, _ = validate(record(publication_date=date))
    assert bool(len(validated)) is accepted


def test_publication_date_year_must_match_publication_year():
    validated, rejected = validate(
        record(publication_year=2024, publication_date="2025-01-01")
    )
    assert validated.empty
    assert "publication date/year mismatch" in rejected.loc[0, "validation_error"]


@pytest.mark.parametrize(
    "year, accepted",
    [
        (2023, True),
        (2026, True),
        (2022, False),
        (2027, False),
        ("2024", True),
        (2024.5, False),
        ("not a year", False),
    ],
)
def test_publication_year_must_be_whole_and_in_range(year, accepted):
    validated, _ = validate(record(publication_year=year, publication_date=None))
    assert bool(len(validated)) is accepted


def test_record_from_another_university_is_rejected():
    validated, rejected = validate(record(university="KSU"), university="KAUST")
    assert validated.empty
    assert "invalid university" in rejected.loc[0, "validation_error"]


def test_duplicate_research_ids_reject_both_records():
    validated, rejected = validate(record(research_id="R1"), record(research_id="R1"))
    assert validated.empty
    assert len(rejected) == 2


def test_every_failed_rule_is_listed_for_same_record():
    validated, rejected = validate(record(doi=None, url="example.org"))
    message = rejected.loc[0, "validation_error"]
    assert "doi is missing" in message
    assert "invalid URL" in message


def test_rejected_records_keep_original_values():
    _, rejected = validate(record(doi=None, title="Keep me"))
    assert rejected.loc[0, "title"] == "Keep me"


def test_failures_by_rule_counts_each_rule():
    _, rejected = validate(
        record(research_id="R1", doi=None),
        record(research_id="R2", doi=None),
        record(research_id="R3", url="example.org"),
    )
    counts = schema.failures_by_rule(rejected).set_index("rule")["records"]
    assert counts["doi is missing"] == 2
    assert counts["invalid URL"] == 1


def test_schema_table_matches_schema_columns():
    table = schema.schema_table()
    assert table["column"].tolist() == schema.SCHEMA_COLUMNS
    assert set(table.loc[~table["nullable"], "column"]) == set(schema.REQUIRED_FIELDS)


def test_missing_schema_column_fails_loudly():
    bad = frame(record()).drop(columns=["doi"])
    with pytest.raises(ValueError, match="missing schema columns"):
        schema.validate_dataset(bad, "KAUST", 2023, 2026)
