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
MIN_TRADES_FIRST = 30  # eşik önerisi için ilk dönemde asgari işlem
MIN_TRADES_LAST = 10  # son dönemde "doğrulandı" demek için asgari işlem
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
            row.update(outcome)
            row["variant"] = variant
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


def split_time(window):
    return window["t_start"] + SPLIT_RATIO * (window["t_end"] - window["t_start"])


def select(rows, mode=None, variant=None, since=None, until=None):
    return [r for r in rows
            if (mode is None or r["mode"] == mode) and (variant is None or r["variant"] == variant)
            and (since is None or r["first_seen_t"] >= since) and (until is None or r["first_seen_t"] < until)]


# ------------------------------------------------------------------ eşik önerisi (yalnız ilk dönem)
GRID = {"min_score": (0, 45, 60, 75), "min_rr": (0, 3, 5, 8), "min_stop_pct": (0.0, 0.3, 0.5),
        "max_distance_pct": (None, 10.0, 5.0)}


def passes(row, f):
    distance = row.get("distance_pct")
    return ((row["score"] or 0) >= f["min_score"] and (row["rr_tp2"] or 0) >= f["min_rr"]
            and (row["stop_pct"] or 0) >= f["min_stop_pct"]
            and (f["max_distance_pct"] is None or distance is None or distance <= f["max_distance_pct"]))


def suggest(rows_first, rows_last):
    """Her mod×varyant için ilk dönemde (n >= MIN_TRADES_FIRST) en yüksek net ortalama R veren eşikler; son dönemde kontrol."""
    out = []
    for mode in MODES:
        for variant in VARIANTS:
            first = select(rows_first, mode, variant)
            last = select(rows_last, mode, variant)
            best = None
            for min_score in GRID["min_score"]:
                for min_rr in GRID["min_rr"]:
                    for min_stop in GRID["min_stop_pct"]:
                        for max_dist in GRID["max_distance_pct"]:
                            f = {"min_score": min_score, "min_rr": min_rr, "min_stop_pct": min_stop,
                                 "max_distance_pct": max_dist}
                            subset = [r for r in first if passes(r, f)]
                            if len(subset) < MIN_TRADES_FIRST:
                                continue
                            avg = _mean([r["r_net"] for r in subset])
                            if best is None or (avg, len(subset)) > (best[0], best[1]):
                                best = (avg, len(subset), f)
            entry = {"mode": mode, "variant": variant, "baseline_first": stats(first), "baseline_last": stats(last)}
            if best is None:
                entry["filter"] = None
            else:
                f = best[2]
                entry["filter"] = f
                entry["first"] = stats([r for r in first if passes(r, f)])
                entry["last"] = stats([r for r in last if passes(r, f)])
                entry["verdict"] = verdict(entry)
            out.append(entry)
    return out


def verdict(entry):
    last = entry["last"]
    if last["n"] < MIN_TRADES_LAST:
        return "doğrulanamadı (son dönemde işlem az)"
    if last["avg_net"] > 0 and last["avg_net"] >= entry["baseline_last"]["avg_net"]:
        return "son dönemde de pozitif ve taban çizgisinden iyi"
    if last["avg_net"] > 0:
        return "son dönemde pozitif ama taban çizgisinden iyi değil"
    return "son dönemde tutmadı (aşırı uyum olasılığı)"


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


def filter_text(f):
    return "min puan {}, min R:R {}, min stop% {}, max mesafe% {}".format(
        f["min_score"], f["min_rr"], f["min_stop_pct"], "yok" if f["max_distance_pct"] is None else f["max_distance_pct"])


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
    first_rows, last_rows = select(rows, until=split), select(rows, since=split)
    lines.extend(["", "### Eşik önerileri (yalnızca ilk dönemden; son dönemde kontrol)", "",
                  "Izgara: puan {}, R:R {}, stop% {}, mesafe% {}. Ölçüt: ilk dönemde en yüksek net ortalama R "
                  "(en az {} işlem). Küçük örneklemde öneriler aşırı uyum içerebilir; yalnızca son dönem sonucu "
                  "doğrulama sayılır.".format(GRID["min_score"], GRID["min_rr"], GRID["min_stop_pct"],
                                              GRID["max_distance_pct"], MIN_TRADES_FIRST), "",
                  "| Mod | Varyant | Önerilen eşikler | İlk dönem (n / ort. R net) | Son dönem (n / ort. R net) | "
                  "Son dönem taban (n / ort. R net) | Sonuç |", "|---|---|---|---:|---:|---:|---|"])
    for entry in suggest(first_rows, last_rows):
        base = entry["baseline_last"]
        if entry["filter"] is None:
            lines.append("| {} | {} | öneri yok (ilk dönemde yeterli işlem yok) | — | — | {} / {} | — |".format(
                entry["mode"], VARIANT_LABEL[entry["variant"]], base["n"], _fmt(base["avg_net"], 3)))
            continue
        lines.append("| {} | {} | {} | {} / {} | {} / {} | {} / {} | {} |".format(
            entry["mode"], VARIANT_LABEL[entry["variant"]], filter_text(entry["filter"]),
            entry["first"]["n"], _fmt(entry["first"]["avg_net"], 3), entry["last"]["n"],
            _fmt(entry["last"]["avg_net"], 3), base["n"], _fmt(base["avg_net"], 3), entry["verdict"]))
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
                 "r_net", "fee_r", "slip_r", "funding_r"]
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
