"""Backtest raporu (FINAL_SPEC §22): strike rate, ortalama R, expectancy (FM-04), max drawdown (FM-10), toplam R, % getiri;
ek: profit factor, VALID/INVALID × WIN/LOSS günlüğü, POI kriterlerinin isabete katkısı, Q-M5 (M15 hedefi 4R'den yakın) listesi,
dolum modeli sayaçları, Q-L3 sınır sayaçları. Yalnızca raporlar — strateji davranışını değiştirmez."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from ..data.tz import ISTANBUL
from ..risk.stops import Side
from .engine import BacktestResult, Trade

FOUR_R = Decimal(4)
D0 = Decimal(0)


def _mean(xs: Sequence[Decimal]) -> Decimal:
    return sum(xs, D0) / len(xs) if xs else D0


@dataclass(frozen=True)
class Metrics:
    n: int
    wins: int
    losses: int
    strike_rate: Decimal            # %
    avg_r: Decimal                  # tüm işlemlerin ortalama R'si (brüt, komisyonsuz)
    avg_r_net: Decimal              # komisyon dahil
    avg_win_r: Decimal
    avg_loss_r: Decimal
    expectancy_r: Decimal           # FM-04: AvgWin·P(win) + AvgLoss·P(loss)  (R, brüt)
    expectancy_r_net: Decimal
    profit_factor: Optional[Decimal]
    total_r: Decimal
    total_r_net: Decimal
    net_pnl: Decimal
    commission: Decimal
    return_pct: Decimal
    max_dd_amount: Decimal          # kapanış bazlı bakiye eğrisi (açık pozisyon dalgalanması yok)
    max_dd_pct: Decimal
    max_dd_r: Decimal               # kümülatif R eğrisinde (brüt) tepe-dip
    max_consec_losses: int


def compute_metrics(res: BacktestResult) -> Metrics:
    tr = res.trades
    n = len(tr)
    wins = [t for t in tr if t.win]
    losses = [t for t in tr if not t.win]
    r = [t.r_gross for t in tr]
    rn = [t.r_net for t in tr]
    p_w = Decimal(len(wins)) / n if n else D0
    aw = _mean([t.r_gross for t in wins])
    al = _mean([t.r_gross for t in losses])
    gp = sum((t.net_pnl for t in wins), D0)
    gl = -sum((t.net_pnl for t in losses), D0)
    peak, dd_amt, dd_pct = res.initial_balance, D0, D0
    for _, bal in res.equity:
        peak = max(peak, bal)
        d = peak - bal
        if d > dd_amt:
            dd_amt, dd_pct = d, d / peak * 100
    cum, cpeak, dd_r = D0, D0, D0
    for x in r:
        cum += x
        cpeak = max(cpeak, cum)
        dd_r = max(dd_r, cpeak - cum)
    streak = mx = 0
    for t in tr:
        streak = 0 if t.win else streak + 1
        mx = max(mx, streak)
    net = sum((t.net_pnl for t in tr), D0)
    return Metrics(n, len(wins), len(losses), p_w * 100, _mean(r), _mean(rn), aw, al,
                   aw * p_w + al * (1 - p_w) if n else D0, _mean(rn), (gp / gl) if gl > 0 else None,
                   sum(r, D0), sum(rn, D0), net, sum((t.commission for t in tr), D0),
                   net / res.initial_balance * 100 if res.initial_balance else D0, dd_amt, dd_pct, dd_r, mx)


def journal_matrix(res: BacktestResult) -> dict[str, int]:
    """VALID/INVALID × WIN/LOSS (§24 journal_tag). Backtest yalnızca plana uygun işlem açar → INVALID_* her zaman 0 (Q-B3)."""
    c = Counter(t.journal_tag for t in res.trades)
    return {k: c.get(k, 0) for k in ("VALID_WIN", "VALID_LOSS", "INVALID_WIN", "INVALID_LOSS")}


def criteria_contribution(trades: Sequence[Trade]) -> list[dict]:
    """Her POI kriteri için: kazanılan / kazanılmayan / bilinmeyen işlemlerde isabet oranı (puan katkısı: fark, yüzde puanı)."""
    acc: dict[str, dict] = defaultdict(lambda: {"w": Decimal(0), "yes": [0, 0], "no": [0, 0], "unk": [0, 0]})
    for t in trades:
        for name, weight, earned in t.intent.criteria:
            a = acc[name]
            a["w"] = weight
            k = "unk" if earned is None else ("yes" if earned else "no")
            a[k][0] += 1
            a[k][1] += 1 if t.win else 0
    rows = []
    for name, a in acc.items():
        rate = lambda v: (Decimal(v[1]) / v[0] * 100) if v[0] else None
        ry, rno = rate(a["yes"]), rate(a["no"])
        rows.append({"criterion": name, "weight": a["w"], "n_yes": a["yes"][0], "win_yes": a["yes"][1], "rate_yes": ry,
                     "n_no": a["no"][0], "win_no": a["no"][1], "rate_no": rno, "n_unknown": a["unk"][0],
                     "delta_pp": (ry - rno) if ry is not None and rno is not None else None})
    return rows


def m15_closer_than_4r(trades: Sequence[Trade]) -> list[Trade]:
    """Q-M5 (yalnız rapor): M15/ilk hedefi 4R'den yakın olan işlemler."""
    return [t for t in trades if t.m15_target_r is not None and t.m15_target_r < FOUR_R]


