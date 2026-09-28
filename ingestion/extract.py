"""
GitHub Data Extraction Pipeline
===============================
Extracts repositories, PRs, reviews, issues, commits, and workflows.
"""

import os
import json
import argparse
import pandas as pd
from datetime import datetime
from ingestion.github_api import GitHubAPIClient
from utils.logger import get_logger

logger = get_logger("ingestion.extract")

def save_raw_json(data, folder, filename):
    """Save data to the raw directory."""
    filepath = os.path.join(folder, filename)
    os.makedirs(folder, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def extract_repository_metadata(client, repos_df, raw_dir):
    logger.info("Extracting repository metadata...")
    repo_folder = os.path.join(raw_dir, "repositories")
    
    for _, row in repos_df.iterrows():
        owner, repo = row['owner'], row['repository']
        logger.info(f"Fetching metadata for {owner}/{repo}")
        try:
            data = client.get(f"repos/{owner}/{repo}")
            save_raw_json(data, repo_folder, f"{owner}_{repo}_metadata.json")
        except Exception as e:
            logger.error(f"Failed to fetch metadata for {owner}/{repo}: {e}")

def extract_pull_requests_and_reviews(client, repos_df, start_date, end_date, raw_dir, test_mode=False):
    logger.info("Extracting pull requests and reviews...")
    pr_folder = os.path.join(raw_dir, "pull_requests")
    review_folder = os.path.join(raw_dir, "reviews")
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=None)
    
    for _, row in repos_df.iterrows():
        owner, repo = row['owner'], row['repository']
        if os.path.exists(os.path.join(pr_folder, f"{owner}_{repo}_prs.json")):
            logger.info(f"Skipping PRs for {owner}/{repo} (already extracted; delete data/raw to redo)")
            continue
        logger.info(f"Fetching PRs for {owner}/{repo}")
        
        pr_results = []
        page = 1
        url = f"repos/{owner}/{repo}/pulls"
        params = {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100}
        
        while url:
            try:
                # Use get() directly to implement custom break condition
                response = client.session.get(f"{client.base_url}/{url}", params=params if page == 1 else None)
                client._check_rate_limit(response)
                response.raise_for_status()
                
                data = response.json()
                if not data:
                    break
                    
                for pr in data:
                    updated_at = datetime.strptime(pr['updated_at'], "%Y-%m-%dT%H:%M:%SZ")
                    # If the PR was last updated before our start date, we can stop paginating
                    if updated_at < start_dt:
                        url = None # Force break
                        break
                    pr_results.append(pr)
                
                if url is not None:
                    url_match = response.links.get("next", {}).get("url")
                    url = url_match.replace(f"{client.base_url}/", "") if url_match else None
                    page += 1
                
                if test_mode and page > 1:
                    break # Only fetch 1 page in test mode
                    
            except Exception as e:
                logger.error(f"Failed PR pagination for {owner}/{repo}: {e}")
                pr_results = []  # incomplete: save nothing so a rerun retries this repo
                break
                
        if pr_results:
            # Reviews only for PRs created inside the window (the warehouse drops the rest anyway)
            in_scope = [pr for pr in pr_results if start_date <= pr["created_at"][:10] <= end_date]
            logger.info(f"Fetching reviews for {len(in_scope)} of {len(pr_results)} PRs in {owner}/{repo}")
            all_reviews = []
            
            # In test mode, only fetch reviews for first 5 PRs to save time/rate limits
            prs_to_check = in_scope[:5] if test_mode else in_scope
            
            for pr in prs_to_check:
                try:
                    pr_num = pr['number']
                    reviews = client.get_paginated(f"repos/{owner}/{repo}/pulls/{pr_num}/reviews")
                    for rev in reviews:
                        rev['pr_number'] = pr_num # Add PR reference
                    all_reviews.extend(reviews)
                except Exception as e:
                    logger.error(f"Failed to fetch reviews for {owner}/{repo} PR {pr_num}: {e}")
                    
            if all_reviews:
                save_raw_json(all_reviews, review_folder, f"{owner}_{repo}_reviews.json")
            save_raw_json(pr_results, pr_folder, f"{owner}_{repo}_prs.json")  # last: marks the repo as done

def extract_issues(client, repos_df, start_date, raw_dir, test_mode=False):
    logger.info("Extracting issues...")
    issue_folder = os.path.join(raw_dir, "issues")
    start_dt_iso = f"{start_date}T00:00:00Z"
    
    for _, row in repos_df.iterrows():
        owner, repo = row['owner'], row['repository']
        if os.path.exists(os.path.join(issue_folder, f"{owner}_{repo}_issues.json")):
            continue  # already extracted
        logger.info(f"Fetching issues for {owner}/{repo}")
        
        try:
            # The GitHub Issues API accepts 'since' parameter
            # Note: This API returns BOTH issues and pull requests
            if test_mode:
                data = client.get(f"repos/{owner}/{repo}/issues", params={"state": "all", "since": start_dt_iso, "per_page": 100})
            else:
                data = client.get_paginated(f"repos/{owner}/{repo}/issues", params={"state": "all", "since": start_dt_iso})
            
            save_raw_json(data, issue_folder, f"{owner}_{repo}_issues.json")
        except Exception as e:
            logger.error(f"Failed to fetch issues for {owner}/{repo}: {e}")

