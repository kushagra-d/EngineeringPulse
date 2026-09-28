"""
Data Quality Checks
===================
Runs on the Gold CSVs (no database needed). Writes data/quality/data_quality_report.csv
and returns the number of failed checks.
"""

import os
import pandas as pd
import yaml
from utils.logger import get_logger

logger = get_logger("processing.data_quality")


def run_checks(gold_dir):
    t = {n: pd.read_csv(os.path.join(gold_dir, f"{n}.csv")) for n in [
        "dim_date", "dim_team", "dim_repository", "dim_developer", "dim_workflow", "bridge_team_repository",
        "fact_pull_request", "fact_review", "fact_issue", "fact_commit", "fact_workflow"]}
    pr, rv, wf = t["fact_pull_request"], t["fact_review"], t["fact_workflow"]
    pr_created = pr.set_index("pr_key").created_at
    fk = lambda df, col, dim, key: int((~df[col].isin(t[dim][key])).sum())

    # check name -> number of violating rows (0 = pass)
    checks = {
        "duplicate PR ids": int(pr.pr_id.duplicated().sum()),
        "duplicate repository ids": int(t["dim_repository"].repository_id.duplicated().sum()),
        "null repository keys (all facts)": sum(int(t[f].repository_key.isna().sum()) for f in
                                                ["fact_pull_request", "fact_review", "fact_issue", "fact_commit", "fact_workflow"]),
        "merged before created": int((pd.to_datetime(pr.merged_at) < pd.to_datetime(pr.created_at)).sum()),
        "review before PR creation": int((rv.review_delay_hours < 0).sum()),
        "workflow end before start": int((wf.duration_seconds < 0).sum()),
        "orphan FK: PR -> repository": fk(pr, "repository_key", "dim_repository", "repository_key"),
        "orphan FK: PR -> developer": fk(pr, "developer_key", "dim_developer", "developer_key"),
        "orphan FK: PR -> date": fk(pr, "created_date_key", "dim_date", "date_key"),
        "orphan FK: review -> PR": fk(rv, "pr_key", "fact_pull_request", "pr_key"),
        "orphan FK: review -> date": fk(rv, "review_date_key", "dim_date", "date_key"),
        "orphan FK: issue -> repository": fk(t["fact_issue"], "repository_key", "dim_repository", "repository_key"),
        "orphan FK: commit -> developer": fk(t["fact_commit"], "developer_key", "dim_developer", "developer_key"),
        "orphan FK: workflow -> workflow dim": fk(wf, "workflow_key", "dim_workflow", "workflow_key"),
        "orphan FK: bridge -> team": fk(t["bridge_team_repository"], "team_key", "dim_team", "team_key"),
        "orphan FK: bridge -> repository": fk(t["bridge_team_repository"], "repository_key", "dim_repository", "repository_key"),
        "repos with no current primary team": int((~t["dim_repository"].repository_key.isin(
            t["bridge_team_repository"].query("role == 'Primary' and is_current").repository_key)).sum()),
    }
    report = pd.DataFrame({"check": checks.keys(), "violations": checks.values()})
    report["status"] = report.violations.map(lambda v: "PASS" if v == 0 else "FAIL")
    return report


def run_quality():
    with open("config/config.yaml") as f:
        paths = yaml.safe_load(f)["paths"]
    report = run_checks(paths["gold_data"])
    os.makedirs(paths["quality_reports"], exist_ok=True)
    report.to_csv(os.path.join(paths["quality_reports"], "data_quality_report.csv"), index=False)
    for r in report.itertuples():
        (logger.info if r.status == "PASS" else logger.error)(f"{r.status}  {r.check}: {r.violations}")
    return int((report.status == "FAIL").sum())


if __name__ == "__main__":
    raise SystemExit(run_quality())
