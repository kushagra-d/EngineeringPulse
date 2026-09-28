"""Run: venv/Scripts/python -m pytest tests -q   (from the project root)"""
import pandas as pd
import pytest
from processing.build_gold import build_gold, get_spark
from processing.data_quality import run_checks

CFG = {"date_range": {"start": "2026-03-01", "end": "2026-08-31"},
       "company": {"teams": ["Backend", "Platform", "Security"]},
       "scd2_demo": {"repository": "o/r", "from_team": "Backend", "to_team": "Platform", "change_date": "2026-06-01"}}


def make_inputs(tmp_path):
    clean = tmp_path / "clean"; clean.mkdir()
    pd.DataFrame([dict(repository_id=1, repository_name="r", full_name="o/r", owner="o", description="", language="Python",
                       created_at="2020-01-01T00:00:00Z", updated_at="2026-08-01T00:00:00Z", archived=False, stars=5, forks=1)]
                 ).to_csv(clean / "repositories_clean.csv", index=False)
    pr = lambda i, created, merged: dict(pr_id=i, pr_number=i, repository_id=1, repo_full_name="o/r", author="Alice", author_id=10,
                                         created_at=created, updated_at=created, closed_at=merged, merged_at=merged, state="closed",
                                         draft=False, additions=None, deletions=None, changed_files=None)
    pd.DataFrame([pr(1, "2026-04-01T00:00:00Z", "2026-04-02T12:00:00Z"),   # merged after 36h
                  pr(2, "2026-04-05T00:00:00Z", None),                     # not merged
                  pr(3, "2025-12-01T00:00:00Z", None),                     # before window -> dropped
                  pr(4, "2026-09-15T00:00:00Z", None)]                     # after window  -> dropped
                 ).to_csv(clean / "pull_requests_clean.csv", index=False)
    pd.DataFrame([dict(review_id=1, pr_number=1, repo_full_name="o/r", reviewer="alice", reviewer_id=10, state="APPROVED",
                       submitted_at="2026-04-01T06:00:00Z"),                # 6h after PR 1 (also checks case-insensitive dev match)
                  dict(review_id=2, pr_number=3, repo_full_name="o/r", reviewer="bob", reviewer_id=11, state="APPROVED",
                       submitted_at="2026-01-01T00:00:00Z")]                # review of a dropped PR -> dropped
                 ).to_csv(clean / "reviews_clean.csv", index=False)
    pd.DataFrame([dict(issue_id=1, issue_number=1, repo_full_name="o/r", author="carol", author_id=12, created_at="2026-05-01T00:00:00Z",
                       updated_at="2026-05-02T00:00:00Z", closed_at="2026-05-03T00:00:00Z", state="closed")]
                 ).to_csv(clean / "issues_clean.csv", index=False)
    # a missing author_id makes pandas write the others as "41898282.0" (regression: Spark cast crashed on that)
    pd.DataFrame([dict(commit_sha="a" * 40, repo_full_name="o/r", author="dave[bot]", author_id=None,
                       timestamp="2026-05-01T10:00:00Z", message="m"),
                  dict(commit_sha="b" * 40, repo_full_name="o/r", author="erin", author_id=41898282,
                       timestamp="2026-05-02T10:00:00Z", message="m")]).to_csv(clean / "commits_clean.csv", index=False)
    pd.DataFrame([dict(workflow_run_id=1, repository_id=1, workflow_id=7, workflow_name="CI", event="push", status="completed",
                       conclusion="success", created_at="2026-05-01T00:00:00Z", updated_at="2026-05-01T00:10:00Z",
                       run_started_at="2026-05-01T00:00:00Z"),
                  # same workflow, but GitHub reported the run title as its name (regression: 300 chars broke VARCHAR(255))
                  dict(workflow_run_id=2, repository_id=1, workflow_id=7, workflow_name="x" * 300, event="push", status="completed",
                       conclusion="success", created_at="2026-05-02T00:00:00Z", updated_at="2026-05-02T00:10:00Z",
                       run_started_at="2026-05-02T00:00:00Z"),
                  dict(workflow_run_id=3, repository_id=1, workflow_id=7, workflow_name="CI", event="push", status="completed",
                       conclusion="success", created_at="2026-05-03T00:00:00Z", updated_at="2026-05-03T00:10:00Z",
                       run_started_at="2026-05-03T00:00:00Z")]).to_csv(clean / "workflows_clean.csv", index=False)
    (tmp_path / "map.csv").write_text("owner,repository,team,secondary_team,technology\no,r,Backend,Security,Python\n")
    return clean, tmp_path / "gold", tmp_path / "map.csv"


@pytest.fixture(scope="module")
def spark():
    return get_spark()


def test_gold_metrics_window_and_scd2(spark, tmp_path):
    clean, gold, mp = make_inputs(tmp_path)
    t = build_gold(spark, str(clean), str(gold), CFG, str(mp))

    pr = t["fact_pull_request"]
    assert list(pr.pr_id) == [1, 2]                          # window filter
    assert pr.cycle_time_hours.iloc[0] == 36.0               # merge - create
    assert pd.isna(pr.cycle_time_hours.iloc[1]) and not pr.is_merged.iloc[1]

    rv = t["fact_review"]
    assert len(rv) == 1 and rv.review_delay_hours.iloc[0] == 6.0
    assert rv.reviewer_key.iloc[0] == pr.developer_key.iloc[0]   # "alice" == "Alice"

    assert t["fact_issue"].resolution_hours.iloc[0] == 48.0
    assert t["fact_workflow"].duration_seconds.iloc[0] == 600
    assert list(t["dim_workflow"].workflow_name) == ["CI"]   # one row per workflow_id, most common name
    assert t["dim_developer"].set_index("username").developer_id["erin"] == 41898282
    assert t["dim_developer"].set_index("username").developer_type["dave[bot]"] == "Bot"

    b = t["bridge_team_repository"]                          # Backend->Platform on 2026-06-01, Security contributes throughout
    assert len(b) == 3
    old = b[~b.is_current].iloc[0]
    assert str(old.valid_to) == "2026-05-31"
    assert b[b.is_current & (b.role == "Primary")].team_key.iloc[0] == 2   # Platform

    assert (run_checks(str(gold)).status == "PASS").all()    # quality module agrees
