# Saudi Technology Research Data Hub

A data engineering project that collects, cleans, validates, and filters research metadata from Saudi universities to support exploration of technology-related research.

The repository keeps the full trail: raw source files, intermediate datasets, validation results, rejection reports, and filtering evidence. The whole pipeline can be re-run from the raw files with a single command.

## 1. Project Scope

The project covers research metadata within the 2023–2026 scope, subject to source availability.

The workflow is:

1. Extract research metadata from university repositories, APIs, and institutional datasets.
2. Clean values and map source fields to a shared 13-column schema.
3. Validate required fields and keep every rejected record with its reason.
4. Select technology-related research using keyword matching.
5. Join the validated datasets into a shared final file.
6. Document every excluded contribution and its limitations.

Coverage is not complete for every university or year. Missing coverage must not be read as an absence of research activity.

## 2. Current Results

Produced by `python main.py` from the raw files:

| Stage | KAUST | KFUPM | KSU |
|---|---:|---:|---:|
| Cleaned | 1,052 | 415 | 3,556 |
| Validated | 938 | 415 | 1,483 |
| Rejected | 114 | 0 | 2,073 |

| Output | Value |
|---|---:|
| Joined validated records | 2,836 |
| Technology candidates (final dataset) | **1,817** |
| No keyword match | 1,019 |
| DOIs shared between two universities | 2 |
| Automated tests passing | 90 |

Final dataset by university: KSU 1,483 · KFUPM 211 · KAUST 123.
Final dataset by year: 2023 → 339 · 2024 → 39 · 2025 → 1,372 · 2026 → 63.

These counts describe the current execution. Any regenerated output must be checked against a fresh run rather than against this table.

## 3. Team Contributions

| Contributor | University scope | Contribution |
|---|---|---|
| Rana Ayman | KAUST and KFUPM | Extraction, cleaning, validation, technology filtering, integration |
| Rana Saad | KSU | Source inspection, cleaning, validation, reviewed enrichment, technology selection |
| Aryam Alotaibi | PNU | Extraction, metadata enrichment, cleaning, validation, filtering workflow |

Merging a contributor's Git branch into `main` does not automatically include that contributor's records in `data/processed/final.csv`. Inclusion is an explicit decision recorded below.

## 4. Dataset Inclusion Status

| Dataset | Status | Explanation |
|---|---|---|
| KAUST | Included | Repository export plus Crossref records |
| KFUPM | Included | KFUPM Pure (OAI-PMH); replaced the older ePrints collection |
| KSU | Included | Annual institutional datasets with reviewed enrichment |
| PNU | Excluded | Enrichment could not be reliably linked to the original records (section 9) |

## 5. Data Sources

### KAUST

Two inputs, each mapped to the shared schema:

- **Repository export** (`KAUST_2023_raw.csv`) for 2023. Partial dates in this export are completed to the first month or day; the original value is kept in the raw file, and the rule is documented in `src/clean.py`.
- **Crossref** (`KAUST_Crossref_2024_2025_page_*.json`) for 2024–2025, filtered by the KAUST ROR affiliation.

Repository and Crossref records use different publication-year conventions. These differences are reviewed, not silently overwritten.

Crossref returns versioned DOIs for some preprint platforms, so a small number of records share a title with a different DOI. They are kept and flagged for review.

### KFUPM

The original KFUPM ePrints data (48 thesis records) was removed at the source and could not be rebuilt. It was replaced by **KFUPM Pure**, harvested through OAI-PMH.

| Item | Value |
|---|---|
| Endpoint | `https://pure.kfupm.edu.sa/ws/oai` (no authentication) |
| Format | MODS 3.8 |
| Raw harvest | 16,256 records across 165 XML pages (2023–2026) |
| Department filter | `Department of Computer Engineering` (Pure organisational unit, exact match) |
| After filters | 449 → 423 with DOI → **415** after removing `Editorial` and `Comment/debate` |

The free-text `affiliation` field is not used for the department filter: it is author-typed and contains departments of other universities.

`publication_date` is about 80% empty because Pure supplies only a year or year-month for most records. No month or day is invented.

### KSU

KSU metadata comes from the institutional annual research datasets for 2023, 2024, and 2025.

Documented source limitations:

- `publication_year` is the year of the annual dataset file; the records carry no publication date.
- `url` is the annual dataset download link, not a per-publication page. KSU does not publish one.
- The 2024 file contains no DOI or abstract fields, so those records cannot pass the required-field policy.
- The 2025 file needed a documented JSON repair before it could be parsed (`data/interim/ksu_2025_repair_note.json`).

