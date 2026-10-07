"""run_backtest uçtan uca testi: sahte fapi + sentetik veri (ağ gerekmez)."""
import io
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bt_synth  # noqa: E402
import config  # noqa: E402
import data_futures  # noqa: E402
import fetch_history  # noqa: E402
import run_backtest  # noqa: E402

DAYS_OF_DATA = 14
END_TS = bt_synth.START + DAYS_OF_DATA * 86400


class FakeFapi:
    """Sentetik serilerden kline/funding/exchangeInfo sunan sahte fapi."""

    def __init__(self):
        self.series = {}
        self.requests = []

    def data_for(self, symbol):
        if symbol not in self.series:
            self.series[symbol] = bt_synth.make_series(sum(map(ord, symbol)) % 7, DAYS_OF_DATA, wave_len=600)
        return self.series[symbol]

    def __call__(self, path, params):
        self.requests.append(path)
        headers = {"x-mbx-used-weight-1m": "5"}
        if path == config.BINANCE_FUTURES_EXCHANGE_INFO_PATH:
            return {"timezone": "UTC", "symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                                                    "quoteAsset": "USDT", "underlyingType": "COIN"}]}, headers
        if path == config.BINANCE_FUTURES_FUNDING_PATH:
            rows = [{"symbol": params["symbol"], "fundingTime": (bt_synth.START + i * 28800) * 1000,
                     "fundingRate": "0.00010000", "markPrice": "100"} for i in range(DAYS_OF_DATA * 3)
                    if params["startTime"] <= (bt_synth.START + i * 28800) * 1000 <= params["endTime"]]
            return rows[:params["limit"]], headers
        assert path == config.BINANCE_FUTURES_KLINES_PATH
        step = fetch_history.INTERVAL_SECONDS[params["interval"]]
        rows = [r for r in self.data_for(params["symbol"])[params["interval"]]
                if params["startTime"] <= r[0] * 1000 <= params["endTime"]][:params["limit"]]
        return [[r[0] * 1000, str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5]), (r[0] + step) * 1000 - 1,
                 "0", 1, "0", "0", "0"] for r in rows], headers


def main():
    real_sleep = time.sleep
    time.sleep = lambda seconds: None
    saved_warmup = dict(config.BT_WARMUP_DAYS)
    config.BT_WARMUP_DAYS.update({"1d": 8, "4h": 6, "1h": 4, "15m": 3, "5m": 2})
    try:
        run()
    finally:
        time.sleep = real_sleep
        config.BT_WARMUP_DAYS.update(saved_warmup)
    print("test_run_backtest: OK")


def run():
    root = tempfile.mkdtemp(prefix="bt_run_")
    data_dir, results_dir = os.path.join(root, "data"), os.path.join(root, "results")
    api = FakeFapi()
    lines = []
    argv = ["--days", "5", "--step", "12", "--symbols", "BTCUSDT,ETHUSDT", "--workers", "1", "--end-ts", str(END_TS),
            "--data-dir", data_dir, "--results-dir", results_dir]
    code = run_backtest.main(argv, request=api, print_fn=lines.append)
    assert code == 0, lines[-5:]
    text = "\n".join(lines)
    for phase in ("1/4 Veri indirme", "2/4 Replay", "3/4 Simülasyon", "4/4 Rapor", "BTCUSDT 5m OK"):
        assert phase in text, phase
    reports = [f for f in os.listdir(results_dir) if f.startswith("bt_")]
    assert any(f.endswith(".md") and f.startswith("bt_report_") for f in reports)
    assert any(f.startswith("bt_trades_") for f in reports) and any(f.startswith("bt_summary_") for f in reports)
    first_requests = len(api.requests)
    assert first_requests > 0
    # Pencere etiketi: dosya adları ve replay önbellek klasörü --days'e göre ayrılır (d5).
    assert any(f.startswith("bt_report_d5_") and f.endswith(".md") for f in reports)
    assert any(f.startswith("bt_hypotheses_d5_") for f in reports) and "bt_latest_d5.md" in reports
    replay_dir = os.path.join(results_dir, "replay_d5")
    assert os.path.isdir(replay_dir) and any(f.startswith("replay_") for f in os.listdir(replay_dir))
    before = {f: open(os.path.join(replay_dir, f), "rb").read() for f in os.listdir(replay_dir)}

    # İkinci koşu: veri tamamen önbellekte → yeni kline isteği yok; replay önbellekten.
    lines2 = []
    code = run_backtest.main(argv, request=api, print_fn=lines2.append)
    assert code == 0 and len(api.requests) == first_requests, (len(api.requests), first_requests)
    assert any("önbellekten" in line for line in lines2)
    print("Uçtan uca koşu + önbellek yeniden kullanımı: GEÇTİ")

    # Farklı pencere (--days 4) aynı klasörleri kullansa da d5 sonuçlarını ezmez; kendi etiketini alır.
    lines4 = []
    code = run_backtest.main(["--days", "4", "--step", "12", "--symbols", "BTCUSDT,ETHUSDT", "--workers", "1",
                              "--end-ts", str(END_TS), "--data-dir", data_dir, "--results-dir", results_dir],
                             request=api, print_fn=lines4.append)
    assert code == 0
    assert os.path.isdir(os.path.join(results_dir, "replay_d4")) and "bt_latest_d4.md" in os.listdir(results_dir)
    after = {f: open(os.path.join(replay_dir, f), "rb").read() for f in os.listdir(replay_dir)}
    assert before == after
    assert "bt_latest_d5.md" in os.listdir(results_dir)
    print("d4/d5 etiketleri ayrı dosya ve önbellek: GEÇTİ")

    # Smoke: şema günlüğü yalnızca alan adları içerir.
    smoke_lines = []
    smoke_results = os.path.join(root, "smoke_results")
    code = run_backtest.main(["--smoke", "--workers", "1", "--end-ts", str(END_TS), "--data-dir",
                              os.path.join(root, "smoke_data"), "--results-dir", smoke_results],
                             request=api, print_fn=smoke_lines.append)
    assert code == 0, smoke_lines[-3:]
    schema_text = open(os.path.join(smoke_results, "schema_log.txt"), encoding="utf-8").read()
    assert schema_text.count("ŞEMA") == 3 and "exchangeInfo" in schema_text and "klines" in schema_text
    assert "symbols[0] keys=" in schema_text and "list of list, sütun sayısı=12" in schema_text
    assert "BTCUSDT" not in schema_text and "0.0001" not in schema_text
    print("--smoke şema günlüğü (yalnız alan adları): GEÇTİ")

    # fapi 451: net hata, çıkış kodu 2, yedek alan adı yok
    def blocked(path, params):
        raise data_futures.FuturesRegionBlocked("Binance futures (fapi) bu konumdan erişime kapalı (HTTP 451).")

    lines3 = []
    code = run_backtest.main(["--symbols", "BTCUSDT", "--days", "5", "--workers", "1", "--data-dir",
                              os.path.join(root, "blocked"), "--results-dir", results_dir],
                             request=blocked, print_fn=lines3.append)
    assert code == 2 and any("451" in line for line in lines3)
    print("HTTP 451 → anlaşılır hata, çıkış kodu 2: GEÇTİ")

    # Argüman doğrulama
    import contextlib
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            run_backtest.parse_args(["--days", "0"])
        raise AssertionError("--days 0 reddedilmeliydi")
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
