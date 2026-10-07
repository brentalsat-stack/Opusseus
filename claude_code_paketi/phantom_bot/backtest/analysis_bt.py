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
