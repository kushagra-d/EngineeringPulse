-- ==============================================================================
-- EngineeringPulse Advanced Analytics (SQL Layer)
-- Demonstrates JOINs, CTEs, Window Functions, Rank, and Aggregations.
-- ==============================================================================

SET search_path TO engineeringpulse;

-- ------------------------------------------------------------------------------
-- TEAM PERFORMANCE METRICS
-- ------------------------------------------------------------------------------

-- 1. Monthly PR Volume by Team
SELECT 
    t.team_name,
    d.year,
    d.month,
    COUNT(pr.pr_key) AS total_prs,
    SUM(CASE WHEN pr.is_merged = TRUE THEN 1 ELSE 0 END) AS merged_prs,
    ROUND(AVG(pr.cycle_time_hours), 2) AS avg_cycle_time_hours
FROM fact_pull_request pr
JOIN bridge_team_repository btr ON pr.repository_key = btr.repository_key AND btr.is_current = TRUE
JOIN dim_team t ON btr.team_key = t.team_key AND t.is_current = TRUE
JOIN dim_date d ON pr.created_date_key = d.date_key
GROUP BY t.team_name, d.year, d.month
ORDER BY d.year, d.month, total_prs DESC;

-- 2. Team Ranking by Merged PRs (Window Function: RANK)
WITH monthly_team_prs AS (
    SELECT
        t.team_name,
        d.year,
        d.month,
        COUNT(*) AS merged_prs
    FROM fact_pull_request pr
    JOIN bridge_team_repository btr ON pr.repository_key = btr.repository_key AND btr.is_current = TRUE
    JOIN dim_team t ON btr.team_key = t.team_key AND t.is_current = TRUE
    JOIN dim_date d ON pr.created_date_key = d.date_key
    WHERE pr.is_merged = TRUE
    GROUP BY t.team_name, d.year, d.month
)
SELECT 
    *,
    RANK() OVER (PARTITION BY year, month ORDER BY merged_prs DESC) AS team_rank
FROM monthly_team_prs;

-- 3. Month-over-Month PR Growth (Window Function: LAG)
WITH monthly_volume AS (
    SELECT 
        t.team_name,
        d.year,
        d.month,
        COUNT(pr.pr_key) AS current_month_prs
    FROM fact_pull_request pr
    JOIN bridge_team_repository btr ON pr.repository_key = btr.repository_key AND btr.is_current = TRUE
    JOIN dim_team t ON btr.team_key = t.team_key AND t.is_current = TRUE
    JOIN dim_date d ON pr.created_date_key = d.date_key
    GROUP BY t.team_name, d.year, d.month
)
SELECT 
    team_name,
    year,
    month,
    current_month_prs,
    LAG(current_month_prs, 1) OVER (PARTITION BY team_name ORDER BY year, month) AS prev_month_prs,
    ROUND(((current_month_prs * 1.0 / NULLIF(LAG(current_month_prs, 1) OVER (PARTITION BY team_name ORDER BY year, month), 0)) - 1) * 100, 2) AS mom_growth_pct
FROM monthly_volume;

-- 4. Median PR Cycle by Team (Window Function: PERCENTILE_CONT)
SELECT DISTINCT
    t.team_name,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pr.cycle_time_hours) AS median_cycle_time_hours
FROM fact_pull_request pr
JOIN bridge_team_repository btr ON pr.repository_key = btr.repository_key AND btr.is_current = TRUE
JOIN dim_team t ON btr.team_key = t.team_key AND t.is_current = TRUE
WHERE pr.is_merged = TRUE
GROUP BY t.team_name;

-- ------------------------------------------------------------------------------
-- REPOSITORY HEALTH METRICS
-- ------------------------------------------------------------------------------

-- 5. Top Repositories by PR Volume
SELECT 
    r.repository_name,
    COUNT(pr.pr_key) AS total_prs,
    ROUND(AVG(pr.cycle_time_hours), 2) AS avg_cycle_time
FROM fact_pull_request pr
JOIN dim_repository r ON pr.repository_key = r.repository_key
GROUP BY r.repository_name
ORDER BY total_prs DESC
LIMIT 10;

-- 6. Open Issue Backlog Age (CTEs & Date Math)
SELECT 
    r.repository_name,
    COUNT(i.issue_key) AS open_issues,
    ROUND(AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - i.created_at))/3600/24), 1) AS avg_age_days,
    MAX(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - i.created_at))/3600/24) AS max_age_days
FROM fact_issue i
JOIN dim_repository r ON i.repository_key = r.repository_key
WHERE i.state = 'open'
GROUP BY r.repository_name
ORDER BY avg_age_days DESC;

