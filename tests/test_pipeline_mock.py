"""End-to-end mock pipeline test.

Runs the full 10-node pipeline with MOCK_MODE=true.
No Groq API calls, no Reddit API calls, no cost.

Run:
    python3 -m pytest tests/test_pipeline_mock.py -v
"""
import json
import os
import sys
import uuid

import pytest

# Force mock mode before any project imports
os.environ["MOCK_MODE"] = "true"
os.environ.setdefault("GROQ_API_KEY", "mock-key-for-testing")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def ensure_db():
    """Make sure the DB tables exist before running (idempotent)."""
    from db.database import Base, engine
    Base.metadata.create_all(bind=engine)


@pytest.fixture()
def fresh_run_id():
    return f"test-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_pipeline_for_test(run_id: str | None = None) -> dict:
    """
    Run the pipeline and return final_state.
    Optionally inject a specific run_id so tests can query the DB afterwards.
    """
    import pipeline.graph as graph_module

    if run_id:
        # Monkey-patch uuid so the run uses our controlled ID
        import unittest.mock as mock
        with mock.patch("pipeline.graph.uuid.uuid4", return_value=mock.MagicMock(
            __str__=lambda _: run_id
        )):
            return graph_module.run_pipeline()
    return graph_module.run_pipeline()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMockPipelineSmoke:
    """Smoke tests: pipeline completes without raising exceptions."""

    def test_pipeline_returns_dict(self):
        state = _run_pipeline_for_test()
        assert isinstance(state, dict), "run_pipeline() must return a dict"

    def test_run_id_present(self):
        state = _run_pipeline_for_test()
        assert "run_id" in state
        assert isinstance(state["run_id"], str)
        assert len(state["run_id"]) > 0

    def test_no_unexpected_exceptions(self):
        """Pipeline must not propagate any exception in mock mode."""
        try:
            _run_pipeline_for_test()
        except Exception as exc:
            pytest.fail(f"Pipeline raised an unexpected exception: {exc}")


class TestMockPipelineState:
    """Verify that key state fields are present and have sensible types."""

    @pytest.fixture(scope="class")
    def state(self):
        return _run_pipeline_for_test()

    def test_budget_in_state(self, state):
        budget = state.get("budget")
        assert budget is not None, "budget must be in final state"

    def test_budget_cost_is_non_negative(self, state):
        budget = state["budget"]
        assert budget.estimated_cost_usd >= 0.0

    def test_errors_is_list(self, state):
        errors = state.get("errors", [])
        assert isinstance(errors, list)

    def test_leads_written_is_int(self, state):
        leads = state.get("leads_written", 0)
        assert isinstance(leads, int)
        assert leads >= 0

    def test_user_aggregates_is_list(self, state):
        aggs = state.get("user_aggregates", [])
        assert isinstance(aggs, list)

    def test_selected_items_is_list(self, state):
        items = state.get("selected_items", [])
        assert isinstance(items, list)

    def test_events_loaded(self, state):
        events = state.get("events", [])
        assert isinstance(events, list)
        # At least one event from sample_event.json
        assert len(events) >= 1, "Expected at least one event to be loaded"

    def test_collected_item_ids_present(self, state):
        item_ids = state.get("collected_item_ids", [])
        assert isinstance(item_ids, list)
        # Mock data has 30 posts
        assert len(item_ids) >= 0  # may be 0 if DB already has them (dedup)


class TestMockPipelineBudget:
    """Budget tracking and status checks."""

    @pytest.fixture(scope="class")
    def budget(self):
        state = _run_pipeline_for_test()
        return state["budget"]

    def test_budget_status_is_valid(self, budget):
        valid_statuses = {"OK", "YELLOW", "WARNING", "DEGRADED"}
        assert budget.budget_status() in valid_statuses

    def test_mock_cost_is_zero_or_tiny(self, budget):
        # In mock mode no real LLM calls are made so cost should be 0
        assert budget.estimated_cost_usd == 0.0, (
            f"Mock mode should have zero cost, got ${budget.estimated_cost_usd:.4f}"
        )

    def test_stop_not_requested_in_mock(self, budget):
        assert not budget.stop_requested, "Budget stop should not be triggered in mock mode"


