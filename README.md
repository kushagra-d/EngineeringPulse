# EngineeringPulse

## Company-Wide Engineering Intelligence & Analytics Platform

EngineeringPulse converts raw GitHub activity into an analytical data platform that answers business questions about team performance, repository health, collaboration patterns, and CI/CD reliability.

### Architecture

```
GitHub REST API → Python ETL → PySpark → PostgreSQL (Star Schema) → Advanced SQL → Power BI
```

| Layer | Location | Produced by |
|-------|----------|-------------|
| Bronze (raw JSON) | `data/raw/` | `ingestion/extract.py` |
| Silver (cleaned CSV) | `data/cleaned/` | `processing/clean_data.py` |
| Gold (11 warehouse tables as CSV) | `data/gold/` | `processing/build_gold.py` (PySpark) |
| Warehouse | PostgreSQL schema `engineeringpulse` | `processing/load_postgres.py`, `sql/schema.sql` |
| Dashboards | `powerbi/EngineeringPulse.pbix` | Power BI Desktop |

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Extraction | Python, Requests, GitHub REST API |
| Cleaning | Pandas |
| Transformation | PySpark 4.x (run locally on Java 17; the notebook is Databricks-compatible) |
| Storage | PostgreSQL 16+ (built on 18) |
| Analytics | SQL: CTEs, window functions (`ROW_NUMBER`, `RANK`, `LAG`, `PERCENTILE_CONT`, rolling averages) |
| Visualization | Power BI Desktop |
| Testing | pytest |

### Data model

Star schema with 5 dimensions, 5 facts and a team-to-repository bridge table with SCD Type 2 history. See [docs/er_diagram.md](docs/er_diagram.md) and [docs/data_dictionary.md](docs/data_dictionary.md).

### Setup and run

```bash
# 1. Virtual environment and dependencies (Python 3.12+, Java 17 for PySpark)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Environment variables
copy .env.example .env
# Edit .env: GITHUB_TOKEN and the DB_* values

# 3. Create the database once (psql or pgAdmin)
#    CREATE DATABASE engineeringpulse;

# 4. Run the pipeline
python run_pipeline.py            # everything, in order
```

Steps can be run one at a time:

```
python run_pipeline.py extract    # long (about 1-2 hours); rate-limit pauses are normal; safe to rerun
python run_pipeline.py clean
python run_pipeline.py gold       # PySpark
python run_pipeline.py quality    # stops the pipeline if any check fails
python run_pipeline.py export     # recreates the schema and loads all 11 tables
```

To redo extraction from scratch, delete `data/raw`. After a new run, open the `.pbix` and click **Home → Refresh**.

### Tests

```bash
python -m pytest tests -q        # PySpark Gold logic on tiny synthetic data (~1 min)
python run_pipeline.py quality   # 17 data-quality checks on the real Gold tables
```

### Project structure

```
EngineeringPulse/
├── config/          # repositories.csv (20 repos → 8 teams) and config.yaml
├── data/            # raw / cleaned / gold / quality (git-ignored, regenerated)
├── ingestion/       # GitHub API client and extractors
├── processing/      # clean_data, build_gold (PySpark), data_quality, load_postgres
├── utils/           # logging
├── databricks/      # notebook that runs the PySpark Gold build
├── notebooks/       # data profiling notebook
├── sql/             # schema.sql and analytics.sql (20 queries)
├── tests/           # PySpark Gold test
├── powerbi/         # EngineeringPulse.pbix
└── docs/            # reference, guides, dictionary, ER diagram, screenshots
```

### Dataset

- **Source:** GitHub REST API (public repositories)
- **Company model:** TechNova Engineering (fictional organisation)
- **Scope:** 20 repositories, 8 teams, 6 months (2026-03-01 to 2026-08-31)
- **Result:** 3,542 PRs, 4,148 reviews, 1,309 issues, 2,782 commits, 15,760 CI runs, 1,910 developers
- **Real vs. simulated:** all activity is real GitHub data from public repos. The company, the teams and which team owns which repo are invented for the demo; one ownership change (pallets/flask, Backend to Platform on 2026-06-01) is seeded to show SCD Type 2.

### Known limitations

- PR size columns (`additions`, `deletions`, `changed_files`) are empty; the list endpoint does not return them.
- Workflow duration is a proxy (`updated_at - run_started_at`); GitHub caps filtered workflow queries, so busy repos may have partial CI history.
- Open issue/PR counts are as of the extraction date (2026-09-26), not the end of the window.
- Analytics attribute PRs to a repository's current team.
- Release metrics are not built; cross-team reviews exist as SQL query 14 only.
- PySpark runs locally. Results are written through pandas because Spark's CSV writer needs `winutils` on Windows; on a cluster use `df.write`.

### Documentation

| Document | What it covers |
|----------|----------------|
| [docs/PROJECT_REFERENCE.md](docs/PROJECT_REFERENCE.md) | Specification, phase-by-phase build log, problems and fixes, design decisions, run and test guide, results |
| [docs/POWERBI_GUIDE.md](docs/POWERBI_GUIDE.md) | Power BI connection, model, DAX measures and the 5 pages |
| [docs/data_dictionary.md](docs/data_dictionary.md) | Every warehouse table and column |
| [docs/er_diagram.md](docs/er_diagram.md) | Mermaid entity-relationship diagram |
| [docs/data_quality_initial.md](docs/data_quality_initial.md) | Record counts, data issues found, quality checks |

---

> **Note:** GitHub activity is sourced from public repositories. Team and ownership relationships are a controlled organizational model created for this analytical demonstration.
