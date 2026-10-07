"""analysis_bt testleri: kriter var/yok grupları, dönemler, fark ve tutarlılık işareti."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analysis_bt as ab  # noqa: E402
import report_bt as rb  # noqa: E402
from test_report_bt import WINDOW, trade  # noqa: E402


def make_trades(seed=3):
    rng = random.Random(seed)
    trades = []
    for index in range(600):
        day = index * 100 / 600.0  # 100 günlük pencereye yayılır; ilk %60 → gün < 60
        fvg = rng.random() < 0.5
        sweep = rng.random() < 0.5
        mode = "risk" if index % 2 else "confirmation"
        # fvg etkisi: var → +0.6, yok → -0.6 ; sweep etkisi yok ; tutarlı iki dönemde
        r = (0.6 if fvg else -0.6) + rng.gauss(0, 0.5)
        breakdown = []
        if fvg:
            breakdown.append({"criterion": "fvg", "points": 6})
        if sweep:
            breakdown.append({"criterion": "sweep_then_bos", "points": 10})
        t = trade(day, r, mode=mode, key=["S", "BULLISH", "4h", index, 1], symbol="S" + str(index % 5))
        t["score_breakdown"] = breakdown
        trades.append(t)
    return trades


def main():
    rows = rb.flatten(make_trades())
    stats = ab.criteria_stats(rows, WINDOW)
    names = [name for name, _, _ in rb.periods(WINDOW)]
    assert names == ["İlk %60", "Son %40"] and len(stats) == 2 * 2 * 2
    split = rb.split_time(WINDOW)

    for (period, mode, variant), table in stats.items():
        subset = rb.select(rows, mode, variant, *(None, split) if period == "İlk %60" else (split, None))
        assert subset and all((r["first_seen_t"] < split) == (period == "İlk %60") for r in subset)
        by = {entry["criterion"]: entry for entry in table}
        assert set(by) == set(rb.REPORT_CRITERIA)
        fvg = by["fvg"]
        assert fvg["yes"]["n"] == sum(1 for r in subset if r["crit_fvg"]) and fvg["yes"]["n"] + fvg["no"]["n"] == len(subset)
        if variant == "TP2":  # B varyantında R yarıya iner; işaret aynı
            assert fvg["yes"]["mean"] > 0.3 and fvg["no"]["mean"] < -0.3, fvg
            assert fvg["diff"]["lo"] > 0 and fvg["diff"]["p_pos"] > 0.99, fvg["diff"]
            assert fvg["yes"]["p_pos"] > 0.99 and fvg["no"]["p_pos"] < 0.01
            sweep = by["sweep_then_bos"]
            # etkisiz kriter: fark, gerçek etkili kriterin (≈1.2R) çok altında (aralık tesadüfen 0'ı dışlayabilir)
            assert abs(sweep["diff"]["mean"]) < 0.4 and fvg["diff"]["mean"] > 1.0, (sweep["diff"], fvg["diff"])
        assert by["fvg"]["consistent"] == "✓"
        assert by["inducement"]["yes"]["n"] == 0 and by["inducement"]["diff"] is None  # kriter hiç yok → fark hesaplanmaz
        assert by["inducement"]["consistent"] == "—"

    # Farkın işareti iki dönemde farklıysa ✗: ikinci dönemde etkiyi ters çevir
    flipped = []
    for t in make_trades(7):
        if t["first_seen_t"] >= rb.split_time(WINDOW):
            fvg = any(b["criterion"] == "fvg" for b in t["score_breakdown"])
            for variant in t["variants"].values():
                variant["r_net"] = -variant["r_net"] if fvg or True else variant["r_net"]
        flipped.append(t)
    flipped_stats = ab.criteria_stats(rb.flatten(flipped), WINDOW)
    table = flipped_stats[("İlk %60", "risk", "TP2")]
    assert {e["criterion"]: e for e in table}["fvg"]["consistent"] == "✗"

    # Deterministik ve Markdown çıktısı
    again = ab.criteria_stats(rows, WINDOW)
    assert again == stats
    markdown = "\n".join(ab.criteria_markdown(stats))
    for header in ("## Puan kriterlerinin katkısı", "### risk — A: TP2", "### confirmation — B: TP1 %50 + BE",
                   "**İlk %60**", "**Son %40**", "Çoklu karşılaştırma uyarısı", "İki dönemde aynı işaret"):
        assert header in markdown, header
    assert "| fvg |" in markdown and "| major_structure_break |" in markdown
    full = rb.build_markdown(make_trades(), WINDOW, {"symbols": ["S"]})
    assert "## Puan kriterlerinin katkısı" in full
    print("Kriter analizi (var/yok, dönemler, fark, tutarlılık, Markdown): GEÇTİ")
    print("test_analysis_bt: OK")


if __name__ == "__main__":
    main()
