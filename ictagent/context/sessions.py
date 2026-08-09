"""
Session / kill-zone timing — fully deterministic, no external API.

Two related but distinct concepts, both used by playbook rule 5:

  - `TRADING_SESSIONS`: broad windows during which a given exchange is
    generally open/liquid (Tokyo, London, New York, and NSE/BSE for the
    Indian equities leg).
  - `KILL_ZONES`: narrow, high-probability ICT entry windows within
    those sessions, anchored to New York local time per common
    convention across ICT-adjacent material.

All windows are defined in their *local* exchange/reference time zone
and converted correctly for DST via the standard library's `zoneinfo`
(not a fixed UTC offset — London/New York's UTC offset changes twice a
year, and a fixed-offset table would silently drift out of sync for half
of it). Naive datetimes passed in are assumed to be UTC.

These are widely-cited *approximate* defaults, not a fixed standard —
exactly the kind of thing playbook/base_rules.md says to refine over
time. Adjust `KILL_ZONES`/`TRADING_SESSIONS` as your own review of
reasoning quality suggests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Window:
    name: str
    zone: str  # IANA timezone name this window is defined in local time for
    start: time
    end: time  # if end <= start, the window wraps past local midnight

    def contains(self, moment: datetime) -> bool:
        local_time = _to_local(moment, self.zone).time()
        if self.start <= self.end:
            return self.start <= local_time < self.end
        return local_time >= self.start or local_time < self.end


def _to_local(moment: datetime, zone: str) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo(zone))


# Broad trading sessions — when each market is generally open.
TRADING_SESSIONS: dict[str, Window] = {
    "tokyo": Window("Tokyo", "Asia/Tokyo", time(9, 0), time(15, 0)),
    "london": Window("London", "Europe/London", time(8, 0), time(16, 30)),
    "new_york": Window("New York", "America/New_York", time(9, 30), time(16, 0)),
    "nse": Window("NSE/BSE (India)", "Asia/Kolkata", time(9, 15), time(15, 30)),
}

# ICT-style kill zones — narrow windows favoured for entries, in New York
# local time. See module docstring: approximate, adjustable defaults.
KILL_ZONES: dict[str, Window] = {
    "asian_kz": Window("Asian Kill Zone", "America/New_York", time(20, 0), time(0, 0)),
    "london_kz": Window("London Kill Zone", "America/New_York", time(2, 0), time(5, 0)),
    "ny_am_kz": Window("New York AM Kill Zone", "America/New_York", time(7, 0), time(10, 0)),
    "london_close_kz": Window("London Close Kill Zone", "America/New_York", time(10, 0), time(12, 0)),
}


@dataclass(frozen=True)
class SessionContext:
    timestamp: datetime
    open_sessions: list[str]
    active_kill_zones: list[str]

    @property
    def in_kill_zone(self) -> bool:
        return len(self.active_kill_zones) > 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open_sessions": self.open_sessions,
            "active_kill_zones": self.active_kill_zones,
            "in_kill_zone": self.in_kill_zone,
        }


def get_session_context(moment: datetime | None = None) -> SessionContext:
    """Which sessions are open and which kill zones are active at `moment`
    (defaults to now, UTC). Naive datetimes are assumed to be UTC."""
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    open_sessions = [name for name, w in TRADING_SESSIONS.items() if w.contains(moment)]
    active_kill_zones = [name for name, w in KILL_ZONES.items() if w.contains(moment)]

    return SessionContext(
        timestamp=moment, open_sessions=open_sessions, active_kill_zones=active_kill_zones
    )
