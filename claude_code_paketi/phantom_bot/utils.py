"""Standart kütüphane ile ortak dosya, HTTP, mum ve saat yardımcıları."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import config

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Eski Python sürümlerinde elle DST hesabı kullanılır.
    ZoneInfo = None


def ensure_directories():
    """Botun gerekli çıktı ve önbellek klasörlerini oluşturur."""
    for path in (config.CACHE_DIR, config.SCANS_DIR, config.LOGS_DIR):
        os.makedirs(path, exist_ok=True)


def mask_secrets(message):
    """Return ``message`` with the API key and ``apikey=`` query values masked."""
    return _safe_log_message(message)


def _safe_log_message(message):
    """Log içeriğinde API anahtarı ve URL query anahtarlarını maskeler."""
    value = str(message)
    if config.TWELVEDATA_API_KEY:
        value = value.replace(config.TWELVEDATA_API_KEY, "***")
    value = re.sub(r"(?i)(apikey=)[^&\s]+", r"\1***", value)
    return value


def log(message):
    """Mesajı ekrana ve günlük UTC tarihli log dosyasına yazar."""
    ensure_directories()
    now = datetime.now(timezone.utc)
    line = "[{}] {}".format(now.strftime("%Y-%m-%d %H:%M:%S UTC"), _safe_log_message(message))
    print(line)
    path = os.path.join(config.LOGS_DIR, "run_{}.log".format(now.strftime("%Y-%m-%d")))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def log_file_only(message):
    """Write a timestamped, sanitized message to the daily log without printing it."""
    ensure_directories()
    now = datetime.now(timezone.utc)
    line = "[{}] {}".format(now.strftime("%Y-%m-%d %H:%M:%S UTC"), _safe_log_message(message))
    path = os.path.join(config.LOGS_DIR, "run_{}.log".format(now.strftime("%Y-%m-%d")))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def http_get_json(url, timeout=None, retries=None, retry_delay=1.0, headers=None):
    """urllib ile GET isteği yapar ve JSON döndürür; varsayılan iki deneme."""
    if timeout is None:
        timeout = config.TD_TIMEOUT_SECONDS
    if retries is None:
        retries = 2
    request_headers = {"User-Agent": "PhantomSMCScanner/1.0"}
    if headers:
        request_headers.update(headers)
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=request_headers, method="GET")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(retry_delay)
    raise RuntimeError("HTTP GET/JSON başarısız ({} deneme): {}".format(retries, last_error))


def normalize_candle(candle):
    """Bir mum girdisini {t,o,h,l,c,v} ortak formatına dönüştürür."""
    if isinstance(candle, dict):
        aliases = {"t": ("t", "time", "datetime", "timestamp"), "o": ("o", "open"),
                   "h": ("h", "high"), "l": ("l", "low"), "c": ("c", "close"), "v": ("v", "volume")}
        values = {}
        for target, names in aliases.items():
            found = next((candle[name] for name in names if name in candle), None)
            if found is None:
                raise ValueError("Mum alanı eksik: {}".format(target))
            values[target] = found
    elif isinstance(candle, (list, tuple)) and len(candle) >= 6:
        values = dict(zip(("t", "o", "h", "l", "c", "v"), candle[:6]))
    else:
        raise ValueError("Mum dict veya en az 6 elemanlı dizi olmalı")
    t_value = values["t"]
    if isinstance(t_value, datetime):
        if t_value.tzinfo is None:
            t_value = t_value.replace(tzinfo=timezone.utc)
        timestamp = int(t_value.astimezone(timezone.utc).timestamp())
    elif isinstance(t_value, str):
        try:
            timestamp = int(float(t_value))
        except ValueError:
            parsed = datetime.fromisoformat(t_value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamp = int(parsed.astimezone(timezone.utc).timestamp())
    else:
        timestamp = int(float(t_value))
    normalized = {"t": timestamp}
    for key in ("o", "h", "l", "c", "v"):
        normalized[key] = float(values[key])
    if not validate_candle(normalized):
        raise ValueError("Geçersiz OHLCV mum verisi")
    return normalized


def validate_candle(candle):
    """Ortak mum alanlarını ve OHLC ilişkilerini kontrol eder."""
    if not isinstance(candle, dict) or not all(key in candle for key in ("t", "o", "h", "l", "c", "v")):
        return False
    try:
        t = int(candle["t"])
        o, h, low, c, v = (float(candle[key]) for key in ("o", "h", "l", "c", "v"))
    except (TypeError, ValueError, OverflowError):
        return False
    return (t >= 0 and all(value == value and abs(value) != float("inf") for value in (o, h, low, c, v))
            and h >= max(o, c, low) and low <= min(o, c, h) and v >= 0)


def _second_sunday(year, month):
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    days_to_sunday = (6 - first.weekday()) % 7
    return 1 + days_to_sunday + 7


def _first_sunday(year, month):
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    return 1 + (6 - first.weekday()) % 7


def _is_us_dst_utc(value):
    """ABD DST aralığı: Martın ikinci pazarı 07:00 UTC–Kasımın ilk pazarı 06:00 UTC."""
    year = value.year
    start = datetime(year, 3, _second_sunday(year, 3), 7, tzinfo=timezone.utc)
    end = datetime(year, 11, _first_sunday(year, 11), 6, tzinfo=timezone.utc)
    return start <= value.astimezone(timezone.utc) < end


def utc_to_new_york(value):
    """Aware/naive UTC datetime veya epoch değerini New York saatine çevirir."""
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value, timezone.utc)
    elif not isinstance(value, datetime):
        raise TypeError("value datetime veya epoch olmalı")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    if ZoneInfo is not None:
        try:
            return value.astimezone(ZoneInfo(config.NEW_YORK_TIMEZONE))
        except Exception:
            pass
    offset = timedelta(hours=-4 if _is_us_dst_utc(value) else -5)
    return value.astimezone(timezone(offset, "EDT" if offset == timedelta(hours=-4) else "EST"))


def now_utc():
    """Şu anın aware UTC zamanını döndürür."""
    return datetime.now(timezone.utc)
