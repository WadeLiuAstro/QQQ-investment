from datetime import datetime, time
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
SESSION_START = time(9, 30)
SESSION_END = time(16, 0)
SESSION_MINUTES = 390


def _to_new_york(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(NY_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=NY_TZ)
    return now.astimezone(NY_TZ)


def is_regular_session_open(now: datetime | None = None) -> bool:
    """True during the regular US equity session (Mon-Fri 9:30-16:00 ET).

    Market holidays are not detected; on such days Yahoo returns no fresh
    intraday bar, so downstream guards fall back to the closed-market path.
    """
    local = _to_new_york(now)
    if local.weekday() >= 5:
        return False
    return SESSION_START <= local.time() < SESSION_END


def session_elapsed_fraction(now: datetime | None = None) -> float | None:
    """Fraction of the regular session elapsed, in [0.0, 1.0].

    Defined on the closed interval [9:30, 16:00] so the exact close still
    yields 1.0; returns None outside the session window or on weekends.
    """
    local = _to_new_york(now)
    if local.weekday() >= 5:
        return None
    current = local.time()
    if current < SESSION_START or current > SESSION_END:
        return None
    elapsed = (current.hour * 60 + current.minute) - (SESSION_START.hour * 60 + SESSION_START.minute)
    return elapsed / SESSION_MINUTES