Four records received reviewed enrichment (DOI from Crossref, abstracts from OpenAlex) after manual verification of title, authors, and journal. The decisions are in `data/interim/ksu_manual_enrichment.json` and are applied automatically; an existing value is never overwritten, and a conflicting DOI raises an error.

## 6. Shared Schema

The consolidated dataset uses these 13 columns in this order:

| Column | Type | Required | Rule |
|---|---|---|---|
| `research_id` | String | Yes | Non-empty and unique |
| `university` | String | Yes | Matches the source's university |
| `title` | String | Yes | Non-empty research title |
| `authors` | String | Yes | Non-empty author information |
| `publication_year` | Integer | Yes | Whole year within 2023–2026 |
| `publication_date` | Date | No | Valid `YYYY-MM-DD` when available |
| `abstract` | String | No | Abstract text when available |
| `research_field` | String | No | Research field when available |
| `tech_category` | String | No | Technology category when assigned |
| `journal` | String | No | Journal or venue when available |
| `doi` | String | Yes | Bare DOI, `10.xxxx/...`, lowercase |
| `url` | String | Yes | Valid HTTP or HTTPS URL |
| `source` | String | Yes | Non-empty source identifier |

`data/processed/final.csv` carries two derived columns after these 13: `has_doi` and `abstract_word_count`.

A record with a missing required value is excluded from the accepted dataset and kept in the rejection report with its reason. This policy can exclude legitimate research that has no DOI; that reflects the project's schema requirement, not the quality of the research.

Missing optional values are allowed and are never invented.

`university` holds the standard codes `KAUST`, `KFUPM`, and `KSU`. The KFUPM records are stored in Pure under the full university name; the code is normalized during cleaning, and the source system is still identifiable through `source`.

## 7. Cleaning and Validation

Cleaning is implemented once, in `src/clean.py`:

- Trim whitespace and convert empty strings to missing values.
- Treat `n/a`, `none`, `null`, and `nan` as missing.
- Normalize DOIs to the bare lowercase form before comparison.
- Parse partial dates per the documented rule for each source.
- Remove duplicates by keeping the most complete record, then the most recently modified one.
- Strip HTML and JATS markup from Crossref titles and abstracts.

Validation is implemented once, in `src/schema.py`, and every source is judged by the same rules: required fields, university match, year range, DOI syntax, URL structure, real calendar dates, and unique identifiers. Every failed rule is listed for the record, and rejected records keep all their original values.

### What validation does not prove

Passing schema validation confirms structure only. It does not prove that a DOI belongs to the supplied title, that the authors belong to the record, that the affiliation is correct, that the year uses the intended convention, that a publication is genuinely technology-related, or that it carries no retraction notice.

## 8. Technology Filtering

One keyword list and one matching implementation, in `src/transform.py`.

Matching rules:

1. Case-insensitive.
2. Whitespace and hyphen variations normalized, so `deep-learning` matches `deep learning`.
3. Whole-word boundaries, so `iot` does not match "riot" and `ai` does not match "Saudi".
4. `computer vision syndrome` is removed before matching; it is an eye condition, not computer vision research.
5. Matched terms are kept for review; records with no match are preserved in a separate file.

Searchable fields differ by source, because the sources differ:

- KAUST and KFUPM: `title` and `abstract`.
- KSU: `Article Title` and `Author Keywords` on the raw records, since KSU publishes keywords instead of a usable abstract in every year. The matched terms are written to `data/interim/ksu_provenance.json` rather than stored as a verified classification.

A keyword match marks a candidate, not a confirmed classification. A record without a match is not necessarily non-technical.

Evidence files:

```text
data/processed/technology_filter/filter_review.csv
data/processed/technology_filter/no_keyword_match.csv
```

## 9. PNU Contribution: Exclusion Decision

Aryam's work is preserved in the repository for audit and reproducibility, but the reviewed PNU output is excluded from `data/processed/final.csv`.

**Primary reason — enrichment index misalignment.** The workflow filtered source records while keeping their original DataFrame indices, then assigned Crossref results held in a new DataFrame with a sequential index:

```python
pnu_enriched[
    ["authors", "doi", "url", "publication_date", "abstract", "journal"]
] = crossref_df
```

Pandas aligns this assignment by index label. Because the two frames no longer represented the same records at the same labels, enriched values were attached to the wrong research records: 1,540 of 1,544 final rows, about 99.74%, are affected. Populated fields that pass format checks are therefore still unreliable.

Supporting findings in the same reviewed output:

