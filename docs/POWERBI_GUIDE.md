# EngineeringPulse: Power BI Implementation Guide

Build the 5 dashboard pages on top of the PostgreSQL warehouse. Do the parts in order: connect, fix the model, add measures, then build pages.
The DAX here was written against the schema in `sql/schema.sql`; check every number against the "Expected values" table in Part 5.

---

## Part 1: Connect

1. Power BI Desktop: **Home > Get data > PostgreSQL database**.
2. Server `localhost`, Database `engineeringpulse`, mode **Import**. Leave Advanced options empty.
3. Credentials, **Database** tab: user `postgres`, the password from your `.env`. If asked about encryption, click **OK**.
   If it complains about a missing driver, install the Npgsql `.msi` (v4.x, tick "GAC Installation") and restart Power BI.
4. In the Navigator, expand the **engineeringpulse** schema, tick all 11 tables (5 `dim_*`, `bridge_team_repository`, 5 `fact_*`) and click **Load**.

After a new pipeline run, click **Home > Refresh**.

---

## Part 2: Fix the model (Model view, the diagram icon on the left)

Delete any relationship Power BI auto-created that is not in this list, then create the missing ones by dragging the column from the dimension onto the fact column.

| From (one side) | To (many side) | Notes |
|---|---|---|
| `dim_date[date_key]` | `fact_pull_request[created_date_key]` | |
| `dim_date[date_key]` | `fact_review[review_date_key]` | |
| `dim_date[date_key]` | `fact_issue[date_key]` | |
| `dim_date[date_key]` | `fact_commit[date_key]` | |
| `dim_date[date_key]` | `fact_workflow[date_key]` | |
| `dim_repository[repository_key]` | `fact_pull_request`, `fact_review`, `fact_issue`, `fact_commit`, `fact_workflow` (`repository_key` in each) | five relationships |
| `dim_developer[developer_key]` | `fact_pull_request[developer_key]`, `fact_issue[developer_key]`, `fact_commit[developer_key]`, `fact_review[reviewer_key]` | |
| `dim_workflow[workflow_key]` | `fact_workflow[workflow_key]` | |
| `dim_team[team_key]` | `bridge_team_repository[team_key]` | |
| `dim_repository[repository_key]` | `bridge_team_repository[repository_key]` | set **Cross filter direction = Both** (double-click the line) |

Rules that prevent wrong numbers:

- **Do not** connect `fact_pull_request[pr_key]` to `fact_review[pr_key]`. `fact_review` already reaches the repository directly, and a second path makes Power BI mark relationships inactive. Review metrics by team and repository work through the repository.
- The *Both* direction on the bridge is what lets a team slicer filter down to repositories and then to the facts: team, then bridge, then repository, then facts.
- Every relationship should be **one-to-many** with the single arrow pointing at the fact, except the bridge one above.

Then set these:

- Select `dim_date` and choose **Table tools > Mark as date table**, with `date` as the date column.
- Select `dim_date[month_name]` and choose **Column tools > Sort by column > month**, so months sort Mar to Aug and not alphabetically.
- Hide the surrogate key columns from Report view (right-click > Hide) so they do not clutter the field list.

---

## Part 3: Measures

Select `fact_pull_request` in the Fields pane, click **New measure** and paste one at a time. (A measure can live on any table.)

```dax
Total PRs = COUNTROWS(fact_pull_request)

Merged PRs = CALCULATE(COUNTROWS(fact_pull_request), fact_pull_request[is_merged] = TRUE())

PR Merge Rate = DIVIDE([Merged PRs], [Total PRs])

Avg PR Cycle (h) = AVERAGE(fact_pull_request[cycle_time_hours])

Median PR Cycle (h) = MEDIAN(fact_pull_request[cycle_time_hours])

Avg Review Delay (h) = AVERAGE(fact_review[review_delay_hours])

Reviews = COUNTROWS(fact_review)

Avg Issue Resolution (h) = AVERAGE(fact_issue[resolution_hours])

Open Issues = CALCULATE(COUNTROWS(fact_issue), fact_issue[state] = "open")

Commits = COUNTROWS(fact_commit)

Active Developers = DISTINCTCOUNT(fact_pull_request[developer_key])

Total Repositories = COUNTROWS(dim_repository)

Total Teams = COUNTROWS(dim_team)

CI Runs = COUNTROWS(fact_workflow)

CI Completed = CALCULATE(COUNTROWS(fact_workflow), fact_workflow[status] = "completed")

CI Success Rate = DIVIDE(CALCULATE(COUNTROWS(fact_workflow), fact_workflow[conclusion] = "success"), [CI Completed])

CI Failure Rate = DIVIDE(CALCULATE(COUNTROWS(fact_workflow), fact_workflow[conclusion] = "failure"), [CI Completed])

Teams per Repo =
CALCULATE(DISTINCTCOUNT(bridge_team_repository[team_key]), bridge_team_repository[is_current] = TRUE())
```

For Dashboard 5 (compares each repository to the organisation average):

```dax
Org Avg PR Cycle (h) =
CALCULATE([Avg PR Cycle (h)], ALL(dim_repository), ALL(dim_team), ALL(bridge_team_repository))

Org CI Failure Rate =
CALCULATE([CI Failure Rate], ALL(dim_repository), ALL(dim_team), ALL(bridge_team_repository))

Cycle vs Org = DIVIDE([Avg PR Cycle (h)], [Org Avg PR Cycle (h)])

Bottleneck Flag =
IF(
    [Cycle vs Org] > 1.5 && [CI Failure Rate] > [Org CI Failure Rate],
    "Potential bottleneck",
    "OK"
)
```

