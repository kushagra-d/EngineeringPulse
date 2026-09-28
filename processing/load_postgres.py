"""
PostgreSQL Loader
=================
Creates the schema from sql/schema.sql, then loads data/gold/<table>.csv in
foreign-key order. Any failure raises (nothing is half-loaded silently).
"""

import os
import pandas as pd
import psycopg2
import yaml
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from utils.logger import get_logger

logger = get_logger("processing.load_postgres")

# Parents before children (foreign keys).
LOAD_ORDER = ["dim_date", "dim_team", "dim_repository", "dim_developer", "dim_workflow",
              "bridge_team_repository", "fact_pull_request", "fact_review", "fact_issue",
              "fact_commit", "fact_workflow"]


def get_db_connection():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "engineeringpulse"), user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"))


def load_table(cur, table, csv_path):
    df = pd.read_csv(csv_path)
    df = df.astype(object).where(df.notna(), None)  # NaN -> NULL
    cols = ",".join(df.columns)
    execute_values(cur, f"INSERT INTO engineeringpulse.{table} ({cols}) VALUES %s",
                   list(df.itertuples(index=False, name=None)), page_size=5000)
    logger.info(f"{table}: {len(df)} rows loaded")
    return len(df)


def run_loading(conn=None, gold_dir=None):
    if gold_dir is None:
        with open("config/config.yaml") as f:
            gold_dir = yaml.safe_load(f)["paths"]["gold_data"]
    conn = conn or get_db_connection()
    try:
        with conn, conn.cursor() as cur:  # one transaction: all tables or none
            with open("sql/schema.sql", encoding="utf-8") as f:
                cur.execute(f.read())
            counts = {t: load_table(cur, t, os.path.join(gold_dir, f"{t}.csv")) for t in LOAD_ORDER}
    finally:
        conn.close()
    logger.info("PostgreSQL load complete.")
    return counts


if __name__ == "__main__":
    run_loading()
