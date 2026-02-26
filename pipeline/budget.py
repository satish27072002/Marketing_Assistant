"""RunBudget — created at the start of every run, passed through LangGraph state.

Every node checks the budget before making any external call.
Notification tiers (from Section 08 of the implementation plan):
  75% cost consumed  → silent log only
  50% cost remaining → dashboard indicator turns yellow
  $2.00 remaining    → dashboard notification (run continues)
  $0.50 remaining    → auto-switch to keyword-only matching
  $0.00 / hard cap   → stop run, finalize with existing data
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RunBudget:
    # Time window
    time_window_start: datetime
    time_window_end: datetime

    # Hard caps (from config.yaml)
    max_queries: int = 20
    max_items_per_run: int = 100
    max_cost_usd: float = 5.00

    # Live counters
    queries_used: int = 0
    items_processed: int = 0
    llm_calls_made: int = 0
    estimated_cost_usd: float = 0.0

    # Control flags
    stop_requested: bool = False
    degraded_mode: bool = False  # True = keyword-only, no LLM

    def cost_remaining(self) -> float:
        return max(0.0, self.max_cost_usd - self.estimated_cost_usd)

    def cost_pct_consumed(self) -> float:
        if self.max_cost_usd == 0:
            return 100.0
        return (self.estimated_cost_usd / self.max_cost_usd) * 100

    def budget_status(self) -> str:
        """Returns dashboard status string: OK | YELLOW | WARNING | DEGRADED."""
        if self.degraded_mode:
            return "DEGRADED"
        remaining = self.cost_remaining()
        if remaining <= 2.00:
            return "WARNING"
        if self.cost_pct_consumed() >= 50:
            return "YELLOW"
        return "OK"

    def should_stop(self) -> bool:
        return self.stop_requested or self.cost_remaining() <= 0

    def check_and_log(self, logger) -> None:
        """Log budget state at appropriate tier."""
        pct = self.cost_pct_consumed()
        remaining = self.cost_remaining()
        if pct >= 75:
            logger.info(
                "Budget: %.1f%% consumed ($%.4f of $%.2f)",
                pct, self.estimated_cost_usd, self.max_cost_usd,
            )
        if remaining <= 2.00:
            logger.warning(
                "Budget WARNING: $%.4f remaining — %d leads found so far",
                remaining, 0,
            )