def _fmt(x: Optional[Decimal], nd: int = 2) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def exit_reasons(trades: Sequence[Trade]) -> Counter:
    c: Counter = Counter()
    for t in trades:
        for f in t.position.fills:
            c[f.leg + (f" ({f.reason})" if f.reason and f.leg == "STOP" else "")] += 1
    return c


def format_report(res: BacktestResult, tz: ZoneInfo = ISTANBUL) -> str:
    m = compute_metrics(res)
    L: list[str] = []
    a = L.append
    a(f"═══ PHOTON BACKTEST RAPORU ═══  {res.pair}  {res.start:%Y-%m-%d} → {(res.end):%Y-%m-%d} (UTC)")
    a(f"M1 mum sayısı (canlı + warm-up): {res.candles}   Başlangıç bakiyesi: {res.initial_balance:.2f} (VARSAYIM Q-B1)   "
      f"Son bakiye: {res.final_balance:.2f}")
    a("Komisyon: " + (f"IBKR %{res.commission.rate_pct} / emir başına en az {res.commission.min_per_order} {res.commission.currency}; "
                      "her dolum (giriş + her çıkış bacağı) ayrı emir (Q-B2)" if res.commission.included
                      else "komisyon dahil değil (config'de costs.commission yok → 0)"))
    a("Not: tüm istatistikler yalnızca KAPANMIŞ işlemlerdir; bakiye eğrisi işlem kapanışlarında güncellenir (açık işlem dalgalanması yok).")
    a("")
    a("── §22 Metrikler ──")
    a(f"İşlem sayısı: {m.n}  (kazanan {m.wins}, kaybeden {m.losses})   Win = net PnL > 0")
    a(f"Strike rate: %{_fmt(m.strike_rate, 1)}")
    a(f"Ortalama R: {_fmt(m.avg_r)} (brüt) / {_fmt(m.avg_r_net)} (komisyon dahil)   Ort. kazanç R {_fmt(m.avg_win_r)}   Ort. kayıp R {_fmt(m.avg_loss_r)}")
    a(f"Expectancy (FM-04): {_fmt(m.expectancy_r)} R (brüt) / {_fmt(m.expectancy_r_net)} R (komisyon dahil)")
    a(f"Toplam R: {_fmt(m.total_r)} (brüt) / {_fmt(m.total_r_net)} (komisyon dahil)")
    a(f"Net PnL: {m.net_pnl:.2f} (komisyon toplamı {m.commission:.2f})   Getiri: %{_fmt(m.return_pct)}")
    a(f"Max drawdown (FM-10): {m.max_dd_amount:.2f} = %{_fmt(m.max_dd_pct)} (bakiye)  /  {_fmt(m.max_dd_r)} R (kümülatif R)")
    a(f"Profit factor (ek metrik): {_fmt(m.profit_factor)}   En uzun kayıp serisi: {m.max_consec_losses}")
    a("")
    a("── Günlük (journal) VALID/INVALID × WIN/LOSS ──")
    jm = journal_matrix(res)
    a(f"VALID_WIN {jm['VALID_WIN']} | VALID_LOSS {jm['VALID_LOSS']} | INVALID_WIN {jm['INVALID_WIN']} | INVALID_LOSS {jm['INVALID_LOSS']}"
      "   (INVALID = plana aykırı işlem; backtest plana aykırı işlem açmaz → 0, Q-B3)")
    a("")
    a("── Sinyal / emir akışı ──")
    kinds = Counter(e.kind for e in res.events)
    a(f"Sinyal {kinds.get('SIGNAL', 0)} | dolmadan iptal {kinds.get('CANCELLED', 0)} | ret olayı {kinds.get('REJECTED', 0)} | "
      f"dolan {m.n + len(res.open_trades)} | dönem sonunda dolmamış bekleyen emir {res.unfilled_orders} | "
      f"dönem sonunda açık pozisyon {len(res.open_trades)} (istatistiğe dahil değil)")
    rej = Counter(e.reason for e in res.events if e.kind == "REJECTED")
    for k, v in rej.most_common():
        a(f"    ret: {k} × {v}")
    a("")
    a("── Dolum modeli sayaçları (mum içi sıra bilinmiyor; tick yok) ──")
    fs = res.fill_stats
    a(f"Aynı mumda stop+hedef → stop sayıldı: {fs.get('same_candle_stop_first', 0)}")
    a(f"Aynı mumda giriş+stop → giriş dolup stop: {fs.get('entry_and_stop_same_candle', 0)}")
    a(f"Giriş mumunda hedef de görüldü (yok sayıldı): {fs.get('entry_and_target_same_candle_ignored', 0)}")
    a(f"Gap'li stop dolumu (açılış fiyatından): {fs.get('stop_gap_fills', 0)}")
    amb = sum(1 for s in {e.setup.id: e.setup for e in res.events}.values() for n in s.notes if n.startswith("AMBIGUOUS_FILL_VS_TARGET"))
    a(f"Aynı mumda dolum + ilk hedef (iptal yerine dolum işlendi): {amb}")
    a("")
    a("── Trend sınıfı kırılımı ──")
    by: dict[str, list[Trade]] = defaultdict(list)
    for t in res.trades:
        by[t.intent.trend_class].append(t)
    for k, ts in sorted(by.items()):
        a(f"  {k}: {len(ts)} işlem, win %{_fmt(Decimal(sum(t.win for t in ts)) / len(ts) * 100, 1)}, ort. R {_fmt(_mean([t.r_gross for t in ts]))}")
    a("")
    a("── Çıkış dolumları ──")
    for k, v in exit_reasons(res.trades).most_common():
        a(f"  {k}: {v}")
    a("")
    a("── POI kriterlerinin isabete katkısı (kazanılan vs kazanılmayan işlemlerde win oranı) ──")
    a(f"  {'kriter':<24}{'ağırlık':>8}{'n(var)':>8}{'win%':>8}{'n(yok)':>8}{'win%':>8}{'Δpp':>8}{'bilinmiyor':>12}")
    for r in criteria_contribution(res.trades):
        a(f"  {r['criterion']:<24}{_fmt(r['weight'], 1):>8}{r['n_yes']:>8}{_fmt(r['rate_yes'], 1):>8}{r['n_no']:>8}"
          f"{_fmt(r['rate_no'], 1):>8}{_fmt(r['delta_pp'], 1):>8}{r['n_unknown']:>12}")
    a("  (küçük örneklemde Δpp anlamlı değildir; sınıf başına işlem sayısına bakın)")
    a("")
    close = m15_closer_than_4r(res.trades)
    a("── Q-M5: M15/ilk hedefi 4R'den yakın işlemler (yalnız rapor; strateji değişmedi) ──")
    nw = sum(t.win for t in close)
    a(f"Sayı: {len(close)} / {m.n}   kazanan {nw}   kaybeden {len(close) - nw}")
    for t in close:
        a(f"  {t.id}  {t.intent.side.value}  giriş {t.fill_time.astimezone(tz):%m-%d %H:%M}  M15 hedefi {_fmt(t.m15_target_r)}R  "
          f"sonuç {t.outcome} {_fmt(t.r_gross)}R  [{t.intent.trend_class}]")
    a("")
    a("── Q-L3: uygulama sınırlarının etkilediği durumlar ──")
    for k, v in sorted(res.limit_report.items()):
        a(f"  {k}: {v}")
    return "\n".join(L)


