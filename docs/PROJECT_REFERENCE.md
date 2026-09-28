# EngineeringPulse — Complete Project Reference

> **Status: built and verified end to end** (extract → clean → PySpark Gold → quality checks → PostgreSQL → 20 SQL queries → Power BI).
> Sections 1–41 are the specification, kept in sync with what was actually built. Sections 42–47 record how it was built, the problems met and how they were solved, the design decisions, how to run and test it, and the final results.

## Company-Wide Engineering Intelligence & Analytics Platform

---

## Table of Contents

1. [Problem & Solution](#1-problem--solution)
2. [Scope Decision](#2-scope-decision)
3. [Dataset Strategy](#3-dataset-strategy)
4. [Company Model — TechNova Engineering](#4-company-model--technova-engineering)
5. [Repository Selection](#5-repository-selection)
6. [Historical Period](#6-historical-period)
7. [Expected Data Size](#7-expected-data-size)
8. [Technology Stack](#8-technology-stack)
9. [High-Level Architecture](#9-high-level-architecture)
10. [Architecture Philosophy](#10-architecture-philosophy)
11. [Phase 0 — Environment Setup](#11-phase-0--environment-setup)
12. [Phase 1 — GitHub Authentication](#12-phase-1--github-authentication)
13. [Phase 2 — Repository Discovery & Config](#13-phase-2--repository-discovery--config)
14. [Phase 3 — Python API Client](#14-phase-3--python-api-client)
15. [Phase 4 — Individual Extractors](#15-phase-4--individual-extractors)
16. [Raw Data Structure](#16-raw-data-structure)
17. [Phase 5 — Data Profiling](#17-phase-5--data-profiling)
18. [Phase 6 — Python Cleaning](#18-phase-6--python-cleaning)
19. [Phase 7 — PySpark Transformations](#19-phase-7--pyspark-transformations)
20. [Phase 8 — Databricks](#20-phase-8--databricks)
21. [Phase 9 — Data Model (Star Schema)](#21-phase-9--data-model-star-schema)
22. [Dimension Tables](#22-dimension-tables)
23. [Bridge Table](#23-bridge-table)
24. [SCD Type 2](#24-scd-type-2)
25. [Fact Tables](#25-fact-tables)
26. [Business Metrics](#26-business-metrics)
27. [SQL Layer](#27-sql-layer)
28. [Required SQL Concepts](#28-required-sql-concepts)
29. [PostgreSQL Setup](#29-postgresql-setup)
30. [Power BI Dashboards](#30-power-bi-dashboards)
31. [Data Quality Module](#31-data-quality-module)
32. [Project Structure](#32-project-structure)
33. [File Responsibilities](#33-file-responsibilities)
34. [Build Order](#34-build-order)
35. [What We Do NOT Build](#35-what-we-do-not-build)
36. [Optional Extensions](#36-optional-extensions)
37. [What the Project Demonstrates](#37-what-the-project-demonstrates)
38. [Faculty Explanation](#38-faculty-explanation)
39. [Interview Explanation](#39-interview-explanation)
40. [Final Technology Flow](#40-final-technology-flow)
41. [Final Scope Summary](#41-final-scope-summary)
42. [Implementation Notes & Known Limitations](#42-implementation-notes--known-limitations)
43. [Build Log — Phase by Phase](#43-build-log--phase-by-phase)
44. [Problems Met and How They Were Solved](#44-problems-met-and-how-they-were-solved)
45. [Design Decisions and Why](#45-design-decisions-and-why)
46. [How to Run and Test](#46-how-to-run-and-test)
47. [Final Results](#47-final-results)

---

## 1. Problem & Solution

### Problem

Software companies have many engineering teams working across multiple repositories. Raw GitHub activity contains a lot of information, but it does not directly answer business questions such as:

- Which teams have the highest PR throughput?
- Which teams have the longest review cycle?
- Which repositories are becoming bottlenecks?
- Where is the issue backlog increasing?
- Which repositories have poor CI reliability?
- Which repositories are shared across teams?
- How has repository ownership changed over time?

### Solution

EngineeringPulse converts GitHub activity into an analytical data platform:

```
GitHub → Python ETL → PySpark → PostgreSQL Data Warehouse → Advanced SQL → Power BI
```

The main hierarchy is:

```
Company → Team → Repository → Developer → PR / Review / Issue / Workflow
```

---

## 2. Scope Decision

We are **not** building a production enterprise platform.

The project uses:

- Real public GitHub data
- A controlled company/team mapping
- A manageable number of repositories (20)
- A limited historical period (~6 months)
- A simplified but proper warehouse

This keeps the project realistic and explainable.

---

## 3. Dataset Strategy

The main dataset is created by querying the **GitHub REST API** for selected public repositories.

### A. Repository Metadata

| Field | Description |
|-------|-------------|
| repository_id | Unique ID from GitHub |
| repository_name | Name of the repo |
| owner | Organization/user who owns it |
| description | Repo description |
| primary_language | Main programming language |
| created_at | When the repo was created |
| updated_at | Last update timestamp |
| pushed_at | Last push timestamp |
| default_branch | Main branch name (e.g., main) |
| archived | Whether the repo is archived |
| fork | Whether the repo is a fork |
| stars | Star count |
| forks | Fork count |
| open_issues_count | Number of open issues |

Source: GitHub REST API — Repositories endpoint.

---

### B. Pull Requests

| Field | Description |
|-------|-------------|
| pr_id | Unique PR ID |
| repository_id | Which repo this PR belongs to |
| author | Who created the PR |
| created_at | When the PR was opened |
| updated_at | Last update |
| closed_at | When it was closed (if closed) |
| merged_at | When it was merged (if merged) |
| state | open / closed |
| draft | Whether it's a draft PR |
| additions | Lines added |
| deletions | Lines removed |
| changed_files | Number of files changed |

Source: GitHub Pull Requests API.

---

### C. Pull Request Reviews

| Field | Description |
|-------|-------------|
| review_id | Unique review ID |
| pr_id | Which PR this review belongs to |
| reviewer | Who reviewed |
| state | APPROVED / CHANGES_REQUESTED / COMMENTED |
| submitted_at | When the review was submitted |

Source: GitHub Pull Request Reviews API.

This lets us calculate time-to-first-review and review turnaround.

---

### D. Issues

| Field | Description |
|-------|-------------|
| issue_id | Unique issue ID |
| repository_id | Which repo this issue belongs to |
| author | Who created the issue |
| created_at | When the issue was opened |
| updated_at | Last update |
| closed_at | When it was closed (if closed) |
| state | open / closed |
| labels | Tags on the issue |
| assignees | Who is assigned |

> **Important:** GitHub's Issues API returns pull requests as well as issues, so the Python pipeline must explicitly distinguish them using the `pull_request` field.

---

### E. Commits

| Field | Description |
|-------|-------------|
| commit_sha | Unique commit hash |
| repository_id | Which repo this commit belongs to |
| author | Who wrote the code |
| committer | Who committed it |
| timestamp | When the commit was made |
| message | Commit message |

Used for repository activity and contributor analysis.

---

### F. GitHub Actions / Workflow Runs

| Field | Description |
|-------|-------------|
| workflow_run_id | Unique workflow run ID |
| repository_id | Which repo this ran in |
| workflow_name | Name of the workflow |
| event | What triggered it (push, PR, etc.) |
| status | queued / in_progress / completed |
| conclusion | success / failure / cancelled |
| created_at | When the run was created |
| started_at | When it actually started |
| updated_at | Last update |

Source: GitHub Actions Workflow Runs API.

This gives us CI/CD analytics.

---

## 4. Company Model — TechNova Engineering

We create a fictional company called **TechNova Engineering** and construct its organizational metadata.

### Teams

```
TechNova Engineering
├── Backend Team
├── Frontend Team
├── Data Platform Team
├── DevOps Team
├── Security Team
├── ML Team
├── Mobile Team
└── Platform Team
```

### Repository-to-Team Mapping

Real public GitHub repositories are assigned to these teams based on their domain/function.

```
Backend
 ├── repository-A
 ├── repository-B
 └── repository-C

Data Platform
 ├── repository-D
 ├── repository-E
 └── repository-F
```

A repository can belong to **multiple teams** with different roles (illustrative example; the real assignments are in `config/repositories.csv`):

```
payment-service
  Backend   → Primary
  Security  → Contributor
  DevOps    → Contributor
```

### Why a Fictional Company?

Because real private organizational team mappings are not publicly available. GitHub's API has organization/team endpoints, but access to private team membership depends on authentication and permissions.

> **Academic Honesty Statement:** "GitHub activity is sourced from public repositories. Team and ownership relationships are a controlled organizational model created for this analytical demonstration."

---

## 5. Repository Selection

We need about **20 repositories** with substantial activity (the original target was 20-25).

### Selection Criteria

- Active in recent months
- Large enough PR volume
- Issues available
- Reviews available
- Multiple contributors
- Preferably GitHub Actions enabled
- Different technologies

A public GitHub organization with many active repositories will be used as the source pool.

### Configuration File

```
config/repositories.csv
```

Example:

```csv
owner,repository,team,secondary_team,technology
org1,repo-a,Backend,Security,Python
org1,repo-b,Frontend,Platform,TypeScript
org1,repo-c,Data Platform,ML,Python
```

**As built:** 20 mid-sized public repositories, frozen in `config/repositories.csv`, chosen after measuring PR and CI volume for about 55 candidates (§44, problem 5). Team labels are simulated.

---

## 6. Historical Period

**6 complete months:**

```
2026-03-01 to 2026-08-31
```

This provides:

- Monthly trends
- Team comparisons
- Historical changes
- PR cycle analysis
- Issue trends
- CI trends

without creating unnecessary data volume.

---

## 7. Expected Data Size

Target:

```
20 repositories
8 teams
6 months
```

**Actual result (20 repositories, 2026-03-01 to 2026-08-31):**

```
3,542 pull requests
4,148 reviews
1,309 issues
2,782 commits
15,760 workflow runs
1,910 developers (18 bots)
```

Full breakdown in §47 and `docs/data_quality_initial.md`.

---

## 8. Technology Stack

| Purpose | Technology |
|---------|-----------|
| Extraction | Python, Requests, GitHub REST API, JSON |
| Data Cleaning | Python, Pandas |
| Distributed Processing | PySpark 4.x (run locally on Java 17); the notebook is Databricks-compatible |
| Database | PostgreSQL |
| Analytics | SQL |
| Visualization | Power BI |
| Testing | pytest (PySpark test on synthetic data) |
| Version Control | Git, GitHub |
| Configuration | YAML / CSV |
| Logging | Python logging module |

---

## 9. High-Level Architecture

```
┌─────────────────────┐
│   GitHub REST API    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Python Extraction   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    RAW JSON/CSV      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     PySpark          │
│  Gold build (keys,   │
│  dims, facts)        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Gold tables (CSV)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ PostgreSQL           │
│ Star Schema          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Advanced SQL         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Power BI Dashboard   │
└─────────────────────┘
```

---

## 10. Architecture Philosophy

We are **not** building a huge enterprise Bronze/Silver/Gold ecosystem for every dataset.

We will demonstrate the concept:

```
Raw → Cleaned → Analytics
```

but keep the implementation small and explainable.

**As built:** Bronze = `data/raw` (JSON), Silver = `data/cleaned` (CSV), Gold = `data/gold` (11 CSVs matching `schema.sql`).

---

## 11. Phase 0 — Environment Setup

### Install

- Python 3.x
- VS Code
- PostgreSQL (when needed)
- pgAdmin (when needed)
- Git
- Power BI Desktop (when needed)
- Java 17 (required by PySpark) and `pip install -r requirements.txt` inside a virtual environment
- Docker Desktop (optional: throwaway PostgreSQL for testing)

### Create

- Databricks Free Edition (when needed)

> **As built:** Databricks was not needed to run the project; the PySpark code runs locally. Uploading the repo to Databricks Community Edition is an optional extra.
>
> **Note:** Databricks Free Edition provides serverless compute but is quota-limited and has restricted outbound connectivity, so API extraction is handled by local Python.

---

## 12. Phase 1 — GitHub Authentication

Create a GitHub Personal Access Token (PAT) with minimum permissions needed for public data.

Store as `.env`:

```
GITHUB_TOKEN=xxxxx
```

**Never commit `.env`.** Add it to `.gitignore`.

Authentication provides:

- Higher rate limits (5000 requests/hour vs 60 unauthenticated)
- Access to more API capabilities

---

## 13. Phase 2 — Repository Discovery & Config

### Create `config/repositories.csv`

```csv
owner,repository,team,secondary_team,technology
```

### Create `config/config.yaml`

Centralized configuration (as built):

```yaml
company:
  name: "TechNova Engineering"
  teams: [Backend, Frontend, Data Platform, DevOps, Security, ML, Mobile, Platform]

date_range:
  start: "2026-03-01"
  end: "2026-08-31"

api:
  base_url: "https://api.github.com"
  per_page: 100
  max_retries: 3
  retry_delay: 5
  rate_limit_buffer: 100        # sleep until reset when fewer requests remain

paths:
  raw_data: "data/raw"
  cleaned_data: "data/cleaned"
  gold_data: "data/gold"
  quality_reports: "data/quality"
  sample_data: "data/sample"

repository_config: "config/repositories.csv"

scd2_demo:                       # seeded ownership change (demo data, not from GitHub)
  repository: "pallets/flask"
  from_team: Backend
  to_team: Platform
  change_date: "2026-06-01"
```

---

## 14. Phase 3 — Python API Client

### Create `ingestion/github_api.py`

The client handles:

- Authentication (token-based)
- GET requests
- Pagination (GitHub API returns data in pages)
- Retries (retry on failure)
- HTTP error handling
- Rate-limit handling: sleeps until the reset time when fewer than 100 requests remain, and honours the `retry-after` header on secondary (burst) limits
- Logging

> **Key Point:** The GitHub REST API is paginated — one API response does NOT contain the complete dataset. The client must follow pagination links.

---

## 15. Phase 4 — Individual Extractors

### Create `ingestion/extract.py`

Small extraction functions:

```
extract_repository_metadata()
extract_pull_requests_and_reviews()   # reviews only for PRs created in the window
extract_issues()
extract_commits()
extract_workflows()
run_extraction()                      # runs all of the above
```

**Resume behaviour:** a repository's file is written only when that repository is complete, and a rerun skips repositories that already have a file, so an interrupted run continues where it stopped. To redo everything, delete `data/raw`.

Each function follows the flow:

```
API → Pagination → Raw JSON → Local file
```

---

## 16. Raw Data Structure

```
data/
└── raw/
    ├── repositories/
    ├── pull_requests/
    ├── reviews/
    ├── issues/
    ├── commits/
    └── workflows/
```

> **Rule:** Never overwrite raw files during transformation.

---

## 17. Phase 5 — Data Profiling

### Create `notebooks/01_data_profiling.ipynb`

Check:

- Number of records
- Missing values
- Duplicate IDs
- Invalid timestamps
- Unexpected states
- Repositories with no PRs
- Repositories with no reviews
- Repositories without Actions

### Output

The notebook writes a raw-record profile to `data/quality/raw_profile.md`. The formal report, `docs/data_quality_initial.md`, records the real counts, the data problems found and the 17 programmatic checks (§31).

This proves actual data engineering rather than blindly processing data.

---

## 18. Phase 6 — Python Cleaning

Use Pandas for smaller API datasets.

Perform:

- Remove duplicate IDs
- Handle nulls
- Flatten nested JSON fields
- Normalize state values
- Separate issues from PRs (GitHub API quirk)

Timestamp typing (UTC) and username normalization (lower-case) happen in the Gold step (§19), where the keys are built.

---

## 19. Phase 7 — PySpark Transformations

### Built in `processing/build_gold.py` (the notebook `databricks/engineeringpulse_transformations.ipynb` calls the same code)

Run with `python run_pipeline.py gold`. Transformations:

1. Read the cleaned CSVs (all columns as strings, then cast explicitly; IDs go through a decimal so `41898282.0` casts exactly)
2. Convert timestamps (session time zone UTC) and keep only activity created inside the analysis window
3. Build surrogate keys with `row_number()` windows and the dimensions (`dim_date` from `sequence`/`explode`)
4. Build the team/repository bridge, including the seeded SCD2 ownership change
5. Join facts to dimension keys (case-insensitive developer match)
6. Create derived metrics:
   - `cycle_time_hours`
   - `review_delay_hours`
   - `resolution_hours` (issues)
   - `duration_seconds` (workflow runs; proxy, see §42)
7. Write 11 CSVs to `data/gold/`, one per warehouse table

---

## 20. Phase 8 — Databricks

**As built:** the layers are files on disk and Databricks is optional.

| Stage | Purpose | Location |
|-------|---------|----------|
| Bronze | Original ingested data | `data/raw/` (JSON) |
| Silver | Cleaned and typed data | `data/cleaned/` (CSV) |
| Gold | Final dimensional tables | `data/gold/` (CSV, 11 tables) |

The notebook runs the same PySpark code on a Databricks cluster (`get_spark()` reuses the cluster session). The project was run locally; running it on Databricks Community Edition is an optional extra.

Kept small — demonstrates the concept without enterprise overhead.

-------|---------|
| Bronze | Original ingested data |
| Silver | Cleaned and typed data |
| Gold | Final dimensional tables |

Kept small — demonstrates the concept without enterprise overhead.

---

## 21. Phase 9 — Data Model (Star Schema)

### Dimensions

- `dim_date`
- `dim_team`
- `dim_repository`
- `dim_developer`
- `dim_workflow` (workflow name/type dimension)

### Facts

- `fact_pull_request`
- `fact_review`
- `fact_issue`
- `fact_commit` (lightweight commit activity)
- `fact_workflow`

### Bridge

- `bridge_team_repository` (many-to-many team-repo relationship)

---

## 22. Dimension Tables

### dim_team

| Column | Description |
|--------|-------------|
| team_key | Surrogate key |
| team_name | Team name |
| valid_from | SCD2 start date |
| valid_to | SCD2 end date |
| is_current | Whether this is the current record |

### dim_repository

| Column | Description |
|--------|-------------|
| repository_key | Surrogate key |
| repository_id | GitHub repository ID |
| repository_name | Repo name |
| full_name | owner/repo |
| language | Primary language |
| created_at | When repo was created |
| archived | Whether archived |
| stars | Star count |
| valid_from | SCD2 start date |
| valid_to | SCD2 end date |
| is_current | Whether this is the current record |

### dim_developer

| Column | Description |
|--------|-------------|
| developer_key | Surrogate key |
| developer_id | GitHub user ID |
| username | GitHub username |
| developer_type | Type (User, Bot, etc.) |

### dim_date

| Column | Description |
|--------|-------------|
| date_key | Integer key (YYYYMMDD) |
| date | Actual date |
| year | Year |
| quarter | Quarter (1-4) |
| month | Month number |
| month_name | Month name |
| week | ISO week number |
| day | Day of month |
| day_name | Day name (Monday, etc.) |

### dim_workflow

| Column | Description |
|--------|-------------|
| workflow_key | Surrogate key |
| workflow_name | Most common name of the workflow (one row per GitHub `workflow_id`) |

---

## 23. Bridge Table

### bridge_team_repository

| Column | Description |
|--------|-------------|
| team_key | FK to dim_team |
| repository_key | FK to dim_repository |
| role | Primary / Contributor |
| valid_from | Start date of relationship |
| valid_to | End date (NULL if current) |
| is_current | Whether this is the current mapping |

Illustrative example (the built data has the same shape for `pallets/flask`: Backend until 2026-05-31, then Platform):

```
Backend    → payment-service → Primary    → 2026-03-01 → 2026-05-31 → 0
Platform   → payment-service → Primary    → 2026-06-01 → NULL       → 1
```

---

## 24. SCD Type 2

**Slowly Changing Dimension Type 2** — one of the strongest interview features.

When something changes (e.g., a repository changes team ownership), we do **not overwrite** the old record. Instead we:

1. Set `valid_to` and `is_current = 0` on the old record
2. Insert a new record with `valid_from` = change date and `is_current = 1`

This preserves the complete history:

```
Payment Service owned by Backend  → March-May
Payment Service owned by Platform → June-Present
```

This demonstrates historical data modeling.

---

## 25. Fact Tables

### fact_pull_request

Grain: **One row = one PR**

| Column | Description |
|--------|-------------|
| pr_key | Surrogate key |
| pr_id | Native GitHub PR id |
| repository_key | FK to dim_repository |
| developer_key | FK to dim_developer |
| created_date_key | FK to dim_date |
| created_at | PR creation timestamp |
| closed_at | PR close timestamp |
| merged_at | PR merge timestamp |
| state | open / closed |
| is_merged | Boolean |
| additions | Lines added |
| deletions | Lines removed |
| changed_files | Files changed |
| cycle_time_hours | Time from creation to merge |

### fact_review

Grain: **One row = one review**

| Column | Description |
|--------|-------------|
| review_key | Surrogate key |
| review_id | Native GitHub review id |
| pr_key | FK to fact_pull_request |
| repository_key | FK to dim_repository |
| reviewer_key | FK to dim_developer |
| review_date_key | FK to dim_date |
| state | APPROVED / CHANGES_REQUESTED / COMMENTED |
| submitted_at | Review submission timestamp |
| review_delay_hours | Time from PR creation to this review |

### fact_issue

Grain: **One row = one issue**

| Column | Description |
|--------|-------------|
| issue_key | Surrogate key |
| issue_id | Native GitHub issue id |
| repository_key | FK to dim_repository |
| developer_key | FK to dim_developer |
| date_key | FK to dim_date |
| created_at | Issue creation timestamp |
| closed_at | Issue close timestamp |
| state | open / closed |
| resolution_hours | Time from creation to close |

### fact_commit

Grain: **One row = one commit**

| Column | Description |
|--------|-------------|
| commit_key | Surrogate key |
| repository_key | FK to dim_repository |
| developer_key | FK to dim_developer (author) |
| date_key | FK to dim_date |
| commit_sha | Unique commit hash |
| timestamp | Commit timestamp |

### fact_workflow

Grain: **One row = one workflow run**

| Column | Description |
|--------|-------------|
| workflow_run_key | Surrogate key |
| workflow_run_id | Native GitHub run id |
| repository_key | FK to dim_repository |
| workflow_key | FK to dim_workflow |
| date_key | FK to dim_date |
| event | Trigger event |
| status | Run status |
| conclusion | Run conclusion |
| created_at | Run creation time |
| started_at | Run start time |
| updated_at | Run update time |
| duration_seconds | `updated_at - started_at` (proxy: the API gives no completion time) |

---

## 26. Business Metrics

### Team Metrics

- PR volume
- Merged PRs
- PR merge rate
- Average PR cycle time
- Median PR cycle time
- Review turnaround
- Issue resolution time
- CI success rate
- Release frequency

### Repository Metrics

- Open PR backlog
- Open issue backlog
- Issue aging
- PR cycle time
- Review time
- CI failure rate
- Contributor count
- Activity trend

### Collaboration Metrics

- Cross-team PRs
- Shared repositories
- Cross-team reviews
- Team/repository contribution distribution

> **As built:** every metric above is available except *Release frequency* (needs the releases API, not extracted). *Cross-team reviews* is SQL query 14 only, not a dashboard visual.

---

## 27. SQL Layer

### Files

```
sql/
├── schema.sql      — Creates PostgreSQL tables
└── analytics.sql   — 20 advanced analytical queries
```

### Target: ~20 Analytical Queries

Examples:

- Top repositories by PR volume
- Monthly team PR trend
- Average PR cycle by team
- Median PR cycle by team
- First-review latency
- Team ranking by month
- Month-over-month PR growth
- Rolling 7-day PR average
- Issue resolution by repository
- Oldest open issues
- CI success by repository
- CI trend by month
- Shared repositories
- Cross-team reviews
- Repository activity trend
- Commit frequency by developer
- Workflow duration trends

---

## 28. Required SQL Concepts

The project visibly demonstrates:

| Concept | Why It Matters |
|---------|----------------|
| INNER JOIN | Combine matching records |
| LEFT JOIN | Include records even without matches |
| CTEs | Break complex queries into readable steps |
| CASE | Conditional logic in SQL |
| GROUP BY | Aggregate data by categories |
| HAVING | Filter aggregated results |
| Subqueries | Queries within queries |
| ROW_NUMBER() | Assign sequential numbers |
| RANK() | Ranking with gaps |
| DENSE_RANK() | Ranking without gaps |
| LAG() | Access previous row's value |
| LEAD() | Access next row's value |
| SUM() OVER() | Running totals |
| AVG() OVER() | Moving averages |
| PARTITION BY | Window function grouping |

> **As built:** `analytics.sql` uses `JOIN` / `LEFT JOIN`, CTEs, `CASE`, `GROUP BY`, `HAVING`, subqueries, `ROW_NUMBER`, `RANK`, `LAG`, `PERCENTILE_CONT`, `SUM()/AVG() OVER` and `PARTITION BY`. `DENSE_RANK` and `LEAD` are not used.

### Example — Team Monthly Ranking

```sql
WITH monthly_team_prs AS (
    SELECT
        t.team_name,
        d.year,
        d.month,
        COUNT(*) AS merged_prs
    FROM fact_pull_request p
    JOIN dim_team t ON p.team_key = t.team_key
    JOIN dim_date d ON p.created_date_key = d.date_key
    WHERE p.is_merged = TRUE
    GROUP BY t.team_name, d.year, d.month
)
SELECT *,
       RANK() OVER (
           PARTITION BY year, month
           ORDER BY merged_prs DESC
       ) AS team_rank
FROM monthly_team_prs;
```

### Example — Rolling Average

```sql
AVG(pr_count) OVER (
    PARTITION BY team_name
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
)
```

---

## 29. PostgreSQL Setup

### Schema: `engineeringpulse`

### Tables

- dim_date
- dim_team
- dim_repository
- dim_developer
- dim_workflow
- fact_pull_request
- fact_review
- fact_issue
- fact_commit
- fact_workflow
- bridge_team_repository

### Indexes

Primary keys on every table plus single-column indexes on the foreign keys used most in joins (see `sql/schema.sql`).

---

## 30. Power BI Dashboards

> Step-by-step build instructions, the model and all DAX measures are in `docs/POWERBI_GUIDE.md`; the finished report is `powerbi/EngineeringPulse.pbix`.

### Dashboard 1 — Executive Overview

**KPIs:** Total Teams, Total Repositories, Active Developers, Total PRs, PR Merge Rate, Avg PR Cycle, Issue Backlog, CI Success Rate

**Charts:** PR trend, Issue trend, CI trend (Release trend not built: needs the releases API)

### Dashboard 2 — Team Performance

**Filters:** Date, Team, Repository, Technology

**Metrics:** PR volume, PR cycle, Review time, Issue resolution, CI success

> Do not create a fake "best team" score. Show multiple dimensions and let the viewer compare.

### Dashboard 3 — Repository Health

**Per repository:** PR backlog, Issue backlog, Average PR cycle, Review delay, CI success rate, Contributor count, Activity trend

**Drill path:** Team → Repository → PR / Issue / Workflow

### Dashboard 4 — Collaboration

**Visualize:** Team → Repository, Team → Team relationships

**Metrics:** Shared repositories, Cross-team PRs, Cross-team reviews

### Dashboard 5 — Engineering Bottlenecks

Automatically flag unusual changes:

```
Repository: payment-service
PR cycle time     ↑ 34%
Review delay      ↑ 46%
CI failures       ↑ 21%
Flag: Potential delivery bottleneck
```

> Say **"potential bottleneck"**, not "bad team."

---

## 31. Data Quality Module

### Create `processing/data_quality.py`

Checks:

- Duplicate PR IDs
- Duplicate repository IDs
- Null repository IDs
- Invalid dates
- Merged date < created date
- Review before PR creation
- Workflow end < start
- Invalid foreign keys

Runs on the Gold CSVs (no database needed): 17 checks, all passing on the final run.

### Output: `data/quality/data_quality_report.csv`

Runs as a pipeline step, callable from `run_pipeline.py`.

---

## 32. Project Structure

```
EngineeringPulse/
│
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── run_pipeline.py            # extract | clean | gold | quality | export
│
├── config/
│   ├── repositories.csv       # 20 repos mapped to 8 teams
│   └── config.yaml
│
├── data/                      # git-ignored, regenerated by the pipeline
│   ├── raw/                   # Bronze: JSON per repo per dataset
│   ├── cleaned/               # Silver: 6 CSVs
│   ├── gold/                  # Gold: 11 CSVs matching schema.sql
│   ├── quality/               # data_quality_report.csv
│   └── sample/
│
├── ingestion/
│   ├── github_api.py
│   └── extract.py
│
├── processing/
│   ├── clean_data.py
│   ├── build_gold.py          # PySpark
│   ├── data_quality.py
│   └── load_postgres.py
│
├── utils/
│   └── logger.py
│
├── databricks/
│   └── engineeringpulse_transformations.ipynb
│
├── notebooks/
│   └── 01_data_profiling.ipynb
│
├── sql/
│   ├── schema.sql
│   └── analytics.sql
│
├── tests/
│   └── test_gold.py
│
├── powerbi/
│   └── EngineeringPulse.pbix
│
└── docs/
    ├── PROJECT_REFERENCE.md
    ├── POWERBI_GUIDE.md
    ├── data_dictionary.md
    ├── data_quality_initial.md
    ├── er_diagram.md          # Mermaid ER diagram
    └── screenshots/           # one PNG per dashboard page
```

Approximately 25 meaningful files.

---

## 33. File Responsibilities

| File | Purpose |
|------|---------|
| `github_api.py` | Authentication, requests, pagination, retry, rate limiting |
| `extract.py` | Calls API for repos, PRs, reviews, issues, commits, workflows |
| `clean_data.py` | Flattening, null handling, deduplication, state normalization, issue/PR separation |
| `build_gold.py` | PySpark: typing, window filter, surrogate keys, dimensions, bridge, facts, derived metrics |
| `data_quality.py` | Programmatic quality checks, outputs report CSV |
| `load_postgres.py` | Creates the schema and loads the 11 Gold CSVs in foreign-key order, in one transaction |
| `run_pipeline.py` | Single entry point: extract → clean → gold → quality → export (steps can be run alone) |
| `logger.py` | Consistent logging format across all scripts |
| `config.yaml` | Centralized configuration (dates, paths, API settings) |
| `engineeringpulse_transformations.ipynb` | Runs the same PySpark Gold build from a notebook (local or Databricks) |
| `schema.sql` | Creates PostgreSQL dimensional tables |
| `analytics.sql` | 20 advanced SQL queries |
| `EngineeringPulse.pbix` | Power BI report (5 pages) |
| `tests/test_gold.py` | pytest check of the PySpark Gold logic on synthetic data |

---

## 34. Build Order

### Stage 1 — Prove the Data Exists

- Start with only 2-3 repositories
- Extract repos, PRs, reviews, issues, workflows
- Confirm the API data is sufficient

### Stage 2 — Freeze Dataset Design

- Expand to 20 repositories
- Set 6-month date range
- Create `repositories.csv` and team mapping
- Freeze configuration

### Stage 3 — Build Complete Python ETL

- API → Raw JSON → Cleaned CSV/Parquet
- Working end-to-end locally

### Stage 4 — Add PySpark

- Process with PySpark: read, transform, join, deduplicate, aggregate, window, write
- Run the PySpark Gold build (Databricks optional)

### Stage 5 — Build PostgreSQL Warehouse

- Create dimensions, facts, bridge table
- Load transformed data

### Stage 6 — Implement SCD Type 2

- Add historical team-repository ownership
- Separate milestone — conceptually important

### Stage 7 — Advanced SQL

- Write 20 analytical queries
- Verify metrics on small subset

### Stage 8 — Power BI

- Connect PostgreSQL
- Build 5 dashboard pages

### Stage 9 — Data Quality + Documentation

- Data dictionary, architecture diagram, ER diagram
- Methodology, limitations, screenshots

---

## 35. What We Do NOT Build

```
Kafka, Airflow, AWS, Azure, Snowflake, dbt, Tableau, Qlik,
Machine Learning, Real-time Streaming, Mobile App, Complex Web Frontend
```

These do not materially improve the project's fit for target roles.

---

## 36. Optional Extensions

Only after the core project works:

1. **Incremental ETL** — Fetch only new/updated data since last run
2. **GitHub Actions** — Automate ETL → Testing → Database refresh
3. **GH Archive** — Add historical event data for large-scale processing

---

## 37. What the Project Demonstrates

| Category | Technologies/Concepts |
|----------|----------------------|
| Data Gathering | GitHub REST API |
| Data Cleaning | Python + Pandas |
| ETL | Python extraction → transformation → PostgreSQL loading |
| Big Data | PySpark (Databricks-compatible) |
| Data Modeling | Star schema, Fact tables, Dimension tables, Bridge table, SCD Type 2 |
| SQL | Joins, CTEs, Window functions, Subqueries, Aggregations |
| BI | Power BI |
| Engineering | Git, GitHub, API, JSON, Data quality, Documentation |

---

## 38. Faculty Explanation

> **Problem:** Engineering teams generate a large amount of GitHub data, but raw data doesn't directly provide team-level operational insights.
>
> **Input:** We collect repository, pull-request, review, issue and workflow data through the GitHub REST API.
>
> **ETL:** Python handles extraction and initial cleaning. PySpark builds the Gold tables (keys, dimensions, derived metrics).
>
> **Storage:** Cleaned data is modeled in PostgreSQL using a dimensional/star schema.
>
> **Advanced Modeling:** A bridge table handles many-to-many team/repository relationships, while SCD Type 2 preserves historical ownership.
>
> **Analytics:** SQL calculates cycle time, review latency, issue resolution, CI success and team/repository trends.
>
> **Output:** Power BI converts these metrics into an interactive management dashboard.

---

## 39. Interview Explanation

> "I built an end-to-end engineering analytics platform using GitHub's REST API. I designed a Python ETL pipeline to extract repository, PR, review, issue and workflow data, cleaned and normalized it, built the Gold layer in PySpark (surrogate keys, joins, derived metrics), and modeled the data into a star-schema PostgreSQL warehouse. I implemented an SCD Type 2 relationship for historical team-repository ownership and used advanced SQL with CTEs and window functions to calculate engineering KPIs. Finally, I built a Power BI dashboard for team, repository, collaboration and CI/CD analysis."

---

## 40. Final Technology Flow

```
              GITHUB
                │
                ▼
       GitHub REST API
                │
                ▼
            PYTHON
                │
       Extract + Clean
                │
                ▼
          RAW DATA
                │
                ▼
           PYSPARK
                │
      Transform + Join
                │
                ▼
         GOLD TABLES
                │
   data/gold/*.csv (11 tables)
                │
                ▼
          POSTGRESQL
                │
     Star Schema + SCD2
                │
                ▼
         ADVANCED SQL
                │
                ▼
           POWER BI
                │
                ▼
    ENGINEERING INTELLIGENCE
```

---

## 41. Final Scope Summary

| Item | Value |
|------|-------|
| Repositories | 20 |
| Teams | 8 |
| Historical Period | 6 months (March-August 2026) |
| ETL | Python |
| Big Data | PySpark (run locally; notebook is Databricks-compatible) |
| Database | PostgreSQL |
| Schema | Star schema + SCD Type 2 |
| SQL Queries | 20 analytical queries |
| Dashboards | 5 Power BI pages |
| Project Files | ~25 meaningful files |

---

## 42. Implementation Notes & Known Limitations

What was actually built, where it differs from the plan above, and what to say about it.

| Topic | As built |
|-------|----------|
| Repositories | 20 mid-sized public repos (about 3,500 PRs in the window), chosen for a tractable extraction; the list is in `config/repositories.csv` |
| Gold layer | PySpark (`processing/build_gold.py`), run with `python run_pipeline.py gold`; the notebook calls the same code. Output is written through pandas because Spark's CSV writer needs `winutils` on Windows. Run locally; not run on Databricks unless you do so yourself |
| SCD Type 2 | `bridge_team_repository` holds real history for one seeded change (pallets/flask: Backend to Platform on 2026-06-01, set in `config.yaml`); `dim_team` and `dim_repository` carry the SCD columns but each has one version |
| `views.sql` | Not built; `analytics.sql` covers the same ground |
| Data quality | `processing/data_quality.py`, 17 checks on the Gold CSVs, run as a pipeline step |
| PR size metrics | `additions`, `deletions`, `changed_files` are NULL (the PR list endpoint does not return them; one call per PR was judged too expensive) |
| Workflow duration | Proxy: `updated_at - run_started_at` |
| Workflow history | GitHub caps filtered workflow-run queries, so very busy repos may have partial CI history |
| Time attribution | Queries attribute PRs to a repository's current team, not the team at the time |
| Snapshot state | Open issue / PR `state` is as of the extraction date (2026-09-26), not the end of the window |
| Release metrics | Not built (would need the releases API) |
| Cross-team reviews | SQL query 14 only; not a Power BI visual |
| Resume / rate limits | Extraction skips repositories that are already saved and sleeps when the GitHub rate limit runs low |
| Real vs. simulated | All activity is real public GitHub data; the company, teams and ownership are simulated |

---

## 43. Build Log — Phase by Phase

Each phase lists what it delivered, the files, and how it was checked. Numbers in brackets point to problems in §44.

### Phase 0 — Environment
- Python 3.14 virtual environment (`venv`), Java 17 for PySpark, PostgreSQL 18, pgAdmin/psql, Power BI Desktop, Docker Desktop.
- `requirements.txt`: requests, pandas, python-dotenv, PyYAML, psycopg2-binary, pyspark, pyarrow, pytest, jupyter. `.gitignore` excludes `.env`, `venv/` and `data/`.
- Checked by importing the packages and starting a local Spark session. [9, 10]

### Phase 1 — GitHub authentication
- A personal access token in `.env` (`GITHUB_TOKEN`); `.env.example` documents every variable, including the `DB_*` values.
- Checked with `python -m ingestion.github_api`, which reports the rate limit (5,000 requests/hour).

### Phase 2 — Repository discovery and config
- `config/config.yaml` (window, API settings, paths, company teams, SCD2 demo) and `config/repositories.csv` (repo → primary team, secondary team, technology).
- The first list had 23 famous repos (Kubernetes, React, vscode, Spark, PyTorch and others). It was replaced by 20 mid-sized repos after measuring volume. [5]

### Phase 3 — API client (`ingestion/github_api.py`)
- Token auth, connection-pooled session, pagination through `Link` headers, retries, and rate-limit handling (sleep until reset when fewer than 100 requests remain; honour `retry-after`). [8]

### Phase 4 — Extractors (`ingestion/extract.py`)
- Repository metadata, PRs, reviews, issues, commits and workflow runs, saved as one JSON file per repo per dataset in `data/raw/`.
- PRs are listed newest-updated first and pagination stops at the window start. Reviews are fetched only for PRs created in the window. A repo is written only when complete, and a rerun skips finished repos. [4, 6, 7]

### Phase 5 — Data profiling
- `notebooks/01_data_profiling.ipynb` counts records per dataset; `docs/data_quality_initial.md` records the real counts and the issues found. The notebook writes its raw profile to `data/quality/raw_profile.md`. [17]

### Phase 6 — Python cleaning (`processing/clean_data.py`)
- Flattens nested JSON, removes duplicate ids, normalizes states, handles nulls, and filters pull requests out of the issues data.
- Repo names are recovered from file names by lookup in `repositories.csv`. [3]

### Phase 7 — PySpark transformations (`processing/build_gold.py`)
- Reads the cleaned CSVs, types them, filters to the window, builds surrogate keys and all dimensions, the SCD2 bridge, the five facts and the derived metrics, and writes 11 CSVs to `data/gold/`. [1, 10, 11, 12, 13]
- The original notebook only re-saved the cleaned CSVs with two extra columns; it was replaced.

### Phase 8 — Layers and Databricks
- Bronze `data/raw`, Silver `data/cleaned`, Gold `data/gold`. The notebook runs the same PySpark code and can run on Databricks Community Edition (optional).

### Phase 9 — Data model, loader and SQL
- `sql/schema.sql`: 5 dimensions, 1 bridge, 5 facts, indexes, in schema `engineeringpulse`.
- `processing/load_postgres.py`: creates the schema and loads the 11 tables in foreign-key order, in one transaction, and raises on any error. [2, 14]
- `sql/analytics.sql`: 20 queries using joins (`JOIN`, `LEFT JOIN`), CTEs, `CASE`, `HAVING`, subqueries, `ROW_NUMBER`, `RANK`, `LAG`, `PERCENTILE_CONT`, and a rolling 7-day `AVG() OVER`. (`DENSE_RANK` and `LEAD`, listed in §28, are not used.) [16]

### Data-quality stage
- `processing/data_quality.py`: 17 checks (duplicates, null keys, impossible dates, orphan foreign keys, repos without an owner). It exits with an error if any fail, so `run_pipeline.py` stops before loading.

### Power BI stage
- Import connection to PostgreSQL, a model of 17 relationships, 22 DAX measures and 5 report pages. Steps and DAX are in `docs/POWERBI_GUIDE.md`. [19–23]

### Testing and documentation
- `tests/test_gold.py` runs the PySpark build on tiny synthetic data with known answers (see §46).
- All docs were reconciled with the built system, and `PROJECT_REFERENCE.md` sections 42–47 were added.

---

## 44. Problems Met and How They Were Solved

| # | Problem | Cause | How it was solved |
|---|---------|-------|-------------------|
| 1 | The pipeline looked finished but could not load a warehouse | The first PySpark notebook re-saved the cleaned CSVs with a couple of new columns: no surrogate keys, no `dim_date`, `dim_team`, `dim_developer`, `dim_workflow`, `fact_commit` or bridge, and column names that did not match `schema.sql` | Wrote `build_gold.py` to produce 11 tables whose columns match `schema.sql` exactly |
| 2 | The loader would have failed and hidden it | It inserted CSV columns straight into differently-shaped tables and swallowed exceptions | Rewrote it: fixed load order (parents first), one transaction, raise on error, row count per table |
| 3 | Repo names were mis-read from file names | `owner_repo_prs.json` was converted back with `_` → `/`, which is wrong for names like `next.js`, `node_exporter`, `react-native` | `repo_name_from_file()` looks the name up in `repositories.csv` |
| 4 | Everything downstream was tested on 2 repos | The extractor had been run in test mode (2 repos, one page, reviews for 5 PRs) | Deleted the sample and ran the full extraction |
| 5 | The first repo list was too big | 23 huge repos would have meant an estimated 20,000+ PRs (not measured) and many hours of rate-limited calls | Queried the GitHub search API for about 55 candidates (PRs created in the window, workflow runs, archived flag) and picked 20 mid-sized ones (about 3,500 PRs) covering all 8 teams |
| 6 | Wasted API calls | Reviews were fetched for every PR *updated* since March, including PRs created years ago that the warehouse drops anyway | Fetch reviews only for PRs created inside the window |
| 7 | An interrupted run had to restart, and a failed PR listing could be saved as "done" | No resume logic; a caught pagination error saved a partial list | A repo's file is written last, only when complete; reruns skip finished repos; a failed repo saves nothing |
| 8 | Burst rate limits | Only the hourly limit was handled | The client waits for the `retry-after` header on 403/429 |
| 9 | `pip install pyspark` failed | The 400 MB download dropped the connection | Retried with `--retries`; PySpark 4.2 works on Python 3.14 with Java 17; added `pyarrow` |
| 10 | Spark could not write CSV on Windows | Spark's writer needs `winutils.exe` / `HADOOP_HOME` | Spark does all transformation; `toPandas()` writes the CSVs (documented as a known ceiling; on a cluster use `df.write`) |
| 11 | Possible one-day errors in `dim_date` | `collect()` returns timestamps in the machine's time zone, not Spark's UTC | The date range is computed with Spark's `to_date` (UTC), and the Spark session time zone is fixed to UTC |
| 12 | `CAST_INVALID_INPUT: '41898282.0'` in the gold step | Pandas writes integer columns with blanks as floats (`41898282.0`), and Spark refuses to cast that text to a long | `_num()` casts through `decimal(20,0)`, which is exact; a regression test now reproduces it |
| 13 | `value too long for type character varying(255)` on load | GitHub reports some runs' name as the run title (a PR title), giving 845 "workflow names" for 197 real workflows | `dim_workflow` is keyed by `workflow_id`, using each workflow's most common name, capped at 255 characters; a regression test covers it |
| 14 | PostgreSQL setup on Windows | Login prompts, database not yet created, credentials not in `.env` | Created `engineeringpulse` with `CREATE DATABASE`, added the `DB_*` variables, and verified with a connection test |
| 15 | How to test the warehouse without risking the real database | — | Used a throwaway Docker PostgreSQL 16 on port 5433, loaded the sample, ran all 20 queries, and removed the container |
| 16 | Analytics query 17 returned nothing | It was hard-coded to a repo named `payment-service` | Pointed it at the seeded repo (`flask`), which returns the 3 ownership rows |
| 17 | The profiling notebook could overwrite the quality report | It wrote `docs/data_quality_initial.md` | It now writes `data/quality/raw_profile.md` |
| 18 | The Spark test was slow and noisy | JVM start-up and missing Arrow | Kept one small test (about 1 minute), installed `pyarrow`, and silenced warnings in the run commands |
| 19 | Power BI would not connect / tables had ugly names | Missing Npgsql driver; tables were named `engineeringpulse fact_...`, which broke the DAX names | Installed the driver; renamed all 11 queries in Power Query |
| 20 | Wrong numbers and dotted (inactive) relationships | Auto-detected relationships were one-to-one and both-direction (`fact_review` ↔ PR, developer, date, repository); the extra path made Power BI deactivate lines | Deleted the PR ↔ review link; recreated every relationship many-to-one, single direction and active; only the repository ↔ bridge link is Both |
| 21 | "Column contains a duplicate value '152'" | A fact table was chosen as the "one" side of `workflow_key` | Fact first, dimension second, cardinality Many to one |
| 22 | Cards showed 2 repos and 118 PRs | The report still held the sample load | **Home → Refresh** |
| 23 | "We can't sort the 'day' column by 'month'"; trend charts showed `20260300`; `fact_workflow` not linked | Sorted the wrong column; used `date_key` instead of `date` on the axis; `fact_workflow` had not been loaded | Sort `month_name` by `month`; use `dim_date[date]` on axes; load `fact_workflow` and add its 3 relationships |
| 24 | Slicers and axes showed months outside the window | `dim_date` spans every date any fact touches, including reviews submitted after 31 Aug | A report-level date filter (2026-03-01 to 2026-08-31) |

---

## 45. Design Decisions and Why

| Decision | Why |
|----------|-----|
| Window is by **creation date** (PRs, issues, commits, workflow runs created 2026-03-01 to 2026-08-31) | The API returns everything *updated* since March; counting by creation makes monthly trends and cycle times comparable |
| Reviews only for in-window PRs | Every review must point at a PR in `fact_pull_request`; also halves the API calls |
| One row per `workflow_id` in `dim_workflow` | The run "name" is unreliable (it can be a PR title) |
| Usernames lower-cased before keying | "Alice" and "alice" must be the same developer across PRs, reviews, issues and commits |
| Unknown authors kept as `unknown` (8 developers with no numeric id) | Commits without a linked GitHub account are still real activity |
| Surrogate keys assigned in PySpark with `row_number()` over a fixed order | Deterministic keys; no dependence on database sequences |
| Bridge table holds the ownership history; `dim_team` / `dim_repository` carry SCD columns with one version | The many-to-many and the history live in one place; a single seeded change (flask: Backend → Platform on 2026-06-01) gives the SCD2 something to show |
| Whole database load in one transaction | Either all 11 tables load or none, so there are no half-loaded warehouses |
| Quality checks stop the pipeline | A failed check exits non-zero before `export` |
| Power BI in **Import** mode with single-direction, many-to-one relationships | Fast, predictable filtering; only repository ↔ bridge is bi-directional so a team filter reaches the facts |
| Bridge filtered to `role = Primary` and `is_current = True` on ownership pages | Stops a repository being counted once per team it contributes to |
| Bottleneck flag = cycle time above 1.5× the organisation average **and** CI failure rate above average | Relative to the data instead of arbitrary fixed hours; worded "potential bottleneck", never "bad team" |
| Real activity, simulated organisation | Real private team data is not public; the assumption is stated everywhere |

---

## 46. How to Run and Test

### One-time setup
1. Install Python, Java 17, PostgreSQL, and Power BI Desktop (Docker optional).
2. `python -m venv venv`, activate it, then `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`; set `GITHUB_TOKEN` and the `DB_*` values.
4. In `psql` (or pgAdmin): `CREATE DATABASE engineeringpulse;`
5. Check the connections:
   - `python -m ingestion.github_api` → "Authentication Successful", 5,000 requests remaining
   - `python -c "from processing.load_postgres import get_db_connection as g; print(g().server_version)"`

### Run the pipeline
```
python run_pipeline.py extract    # long (about 1-2 hours); rate-limit pauses are normal; safe to rerun
python run_pipeline.py clean
python run_pipeline.py gold       # PySpark
python run_pipeline.py quality    # must show no FAIL
python run_pipeline.py export     # recreates the schema and loads all tables
```
To redo extraction from scratch, delete `data/raw` first.

### How each layer is tested
| Layer | Test | How to run |
|-------|------|------------|
| Gold logic | `tests/test_gold.py`: synthetic data with known answers (36 h cycle time, 6 h review delay, 48 h issue resolution, 600 s workflow, window filtering, SCD2 dates, case-insensitive developer match, float-looking ids, over-long workflow names) | `python -m pytest tests -q` (about 1 minute) |
| Data | 17 checks on the real Gold tables | `python run_pipeline.py quality` |
| Load | Row counts printed per table; foreign keys enforced by PostgreSQL | `python run_pipeline.py export` |
| SQL | All 20 queries execute and return rows | run `sql/analytics.sql` in pgAdmin |
| Dashboards | Cards match the expected values in §47 | Power BI, with the date filter on and no slicers |

### Refresh Power BI after a new run
Open `powerbi/EngineeringPulse.pbix` and click **Home → Refresh**.

---

## 47. Final Results

### Warehouse contents
| Table | Rows |
|-------|------|
| dim_date | 210 |
| dim_team | 8 |
| dim_repository | 20 |
| dim_developer | 1,910 (18 bots) |
| dim_workflow | 197 |
| bridge_team_repository | 41 |
| fact_pull_request | 3,542 (1,774 merged) |
| fact_review | 4,148 |
| fact_issue | 1,309 (295 open on the extraction date) |
| fact_commit | 2,782 |
| fact_workflow | 15,760 |

Verification: 17 of 17 quality checks pass; 20 of 20 analytics queries run.

### What the data shows (for talking points)
- **Review outcomes:** 1,637 approved, 2,274 commented, 229 changes requested, 8 dismissed.
- **CI:** 11,742 successes and 2,678 failures among 15,760 runs; success rate about 74.5% of completed runs.
- **Average PR cycle time (hours, by current primary team):** Backend 46, Data Platform 49, Security 87, Frontend 114, Mobile 160, Platform 195, DevOps 204, ML 289. Long cycle times are normal for volunteer-reviewed open-source projects; the comparison, not the absolute number, is the point.

### Power BI expected values (date filter on, no slicers)
Total PRs 3,542 · Merged PRs 1,774 (50.1%) · Repositories 20 · Teams 8 · Reviews 4,148 (a few submitted after 31 Aug leave the monthly charts) · Commits 2,782 · CI runs 15,760 · Open issues 295.

### Deliverables
`powerbi/EngineeringPulse.pbix` (5 pages), `docs/screenshots/`, the 11-table warehouse, the `sql/analytics.sql` query set, and the documents in `docs/`.

---

*This is large enough to be a serious portfolio project, but small enough that every component can be explained to faculty and every technology choice defended in an interview.*
