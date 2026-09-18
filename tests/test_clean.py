"""Tests for cleaning helpers and source mappings."""

import json

import pandas as pd
import pytest

from src import clean, extract


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("10.1016/J.IOT.2023.100986", "10.1016/j.iot.2023.100986"),
        ("https://doi.org/10.1109/TCE.2023.3325131", "10.1109/tce.2023.3325131"),
        ("http://dx.doi.org/10.1080/10106049.2023.2256297", "10.1080/10106049.2023.2256297"),
        ("doi: 10.1234/abc.def", "10.1234/abc.def"),
        ("  10.1234/abc  ", "10.1234/abc"),
        ("10.1234/abc.", "10.1234/abc"),
    ],
)
def test_normalize_doi_returns_bare_lowercase_doi(raw, expected):
    assert clean.normalize_doi(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "not a doi", "10.123/x", float("nan")])
def test_normalize_doi_rejects_values_that_are_not_dois(raw):
    assert pd.isna(clean.normalize_doi(raw))


def test_partial_dates_are_never_completed():
    assert clean.parse_partial_date("2024-03") is None
    assert clean.parse_partial_date("2024") is None
    assert str(clean.parse_partial_date("2024-03-07")) == "2024-03-07"
    assert str(clean.parse_partial_date("2024-03-07T09:30:00Z")) == "2024-03-07"


@pytest.mark.parametrize("value", ["2023-02-30", "not a date", "", None, "01-2023"])
def test_invalid_dates_become_missing(value):
    assert clean.parse_partial_date(value) is None


def test_extract_year_does_not_require_a_full_date():
    assert clean.extract_year("2023") == 2023
    assert clean.extract_year("2023-04") == 2023
    assert clean.extract_year("2023-04-11") == 2023
    assert pd.isna(clean.extract_year("not a date"))


def test_format_date_uses_schema_format():
    assert clean.format_date(clean.parse_partial_date("2023-4-10")) == "2023-04-10"
    assert pd.isna(clean.format_date(None))


def test_clean_markup_removes_jats_tags_and_collapses_spaces():
    raw = "<jats:p>Deep   learning &amp; robotics</jats:p>"
    assert clean.clean_markup(raw) == "Deep learning & robotics"


def test_snake_case_columns_and_missing_markers():
    frame = pd.DataFrame(
        {
            "Publication Date": ["  2023-01-01 ", "N/A"],
            "Link to PDF": ["   ", "null"],
        }
    )
    result = clean.strip_and_blank_to_na(clean.snake_case_columns(frame))

    assert list(result.columns) == ["publication_date", "link_to_pdf"]
    assert result.loc[0, "publication_date"] == "2023-01-01"
    assert pd.isna(result.loc[0, "link_to_pdf"])
    assert pd.isna(result.loc[1, "publication_date"])
    assert pd.isna(result.loc[1, "link_to_pdf"])


def test_deduplicate_keeps_the_most_complete_record():
    frame = pd.DataFrame(
        {
            "key": ["a", "a", "b"],
            "completeness": [5, 9, 3],
            "modified": ["2023-01-01", "2023-01-02", "2023-01-03"],
            "label": ["sparse", "complete", "other"],
        }
    )

    result = clean.deduplicate(frame, subset=["key"], prefer=["completeness", "modified"])
    assert len(result) == 2
    assert result.loc[result["key"] == "a", "label"].item() == "complete"


def test_deduplicate_breaks_ties_with_the_newest_record():
    frame = pd.DataFrame(
        {
            "key": ["a", "a"],
            "completeness": [5, 5],
            "modified": ["2023-01-01", "2024-06-01"],
            "label": ["old", "new"],
        }
    )
    result = clean.deduplicate(frame, subset=["key"], prefer=["completeness", "modified"])
    assert result["label"].item() == "new"


def test_kaust_repository_keeps_partial_date_record_but_leaves_date_empty():
    raw = pd.DataFrame(
        {
            "Type": ["Article"],
            "Title": ["Technology paper"],
            "Authors": ["A Author"],
            "Journal": ["Journal"],
            "Publisher": ["Publisher"],
            "DOI": ["10.1234/test"],
            "Handle": ["https://repository.example/1"],
            "Publication Date": ["2023-04"],
            "Citation": ["Citation"],
            "Abstract": ["Abstract"],
            "Link to License": [None],
            "Status": ["Published"],
            "Link to PDF": [None],
            "Link to Extracted Text": [None],
            "Metadata Last Modified": ["2024-01-01"],
        }
    )

    result = clean.clean_kaust_repository(raw, year=2023)
    assert len(result) == 1
    assert result.loc[0, "publication_year"] == 2023
    assert pd.isna(result.loc[0, "publication_date"])


def test_clean_ksu_uses_annual_file_year_and_leaves_date_empty():
    raw = pd.DataFrame(
        {
            "Article Title": ["A study of robotics"],
            "Authors": ["Alharbi, S"],
            "Source Title": ["JOURNAL OF TESTS"],
            "DOI": ["http://dx.doi.org/10.1234/ABC"],
            "Abstract": ["Text"],
            "source_file_year": [2023],
            "source_row_index": [7],
        }
    )

    result = clean.clean_ksu(raw, year=2023, dataset_url="https://example.org/{year}.json")
    row = result.iloc[0]
    assert row["research_id"] == "KSU_2023_7"
    assert row["publication_year"] == 2023
    assert pd.isna(row["publication_date"])
    assert row["doi"] == "10.1234/abc"
    assert row["url"] == "https://example.org/2023.json"


