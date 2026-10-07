"""Hipotez simülasyonu testleri: minimum stop (a: %0.5, b: 1h ATR) ve sabit 3R hedef."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import fetch_history  # noqa: E402
import indicators  # noqa: E402
import replay  # noqa: E402
import report_bt as rb  # noqa: E402
import simulate  # noqa: E402
import test_simulate as S  # noqa: E402

T0 = S.T0


def make_data(spec, funding=None):
    rows, _ = S.bars(spec)
    series = {tf: rows[:1] for tf in ("15m", "1h", "4h", "1d")}
    series["5m"] = rows
    return replay.SymbolData("TESTUSDT", series, funding or [])


def record(direction="BULLISH", distal=90.0):
    return {"symbol": "TESTUSDT", "key": ["TESTUSDT", direction, "1h", 100.5, distal], "direction": direction,
            "poi_tf": "1h", "grade": "B", "score": 65, "first_seen_t": T0, "poi_distal": distal,
            "poi_proximal": 100.5, "poi_eq": 99.0, "market": "crypto", "score_breakdown": []}


def run(spec, entry=100.0, stop=99.9, tp1=100.5, tp2=103.0, min_stops=None, direction="BULLISH", distal=90.0):
    data = make_data(spec)
    params = simulate._params()
    return simulate._run_order(record(direction, distal), "confirmation", data, T0, entry, stop, tp1, tp2,
                               T0 + 10 ** 6, params, min_stops=min_stops)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_minstop():
    # Dolum (100'e iniş), sonra 99.7'ye sarkma (base stop 99.9 çalışır; %0.5 stop = 99.5 çalışmaz), sonra TP2 (103)
    spec = [(101, 101.5, 100.5, 101), (101, 101, 99.95, 100.3), (100.3, 100.5, 99.7, 100.2),
            (100.2, 101.5, 100.1, 101.2), (101.2, 103.5, 101, 103.2)]
    result = run(spec, min_stops={"minstop_pct": 0.005 * 100.0, "minstop_atr": 0.05})
    assert result["status"] == "FILLED"
    base = result["variants"]["TP2"]
    assert base["exit_reason"] == "STOP" and approx(base["r_gross"], -1.0)
    wide = result["minstop"]["minstop_pct"]
    assert wide["changed"] and approx(wide["stop"], 99.5) and approx(wide["stop_pct"], 0.5)
    assert approx(wide["rr_tp2"], 3.0 / 0.5)
    out = wide["variants"]["TP2"]
    assert out["exit_reason"] == "TP2" and approx(out["r_gross"], 3.0 / 0.5), out
    # maliyet R'si stop genişleyince küçülür (aynı notional ücreti, daha büyük risk mesafesi)
    assert out["fee_r"] < base["fee_r"] and out["slip_r"] < base["slip_r"]
    assert wide["variants"]["TP1BE"]["exit_reason"] in ("TP1_TP2", "TP1_BE")
    # (b) mesafe mevcut stoptan küçükse (0.05 < 0.1): değişmez, ana sonuç yeniden kullanılır
    same = result["minstop"]["minstop_atr"]
    assert not same["changed"] and same["variants"] is result["variants"] and approx(same["stop"], 99.9)
    # Giriş ve hedefler aynı: tp2 / entry sonuçta değişmedi
    assert result["entry"] == 100.0 and result["tp2"] == 103.0
    # Genişleyen stop de aşılırsa kayıp -1R (yeni stopa göre) ve maliyet R'si
    spec2 = [(101, 101.5, 100.5, 101), (101, 101, 99.95, 100.3), (100.3, 100.5, 99.4, 99.6)]
    result2 = run(spec2, min_stops={"minstop_pct": 0.5})
    out2 = result2["minstop"]["minstop_pct"]["variants"]["TP2"]
    assert out2["exit_reason"] == "STOP" and approx(out2["r_gross"], -1.0)
    # Short simetri: stop yukarı genişler
    spec3 = [(99, 99.5, 98.5, 99), (99, 100.05, 99, 99.7), (99.7, 100.2, 99.5, 99.8), (99.8, 99.9, 96.5, 96.8)]
    short = run(spec3, entry=100.0, stop=100.1, tp1=99.0, tp2=97.0, min_stops={"minstop_pct": 0.5},
                direction="BEARISH", distal=110.0)
    assert short["status"] == "FILLED" and approx(short["minstop"]["minstop_pct"]["stop"], 100.5)
    assert short["variants"]["TP2"]["exit_reason"] == "STOP"
    assert short["minstop"]["minstop_pct"]["variants"]["TP2"]["exit_reason"] == "TP2"
    # Dolum mumunda yeni stop de kontrol edilir (dolum mumunda yalnızca stop)
    spec4 = [(101, 101.5, 99.3, 101)]
    wick = run(spec4, min_stops={"minstop_pct": 0.5}, tp2=104.0)
    assert wick["variants"]["TP2"]["exit_reason"] == "STOP" and wick["minstop"]["minstop_pct"]["variants"]["TP2"]["exit_reason"] == "STOP"
    print("Min stop: genişletme, R yeniden hesabı, değişmeyen durum, short, dolum mumu: GEÇTİ")


def test_r3():
    # Long: giriş 100, stop 99 (1R) → 3R hedef 103; TP2 106. Dolum sonrası 103.2'ye çıkar → R3 kazanç 3R (brüt).
    spec = [(101, 101.5, 100.5, 101), (101, 101, 99.9, 100.3), (100.3, 101.5, 100.2, 101), (101, 103.4, 100.8, 103.2)]
    result = run(spec, stop=99.0, tp1=102.0, tp2=106.0)
    r3 = result["r3"]
    assert r3["status"] == "FILLED" and approx(r3["target"], 103.0) and r3["rr_tp2"] == 3.0
    assert r3["outcome"]["exit_reason"] == "R3" and approx(r3["outcome"]["r_gross"], 3.0)
    assert result["variants"]["TP2"]["exit_reason"] == "TIMEOUT"  # TP2 (106) görülmedi; A varyantı farklı
    # TP çıkışı maker: ücret = giriş maker + TP maker
    p = simulate._params()
    assert approx(r3["outcome"]["fee_r"], p["maker"] * 100 / 1.0 + p["maker"] * 103 / 1.0)
    # Stop: -1R; aynı mumda 3R ve stop → STOP
    stop_spec = [(101, 101.5, 100.5, 101), (101, 101, 99.9, 100.3), (100.3, 103.5, 98.5, 100)]
    both = run(stop_spec, stop=99.0, tp1=102.0, tp2=106.0)["r3"]
    assert both["outcome"]["exit_reason"] == "STOP" and approx(both["outcome"]["r_gross"], -1.0)
    # R3'ün kendi iptal kuralı: dolmadan 3R'a ulaşılırsa iptal (TP2 uzak olduğundan A hâlâ canlı)
    cancel_spec = [(101, 103.2, 100.6, 103), (103, 103.1, 99.9, 100.2)]
    cancelled = run(cancel_spec, stop=99.0, tp1=102.0, tp2=106.0)
    assert cancelled["r3"]["status"] == "CANCEL_TP2" and cancelled["status"] == "FILLED", (cancelled["r3"]["status"], cancelled["status"])
    # Hedefsiz (NO_TARGET) setup'ta R3 yine de çalışır; ana sonuç NO_TARGET
    no_target = run(spec, stop=99.0, tp1=None, tp2=None)
    assert no_target["status"] == "NO_TARGET" and no_target["r3"]["status"] == "FILLED"
    # Short simetri
    short_spec = [(99, 99.5, 98.5, 99), (99, 100.05, 99, 99.7), (99.7, 99.9, 96.5, 96.8)]
    short = run(short_spec, entry=100.0, stop=101.0, tp1=98.0, tp2=94.0, direction="BEARISH", distal=110.0)["r3"]
    assert approx(short["target"], 97.0) and short["outcome"]["exit_reason"] == "R3" and approx(short["outcome"]["r_gross"], 3.0)
    print("Sabit 3R hedef: hedef/maker ücreti, stop önceliği, kendi iptali, NO_TARGET, short: GEÇTİ")


def test_flatten_rows():
    spec = [(101, 101.5, 100.5, 101), (101, 101, 99.95, 100.3), (100.3, 100.5, 99.7, 100.2),
            (100.2, 101.5, 100.1, 101.2), (101.2, 103.5, 101, 103.2)]
    result = run(spec, min_stops={"minstop_pct": 0.5, "minstop_atr": 0.05}, tp2=103.0)
    rows = rb.flatten([result])
    kinds = sorted((r["hypothesis"], r["variant"]) for r in rows)
    # Bu serinin 1. mumu 3R hedefe (100.3) dolmadan ulaştığı için R3 emri iptal olur → R3 satırı yok.
    assert kinds == sorted([("base", "TP2"), ("base", "TP1BE"), ("minstop_pct", "TP2"), ("minstop_pct", "TP1BE"),
                            ("minstop_atr", "TP2"), ("minstop_atr", "TP1BE")]), kinds
    assert result["r3"]["status"] == "CANCEL_TP2"
    filled = run([(101, 101.5, 100.5, 101), (101, 101, 99.9, 100.3), (100.3, 101.5, 100.2, 101),
                  (101, 103.4, 100.8, 103.2)], stop=99.0, tp1=102.0, tp2=106.0)
    filled_rows = rb.flatten([filled])
    r3_rows = [r for r in filled_rows if r["hypothesis"] == "r3"]
    assert len(r3_rows) == 1 and r3_rows[0]["variant"] == "R3" and approx(r3_rows[0]["tp2"], 103.0)
    assert approx(r3_rows[0]["rr_tp2"], 3.0) and r3_rows[0]["exit_reason"] == "R3"
    assert len({r["trade_id"] for r in rows}) == 1
    # Varsayılan select yalnızca base; hipotezler açıkça istenir
    assert {r["hypothesis"] for r in rb.select(rows)} == {"base"}
    assert {r["hypothesis"] for r in rb.select(filled_rows, hypothesis="r3")} == {"r3"}
    assert {r["hypothesis"] for r in rb.select(filled_rows, hypothesis=None)} >= {"base", "r3"}
    pct = [r for r in rows if r["hypothesis"] == "minstop_pct" and r["variant"] == "TP2"][0]
    assert approx(pct["stop"], 99.5) and approx(pct["stop_pct"], 0.5) and pct["stop_changed"] == 1
    unchanged = [r for r in rows if r["hypothesis"] == "minstop_atr" and r["variant"] == "TP2"][0]
    assert unchanged["stop_changed"] == 0 and unchanged["r_net"] == [r for r in rows if r["hypothesis"] == "base" and r["variant"] == "TP2"][0]["r_net"]
    # Dolmayan ana emirde de R3 satırı olabilir (kendi dolum kümesi)
    cancelled = run([(101, 103.2, 100.6, 103), (103, 103.1, 99.9, 100.2)], stop=99.0, tp1=102.0, tp2=106.0)
    cancelled["status"] = "CANCEL_TP2"
    assert [r["hypothesis"] for r in rb.flatten([cancelled])] == []  # r3 iptal → satır yok
    print("Düzleştirme: hipotez satırları, trade_id, select varsayılanı: GEÇTİ")


def test_confirmation_atr_rule_no_lookahead():
    series, data, rec = S.confirmation_fixture()
    params = simulate._params()
    base = simulate.simulate_confirmation(rec, data, params)
    assert base["status"] == "FILLED" and "minstop" in base and base["atr_1h"] is not None
    confirm_t = base["confirm_t"]
    expected_atr = indicators.atr(data.closed("1h", confirm_t, config.ATR_PERIOD + 1), config.ATR_PERIOD)
    assert approx(base["atr_1h"], expected_atr)
    risk = abs(base["entry"] - base["stop"])
    wide = base["minstop"]["minstop_atr"]
    assert approx(abs(base["entry"] - wide["stop"]), max(risk, expected_atr), 1e-9)
    assert wide["changed"] == (expected_atr > risk * (1 + 1e-12))
    pct = base["minstop"]["minstop_pct"]
    assert approx(abs(base["entry"] - pct["stop"]), max(risk, 0.005 * base["entry"]), 1e-9)
    # Teyit anından sonraki 1h/5m/15m mumlar değişse bile ATR ve genişletilmiş stoplar aynı kalır
    changed = {tf: [r if r[0] + fetch_history.INTERVAL_SECONDS[tf] <= confirm_t else
                    (r[0], r[1] * 1.3, r[2] * 1.4, r[3] * 1.2, r[4] * 1.3, r[5]) for r in rows]
               for tf, rows in series.items()}
    other = simulate.simulate_confirmation(rec, replay.SymbolData("TUSDT", changed), params)
    assert approx(other["atr_1h"], base["atr_1h"])
    # (dolum gelecekteki mumlara bağlı olduğundan yalnızca teyit anında belirlenen büyüklükler karşılaştırılır)
    assert approx(other["entry"], base["entry"]) and approx(other["stop"], base["stop"])
    assert other["confirm_t"] == base["confirm_t"]
    # Risk modu min stop hipotezi taşımaz (yalnız confirmation)
    risk_trade = simulate.simulate_risk(dict(rec, risk={"t": rec["first_seen_t"], "entry": base["entry"],
                                                        "stop": base["stop"], "tp1": base["tp1"], "tp2": base["tp2"]}),
                                        data, params)
    assert "minstop" not in risk_trade and "r3" in risk_trade
    print("1h ATR kuralı teyit anına kadar kapanmış mumlarla (look-ahead yok); risk modunda min stop yok: GEÇTİ")


def main():
    test_minstop()
    test_r3()
    test_flatten_rows()
    test_confirmation_atr_rule_no_lookahead()
    print("test_hypotheses: OK")


if __name__ == "__main__":
    main()