- Crossref candidates were accepted by first-result position, with no verification against title, authors, or year.
- 92 rows, about 5.96%, fell into duplicate DOI groups, some with different titles.
- 383 rows, about 24.81%, had a publication-date year different from `publication_year`.
- The technology filter used unrestricted substring matching, so terms such as `ai` matched inside unrelated words; with word boundaries, 731 of 1,544 rows would not pass.

These groups overlap, so their percentages must not be added into a single error rate.

**Requirements for future inclusion:** return to the original source records, keep a stable identifier per record, rebuild enrichment as a join on that identifier, verify each Crossref candidate, investigate duplicate DOIs and year inconsistencies, apply the agreed filter rules, and rerun validation. Resetting the index alone does not repair metadata that was already misassigned.

## 10. Repository Structure

```text
saudi-tech-research/
├── data/
│   ├── raw/                     # unchanged source files (frozen snapshot)
│   ├── interim/                 # cleaned, validated, rejected, provenance
│   └── processed/
│       ├── final.csv            # consolidated dataset
│       ├── shared_doi_review.csv
│       ├── run_summary.json
│       └── technology_filter/
├── notebooks/                   # analysis, profiling, and the decisions behind the rules
│   ├── 01_extract.ipynb
│   ├── 02_profile_clean.ipynb
│   ├── 03_schema_validate.ipynb
│   ├── 04_join_transform.ipynb
│   ├── 05_team_merge.ipynb
│   ├── KFUPM_Pure_extract_clean.ipynb
│   └── hasaniah_ksu_inspect.ipynb
├── src/                         # the pipeline implementation
│   ├── config.py                # config.yaml and path resolution
│   ├── extract.py               # reading raw CSV, JSON, and MODS XML
│   ├── profile.py               # missing values, duplicates, year distribution
│   ├── clean.py                 # cleaning and mapping to the shared schema
│   ├── schema.py                # schema definition and validation rules
│   └── transform.py             # technology filter, join, derived columns
├── tests/                       # 90 tests over the rules above
├── config.yaml                  # paths, year range, keyword list, source settings
├── main.py                      # runs the whole pipeline
├── requirements.txt
└── README.md
```

The notebooks show the analysis and justify the rules; `src/` holds the implementation they call. Keeping one implementation is deliberate: the team cannot end up with two different versions of the filter or the validator.

## 11. Running the Workflow

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the pipeline:

```bash
python main.py                    # every source
python main.py --sources kaust    # one or more sources
python main.py --no-tech-filter   # skip the keyword filter
```

Run the tests:

```bash
python -m pytest tests -q
```

The extraction step is not repeated by `main.py`: the files under `data/raw` are the frozen snapshot the project works from. Re-downloading them is done in `notebooks/01_extract.ipynb` and `notebooks/KFUPM_Pure_extract_clean.ipynb`, which is deliberate, since re-harvesting changes the record counts.

To use the same logic inside a notebook:

```python
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

from src import clean, extract, profile, schema, transform
```

After a run, check the row count and university distribution, the column order, missing required values, duplicate identifiers, shared DOI cases, and the year range. `data/processed/run_summary.json` records the counts of the last run.

Close any CSV open in Excel before running, or the write will fail.

## 12. Known Limitations and Pending Work

**Uneven coverage.** The sources differ in collection method, year coverage, and available metadata. Raw counts must not be used to rank university research activity. KSU dominates the final dataset because its annual files are institution-wide, while KFUPM is limited to one department.

**`tech_category` is empty** for every record. The technology filter selects candidates; it does not assign a category.

**Publication-year interpretation.** Deposit dates, online publication dates, issue dates, and annual reporting years differ across sources. A single analytical year policy is still needed.

**Publication status.** Validation does not check retractions or expressions of concern. The KSU review found records carrying status notices; they need explicit treatment before analysis.

**Cross-university duplicates.** A co-authored paper legitimately appears under two universities. Those records are kept, and the cases are written to `data/processed/shared_doi_review.csv` for review rather than removed. The current run contains two such DOIs, one shared between KAUST and KSU and one between KSU and KFUPM.

**Filter fields differ by source.** KSU is matched on author keywords and KAUST/KFUPM on abstracts, because of what each source publishes. This is documented rather than hidden, but it does mean the selection is not perfectly uniform.

**PNU remediation.** The preserved PNU workflow needs correction and a fresh quality assessment before it can be included.

## 13. Intended Use

The dataset supports exploratory analysis and the development of data engineering workflows.

It is not an exhaustive inventory of Saudi research, a university ranking, or a guarantee of publication quality. Interpretation should account for source coverage, keyword-selection limits, shared affiliations, publication-year conventions, and publication-status notices.
