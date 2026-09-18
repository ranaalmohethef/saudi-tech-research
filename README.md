# Saudi Technology Research Data Hub

A data engineering project that collects, cleans, validates, and filters research metadata from Saudi universities to support exploration of technology-related research.

The repository preserves team contributions, intermediate datasets, validation results, and filtering reports. Only selected datasets are included in the consolidated output.

## 1. Project Scope

The project covers research metadata within the 2023–2026 scope, subject to source availability.

The workflow includes:

1. Extracting research metadata from university repositories, APIs, and institutional datasets.
2. Cleaning values and mapping source fields to a shared schema.
3. Validating required fields and recording rejected records.
4. Selecting technology-related research using keyword matching.
5. Combining eligible datasets into a shared final file.
6. Preserving excluded contributions and documenting their limitations.

Coverage is not complete for every university or year. Missing coverage must not be interpreted as an absence of research activity.

## 2. Team Contributions

| Contributor | University scope | Contribution |
|---|---|---|
| Rana Ayman | KAUST and KFUPM | Extraction, cleaning, validation, technology filtering, and integration |
| Rana Saad | KSU | Source inspection, cleaning, validation, and technology-related research selection |
| Aryam Alotaibi | PNU | Extraction, metadata enrichment, cleaning, validation, and filtering workflow |

All contributions are retained for documentation and review.

Merging a contributor's Git branch into `main` does not automatically include that contributor's records in `data/processed/final.csv`.

## 3. Dataset Inclusion Status

| Dataset | Status | Explanation |
|---|---|---|
| KAUST | Included | Selected records from Rana Ayman's final dataset |
| KSU | Included | KSU records selected from Rana Saad's validated output |
| KFUPM | Pending integration | The newer Pure collection requires validation and integration with the shared workflow |
| PNU | Excluded from the consolidated final dataset | The reviewed output contains enrichment and matching issues described below |

The team merge workflow uses explicit input files. It must not combine every CSV found under `data/processed`.

### Consolidation snapshot

The input snapshot reviewed for the team merge contained:

| University | Rows |
|---|---:|
| KAUST | 123 |
| KSU | 1,477 |
| Total | 1,600 |

These inputs contained 1,599 distinct DOI values. One DOI appeared under both universities.

These counts describe the reviewed snapshot. Regenerated outputs may differ and must be checked against the latest execution results.

## 4. Data Sources

### KAUST

KAUST metadata is collected from repository records and Crossref.

Repository records and Crossref records may use different publication-year conventions. These differences require review rather than automatic replacement of one year with another.

### KSU

KSU metadata is obtained from institutional annual research datasets.

In the reviewed KSU output, the `url` field refers to the annual source dataset rather than an individual publication page. This is a documented source-traceability limitation.

### KFUPM

The repository contains work based on:

- Historical KFUPM ePrints records.
- A newer KFUPM Pure extraction workflow.

These collections must be distinguished when validating and reporting results.

The reviewed snapshot contained a newer Pure cleaned dataset alongside validation outputs from the older ePrints collection. Those validation outputs do not establish the quality of the newer Pure dataset.

### PNU

The PNU contribution includes source collection and Crossref metadata enrichment.

Its reviewed final output is retained for audit and reproducibility but is excluded from the consolidated dataset.

## 5. Shared Schema

The consolidated dataset uses the following 13 columns in this order:

| Column | Type | Required | Rule |
|---|---|---|---|
| `research_id` | String | Yes | Non-empty and unique |
| `university` | String | Yes | Standard university code |
| `title` | String | Yes | Non-empty research title |
| `authors` | String | Yes | Non-empty author information |
| `publication_year` | Integer | Yes | Whole year within 2023–2026 |
| `publication_date` | Date | No | Valid `YYYY-MM-DD` date when available |
| `abstract` | String | No | Abstract text when available |
| `research_field` | String | No | Research field when available |
| `tech_category` | String | No | Technology category when assigned |
| `journal` | String | No | Journal or publication venue when available |
| `doi` | String | Yes | DOI in the expected format |
| `url` | String | Yes | Valid HTTP or HTTPS URL |
| `source` | String | Yes | Non-empty source identifier |

Standard university codes are:

- `KAUST`
- `KFUPM`
- `KSU`
- `PNU`

### Required-field policy

The required fields are:

```text
research_id
university
title
authors
publication_year
doi
url
source
```

A record with a missing required value is excluded from the accepted dataset and retained in a rejection report where supported by the workflow.

This policy can exclude legitimate research that has no DOI. Such exclusion reflects the project's schema requirement and does not mean the research itself is invalid.

### Optional-field policy

Missing optional values are allowed.

Unavailable dates, abstracts, journals, research fields, or technology categories must not be invented.

A word-count field such as `abstract_word_count` is a derived value and does not replace the original `abstract` text.

## 6. Cleaning and Validation

The shared workflow should:

- Trim surrounding whitespace.
- Normalize recognized missing-value markers.
- Standardize university names to the agreed codes.
- Normalize DOI representations before comparison.
- Verify required values.
- Check research identifier uniqueness.
- Validate whole-number publication years.
- Validate optional full dates.
- Check DOI syntax.
- Check URL structure.
- Preserve rejected records with reasons.

