# Saudi Technology Research Data Hub

## Project Overview

The Saudi Technology Research Data Hub is a data engineering project that collects, cleans, standardizes, validates, and combines research metadata from selected Saudi universities and trusted scholarly data sources.

Research information is distributed across university repositories, Excel and CSV files, and external APIs. These sources have different formats, structures, naming conventions, and levels of completeness.

The purpose of this project is to create a consistent and analysis-ready dataset that can support the analysis of technology-related research across Saudi universities.

---

## Project Objective

The project aims to build a repeatable data pipeline that:

1. Collects research metadata from multiple Saudi university sources.
2. Profiles the raw datasets and identifies data-quality issues.
3. Cleans and standardizes data from different formats.
4. Converts source-specific structures into a common schema.
5. Validates records using defined schema and quality rules.
6. Combines validated datasets.
7. Applies transformation rules.
8. Produces an analysis-ready dataset for future analysis.

---

## Data Sources

The project uses a combination of university datasets, institutional repositories, and public scholarly APIs.

| Source | Source Type | Format | Authentication | Project Use |
|---|---|---|---|---|
| Princess Nourah University (PNU) | University Open Data | Excel | None | Research publications for 2023–2025 |
| King Saud University (KSU) | University Open Data | JSON | None | Annual research datasets for 2023–2025; technology candidates selected using documented keyword rules |
| KAUST Research Repository | Institutional Research Repository | CSV | None | KAUST research records |
| KFUPM ePrints | Institutional Research Repository | JSON | None | Computer Engineering research records for 2023–2026 |
| Crossref REST API | Public Scholarly API | JSON | None | Research metadata and KAUST 2024–2025 records |
| OpenAlex API | Public Scholarly API | JSON | Anonymous access used for the recorded trial; rate limits may apply | Enrichment only; matched metadata supplements existing publications rather than creating separate research records |

Detailed information about each source, including URLs, file paths, licences, sizes, and known issues, is documented in the project requirements workbook.

---

## Pipeline Overview

The current project pipeline follows these stages:

```text
Extract
   ↓
Profile & Clean
   ↓
Schema Validation
   ↓
Join & Transform
   ↓
Processed Dataset
```

Each stage reads its input from the `data/` directory and writes its output back to the appropriate folder.

---

# Task 1 — Data Extraction

The first stage collects raw research data from university datasets, repositories, and APIs.

The original source data is preserved without applying cleaning or transformation.

Raw files are stored in:

```text
data/raw/
```

The extraction stage includes:

- Reading CSV and Excel source files
- Reading JSON repository records
- Retrieving data from APIs
- Preserving original source data
- Recording source information and provenance

Main extraction notebook:

```text
notebooks/01_extract.ipynb
```

Additional source-specific notebooks may also be used where necessary.

---

# Task 2 — Data Profiling and Cleaning

The second stage profiles the raw data and identifies data-quality issues.

Profiling includes:

- Column names
- Row and column counts
- Data types
- Missing values
- Percentage of missing values
- Unique values
- Sample values
- Duplicate records
- Nested fields
- Inconsistent text
- Date-format differences

Cleaning activities include:

- Flattening nested structures
- Standardizing column names
- Cleaning whitespace
- Removing unwanted markup
- Standardizing DOI values
- Parsing dates
- Handling missing values
- Reviewing duplicate records
- Standardizing source-specific fields

Cleaned datasets are stored in:

```text
data/interim/
```

Main cleaning notebook:

```text
notebooks/02_profile_clean.ipynb
```

---

## Data Quality Rules

The project follows several general data-quality principles:

- Raw source files must remain unchanged.
- Missing dates must not be invented.
- If only the publication year is available, the full publication date remains empty.
- Duplicate records must be reviewed before removal.
- Stable source identifiers are preferred for `research_id`.
- Missing optional metadata does not automatically cause a record to be rejected.
- Text formatting is standardized where needed.
- Different source structures are converted into a shared schema.

---

# Task 3 — Schema Definition and Validation

After cleaning, the datasets are validated against a common schema.

The validation process checks:

- Required fields
- Missing values
- Publication-year ranges
- URL format
- DOI format
- Publication-date validity
- University values
- Duplicate `research_id` values

