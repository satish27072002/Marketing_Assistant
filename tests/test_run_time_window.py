from datetime import datetime, timedelta, timezone

import pytest

from pipeline.graph import _resolve_time_window


def test_resolve_time_window_prefers_explicit_range() -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)

    resolved_start, resolved_end, hours = _resolve_time_window(
        now=now,
        default_hours=48,
        requested_hours=24,
        requested_start=start,
        requested_end=end,
    )

    assert resolved_start == start
    assert resolved_end == end
    assert hours == 108


def test_resolve_time_window_requires_both_range_bounds() -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        _resolve_time_window(
            now=now,
            default_hours=48,
            requested_start=start,
            requested_end=None,
        )


def test_resolve_time_window_uses_hours_fallback() -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)

    resolved_start, resolved_end, hours = _resolve_time_window(
        now=now,
        default_hours=48,
        requested_hours=72,
    )

    assert resolved_end == now
    assert resolved_start == now - timedelta(hours=72)
    assert hours == 72
