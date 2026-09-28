"""
EngineeringPulse Pipeline Orchestrator
======================================
Single entry point that runs the full local pipeline:
    Extract → Clean → Quality Check → Export

Usage:
    python run_pipeline.py           # Run full pipeline
    python run_pipeline.py extract   # Run extraction only
    python run_pipeline.py clean     # Run cleaning only
    python run_pipeline.py gold      # Build Gold tables (keys, dims, facts) only
    python run_pipeline.py quality   # Run quality checks only
    python run_pipeline.py export    # Load Gold into PostgreSQL only
"""

import sys
from utils.logger import get_logger

logger = get_logger("pipeline")


def main():
    """Main pipeline orchestrator."""
    logger.info("=" * 60)
    logger.info("EngineeringPulse Pipeline")
    logger.info("=" * 60)

    # Determine which step to run
    step = sys.argv[1] if len(sys.argv) > 1 else "all"

    if step in ("all", "extract"):
        logger.info("Step 1: Extraction")
        from ingestion.extract import run_extraction
        run_extraction(test_mode=False)

    if step in ("all", "clean"):
        logger.info("Step 2: Cleaning")
        from processing.clean_data import run_cleaning
        run_cleaning()

    if step in ("all", "gold"):
        logger.info("Step 3: Build Gold layer")
        from processing.build_gold import run_gold
        run_gold()

    if step in ("all", "quality"):
        logger.info("Step 4: Quality Checks")
        from processing.data_quality import run_quality
        if run_quality():
            sys.exit("Data quality checks failed; see data/quality/data_quality_report.csv")

    if step in ("all", "export"):
        logger.info("Step 5: Export to PostgreSQL")
        from processing.load_postgres import run_loading
        run_loading()

    logger.info("=" * 60)
    logger.info("Pipeline complete.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
