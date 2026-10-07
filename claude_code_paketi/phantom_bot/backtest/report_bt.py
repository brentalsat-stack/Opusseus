"""Backtest raporu (Markdown + CSV): mod × varyant, kırılımlar, maliyetli/maliyetsiz, 60/40 doğrulama."""
import csv
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

MODES = ("risk", "confirmation")
VARIANTS = ("TP2", "TP1BE")
VARIANT_LABEL = {"TP2": "A: TP2", "TP1BE": "B: TP1 %50 + BE"}
SPLIT_RATIO = 0.6

NOTES = [
    "1R sabit risk; kaldıraç/likidasyon modellenmez (stop'un likidasyondan önce çalıştığı varsayılır). Sonuçlar R cinsindendir.",
    "Dolum: limit emir giriş seviyesinde dolar (iyileşme yok); dolum mumunda yalnızca STOP kontrol edilir, TP/BE sonraki mumdan başlar.",
    "Aynı 5m mumunda stop ve hedef birlikte görülürse STOP kazanır.",
    "Ücret: giriş ve TP çıkışı MAKER; STOP, BE ve TIMEOUT çıkışları TAKER + kayma. Funding pozisyon açıkken geçen her funding anında uygulanır.",
    "TIMEOUT: açık pozisyon BT_MAX_HOLD_DAYS sonunda (veya veri bitince) piyasadan kapatılır; ayrı raporlanır.",
    "Risk modunda limit emir BT_TOUCH_EXPIRY_HOURS içinde dolmalı; confirmation'da POI dokunuşu aynı süre içinde olmalı, teyitten sonra "
    "LTF OB girişi BT_CONFIRM_FILL_HOURS içinde dolmalı. Teyit için dokunuştan sonra BT_CONFIRM_WAIT_HOURS beklenir (varsayım).",
    "Aynı POI (sembol+yön+TF+proximal+distal) tek setup sayılır; risk modu ilk görüldüğü andaki ilk 'risk' seviyelerini kullanır.",
    "Confirmation modu, her 15m kapanışında signals.ltf_status ve evaluate_ob_state'i o ana kadar kapanmış mumlarla çalıştırır.",
]


# ------------------------------------------------------------------ puan kriterleri (0/1 sütunlar)
CRITERIA = (  # (sütun adı, puan tablosundaki kriter adları — herhangi biri varsa 1)
    ("htf_alignment", ("htf_alignment",)),
    ("stack_2plus", ("stack_2tf", "stack_3tf")),
    ("stack_3tf", ("stack_3tf",)),
    ("fresh_ob", ("fresh_ob",)),
    ("extreme_ob", ("extreme_ob",)),
    ("sweep_then_bos", ("sweep_then_bos",)),
    ("fvg", ("fvg",)),
    ("major_structure_break", ("major_structure_break",)),
    ("inducement", ("inducement",)),
    ("premium_discount", ("premium_discount",)),
    ("corrective_return", ("corrective_return",)),
    ("mitigated_left_zone", ("mitigated_left_zone",)),
    ("preferred_session", ("preferred_session",)),
    ("v_reversal_penalty", ("v_reversal_penalty",)),
    ("counter_trend_penalty", ("counter_trend_penalty",)),
)
REPORT_CRITERIA = [name for name, _ in CRITERIA[:12]]  # raporda analiz edilenler
CRITERIA_COLUMNS = ["crit_" + name for name, _ in CRITERIA]


def criteria_flags(score_breakdown):
    """score_breakdown ([{criterion, points}, ...]) → {crit_<ad>: 0/1}."""
    present = {item.get("criterion") for item in (score_breakdown or []) if isinstance(item, dict)}
    return {"crit_" + name: int(any(key in present for key in keys)) for name, keys in CRITERIA}


