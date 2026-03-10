"""Run the full pipeline in live mode (configured sources + Groq API calls).

Usage:
    python3 scripts/run_pipeline.py [--time-window-hours N] [--max-cost USD] [--sources reddit,facebook]

Environment variables (from .env or shell):
    GROQ_API_KEY          — required
    REDDIT_USER_AGENT     — optional (defaults to leadgen-bot/1.0)
    MOCK_MODE             — must NOT be "true"

No Reddit credentials needed — uses the free public JSON API for Reddit source.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, time as dt_time, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def _date_range_to_utc_window(start_date, end_date) -> tuple[datetime, datetime]:
    """Convert local date range to UTC datetimes (inclusive end date)."""
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    now_local = datetime.now(local_tz)

    start_local = datetime.combine(start_date, dt_time.min, tzinfo=local_tz)
    if end_date == now_local.date():
        end_local = now_local
    else:
        end_local = datetime.combine(end_date, dt_time.max, tzinfo=local_tz)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


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
    parser = argparse.ArgumentParser(description="Run the lead-gen pipeline (live).")
    parser.add_argument(
        "--time-window-hours", type=int, default=None,
        help="How many hours back to scrape (overrides config.yaml / env)",
    )
    parser.add_argument(
        "--max-cost", type=float, default=None,
        help="Hard cost cap in USD (overrides config.yaml / env)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated sources to run (e.g. reddit or reddit,facebook).",
    )
    parser.add_argument(
        "--start-date", type=str, default=None,
        help="Optional start date in YYYY-MM-DD (must be used with --end-date).",
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="Optional end date in YYYY-MM-DD (must be used with --start-date).",
    )
    args = parser.parse_args()

    if not _check_env():
        sys.exit(1)

    if args.time_window_hours is not None:
        os.environ["TIME_WINDOW_HOURS"] = str(args.time_window_hours)
    if args.max_cost is not None:
        os.environ["MAX_COST_USD"] = str(args.max_cost)

    if bool(args.start_date) ^ bool(args.end_date):
        logger.error("Provide both --start-date and --end-date together.")
        sys.exit(2)
    if args.start_date and args.end_date and args.time_window_hours is not None:
        logger.error("Use either --time-window-hours or --start-date/--end-date, not both.")
        sys.exit(2)

    window_start = None
    window_end = None
    parsed_sources = None
    if args.start_date and args.end_date:
        try:
            start_d = datetime.strptime(args.start_date, "%Y-%m-%d").date()
            end_d = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Dates must be in YYYY-MM-DD format.")
            sys.exit(2)
        if end_d < start_d:
            logger.error("--end-date must be on or after --start-date.")
            sys.exit(2)
        window_start, window_end = _date_range_to_utc_window(start_d, end_d)

    if args.sources:
        parsed_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
        allowed = {"reddit", "facebook"}
        invalid = [s for s in parsed_sources if s not in allowed]
        if invalid:
            logger.error("Invalid --sources values: %s (allowed: %s)", invalid, sorted(allowed))
            sys.exit(2)

    logger.info("=== Live pipeline run starting ===")

    from pipeline.graph import run_pipeline

    try:
        final_state = run_pipeline(
            time_window_hours=args.time_window_hours,
            time_window_start=window_start,
            time_window_end=window_end,
            max_cost_usd=args.max_cost,
            sources=parsed_sources,
        )
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
