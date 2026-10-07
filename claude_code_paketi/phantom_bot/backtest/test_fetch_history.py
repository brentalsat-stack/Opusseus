"""fetch_history testleri — sahte fapi yanıtlarıyla, ağ gerekmez."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import fetch_history as fh  # noqa: E402

START = 1_700_000_000 - (1_700_000_000 % 86400)  # gün sınırı


class FakeFapi:
    """Belirli bir sembol için 5m/1h kline ve funding üreten sahte uç nokta."""

    def __init__(self, count_5m=3500, funding_count=2500):
        self.requests = []
        self.count_5m = count_5m
        self.funding_count = funding_count

    def __call__(self, path, params):
        self.requests.append((path, dict(params)))
        headers = {"x-mbx-used-weight-1m": "10"}
        if path == config.BINANCE_FUTURES_KLINES_PATH:
            step = fh.INTERVAL_SECONDS[params["interval"]] * 1000
            first = START * 1000
            rows = []
            index = max(0, -(-(params["startTime"] - first) // step))
            while len(rows) < params["limit"]:
                open_ms = first + index * step
                if open_ms > params["endTime"] or index >= self.count_5m:
                    break
                rows.append([open_ms, "10", "12", "9", "11", "100", open_ms + step - 1, "0", 1, "0", "0", "0"])
                index += 1
            return rows, headers
        assert path == config.BINANCE_FUTURES_FUNDING_PATH
        rows = []
        first = START * 1000
        step = 8 * 3600 * 1000
        index = max(0, -(-(params["startTime"] - first) // step))
        while len(rows) < params["limit"] and index < self.funding_count:
            time_ms = first + index * step
            if time_ms > params["endTime"]:
                break
            rows.append({"symbol": params["symbol"], "fundingTime": time_ms, "fundingRate": "0.00010000",
                         "markPrice": "100.0"})
            index += 1
        return rows, headers


def main():
    import time
    real_sleep = time.sleep
    time.sleep = lambda seconds: None
    try:
        run()
    finally:
        time.sleep = real_sleep
    print("test_fetch_history: OK")


def run():
    root = tempfile.mkdtemp(prefix="bt_fetch_")
    step = 300
    end_s = START + 3500 * step  # tüm mumlar kapanmış sayılsın
    now_ms = (end_s + 10) * 1000

    # 1) Sayfalama: 3500 mum, 1500'lük sayfalarla 3 istek; çıktı eskiden yeniye, tekrarsız.
    api = FakeFapi()
    rows = fh.fetch_klines_range("BTCUSDT", "5m", START, end_s, request=api, now_ms=now_ms)
    assert len(rows) == 3500 and [r[0] for r in rows] == sorted({r[0] for r in rows}), len(rows)
    assert len(api.requests) == 3 and all(p["limit"] == 1500 for _, p in api.requests)
    assert rows[0] == (START, 10.0, 12.0, 9.0, 11.0, 100.0)
    print("Kline sayfalama (1500): GEÇTİ")

    # 2) Kapanmamış son mum dışarıda kalır (kapanış zamanı now'dan sonra).
    api = FakeFapi(count_5m=10)
    rows = fh.fetch_klines_range("BTCUSDT", "5m", START, START + 10 * step, request=api,
                                 now_ms=(START + 9 * step + 100) * 1000)
    assert len(rows) == 9 and rows[-1][0] == START + 8 * step, [r[0] - START for r in rows]
    print("Açık mum indirilmiyor: GEÇTİ")

    # 3) Önbellek: ilk çalıştırma indirir, ikinci çalıştırma istek atmaz, genişleyen aralık yalnızca eksik kısmı indirir.
    api = FakeFapi()
    all_rows, fetched = fh.update_klines("BTCUSDT", "5m", START, START + 2000 * step, data_dir=root,
                                         request=api, now_ms=now_ms)
    assert fetched == 2000 and len(all_rows) == 2000
    first_requests = len(api.requests)
    rows_again, fetched = fh.update_klines("BTCUSDT", "5m", START, START + 2000 * step, data_dir=root,
                                           request=api, now_ms=now_ms)
    assert fetched == 0 and len(api.requests) == first_requests and rows_again == all_rows
    rows_more, fetched = fh.update_klines("BTCUSDT", "5m", START, START + 3000 * step, data_dir=root,
                                          request=api, now_ms=now_ms)
    assert fetched == 1000 and len(rows_more) == 3000, fetched
    new_requests = api.requests[first_requests:]
    assert len(new_requests) == 1 and new_requests[0][1]["startTime"] == (START + 2000 * step) * 1000, new_requests
    # Geriye (ısınma) genişleme: yalnızca önceki kısım indirilir.
    api2 = FakeFapi()
    prefix_dir = tempfile.mkdtemp(prefix="bt_fetch_")
    fh.update_klines("ETHUSDT", "5m", START + 1000 * step, START + 2000 * step, data_dir=prefix_dir,
                     request=api2, now_ms=now_ms)
    before = len(api2.requests)
    rows_back, fetched = fh.update_klines("ETHUSDT", "5m", START, START + 2000 * step, data_dir=prefix_dir,
                                          request=api2, now_ms=now_ms)
    assert fetched == 1000 and rows_back[0][0] == START and len(rows_back) == 2000
    assert api2.requests[before][1]["endTime"] == (START + 1000 * step) * 1000 - 1
    # CSV gidiş-dönüş
    assert fh.read_klines(fh.kline_path("BTCUSDT", "5m", root)) == rows_more
    print("CSV önbelleği: yalnızca eksik kısım indiriliyor (ileri/geri): GEÇTİ")

    # 4) Funding: 2500 kayıt → 3 sayfa; parse; artımlı güncelleme.
    api = FakeFapi()
    funding_dir = tempfile.mkdtemp(prefix="bt_fetch_")
    end_funding = START + 2500 * 8 * 3600 + 1
    rows, fetched = fh.update_funding("BTCUSDT", START, end_funding, data_dir=funding_dir, request=api)
    assert fetched == 2500 and rows[0] == (START, 0.0001) and len(api.requests) == 3, (fetched, len(api.requests))
    again, fetched = fh.update_funding("BTCUSDT", START, end_funding, data_dir=funding_dir, request=api)
    assert fetched == 0 and again == rows
    assert fh.parse_funding([{"fundingTime": 8000, "fundingRate": "-0.0002", "x": 1}, {"bozuk": 1}]) == [(8, -0.0002)]
    try:
        fh.parse_funding({"code": -1})
        raise AssertionError("şemasız funding reddedilmeliydi")
    except fh.data_futures.FuturesAPIError:
        pass
    print("Funding sayfalama/ayrıştırma/önbellek: GEÇTİ")

    # 5) Şema günlüğü yalnızca alan adı yazar, değer yazmaz; uç nokta başına bir kez, limit kadar.
    schema = fh.SchemaLog(limit=2)
    api = FakeFapi(count_5m=5, funding_count=3)
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        fh.fetch_klines_range("BTCUSDT", "5m", START, START + 5 * step, request=api, schema=schema,
                              now_ms=now_ms)
        fh.fetch_klines_range("BTCUSDT", "5m", START, START + 5 * step, request=api, schema=schema,
                              now_ms=now_ms)
        fh.fetch_funding_range("BTCUSDT", START, START + 3 * 8 * 3600, request=api, schema=schema)
        schema.record("exchangeInfo", {"symbols": [{"symbol": "X"}]})  # limit doldu → yok sayılır
    assert len(schema.lines) == 2, schema.lines
    assert "list of list, sütun sayısı=12" in schema.lines[0]
    assert "fundingRate" in schema.lines[1] and "fundingTime" in schema.lines[1] and "markPrice" in schema.lines[1]
    assert "100.0" not in " ".join(schema.lines) and "0.0001" not in " ".join(schema.lines)
    assert "symbols[0] keys=symbol" in fh.schema_of({"symbols": [{"symbol": "X", "v": 1}], "timezone": "UTC"})
    print("Şema günlüğü yalnız alan adları: GEÇTİ")

    # 6) fetch_all: ilerleme çıktısı, eksik mum sayımı, sembol/TF özeti.
    api = FakeFapi(count_5m=4000, funding_count=100)
    lines = []
    all_dir = tempfile.mkdtemp(prefix="bt_fetch_")
    saved = dict(config.BT_WARMUP_DAYS)
    config.BT_WARMUP_DAYS.update({"1d": 0, "4h": 0, "1h": 0, "15m": 0, "5m": 0})
    try:
        summary = fh.fetch_all(["BTCUSDT"], 3, end_s=START + 3 * 86400, data_dir=all_dir, request=api,
                               now_ms=(START + 3 * 86400 + 60) * 1000, print_fn=lines.append)
    finally:
        config.BT_WARMUP_DAYS.update(saved)
    assert summary["BTCUSDT"]["5m"] == 3 * 288 and summary["BTCUSDT"]["1d"] == 3, summary
    assert any("[1/1] BTCUSDT 5m OK" in line for line in lines) and any("funding OK" in line for line in lines)
    assert fh.count_gaps([(0, 1, 1, 1, 1, 1), (900, 1, 1, 1, 1, 1)], "5m") == 2
    # İstenenden kısa geçmiş: uyarı yazılır, hata verilmez
    short_lines = []
    config.BT_WARMUP_DAYS.update({"1d": 0, "4h": 0, "1h": 0, "15m": 0, "5m": 0})
    try:
        fh.fetch_all(["SHORTUSDT"], 10, end_s=START + 3 * 86400, data_dir=tempfile.mkdtemp(prefix="bt_fetch_"),
                     request=FakeFapi(count_5m=4000, funding_count=100), now_ms=(START + 3 * 86400 + 60) * 1000,
                     print_fn=short_lines.append)
    finally:
        config.BT_WARMUP_DAYS.update(saved)
    assert any("UYARI: SHORTUSDT 5m geçmişi istenenden kısa" in line for line in short_lines), short_lines
    print("fetch_all ilerleme çıktısı ve özet: GEÇTİ")


if __name__ == "__main__":
    main()
