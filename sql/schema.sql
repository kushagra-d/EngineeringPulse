-- ==============================================================================
-- EngineeringPulse Data Warehouse Schema (PostgreSQL)
-- Implements a Star Schema with a Bridge Table and SCD Type 2 history.
-- ==============================================================================

DROP SCHEMA IF EXISTS engineeringpulse CASCADE;
CREATE SCHEMA engineeringpulse;
SET search_path TO engineeringpulse;

-- ==============================================================================
-- 1. DIMENSION TABLES
-- ==============================================================================

-- Date Dimension (Standard calendar)
CREATE TABLE dim_date (
    date_key INT PRIMARY KEY,           -- e.g., 20260301
    date DATE NOT NULL,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    week INT NOT NULL,
    day INT NOT NULL,
    day_name VARCHAR(20) NOT NULL
);

-- Team Dimension (SCD Type 2)
CREATE TABLE dim_team (
    team_key SERIAL PRIMARY KEY,        -- Surrogate Key
    team_name VARCHAR(100) NOT NULL,
    valid_from DATE NOT NULL,           -- SCD2 Start
    valid_to DATE,                      -- SCD2 End (NULL if current)
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);

-- Repository Dimension (SCD Type 2)
CREATE TABLE dim_repository (
    repository_key SERIAL PRIMARY KEY,  -- Surrogate Key
    repository_id BIGINT NOT NULL,      -- GitHub ID
    repository_name VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    language VARCHAR(100),
    created_at TIMESTAMP,
    archived BOOLEAN,
    stars INT,
    valid_from DATE NOT NULL,           -- SCD2 Start
    valid_to DATE,                      -- SCD2 End
    is_current BOOLEAN NOT NULL DEFAULT TRUE
);

-- Developer Dimension
CREATE TABLE dim_developer (
    developer_key SERIAL PRIMARY KEY,   -- Surrogate Key
    developer_id BIGINT,                -- GitHub User ID
    username VARCHAR(100) NOT NULL,
    developer_type VARCHAR(50) DEFAULT 'User'
);

-- Workflow Dimension
CREATE TABLE dim_workflow (
    workflow_key SERIAL PRIMARY KEY,
    workflow_name VARCHAR(255) NOT NULL
);


-- ==============================================================================
-- 2. BRIDGE TABLE (Resolves Many-to-Many between Teams and Repositories)
-- ==============================================================================

-- Bridge Team Repository (SCD Type 2)
CREATE TABLE bridge_team_repository (
    team_key INT REFERENCES dim_team(team_key),
    repository_key INT REFERENCES dim_repository(repository_key),
    role VARCHAR(50) NOT NULL,          -- 'Primary' or 'Contributor'
    valid_from DATE NOT NULL,           -- SCD2 Start
    valid_to DATE,                      -- SCD2 End
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (team_key, repository_key, valid_from)
);


-- ==============================================================================
-- 3. FACT TABLES
-- ==============================================================================

-- Fact Pull Request (Grain: One row per PR)
CREATE TABLE fact_pull_request (
    pr_key SERIAL PRIMARY KEY,
    pr_id BIGINT NOT NULL,
    repository_key INT REFERENCES dim_repository(repository_key),
    developer_key INT REFERENCES dim_developer(developer_key),
    created_date_key INT REFERENCES dim_date(date_key),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    closed_at TIMESTAMP,
    merged_at TIMESTAMP,
    state VARCHAR(20) NOT NULL,
    is_merged BOOLEAN NOT NULL,
    additions INT,
    deletions INT,
    changed_files INT,
    cycle_time_hours NUMERIC(10, 2)
);

-- Fact Review (Grain: One row per Review)
CREATE TABLE fact_review (
    review_key SERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL,
    pr_key INT REFERENCES fact_pull_request(pr_key),
    repository_key INT REFERENCES dim_repository(repository_key),
    reviewer_key INT REFERENCES dim_developer(developer_key),
    review_date_key INT REFERENCES dim_date(date_key),
    state VARCHAR(50) NOT NULL,
    submitted_at TIMESTAMP NOT NULL,
    review_delay_hours NUMERIC(10, 2)
);

-- Fact Issue (Grain: One row per Issue)
CREATE TABLE fact_issue (
    issue_key SERIAL PRIMARY KEY,
    issue_id BIGINT NOT NULL,
    repository_key INT REFERENCES dim_repository(repository_key),
    developer_key INT REFERENCES dim_developer(developer_key),
    date_key INT REFERENCES dim_date(date_key),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    closed_at TIMESTAMP,
    state VARCHAR(20) NOT NULL,
    resolution_hours NUMERIC(10, 2)
);

-- Fact Commit (Grain: One row per Commit)
CREATE TABLE fact_commit (
    commit_key SERIAL PRIMARY KEY,
    commit_sha VARCHAR(40) NOT NULL,
    repository_key INT REFERENCES dim_repository(repository_key),
    developer_key INT REFERENCES dim_developer(developer_key),
    date_key INT REFERENCES dim_date(date_key),
    timestamp TIMESTAMP NOT NULL
);

-- Fact Workflow (Grain: One row per Workflow Run)
CREATE TABLE fact_workflow (
    workflow_run_key SERIAL PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL,
    repository_key INT REFERENCES dim_repository(repository_key),
    workflow_key INT REFERENCES dim_workflow(workflow_key),
    date_key INT REFERENCES dim_date(date_key),
    event VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    conclusion VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    updated_at TIMESTAMP,
    duration_seconds NUMERIC(10, 2)
);

-- ==============================================================================
-- 4. INDEXES FOR PERFORMANCE
-- ==============================================================================

CREATE INDEX idx_fact_pr_repo ON fact_pull_request(repository_key);
CREATE INDEX idx_fact_pr_date ON fact_pull_request(created_date_key);
CREATE INDEX idx_fact_pr_dev ON fact_pull_request(developer_key);

CREATE INDEX idx_fact_review_pr ON fact_review(pr_key);
CREATE INDEX idx_fact_review_repo ON fact_review(repository_key);

CREATE INDEX idx_fact_issue_repo ON fact_issue(repository_key);
CREATE INDEX idx_fact_commit_repo ON fact_commit(repository_key);

CREATE INDEX idx_bridge_team ON bridge_team_repository(team_key);
CREATE INDEX idx_bridge_repo ON bridge_team_repository(repository_key);
