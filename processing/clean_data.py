"""
Data Cleaning Module
====================
Reads raw JSON files, flattens them, normalizes data, and saves as CSV.
Handles the GitHub quirk where issues include pull requests.
"""

import os
import json
import glob
import pandas as pd
from datetime import datetime
import yaml
from utils.logger import get_logger

logger = get_logger("processing.clean_data")

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def repo_name_from_file(path, suffix):
    """'owner_repo_prs.json' -> 'owner/repo'. Looked up in repositories.csv because
    repo names can contain '_' or '-', so a blind replace('_', '/') is wrong."""
    lookup = {f"{o}_{r}": f"{o}/{r}" for o, r in pd.read_csv("config/repositories.csv")[["owner", "repository"]].values}
    return lookup[os.path.basename(path)[: -len(suffix)]]

def get_json_files(directory):
    """Returns a list of all JSON files in a directory."""
    return glob.glob(os.path.join(directory, "*.json"))

def clean_repositories(raw_dir, clean_dir):
    logger.info("Cleaning repositories...")
    files = get_json_files(os.path.join(raw_dir, "repositories"))
    data = []
    
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            repo = json.load(file)
            data.append({
                "repository_id": repo.get("id"),
                "repository_name": repo.get("name"),
                "full_name": repo.get("full_name"),
                "owner": repo.get("owner", {}).get("login"),
                "description": repo.get("description"),
                "language": repo.get("language"),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
                "archived": repo.get("archived", False),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0)
            })
            
    if data:
        df = pd.DataFrame(data)
        # Handle nulls
        df["language"] = df["language"].fillna("Unknown")
        df.to_csv(os.path.join(clean_dir, "repositories_clean.csv"), index=False)
        logger.info(f"Cleaned {len(df)} repositories.")

def clean_pull_requests(raw_dir, clean_dir):
    logger.info("Cleaning pull requests...")
    files = get_json_files(os.path.join(raw_dir, "pull_requests"))
    data = []
    
    for f in files:
        # Extract repo name from filename like 'owner_repo_prs.json'
        # To be safe, we might not have repo_id inside the PR list if it's a list of PRs
        repo_full_name = repo_name_from_file(f, "_prs.json")
        
        with open(f, "r", encoding="utf-8") as file:
            prs = json.load(file)
            for pr in prs:
                # Some endpoints nest the base repo id, some don't. We use the full name as a reliable join key for now, 
                # or extract repo ID if available
                repo_id = pr.get("base", {}).get("repo", {}).get("id")
                
                data.append({
                    "pr_id": pr.get("id"),
                    "pr_number": pr.get("number"),
                    "repository_id": repo_id,
                    "repo_full_name": repo_full_name, # fallback
                    "author": pr.get("user", {}).get("login"),
                    "author_id": pr.get("user", {}).get("id"),
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                    "closed_at": pr.get("closed_at"),
                    "merged_at": pr.get("merged_at"),
                    "state": pr.get("state"),
                    "draft": pr.get("draft", False),
                    # The standard PR list endpoint might not include lines added/deleted.
                    # GitHub API usually only includes these when fetching a specific PR.
                    # We will safe_get them, defaulting to 0 or None if missing.
                    "additions": pr.get("additions"),
                    "deletions": pr.get("deletions"),
                    "changed_files": pr.get("changed_files")
                })
                
    if data:
        df = pd.DataFrame(data)
        df = df.drop_duplicates(subset=["pr_id"])
        # Normalize states
        df["state"] = df["state"].str.lower()
        df.to_csv(os.path.join(clean_dir, "pull_requests_clean.csv"), index=False)
        logger.info(f"Cleaned {len(df)} pull requests.")

def clean_reviews(raw_dir, clean_dir):
    logger.info("Cleaning PR reviews...")
    files = get_json_files(os.path.join(raw_dir, "reviews"))
    data = []
    
    for f in files:
        repo_full_name = repo_name_from_file(f, "_reviews.json")
        with open(f, "r", encoding="utf-8") as file:
            reviews = json.load(file)
            for r in reviews:
                data.append({
                    "review_id": r.get("id"),
                    "pr_number": r.get("pr_number"),
                    "repo_full_name": repo_full_name,
                    "reviewer": r.get("user", {}).get("login") if r.get("user") else "UNKNOWN",
                    "reviewer_id": r.get("user", {}).get("id") if r.get("user") else None,
                    "state": r.get("state"),
                    "submitted_at": r.get("submitted_at")
                })
                
    if data:
        df = pd.DataFrame(data)
        df = df.drop_duplicates(subset=["review_id"])
        # Standardize state text
        df["state"] = df["state"].str.upper()
        df.to_csv(os.path.join(clean_dir, "reviews_clean.csv"), index=False)
        logger.info(f"Cleaned {len(df)} reviews.")

