"""Binance USDⓈ-M perpetual public market data helpers (no trading endpoints).

Yalnızca fapi alan adı kullanılır; spot'un yedek alan adları (data-api.binance.vision)
vadeli piyasada geçerli olmadığından burada denenmez.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import data_binance
import utils


class FuturesAPIError(RuntimeError):
    """fapi isteklerinin başarısız olduğunu belirtir."""


class FuturesRegionBlocked(FuturesAPIError):
    """HTTP 451/403: fapi bu konumdan erişime kapalı (bölgesel kısıt)."""


def request_json(path, params=None, with_headers=False):
    """fapi'den JSON okur. 418/429'da uzun bekleyip bir kez tekrar dener.

    ``with_headers=True`` iken (payload, başlıklar sözlüğü) döner; başlıklar küçük
    harfe çevrilir (ör. ``x-mbx-used-weight-1m``).
    """
    query = urllib.parse.urlencode(params or {})
    suffix = "?" + query if query else ""
    errors = []
    for base_url in config.BINANCE_FUTURES_BASE_URLS:
        url = base_url.rstrip("/") + path + suffix
        time.sleep(config.BINANCE_REQUEST_DELAY)
        for attempt in range(2):
            request = urllib.request.Request(url, headers={"User-Agent": "PhantomSMCScanner/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=config.BINANCE_TIMEOUT_SECONDS) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    headers = {key.lower(): value for key, value in response.headers.items()}
                return (payload, headers) if with_headers else payload
            except urllib.error.HTTPError as exc:
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                if exc.code in (451, 403):
                    raise FuturesRegionBlocked(
                        "Binance futures (fapi) bu konumdan erişime kapalı (HTTP {}). "
                        "VPN/farklı ağ gerekebilir: {}".format(exc.code, body[:160]))
                errors.append("{} HTTP {} {}".format(base_url, exc.code, body[:200]))
                if exc.code in (418, 429) and attempt == 0:
                    time.sleep(config.BINANCE_RATE_LIMIT_WAIT)
                    continue
                break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                errors.append("{} {}".format(base_url, exc))
                break
    raise FuturesAPIError("Binance futures isteği başarısız: " + "; ".join(errors))


def parse_exchange_info(payload):
    """exchangeInfo yanıtından uygun perpetual USDT sembollerini seçer.

    Dönüş: (semboller listesi, bilgi sözlüğü). Koşullar: contractType == PERPETUAL,
    quoteAsset == USDT, status == TRADING ve underlyingType == COIN. underlyingType
    alanı yoksa sembol ATILMAZ; sayılır ve ``missing_underlying`` listesinde döner
    (EXCLUDED_SYMBOLS / stable kuralı yine uygulanır).
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise FuturesAPIError("exchangeInfo yanıtında 'symbols' listesi yok")
    rows = [row for row in payload["symbols"] if isinstance(row, dict)]
    listed = {str(row.get("symbol", "")) for row in rows}
    selected, missing, not_coin = [], [], []
    for row in rows:
        symbol = str(row.get("symbol", ""))
        if (row.get("contractType") != "PERPETUAL" or row.get("quoteAsset") != config.BINANCE_QUOTE_ASSET
                or row.get("status") != "TRADING"):
            continue
        if data_binance._excluded_symbol(symbol, listed):
            continue
        underlying = row.get("underlyingType")
        if underlying is None:
            missing.append(symbol)
        elif underlying != "COIN":
            not_coin.append(symbol)
            continue
        selected.append(symbol)
    return selected, {"missing_underlying": missing, "not_coin": not_coin}


def get_top_symbols(n=None):
    """24 saatlik quoteVolume'a göre en yüksek n perpetual USDT sembolü.

    Dönüş biçimi spot ile aynı: [{"symbol": "BTCUSDT", "quoteVolume": 123.0}, ...].
    """
    if n is None:
        n = config.CRYPTO_TOP_DEFAULT
    n = int(n)
    if n < 1:
        raise ValueError("n pozitif tam sayı olmalı")
    allowed, info = parse_exchange_info(request_json(config.BINANCE_FUTURES_EXCHANGE_INFO_PATH))
    if info["missing_underlying"]:
        utils.log_file_only("futures: underlyingType alanı olmayan {} sembol dahil edildi: {}".format(
            len(info["missing_underlying"]), ",".join(info["missing_underlying"][:10])))
    ticker = request_json(config.BINANCE_FUTURES_TICKER_24HR_PATH)
    if not isinstance(ticker, list):
        raise FuturesAPIError("24 saatlik ticker yanıtı liste biçiminde değil")
    return rank_by_volume(ticker, set(allowed))[:n]


def rank_by_volume(ticker_rows, allowed):
    rows = []
    for item in ticker_rows:
        if not isinstance(item, dict) or item.get("symbol") not in allowed:
            continue
        try:
            volume = float(item["quoteVolume"])
        except (KeyError, TypeError, ValueError):
            continue
        if volume >= 0:
            rows.append({"symbol": item["symbol"], "quoteVolume": volume})
    rows.sort(key=lambda row: (-row["quoteVolume"], row["symbol"]))
    return rows


def get_klines(symbol, interval, limit):
    """Spot ile aynı sonuç biçimi: candles (kapanmış), last_candle, last_candle_closed."""
    symbol = str(symbol).upper()
    limit = int(limit)
    if not symbol or limit < 1:
        raise ValueError("symbol boş olamaz ve limit pozitif olmalı")
    payload = request_json(config.BINANCE_FUTURES_KLINES_PATH,
                           {"symbol": symbol, "interval": str(interval), "limit": limit})
    if not isinstance(payload, list):
        raise FuturesAPIError("Kline yanıtı liste biçiminde değil")
    return data_binance.parse_klines(payload)