TRADE_COLS = ["id", "side", "poi_tf", "trend_class", "session", "signal_time_utc", "fill_time_utc", "close_time_utc",
              "fill_time_istanbul", "entry", "stop", "pip_risk", "lots", "risk_amount", "m15_target_r", "closer_than_4r",
              "r_gross", "r_net", "gross_pnl", "commission", "net_pnl", "balance_before", "balance_after", "outcome",
              "journal_tag", "poi_score", "poi_max_score", "exits", "notes", "news"]


def _trade_row(t: Trade, tz: ZoneInfo) -> dict:
    it = t.intent
    m15r = t.m15_target_r
    return {"id": t.id, "side": it.side.value, "poi_tf": it.poi_tf.value, "trend_class": it.trend_class, "session": it.session,
            "signal_time_utc": it.time.isoformat(), "fill_time_utc": t.fill_time.isoformat(),
            "close_time_utc": t.close_time.isoformat() if t.close_time else "",
            "fill_time_istanbul": t.fill_time.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
            "entry": it.entry, "stop": it.stop, "pip_risk": it.pip_risk, "lots": it.lots, "risk_amount": it.risk_amount,
            "m15_target_r": "" if m15r is None else f"{m15r:.2f}", "closer_than_4r": "" if m15r is None else int(m15r < FOUR_R),
            "r_gross": f"{t.r_gross:.3f}", "r_net": f"{t.r_net:.3f}", "gross_pnl": f"{t.gross_pnl:.2f}",
            "commission": f"{t.commission:.2f}", "net_pnl": f"{t.net_pnl:.2f}", "balance_before": f"{t.balance_before:.2f}",
            "balance_after": f"{t.balance_after:.2f}", "outcome": t.outcome, "journal_tag": t.journal_tag,
            "poi_score": it.poi_score, "poi_max_score": it.poi_max_score,
            "exits": "|".join(f"{f.leg}@{f.price}x{f.lots}" for f in t.position.fills),
            "notes": "|".join(t.position.notes + t.setup.notes), "news": it.news}


