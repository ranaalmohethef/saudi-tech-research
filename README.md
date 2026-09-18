# Saudi Technology Research Data Hub

A data engineering project that collects, profiles, cleans, validates and combines research metadata from Saudi universities into a common dataset for technology research analysis.

## Scope and current status

The project covers research dated 2023–2026. Source coverage varies by university and does not represent every publication produced by that institution.

The Rana Ayman and Rana Saad branches have been merged into `main`. Branch integration brings project files together; it does not itself create a combined research dataset.

### Latest inspected input snapshots

| Dataset | Records | Status |
|---|---:|---|
| `data/processed/final_rana.csv` | 123 | Technology candidates from KAUST; 119 dated 2023, 2 dated 2024 and 2 dated 2025 |
| KSU subset of Rana Saad's accepted validation output | 1,477 | Accepted KSU technology candidates |
| `data/interim/KFUPM_cleaned.csv` | 415 | New KFUPM Pure records awaiting consistent downstream integration |
| PNU | Not included | No PNU dataset approved for this combined output |

The proposed KAUST + KSU merge produces **1,600 university-associated records with 1,599 distinct DOI values** from these snapshots. Execution and saving of the team merge must be confirmed before treating these as generated output counts.

The shared DOI `10.5194/hess-29-4983-2025` appears in both KAUST and KSU with matching research titles. Both university associations are retained. A row is a source research record associated with a university, not necessarily a globally unique publication.

## Sources

| Source | Format | Role |
|---|---|---|
| KAUST Research Repository | CSV | Repository metadata used for the KAUST 2023 collection |
| Crossref | JSON / REST API | KAUST 2024–2025 collection using institutional ROR filtering |
| KSU Open Data | Annual JSON datasets | Research records reported in 2023–2025 annual datasets |
| KFUPM Pure | XML / OAI-PMH / MODS | New Computer Engineering research collection for 2023–2026 |
| KFUPM ePrints | JSON | Historical collection of 48 theses; excluded from its validation run because DOI was missing |
| PNU Open Data | Excel | Source retained for separate preparation and review |
| OpenAlex and ORCID | Enrichment trials | Supporting matching and metadata review; not independent publications added to the final dataset |

Relevant service addresses:

- [KAUST Repository](https://repository.kaust.edu.sa/)
- [Crossref API](https://api.crossref.org/works)
- [KFUPM Pure](https://pure.kfupm.edu.sa/)
- [KFUPM OAI-PMH endpoint](https://pure.kfupm.edu.sa/ws/oai)

Preserve source responses and provenance alongside cleaned records. A DOI obtained through enrichment must identify the same work. A related journal article cannot supply the DOI for a thesis.

## Common schema

The combined dataset uses these 13 columns in this order:

| Column | Type | Required | Rule |
|---|---|---|---|
| `research_id` | String | Yes | Non-empty stable identifier; unique in the combined inputs |
| `university` | String | Yes | Standardized university label: KAUST, KFUPM, KSU or PNU |
| `title` | String | Yes | Non-empty research title |
| `authors` | String | Yes | Non-empty author information |
| `publication_year` | Integer | Yes | Whole year from 2023 through 2026 |
| `publication_date` | Date string | No | Real calendar date written as YYYY-MM-DD when complete |
| `abstract` | String | No | Available abstract text |
| `research_field` | String | No | Available subject or field |
| `tech_category` | String | No | Assigned technology category, when available |
| `journal` | String | No | Journal, proceedings or source title |
| `doi` | String | Yes | Bare DOI, trimmed and normalized to lowercase |
| `url` | String | Yes | HTTP(S) URL with a hostname and no whitespace |
| `source` | String | Yes | Source label identifying the record's provenance |

Blank values and placeholders such as `none`, `null`, `nan`, `n/a`, `na`, `<na>` and `NaT` are treated as missing, ignoring case and surrounding whitespace.

These are the shared data contract requirements. Individual notebooks must be checked against this contract; documenting a rule does not establish that every notebook currently enforces it.

### Dates and publication years

- Never invent a month or day when only a publication year is known.
- Missing optional dates remain empty.
- Date formatting changes must not silently change the reported publication year.
- KSU uses the annual source dataset's reported year. API year differences are preserved for review rather than automatically replacing that year.
- Repository, online publication, conference and print dates can differ. Resolve the publication-year basis before using disputed records in year-based comparisons.

## Pipeline and files

The workflow is extraction, profiling and cleaning, schema validation, technology screening, transformation, then team combination.

| File or folder | Purpose |
|---|---|
| `data/raw/` | Original source files and saved API responses |
| `data/interim/` | Cleaned data, validation results and rejected records |
| `data/processed/` | Transformed datasets and filter review outputs |
| `notebooks/01_extract.ipynb` | Inspect the merged extraction code before running; source refresh can change inputs |
| `notebooks/02_profile_clean.ipynb` | KAUST and historical KFUPM cleaning |
| `notebooks/03_schema_validate.ipynb` | KAUST / KFUPM validation |
| `notebooks/04_join_transform.ipynb` | Technology screening and generation of `final_rana.csv` |
| `notebooks/hasaniah_ksu_inspect.ipynb` | KSU inspection and preparation |
| `notebooks/03_schema_validate_hasaniah.ipynb` | Rana Saad's validation workflow |
| `notebooks/KFUPM_Pure_extract_clean.ipynb` | Separate preparation of the new KFUPM Pure collection |
| `notebooks/05_team_merge.ipynb` | Team merge notebook to add/run using the agreed merge code |
| `README_rana_saad.md` | Historical validation documentation preserved during branch integration |
| `src/`, `main.py`, `tests/` | Integration scaffolding; not documented as a completed automated pipeline |

## Running the current team merge

### Environment

From the project root on Windows PowerShell:

```powershell
# Create the environment only if it does not already exist.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Open the project in VS Code and select its `.venv` Python environment for the notebook kernel. Run notebook cells in order. Source notebooks generally use paths relative to `notebooks/`; confirm the working directory before running them.

### Combine existing accepted snapshots

Use these inputs:

1. `data/processed/final_rana.csv`
2. `data/interim/rana_saad_validation/four_sources_20260913T112108887260Z/validated.csv`

The second file contains **2,405 records: 1,477 KSU and 928 KAUST**. Select **KSU only** from this file. Appending its entire contents would reintroduce another KAUST collection and bypass the selected KAUST final output.

The team merge should:

1. Check that both inputs exist and contain the common schema.
2. Select the 13 shared columns, excluding local helper columns.
3. Select KSU from Rana Saad's accepted output.
4. Concatenate the selected inputs vertically using `pd.concat`.
5. Normalize missing values and DOI casing.
6. Check mandatory values, whole publication years, DOI syntax, URL structure and full dates.
7. Reject duplicate research identifiers and duplicate university/DOI pairs for review.
8. Preserve cross-university DOI matches in a review file.
9. Save outputs only after these checks pass.

Expected outputs after successful execution:

| Output | Purpose |
|---|---|
| `data/processed/final.csv` | Combined 13-column dataset |
| `data/processed/shared_doi_review.csv` | Records whose DOI appears more than once across universities |

Do not rerun extraction simply to combine already accepted files. Refreshing a source is a separate operation and requires revalidation of all affected downstream outputs.

## Technology screening

Technology filtering selects candidates using documented keyword rules. It does not prove relevance or completeness.

- KAUST screening searches the title and abstract separately.
- Text is normalized for capitalization, Unicode and hyphens.
- Terms use word boundaries, avoiding broad substring matches such as `ai` inside unrelated words.
- The phrase `computer vision syndrome` is excluded from matching by itself; another relevant term can still select the record.
- KSU candidate selection also uses source author keywords. Results therefore need not match a title-and-abstract-only filter.

Examples of terms include artificial intelligence, machine learning, neural networks, cybersecurity, robotics, internet of things, cloud computing and software engineering. The executable notebook holds the full list.

Preserve review outputs such as `filter_review.csv` and `no_keyword_match.csv`. A record with no keyword match is not automatically proven nontechnical.

## Transformations

Local processing may derive:

| Column | Meaning |
|---|---|
| `has_doi` | Whether DOI is present; expected to be true for accepted records |
| `abstract_word_count` | Whitespace-separated word count; zero for missing abstracts |

These helper columns belong to local outputs such as `final_rana.csv`. The proposed team output contains the 13 shared columns. Additional derived fields can be added consistently later.

## KFUPM Pure integration: remaining work

The supplied Pure cleaned file has **415 records**, but the supplied KFUPM validation outputs still describe the historical **48 ePrints theses**: zero accepted and 48 rejected for missing DOI. These are different datasets and must not be reported as one validation run.

Before integrating Pure:

1. Separate or version Pure and ePrints outputs. Both preparation workflows currently target `data/interim/KFUPM_cleaned.csv`, so rerunning one can overwrite the other's input.
2. Normalize the Pure university label from `King Fahd University of Petroleum and Minerals` to `KFUPM` in the preparation code. The current validator expects `KFUPM`.
3. Validate the Pure records against the common contract, then regenerate its accepted and rejected files.
4. Apply the agreed technology selection and transformation steps.
5. Rebuild the team merge and update verified counts.

The current 123-row `final_rana.csv` contains KAUST only. The 415 Pure records are not part of the expected 1,600-row KAUST + KSU merge.

## Quality limitations and review items

- Missing optional abstracts, journals, research fields or technology categories are allowed; report their completeness when analyzing them.
- DOI syntax checks do not prove that a DOI resolves or belongs to the stated title. Enrichment requires identity checks against title, year and authors where available.
- KSU URLs point to annual source datasets, not necessarily to individual articles.
- Prior quality review identified publication-year differences that require an explicit source-date policy, plus publication-status flags in KSU. Consult the review evidence before presenting records as current, unretracted scientific evidence.
- The inspected KAUST/KFUPM validator still needs stronger whole-year, URL-hostname and placeholder checks. Its KAUST invocation currently caps the year at 2025, although the shared project range ends in 2026.
- Historic validation counts remain useful evidence but are not current team output counts.
- PNU must undergo separate verification before entering the combined dataset.
- A successful Git merge confirms file integration, not data validity or end-to-end pipeline execution.

## Next integration work

- Confirm execution of the team merge and record its actual output counts.
- Complete KFUPM Pure integration and PNU review.
- Harmonize validators and publication-year policies across sources.
- Consolidate source-specific notebooks into reusable modules.
- Connect a repeatable pipeline through `main.py` and migrate meaningful checks into `tests/`.
- Document source refresh versions and retain rejected records with reasons.

## Team

- Rana Ayman Almohethef — KAUST and KFUPM
- Rana Saad AlHasaniah — KSU
- Aryam Saad Alotaibi — PNU

## Intended use

The dataset supports exploration of technology research topics, university-associated publication activity and metadata coverage. Interpret university and year comparisons in light of source coverage, shared publications, missing optional metadata and unresolved review items.