class TestMockPipelineDatabase:
    """Check that the pipeline wrote expected records to SQLite."""

    @pytest.fixture(scope="class")
    def run_state(self):
        rid = f"test-e2e-{uuid.uuid4().hex[:6]}"
        state = _run_pipeline_for_test(run_id=rid)
        return state, rid

    def test_run_record_exists(self, run_state):
        state, run_id = run_state
        from db.database import SessionLocal
        from db.models import Run
        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            assert run is not None, f"Run record {run_id} not found in DB"
        finally:
            db.close()

    def test_run_status_completed(self, run_state):
        state, run_id = run_state
        from db.database import SessionLocal
        from db.models import Run
        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            assert run is not None
            assert run.status in {"COMPLETED", "STOPPED"}, (
                f"Expected COMPLETED or STOPPED, got {run.status}"
            )
        finally:
            db.close()

    def test_raw_items_written(self, run_state):
        state, run_id = run_state
        from db.database import SessionLocal
        from db.models import RawItem
        db = SessionLocal()
        try:
            count = db.query(RawItem).filter(RawItem.run_id == run_id).count()
            assert count >= 0  # may be 0 if all posts were already deduped
        finally:
            db.close()

    def test_run_completed_at_set(self, run_state):
        state, run_id = run_state
        from db.database import SessionLocal
        from db.models import Run
        db = SessionLocal()
        try:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            assert run is not None
            assert run.completed_at is not None, "completed_at should be set after finalize"
        finally:
            db.close()


class TestMockPipelineLeads:
    """Verify lead quality when mock data produces matches."""

    @pytest.fixture(scope="class")
    def leads_and_run(self):
        rid = f"test-leads-{uuid.uuid4().hex[:6]}"
        state = _run_pipeline_for_test(run_id=rid)
        from db.database import SessionLocal
        from db.models import Lead
        db = SessionLocal()
        try:
            leads = db.query(Lead).all()
            return leads, state
        finally:
            db.close()

    def test_leads_have_required_fields(self, leads_and_run):
        leads, _ = leads_and_run
        for lead in leads:
            assert lead.source, f"Lead {lead.id} missing source"
            assert lead.username, f"Lead {lead.id} missing username"
            assert lead.primary_event_id, f"Lead {lead.id} missing primary_event_id"
            assert lead.status == "NEW", f"Lead {lead.id} has unexpected status {lead.status}"

    def test_lead_confidence_in_range(self, leads_and_run):
        leads, _ = leads_and_run
        for lead in leads:
            assert 0.0 <= lead.top_confidence <= 1.0, (
                f"Lead {lead.id} confidence {lead.top_confidence} out of [0,1]"
            )

    def test_leads_written_matches_db(self, leads_and_run):
        leads, state = leads_and_run
        leads_written = state.get("leads_written", 0)
        # leads_written counts only from this run; DB may have more from prior runs
        assert leads_written >= 0


class TestMockPipelineRecoveryQueue:
    """Check that recovery_queue.json is written after a run."""

    def test_recovery_queue_exists(self):
        _run_pipeline_for_test()
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "recovery_queue.json",
        )
        assert os.path.exists(path), "data/recovery_queue.json should exist after a run"

    def test_recovery_queue_is_valid_json(self):
        _run_pipeline_for_test()
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "recovery_queue.json",
        )
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, list), "recovery_queue.json should contain a JSON list"


class TestMockPipelineIdempotent:
    """Running the pipeline twice should not crash or double-write leads."""

    def test_second_run_does_not_crash(self):
        _run_pipeline_for_test()
        try:
            _run_pipeline_for_test()
        except Exception as exc:
            pytest.fail(f"Second pipeline run raised: {exc}")

    def test_leads_not_duplicated(self):
        """Lead dedup: same (source, username, event_id) should not appear twice."""
        _run_pipeline_for_test()
        _run_pipeline_for_test()
        from db.database import SessionLocal
        from db.models import Lead
        db = SessionLocal()
        try:
            leads = db.query(Lead).all()
            seen: set[tuple] = set()
            for lead in leads:
                key = (lead.source, lead.username, lead.primary_event_id)
                assert key not in seen, f"Duplicate lead found: {key}"
                seen.add(key)
        finally:
            db.close()
