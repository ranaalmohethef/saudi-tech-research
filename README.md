# Diraya — Saudi Technology Research Hub

![tests](https://github.com/ranaalmohethef/saudi-tech-research/actions/workflows/tests.yml/badge.svg)

Diraya collects research metadata from six Saudi universities, standardizes and validates it, and publishes technology-related records through a searchable website.

The project combines Azure Data Factory, Azure Functions, Azure Data Lake Storage Gen2, PostgreSQL, and a Flask API.

**Team:** Rana Ayman Almohethef · Rana Saad AlHasaniah · Aryam Saad Alotaibi

## 1. Results

The following figures describe the pipeline run of September 26, 2026. Live counts may change after subsequent pipeline runs.

| Metric | Value |
|---|---:|
| Technology-related research records | 5,344 |
| Distinct DOIs across all universities | 4,987 |
| Validated records before technology filtering | 22,960 |
| Universities | 6 |
| Publication years covered | 2023–2026 |

| University | Final records |
|---|---:|
| KSU | 1,483 |
| KAU | 1,404 |
| KKU | 1,097 |
| PSAU | 1,017 |
| KFUPM | 211 |
| KAUST | 132 |
| **Total** | **5,344** |

A research paper associated with more than one included university may appear once for each university. Therefore, the number of university-associated records differs from the number of distinct DOIs.

These counts describe the collected dataset and are not a ranking of universities.

### Technology Filter Accuracy

The 33-term technology filter was reviewed by hand on a sample of about 60 papers drawn from both the published dataset and the rejected rows.

| Measure | Sample result |
|---|---:|
| Precision | ≈ 93% |
| Recall | ≈ 68% |
| Agreement with manual reading | ≈ 88% |

These are indicative figures from a small sample, not a formal measurement. Recall is the known weak point: a paper that uses none of the 33 terms is never kept. A labelled evaluation over 200 randomly drawn papers is the planned next step.

## 2. Repository Contents

| Path | Contents |
|---|---|
| `adf/pipeline/` | Eight Data Factory pipelines, including `PL_Master` |
| `adf/dataflow/` | Four mapping data flows |
| `adf/dataset/` | Twenty-one dataset definitions |
| `adf/linkedService/` | Nine linked-service definitions |
| `adf/factory/` | Data Factory definition |
| `azure_function/function_app.py` | Five HTTP functions for processing, quality checks, statistics, and health |
| `azure_function/processing.py` | KFUPM and OpenAlex processing entry point |
| `azure_function/main.py` | Shared processing workflow |
| `azure_function/src/` | Extraction, cleaning, validation, and transformation modules |
| `azure_function/config.yaml` | Source configuration, years, and technology keywords |
| `Website/` | Flask API, website, saved data, and local setup instructions |
| `docs/Documents/` | Project report in PDF and Word formats |
| `docs/architecture/` | Architecture diagram in PNG and PDF formats |

The Python pipeline source and its 129 unit tests (run automatically on every push) are maintained in a separate repository: [ranaalmohethef/saudi-tech-research](https://github.com/ranaalmohethef/saudi-tech-research). The modules under `azure_function/src/` in this repository are the deployed copies of that code.

## 3. Architecture

![Diraya architecture](docs/architecture/Diraya_Diagram.png)

The processing stages are:

1. Collect metadata from public APIs and university websites, or read the staged KAUST 2023 CSV.
2. Store source files in ADLS Gen2.
3. Clean and validate records using ADF mapping data flows and Python Azure Functions.
4. Write validated outputs to ADLS or PostgreSQL.
5. Combine sources and apply the technology filter.
6. Write the results to `research.final_dataset_candidate`.
7. Validate the candidate table and publish it to `research.final_dataset`.
8. Run post-publication quality checks and update source statistics.
9. Serve the results through the Flask API and website.

Raw files are not modified during cleaning. A subsequent ingestion run may overwrite files with the same names.

### Azure Resources

| Resource | Project resource |
|---|---|
| Data Factory | `saudi-tech-adf-rana` |
| Storage account | `storageacc4saudi` |
| Storage container | `saudi-tech-research` |
| PostgreSQL server | `saudi-tech-pg` |
| PostgreSQL database | `research_hub` |
| PostgreSQL schema | `research` |
| Function App | `saudi-tech-func-rana` |
| Logic App | `la-saudi-tech-notify` |
| Key Vault | `kv-saudi-tech-rana` |

These names refer to the team's existing environment. A separate deployment requires its own resources, permissions, and connection settings.

## 4. Data Sources

| University | Source | Format | Processing | Scope |
|---|---|---|---|---|
| KAUST | KAUST repository | CSV | ADF data flow | Staged 2023 snapshot |
| KAUST | Crossref API | JSON | ADF data flow | 2024–2026 |
| KSU | KSU open data portal | JSON | ADF data flow | 2023–2025 |
| KFUPM | Pure OAI-PMH repository | MODS XML | Azure Function | Computer Engineering, 2023–2026 |
| KAU, KKU, PSAU | OpenAlex API | JSON | Azure Function | Computer Science, 2023–2026, with DOI |

Most data are collected automatically. KAUST's 2023 records are read from a previously downloaded CSV because the team encountered access restrictions when requesting the repository from Azure.

Python functions handle KFUPM's nested MODS XML and reconstruct OpenAlex abstracts from inverted indexes.

KSU uses a separate enrichment file to fill selected missing DOI and abstract values.

## 5. Pipeline Orchestration

### Master Pipeline

`PL_Master` coordinates processing in the following order:

| Order | Activity | Purpose |
|---|---|---|
| 1 | `GetEmailUrl` | Read the notification URL from Key Vault |
| 2 | `RunKaust` | Process the staged KAUST 2023 file |
| 3 | `RunCrossref` | Collect and process KAUST records from Crossref |
| 4 | `RunKsu` | Collect and process KSU yearly files |
| 5 | `RunKfupm` | Harvest and process KFUPM records |
| 6 | `RunOpenAlex` | Collect and process KAU, KKU, and PSAU records |
| 7 | `RunFinal` | Build, validate, and publish the final dataset |
| 8 | `QualityCheck` | Check the published dataset |
| 9 | `UpdateStats` | Update source statistics |
| 10 | `EmailSuccess` | Send the success notification |

The failure branch uses `EmailFailure` when `UpdateStats` fails or is skipped. `FailPipeline` follows a successful failure notification to keep the pipeline marked as failed.

### Child Pipelines

| Pipeline | Purpose |
|---|---|
| `KAUST_Clean_Pipeline` | Clean the KAUST 2023 snapshot and merge records into `research.publications` |
| `PL_Ingest_Crossref` | Collect paginated Crossref results, clean them, and merge them into `research.publications` |
| `PL_Ingest_KSU` | Process the configured KSU years and write validated Parquet files |
| `PL_Ingest_KFUPM` | Coordinate yearly harvesting and call the KFUPM processing function |
| `PL_Harvest_KFUPM_Year` | Retrieve and store the XML pages for one year |
| `PL_Ingest_OpenAlex` | Collect three universities and call the OpenAlex processing function |
| `PL_Final_Union` | Build the candidate table, validate it, and publish it |

### KAUST Inactive Activities

`GetBundles`, `GetBitstreams`, and `DownloadCsv` are intentionally inactive in `KAUST_Clean_Pipeline`.

The pipeline reads the existing KAUST 2023 CSV instead. Its cleaning and database merge activities remain active.

### Mapping Data Flows

| Data flow | Main responsibilities |
|---|---|
| `KAUST_2023_Clean_DF` | Normalize missing values, parse dates, keep 2023 records, rank duplicates, align fields, and write outputs |
| `Crossref_Clean_DF` | Flatten API results, extract metadata, clean abstracts, validate records, and write staging data |
| `KSU_Clean_DF` | Generate identifiers, clean fields, join enrichment, fill missing values, validate records, and write Parquet |
| `Final_Union_DF` | Align source schemas, combine records, calculate metrics, apply the technology filter, and write the candidate table |

The technology filter uses 33 whole-word terms. For KSU, it searches titles and author keywords; for the other sources, it searches titles and abstracts.

## 6. Data Quality and Publishing

### Before Publishing

`ValidateCandidate` performs eleven checks:

1. The candidate table is not empty.
2. Eight required fields are present: `research_id`, `university`, `title`, `authors`, `publication_year`, `doi`, `url`, and `source`.
3. University values belong to the six supported universities.
4. All six universities are represented.
5. Publication years are integers between 2023 and 2026.
6. DOIs match the expected format.
7. URLs pass the HTTP/HTTPS format check and contain no whitespace.
8. When a publication date is present, its year matches `publication_year`.
9. `research_id` values are unique.
10. Normalized DOIs are unique within each university.
11. No university's row count has decreased by more than 20% compared with the current published table.

Missing-value markers such as `n/a`, `null`, and empty strings are treated as missing in the required-field check.

DOI and URL checks validate their format; they do not confirm that every external link is reachable.

### Publishing

After validation succeeds, `PublishFinal` replaces `research.final_dataset` inside a database transaction.

If the replacement fails within that transaction, the changes are rolled back.

### After Publishing

The `quality_check` Azure Function performs eight checks covering:

- Representation of the expected universities.
- Duplicate research identifiers.
- Missing required values.
- Lowercase DOIs.
- DOI format.
- Publication-year range.
- URL format.
- Total row-count decline compared with the previous successful quality check.

Results are recorded in `research.quality_checks`. A failed post-publication check marks the activity as failed; it does not automatically restore the previous dataset.

### Rejected Records

KFUPM and OpenAlex processing saves rejected records and failure summaries under `interim/rejected/`.

The ADF data flows filter invalid records without writing equivalent rejected-record files.

## 7. Azure Functions

| Function | Route | Purpose |
|---|---|---|
| `process_kfupm` | `/api/process/kfupm` | Parse, clean, and validate KFUPM XML files |
| `process_openalex` | `/api/process/openalex` | Reconstruct abstracts, clean, and validate OpenAlex records |
| `quality_check` | `/api/quality_check` | Check the published table and record results |
| `update_stats` | `/api/update_stats` | Update the statistics read by the website |
| `health` | `/api/health` | Check storage access |

The Function App uses the following application settings:

| Setting | Purpose |
|---|---|
| `STORAGE_ACCOUNT_URL` | Storage account endpoint |
| `DATA_CONTAINER` | Container name |
| `PGHOST` | PostgreSQL hostname |
| `PGDATABASE` | Database name |
| `PGUSER` | Database user |
| `PGPASSWORD` | Database password |

The Function App's managed identity requires access to the storage account. Database credentials belong in application settings, not in committed source files.

The Function App source is in `azure_function/`. Its deployment package must contain `host.json` at the package root.

## 8. Database Tables

| Table | Purpose |
|---|---|
| `research.publications_staging` | Intermediate KAUST and Crossref loading |
| `research.publications` | Merged KAUST and Crossref records |
| `research.final_dataset_candidate` | Combined and filtered records awaiting publication |
| `research.final_dataset` | Published records used by the website |
| `research.quality_checks` | Quality-check history |
| `research.source_stats` | Latest source statistics |

### Final Dataset Fields

The publication step writes these fifteen fields:

| Field | Purpose |
|---|---|
| `research_id` | Research-record identifier |
| `university` | University code |
| `title` | Research title |
| `authors` | Author information |
| `publication_year` | Publication year |
| `publication_date` | Publication date, when available |
| `abstract` | Abstract, when available |
| `research_field` | Research field, when available |
| `tech_category` | Technology category, when available |
| `journal` | Journal or source title |
| `doi` | Normalized DOI |
| `url` | Source or record URL |
| `source` | Data-source label |
| `has_doi` | Derived DOI-presence flag |
| `abstract_word_count` | Derived abstract word count |

The deployed table also includes `loaded_at`, which the website uses to show the last data-loading time.

## 9. Website

The website supports two modes.

### Saved-Data Mode

Open:

`Website/static/index.html`

This displays the saved dataset without requiring a PostgreSQL connection.

`Website/diraya.html` provides a bundled version for sharing and demonstration.

Saved copies remain unchanged until they are regenerated.

### Live Database Mode

From the `Website` directory:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the connection details:

```dotenv
PGHOST=your-server.postgres.database.azure.com
PGPORT=5432
PGDATABASE=research_hub
PGUSER=your_database_user
PGPASSWORD=your_database_password
```

Ensure that the database is running and permits access from the machine running Flask.

Check the connection:

```bash
python test_connection.py
```

Start the local server:

```bash
python server.py
```

Open:

http://localhost:5000

The website indicates whether it is using live database records or the saved copy. Reload the page to fetch updated data.

The included Flask startup is intended for local development and demonstration.

### Refreshing Saved Copies

From `Website`, with database access configured:

```bash
python make_data_js.py --db
python build_single.py
```

The first command refreshes `static/data.js`. The second rebuilds `diraya.html`.

### Source Statistics

Azure's `UpdateStats` activity maintains `research.source_stats`.

The local command below creates the statistics table when needed without replacing existing counts:

```bash
python setup_stats.py
```

It is not required after each Azure pipeline run. Do not use a local Python `run_summary.json` to overwrite Azure statistics.

For KSU and KAUST, the statistics function refreshes validated counts while retaining existing cleaned counts when a new cleaned count is unavailable.

## 10. Running the Azure Pipeline

These instructions assume the team's Azure resources, database tables, staged files, and permissions already exist.

1. Save and publish the intended Data Factory changes.
2. Start `PL_Master`.
3. Monitor the run and inspect any failed activity.
4. Confirm that final publication, quality checks, and statistics updates succeeded.
5. Review the published data using the queries below.
6. Refresh the website or rebuild its saved copy as needed.

Avoid overlapping full runs or manually running child pipelines while a full run is active, because they share intermediate files and database tables.

### Verification Queries

```sql
-- Final records per university.
SELECT university, COUNT(*) AS records
FROM research.final_dataset
GROUP BY university
ORDER BY university;

-- Total records and distinct DOIs.
SELECT
    COUNT(*) AS total_records,
    COUNT(DISTINCT LOWER(BTRIM(doi))) AS distinct_dois
FROM research.final_dataset;

-- Latest quality-check result.
SELECT checked_at, total_rows, passed, details
FROM research.quality_checks
ORDER BY checked_at DESC
LIMIT 1;

-- Current source statistics.
SELECT university, cleaned, validated, updated_at
FROM research.source_stats
ORDER BY university;
```

## 11. Notifications and Credentials

- `GetEmailUrl` reads the Logic App callback URL from Key Vault using managed identity.
- Notification activities send the pipeline status and run ID to the Logic App.
- The success message includes the final record count and validated total.
- Notification delivery depends on Key Vault access and the Logic App being available.
- Azure Monitor alerts are configured in the deployed Azure environment.
- Website credentials are stored locally in `.env`.
- Do not commit passwords, function keys, callback secrets, or populated `.env` files.
- `.env.example` contains configuration placeholders for local setup.
- `.gitignore` excludes `.env`, Python caches, and build output from version control.

## 12. Deployment Requirements and Limitations

This repository contains application code and ADF definitions. It is not a complete one-command deployment package for a new Azure account.

A separate environment requires Azure resources, database table definitions, connection settings, permissions, notification configuration, and the staged input files.

| Item | Current behavior |
|---|---|
| KAUST 2023 | Reads a previously downloaded CSV rather than downloading it during each run |
| KSU enrichment | Requires the separate enrichment JSON file in storage |
| KSU identifiers | Generated from yearly row positions; changes in row ordering can affect enrichment matching |
| KAUST and Crossref merge | Uses upserts; records removed upstream are not automatically deleted |
| KFUPM raw pages | Files are overwritten by name; surplus pages from an earlier harvest are not automatically removed |
| Rejected-record files | Produced for KFUPM and OpenAlex |
| Source statistics | Store the latest values; quality-check history is stored separately |
| Saved website | Requires regeneration to reflect a newer database snapshot |
| External sources | Availability, metadata, and record counts may change between runs |
| Processing functions | Run synchronously within HTTP requests; larger workloads may require a different execution approach |

## 13. Scope

Diraya provides research metadata, search, and descriptive analytics for the six included universities within the configured source and year coverage.

It does not host full research papers. Access to full text depends on the original publisher or repository.

## 15. Technologies

Python · pandas · PyYAML · pytest · Jupyter Notebook · VS Code · Git/GitHub · Crossref REST API · OpenAlex · OAI-PMH · CSV · JSON · XML · XLSX