def test_clean_ksu_handles_year_without_doi_or_abstract():
    raw = pd.DataFrame(
        {
            "Article Title": ["Machine learning in agriculture"],
            "Authors": ["Alotaibi, A"],
            "Source Title": ["JOURNAL"],
            "source_file_year": [2024],
            "source_row_index": [0],
        }
    )

    result = clean.clean_ksu(raw, year=2024, dataset_url="https://example.org/{year}.json")
    assert pd.isna(result.loc[0, "doi"])
    assert pd.isna(result.loc[0, "abstract"])


def test_clean_kfupm_keeps_missing_doi_for_validation():
    raw = pd.DataFrame(
        [
            {
                "uuid": "1",
                "title": "In scope",
                "authors": "A B",
                "date_issued": "2024-05-06",
                "abstract": None,
                "topics": None,
                "journal": "J",
                "doi_raw": "10.1016/j.test.2024.01",
                "url": "https://pure.example/1",
                "genre": "Article",
                "organisational_units": ["Department of Computer Engineering"],
            },
            {
                "uuid": "2",
                "title": "Other department",
                "authors": "C D",
                "date_issued": "2024",
                "abstract": None,
                "topics": None,
                "journal": "J",
                "doi_raw": "10.1016/j.test.2024.02",
                "url": "https://pure.example/2",
                "genre": "Article",
                "organisational_units": ["Department of Information and Computer Science"],
            },
            {
                "uuid": "3",
                "title": "Editorial",
                "authors": "E F",
                "date_issued": "2024",
                "abstract": None,
                "topics": None,
                "journal": "J",
                "doi_raw": "10.1016/j.test.2024.03",
                "url": "https://pure.example/3",
                "genre": "Editorial",
                "organisational_units": ["Department of Computer Engineering"],
            },
            {
                "uuid": "4",
                "title": "No DOI",
                "authors": "G H",
                "date_issued": "2024",
                "abstract": None,
                "topics": None,
                "journal": "J",
                "doi_raw": None,
                "url": "https://pure.example/4",
                "genre": "Article",
                "organisational_units": ["Department of Computer Engineering"],
            },
        ]
    )

    result = clean.clean_kfupm_pure(
        raw,
        department="Department of Computer Engineering",
        university="KFUPM",
        source_label="KFUPM Pure (OAI-PMH)",
        min_year=2023,
        max_year=2026,
        excluded_genres=["Editorial", "Comment/debate"],
    )

    assert result["research_id"].tolist() == ["KFUPM_1", "KFUPM_4"]
    assert result.loc[0, "publication_date"] == "2024-05-06"
    assert pd.isna(result.loc[1, "doi"])
    assert pd.isna(result.loc[1, "publication_date"])


def test_manual_enrichment_only_fills_missing_values(tmp_path):
    frame = pd.DataFrame(
        {
            "research_id": ["KSU_2024_69", "KSU_2024_70"],
            "doi": [pd.NA, "10.1016/j.existing.2024"],
            "abstract": [pd.NA, "Kept"],
        }
    )
    decisions = tmp_path / "enrichment.json"
    decisions.write_text(
        '[{"research_id": "KSU_2024_69", "doi": "10.1109/TCE.2023.3325131",'
        ' "abstract": "Added"},'
        ' {"research_id": "KSU_2024_70", "doi": "10.1016/j.existing.2024", "abstract": "Ignored"}]',
        encoding="utf-8",
    )

    result, log = clean.apply_manual_enrichment(frame, decisions)
    assert result.loc[0, "doi"] == "10.1109/tce.2023.3325131"
    assert result.loc[0, "abstract"] == "Added"
    assert result.loc[1, "abstract"] == "Kept"
    assert log[0]["fields_added"] == ["doi", "abstract"]


def test_manual_enrichment_refuses_conflicting_doi(tmp_path):
    frame = pd.DataFrame(
        {
            "research_id": ["KSU_2024_69"],
            "doi": ["10.1016/j.original.2024"],
            "abstract": [pd.NA],
        }
    )
    decisions = tmp_path / "enrichment.json"
    decisions.write_text(
        '[{"research_id": "KSU_2024_69", "doi": "10.1016/j.different.2024"}]',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        clean.apply_manual_enrichment(frame, decisions)


def test_repair_ksu_json_preserves_raw_and_creates_valid_copy(tmp_path):
    source = tmp_path / "raw.json"
    output = tmp_path / "repaired.json"
    source.write_text('[{"text": "F\\\t-score"}]', encoding="utf-8")

    original = source.read_bytes()
    repaired_path, count = extract.repair_ksu_json(source, output)

    assert source.read_bytes() == original
    assert count == 1
    assert repaired_path == output
    assert json.loads(output.read_text(encoding="utf-8"))[0]["text"] == "F\\\t-score".replace("\\\t", "\\\t")
