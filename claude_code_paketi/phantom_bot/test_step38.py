"""Adım 38: Binance futures (fapi) ayrıştırma — sahte JSON ile, ağ gerekmez."""
import json

import config
import data_futures
import synth

EXCHANGE_INFO = {"symbols": [
    {"symbol": "BTCUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "ETHUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "BTCUSDT_261225", "contractType": "CURRENT_QUARTER", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "ETHUSDC", "contractType": "PERPETUAL", "quoteAsset": "USDC", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "OLDUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "SETTLING", "underlyingType": "COIN"},
    {"symbol": "XAUUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COMMODITY"},
    {"symbol": "NOFIELDUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING"},
    {"symbol": "UUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "USDCUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "BTCUPUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "1000PEPEUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
    {"symbol": "SUPERUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING", "underlyingType": "COIN"},
]}
TICKER = [{"symbol": "ETHUSDT", "quoteVolume": "900.5"}, {"symbol": "BTCUSDT", "quoteVolume": "1000"},
          {"symbol": "1000PEPEUSDT", "quoteVolume": "50"}, {"symbol": "NOFIELDUSDT", "quoteVolume": "70"},
          {"symbol": "XAUUSDT", "quoteVolume": "5000"}, {"symbol": "SUPERUSDT", "quoteVolume": "bozuk"},
          {"symbol": "OLDUSDT", "quoteVolume": "9999"}]


def main():
    selected, info = data_futures.parse_exchange_info(EXCHANGE_INFO)
    assert set(selected) == {"BTCUSDT", "ETHUSDT", "NOFIELDUSDT", "1000PEPEUSDT", "SUPERUSDT"}, selected
    assert info["missing_underlying"] == ["NOFIELDUSDT"] and info["not_coin"] == ["XAUUSDT"], info
    ranked = data_futures.rank_by_volume(TICKER, set(selected))
    assert [row["symbol"] for row in ranked] == ["BTCUSDT", "ETHUSDT", "NOFIELDUSDT", "1000PEPEUSDT"], ranked
    try:
        data_futures.parse_exchange_info({"code": -1})
        raise AssertionError("şemasız yanıt reddedilmeliydi")
    except data_futures.FuturesAPIError:
        pass
    print("exchangeInfo filtreleri (PERPETUAL/USDT/TRADING/COIN, alan yoksa atma): GEÇTİ")

    # get_top_symbols ve get_klines: sahte HTTP katmanıyla.
    synth.isolate_dirs()
    calls = []

    def fake(path, params=None, with_headers=False):
        calls.append(path)
        if path == config.BINANCE_FUTURES_EXCHANGE_INFO_PATH:
            return EXCHANGE_INFO
        if path == config.BINANCE_FUTURES_TICKER_24HR_PATH:
            return TICKER
        assert path == config.BINANCE_FUTURES_KLINES_PATH and params["symbol"] == "BTCUSDT"
        return [[1_700_000_000_000 + i * 3_600_000, "10", "11", "9", "10.5", "5", 1_700_000_000_000 + i * 3_600_000 + 3_599_999]
                for i in range(3)] + [[4_000_000_000_000, "10", "11", "9", "10.2", "5", 4_000_003_599_999]]

    original = data_futures.request_json
    data_futures.request_json = fake
    try:
        top = data_futures.get_top_symbols(2)
        assert [row["symbol"] for row in top] == ["BTCUSDT", "ETHUSDT"], top
        result = data_futures.get_klines("btcusdt", "1h", 4)
        assert len(result["candles"]) == 3 and result["last_candle_closed"] is False, result
        assert result["candles"][0] == {"t": 1_700_000_000, "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.5, "v": 5.0}
    finally:
        data_futures.request_json = original
    assert config.BINANCE_FUTURES_BASE_URLS == ["https://fapi.binance.com"]
    assert "binance.vision" not in json.dumps(config.BINANCE_FUTURES_BASE_URLS)
    print("get_top_symbols/get_klines ayrıştırma, yalnızca fapi alan adı: GEÇTİ")
    # HTTP 451: net bölgesel engel hatası, yedek alan adı denenmez, tekrar denenmez.
    import io
    import urllib.error
    import urllib.request
    attempts = []

    def blocked(request, timeout=None):
        attempts.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 451, "blocked", {},
                                     io.BytesIO(b'{"code":0,"msg":"restricted location"}'))

    saved = (urllib.request.urlopen, config.BINANCE_REQUEST_DELAY)
    urllib.request.urlopen, config.BINANCE_REQUEST_DELAY = blocked, 0
    try:
        data_futures.request_json("/fapi/v1/ping")
        raise AssertionError("451 bölgesel engel hatası vermeliydi")
    except data_futures.FuturesRegionBlocked as exc:
        assert "451" in str(exc)
    finally:
        urllib.request.urlopen, config.BINANCE_REQUEST_DELAY = saved
    assert len(attempts) == 1 and attempts[0].startswith("https://fapi.binance.com/"), attempts
    print("HTTP 451 → FuturesRegionBlocked, tek istek: GEÇTİ")
    print("test_step38: OK")


if __name__ == "__main__":
    main()
