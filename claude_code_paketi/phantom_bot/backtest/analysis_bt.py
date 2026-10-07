"""Önceden belirlenmiş analizler: puan kriteri katkısı (ve sonraki parçalarda hipotez tabloları).

Izgara araması YOK. Her analiz ilk %60 ve son %40 dönemde AYRI raporlanır.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bt_stats  # noqa: E402
import report_bt as rb  # noqa: E402


def _fmt(value, digits=2):
    return "—" if value is None else ("{:.%df}" % digits).format(value)


def _ci(lo, hi, digits=2):
    return "—" if lo is None else "[{}, {}]".format(_fmt(lo, digits), _fmt(hi, digits))


def group_stats(values, label):
    """Net R listesi için n, win%, ortalama, düz bootstrap %90 aralığı, P(ort>0)."""
    ci = bt_stats.mean_ci(values, label)
    return {"n": len(values), "winrate": (sum(1 for v in values if v > 0) / len(values) * 100.0) if values else 0.0,
            "mean": ci["mean"], "lo": ci["lo"], "hi": ci["hi"], "p_pos": ci["p_pos"]}


def criteria_stats(rows, window):
    """{(dönem, mod, varyant): [kriter satırları]} — var/yok grupları, fark ve iki dönemde işaret tutarlılığı."""
    out = {}
    for period, since, until in rb.periods(window):
        for mode in rb.MODES:
            for variant in rb.VARIANTS:
                subset = rb.select(rows, mode, variant, since, until)
                table = []
                for criterion in rb.REPORT_CRITERIA:
                    key = "crit_" + criterion
                    yes = [r["r_net"] for r in subset if r.get(key)]
                    no = [r["r_net"] for r in subset if not r.get(key)]
                    label = "crit|{}|{}|{}|{}".format(period, mode, variant, criterion)
                    entry = {"criterion": criterion, "yes": group_stats(yes, label + "|var"),
                             "no": group_stats(no, label + "|yok"), "diff": None}
                    if len(yes) >= bt_stats.MIN_N and len(no) >= bt_stats.MIN_N:
                        boots_yes = bt_stats.boot_means(yes, label + "|var")
                        boots_no = bt_stats.boot_means(no, label + "|yok")
                        summary = bt_stats.summarize([a - b for a, b in zip(boots_yes, boots_no)])
                        summary["mean"] = entry["yes"]["mean"] - entry["no"]["mean"]
                        entry["diff"] = summary
                    table.append(entry)
                out[(period, mode, variant)] = table
    # İki dönemde fark işareti aynı mı? (mekanik işaret; seçim yapmaz)
    names = [name for name, _, _ in rb.periods(window)]
    for mode in rb.MODES:
        for variant in rb.VARIANTS:
            first, last = out[(names[0], mode, variant)], out[(names[1], mode, variant)]
            for a, b in zip(first, last):
                if a["diff"] and b["diff"] and a["diff"]["mean"] != 0 and b["diff"]["mean"] != 0:
                    same = (a["diff"]["mean"] > 0) == (b["diff"]["mean"] > 0)
                    a["consistent"] = b["consistent"] = "✓" if same else "✗"
                else:
                    a["consistent"] = b["consistent"] = "—"
    return out


def criteria_markdown(stats):
    lines = ["## Puan kriterlerinin katkısı (var / yok)", "",
             "Her kriter için kriterin bulunduğu ve bulunmadığı işlemler ayrı; ölçü net ortalama R "
             "(düz bootstrap %90 aralık ve P(ort>0)). **Fark** = var − yok. Son sütun, farkın iki dönemde aynı "
             "işaretli olup olmadığını mekanik olarak gösterir.", "",
             "> Çoklu karşılaştırma uyarısı: 12 kriter × 2 mod × 2 varyant × 2 dönem ≈ 100 aralık var. %90 düzeyinde "
             "bunların yaklaşık 10'u yalnızca tesadüfen sıfırı dışlar. Tek bir aralığa değil, iki dönemde tutarlı "
             "ve her iki varyantta aynı yöndeki örüntülere bakın.", ""]
    grouped = {}
    for (period, mode, variant), table in stats.items():
        grouped.setdefault((mode, variant), []).append((period, table))
    for mode in rb.MODES:
        for variant in rb.VARIANTS:
            lines.extend(["### {} — {}".format(mode, rb.VARIANT_LABEL[variant]), ""])
            for period, table in grouped[(mode, variant)]:
                lines.extend(["**{}**".format(period), "",
                              "| Kriter | Var n | Var win % | Var ort. R | Var %90 CI | Var P(>0) | Yok n | Yok win % | "
                              "Yok ort. R | Yok %90 CI | Yok P(>0) | Fark | Fark %90 CI | P(fark>0) | İki dönemde aynı işaret |",
                              "|---|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|---|---:|:---:|"])
                for entry in table:
                    y, n, d = entry["yes"], entry["no"], entry["diff"]
                    lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                        entry["criterion"], y["n"], _fmt(y["winrate"], 1), _fmt(y["mean"], 3), _ci(y["lo"], y["hi"]),
                        _fmt(y["p_pos"]), n["n"], _fmt(n["winrate"], 1), _fmt(n["mean"], 3), _ci(n["lo"], n["hi"]),
                        _fmt(n["p_pos"]), _fmt(d["mean"], 3) if d else "—", _ci(d["lo"], d["hi"]) if d else "—",
                        _fmt(d["p_pos"]) if d else "—", entry.get("consistent", "—")))
                lines.append("")
    return lines


# ====================================================================== hipotez tabloları
PREREG_TEXT = ("Bir hipotez ancak 365 günlük veride, maliyetli net ortalama R hem ilk %60 hem son %40 döneminde > 0 "
               "VE gün bazlı küme bootstrap ile her iki dönemde P(ort>0) ≥ 0.90 ise 'geçti' sayılır. "
               "Aksi halde 'geçmedi'.")
PREREG_P = 0.90
FINAL_DAYS = 360  # pencere bu kadar günden uzunsa "365 günlük veri" sayılır
PERIOD_ALL = "Tüm dönem"
PERIOD_FIRST, PERIOD_LAST = "İlk %60", "Son %40"

# (mod, hipotez, varyant, etiket, bilgi_amaçlı_satır)
HYPOTHESES = (
    ("confirmation", "base", "TP2", "taban A: TP2", False),
    ("confirmation", "base", "TP1BE", "taban B: TP1 %50 + BE", False),
    ("confirmation", "minstop_pct", "TP2", "min stop %0.5 — A", False),
    ("confirmation", "minstop_pct", "TP1BE", "min stop %0.5 — B", False),
    ("confirmation", "minstop_atr", "TP2", "min stop 1h ATR(14) — A", False),
    ("confirmation", "minstop_atr", "TP1BE", "min stop 1h ATR(14) — B", False),
    ("confirmation", "r3", "R3", "sabit 3R hedef", False),
    ("risk", "base", "TP2", "taban A: TP2", False),
    ("risk", "base", "TP1BE", "taban B: TP1 %50 + BE", False),
    ("risk", "r3", "R3", "sabit 3R hedef", False),
)


def window_days(window):
    return (window["t_end"] - window["t_start"]) / 86400.0


def is_final_window(window):
    return window_days(window) >= FINAL_DAYS


def preregistered_header(window):
    """Raporun başına konan sabit metin; 365 günden kısa pencerede 'nihai karar 365 gün raporundadır' notu."""
    lines = ["> **Önceden kayıtlı başarı ölçütü:** " + PREREG_TEXT, ""]
    if not is_final_window(window):
        lines.extend(["> **Not: Bu rapor {:.0f} günlüktür; nihai karar 365 gün raporundadır.** "
                      "Aşağıdaki geçti/geçmedi işaretleri (†) yalnızca bilgi içindir.".format(window_days(window)), ""])
    return lines


def _row_stats(subset, label):
    values = [r["r_net"] for r in subset]
    ci = cluster_ci = rb.cluster_stats(subset, label)
    n = len(values)
    costs = [r["fee_r"] + r["slip_r"] + r["funding_r"] for r in subset]
    changed = [r.get("stop_changed") for r in subset if r.get("stop_changed") is not None]
    return {"n": n, "winrate": (sum(1 for v in values if v > 0) / n * 100.0) if n else 0.0,
            "mean": ci["mean"], "lo": cluster_ci["lo"], "hi": cluster_ci["hi"], "p_pos": cluster_ci["p_pos"],
            "clusters": cluster_ci["clusters"], "trim5": ci["trim5"], "total": sum(values),
            "avg_stop_pct": (sum(r["stop_pct"] for r in subset) / n) if n else None,
            "avg_cost": (sum(costs) / n) if n else None,
            "changed_pct": (sum(changed) / len(changed) * 100.0) if changed else None}


def verdict_for(first, last):
    """Mekanik karar: her iki dönemde net ort. R > 0 VE küme bootstrap P(ort>0) ≥ 0.90."""
    for period in (first, last):
        if period["n"] == 0 or period["p_pos"] is None:
            return False
    return (first["mean"] > 0 and last["mean"] > 0 and first["p_pos"] >= PREREG_P and last["p_pos"] >= PREREG_P)


def hypothesis_stats(rows, window):
    """{(mod, hipotez, varyant): {...}} + R3 için A ile ortak işlem satırları (bilgi amaçlı, karar dışı)."""
    ranges = [(PERIOD_FIRST,) + rb.periods(window)[0][1:], (PERIOD_LAST,) + rb.periods(window)[1][1:],
              (PERIOD_ALL, None, None)]
    out = {}
    for mode, hypothesis, variant, label, _ in HYPOTHESES:
        entry = {"label": label, "mode": mode, "hypothesis": hypothesis, "variant": variant, "info": False,
                 "periods": {}}
        for period, since, until in ranges:
            subset = rb.select(rows, mode, variant, since, until, hypothesis)
            entry["periods"][period] = _row_stats(subset, "hyp|{}|{}|{}|{}".format(period, mode, hypothesis, variant))
        entry["pass"] = verdict_for(entry["periods"][PERIOD_FIRST], entry["periods"][PERIOD_LAST])
        out[(mode, hypothesis, variant)] = entry
    # R3 ve A'nın ortak işlemleri (aynı setup + mod her ikisinde de doldu)
    for mode in rb.MODES:
        common = {}
        for period, since, until in ranges:
            a_rows = rb.select(rows, mode, "TP2", since, until, "base")
            r_rows = rb.select(rows, mode, "R3", since, until, "r3")
            shared = {r["trade_id"] for r in a_rows} & {r["trade_id"] for r in r_rows}
            common[period] = (
                _row_stats([r for r in a_rows if r["trade_id"] in shared], "common|A|{}|{}".format(period, mode)),
                _row_stats([r for r in r_rows if r["trade_id"] in shared], "common|R3|{}|{}".format(period, mode)))
        for index, (name, hypothesis, variant) in enumerate((("taban A: TP2 (R3 ile ortak işlemler)", "base_common", "TP2"),
                                                              ("sabit 3R (A ile ortak işlemler)", "r3_common", "R3"))):
            out[(mode, hypothesis, variant)] = {
                "label": name, "mode": mode, "hypothesis": hypothesis, "variant": variant, "info": True,
                "periods": {period: common[period][index] for period in common}, "pass": None}
    return out


def _verdict_text(entry, window):
    if entry["info"]:
        return "bilgi"
    text = "geçti" if entry["pass"] else "geçmedi"
    return text if is_final_window(window) else text + " †"


def hypothesis_markdown(stats, window):
    first_name, last_name = PERIOD_FIRST, PERIOD_LAST
    lines = ["## Hipotez analizleri (önceden belirlenmiş; ızgara yok)", "",
             "Hipotezler: (2) minimum stop — yalnız confirmation: stop mesafesi (a) giriş × %0.5 veya (b) 1h ATR(14) "
             "(teyit anına kadar kapanmış 1h mumlarla) değerinden küçükse stop genişletilir, giriş ve hedefler aynı, "
             "R yeniden hesaplanır; (3) TP2 yerine sabit 3R hedef (giriş ± 3 × **orijinal** stop mesafesi; TP1/BE yok; "
             "kendi dolum/iptal çözümüyle). Tüm değerler maliyetli net R'dir. Aralıklar gün bazlı (fill günü) küme "
             "bootstrap'idir. Karar yalnızca ilk %60 ve son %40 dönem sonuçlarından verilir; 'tüm dönem' bilgi amaçlıdır.",
             "", "### Karar özeti", "",
             "| Mod | Hipotez | İlk %60 ort. R (P) | Son %40 ort. R (P) | Tüm dönem ort. R (P) | Karar |",
             "|---|---|---|---|---|---|"]

    def cell(stat):
        return "{} ({})".format(_fmt(stat["mean"], 3), _fmt(stat["p_pos"])) if stat["n"] else "— (n=0)"

    for key, entry in stats.items():
        p = entry["periods"]
        lines.append("| {} | {} | {} (n={}) | {} (n={}) | {} (n={}) | {} |".format(
            entry["mode"], entry["label"], cell(p[first_name]), p[first_name]["n"], cell(p[last_name]),
            p[last_name]["n"], cell(p[PERIOD_ALL]), p[PERIOD_ALL]["n"], _verdict_text(entry, window)))
    if not is_final_window(window):
        lines.extend(["", "† Bu rapor 365 günden kısa; nihai karar 365 gün raporundadır."])
    for period in (first_name, last_name, PERIOD_ALL):
        lines.extend(["", "### {}".format(period + (" (karar ölçütü)" if period != PERIOD_ALL else " (bilgi amaçlı)")), "",
                      "| Mod | Hipotez | İşlem | Win % | Ort. R net | Küme %90 CI | P(ort>0) küme | Top-5 hariç ort. R | "
                      "Toplam R net | Ort. stop % | Ort. maliyet R | Stopu genişleyen % |",
                      "|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|"])
        for entry in stats.values():
            s = entry["periods"][period]
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                entry["mode"], entry["label"], s["n"], _fmt(s["winrate"], 1), _fmt(s["mean"], 3) if s["n"] else "—",
                _ci(s["lo"], s["hi"]), _fmt(s["p_pos"]), _fmt(s["trim5"], 3), _fmt(s["total"]) if s["n"] else "—",
                _fmt(s["avg_stop_pct"], 3), _fmt(s["avg_cost"], 3), _fmt(s["changed_pct"], 1)))
    return lines


SUMMARY_HYP_COLUMNS = ["mode", "hypothesis", "variant", "label", "period", "n", "winrate", "mean_net", "ci_lo", "ci_hi",
                       "p_pos_cluster", "trim5_mean", "total_net", "avg_stop_pct", "avg_cost_r", "changed_pct", "verdict"]


def hypothesis_csv_rows(stats, window):
    rows = []
    for entry in stats.values():
        for period, s in entry["periods"].items():
            rows.append({"mode": entry["mode"], "hypothesis": entry["hypothesis"], "variant": entry["variant"],
                         "label": entry["label"], "period": period, "n": s["n"], "winrate": s["winrate"],
                         "mean_net": s["mean"], "ci_lo": s["lo"], "ci_hi": s["hi"], "p_pos_cluster": s["p_pos"],
                         "trim5_mean": s["trim5"], "total_net": s["total"], "avg_stop_pct": s["avg_stop_pct"],
                         "avg_cost_r": s["avg_cost"], "changed_pct": s["changed_pct"],
                         "verdict": _verdict_text(entry, window) if period == PERIOD_ALL else ""})
    return rows
