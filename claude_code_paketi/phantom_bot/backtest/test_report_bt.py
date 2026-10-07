"""report_bt testleri: istatistikler, kırılımlar, 60/40 bölme, eşik önerisinin yalnız ilk döneme dayanması."""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report_bt as rb  # noqa: E402

START = 1_700_000_000
WINDOW = {"t_start": START, "t_end": START + 100 * 86400, "step_s": 14400}


def outcome(r_net, reason="TP2", exit_t=0, gross=None, fee=0.05, slip=0.02, funding=0.01):
    return {"exit_reason": reason, "exit_t": exit_t, "r_gross": r_net + fee + slip + funding if gross is None else gross,
            "r_net": r_net, "fee_r": fee, "slip_r": slip, "funding_r": funding, "hold_hours": 5.0, "data_end": False}


def trade(day, r_net, mode="risk", grade="B", poi_tf="4h", direction="BULLISH", symbol="BTCUSDT", score=65,
          rr=6.0, stop_pct=0.7, status="FILLED", reason="TP2", variants=None, key=None, distance=2.0):
    t = {"mode": mode, "symbol": symbol, "key": key or [symbol, direction, poi_tf, day, 1.0],
         "direction": direction, "poi_tf": poi_tf, "grade": grade, "score": score,
         "first_seen_t": START + int(day * 86400), "actionable": True, "distance_pct": distance, "status": status,
         "order_t": START, "fill_t": START + 60, "entry": 100.0, "stop": 99.0, "tp1": 102.0, "tp2": 106.0,
         "rr_tp1": 2.0, "rr_tp2": rr, "stop_pct": stop_pct, "market": "crypto"}
    if status == "FILLED":
        t["variants"] = variants or {"TP2": outcome(r_net, reason, exit_t=START + int(day * 86400) + 3600),
                                     "TP1BE": outcome(r_net / 2, reason, exit_t=START + int(day * 86400) + 3600)}
    return t


def test_stats():
    rows = []
    for index, value in enumerate([2.0, -1.0, -1.0, -1.0, 3.0, -1.0, 1.0]):
        rows.append(next(r for r in rb.flatten([trade(index, value)]) if r["variant"] == "TP2"))
    s = rb.stats(rows)
    assert s["n"] == 7 and abs(s["winrate"] - 3 / 7 * 100) < 1e-9
    assert abs(s["total_net"] - 2.0) < 1e-9 and abs(s["avg_net"] - 2 / 7) < 1e-9 and abs(s["expectancy"] - 2 / 7) < 1e-9
    assert abs(s["avg_win"] - 2.0) < 1e-9 and abs(s["avg_loss"] + 1.0) < 1e-9
    assert s["longest_loss_streak"] == 3, s["longest_loss_streak"]
    # Eğri: 2, 1, 0, -1, 2, 1, 2 → tepe 2, dip -1 → max DD 3
    assert abs(s["max_dd"] - 3.0) < 1e-9, s["max_dd"]
    assert abs(s["total_gross"] - (2.0 + 7 * 0.08)) < 1e-9
    assert s["se"] > 0
    assert rb.stats([])["n"] == 0 and rb.stats([])["winrate"] == 0.0
    # TIMEOUT ayrı sayılır
    timeout_rows = [dict(rows[0], exit_reason="TIMEOUT", r_net=-0.4)]
    t = rb.stats(timeout_rows)
    assert t["timeouts"] == 1 and abs(t["timeout_r"] + 0.4) < 1e-9
    print("İstatistikler (win%, ortalama, toplam, max DD, kayıp serisi, TIMEOUT): GEÇTİ")


def test_buckets_and_flatten():
    assert [rb.rr_bucket({"rr_tp2": v}) for v in (2.99, 3, 4.99, 5, 9.99, 10, 40)] == ["<3", "3–5", "3–5", "5–10", "5–10", ">10", ">10"]
    assert [rb.stop_bucket({"stop_pct": v}) for v in (0.2, 0.5, 1.0, 1.01)] == ["<%0.5", "%0.5–1", "%0.5–1", ">%1"]
    trades = [trade(1, 1.0), trade(2, 0, status="NO_TOUCH", mode="confirmation")]
    rows = rb.flatten(trades)
    assert len(rows) == 2 and {r["variant"] for r in rows} == {"TP2", "TP1BE"}  # dolmayan işlem satır üretmez
    print("R:R / stop kovaları ve düzleştirme: GEÇTİ")