# ------------------------------------------------------------------ düzleştirme ve istatistik
def flatten(trades):
    """İşlem sonuçlarını (mod × varyant) satırlara çevirir; yalnızca dolmuş işlemler."""
    rows = []
    for trade in trades:
        if trade.get("status") != "FILLED":
            continue
        for variant, outcome in sorted(trade["variants"].items()):
            row = {key: trade.get(key) for key in (
                "mode", "symbol", "direction", "poi_tf", "grade", "score", "first_seen_t", "actionable",
                "distance_pct", "order_t", "fill_t", "entry", "stop", "tp1", "tp2", "rr_tp1", "rr_tp2", "stop_pct",
                "confirm_t", "confirm_status", "ltf_tf")}
            row.update(criteria_flags(trade.get("score_breakdown")))
            row.update(outcome)
            row["variant"] = variant
            row["hypothesis"] = "base"
            rows.append(row)
    return rows


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def stats(rows):
    """Bir işlem satırı kümesi için özet istatistikler (net ve brüt)."""
    n = len(rows)
    net = [r["r_net"] for r in rows]
    gross = [r["r_gross"] for r in rows]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value <= 0]
    ordered = sorted(rows, key=lambda r: (r["exit_t"], r["symbol"], r["first_seen_t"]))
    equity = peak = drawdown = 0.0
    streak = longest = 0
    for row in ordered:
        equity += row["r_net"]
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if row["r_net"] <= 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    mean = _mean(net)
    variance = sum((value - mean) ** 2 for value in net) / (n - 1) if n > 1 else 0.0
    timeouts = [r for r in rows if r["exit_reason"] == "TIMEOUT"]
    return {
        "n": n, "winrate": len(wins) / n * 100.0 if n else 0.0,
        "avg_win": _mean(wins), "avg_loss": _mean(losses),
        "avg_net": mean, "avg_gross": _mean(gross),
        "expectancy": (len(wins) / n * _mean(wins) + len(losses) / n * _mean(losses)) if n else 0.0,
        "total_net": sum(net), "total_gross": sum(gross),
        "max_dd": drawdown, "longest_loss_streak": longest,
        "se": math.sqrt(variance / n) if n > 1 else 0.0,
        "timeouts": len(timeouts), "timeout_r": sum(r["r_net"] for r in timeouts),
        "fees": sum(r["fee_r"] for r in rows), "slip": sum(r["slip_r"] for r in rows),
        "funding": sum(r["funding_r"] for r in rows),
        "exits": dict(Counter(r["exit_reason"] for r in rows)),
    }


def rr_bucket(row):
    value = row.get("rr_tp2")
    if value is None:
        return "—"
    return "<3" if value < 3 else "3–5" if value < 5 else "5–10" if value < 10 else ">10"


def stop_bucket(row):
    value = row.get("stop_pct")
    if value is None:
        return "—"
    return "<%0.5" if value < 0.5 else "%0.5–1" if value <= 1.0 else ">%1"


BREAKDOWNS = (
    ("Not", lambda r: r["grade"] or "-", ["A", "B", "C", "-"]),
    ("POI TF", lambda r: r["poi_tf"], ["4h", "1h"]),
    ("Yön", lambda r: r["direction"], ["BULLISH", "BEARISH"]),
    ("Sembol", lambda r: r["symbol"], None),
    ("R:R (TP2)", rr_bucket, ["<3", "3–5", "5–10", ">10"]),
    ("Stop genişliği", stop_bucket, ["<%0.5", "%0.5–1", ">%1"]),
    ("Actionable", lambda r: "evet" if r.get("actionable", True) else "hayır", ["evet", "hayır"]),
)


def periods(window):
    """(ad, since, until) üçlüleri: ilk %60 ve son %40 (setup'ın ilk görülme zamanına göre)."""
    split = split_time(window)
    return [("İlk %60", None, split), ("Son %40", split, None)]


def split_time(window):
    return window["t_start"] + SPLIT_RATIO * (window["t_end"] - window["t_start"])


def select(rows, mode=None, variant=None, since=None, until=None, hypothesis="base"):
    """Satır filtresi. ``hypothesis="base"`` (varsayılan) yalnızca mevcut strateji satırlarını seçer; None hepsini."""
    return [r for r in rows
            if (mode is None or r["mode"] == mode) and (variant is None or r["variant"] == variant)
            and (hypothesis is None or r.get("hypothesis", "base") == hypothesis)
            and (since is None or r["first_seen_t"] >= since) and (until is None or r["first_seen_t"] < until)]


# ------------------------------------------------------------------ Markdown
def _fmt(value, digits=2):
    return "—" if value is None else ("{:.%df}" % digits).format(value)