Rows that pass validation are saved as validated records.

Rows that fail validation are routed to rejected datasets together with the reason for rejection.

Main validation notebook:

```text
notebooks/03_schema_validate_hasaniah.ipynb
```

---

## Common Schema

All university datasets are standardized into the following common schema:

| Column | Data Type | Nullable | Validation Rule |
|---|---|---|---|
| research_id | String | No | Non-empty and unique across validation inputs |
| university | String | No | Must match the standardized university label for its source |
| title | String | No | Non-empty after trimming whitespace |
| authors | String | No | Non-empty after trimming whitespace |
| publication_year | Integer | No | Four-digit year from 2023 through 2026 |
| publication_date | Date string | Yes | When present, a real calendar date in YYYY-MM-DD format; never invent a month or day |
| abstract | String | Yes | Preserve available abstract text; missing values do not reject the row |
| research_field | String | Yes | Preserve when available; missing values do not reject the row |
| tech_category | String | Yes | Preserve when assigned; missing values do not reject the row |
| journal | String | Yes | Preserve when available; missing values do not reject the row |
| doi | String | No | Required normalized DOI matching the declared syntax check; syntax does not prove online resolution |
| url | String | No | HTTP or HTTPS URL with a hostname and no whitespace |
| source | String | No | Non-empty source label identifying the original data source |


Missing values include blanks, null values, and the text placeholders
`null`, `none`, `nan`, and `n/a`, ignoring capitalization and surrounding
whitespace. A missing mandatory value rejects the row. Missing optional
values do not reject it; populated DOI, URL, year and date values must
pass their applicable format checks.

Rejected rows are excluded from the accepted dataset and preserved
separately with all failure reasons. Original source files remain unchanged.
Verified enrichment may recover rejected records, which must then be
validated again.

For KSU, `publication_year` uses the annual dataset's reported year.
This basis is recorded in the provenance file. Conflicting API dates are
preserved separately and do not automatically replace that year.

### Publication Date Rule

A full publication date is only stored when the complete year, month, and day are available.

For example:

```text
2024-05-12
```

is stored as a valid publication date.

If the source provides only:

```text
2024
```

the value is stored in `publication_year`, while `publication_date` remains empty.

No missing month or day values are inferred.

---

# Task 4 — Join and Transformation

Validated datasets that follow the same common schema are combined into one dataset.

Because the university datasets contain the same standardized columns, they are combined vertically using:

```python
pd.concat()
```

rather than using a relational database-style join.

The combined dataset preserves one row per research record.

---

## Transformation Rules

The current transformation stage applies the following rules:

| Rule ID | Input | Output | Description |
|---|---|---|---|
| R1 | publication_year | publication_year | Convert publication year to nullable integer |
| R2 | doi | has_doi | Create a Boolean flag showing whether a DOI is available |
| R3 | abstract | abstract_word_count | Calculate the number of words in the abstract |

### R1 — Publication Year

The publication year is converted into a consistent nullable integer type.

```python
pd.to_numeric(
    publication_year,
    errors="coerce"
).astype("Int64")
```

### R2 — DOI Availability Flag

A new column called:

```text
has_doi
```

is created.

The value is:

```text
True
```

when a DOI exists and:
```text
False
```
when the DOI is missing.

Under the current validation rules, DOI is mandatory. Therefore,
`has_doi` is expected to be `True` for every accepted record.
Records without a DOI remain in the rejected dataset until a verified
DOI is recovered and the record passes validation again.

### R3 — Abstract Word Count

A new column called:

```text
abstract_word_count
```

stores the number of words in each research abstract.

If the abstract is missing, the word count is:

```text
0
```

---

## Rana Saad validation results

The current validation run covers KAUST, KFUPM and KSU.
PNU has not yet been included in this validation run.
OpenAlex is used for enrichment only.

The notebook is `notebooks/03_schema_validate_hasaniah.ipynb`.
All 43 validator tests passed.

### Results after reviewed enrichment

| Source | Input rows | Accepted | Rejected |
|---|---:|---:|---:|
| KAUST | 114 | 114 | 0 |
| KFUPM | 48 | 0 | 48 |
| KSU | 3535 | 1477 | 2058 |
| Total | 3697 | 1591 | 2106 |

