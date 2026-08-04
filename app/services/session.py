from datetime import date, datetime, time, timedelta
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


def latest_trading_day(today: date) -> date:
    """today 之前（含当天）最近的一个常规交易日（跳过周末，节假日不识别）。"""
    candidate = today
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def trading_day_lag(latest: date, today: date) -> int:
    """最新数据日期到最近交易日的滞后交易日数（0 = 已是最新；周末不计）。"""
    target = latest_trading_day(today)
    if latest >= target:
        return 0
    lag = 0
    cursor = latest + timedelta(days=1)
    while cursor <= target:
        if cursor.weekday() < 5:
            lag += 1
        cursor += timedelta(days=1)
    return lag


def expected_bar_date(now: datetime) -> date:
    """最近一个已收盘交易日的日期（16:00 后当天算已收盘；盘前/周末回退）。"""
    local = _to_new_york(now)
    if local.time() >= SESSION_END:
        return latest_trading_day(local.date())
    return latest_trading_day(local.date() - timedelta(days=1))
