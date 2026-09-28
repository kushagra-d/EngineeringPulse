"""
Gold Layer Builder (PySpark)
============================
Turns the cleaned CSVs into tables whose columns match sql/schema.sql exactly:
surrogate keys, dimensions, the SCD2 team<->repo bridge, and the facts with
derived metrics. Output: data/gold/<table>.csv (one file per warehouse table).

Runs locally (pip install pyspark + Java 17) or on Databricks (same code, pass the
existing `spark`). ponytail: results are written via toPandas() because Spark's own
CSV writer needs winutils on Windows; Gold tables are small, so use df.write on a cluster.
"""

import os
import sys
from datetime import date, datetime, timedelta

import yaml
from pyspark.sql import SparkSession, Window, functions as F
from utils.logger import get_logger

logger = get_logger("processing.build_gold")

TABLES = ["dim_date", "dim_team", "dim_repository", "dim_developer", "dim_workflow", "bridge_team_repository",
          "fact_pull_request", "fact_review", "fact_issue", "fact_commit", "fact_workflow"]


def get_spark():
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    return (SparkSession.builder.appName("EngineeringPulse")
            .config("spark.sql.session.timeZone", "UTC")  # all timestamps are UTC
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.ui.enabled", "false").getOrCreate())


def _num(col, to):
    """CSV numbers may look like '41898282.0' (pandas floats); go via decimal so the cast is exact."""
    return F.col(col).cast("decimal(20,0)").cast(to).alias(col)


def _hours(end, start):
    return F.round((F.unix_timestamp(end) - F.unix_timestamp(start)) / 3600, 2)


def _date_key(ts):
    return F.date_format(ts, "yyyyMMdd").cast("int")


def _keyed(df, name, *order):
    """Prepend a 1..N surrogate key, deterministic via `order`."""
    return df.select(F.row_number().over(Window.orderBy(*order)).alias(name), *df.columns)


def build_gold(spark, clean_dir, gold_dir, config, repos_map_path="config/repositories.csv"):
    start = config["date_range"]["start"]
    end_excl = (datetime.strptime(config["date_range"]["end"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    demo = config.get("scd2_demo")
    ts = F.to_timestamp
    in_window = lambda c: (c >= F.lit(start).cast("timestamp")) & (c < F.lit(end_excl).cast("timestamp"))
    rd = lambda n: spark.read.csv(os.path.join(clean_dir, f"{n}_clean.csv"), header=True)  # all strings; cast explicitly

    # ---- typed inputs; only activity created inside the analysis window ----
    repos = rd("repositories").select(
        _num("repository_id", "long"), "repository_name", "full_name", "language",
        ts("created_at").alias("created_at"), F.col("archived").cast("boolean"), _num("stars", "int"))
    prs = rd("pull_requests").select(
        _num("pr_id", "long"), _num("pr_number", "long"), "repo_full_name", "author",
        _num("author_id", "long"), ts("created_at").alias("created_at"), ts("updated_at").alias("updated_at"),
        ts("closed_at").alias("closed_at"), ts("merged_at").alias("merged_at"), F.lower("state").alias("state"),
        _num("additions", "int"), _num("deletions", "int"), _num("changed_files", "int")
    ).filter(in_window(F.col("created_at")))
    reviews = rd("reviews").select(
        _num("review_id", "long"), _num("pr_number", "long"), "repo_full_name", "reviewer",
        _num("reviewer_id", "long"), "state", ts("submitted_at").alias("submitted_at")
    ).filter(F.col("submitted_at").isNotNull())  # PENDING reviews have no timestamp
    issues = rd("issues").select(
        _num("issue_id", "long"), "repo_full_name", "author", _num("author_id", "long"),
        ts("created_at").alias("created_at"), ts("updated_at").alias("updated_at"), ts("closed_at").alias("closed_at"), "state"
    ).filter(in_window(F.col("created_at")))
    commits = rd("commits").select(
        "commit_sha", "repo_full_name", "author", _num("author_id", "long"), ts("timestamp").alias("timestamp")
    ).filter(in_window(F.col("timestamp")))
    wf = rd("workflows").select(
        _num("workflow_run_id", "long"), _num("repository_id", "long"), _num("workflow_id", "long"), "workflow_name", "event", "status",
        "conclusion", ts("created_at").alias("created_at"), ts("updated_at").alias("updated_at"),
        ts("run_started_at").alias("started_at")
    ).filter(in_window(F.col("created_at")))

    # ---- dim_repository / dim_team (SCD2 columns start "current") ----
    scd2 = lambda df: (df.withColumn("valid_from", F.lit(start).cast("date"))
                         .withColumn("valid_to", F.lit(None).cast("date")).withColumn("is_current", F.lit(True)))
    dim_repository = scd2(_keyed(repos, "repository_key", "repository_id"))
    dim_team = scd2(spark.createDataFrame([(i + 1, t) for i, t in enumerate(config["company"]["teams"])],
                                          "team_key int, team_name string"))
    repo_key = {r.full_name: r.repository_key for r in dim_repository.select("full_name", "repository_key").collect()}
    team_key = {r.team_name: r.team_key for r in dim_team.select("team_name", "team_key").collect()}
    repo_keys = dim_repository.select("repository_key", F.col("full_name").alias("repo_full_name"))

    # ---- bridge_team_repository: primary + contributor, plus one seeded ownership change ----
    # (config-sized data, so plain Python is fine here)
    rows, start_d = [], date.fromisoformat(start)
    for m in spark.read.csv(repos_map_path, header=True).collect():
        full = f"{m.owner}/{m.repository}"
        if full not in repo_key:
            continue  # repo not extracted yet
        rk, primary = repo_key[full], m.team
        if demo and demo["repository"] == full:
            change = date.fromisoformat(demo["change_date"])
            rows.append((team_key[demo["from_team"]], rk, "Primary", start_d, change - timedelta(days=1), False))
            primary = demo["to_team"]
            rows.append((team_key[primary], rk, "Primary", change, None, True))
        else:
            rows.append((team_key[primary], rk, "Primary", start_d, None, True))
        if m.secondary_team and m.secondary_team != primary:
            rows.append((team_key[m.secondary_team], rk, "Contributor", start_d, None, True))
    bridge = spark.createDataFrame(rows, "team_key int, repository_key int, role string, valid_from date, "
                                         "valid_to date, is_current boolean")

    # ---- dim_developer (usernames lower-cased so the same person matches across sources) ----
    uname = lambda c: F.lower(F.coalesce(c, F.lit("unknown")))
    people = (prs.select(uname(F.col("author")).alias("username"), F.col("author_id").alias("developer_id"))
              .unionByName(reviews.select(uname(F.col("reviewer")).alias("username"), F.col("reviewer_id").alias("developer_id")))
              .unionByName(issues.select(uname(F.col("author")).alias("username"), F.col("author_id").alias("developer_id")))
              .unionByName(commits.select(uname(F.col("author")).alias("username"), F.col("author_id").alias("developer_id")))
              .groupBy("username").agg(F.first("developer_id", ignorenulls=True).alias("developer_id")))
    dim_developer = _keyed(people.select("developer_id", "username"), "developer_key", "username") \
        .withColumn("developer_type", F.when(F.col("username").endswith("[bot]"), "Bot").otherwise("User"))
    dev_keys = F.broadcast(dim_developer.select("username", "developer_key"))

    def with_dev(df, col, out):
        return (df.withColumn("username", uname(F.col(col))).join(dev_keys, "username", "left")
                  .withColumnRenamed("developer_key", out).drop("username"))

    # ---- dim_workflow: one row per workflow_id. GitHub reports some runs' "name" as the run title
    # (PR title etc.), so use each workflow's most common name, capped to the column width. ----
    top_name = Window.partitionBy("workflow_id").orderBy(F.desc("n"), "workflow_name")
    wf_dim = _keyed(
        wf.where(F.col("workflow_id").isNotNull()).groupBy("workflow_id", F.coalesce("workflow_name", F.lit("unknown")).alias("workflow_name"))
          .agg(F.count("*").alias("n")).withColumn("r", F.row_number().over(top_name)).where("r = 1")
          .select("workflow_id", F.substring("workflow_name", 1, 255).alias("workflow_name")),
        "workflow_key", "workflow_id")
    dim_workflow = wf_dim.select("workflow_key", "workflow_name")

    # ---- facts ----
    p = with_dev(prs.join(repo_keys, "repo_full_name"), "author", "developer_key")
    p = p.withColumn("created_date_key", _date_key(F.col("created_at"))) \
         .withColumn("is_merged", F.col("merged_at").isNotNull()) \
         .withColumn("cycle_time_hours", _hours(F.col("merged_at"), F.col("created_at")))
    p = _keyed(p, "pr_key", "created_at", "pr_id")
    fact_pull_request = p.select("pr_key", "pr_id", "repository_key", "developer_key", "created_date_key", "created_at",
                                 "updated_at", "closed_at", "merged_at", "state", "is_merged", "additions",
                                 "deletions", "changed_files", "cycle_time_hours")

    pr_lookup = p.select("repo_full_name", "pr_number", "pr_key", F.col("created_at").alias("pr_created_at"))
    r = reviews.join(pr_lookup, ["repo_full_name", "pr_number"]).join(repo_keys, "repo_full_name")  # only reviews of in-scope PRs
    r = with_dev(r, "reviewer", "reviewer_key")
    r = r.withColumn("review_date_key", _date_key(F.col("submitted_at"))) \
         .withColumn("review_delay_hours", _hours(F.col("submitted_at"), F.col("pr_created_at")))
    fact_review = _keyed(r, "review_key", "review_id").select(
        "review_key", "review_id", "pr_key", "repository_key", "reviewer_key", "review_date_key", "state",
        "submitted_at", "review_delay_hours")

    i = with_dev(issues.join(repo_keys, "repo_full_name"), "author", "developer_key")
    i = i.withColumn("date_key", _date_key(F.col("created_at"))) \
         .withColumn("resolution_hours", _hours(F.col("closed_at"), F.col("created_at")))
    fact_issue = _keyed(i, "issue_key", "issue_id").select(
        "issue_key", "issue_id", "repository_key", "developer_key", "date_key", "created_at", "updated_at",
        "closed_at", "state", "resolution_hours")

    c = with_dev(commits.join(repo_keys, "repo_full_name"), "author", "developer_key")
    c = c.withColumn("date_key", _date_key(F.col("timestamp")))
    fact_commit = _keyed(c, "commit_key", "timestamp", "commit_sha").select(
        "commit_key", "commit_sha", "repository_key", "developer_key", "date_key", "timestamp")

    w = wf.join(dim_repository.select("repository_id", "repository_key"), "repository_id", "left") \
          .join(wf_dim.select("workflow_id", "workflow_key"), "workflow_id", "left") \
          .withColumn("date_key", _date_key(F.col("created_at"))) \
          .withColumn("duration_seconds", F.unix_timestamp("updated_at") - F.unix_timestamp("started_at"))  # ponytail: proxy, the runs endpoint has no completed_at
    fact_workflow = _keyed(w, "workflow_run_key", "created_at", "workflow_run_id").select(
        "workflow_run_key", "workflow_run_id", "repository_key", "workflow_key", "date_key", "event", "status",
        "conclusion", "created_at", "started_at", "updated_at", "duration_seconds")

    # ---- dim_date: must cover every date any fact points at ----
    fact_ts = (prs.select(F.col("created_at").alias("t")).unionByName(reviews.select(F.col("submitted_at").alias("t")))
               .unionByName(issues.select(F.col("created_at").alias("t"))).unionByName(commits.select(F.col("timestamp").alias("t")))
               .unionByName(wf.select(F.col("created_at").alias("t"))))
    lo, hi = fact_ts.agg(F.min(F.to_date("t")), F.max(F.to_date("t"))).first()  # dates in Spark (UTC), not collected timestamps
    d_end = date.fromisoformat(end_excl) - timedelta(days=1)
    d0 = min(start_d, lo) if lo else start_d
    d1 = max(d_end, hi) if hi else d_end
    dim_date = (spark.createDataFrame([(d0, d1)], "a date, b date")
                .select(F.explode(F.sequence("a", "b")).alias("date"))
                .select(F.date_format("date", "yyyyMMdd").cast("int").alias("date_key"), "date",
                        F.year("date").alias("year"), F.quarter("date").alias("quarter"), F.month("date").alias("month"),
                        F.date_format("date", "MMMM").alias("month_name"), F.weekofyear("date").alias("week"),
                        F.dayofmonth("date").alias("day"), F.date_format("date", "EEEE").alias("day_name")))

    tables = dict(dim_date=dim_date, dim_team=dim_team, dim_repository=dim_repository, dim_developer=dim_developer,
                  dim_workflow=dim_workflow, bridge_team_repository=bridge, fact_pull_request=fact_pull_request,
                  fact_review=fact_review, fact_issue=fact_issue, fact_commit=fact_commit, fact_workflow=fact_workflow)
    os.makedirs(gold_dir, exist_ok=True)
    out = {}
    for name in TABLES:
        pdf = tables[name].toPandas()
        pdf.to_csv(os.path.join(gold_dir, f"{name}.csv"), index=False)
        logger.info(f"{name}: {len(pdf)} rows")
        out[name] = pdf
    return out


def run_gold():
    with open("config/config.yaml") as f:
        config = yaml.safe_load(f)
    return build_gold(get_spark(), config["paths"]["cleaned_data"], config["paths"]["gold_data"], config)


if __name__ == "__main__":
    run_gold()
