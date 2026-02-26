"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="RUNNING"),
        sa.Column("time_window_start", sa.DateTime(), nullable=False),
        sa.Column("time_window_end", sa.DateTime(), nullable=False),
        sa.Column("items_collected", sa.Integer(), server_default="0"),
        sa.Column("items_matched", sa.Integer(), server_default="0"),
        sa.Column("leads_written", sa.Integer(), server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("stop_requested", sa.Boolean(), server_default="0"),
        sa.Column("error_log", sa.Text(), nullable=True),
    )

    op.create_table(
        "raw_items",
        sa.Column("item_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("subreddit", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("permalink", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_utc", sa.DateTime(), nullable=False),
        sa.Column("query_used", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default="0"),
        sa.Column("processing_status", sa.String(), server_default="PENDING"),
    )

    op.create_table(
        "user_event_affinity",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False, server_default="reddit"),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("profile_url", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("evidence_item_id", sa.String(), nullable=False),
        sa.Column("evidence_excerpt", sa.String(), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.Column("match_reason", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "source", "username", "event_id", "evidence_item_id",
            name="uq_affinity_key"
        ),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False, server_default="reddit"),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("profile_url", sa.String(), nullable=True),
        sa.Column("primary_event_id", sa.String(), nullable=False),
        sa.Column("other_event_ids", sa.String(), nullable=True),
        sa.Column("top_confidence", sa.Float(), nullable=False),
        sa.Column("user_summary", sa.Text(), nullable=True),
        sa.Column("evidence_excerpts", sa.Text(), nullable=True),
        sa.Column("evidence_urls", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="NEW"),
        sa.Column("reviewer_feedback", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "source", "username", "primary_event_id",
            name="uq_lead_key"
        ),
    )

    op.create_table(
        "processing_queue",
        sa.Column("item_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("processing_queue")
    op.drop_table("leads")
    op.drop_table("user_event_affinity")
    op.drop_table("raw_items")
    op.drop_table("runs")