-- 7. First-Review Latency (Subqueries & Window Functions)
WITH first_reviews AS (
    SELECT 
        pr_key,
        MIN(review_delay_hours) AS time_to_first_review
    FROM fact_review
    GROUP BY pr_key
)
SELECT 
    r.repository_name,
    ROUND(AVG(fr.time_to_first_review), 2) AS avg_time_to_first_review_hours
FROM first_reviews fr
JOIN fact_pull_request pr ON fr.pr_key = pr.pr_key
JOIN dim_repository r ON pr.repository_key = r.repository_key
GROUP BY r.repository_name
ORDER BY avg_time_to_first_review_hours ASC;

-- 8. Contributor Count by Repository (COUNT DISTINCT)
SELECT 
    r.repository_name,
    COUNT(DISTINCT pr.developer_key) AS unique_pr_authors,
    COUNT(DISTINCT c.developer_key) AS unique_committers
FROM dim_repository r
LEFT JOIN fact_pull_request pr ON r.repository_key = pr.repository_key
LEFT JOIN fact_commit c ON r.repository_key = c.repository_key
GROUP BY r.repository_name
ORDER BY unique_committers DESC;

-- 9. Oldest Open Issues
SELECT 
    r.repository_name,
    i.issue_id,
    i.created_at,
    ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - i.created_at))/3600/24, 0) AS age_in_days
FROM fact_issue i
JOIN dim_repository r ON i.repository_key = r.repository_key
WHERE i.state = 'open'
ORDER BY age_in_days DESC
LIMIT 10;

-- ------------------------------------------------------------------------------
-- CI/CD & WORKFLOW METRICS
-- ------------------------------------------------------------------------------

-- 10. CI Success by Repository
SELECT 
    r.repository_name,
    COUNT(w.workflow_run_key) AS total_runs,
    SUM(CASE WHEN w.conclusion = 'success' THEN 1 ELSE 0 END) AS success_runs,
    ROUND((SUM(CASE WHEN w.conclusion = 'success' THEN 1 ELSE 0 END) * 100.0) / NULLIF(COUNT(w.workflow_run_key), 0), 2) AS success_rate_pct
FROM fact_workflow w
JOIN dim_repository r ON w.repository_key = r.repository_key
GROUP BY r.repository_name
ORDER BY success_rate_pct ASC;

-- 11. CI Trend by Month
SELECT 
    d.year,
    d.month,
    COUNT(w.workflow_run_key) AS total_runs,
    ROUND((SUM(CASE WHEN w.conclusion = 'success' THEN 1 ELSE 0 END) * 100.0) / NULLIF(COUNT(w.workflow_run_key), 0), 2) AS success_rate_pct
FROM fact_workflow w
JOIN dim_date d ON w.date_key = d.date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- 12. Workflow Duration Trends
SELECT 
    r.repository_name,
    wf.workflow_name,
    ROUND(AVG(w.duration_seconds), 2) AS avg_duration_seconds,
    MAX(w.duration_seconds) AS max_duration_seconds
FROM fact_workflow w
JOIN dim_repository r ON w.repository_key = r.repository_key
JOIN dim_workflow wf ON w.workflow_key = wf.workflow_key
WHERE w.conclusion = 'success'
GROUP BY r.repository_name, wf.workflow_name
ORDER BY avg_duration_seconds DESC;

-- ------------------------------------------------------------------------------
-- COLLABORATION & CROSS-TEAM METRICS
-- ------------------------------------------------------------------------------

-- 13. Shared Repositories (Repositories owned by >1 team)
SELECT 
    r.repository_name,
    COUNT(btr.team_key) AS assigned_teams,
    STRING_AGG(t.team_name, ', ') AS team_list
FROM bridge_team_repository btr
JOIN dim_repository r ON btr.repository_key = r.repository_key AND btr.is_current = TRUE
JOIN dim_team t ON btr.team_key = t.team_key AND t.is_current = TRUE
GROUP BY r.repository_name
HAVING COUNT(btr.team_key) > 1;

-- 14. Cross-Team Reviews (Developer from Team A reviewing PR from Team B)
-- Simplified representation: Assuming we associate a developer with the team of the repo they contribute to most
WITH dev_primary_team AS (
    SELECT 
        pr.developer_key,
        btr.team_key,
        ROW_NUMBER() OVER (PARTITION BY pr.developer_key ORDER BY COUNT(*) DESC) AS rn
    FROM fact_pull_request pr
    JOIN bridge_team_repository btr ON pr.repository_key = btr.repository_key
    GROUP BY pr.developer_key, btr.team_key
)
SELECT 
    t_pr.team_name AS pr_team,
    t_rev.team_name AS reviewer_team,
    COUNT(r.review_key) AS cross_reviews