def write_outputs(res: BacktestResult, out: Path, tz: ZoneInfo = ISTANBUL) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    p = out / f"{res.pair}_trades.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, TRADE_COLS)
        w.writeheader()
        for t in res.trades:
            w.writerow(_trade_row(t, tz))
    paths["trades"] = p
    p = out / f"{res.pair}_fills.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trade_id", "time_utc", "leg", "price", "lots", "r", "reason"])
        for t in res.trades:
            for f in t.position.fills:
                w.writerow([t.id, f.time.isoformat(), f.leg, f.price, f.lots, f"{f.r:.3f}", f.reason])
    paths["fills"] = p
    p = out / f"{res.pair}_journal.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trade_id", "journal_tag", "fill_time_utc", "r_gross", "poi_score", "criteria_earned", "criteria_not_earned", "rules"])
        for t in res.trades:
            it = t.intent
            w.writerow([t.id, t.journal_tag, t.fill_time.isoformat(), f"{t.r_gross:.3f}", it.poi_score,
                        "|".join(n for n, _, e in it.criteria if e), "|".join(n for n, _, e in it.criteria if e is False),
                        "|".join(it.rules)])
    paths["journal"] = p
    p = out / f"{res.pair}_signals.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_utc", "kind", "setup_id", "reason"])
        for e in res.events:
            w.writerow([e.time.isoformat(), e.kind, e.setup.id, e.reason])
    paths["signals"] = p
    p = out / f"{res.pair}_criteria.csv"
    rows = criteria_contribution(res.trades)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["criterion", "weight", "n_yes", "win_yes", "rate_yes", "n_no", "win_no", "rate_no", "n_unknown", "delta_pp"])
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    paths["criteria"] = p
    p = out / f"{res.pair}_report.txt"
    p.write_text(format_report(res, tz) + "\n", encoding="utf-8")
    paths["report"] = p
    return paths
