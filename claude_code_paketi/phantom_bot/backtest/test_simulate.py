"""simulate testleri: dolum/iptal kuralları, aynı-mum stop önceliği, maliyet/funding hesabı, look-ahead yok."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bt_synth  # noqa: E402
import config  # noqa: E402
import fetch_history  # noqa: E402
import replay  # noqa: E402
import simulate  # noqa: E402
import test_replay  # noqa: E402

T0 = 1_700_000_000 - (1_700_000_000 % 300)


def bars(spec):
    """[(open, high, low, close), ...] → 5m satırları ve zaman listesi."""
    rows = [(T0 + i * 300, o, h, low, c, 1.0) for i, (o, h, low, c) in enumerate(spec)]
    return rows, [r[0] for r in rows]


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_resolve_order():
    # Long: giriş 100, TP2 110, distal 98.
    rows, times = bars([(105, 106, 103, 104), (104, 105, 101, 102), (102, 102.5, 99.5, 100.5)])
    assert simulate.resolve_order(rows, times, T0, "BULLISH", 100, 97, 110, 98, T0 + 99999)[0] == "FILLED"
    status, index = simulate.resolve_order(rows, times, T0, "BULLISH", 99, 97, 110, 98, T0 + 99999)
    assert status == "PENDING_END" and index == 2
    # TP2'ye dolmadan ulaşıldı → iptal
    rows, times = bars([(105, 111, 103, 104), (104, 105, 99, 100)])
    assert simulate.resolve_order(rows, times, T0, "BULLISH", 100, 97, 110, 98, T0 + 99999) == ("CANCEL_TP2", 0)
    # distal ötesinde gövde kapanışı (dolum yok: giriş 99'un altında kalmadı)
    rows, times = bars([(102, 103, 101.5, 102), (102, 103, 101.2, 101.5)])
    assert simulate.resolve_order(rows, times, T0, "BULLISH", 100, 97, 110, 101.8, T0 + 99999) == ("CANCEL_INVALID", 1)
    # süre dolumu
    rows, times = bars([(105, 106, 103, 104)] * 4)
    assert simulate.resolve_order(rows, times, T0, "BULLISH", 100, 97, 110, 98, T0 + 600) == ("EXPIRED", 2)
    # Aynı mumda hem dolum hem TP2 → dolum öncelikli
    rows, times = bars([(105, 111, 99, 104)])
    assert simulate.resolve_order(rows, times, T0, "BULLISH", 100, 97, 110, 98, T0 + 9999)[0] == "FILLED"
    # Short: giriş 100 (high ≥ giriş), TP2 90
    rows, times = bars([(95, 96, 94, 95), (95, 100.2, 94, 99)])
    assert simulate.resolve_order(rows, times, T0, "BEARISH", 100, 103, 90, 102, T0 + 9999) == ("FILLED", 1)
    rows, times = bars([(95, 96, 89, 95)])
    assert simulate.resolve_order(rows, times, T0, "BEARISH", 100, 103, 90, 102, T0 + 9999)[0] == "CANCEL_TP2"
    print("Emir dolumu/iptal/süre (alış-satış, dolum önceliği): GEÇTİ")


def legs_for(spec, variant="TP2", direction="BULLISH", entry=100, stop=99, tp1=102, tp2=104, max_hold=10 ** 9):
    rows, _ = bars(spec)
    return simulate.manage_position(rows, 0, direction, entry, stop, tp1, tp2, variant, max_hold)


def test_manage_position():
    # Dolum mumunda hedef görünse bile sayılmaz; yalnızca stop (aynı mumda stop → STOP).
    legs = legs_for([(100, 105, 98.5, 101), (101, 105, 100, 104)])
    assert [(l[2], l[1]) for l in legs] == [("STOP", 99)], legs
    legs = legs_for([(100, 105, 99.5, 101), (101, 105, 100, 104)])
    assert [(l[2], l[1]) for l in legs] == [("TP", 104)], legs
    # Aynı mumda stop ve TP2 → STOP
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 105, 98.5, 102)])
    assert [(l[2], l[1]) for l in legs] == [("STOP", 99)], legs
    # Varyant B: TP1 sonra TP2
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 102.5, 100.2, 102), (102, 104.5, 101, 104)], "TP1BE")
    assert [(l[0], l[1], l[2]) for l in legs] == [(0.5, 102, "TP"), (0.5, 104, "TP")], legs
    # Varyant B: TP1 sonra BE
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 102.5, 100.2, 102), (102, 102.2, 99.8, 100)], "TP1BE")
    assert [(l[0], l[1], l[2]) for l in legs] == [(0.5, 102, "TP"), (0.5, 100, "BE")], legs
    # Varyant B: TP1 mumunda orijinal stop de görülürse STOP (tam)
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 102.5, 98.9, 100)], "TP1BE")
    assert [(l[0], l[2]) for l in legs] == [(1.0, "STOP")], legs
    # Varyant B: aynı mumda TP1 ve TP2 (stop yok) → ikisi de
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 105, 100.2, 104.5)], "TP1BE")
    assert [(l[0], l[2]) for l in legs] == [(0.5, "TP"), (0.5, "TP")], legs
    # BE mumunda TP2 de görülürse BE (stop önceliği)
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 102.5, 100.2, 102), (102, 105, 99.9, 103)], "TP1BE")
    assert legs[-1][2] == "BE", legs
    # tp1 yoksa TP1BE = TP2 davranışı
    legs = simulate.manage_position(bars([(100, 101, 99.5, 100.5), (100.5, 105, 100.2, 104.5)])[0],
                                    0, "BULLISH", 100, 99, None, 104, "TP1BE", 10 ** 9)
    assert [(l[0], l[2]) for l in legs] == [(1.0, "TP")]
    # TIMEOUT ve veri sonu
    legs = legs_for([(100, 101, 99.5, 100.5)] + [(100.5, 101, 100, 100.6)] * 5, max_hold=900)
    assert legs[-1][2] == "TIMEOUT" and legs[-1][1] == 100.6
    legs = legs_for([(100, 101, 99.5, 100.5), (100.5, 101, 100, 100.7)])
    assert legs[-1][2] == "TIMEOUT" and legs[-1][1] == 100.7
    # Short simetri
    legs = legs_for([(100, 100.5, 99.5, 99.8), (99.8, 100.2, 95, 96)], direction="BEARISH", entry=100, stop=101,
                    tp1=98, tp2=96)
    assert [(l[2], l[1]) for l in legs] == [("TP", 96)], legs
    legs = legs_for([(100, 100.5, 99.5, 99.8), (99.8, 101.5, 95, 96)], direction="BEARISH", entry=100, stop=101,
                    tp1=98, tp2=96)
    assert [(l[2], l[1]) for l in legs] == [("STOP", 101)], legs
    print("Pozisyon yönetimi (stop önceliği, TP1/BE, TIMEOUT, short): GEÇTİ")


def test_costs():
    p = {"maker": 0.0002, "taker": 0.0005, "slip": 0.0002, "max_hold": 10 ** 9}
    entry, stop = 100.0, 99.0
    # TP2 kazancı (long): brüt +3; ücret = 0.02 (giriş) + 0.0206 (TP maker); funding 1 kez 0.0001 → long öder 0.01
    funding = [(T0 + 900, 0.0001)]
    legs = [(1.0, 103.0, "TP", T0 + 1800)]
    r = simulate.trade_result("BULLISH", entry, stop, legs, T0, funding, p)
    assert approx(r["r_gross"], 3.0) and approx(r["slip_r"], 0.0)
    assert approx(r["fee_r"], 0.02 + 0.0206) and approx(r["funding_r"], 0.01), r
    assert approx(r["r_net"], 3.0 - 0.0406 - 0.01) and r["exit_reason"] == "TP2"
    # STOP kaybı: kayma 99*0.0002/1 = 0.0198; taker 0.0005*98.9802; giriş 0.02
    r = simulate.trade_result("BULLISH", entry, stop, [(1.0, 99.0, "STOP", T0 + 600)], T0, [], p)
    assert approx(r["r_gross"], -1.0) and approx(r["slip_r"], 0.0198)
    assert approx(r["fee_r"], 0.02 + 0.0005 * 98.9802) and approx(r["r_net"], -1 - 0.0198 - 0.02 - 0.0005 * 98.9802)
    assert r["exit_reason"] == "STOP"
    # Short: funding pozitifken short ALIR (maliyet negatif); kayma fiyatı yukarı iter
    r = simulate.trade_result("BEARISH", 100.0, 101.0, [(1.0, 98.0, "TP", T0 + 1800)], T0, funding, p)
    assert approx(r["r_gross"], 2.0) and approx(r["funding_r"], -0.01), r
    r = simulate.trade_result("BEARISH", 100.0, 101.0, [(1.0, 101.0, "STOP", T0 + 600)], T0, [], p)
    assert approx(r["slip_r"], 101 * 0.0002) and approx(r["r_gross"], -1.0)
    # Varyant B: yarım TP1 (maker), yarım BE (taker+kayma); funding açık orana göre: önce 1.0 sonra 0.5
    funding = [(T0 + 400, 0.0001), (T0 + 1000, 0.0001)]
    legs = [(0.5, 102.0, "TP", T0 + 600), (0.5, 100.0, "BE", T0 + 1500)]
    r = simulate.trade_result("BULLISH", entry, stop, legs, T0, funding, p)
    assert approx(r["r_gross"], 0.5 * 2.0 + 0.0) and r["exit_reason"] == "TP1_BE"
    assert approx(r["funding_r"], 0.0001 * 1.0 * 100 + 0.0001 * 0.5 * 100), r
    assert approx(r["slip_r"], 0.5 * 100 * 0.0002)
    # Funding yalnızca pozisyon açıkken (dolumdan sonra, çıkıştan önce): dışarıdakiler sayılmaz
    r = simulate.trade_result("BULLISH", entry, stop, [(1.0, 103.0, "TP", T0 + 1800)], T0 + 300,
                              [(T0 + 300, 0.01), (T0 + 600, 0.0001), (T0 + 1800, 0.0001), (T0 + 2100, 0.01)], p)
    assert approx(r["funding_r"], 0.0001 * 100 * 2), r
    print("Maliyet/funding hesabı (maker/taker/kayma, long/short, kısmi): GEÇTİ")


def test_simulate_risk_end_to_end():
    series = {tf: [] for tf in fetch_history.TIMEFRAMES}
    rows, _ = bars([(103.5, 103.8, 103, 103.2)] * 3 + [(103.2, 103.5, 99.5, 100.5), (100.5, 101, 100, 100.8),
                                                 (100.8, 104.5, 100.5, 104.2), (104, 105, 103, 104)])
    series["5m"] = rows
    for tf in ("15m", "1h", "4h", "1d"):
        series[tf] = rows[:1]
    funding = [(T0 + 1200, 0.0001)]
    data = replay.SymbolData("TESTUSDT", series, funding)
    record = {"symbol": "TESTUSDT", "key": ["TESTUSDT", "BULLISH", "1h", 100.5, 98.0], "direction": "BULLISH",
              "poi_tf": "1h", "grade": "B", "score": 65, "first_seen_t": T0, "poi_distal": 98.0,
              "poi_proximal": 100.5, "poi_eq": 99.25, "market": "crypto",
              "risk": {"t": T0, "entry": 100.0, "stop": 99.0, "tp1": 102.0, "tp2": 104.0}}
    result = simulate.simulate_risk(record, data, simulate._params())
    assert result["status"] == "FILLED" and result["fill_t"] == T0 + 3 * 300, result
    assert result["variants"]["TP2"]["exit_reason"] == "TP2"
    assert result["variants"]["TP1BE"]["exit_reason"] == "TP1_TP2"
    assert approx(result["variants"]["TP2"]["r_gross"], 4.0) and result["rr_tp2"] == 4.0
    assert result["variants"]["TP2"]["funding_r"] > 0
    assert simulate.simulate_risk(dict(record, risk=None), data, simulate._params())["status"] == "NO_RISK_LEVELS"
    no_target = dict(record, risk=dict(record["risk"], tp2=None))
    assert simulate.simulate_risk(no_target, data, simulate._params())["status"] == "NO_TARGET"
    print("Risk modu uçtan uca (dolum, iki varyant, NO_TARGET, NO_RISK_LEVELS): GEÇTİ")


def confirmation_fixture():
    series = bt_synth.make_series(2, 60, wave_len=600)
    data = replay.SymbolData("TUSDT", series)
    first_seen = 1702180800
    record = [r for r in replay.replay_symbol("TUSDT", data, first_seen, first_seen, 14400)
              if r["direction"] == "BULLISH" and r["poi_tf"] == "1h"]
    params = simulate._params()
    filled = [r for r in record if simulate.simulate_confirmation(r, data, params)["status"] == "FILLED"]
    assert len(filled) == 1, [simulate.simulate_confirmation(r, data, params)["status"] for r in record]
    return series, data, filled[0]


def test_confirmation_and_lookahead():
    series, data, record = confirmation_fixture()
    params = simulate._params()
    base = simulate.simulate_confirmation(record, data, params)
    assert base["status"] == "FILLED" and base["confirm_status"] == "ENTRY2_READY", base
    assert base["confirm_t"] == 1702188000 and base["entry"] < base["tp2"] and base["stop"] < base["entry"]
    # Teyitten sonraki mumlar değişse bile teyit anı ve seviyeler aynı kalır (look-ahead yok).
    cut = base["confirm_t"]
    changed = {tf: [r if r[0] + fetch_history.INTERVAL_SECONDS[tf] <= cut else
                    (r[0], r[1] * 1.3, r[2] * 1.4, r[3] * 1.2, r[4] * 1.3, r[5]) for r in rows]
               for tf, rows in series.items()}
    other = simulate.simulate_confirmation(record, replay.SymbolData("TUSDT", changed), params)
    for field in ("confirm_t", "confirm_status", "ltf_tf", "entry", "stop", "tp1", "tp2", "order_t"):
        assert other.get(field) == base.get(field), (field, other.get(field), base.get(field))
    # Teyit yokken (dokunuş öncesi) işlem açılmaz: BOS zamanı sonrası dokunuş olmayan kayıt
    far = dict(record, poi_proximal=record["poi_proximal"] * 3, poi_distal=record["poi_distal"] * 3,
               poi_eq=record["poi_eq"] * 3)
    assert simulate.simulate_confirmation(far, data, params)["status"] == "NO_TOUCH"
    # Süreler: teyitten sonra dolum penceresi BT_CONFIRM_FILL_HOURS ile sınırlı
    saved = config.BT_CONFIRM_FILL_HOURS
    config.BT_CONFIRM_FILL_HOURS = 0
    try:
        assert simulate.simulate_confirmation(record, data, simulate._params())["status"] == "EXPIRED"
    finally:
        config.BT_CONFIRM_FILL_HOURS = saved
    print("Confirmation: teyit anı/seviyeler look-ahead'siz, NO_TOUCH, dolum süresi: GEÇTİ")


def test_dedupe_and_determinism():
    data_dir = tempfile.mkdtemp(prefix="bt_sim_")
    series = bt_synth.make_series(2, 60, wave_len=600)
    test_replay.write_csvs("TUSDT", series, data_dir)
    data = replay.SymbolData.load("TUSDT", data_dir)
    first_seen = 1702180800
    records = replay.replay_symbol("TUSDT", data, first_seen, first_seen, 14400)
    again = replay.replay_symbol("TUSDT", data, first_seen, first_seen + 14400, 14400)
    keys = [tuple(r["key"]) for r in again]
    assert len(keys) == len(set(keys)) and {tuple(r["key"]) for r in records} <= set(keys)
    serial = simulate.simulate_all(records, ["TUSDT"], data_dir, workers=1, print_fn=lambda m: None)
    assert serial and {t["mode"] for t in serial} == {"risk", "confirmation"}
    assert len(serial) == 2 * len(records)
    sym2 = [dict(r, symbol="UUUUSDT") for r in records]
    test_replay.write_csvs("UUUUSDT", series, data_dir)
    parallel = simulate.simulate_all(records + sym2, ["TUSDT", "UUUUSDT"], data_dir, workers=2, print_fn=lambda m: None)
    serial2 = simulate.simulate_all(records + sym2, ["TUSDT", "UUUUSDT"], data_dir, workers=1, print_fn=lambda m: None)
    dump = lambda rows: json.dumps(rows, sort_keys=True, default=str)  # noqa: E731
    assert dump(parallel) == dump(serial2)
    print("simulate_all: seri == çok süreçli, deterministik sıra: GEÇTİ")


def main():
    test_resolve_order()
    test_manage_position()
    test_costs()
    test_simulate_risk_end_to_end()
    test_confirmation_and_lookahead()
    test_dedupe_and_determinism()
    print("test_simulate: OK")


if __name__ == "__main__":
    main()