FROM fact_review r
JOIN fact_pull_request pr ON r.pr_key = pr.pr_key
JOIN dev_primary_team dpt_pr ON pr.developer_key = dpt_pr.developer_key AND dpt_pr.rn = 1
JOIN dev_primary_team dpt_rev ON r.reviewer_key = dpt_rev.developer_key AND dpt_rev.rn = 1
JOIN dim_team t_pr ON dpt_pr.team_key = t_pr.team_key
JOIN dim_team t_rev ON dpt_rev.team_key = t_rev.team_key
WHERE t_pr.team_key != t_rev.team_key
GROUP BY t_pr.team_name, t_rev.team_name
ORDER BY cross_reviews DESC;

-- ------------------------------------------------------------------------------
-- BOTTLENECK ANALYSIS
-- ------------------------------------------------------------------------------

-- 15. Rolling 7-Day PR Average (Window Function: ROWS BETWEEN)
WITH daily_prs AS (
    SELECT 
        r.repository_name,
        d.date,
        COUNT(pr.pr_key) AS pr_count
    FROM fact_pull_request pr
    JOIN dim_repository r ON pr.repository_key = r.repository_key
    JOIN dim_date d ON pr.created_date_key = d.date_key
    GROUP BY r.repository_name, d.date
)
SELECT 
    repository_name,
    date,
    pr_count,
    ROUND(AVG(pr_count) OVER (
        PARTITION BY repository_name 
        ORDER BY date 
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS rolling_7d_avg
FROM daily_prs
ORDER BY repository_name, date;

-- 16. Potential Delivery Bottleneck Flag
WITH repo_stats AS (
    SELECT 
        r.repository_name,
        ROUND(AVG(pr.cycle_time_hours), 2) AS avg_cycle,
        ROUND(AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - i.created_at))/3600/24), 2) AS avg_issue_age_days
    FROM dim_repository r
    LEFT JOIN fact_pull_request pr ON r.repository_key = pr.repository_key
    LEFT JOIN fact_issue i ON r.repository_key = i.repository_key AND i.state = 'open'
    GROUP BY r.repository_name
)
SELECT 
    repository_name,
    avg_cycle,
    avg_issue_age_days,
    CASE 
        WHEN avg_cycle > 72 AND avg_issue_age_days > 30 THEN 'High Bottleneck Risk'
        WHEN avg_cycle > 48 OR avg_issue_age_days > 14 THEN 'Medium Risk'
        ELSE 'Healthy'
    END AS bottleneck_flag
FROM repo_stats
ORDER BY avg_cycle DESC;

-- ------------------------------------------------------------------------------
-- HISTORICAL (SCD TYPE 2) QUERIES
-- ------------------------------------------------------------------------------

-- 17. View Historical Ownership of a Repository
SELECT 
    r.repository_name,
    t.team_name,
    btr.role,
    btr.valid_from,
    btr.valid_to,
    btr.is_current
FROM bridge_team_repository btr
JOIN dim_repository r ON btr.repository_key = r.repository_key
JOIN dim_team t ON btr.team_key = t.team_key
WHERE r.repository_name = 'flask' -- seeded ownership change (config.yaml scd2_demo)
ORDER BY btr.valid_from DESC;

-- 18. Issue Resolution by Repository
SELECT 
    r.repository_name,
    COUNT(i.issue_key) AS resolved_issues,
    ROUND(AVG(i.resolution_hours), 2) AS avg_resolution_hours
FROM fact_issue i
JOIN dim_repository r ON i.repository_key = r.repository_key
WHERE i.state = 'closed'
GROUP BY r.repository_name
ORDER BY avg_resolution_hours ASC;

-- 19. Commit Frequency by Developer
SELECT 
    d.username,
    COUNT(c.commit_key) AS total_commits,
    COUNT(DISTINCT c.repository_key) AS repos_contributed_to
FROM fact_commit c
JOIN dim_developer d ON c.developer_key = d.developer_key
GROUP BY d.username
ORDER BY total_commits DESC
LIMIT 20;

-- 20. PR Merge Rate by Developer
SELECT 
    d.username,
    COUNT(pr.pr_key) AS total_prs,
    SUM(CASE WHEN pr.is_merged = TRUE THEN 1 ELSE 0 END) AS merged_prs,
    ROUND((SUM(CASE WHEN pr.is_merged = TRUE THEN 1 ELSE 0 END) * 100.0) / NULLIF(COUNT(pr.pr_key), 0), 2) AS merge_rate_pct
FROM fact_pull_request pr
JOIN dim_developer d ON pr.developer_key = d.developer_key
GROUP BY d.username
HAVING COUNT(pr.pr_key) > 5
ORDER BY merge_rate_pct DESC, total_prs DESC
LIMIT 20;