Validation results must correspond to the current cleaned inputs.

A file named `validated.csv` is not sufficient evidence of current validation if its input dataset has subsequently changed.

### Structural and semantic quality

Passing schema validation confirms structural requirements.

It does not prove that:

- A DOI belongs to the supplied title.
- Authors belong to the supplied research record.
- The source university affiliation is correct.
- The publication year uses the intended date convention.
- A publication is genuinely technology-related.
- A publication has no retraction or other status notice.

These checks require additional evidence.

## 7. Technology Filtering

Technology filtering identifies candidate records using a shared keyword approach.

Depending on source availability, searchable fields include:

- Title.
- Abstract.
- Author keywords.

Keyword matching should:

1. Be case-insensitive.
2. Normalize whitespace and common hyphen variations.
3. Use word boundaries for short terms and abbreviations.
4. Retain matched terms for review.
5. Preserve records with no keyword match in a separate output.

Short terms such as `ai` must not be matched as unrestricted substrings inside unrelated words.

A keyword match indicates a candidate record, not a confirmed technology classification. Similarly, a record without a keyword match is not necessarily non-technical.

Filtering evidence may include:

```text
filter_review.csv
no_keyword_match.csv
technology_selected.csv
```

These files must be regenerated from the same input snapshot as the corresponding final output.

## 8. PNU Contribution: Issues and Exclusion Decision

Aryam's contribution is preserved in this repository.

However, the PNU output reviewed during the quality assessment is excluded from `data/processed/final.csv` because its enriched metadata could not be reliably associated with the original research records.

The findings below apply to the reviewed 1,544-row PNU output. They are not quality measurements of every PNU publication or of a future corrected extraction.

### 8.1 Enrichment index misalignment

The reviewed workflow filtered source records while retaining their original DataFrame indices.

Crossref results were then stored in a new DataFrame with a sequential index and assigned directly:

```python
pnu_enriched[
    ["authors", "doi", "url", "publication_date", "abstract", "journal"]
] = crossref_df
```

Pandas aligns this assignment by index labels.

Because the two DataFrames no longer represented the same records at the same index labels, enrichment values could be attached to the wrong research records.

Affected fields included:

- Authors.
- DOI.
- URL.
- Publication date.
- Abstract.
- Journal.

The review identified 1,540 of 1,544 final records, approximately 99.74%, as affected by unreliable metadata association.

This issue prevents acceptance even when the affected fields are populated and pass format checks.

### 8.2 Crossref candidate verification

The reviewed workflow also relied on a first-result matching approach without sufficient verification.

A Crossref search result is a candidate match. Its position in the results does not establish that it is the correct publication.

Before accepting enrichment, the workflow must compare the candidate against the original record using:

- Title.
- Available author information.
- Publication year and date context.
- Other available identifiers or publication details.

Low-confidence matches must remain unresolved.

### 8.3 Duplicate DOI assignments

The reviewed PNU final output contained 92 records in duplicate DOI groups, approximately 5.96% of the dataset.

Some DOI values were associated with different titles.

These cases require identity checks. Simply dropping duplicate DOI rows does not repair metadata that was assigned to the wrong record.

### 8.4 Publication-year inconsistencies

The review found 383 records, approximately 24.81%, whose publication-date year differed from `publication_year`.

Some year differences can occur legitimately between online publication, issue publication, and source reporting dates. However, the enrichment misalignment makes these differences unreliable until the underlying record matching is corrected.

The reviewed final output also contained only 2023 records despite the source collection containing records from 2023, 2024, and 2025.

The loss of later-year coverage requires investigation.

### 8.5 Technology-filter over-selection

The reviewed filter used unrestricted substring matching for terms such as `ai`.

This can match unrelated words and admit records without the intended keyword evidence.

In a comparison using the same terms with word boundaries, 731 of 1,544 records, approximately 47.34%, would not pass.

This is evidence of potential over-selection. It does not prove that all 731 records are non-technical.

### 8.6 Interpreting the percentages

These issue groups overlap.

Their percentages must not be added together to calculate a total error rate.

The enrichment association issue is the primary reason for excluding the reviewed PNU output.

### 8.7 Requirements for future inclusion

PNU can be reconsidered after:

1. Returning to the original source records.
2. Preserving a stable identifier for every source record.
3. Rebuilding enrichment with an explicit link to that identifier.
4. Checking Crossref candidates before accepting metadata.
5. Investigating duplicate DOI assignments.
6. Reviewing publication-year inconsistencies and year coverage.
7. Applying the agreed technology-filter rules.
8. Rerunning validation and generating fresh quality reports.

Resetting the index alone is not sufficient unless enrichment results preserve the exact same record order, including failed or unmatched requests.

Joining enrichment results through a stable source identifier is preferable.

Existing misassigned metadata must not be treated as corrected merely because the final DataFrame index has been reset.

## 9. Preserving Aryam's Work

The contribution is retained using separate filenames where notebook names overlap with the existing team workflow:

```text
README_aryam.md
notebooks/pnu_aryam.ipynb
notebooks/02_profile_clean_aryam.ipynb
notebooks/03_schema_validate_aryam.ipynb
notebooks/04_join_transform_aryam.ipynb
```

The preserved notebooks document the submitted work. Renaming them does not itself fix their logic or isolate their output paths.

Review their input and output paths before execution.

`data/processed/final_pnu.csv` is retained as an excluded contribution artifact. Its filename does not mean it is approved for the shared final dataset.

Contributor-specific README files are historical documentation. This main README defines the current team-level inclusion decision.

## 10. Team Merge

The team merge workflow is maintained in:

```text
notebooks/05_team_merge.ipynb
```

The reviewed consolidation uses:

- Rana Ayman's selected KAUST records.
- The KSU subset of Rana Saad's validated output.

It excludes:

- PNU records pending correction.
- KFUPM records pending integration.
- Rejected records.
- Records excluded by the applicable technology filter.
- Duplicate copies of KAUST records present in another contributor's combined validation output.

The final dataset contains only the shared 13 columns.

Contributor-specific helper columns, including `has_doi` and `abstract_word_count`, are not part of the consolidated schema.

### Cross-university DOI handling

A publication may be associated with more than one university.

A DOI appearing under different universities should be reviewed rather than automatically removed.

The current consolidation preserves university associations and writes shared DOI cases to:

```text
data/processed/shared_doi_review.csv
```

The reviewed input snapshot contained one DOI shared between KAUST and KSU:

```text
10.5194/hess-29-4983-2025
```

Therefore, the reviewed 1,600-row snapshot represents university-associated records and contains 1,599 distinct DOI values.

## 11. Repository Structure

```text
saudi-tech-research/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
│       ├── final.csv
│       ├── final_rana.csv
│       ├── final_pnu.csv
│       ├── shared_doi_review.csv
│       └── technology_filter/
├── notebooks/
│   ├── 01_extract.ipynb
│   ├── 02_profile_clean.ipynb
│   ├── 03_schema_validate.ipynb
│   ├── 04_join_transform.ipynb
│   ├── 05_team_merge.ipynb
│   ├── KFUPM_Pure_extract_clean.ipynb
│   ├── hasaniah_ksu_inspect.ipynb
│   ├── pnu_aryam.ipynb
│   ├── 02_profile_clean_aryam.ipynb
│   ├── 03_schema_validate_aryam.ipynb
│   └── 04_join_transform_aryam.ipynb
├── src/
├── tests/
├── config.yaml
├── main.py
├── requirements.txt
├── README.md
├── README_rana_saad.md
└── README_aryam.md
```

This structure highlights the principal files. Additional source and contributor artifacts may also be present.

## 12. Running the Workflow

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

Select the project Python environment as the Jupyter kernel.

For the main notebook workflow, run the notebooks in order:

```text
01_extract.ipynb
02_profile_clean.ipynb
03_schema_validate.ipynb
04_join_transform.ipynb
05_team_merge.ipynb
```

Contributor workflows may have separate inputs and dependencies. They should not be treated as interchangeable replacements for the main notebooks.

Before running the team merge:

1. Confirm that the expected input files exist.
2. Confirm that validation outputs were generated from the current cleaned inputs.
3. Review accepted, rejected, and filtered record counts.
4. Confirm that the merge reads only the intended datasets.
5. Close CSV files open in Excel before overwriting them.

After running the team merge, check:

- Row count and university distribution.
- Exact column order.
- Missing required values.
- Duplicate research identifiers.
- DOI duplication within each university.
- Shared DOI cases across universities.
- Publication-year range and date validity.
- Absence of PNU records from the consolidated output.

Do not infer successful execution from old notebook outputs alone.

## 13. Known Limitations and Pending Work

### Uneven coverage

The datasets differ in collection method, year coverage, and available metadata. Raw publication counts should not be used directly to rank university research activity.

### Optional metadata gaps

Some accepted records lack optional metadata. This is permitted by the schema but limits downstream analysis.

### Publication-year interpretation

Repository deposit dates, online publication dates, issue dates, and annual reporting years may differ. A consistent analytical year policy remains important.

### Publication status

Schema validation does not check whether a publication has been retracted or has an expression of concern.

The earlier KSU review identified records with publication-status notices. These require review and explicit treatment before substantive research analysis.

### KFUPM integration

The newer Pure dataset requires:

- University-code normalization.
- Validation against the shared schema.
- Technology filtering.
- Fresh accepted and rejected outputs.
- Separation from historical ePrints output paths.

Do not overwrite a newer cleaned collection with outputs from an older extraction workflow.

### PNU remediation

The preserved PNU workflow requires correction and a new quality assessment before inclusion.

### Reproducibility

Input versions, extraction dates, API parameters, matching decisions, and rejection reasons should be recorded so that outputs can be reproduced and audited.

## 14. Intended Use

The dataset supports exploratory analysis and development of data engineering workflows.

It is not an exhaustive inventory of Saudi research, a university ranking, or a guarantee of publication quality.

Users should account for source coverage, keyword-selection limitations, shared university affiliations, publication-year conventions, and publication-status notices when interpreting results.
