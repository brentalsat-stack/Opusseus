"""Hipotez tabloları, önceden kayıtlı başarı ölçütü ve küme bootstrap'in rapora bağlanması."""
import csv
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analysis_bt as ab  # noqa: E402
import report_bt as rb  # noqa: E402
from test_report_bt import outcome, START  # noqa: E402

WINDOW_365 = {"t_start": START, "t_end": START + 365 * 86400, "step_s": 14400}
WINDOW_180 = {"t_start": START, "t_end": START + 180 * 86400, "step_s": 14400}


def make(day, r, mode="confirmation", index=0, same_day=False, r3=None, minstop=None, window_days=365):
    first = START + int(day * 86400)
    fill = first + 3600
    t = {"mode": mode, "symbol": "BTCUSDT", "key": ["BTCUSDT", "BULLISH", "1h", index, 1], "direction": "BULLISH",
         "poi_tf": "1h", "grade": "B", "score": 65, "first_seen_t": first, "actionable": True, "distance_pct": 1.0,
         "status": "FILLED", "order_t": first, "fill_t": fill, "entry": 100.0, "stop": 99.8, "tp1": 101.0, "tp2": 101.0,
         "rr_tp1": 2.0, "rr_tp2": 5.0, "stop_pct": 0.2, "market": "crypto", "score_breakdown": []}
    base = outcome(r, exit_t=fill + 3600)
    t["variants"] = {"TP2": dict(base), "TP1BE": dict(base)}
    if minstop is not None:
        t["minstop"] = {"minstop_pct": {"changed": True, "stop": 99.5, "stop_pct": 0.5, "rr_tp2": 2.0,
                                        "variants": {"TP2": outcome(minstop, exit_t=fill + 3600),
                                                     "TP1BE": outcome(minstop, exit_t=fill + 3600)}},
                        "minstop_atr": {"changed": False, "stop": 99.8, "stop_pct": 0.2, "rr_tp2": 5.0,
                                        "variants": t["variants"]}}
    if r3 is not None:
        t["r3"] = {"status": "FILLED", "target": 100.6, "rr_tp2": 3.0, "stop_pct": 0.2, "fill_t": fill,
                   "outcome": dict(outcome(r3, exit_t=fill + 3600), exit_reason="R3")}
    return t


def population(days, mean_first, mean_last, sd=0.3, per_day=1, seed=1, split_day=219):
    rng = random.Random(seed)
    trades, index = [], 0
    for day in range(days):
        for _ in range(per_day):
            mean = mean_first if day < split_day else mean_last
            for mode in ("confirmation", "risk"):
                value = mean + rng.gauss(0, sd)
                trades.append(make(day + 0.01 * index % 1, value, mode=mode, index=index, r3=value, minstop=value))
            index += 1
    return trades


def entry(stats, mode, hypothesis, variant):
    return stats[(mode, hypothesis, variant)]


def main():
    import config
    saved = config.BT_BOOTSTRAP_N
    config.BT_BOOTSTRAP_N = 400  # test hızı için; karar eşiği P ≥ 0.90 bu çözünürlükte de ayırt edilir
    try:
        run()
    finally:
        config.BT_BOOTSTRAP_N = saved


