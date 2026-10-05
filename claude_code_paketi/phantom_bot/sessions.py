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
