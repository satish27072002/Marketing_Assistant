"""Run the full pipeline in live mode (real Reddit + Groq API calls).

Usage:
    python3 scripts/run_pipeline.py [--time-window-hours N] [--max-cost USD]

Environment variables (from .env or shell):
    GROQ_API_KEY          — required
    REDDIT_USER_AGENT     — optional (defaults to leadgen-bot/1.0)
    MOCK_MODE             — must NOT be "true"

No Reddit credentials needed — uses the free public JSON API.
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def _check_env() -> bool:
    required = ["GROQ_API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Set them in .env or export them before running.")
        return False
    if os.environ.get("MOCK_MODE", "false").lower() == "true":
        logger.warning("MOCK_MODE=true detected — switching to live mode. "
                       "Use run_pipeline_mock.py for mock runs.")
        os.environ["MOCK_MODE"] = "false"
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Reddit lead-gen pipeline (live).")
    parser.add_argument(
        "--time-window-hours", type=int, default=None,
        help="How many hours back to scrape (overrides config.yaml / env)",
    )
    parser.add_argument(
        "--max-cost", type=float, default=None,
        help="Hard cost cap in USD (overrides config.yaml / env)",
    )
    args = parser.parse_args()

    if not _check_env():
        sys.exit(1)

    if args.time_window_hours is not None:
        os.environ["TIME_WINDOW_HOURS"] = str(args.time_window_hours)
    if args.max_cost is not None:
        os.environ["MAX_COST_USD"] = str(args.max_cost)

    logger.info("=== Live pipeline run starting ===")

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
    print("  LIVE PIPELINE COMPLETE")
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