def extract_commits(client, repos_df, start_date, end_date, raw_dir, test_mode=False):
    logger.info("Extracting commits...")
    commit_folder = os.path.join(raw_dir, "commits")
    start_dt_iso = f"{start_date}T00:00:00Z"
    end_dt_iso = f"{end_date}T23:59:59Z"
    
    for _, row in repos_df.iterrows():
        owner, repo = row['owner'], row['repository']
        if os.path.exists(os.path.join(commit_folder, f"{owner}_{repo}_commits.json")):
            continue  # already extracted
        logger.info(f"Fetching commits for {owner}/{repo}")
        
        try:
            params = {"since": start_dt_iso, "until": end_dt_iso}
            if test_mode:
                params["per_page"] = 100
                data = client.get(f"repos/{owner}/{repo}/commits", params=params)
            else:
                data = client.get_paginated(f"repos/{owner}/{repo}/commits", params=params)
            
            save_raw_json(data, commit_folder, f"{owner}_{repo}_commits.json")
        except Exception as e:
            logger.error(f"Failed to fetch commits for {owner}/{repo}: {e}")

def extract_workflows(client, repos_df, start_date, end_date, raw_dir, test_mode=False):
    logger.info("Extracting workflow runs...")
    workflow_folder = os.path.join(raw_dir, "workflows")
    date_query = f"{start_date}..{end_date}"
    
    for _, row in repos_df.iterrows():
        owner, repo = row['owner'], row['repository']
        if os.path.exists(os.path.join(workflow_folder, f"{owner}_{repo}_workflows.json")):
            continue  # already extracted
        logger.info(f"Fetching workflow runs for {owner}/{repo}")
        
        try:
            params = {"created": date_query}
            if test_mode:
                params["per_page"] = 100
                response = client.get(f"repos/{owner}/{repo}/actions/runs", params=params)
                data = response.get("workflow_runs", [])
            else:
                # The workflow API returns {"total_count": X, "workflow_runs": [...]}
                # get_paginated in github_api.py is designed to handle this (it extracts "items" if present, but for workflows it's "workflow_runs")
                # So we use a custom fetch for workflows to handle the "workflow_runs" key
                data = []
                url = f"repos/{owner}/{repo}/actions/runs"
                params["per_page"] = 100
                
                while url:
                    response = client.session.get(f"{client.base_url}/{url}", params=params)
                    client._check_rate_limit(response)
                    response.raise_for_status()
                    
                    page_data = response.json()
                    data.extend(page_data.get("workflow_runs", []))
                    
                    url_match = response.links.get("next", {}).get("url")
                    url = url_match.replace(f"{client.base_url}/", "") if url_match else None
                    params = None # only needed for first request
                    
            save_raw_json(data, workflow_folder, f"{owner}_{repo}_workflows.json")
        except Exception as e:
            logger.error(f"Failed to fetch workflows for {owner}/{repo}: {e}")

def run_extraction(test_mode=False):
    """Main extraction orchestration."""
    client = GitHubAPIClient()
    
    start_date = client.config["date_range"]["start"]
    end_date = client.config["date_range"]["end"]
    raw_dir = client.config["paths"]["raw_data"]
    repo_file = client.config["repository_config"]
    
    logger.info(f"Starting extraction for date range: {start_date} to {end_date}")
    if test_mode:
        logger.info("RUNNING IN TEST MODE (Limited repos & pagination)")
    
    if not os.path.exists(repo_file):
        logger.error(f"Repository mapping not found at {repo_file}")
        return
        
    repos_df = pd.read_csv(repo_file)
    
    if test_mode:
        # Just use the first 2 repos for testing
        repos_df = repos_df.head(2)
        
    logger.info(f"Loaded {len(repos_df)} repositories to process.")
    
    # Execute extraction phases
    extract_repository_metadata(client, repos_df, raw_dir)
    extract_pull_requests_and_reviews(client, repos_df, start_date, end_date, raw_dir, test_mode)
    extract_issues(client, repos_df, start_date, raw_dir, test_mode)
    extract_commits(client, repos_df, start_date, end_date, raw_dir, test_mode)
    extract_workflows(client, repos_df, start_date, end_date, raw_dir, test_mode)
    
    logger.info("Extraction complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run in test mode (limit to 2 repos, 1 page of data)")
    args = parser.parse_args()
    
    run_extraction(test_mode=args.test)
