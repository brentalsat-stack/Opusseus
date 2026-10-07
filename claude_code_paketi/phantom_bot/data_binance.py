"""Binance public spot market data helpers (no trading endpoints)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import utils


class BinanceAPIError(RuntimeError):
    """Binance isteklerinin tüm alan adlarında başarısız olduğunu belirtir."""


def _request_json(path, params=None):
    """Yedek alan adlarını dener; 418/429 yanıtında bekleyip aynı alan adını tekrarlar."""
    query = urllib.parse.urlencode(params or {})
    suffix = "?" + query if query else ""
    errors = []
    for base_url in config.BINANCE_BASE_URLS:
        url = base_url.rstrip("/") + path + suffix
        # İstekler arası hız sınırı; 429/418 durumunda ayrıca uzun bekleme uygulanır.
        time.sleep(config.BINANCE_REQUEST_DELAY)
        for attempt in range(2):
            request = urllib.request.Request(url, headers={"User-Agent": "PhantomSMCScanner/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=config.BINANCE_TIMEOUT_SECONDS) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = "{} HTTP {}".format(base_url, exc.code)
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                errors.append("{} {}".format(detail, body[:250]))
                if exc.code in (418, 429) and attempt == 0:
                    time.sleep(config.BINANCE_RATE_LIMIT_WAIT)
                    continue
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append("{} {}".format(base_url, exc))
                break
    raise BinanceAPIError("Binance public API isteği başarısız: " + "; ".join(errors))


def _excluded_symbol(symbol, listed_symbols=None):
    """USDT spot evreninden stablecoin, kaldıraçlı token ve EXCLUDED_SYMBOLS'ı eler.

    Kaldıraçlı token yalnız SONEKLE tanınır (BTCUPUSDT → base BTCUP). "UP" ile biten
    gerçek coinler (JUP, SYRUP) korunur: base'den sonek çıkarılınca kalan varlığın da
    USDT paritesi listede olmalıdır (BTCUP → BTCUSDT var; JUP → JUSDT yok). SUPER gibi
    ortasında UP geçenler hiç etkilenmez.
    """
    if not symbol.endswith(config.BINANCE_QUOTE_ASSET) or symbol in config.EXCLUDED_SYMBOLS:
        return True
    base = symbol[:-len(config.BINANCE_QUOTE_ASSET)]
    if base in set(config.BINANCE_EXCLUDED_BASES):
        return True
    for marker in config.BINANCE_LEVERAGED_MARKERS:
        if base.endswith(marker) and len(base) > len(marker):
            underlying = base[:-len(marker)] + config.BINANCE_QUOTE_ASSET
            if listed_symbols is None or underlying in listed_symbols:
                return True
    return False


def get_top_symbols(n=None):
    """24 saatlik quoteVolume'a göre en yüksek n USDT spot sembolünü döndürür.

    Dönüş biçimi: [{"symbol": "BTCUSDT", "quoteVolume": 123.0}, ...].
    Binance'in ticker/24hr sembolleri spot işlem sembolleridir.
    """
    if n is None:
        n = config.CRYPTO_TOP_DEFAULT
    n = int(n)
    if n < 1:
        raise ValueError("n pozitif tam sayı olmalı")
    payload = _request_json(config.BINANCE_TICKER_24HR_PATH)
    if not isinstance(payload, list):
        raise BinanceAPIError("24 saatlik ticker yanıtı liste biçiminde değil")
    rows = []
    listed = {str(item.get("symbol", "")) for item in payload if isinstance(item, dict)}
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", ""))
        if _excluded_symbol(symbol, listed):
            continue
        try:
            volume = float(item["quoteVolume"])
        except (KeyError, TypeError, ValueError):
            continue
        if volume < 0:
            continue
        rows.append({"symbol": symbol, "quoteVolume": volume})
    rows.sort(key=lambda row: (-row["quoteVolume"], row["symbol"]))
    return rows[:n]


def get_klines(symbol, interval, limit):
    """Mumları ortak formata normalize eder ve açık son mumu ayrıca bildirir.

    Sonuç anahtarları:
      candles: kapanmış mumlar, eskiden yeniye ortak {t,o,h,l,c,v} formatında
      last_candle: API'nin son mumu aynı formatta, varsa
      last_candle_closed: son mumun kapanış zamanı geçmiş mi?

    Son mum kapanmışsa last_candle da candles listesine eklenir. Açık ise
    yapı hesaplarına karışmaması için candles dışında tutulur.
    """
    symbol = str(symbol).upper()
    interval = str(interval)
    limit = int(limit)
    if not symbol or limit < 1:
        raise ValueError("symbol boş olamaz ve limit pozitif olmalı")
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    payload = _request_json(config.BINANCE_KLINES_PATH, params)
    if not isinstance(payload, list):
        raise BinanceAPIError("Kline yanıtı liste biçiminde değil")
    return parse_klines(payload)


def parse_klines(payload, now_ms=None):
    """Binance kline satırlarını (spot ve futures aynı biçim) ortak mum formatına çevirir.

    Sonuç anahtarları get_klines ile aynıdır. ``now_ms`` verilmezse şu an kullanılır;
    kapanış zamanı geçmemiş son mum candles dışında tutulur.
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    closed = []
    last_candle = None
    last_closed = None
    for row in payload:
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            continue
        # Binance kline alanları: open time, OHLC, volume, close time, ...
        candle = utils.normalize_candle({"t": int(row[0]) // 1000, "o": row[1], "h": row[2],
                                         "l": row[3], "c": row[4], "v": row[5]})
        is_closed = int(row[6]) < now_ms
        if last_candle is None or candle["t"] >= last_candle["t"]:
            if last_candle is not None and last_closed:
                closed.append(last_candle)
            last_candle, last_closed = candle, is_closed
        elif is_closed:
            closed.append(candle)
    closed.sort(key=lambda item: item["t"])
    if last_candle is not None and last_closed:
        closed.append(last_candle)
    return {"candles": closed, "last_candle": last_candle, "last_candle_closed": last_closed}