def _date(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def main_table(rows, trades, since=None, until=None):
    lines = ["| Mod | Varyant | İşlem | Dolmayan/iptal | Win % | Ort. kazanç R | Ort. kayıp R | Ort. R net (±SE) | "
             "Ort. R brüt | Toplam R net | Toplam R brüt | Max DD (R) | En uzun kayıp serisi | TIMEOUT (n / R) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        mode_trades = [t for t in trades if t["mode"] == mode and (since is None or t["first_seen_t"] >= since)
                       and (until is None or t["first_seen_t"] < until)]
        unfilled = sum(1 for t in mode_trades if t["status"] != "FILLED")
        for variant in VARIANTS:
            s = stats(select(rows, mode, variant, since, until))
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} ± {} | {} | {} | {} | {} | {} | {} / {} |".format(
                mode, VARIANT_LABEL[variant], s["n"], unfilled, _fmt(s["winrate"], 1), _fmt(s["avg_win"]),
                _fmt(s["avg_loss"]), _fmt(s["avg_net"], 3), _fmt(s["se"], 3), _fmt(s["avg_gross"], 3),
                _fmt(s["total_net"]), _fmt(s["total_gross"]), _fmt(s["max_dd"]), s["longest_loss_streak"],
                s["timeouts"], _fmt(s["timeout_r"])))
    return lines


def status_table(trades, since=None, until=None):
    lines = ["| Mod | Durum | Adet |", "|---|---|---:|"]
    for mode in MODES:
        counter = Counter(t["status"] for t in trades if t["mode"] == mode
                          and (since is None or t["first_seen_t"] >= since)
                          and (until is None or t["first_seen_t"] < until))
        for status, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
            lines.append("| {} | {} | {} |".format(mode, status, count))
    return lines


def breakdown_table(rows, mode, variant, title, key_fn, order):
    groups = {}
    for row in select(rows, mode, variant):
        groups.setdefault(key_fn(row), []).append(row)
    keys = [k for k in (order or sorted(groups)) if k in groups] + \
           [k for k in sorted(groups) if order and k not in order]
    lines = ["| {} | İşlem | Win % | Ort. R net | Ort. R brüt | Toplam R net | Toplam R brüt |".format(title),
             "|---|---:|---:|---:|---:|---:|---:|"]
    for key in keys:
        s = stats(groups[key])
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            key, s["n"], _fmt(s["winrate"], 1), _fmt(s["avg_net"], 3), _fmt(s["avg_gross"], 3),
            _fmt(s["total_net"]), _fmt(s["total_gross"])))
    if not keys:
        lines.append("| — | 0 | — | — | — | — | — |")
    return lines


