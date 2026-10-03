"""Twelve Data time_series public market data client with local JSON cache."""
import hashlib
import json
import os
import time
import urllib.parse

import config
import utils


_last_request_at = None


def pip_size(symbol):
    """Döviz/altın sembolünün pip büyüklüğünü verir."""
    normalized = str(symbol).upper().replace(" ", "")
    if "XAU" in normalized:
        return 0.1
    if "JPY" in normalized:
        return 0.01
    return 0.0001


def _cache_path(symbol, interval, outputsize):
    """Parametreleri güvenli dosya adına çevirir."""
    identity = "{}|{}|{}".format(symbol.upper(), interval, int(outputsize))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return os.path.join(config.CACHE_DIR, "twelvedata_{}_{}.json".format(interval, digest))


def _cache_ttl(interval):
    """Önbellek süresini config'ten alır; listelenmeyen aralıklar önbelleksizdir."""
    return int(config.TD_CACHE_TTL_SECONDS.get(interval, 0))


def _read_cache(path, ttl):
    if ttl <= 0:
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
        age = time.time() - float(cached["saved_at"])
        if age < 0 or age >= ttl:
            return None
        candles = cached.get("candles")
        if not isinstance(candles, list) or not all(utils.validate_candle(candle) for candle in candles):
            return None
        return candles
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _write_cache(path, candles):
    utils.ensure_directories()
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"saved_at": time.time(), "candles": candles}, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


def _wait_request_interval():
    """Enforces the configured minimum spacing between outbound requests."""
    global _last_request_at
    if _last_request_at is not None:
        remaining = float(config.REQUEST_DELAY_TD) - (time.monotonic() - _last_request_at)
        if remaining > 0:
            time.sleep(remaining)
    _last_request_at = time.monotonic()


def _request_series(symbol, interval, outputsize):
    """Fetches and validates the Twelve Data payload, retrying one API error once."""
    query = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "outputsize": int(outputsize),
        "timezone": "UTC",
        "apikey": config.TWELVEDATA_API_KEY,
    })
    url = config.TWELVEDATA_BASE_URL.rstrip("/") + config.TWELVEDATA_TIME_SERIES_PATH + "?" + query
    for attempt in range(2):
        try:
            _wait_request_interval()
            # One call per attempt: API status/credit-limit failures are retried below once.
            payload = utils.http_get_json(url, timeout=config.TD_TIMEOUT_SECONDS, retries=1)
            if not isinstance(payload, dict):
                raise ValueError("API yanıtı JSON nesnesi değil")
            if payload.get("status") == "error" or "values" not in payload:
                message = payload.get("message", payload.get("code", "geçersiz API yanıtı"))
                raise ValueError("Twelve Data API hatası: {}".format(message))
            if not isinstance(payload["values"], list):
                raise ValueError("Twelve Data values alanı liste değil")
            candles = []
            for value in payload["values"]:
                candles.append(utils.normalize_candle({
                    "t": value["datetime"],
                    "o": value["open"], "h": value["high"], "l": value["low"],
                    "c": value["close"], "v": value.get("volume", 0),
                }))
            return sorted(candles, key=lambda candle: candle["t"])
        except Exception as exc:
            if attempt == 0:
                time.sleep(float(config.REQUEST_DELAY_TD))
                continue
            # Never include the request URL, since it contains the API key.
            utils.log("Twelve Data {} {} alınamadı: {}".format(symbol, interval, exc))
    return None


def get_series(symbol, interval, outputsize):
    """Returns normalized OHLCV candles oldest-first, or None on API failure."""
    symbol = str(symbol).strip()
    interval = str(interval).strip()
    outputsize = int(outputsize)
    if not symbol or not interval or outputsize < 1:
        raise ValueError("symbol/interval boş olamaz ve outputsize pozitif olmalı")

    utils.ensure_directories()
    ttl = _cache_ttl(interval)
    path = _cache_path(symbol, interval, outputsize)
    cached = _read_cache(path, ttl)
    if cached is not None:
        utils.log("Twelve Data cache hit: {} {} ({} mum)".format(symbol, interval, len(cached)))
        return cached

    candles = _request_series(symbol, interval, outputsize)
    if candles is None:
        return None
    if ttl > 0:
        try:
            _write_cache(path, candles)
        except OSError as exc:
            utils.log("Twelve Data cache yazılamadı ({} {}): {}".format(symbol, interval, exc))
    return candles


def get_series_with_last(symbol, interval, outputsize):
    """Return closed candles separately from the newest candle.

    Twelve Data does not include a reliable close-time field in its time_series
    values. Candle timestamps denote interval starts, so the interval duration
    is used to determine whether the latest bar has closed. ``candles`` contains
    closed bars only; ``last_candle`` is reserved for current-price context.
    """
    candles = get_series(symbol, interval, outputsize)
    if candles is None:
        return None
    durations = {"1day": 86400, "4h": 14400, "1h": 3600,
                 "15min": 900, "5min": 300, "1min": 60}
    duration = durations.get(str(interval))
    if duration is None:
        raise ValueError("Bilinmeyen Twelve Data aralığı: {}".format(interval))
    now = time.time()
    closed = [candle for candle in candles if int(candle["t"]) + duration <= now]
    last_candle = candles[-1] if candles else None
    last_is_closed = bool(last_candle and int(last_candle["t"]) + duration <= now)
    return {"candles": closed, "last_candle": last_candle,
            "last_candle_closed": last_is_closed}
