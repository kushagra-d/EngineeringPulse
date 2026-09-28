# Data Quality Report

Full run over the 20 repositories in `config/repositories.csv`, window 2026-03-01 to 2026-08-31, extracted 2026-09-26.
The programmatic checks live in `processing/data_quality.py` (`python run_pipeline.py quality`) and write `data/quality/data_quality_report.csv`.

## Record counts through the pipeline

| Dataset | Raw files | Cleaned rows | In warehouse | Why rows drop |
|---------|-----------|--------------|--------------|---------------|
| Repositories | 20 | 20 | 20 | none |
| Pull requests | 20 | 5,196 | 3,542 | The PR endpoint returns every PR *updated* since March; only PRs *created* in the window are kept |
| Reviews | 20 | 4,148 | 4,148 | Fetched only for in-window PRs; PENDING reviews (no timestamp) are dropped |
| Issues | 20 | 3,197 | 1,309 | Issues updated since March include older ones; only issues created in the window are kept. PRs are filtered out at the cleaning step |
| Commits | 20 | 2,801 | 2,782 | Author date vs. window edge |
| Workflow runs | 20 | 15,760 | 15,760 | none |

## Automated checks (17, all PASS on this run)

Duplicate PR ids · duplicate repository ids · null repository keys on every fact · merged before created · review before PR creation · workflow end before start · orphan foreign keys (PR to repository/developer/date, review to PR/date, issue to repository, commit to developer, workflow to workflow dimension, bridge to team/repository) · repositories without a current Primary team.

## Issues found in the data and how they were handled

| Finding | Handling |
|---------|----------|
| Issues endpoint returns pull requests as well | Filtered out on the `pull_request` field in `clean_data.py` |
| Pandas wrote IDs as `41898282.0` when a column had blanks; Spark refused to cast them | `_num()` in `build_gold.py` casts through a decimal so the value is exact |
| GitHub reports some runs' `name` as the run title (a PR title, for example), giving 845 "workflow names" for 197 real workflows, some over 255 characters | `dim_workflow` is keyed by `workflow_id`, using each workflow's most common name |
| Repository names contain `_` and `-`, so file names could not be mapped back with a simple replace | The name is looked up in `repositories.csv` |
| Commits without a linked GitHub account (8 people) | Kept with the git author name; `developer_id` is NULL |
| Reviews of PRs from outside the window | Dropped so every review has a PR in `fact_pull_request` |

## Known limitations (documented, not fixed)

- `additions`, `deletions`, `changed_files` on PRs are NULL: the PR list endpoint does not return them, and one extra call per PR was judged too expensive.
- `duration_seconds` on workflow runs is `updated_at - run_started_at`, a proxy; the runs endpoint has no completion time.
- GitHub caps filtered workflow-run queries, so very busy repositories may have partial CI history.
- Issue and PR `state` is the state on the extraction date (2026-09-26), not at the end of the window. For example, the 295 open issues are open today.
- Team ownership is simulated. One ownership change (pallets/flask, Backend to Platform on 2026-06-01) is seeded from `config.yaml` so the SCD Type 2 history has content. Queries attribute PRs to a repository's *current* team.
- Usernames are real public GitHub accounts; dashboards aggregate by team and repository.
