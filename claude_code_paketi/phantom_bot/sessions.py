"""New York trading sessions, Asia range, rollover, Sunday and news windows."""
import csv
import os
from datetime import datetime, timedelta, timezone

import config
import utils


def _as_utc(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if not isinstance(value, datetime):
        raise TypeError("zaman datetime veya epoch olmalı")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _minutes(hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return hour * 60 + minute


def session_tags(value):
    """Return names of active configured sessions containing the UTC time."""
    local = utils.utc_to_new_york(_as_utc(value))
    minute = local.hour * 60 + local.minute
    tags = []
    for name, start_text, end_text, active in config.SESSIONS:
        if not active:
            continue
        start, end = _minutes(start_text), _minutes(end_text)
        if start <= end:
            inside = start <= minute < end
        else:
            inside = minute >= start or minute < end
        if inside:
            tags.append(name)
    return tags


def asia_range(candles, session_date=None):
    """Return ASIA high/low/midline for a NY-local 20:00–00:00 session.

    ``session_date`` is the New York calendar date on which the session starts.
    When omitted, date is inferred from the latest candle and its session side.
    """
    if not candles:
        return {"high": None, "low": None, "midline": None}
    converted = [(utils.utc_to_new_york(_as_utc(c["t"])), c) for c in candles]
    if session_date is None:
        latest = converted[-1][0]
        session_date = latest.date() - timedelta(days=1) if latest.hour < 1 else latest.date()
    if isinstance(session_date, str):
        session_date = datetime.strptime(session_date, "%Y-%m-%d").date()
    start = datetime.combine(session_date, datetime.min.time()).replace(hour=20)
    end = datetime.combine(session_date + timedelta(days=1), datetime.min.time())
    selected = [c for local, c in converted if start <= local.replace(tzinfo=None) < end]
    if not selected:
        return {"high": None, "low": None, "midline": None}
    high = max(float(c.get("h", c.get("high"))) for c in selected)
    low = min(float(c.get("l", c.get("low"))) for c in selected)
    return {"high": high, "low": low, "midline": (high + low) / 2.0}


def in_spread_hour(value):
    """Whether the New York local time falls in configured rollover window."""
    local = utils.utc_to_new_york(_as_utc(value))
    minute = local.hour * 60 + local.minute
    start, end = (_minutes(item) for item in config.SPREAD_HOUR)
    if start <= end:
        return start <= minute < end
    return minute >= start or minute < end


def sunday_open_restriction(value):
    """True during the configured hours after Sunday 17:00 New York open."""
    local = utils.utc_to_new_york(_as_utc(value))
    if local.weekday() != 6:
        return False
    opened = local.replace(hour=17, minute=0, second=0, microsecond=0)
    return timedelta(0) <= local - opened < timedelta(hours=int(config.SUNDAY_HOURS))


def _parse_news_datetime(text):
    parsed = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def news_warnings(value, symbol, market="forex", news_path=None):
    """Return high-impact news matches in the configured +/- minute window.

    Missing news.csv is deliberately silent. FX symbols match either currency;
    crypto only matches USD and ALL. Returns list of matched row dictionaries.
    """
    path = news_path or config.NEWS_CSV
    if not os.path.isfile(path):
        return []
    now = _as_utc(value)
    currencies = {part.strip().upper() for part in str(symbol).upper().split("/")}
    if str(market).lower() == "crypto":
        currencies = {"USD"}
    currencies.add("ALL")
    window = timedelta(minutes=int(config.NEWS_WINDOW_MIN))
    matches = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                impact = str(row.get("impact", "")).strip().lower()
                currency = str(row.get("currency", "")).strip().upper()
                if impact not in ("high", "red", "3") or currency not in currencies:
                    continue
                try:
                    news_time = _parse_news_datetime(row.get("datetime_utc", ""))
                except (TypeError, ValueError):
                    continue
                if abs(now - news_time) <= window:
                    matches.append(dict(row))
    except OSError:
        return []
    return matches
