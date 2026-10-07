"""replay testleri — sentetik, hizalı çok-zaman-dilimli veriyle."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bt_synth  # noqa: E402
import config  # noqa: E402
import fetch_history  # noqa: E402
import phantom_scan  # noqa: E402
import replay  # noqa: E402
import utils  # noqa: E402

DAYS = 40
STEP = 12 * 3600


def write_csvs(symbol, series, data_dir):
    for tf, rows in series.items():
        fetch_history._write_csv(fetch_history.kline_path(symbol, tf, data_dir), fetch_history.KLINE_HEADER, rows)
    fetch_history._write_csv(fetch_history.funding_path(symbol, data_dir), fetch_history.FUNDING_HEADER,
                             [(bt_synth.START + i * 28800, 0.0001) for i in range(DAYS * 3)])


def window(series):
    t_end = series["5m"][-1][0] + 300
    t_start = ((t_end - 6 * 86400) // STEP) * STEP
    return t_start, t_end


def test_series_at():
    series = bt_synth.make_series(1, DAYS)
    data = replay.SymbolData("TESTUSDT", series)
    t = bt_synth.START + 20 * 86400 + 3 * 3600 + 300 * 5  # 03:25 → 1h mumu 03:00 açık
    view = data.series_at(t)
    assert view["1h"][-1]["t"] == bt_synth.START + 20 * 86400 + 2 * 3600, view["1h"][-1]["t"] - bt_synth.START
    assert view["5m"][-1]["t"] == t - 300 and view["15m"][-1]["t"] == (t // 900) * 900 - 900
    assert all(c["t"] + replay.fetch_history.INTERVAL_SECONDS[tf] <= t for tf, key in
               (("5m", "5m"), ("15m", "15m"), ("1h", "1h"), ("4h", "4h"), ("1d", "1day")) for c in view[key])
    assert len(view["5m"]) == 500 and view["1h_last"]["t"] == bt_synth.START + 20 * 86400 + 3 * 3600
    assert view["1h_last"]["c"] == view["5m"][-1]["c"]
    # t tam bir 1h sınırındaysa o saatlik mum (açılış t-3600) kapanmıştır; bir saniye önce kapanmamıştır.
    boundary = bt_synth.START + 21 * 86400 + 4 * 3600
    assert data.closed("1h", boundary)[-1]["t"] == boundary - 3600
    assert data.closed("1h", boundary - 1)[-1]["t"] == boundary - 7200
    print("series_at yalnızca kapanmış mumlar; güncel fiyat son 5m kapanışı: GEÇTİ")


def test_no_lookahead():
    series = bt_synth.make_series(2, DAYS)
    t_start, t_end = window(series)
    cut = t_start + 8 * STEP
    base = replay.replay_symbol("TESTUSDT", replay.SymbolData("TESTUSDT", series), t_start, cut, STEP)
    changed = {tf: [r if r[0] + replay.fetch_history.INTERVAL_SECONDS[tf] <= cut else
                    (r[0], r[1] * 3, r[2] * 3.5, r[3] * 2.5, r[4] * 3, r[5]) for r in rows]
               for tf, rows in series.items()}
    assert changed["5m"] != series["5m"]
    altered = replay.replay_symbol("TESTUSDT", replay.SymbolData("TESTUSDT", changed), t_start, cut, STEP)
    assert base and json.dumps(base, sort_keys=True, default=str) == json.dumps(altered, sort_keys=True, default=str)
    print("Look-ahead yok: t sonrası mumlar sonucu değiştirmiyor: GEÇTİ")


def test_dedupe_and_first_seen():
    series = bt_synth.make_series(2, DAYS)
    data = replay.SymbolData("TESTUSDT", series)
    t_start, t_end = window(series)
    records = replay.replay_symbol("TESTUSDT", data, t_start, t_end, STEP)
    keys = [tuple(r["key"]) for r in records]
    assert records and len(keys) == len(set(keys)), "tekilleştirme çalışmadı"
    assert [r["first_seen_t"] for r in records] == sorted(r["first_seen_t"] for r in records)
    # İlk görüldüğü adımda tek başına taramayla aynı seviyeler.
    for record in records[:3]:
        with replay.replay_environment(record["first_seen_t"], data):
            candidates, _ = phantom_scan._scan_symbol("TESTUSDT", "crypto", False, lambda *a: None)
        match = [c for c in candidates if replay.setup_key(dict(c, symbol="TESTUSDT")) == tuple(record["key"])]
        assert len(match) == 1
        for field in ("entry", "stop", "tp2", "score"):
            assert match[0][field] == record[field], (field, match[0][field], record[field])
        assert record["ctx"]["irl"] is not None and record["market"] == "crypto"
    print("Tekilleştirme ve ilk görülme seviyeleri: GEÇTİ ({} setup)".format(len(records)))


def test_environment_restored():
    series = bt_synth.make_series(3, DAYS)
    data = replay.SymbolData("TESTUSDT", series)
    before = (phantom_scan._load_symbol_data, utils.now_utc, utils.log_file_only, config.NEWS_CSV)
    with replay.replay_environment(window(series)[0], data):
        assert not os.path.isfile(config.NEWS_CSV) and utils.now_utc().timestamp() == window(series)[0]
    after = (phantom_scan._load_symbol_data, utils.now_utc, utils.log_file_only, config.NEWS_CSV)
    assert before == after
    try:
        replay.SymbolData.load("YOKUSDT", tempfile.mkdtemp())
        raise AssertionError("eksik veri hata vermeliydi")
    except RuntimeError as exc:
        assert "YOKUSDT" in str(exc)
    print("Replay ortamı geri yüklenir; eksik veri net hata: GEÇTİ")


def test_replay_all_deterministic_and_cached():
    data_dir = tempfile.mkdtemp(prefix="bt_replay_")
    results_dir = tempfile.mkdtemp(prefix="bt_results_")
    symbols = ["AAAUSDT", "BBBUSDT"]
    for index, symbol in enumerate(symbols):
        write_csvs(symbol, bt_synth.make_series(10 + index, DAYS), data_dir)
    series = bt_synth.make_series(10, DAYS)
    t_start, t_end = window(series)
    messages = []
    serial, win = replay.replay_all(symbols, data_dir, 6, 12, workers=1, results_dir=results_dir,
                                    print_fn=messages.append, t_window=(t_start, t_end, STEP))
    cached, _ = replay.replay_all(symbols, data_dir, 6, 12, workers=1, results_dir=results_dir,
                                  print_fn=messages.append, t_window=(t_start, t_end, STEP))
    assert any("önbellekten" in m for m in messages)
    other_dir = tempfile.mkdtemp(prefix="bt_results_")
    parallel, _ = replay.replay_all(symbols, data_dir, 6, 12, workers=2, results_dir=other_dir,
                                    print_fn=messages.append, t_window=(t_start, t_end, STEP))
    dump = lambda rows: json.dumps(rows, sort_keys=True, default=str)  # noqa: E731
    assert serial and dump(serial) == dump(cached) == dump(parallel)
    assert {r["symbol"] for r in serial} <= set(symbols)
    assert [(r["first_seen_t"], r["symbol"]) for r in serial] == sorted((r["first_seen_t"], r["symbol"]) for r in serial)
    print("replay_all: seri == önbellek == çok süreçli (deterministik sıra): GEÇTİ")


def test_effective_start_for_short_history():
    series = bt_synth.make_series(4, DAYS)
    late = {tf: [r for r in rows if r[0] >= bt_synth.START + 20 * 86400] for tf, rows in series.items()}
    data = replay.SymbolData("KISAUSDT", late)
    t_start = bt_synth.START + 10 * 86400
    effective = replay.effective_start(data, t_start, STEP)
    assert effective > t_start and (effective - t_start) % STEP == 0
    earliest = max(data.times[tf][0] + replay.fetch_history.INTERVAL_SECONDS[tf] for tf in data.times)
    assert effective >= earliest and effective - STEP < earliest
    full = replay.SymbolData("TAMUSDT", series)
    assert replay.effective_start(full, bt_synth.START + 30 * 86400, STEP) == bt_synth.START + 30 * 86400
    # Kısa geçmişli sembol hata vermeden çalışır ve uyarı yazar
    import contextlib, io
    data_dir = tempfile.mkdtemp(prefix="bt_short_")
    write_csvs("KISAUSDT", late, data_dir)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        symbol, records = replay.replay_worker({"symbol": "KISAUSDT", "data_dir": data_dir, "t_start": t_start,
                                                "t_end": t_start + 12 * 86400, "step_s": STEP})
    assert symbol == "KISAUSDT" and "UYARI: KISAUSDT" in buffer.getvalue()
    assert all(r["first_seen_t"] >= effective for r in records)
    print("Kısa geçmişli sembolde replay erken adımları atlıyor ve uyarıyor: GEÇTİ")


def main():
    test_series_at()
    test_effective_start_for_short_history()
    test_no_lookahead()
    test_dedupe_and_first_seen()
    test_environment_restored()
    test_replay_all_deterministic_and_cached()
    print("test_replay: OK")


if __name__ == "__main__":
    main()
