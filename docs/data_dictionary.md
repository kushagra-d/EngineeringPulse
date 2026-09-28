# EngineeringPulse Data Dictionary

This document details the schema of the PostgreSQL data warehouse for the EngineeringPulse project.

## Dimensions

### `dim_team`
Represents engineering teams within the organization. Utilizes Slowly Changing Dimension (SCD) Type 2.
* `team_key` (PK): Surrogate key.
* `team_name`: Name of the team (e.g., "Backend", "Data Platform").
* `valid_from`: Start date of this team record's validity.
* `valid_to`: End date of validity (NULL if it is the current record).
* `is_current`: Boolean indicating if this is the active record for the team.

### `dim_repository`
Represents GitHub repositories. Utilizes SCD Type 2.
* `repository_key` (PK): Surrogate key.
* `repository_id`: Native GitHub repository ID.
* `repository_name`: Short name of the repository (e.g., "flask").
* `full_name`: Organization and repository name (e.g., "pallets/flask").
* `language`: Primary programming language.
* `created_at`: Original creation timestamp in GitHub.
* `archived`: Boolean indicating if the repo is read-only.
* `valid_from` / `valid_to` / `is_current`: SCD Type 2 tracking columns.

### `dim_developer`
Represents GitHub users/contributors.
* `developer_key` (PK): Surrogate key.
* `developer_id`: Native GitHub user ID.
* `username`: GitHub login handle.
* `developer_type`: 'User' or 'Bot'.

### `dim_workflow`
Represents CI/CD workflows, one row per GitHub `workflow_id` (197 rows).
* `workflow_key` (PK): Surrogate key.
* `workflow_name`: The workflow's most common name across its runs, cut to 255 characters. GitHub reports some runs' name as the run title, so the raw name is not stable.

### `dim_date`
Standard calendar dimension for time-series analytics.
* `date_key` (PK): Integer representation of the date (YYYYMMDD).
* `date`: Standard DATE format.
* `year`, `quarter`, `month`, `month_name`, `week`, `day`, `day_name`: Extracted date parts.

---

## Bridge Table

### `bridge_team_repository`
Resolves the Many-to-Many relationship between Teams and Repositories (SCD Type 2).
* `team_key` (FK): Reference to `dim_team`.
* `repository_key` (FK): Reference to `dim_repository`.
* `role`: Level of ownership (e.g., "Primary", "Contributor").
* `valid_from` / `valid_to` / `is_current`: Tracks when a team owned a repo.

---

## Fact Tables

### `fact_pull_request`
Grain: One row per Pull Request.
* `pr_key` (PK): Surrogate key.
* `pr_id`: Native GitHub PR ID.
* `repository_key` (FK): The repo the PR belongs to.
* `developer_key` (FK): The author of the PR.
* `created_date_key` (FK): Links to `dim_date` for PR creation.
* `created_at`, `closed_at`, `merged_at`: Core timestamps.
* `state`: 'open' or 'closed'.
* `is_merged`: Boolean.
* `additions`, `deletions`, `changed_files`: Code churn metrics. Always NULL: the PR list endpoint does not return them.
* `cycle_time_hours`: Derived metric (merged_at - created_at).

### `fact_review`
Grain: One row per PR Review.
* `review_key` (PK): Surrogate key.
* `pr_key` (FK): Links back to `fact_pull_request`.
* `repository_key` (FK): Links to `dim_repository`.
* `reviewer_key` (FK): Links to `dim_developer`.
* `state`: Review outcome (e.g., 'APPROVED', 'CHANGES_REQUESTED').
* `submitted_at`: When the review was submitted.
* `review_delay_hours`: Derived metric (submitted_at - pr_created_at).

### `fact_issue`
Grain: One row per Issue (excluding PRs).
* `issue_key` (PK): Surrogate key.
* `repository_key` (FK): Links to `dim_repository`.
* `created_at`, `closed_at`: Core timestamps.
* `state`: 'open' or 'closed'.
* `resolution_hours`: Derived metric (closed_at - created_at).

### `fact_commit`
Grain: One row per Commit.
* `commit_key` (PK): Surrogate key.
* `commit_sha`: Git commit hash.
* `repository_key`, `developer_key`, `date_key`: Foreign keys.
* `timestamp`: When the commit was made.

### `fact_workflow`
Grain: One row per CI/CD Workflow Run.
* `workflow_run_key` (PK): Surrogate key.
* `repository_key`, `workflow_key`, `date_key`: Foreign keys.
* `event`: Trigger event (e.g., 'push', 'pull_request').
* `conclusion`: Run result (e.g., 'success', 'failure').
* `duration_seconds`: Derived metric (updated_at - started_at). A proxy, because the API gives no completion time.

---

## Notes

* `pr_id`, `review_id`, `issue_id`, `workflow_run_id` are the native GitHub ids; the `*_key` columns are warehouse surrogate keys generated in `processing/build_gold.py`.
* `fact_review`, `fact_issue`, `fact_pull_request` and `fact_workflow` hold only activity created in 2026-03-01 to 2026-08-31.
* `valid_from` / `valid_to` / `is_current` on `dim_team` and `dim_repository` are all "current" (one version per row). Real history is in `bridge_team_repository`, where one ownership change is seeded (see `scd2_demo` in `config/config.yaml`).
* Usernames are lower-cased so the same person matches across PRs, reviews, issues and commits.
