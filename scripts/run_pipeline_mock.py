"""Run the full pipeline in MOCK_MODE=true.

Usage:
    python3 scripts/run_pipeline_mock.py

All LLM calls are stubbed — no Groq API calls, no Reddit API calls.
Uses data/mock/mock_reddit_posts.json as the Reddit data source.
"""
import logging
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force mock mode before any imports that read env
os.environ["MOCK_MODE"] = "true"
# Use a very long window so all historical mock data is captured
os.environ.setdefault("TIME_WINDOW_HOURS", "99999")

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline_mock")


def main() -> None:
    logger.info("=== Mock pipeline run starting ===")

    # Late import so env override above takes effect first
    from pipeline.graph import run_pipeline

    try:
        final_state = run_pipeline()
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        sys.exit(1)

    leads = final_state.get("leads_written", 0)
    budget = final_state.get("budget")
    errors = final_state.get("errors", [])

    print("\n" + "=" * 60)
    print("  MOCK PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Leads written   : {leads}")
    if budget:
        print(f"  Estimated cost  : ${budget.estimated_cost_usd:.4f}")
        print(f"  LLM calls made  : {budget.llm_calls_made}")
        print(f"  Budget status   : {budget.budget_status()}")
    if errors:
        print(f"  Errors          : {len(errors)}")
        for err in errors[:5]:
            print(f"    - {err}")
        if len(errors) > 5:
            print(f"    ... and {len(errors) - 5} more")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