def clean_issues(raw_dir, clean_dir):
    logger.info("Cleaning issues (filtering out PRs)...")
    files = get_json_files(os.path.join(raw_dir, "issues"))
    data = []
    
    for f in files:
        repo_full_name = repo_name_from_file(f, "_issues.json")
        with open(f, "r", encoding="utf-8") as file:
            issues = json.load(file)
            for issue in issues:
                # CRITICAL: GitHub Issues API returns PRs too. We must filter them.
                if "pull_request" in issue:
                    continue # Skip, it's a PR
                
                # We need repo_id. Since the issue payload might not have the base repo object,
                # we rely on repo_full_name to join later or parse url.
                repo_id_url = issue.get("repository_url", "")
                
                data.append({
                    "issue_id": issue.get("id"),
                    "issue_number": issue.get("number"),
                    "repo_full_name": repo_full_name,
                    "author": issue.get("user", {}).get("login"),
                    "author_id": issue.get("user", {}).get("id"),
                    "created_at": issue.get("created_at"),
                    "updated_at": issue.get("updated_at"),
                    "closed_at": issue.get("closed_at"),
                    "state": issue.get("state")
                })
                
    if data:
        df = pd.DataFrame(data)
        df = df.drop_duplicates(subset=["issue_id"])
        df.to_csv(os.path.join(clean_dir, "issues_clean.csv"), index=False)
        logger.info(f"Cleaned {len(df)} pure issues (PRs filtered out).")
        
def clean_commits(raw_dir, clean_dir):
    logger.info("Cleaning commits...")
    files = get_json_files(os.path.join(raw_dir, "commits"))
    data = []
    
    for f in files:
        repo_full_name = repo_name_from_file(f, "_commits.json")
        with open(f, "r", encoding="utf-8") as file:
            commits = json.load(file)
            for c in commits:
                author_login = c.get("author", {}).get("login") if c.get("author") else "UNKNOWN"
                author_id = c.get("author", {}).get("id") if c.get("author") else None
                
                # Sometimes author block is null but commit.author (git config) exists
                commit_info = c.get("commit", {})
                git_author = commit_info.get("author", {}).get("name", "UNKNOWN")
                date = commit_info.get("author", {}).get("date")
                
                data.append({
                    "commit_sha": c.get("sha"),
                    "repo_full_name": repo_full_name,
                    "author": author_login if author_login != "UNKNOWN" else git_author,
                    "author_id": author_id,
                    "timestamp": date,
                    # Truncate message to avoid huge CSVs
                    "message": commit_info.get("message", "")[:100].replace("\n", " ") 
                })
                
    if data:
        df = pd.DataFrame(data)
        df = df.drop_duplicates(subset=["commit_sha"])
        df.to_csv(os.path.join(clean_dir, "commits_clean.csv"), index=False)
        logger.info(f"Cleaned {len(df)} commits.")

def clean_workflows(raw_dir, clean_dir):
    logger.info("Cleaning workflow runs...")
    files = get_json_files(os.path.join(raw_dir, "workflows"))
    data = []
    
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            runs = json.load(file)
            for r in runs:
                data.append({
                    "workflow_run_id": r.get("id"),
                    "repository_id": r.get("repository", {}).get("id"),
                    "workflow_id": r.get("workflow_id"),
                    "workflow_name": r.get("name"),
                    "event": r.get("event"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                    "run_started_at": r.get("run_started_at")
                })
                
    if data:
        df = pd.DataFrame(data)
        df = df.drop_duplicates(subset=["workflow_run_id"])
        
        # Fill null conclusions (e.g. if still running)
        df["conclusion"] = df["conclusion"].fillna("unknown")
        df.to_csv(os.path.join(clean_dir, "workflows_clean.csv"), index=False)
        logger.info(f"Cleaned {len(df)} workflow runs.")

def run_cleaning():
    """Main cleaning orchestration."""
    config = load_config()
    raw_dir = config["paths"]["raw_data"]
    clean_dir = config["paths"]["cleaned_data"]
    
    logger.info(f"Starting data cleaning from {raw_dir} to {clean_dir}")
    
    os.makedirs(clean_dir, exist_ok=True)
    
    clean_repositories(raw_dir, clean_dir)
    clean_pull_requests(raw_dir, clean_dir)
    clean_reviews(raw_dir, clean_dir)
    clean_issues(raw_dir, clean_dir)
    clean_commits(raw_dir, clean_dir)
    clean_workflows(raw_dir, clean_dir)
    
    logger.info("Data cleaning complete!")

if __name__ == "__main__":
    run_cleaning()
