from datetime import datetime, timezone

from ictagent.context.sessions import get_session_context, TRADING_SESSIONS, KILL_ZONES


def test_asian_kill_zone_in_winter_est():
    # NY local 21:00 EST (UTC-5) on 2026-01-15 -> UTC 2026-01-16 02:00
    moment = datetime(2026, 1, 16, 2, 0, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert "asian_kz" in ctx.active_kill_zones
    assert ctx.in_kill_zone


def test_asian_kill_zone_in_summer_edt_dst_handled_correctly():
    # NY local 21:00 EDT (UTC-4) on 2026-07-15 -> UTC 2026-07-16 01:00.
    # This only passes if DST is actually applied (zoneinfo, not a fixed
    # UTC offset) — the same NY local time maps to a different UTC hour
    # than the winter case above.
    moment = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert "asian_kz" in ctx.active_kill_zones


def test_london_kill_zone():
    # NY local 03:00 EST (UTC-5) on 2026-01-15 -> UTC 08:00
    moment = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert "london_kz" in ctx.active_kill_zones
    assert "asian_kz" not in ctx.active_kill_zones


def test_new_york_am_kill_zone():
    # NY local 08:00 EST (UTC-5) on 2026-01-15 -> UTC 13:00
    moment = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert "ny_am_kz" in ctx.active_kill_zones


def test_no_kill_zone_mid_afternoon_new_york():
    # NY local 15:00 EST (UTC-5) on 2026-01-15 -> UTC 20:00 — between the
    # London-close KZ (ends 12:00 NY) and the Asian KZ (starts 20:00 NY).
    moment = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert ctx.active_kill_zones == []
    assert not ctx.in_kill_zone


def test_nse_session_open():
    # Kolkata local 10:00 IST (UTC+5:30) -> UTC 04:30
    moment = datetime(2026, 1, 15, 4, 30, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert "nse" in ctx.open_sessions


def test_nse_session_closed_outside_hours():
    # Kolkata local 20:00 IST -> UTC 14:30, well after NSE close (15:30 IST)
    moment = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    ctx = get_session_context(moment)
    assert "nse" not in ctx.open_sessions


def test_naive_datetime_assumed_utc():
    aware = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 15, 13, 0)
    assert get_session_context(naive).active_kill_zones == get_session_context(aware).active_kill_zones


def test_default_moment_is_now_and_does_not_raise():
    ctx = get_session_context()
    assert isinstance(ctx.open_sessions, list)
    assert isinstance(ctx.active_kill_zones, list)


def test_to_dict_shape():
    moment = datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc)
    d = get_session_context(moment).to_dict()
    assert set(d) == {"timestamp", "open_sessions", "active_kill_zones", "in_kill_zone"}
    assert d["in_kill_zone"] is True


def test_all_windows_are_registered_with_valid_names():
    assert set(TRADING_SESSIONS) == {"tokyo", "london", "new_york", "nse"}
    assert set(KILL_ZONES) == {"asian_kz", "london_kz", "ny_am_kz", "london_close_kz"}