Four reviewed KSU DOIs and three abstracts were added before this run.
All 48 KFUPM records remain rejected because DOI is mandatory and missing.
Four KFUPM repository pages were inspected; their metadata contained no DOI.
This does not establish that no DOI exists elsewhere.

Rejected records are preserved with failure reasons and may be recovered
through verified enrichment followed by revalidation.

### Output location

The reviewed-enrichment validation outputs are stored in:

`data/interim/rana_saad_validation/enriched_20260912T164601930202Z/`

- `validated.csv`: accepted records for the next pipeline stage.
- `rejected.csv`: rejected records with failure reasons.
- `validation_summary.csv`: input, accepted and rejected counts by source.
- `validation_failures_by_rule.csv`: failure counts by source and rule.
- `validation_test_results.csv`: results of the 43 validator tests.
- `validation_rules.json`: rules used for this run.
- `enrichment_log.json`: fields added and references to supporting evidence.
- `ksu_provenance.json`: source references and KSU mapping decisions.

These are validation outputs, not the final transformed dataset.

### Coverage and limitations

- The allowed year range is 2023–2026.
- KSU uses the annual source file's year as its reported publication year.
- KSU source URLs point to annual datasets, not individual publication pages.
- Technology filtering produces candidates and may miss relevant research
  or include irrelevant records.
- DOI validation checks syntax; it does not verify that every DOI resolves.
- Only the small reviewed enrichment trial has been applied.
- PNU validation and team review remain pending.


## Transformation Tests

The transformation stage includes tests to verify that:

- The number of records is preserved after transformation.
- `research_id` remains unique.
- `publication_year` contains valid values.
- `has_doi` contains only Boolean values.
- `abstract_word_count` is never negative.

Assertion cells are used inside the notebook to verify these rules.

Main transformation notebook:

```text
notebooks/04_join_transform.ipynb
```

Processed datasets are stored in:

```text
data/processed/
```

---

# Repository Structure

```text
saudi-tech-research/
│
├── data/
│   ├── raw/
│   │   └── Original source files and API responses
│   │
│   ├── interim/
│   │   └── Cleaned, validated, and rejected datasets
│   │
│   └── processed/
│       └── Final processed datasets
│
├── notebooks/
│   ├── 01_extract.ipynb
│   ├── 02_profile_clean.ipynb
│   ├── 03_schema_validate_hasaniah.ipynb
│   └── 04_join_transform.ipynb
│
├── src/
│   └── Placeholder for integration-stage Python modules
│
├── tests/
│   └── Placeholder for integration-stage automated tests
│
├── config.yaml
├── main.py
├── requirements.txt
├── .gitignore
└── README.md
```

---

# Technologies Used

The project currently uses:

- Python
- pandas
- Jupyter Notebook
- VS Code
- Git
- GitHub
- REST APIs
- CSV
- Excel
- JSON

---

# Current Project Status

The following stages are currently completed or being completed by the team:

- Source identification
- Data extraction
- Data profiling
- Data cleaning
- Data standardization
- Common schema definition
- Schema validation
- Join and transformation rules
- Transformation testing
- Processed CSV generation

The project is currently being developed through Jupyter notebooks.

Refactoring the notebook logic into the `src/` modules, connecting the entire pipeline through `main.py`, and migrating notebook tests into the `tests/` folder will be completed during the later Integration stage.

---

# Future Integration

During the integration stage, the team will:

- Merge all members' completed datasets.
- Refactor notebook code into reusable Python modules.
- Connect the pipeline through `main.py`.
- Move assertion tests into the `tests/` directory.
- Verify the pipeline from extraction to final output.
- Produce the final team-wide analysis-ready dataset.

---

# Final Goal

The final output of the project will be a unified dataset containing standardized research metadata from selected Saudi universities.

The dataset will support questions such as:

> What technology-related research is being published by Saudi universities, and how is it changing over time?

The resulting data can later support:

- Research trend analysis
- University comparisons
- Technology-category analysis
- Dashboards
- Research-gap identification
- Further academic analysis

---

# Team Members

- Rana Ayman Almohethef
- Aryam Saad Alotaibi
- Rana Saad AlHasaniah
