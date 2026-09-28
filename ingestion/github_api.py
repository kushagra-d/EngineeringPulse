"""
GitHub API Client
=================
Handles authentication, GET requests, pagination, retries, and rate limiting.
"""

import os
import time
import requests
import yaml
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from utils.logger import get_logger

# Load environment variables (gets GITHUB_TOKEN from .env)
load_dotenv()
logger = get_logger("ingestion.github_api")

class GitHubAPIClient:
    def __init__(self, config_path: str = "config/config.yaml"):
        # Load configuration
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
            
        self.base_url = self.config["api"]["base_url"]
        self.per_page = self.config["api"]["per_page"]
        self.max_retries = self.config["api"]["max_retries"]
        self.retry_delay = self.config["api"]["retry_delay"]
        self.rate_limit_buffer = self.config["api"]["rate_limit_buffer"]
        
        # Setup authentication
        self.token = os.getenv("GITHUB_TOKEN")
        if not self.token:
            logger.error("GITHUB_TOKEN not found in environment variables.")
            raise ValueError("GITHUB_TOKEN is required.")
            
        # Initialize a requests Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })
        
    def _check_rate_limit(self, response: requests.Response):
        """Monitors GitHub API rate limit headers and pauses if necessary."""
        if response.status_code in (403, 429) and "retry-after" in response.headers:  # secondary (burst) limit
            wait = int(response.headers["retry-after"]) + 5
            logger.warning(f"Secondary rate limit hit. Sleeping for {wait}s.")
            time.sleep(wait)
        remaining = int(response.headers.get("x-ratelimit-remaining", -1))
        reset_time = int(response.headers.get("x-ratelimit-reset", 0))
        
        if remaining != -1 and remaining <= self.rate_limit_buffer:
            sleep_time = max(0, reset_time - int(time.time())) + 5 # Add 5s buffer
            logger.warning(f"Rate limit critical ({remaining} left). Sleeping for {sleep_time}s.")
            time.sleep(sleep_time)

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a single GET request to the GitHub API with retry logic.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params)
                self._check_rate_limit(response)
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Attempt {attempt}/{self.max_retries} failed for {url}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Max retries reached for {url}")
                    raise

    def get_paginated(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Make GET requests and follow pagination links until all pages are retrieved.
        """
        if params is None:
            params = {}
        
        params["per_page"] = self.per_page
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        results = []
        
        while url:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = self.session.get(url, params=params if attempt == 1 else None)
                    self._check_rate_limit(response)
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Handle both list responses and dictionary responses containing a list
                    if isinstance(data, list):
                        results.extend(data)
                    elif isinstance(data, dict) and "items" in data:
                        results.extend(data["items"])
                    else:
                        results.append(data)
                        
                    # Find the next page URL in the headers
                    url = response.links.get("next", {}).get("url")
                    
                    # Clear params after first request since pagination URL includes them
                    params = None 
                    break # Break out of the retry loop on success
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Attempt {attempt}/{self.max_retries} failed for {url}: {e}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay)
                    else:
                        logger.error(f"Max retries reached for {url}")
                        raise
                        
        return results

if __name__ == "__main__":
    # Simple test to verify authentication
    logger.info("Testing GitHub API Client Authentication...")
    try:
        client = GitHubAPIClient()
        rate_limit = client.get("rate_limit")
        core_limit = rate_limit.get("resources", {}).get("core", {})
        
        logger.info("Authentication Successful!")
        logger.info(f"Rate Limit: {core_limit.get('limit')}")
        logger.info(f"Remaining: {core_limit.get('remaining')}")
    except Exception as e:
        logger.error(f"Authentication test failed: {e}")