def build_markdown(trades, window, meta=None):
    rows = flatten(trades)
    split = split_time(window)
    meta = meta or {}
    lines = ["# Phantom SMC Backtest Raporu (Binance USDⓈ-M perpetual)", "", "## Özet", "",
             "- Dönem: {} → {} (UTC), adım: {} saat".format(_date(window["t_start"]), _date(window["t_end"]),
                                                          window["step_s"] // 3600),
             "- Setup sayısı (tekil POI): {}".format(len({(t["symbol"], tuple(t["key"])) for t in trades})),
             "- Dolan işlem: risk {}, confirmation {}".format(
                 sum(1 for t in trades if t["mode"] == "risk" and t["status"] == "FILLED"),
                 sum(1 for t in trades if t["mode"] == "confirmation" and t["status"] == "FILLED")),
             "- Semboller: {}".format(", ".join(meta.get("symbols", [])) or "—"),
             "- Maliyet parametreleri: maker %{}, taker %{}, kayma %{}".format(
                 config.BT_FEE_MAKER_PCT, config.BT_FEE_TAKER_PCT, config.BT_SLIPPAGE_PCT),
             "", "## Varsayımlar", ""]
    lines.extend("- " + note for note in NOTES)
    lines.extend(["", "## Tüm dönem — mod × varyant (maliyetli = net, maliyetsiz = brüt)", ""])
    lines.extend(main_table(rows, trades))
    lines.extend(["", "### Dolmayan / iptal / elenen setup'lar", ""])
    lines.extend(status_table(trades))
    lines.extend(["", "## Kırılımlar (tüm dönem)", ""])
    for mode in MODES:
        for variant in VARIANTS:
            lines.extend(["", "### {} — {}".format(mode, VARIANT_LABEL[variant]), ""])
            for title, key_fn, order in BREAKDOWNS:
                lines.extend(breakdown_table(rows, mode, variant, title, key_fn, order))
                lines.append("")
    lines.extend(["", "## Doğrulama: ilk %60 / son %40", "",
                  "- İlk dönem: {} → {} ; son dönem: {} → {} (setup'ın ilk görülme zamanına göre bölünür)".format(
                      _date(window["t_start"]), _date(split), _date(split), _date(window["t_end"])), ""])
    lines.extend(["### İlk dönem (%60)", ""])
    lines.extend(main_table(rows, trades, until=split))
    lines.extend(["", "### Son dönem (%40)", ""])
    lines.extend(main_table(rows, trades, since=split))
    import analysis_bt  # geç içe aktarma: analysis_bt bu modülü kullanır
    lines.append("")
    lines.extend(analysis_bt.criteria_markdown(analysis_bt.criteria_stats(rows, window)))
    lines.extend(["", "### Maliyet bileşenleri (tüm dönem, toplam R)", "",
                  "| Mod | Varyant | Ücret | Kayma | Funding |", "|---|---|---:|---:|---:|"])
    for mode in MODES:
        for variant in VARIANTS:
            s = stats(select(rows, mode, variant))
            lines.append("| {} | {} | {} | {} | {} |".format(mode, VARIANT_LABEL[variant], _fmt(s["fees"]),
                                                              _fmt(s["slip"]), _fmt(s["funding"])))
    lines.extend(["", "Bu çıktı geçmiş veriyle yapılmış simülasyondur, yatırım tavsiyesi değildir. İşlem kararı kullanıcıya aittir.", ""])
    return "\n".join(lines)


# ------------------------------------------------------------------ CSV / dosya
TRADE_COLUMNS = ["mode", "variant", "symbol", "direction", "poi_tf", "grade", "score", "first_seen_t", "actionable",
                 "distance_pct", "order_t", "confirm_t", "confirm_status", "ltf_tf", "fill_t", "entry", "stop",
                 "tp1", "tp2", "rr_tp1", "rr_tp2", "stop_pct", "exit_reason", "exit_t", "hold_hours", "r_gross",
                 "r_net", "fee_r", "slip_r", "funding_r"] + CRITERIA_COLUMNS
SUMMARY_COLUMNS = ["period", "mode", "variant", "n", "unfilled", "winrate", "avg_win", "avg_loss", "avg_net", "se",
                   "avg_gross", "total_net", "total_gross", "max_dd", "longest_loss_streak", "timeouts", "timeout_r"]


def write_reports(trades, window, out_dir=None, meta=None, stamp=None):
    """bt_report_*.md, bt_trades_*.csv ve bt_summary_*.csv yazar; dosya yollarını döndürür."""
    out_dir = out_dir or config.BT_RESULTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M_UTC")
    rows = flatten(trades)
    split = split_time(window)
    md_path = os.path.join(out_dir, "bt_report_{}.md".format(stamp))
    with open(md_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(build_markdown(trades, window, meta))
    trades_path = os.path.join(out_dir, "bt_trades_{}.csv".format(stamp))
    with open(trades_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRADE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["first_seen_t"], r["symbol"], r["mode"], r["variant"])):
            writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in TRADE_COLUMNS})
    summary_path = os.path.join(out_dir, "bt_summary_{}.csv".format(stamp))
    with open(summary_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for period, since, until in (("all", None, None), ("first_60", None, split), ("last_40", split, None)):
            for mode in MODES:
                unfilled = sum(1 for t in trades if t["mode"] == mode and t["status"] != "FILLED"
                               and (since is None or t["first_seen_t"] >= since)
                               and (until is None or t["first_seen_t"] < until))
                for variant in VARIANTS:
                    s = stats(select(rows, mode, variant, since, until))
                    record = {"period": period, "mode": mode, "variant": variant, "unfilled": unfilled}
                    record.update({key: s[key] for key in SUMMARY_COLUMNS if key in s})
                    writer.writerow(record)
    latest = os.path.join(out_dir, "bt_latest.md")
    with open(latest, "w", encoding="utf-8", newline="") as handle:
        handle.write(open(md_path, encoding="utf-8").read())
    return {"md": md_path, "trades": trades_path, "summary": summary_path, "latest": latest}