def test_split_and_tables():
    split = rb.split_time(WINDOW)
    assert split == START + 0.6 * 100 * 86400
    early = [trade(day, 1.0, key=["A", "BULLISH", "4h", day, 1]) for day in (5, 20, 59)]
    late = [trade(day, -1.0, key=["A", "BULLISH", "4h", day, 1]) for day in (60.5, 80)]
    rows = rb.flatten(early + late)
    assert len(rb.select(rows, "risk", "TP2", until=split)) == 3 and len(rb.select(rows, "risk", "TP2", since=split)) == 2
    markdown = rb.build_markdown(early + late + [trade(10, 0, status="EXPIRED", key=["B", "BULLISH", "4h", 10, 1])], WINDOW,
                                 {"symbols": ["BTCUSDT"]})
    assert "## Doğrulama: ilk %60 / son %40" in markdown and "### İlk dönem (%60)" in markdown
    assert "| risk | A: TP2 | 5 |" in markdown  # tüm dönem 5 işlem
    assert "| risk | A: TP2 | 3 | 1 |" in markdown and "| risk | A: TP2 | 2 | 0 |" in markdown  # dönem bazında dolmayan sayısı
    assert "EXPIRED" in markdown and "Toplam R brüt" in markdown and "Ort. R brüt" in markdown
    for title in ("Not", "POI TF", "Yön", "Sembol", "R:R (TP2)", "Stop genişliği"):
        assert "| {} | İşlem |".format(title) in markdown, title
    assert "1R sabit risk" in markdown and "TIMEOUT" in markdown
    print("Dönem bölme, ana tablo, kırılım başlıkları, dolmayan sayımı: GEÇTİ")


def test_thresholds_use_first_period_only():
    split_day = 60
    first = []
    # İlk dönem: yüksek puanlı işlemler kazanıyor, düşük puanlılar kaybediyor (40'ar işlem)
    for i in range(40):
        first.append(trade(i * 1.4, 1.0, score=80, key=["S", "BULLISH", "4h", i, 1]))
        first.append(trade(i * 1.4 + 0.1, -1.0, score=50, key=["S", "BULLISH", "4h", i, 2]))
    last_a = [trade(61 + i * 0.9, 0.5, score=80, key=["S", "BULLISH", "4h", 100 + i, 1]) for i in range(20)]
    last_b = [trade(61 + i * 0.9, -2.0, score=80, key=["S", "BULLISH", "4h", 100 + i, 1]) for i in range(20)]
    rows_first = rb.select(rb.flatten(first), until=rb.split_time(WINDOW))
    assert len(rows_first) == 160
    result_a = rb.suggest(rows_first, rb.flatten(last_a))
    result_b = rb.suggest(rows_first, rb.flatten(last_b))
    entry_a = next(e for e in result_a if e["mode"] == "risk" and e["variant"] == "TP2")
    entry_b = next(e for e in result_b if e["mode"] == "risk" and e["variant"] == "TP2")
    assert entry_a["filter"] == entry_b["filter"] and entry_a["filter"]["min_score"] >= 51 - 6, entry_a["filter"]
    assert entry_a["filter"]["min_score"] in (60, 75)
    assert entry_a["first"]["n"] >= rb.MIN_TRADES_FIRST and entry_a["first"]["avg_net"] > 0.9
    assert "pozitif" in entry_a["verdict"] and "tutmadı" in entry_b["verdict"], (entry_a["verdict"], entry_b["verdict"])
    # İlk dönemde yeterli işlem yoksa öneri yok
    few = rb.suggest(rows_first[:10], rb.flatten(last_a))
    assert all(e["filter"] is None for e in few)
    print("Eşik önerisi yalnız ilk döneme dayanıyor; son dönem yalnız doğrulama: GEÇTİ")


def test_write_reports():
    out = tempfile.mkdtemp(prefix="bt_rep_")
    trades = [trade(day, 1.0 if day % 2 else -1.0, key=["A", "BULLISH", "4h", day, 1]) for day in range(1, 90, 3)]
    paths = rb.write_reports(trades, WINDOW, out, {"symbols": ["BTCUSDT"]}, stamp="2026-01-01_0000_UTC")
    for path in paths.values():
        assert os.path.isfile(path), path
    with open(paths["summary"], encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["period"] for r in rows} == {"all", "first_60", "last_40"} and len(rows) == 12
    all_risk = next(r for r in rows if r["period"] == "all" and r["mode"] == "risk" and r["variant"] == "TP2")
    assert int(all_risk["n"]) == len(trades)
    with open(paths["trades"], encoding="utf-8-sig") as handle:
        trade_rows = list(csv.DictReader(handle))
    assert len(trade_rows) == 2 * len(trades) and {"r_net", "r_gross", "variant", "exit_reason"} <= set(trade_rows[0])
    assert open(paths["latest"], encoding="utf-8").read() == open(paths["md"], encoding="utf-8").read()
    print("md/csv dosyaları yazılıyor: GEÇTİ")


def main():
    test_stats()
    test_buckets_and_flatten()
    test_split_and_tables()
    test_thresholds_use_first_period_only()
    test_write_reports()
    print("test_report_bt: OK")


if __name__ == "__main__":
    main()
