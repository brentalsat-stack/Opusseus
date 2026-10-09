"""Zaman dilimi yardımcıları. Saklama UTC; çeviri IANA (zoneinfo)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
LONDON = ZoneInfo("Europe/London")
ISTANBUL = ZoneInfo("Europe/Istanbul")


def ensure_utc(dt: datetime) -> datetime:
    """Tz-aware datetime'ı UTC'ye çevirir; naive reddedilir."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive datetime kabul edilmez; saat dilimi belirtin")
    return dt.astimezone(UTC)


def to_tz(dt: datetime, tz: ZoneInfo | str) -> datetime:
    return ensure_utc(dt).astimezone(ZoneInfo(tz) if isinstance(tz, str) else tz)


def to_london(dt: datetime) -> datetime:
    return to_tz(dt, LONDON)


def to_istanbul(dt: datetime) -> datetime:
    return to_tz(dt, ISTANBUL)


def local_to_utc(naive: datetime, tz: ZoneInfo | str, fold: int = 0) -> datetime:
    """Yerel duvar saatini UTC'ye çevirir. DST boşluğundaki (var olmayan) saat reddedilir;
    belirsiz (çift) saatte `fold` ile seçim yapılır (0 = ilk)."""
    if naive.tzinfo is not None:
        raise ValueError("naive yerel saat bekleniyor")
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    aware = naive.replace(tzinfo=zone, fold=fold)
    utc = aware.astimezone(UTC)
    if utc.astimezone(zone).replace(tzinfo=None) != naive:
        raise ValueError(f"{naive} {zone.key} saatinde mevcut değil (DST boşluğu)")
    return utc
