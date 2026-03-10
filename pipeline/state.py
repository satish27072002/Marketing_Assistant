from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from typing_extensions import TypedDict


@dataclass
class Event:
    event_id: str
    title: str
    city: str
    start_time: datetime
    end_time: datetime
    description: str
    tags: list[str]
    languages: list[str] = field(default_factory=list)
    capacity: Optional[int] = None


class PipelineState(TypedDict, total=False):
    # Node A output
    events: list[Event]

    # Node B output
    event_index_ready: bool

    # Node C output
    scrape_plan: dict[str, Any]

    # Node D output
    validated_plan: dict[str, Any]

    # Node E output
    collected_item_ids: list[str]

    # Node F output
    selected_items: list[dict[str, Any]]

    # Node G output
    affinities_written: int

    # Node H output
    user_aggregates: list[dict[str, Any]]

    # Node I output
    leads_written: int

    # Shared
    run_id: str
    run_config: dict[str, Any]
    budget: Any
    errors: list[str]
