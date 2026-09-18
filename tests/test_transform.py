"""Tests for the technology filter, the join and the derived columns."""

import pandas as pd
import pytest

from src import transform
from src.schema import SCHEMA_COLUMNS


def record(**overrides) -> dict:
    """A schema-shaped record with sensible defaults."""
    base = {
        "research_id": "R1",
        "university": "KAUST",
        "title": "A title",
        "authors": "Author, A",
        "publication_year": 2024,
        "publication_date": "2024-01-01",
        "abstract": "",
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
    return pd.DataFrame(list(records), columns=SCHEMA_COLUMNS)


# --------------------------------------------------------------------------
# Whole-word matching
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title",
    [
        "Deep learning for X",
        "DEEP-LEARNING for X",          # hyphen
        "Deep  learning for X",         # double space
        "A study of IoT devices",
    ],
)
def test_filter_keeps_real_technology_records(title):
    selected, _, _ = transform.filter_technology(frame(record(title=title)))
    assert len(selected) == 1


@pytest.mark.parametrize(
    "title",
    [
        "Riot control and public order",       # contains "iot"
        "Rainfall and pain assessment",
        "Saudi maintained again the trial",    # the classic "ai" substring trap
    ],
)
def test_filter_does_not_match_fragments_inside_other_words(title):
    selected, excluded, _ = transform.filter_technology(frame(record(title=title)))
    assert len(selected) == 0
    assert len(excluded) == 1


def test_computer_vision_syndrome_is_not_computer_vision_research():
    selected, _, _ = transform.filter_technology(
        frame(record(title="Computer vision syndrome among students"))
    )
    assert len(selected) == 0


def test_computer_vision_syndrome_paper_still_matches_another_real_term():
    selected, _, _ = transform.filter_technology(
        frame(record(title="Computer vision syndrome detection",
                     abstract="Using deep learning"))
    )
    assert len(selected) == 1


def test_filter_searches_the_abstract_too():
    selected, _, review = transform.filter_technology(
        frame(record(title="A clinical study", abstract="We used random forest models"))
    )
    assert len(selected) == 1
    assert "random forest" in review.loc[0, "matched_terms"]


def test_filter_handles_missing_title_and_abstract():
    selected, excluded, _ = transform.filter_technology(
        frame(record(title=None, abstract=None))
    )
    assert len(selected) == 0
    assert len(excluded) == 1


def test_terms_never_match_across_the_field_boundary():
    """A title ending in "machine" plus an abstract starting with "learning"."""
    selected, _, _ = transform.filter_technology(
        frame(record(title="A new machine", abstract="learning outcomes in schools"))
    )
    assert len(selected) == 0


def test_review_file_lists_every_record_with_its_matched_terms():
    data = frame(
        record(research_id="R1", title="Blockchain in logistics"),
        record(research_id="R2", title="Soil chemistry"),
    )
    _, _, review = transform.filter_technology(data)

    assert review["selected"].tolist() == [True, False]
    assert review.loc[0, "matched_terms"] == "blockchain"
    assert review.loc[1, "matched_terms"] == ""


def test_raw_filter_uses_the_source_columns_and_keeps_the_row_order():
    """KSU has author keywords instead of an abstract."""
    raw = pd.DataFrame({
        "Article Title": ["Soil study", "Land cover mapping", "Bridge design"],
        "Author Keywords": ["soil", "multilayer perceptron; Markov", "concrete"],
        "source_row_index": [0, 1, 2],
    })

    selected, matches = transform.filter_raw_records(
        raw, fields=["Article Title", "Author Keywords"]
    )

    assert selected["source_row_index"].tolist() == [1]
    assert matches.iloc[1] == ["multilayer perceptron"]


# --------------------------------------------------------------------------
# Join
# --------------------------------------------------------------------------
def test_combine_sources_stacks_the_universities():
    combined = transform.combine_sources([
        frame(record(research_id="A1", university="KAUST")),
        frame(record(research_id="B1", university="KSU")),
    ])

    assert len(combined) == 2
    assert combined["university"].tolist() == ["KAUST", "KSU"]
    assert list(combined.columns) == SCHEMA_COLUMNS


def test_combine_sources_refuses_duplicate_research_ids():
    with pytest.raises(ValueError):
        transform.combine_sources([
            frame(record(research_id="A1")),
            frame(record(research_id="A1")),
        ])


def test_combine_sources_ignores_empty_inputs():
    combined = transform.combine_sources([
        frame(record(research_id="A1")),
        pd.DataFrame(columns=SCHEMA_COLUMNS),
    ])
    assert len(combined) == 1


def test_shared_doi_report_reports_co_authored_papers_without_dropping_them():
    """The same paper can legitimately belong to two universities."""
    combined = transform.combine_sources([
        frame(record(research_id="A1", university="KAUST", doi="10.1016/j.shared.2024")),
        frame(record(research_id="B1", university="KSU", doi="10.1016/j.shared.2024")),
        frame(record(research_id="C1", university="KSU", doi="10.1016/j.own.2024")),
    ])

    shared = transform.shared_doi_report(combined)

    assert shared["doi"].unique().tolist() == ["10.1016/j.shared.2024"]
    assert len(shared) == 2
    assert len(combined) == 3          # nothing was removed


# --------------------------------------------------------------------------
# Derived columns
# --------------------------------------------------------------------------
def test_apply_transformations_adds_the_three_derived_columns():
    result = transform.apply_transformations(
        frame(
            record(research_id="A1", abstract="one two three", publication_year="2024"),
            record(research_id="A2", abstract=None, doi=None),
        )
    )

    assert result["publication_year"].dtype == "Int64"
    assert result.loc[0, "abstract_word_count"] == 3
    assert result.loc[1, "abstract_word_count"] == 0
    assert result.loc[0, "has_doi"] is True or bool(result.loc[0, "has_doi"])
    assert not bool(result.loc[1, "has_doi"])


def test_apply_transformations_does_not_change_the_row_count():
    data = frame(record(research_id="A1"), record(research_id="A2"))
    assert len(transform.apply_transformations(data)) == len(data)