def run():
    # ---- önceden kayıtlı metin ve nihai olmayan pencere notu
    full = rb.build_markdown(population(360, 0.4, 0.4), WINDOW_365, {"symbols": ["BTCUSDT"]})
    assert full.index("Önceden kayıtlı başarı ölçütü") < full.index("## Özet")
    assert ("Bir hipotez ancak 365 günlük veride, maliyetli net ortalama R hem ilk %60 hem son %40 döneminde > 0 VE gün "
            "bazlı küme bootstrap ile her iki dönemde P(ort>0) ≥ 0.90 ise 'geçti' sayılır. Aksi halde 'geçmedi'.") in full
    assert "nihai karar 365 gün raporundadır" not in full.split("## Özet")[0]
    short = rb.build_markdown(population(170, 0.4, 0.4, split_day=108), WINDOW_180, {"symbols": ["BTCUSDT"]})
    head = short.split("## Özet")[0]
    assert "Önceden kayıtlı başarı ölçütü" in head and "nihai karar 365 gün raporundadır" in head
    assert "geçti †" in short and "† Bu rapor 365 günden kısa" in short
    print("Sabit başarı ölçütü metni ve 180 günlük rapor notu: GEÇTİ")

    # ---- mekanik karar
    rows = rb.flatten(population(360, 0.4, 0.4))
    stats = ab.hypothesis_stats(rows, WINDOW_365)
    for key in (("confirmation", "r3", "R3"), ("confirmation", "minstop_pct", "TP2"), ("risk", "base", "TP2")):
        e = entry(stats, *key)
        assert e["pass"] is True, (key, e["periods"])
        assert e["periods"][ab.PERIOD_FIRST]["p_pos"] >= 0.9 and e["periods"][ab.PERIOD_LAST]["p_pos"] >= 0.9
    assert ab._verdict_text(entry(stats, "risk", "r3", "R3"), WINDOW_365) == "geçti"
    assert ab._verdict_text(entry(stats, "risk", "r3", "R3"), WINDOW_180) == "geçti †"

    # ilk dönem pozitif, son dönem negatif → geçmedi
    mixed = ab.hypothesis_stats(rb.flatten(population(360, 0.5, -0.4)), WINDOW_365)
    assert mixed[("confirmation", "r3", "R3")]["pass"] is False
    assert ab._verdict_text(mixed[("confirmation", "r3", "R3")], WINDOW_365) == "geçmedi"
    # iki dönemde de pozitif ama P < 0.90 (gürültü büyük) → geçmedi
    noisy = ab.hypothesis_stats(rb.flatten(population(360, 0.03, 0.03, sd=1.5)), WINDOW_365)
    e = noisy[("confirmation", "r3", "R3")]
    assert e["periods"][ab.PERIOD_FIRST]["mean"] > 0 or e["periods"][ab.PERIOD_LAST]["mean"] > 0
    assert e["pass"] is False and min(e["periods"][p]["p_pos"] for p in (ab.PERIOD_FIRST, ab.PERIOD_LAST)) < 0.9
    # bir dönemde hiç işlem yok → geçmedi
    only_first = [t for t in population(360, 0.5, 0.5) if t["first_seen_t"] < ab.rb.split_time(WINDOW_365)]
    empty_last = ab.hypothesis_stats(rb.flatten(only_first), WINDOW_365)
    assert empty_last[("confirmation", "r3", "R3")]["pass"] is False
    # tüm işlemler aynı gün → küme sayısı 1 → P hesaplanamaz → geçmedi (pozitif ortalamaya rağmen)
    one_day = [make(10 + 0.00001 * i, 0.5, index=i, r3=0.5, minstop=0.5) for i in range(40)]
    one_day += [make(300 + 0.00001 * i, 0.5, index=100 + i, r3=0.5, minstop=0.5) for i in range(40)]
    clustered = ab.hypothesis_stats(rb.flatten(one_day), WINDOW_365)
    e = clustered[("confirmation", "r3", "R3")]
    assert e["periods"][ab.PERIOD_FIRST]["clusters"] == 1 and e["periods"][ab.PERIOD_FIRST]["p_pos"] is None
    assert e["pass"] is False
    print("Önceden kayıtlı ölçütün mekanik uygulanması (geçti/geçmedi, dönemler, küme): GEÇTİ")

    # ---- tablo içeriği, top-5 hariç, ortak işlemler, ek sütunlar
    markdown = "\n".join(ab.hypothesis_markdown(stats, WINDOW_365))
    for text in ("### Karar özeti", "### İlk %60 (karar ölçütü)", "### Son %40 (karar ölçütü)", "### Tüm dönem (bilgi amaçlı)",
                 "min stop %0.5 — A", "min stop 1h ATR(14) — B", "sabit 3R hedef", "taban A: TP2 (R3 ile ortak işlemler)",
                 "sabit 3R (A ile ortak işlemler)", "Top-5 hariç ort. R", "Küme %90 CI", "Stopu genişleyen %"):
        assert text in markdown, text
    pct = entry(stats, "confirmation", "minstop_pct", "TP2")["periods"][ab.PERIOD_ALL]
    assert pct["changed_pct"] == 100.0 and abs(pct["avg_stop_pct"] - 0.5) < 1e-9
    atr = entry(stats, "confirmation", "minstop_atr", "TP2")["periods"][ab.PERIOD_ALL]
    assert atr["changed_pct"] == 0.0
    assert entry(stats, "confirmation", "r3", "R3")["periods"][ab.PERIOD_ALL]["trim5"] is not None
    common_a = entry(stats, "risk", "base_common", "TP2")["periods"][ab.PERIOD_ALL]
    common_r = entry(stats, "risk", "r3_common", "R3")["periods"][ab.PERIOD_ALL]
    assert common_a["n"] == common_r["n"] > 0 and entry(stats, "risk", "r3_common", "R3")["pass"] is None
    assert "bilgi" in markdown
    # min stop hipotezi risk modunda yok
    assert ("risk", "minstop_pct", "TP2") not in stats
    # başlık tablosunda küme sütunları
    main = "\n".join(rb.main_table(rows, population(360, 0.4, 0.4)))
    assert "Küme %90 CI" in main and "P(ort>0) küme" in main and "Top-5 hariç ort. R" in main
    print("Hipotez tabloları (dönemler, ortak işlemler, top-5 hariç, genişleyen %): GEÇTİ")

    # ---- CSV
    out = tempfile.mkdtemp(prefix="bt_hyp_")
    paths = rb.write_reports(population(360, 0.4, 0.4), WINDOW_365, out, {"symbols": ["BTCUSDT"]}, stamp="s")
    with open(paths["hypotheses"], encoding="utf-8-sig") as handle:
        rows_csv = list(csv.DictReader(handle))
    assert {r["period"] for r in rows_csv} == {"İlk %60", "Son %40", "Tüm dönem"}
    verdicts = [r for r in rows_csv if r["verdict"]]
    assert verdicts and all(r["period"] == "Tüm dönem" for r in verdicts)
    assert any(r["hypothesis"] == "r3" and r["verdict"] == "geçti" for r in rows_csv)
    with open(paths["trades"], encoding="utf-8-sig") as handle:
        trade_rows = list(csv.DictReader(handle))
    assert {"base", "minstop_pct", "minstop_atr", "r3"} <= {r["hypothesis"] for r in trade_rows}
    print("Hipotez CSV ve işlem CSV'sinde hipotez satırları: GEÇTİ")
    print("test_hypothesis_report: OK")


if __name__ == "__main__":
    main()