Say "potential bottleneck", never "bad team".

---

## Part 4: Pages

Use **Insert > New page** four times (5 pages), and rename each tab by double-clicking it.

### Report-level filter (once, before building pages)

Open the **Filters** pane, drag `dim_date[date]` to **Filters on all pages**, choose *Advanced filtering*: is on or after `2026-03-01` and is before or on `2026-08-31`. The date table also holds a few days outside the window.

### Page-level filter for ownership pages (Pages 1, 2, 3 and 5)

On each of those pages drag `bridge_team_repository[role]` to *Filters on this page* and tick **Primary**; drag `bridge_team_repository[is_current]` and tick **True**. This stops a repository counting once per team it contributes to. **Do not** add these on Page 4.

### Page 1: Executive Overview
- Cards (Visualizations > Card): `Total Teams`, `Total Repositories`, `Active Developers`, `Total PRs`, `PR Merge Rate` (format %), `Avg PR Cycle (h)`, `Open Issues`, `CI Success Rate` (format %).
- Line chart, PR trend: X `dim_date[date]` (set to Month), Y `Total PRs`.
- Line chart, CI trend: X `dim_date[date]` (Month), Y `CI Success Rate`.
- Line chart, issue trend: X `dim_date[date]` (Month), Y `Open Issues`.

### Page 2: Team Performance
- Slicers: `dim_date[month_name]`, `dim_team[team_name]`, `dim_repository[language]`.
- Matrix: Rows `dim_team[team_name]`; Values `Total PRs`, `Avg PR Cycle (h)`, `Median PR Cycle (h)`, `Avg Review Delay (h)`, `Avg Issue Resolution (h)`, `CI Success Rate`.
- Clustered bar: Y `dim_team[team_name]`, X `Total PRs`.
- Clustered bar: Y `dim_team[team_name]`, X `Avg Review Delay (h)`.
- Do not build a single "best team" score; show the dimensions side by side.

### Page 3: Repository Health
- Slicer: `dim_repository[repository_name]`.
- Cards: `Open Issues`, `Total PRs`, `Avg PR Cycle (h)`, `Avg Review Delay (h)`.
- Line chart: X `dim_date[date]` (Month), Y `Commits`.
- Donut: Legend `fact_workflow[conclusion]`, Values `CI Runs`.
- Table: `dim_team[team_name]`, `dim_repository[repository_name]`, `Total PRs`, `Avg PR Cycle (h)`, `CI Success Rate`.

### Page 4: Collaboration (no bridge filters on this page)
- Matrix: Rows `dim_repository[repository_name]`, Columns `dim_team[team_name]`, Values `Total PRs`. A repository with values under two teams is shared.
- Card: count of repositories with `Teams per Repo` > 1 (add `Teams per Repo` to a table with `repository_name`, then sort descending).
- Table: `dim_team[team_name]`, `bridge_team_repository[role]`, `dim_repository[repository_name]`, `bridge_team_repository[valid_from]`, `bridge_team_repository[valid_to]`, `bridge_team_repository[is_current]`, filtered to `pallets/flask`. This shows the SCD Type 2 ownership change.
- Cross-team reviews are easier in SQL: query 14 in `sql/analytics.sql`. Optional: **Get data > PostgreSQL database > Advanced options > SQL statement**, paste the query with `engineeringpulse.` in front of each table name, and show it as a table.

### Page 5: Engineering Bottlenecks
- Table: `dim_repository[repository_name]`, `Avg PR Cycle (h)`, `Org Avg PR Cycle (h)`, `Cycle vs Org`, `Avg Review Delay (h)`, `CI Failure Rate`, `Bottleneck Flag`.
- Colour the flag: in the table's **Format > Cell elements**, choose the `Bottleneck Flag` column, turn on **Background color**, *Format style = Rules*: if value is `Potential bottleneck` then red, if `OK` then green.
- Bar chart: Y `dim_repository[repository_name]`, X `Cycle vs Org`, sorted descending.

---

## Part 5: Expected values (check these before trusting any dashboard)

With the report-level date filter applied and no slicers:

| Measure | Expected |
|---|---|
| Total PRs | 3,542 |
| Merged PRs | 1,774 (`PR Merge Rate` about 50.1%) |
| Total Repositories / Total Teams | 20 / 8 |
| Reviews | 4,148 (a few submitted after 2026-08-31 drop out of monthly charts) |
| Commits | 2,782 |
| CI Runs | 15,760 (`CI Success Rate` about 74.5%) |
| Open Issues | 295 (as of the extraction date, 2026-09-26) |

If `Total PRs` is above 3,542 with no team selected, a relationship or filter is wrong (most often the bridge page filter is missing, or `fact_pull_request` got a second path to `dim_repository`).

---

## Part 6: Finish

- Give every visual a title; add **Format > Tooltips** for exact numbers.
- Pick one theme (**View > Themes**).
- **File > Save as** `powerbi/EngineeringPulse.pbix`.
- Take a screenshot of each page for the README.
- Aggregate by team and repository. Do not publish views that rank named individuals.
