"""Backtest raporu (FINAL_SPEC §22): strike rate, ortalama R, expectancy (FM-04), max drawdown (FM-10), toplam R, % getiri;
ek: profit factor, VALID/INVALID × WIN/LOSS günlüğü, POI kriterlerinin isabete katkısı, Q-M5 (M15 hedefi 4R'den yakın) listesi,
dolum modeli sayaçları, Q-L3 sınır sayaçları. Yalnızca raporlar — strateji davranışını değiştirmez."""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta
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


CLASSES = ("PRO", "MIXED", "COUNTER_HTF", "UNKNOWN")


def funnel(res: BacktestResult) -> list[tuple[str, dict]]:
    """Kurulum hunisi: POI tespit → mitigasyon → izin → M1 CHoCH → giriş zonu → kapılar → sinyal → dolum. Sayılar OLAY sayısıdır
    (bir kurulum birden çok kez mitige olabilir); ilk satır benzersiz kurulum sayısıdır. Trend sınıfı olayın anındaki sınıftır."""
    rows: list[tuple[str, dict]] = []
    cnt: dict[str, Counter] = defaultdict(Counter)
    for s in res.setups:
        for _, stage, cls, _ in s.trace:
            cnt[stage][cls] += 1
    uniq = len(res.setups)
    born = sum(1 for s in res.setups if not s.poi.warmup)
    rows.append((f"1. POI izlenen kurulum (benzersiz; dönem içinde doğan {born})", {"TOPLAM": uniq}))

    def add(label, stage):
        c = cnt.get(stage, Counter())
        rows.append((label, {**{k: c.get(k, 0) for k in CLASSES}, "TOPLAM": sum(c.values())}))
    add("2. Mitigasyon (POI/rafine zona dokunuş)", "MITIGATED")
    for st in sorted(k for k in cnt if k.startswith("PERMISSION_WAIT:")):
        add(f"   izin bekleme: {st.split(':', 1)[1]}", st)
    add("3. İzin geçti (EN-R006/Q-P1)", "PERMISSION_OK")
    add("4. M1 CHoCH (mitigasyondan sonra)", "CHOCH")
    add("   giriş zonu YOK (NO_ENTRY_ZONE)", "NO_ENTRY_ZONE")
    add("5. Giriş zonu bulundu", "ENTRY_ZONE_OK")
    for st in sorted(k for k in cnt if k.startswith("GATE_FAIL:")):
        add(f"   kapı elendi: {st.split(':', 1)[1]} (aynı anda birden çok kapı olabilir)", st)
    add("   aynı giriş kutusu: başka POI'ye bağlandı (SAME_ENTRY_BOX)", "SAME_ENTRY_BOX")
    add("6. Sinyal", "SIGNAL")
    can = Counter(e.setup.trend_class for e in res.events if e.kind == "CANCELLED")
    rows.append(("   dolmadan iptal", {**{k: can.get(k, 0) for k in CLASSES}, "TOPLAM": sum(can.values())}))
    fl = Counter(t.intent.trend_class for t in res.trades + res.open_trades)
    rows.append(("7. Dolum (işlem)", {**{k: fl.get(k, 0) for k in CLASSES}, "TOPLAM": sum(fl.values())}))
    return rows


def monthly_funnel(res: BacktestResult) -> list[dict]:
    """Ay bazında huni (UTC ay). Sıfır işlemli ayların nedeni için: hangi aşamada tıkandığı `neden` alanında."""
    m: dict[str, Counter] = defaultdict(Counter)
    for s in res.setups:
        if not s.poi.warmup:
            m[f"{s.poi.created_time:%Y-%m}"]["poi"] += 1
        for t, stage, _, _ in s.trace:
            k = f"{t:%Y-%m}"
            if stage.startswith("PERMISSION_WAIT"):
                m[k]["izin_bekleme"] += 1
            elif stage.startswith("GATE_FAIL:"):
                g = stage.split(":", 1)[1]
                m[k]["gate_" + (g if g in ("range_filter", "liquidation", "session") else "diger")] += 1
            else:
                m[k][stage] += 1
    for e in res.events:
        if e.kind == "CANCELLED":
            m[f"{e.time:%Y-%m}"]["iptal"] += 1
    for t in res.trades + res.open_trades:
        m[f"{t.fill_time:%Y-%m}"]["dolum"] += 1
    if res.start and res.end:                                            # boş ayları da göster
        y, mo = res.start.year, res.start.month
        while (y, mo) <= ((res.end - timedelta(seconds=1)).year, (res.end - timedelta(seconds=1)).month):
            m.setdefault(f"{y}-{mo:02d}", Counter())
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    rows = []
    for k in sorted(m):
        c = m[k]
        if c["MITIGATED"] == 0:
            why = "mitigasyon yok (izlenen POI'ye dokunuş olmadı / seans-kilit)"
        elif c["PERMISSION_OK"] == 0:
            why = "izin (EN-R006/Q-P1) geçmedi"
        elif c["CHOCH"] == 0:
            why = "mitigasyon sonrası M1 CHoCH yok"
        elif c["SIGNAL"] == 0:
            why = "tüm girişler kapılarda elendi"
        elif c["dolum"] == 0:
            why = "sinyal var, dolum yok (iptal/dolmadı)"
        else:
            why = ""
        rows.append({"ay": k, "poi": c["poi"], "mitigasyon": c["MITIGATED"], "izin_bekleme": c["izin_bekleme"],
                     "izin_ok": c["PERMISSION_OK"], "choch": c["CHOCH"], "giris_zonu": c["ENTRY_ZONE_OK"],
                     "range_filter": c["gate_range_filter"], "liquidation": c["gate_liquidation"], "session": c["gate_session"],
                     "diger_kapi": c["gate_diger"], "sinyal": c["SIGNAL"], "iptal": c["iptal"], "dolum": c["dolum"], "neden": why})
    return rows


def format_monthly_funnel(res: BacktestResult) -> str:
    cols = [("ay", 8), ("poi", 5), ("mitigasyon", 11), ("izin_bekleme", 13), ("izin_ok", 8), ("choch", 6), ("giris_zonu", 11),
            ("range_filter", 13), ("liquidation", 12), ("session", 8), ("diger_kapi", 11), ("sinyal", 7), ("iptal", 6), ("dolum", 6)]
    L = ["  " + "".join(f"{n:>{w}}" for n, w in cols) + "  neden (dolum=0 ise)"]
    for r in monthly_funnel(res):
        L.append("  " + "".join(f"{r[n]:>{w}}" for n, w in cols) + (f"  {r['neden']}" if r["dolum"] == 0 else ""))
    return "\n".join(L)


def stop_quick_ratio(trades: Sequence[Trade], minutes: int = 5) -> tuple[int, int]:
    """Kaybeden işlemlerden dolumdan ≤ `minutes` dk içinde kapananlar: (sayı, kaybeden sayısı). Süre mum açılışlarından ölçülür."""
    losers = [t for t in trades if not t.win and t.close_time is not None]
    return sum(1 for t in losers if (t.close_time - t.fill_time) <= timedelta(minutes=minutes)), len(losers)


def format_funnel(res: BacktestResult) -> str:
    L = [f"  {'aşama':<78}" + "".join(f"{c:>13}" for c in CLASSES + ("TOPLAM",))]
    for label, d in funnel(res):
        L.append(f"  {label:<78}" + "".join(f"{d.get(c, 0) if c in d else '':>13}" for c in CLASSES + ("TOPLAM",)))
    return "\n".join(L)


_IDX = re.compile(r"@idx(\d+)")


def diagnostics_text(res: BacktestResult, tz: ZoneInfo = ISTANBUL, per_cat: int = 6) -> str:
    """Teşhis: range_filter ve NO_ENTRY_ZONE örnekleri (zaman, range, zon EQ %), NO_ENTRY_ZONE pencere istatistikleri."""
    T = res.runner.struct[res.runner.profile.mid].T if res.runner is not None else []

    def conv(txt: str) -> str:
        return _IDX.sub(lambda m: f"@idx{m.group(1)}({T[int(m.group(1))].strftime('%m-%d %H:%M')}Z)" if int(m.group(1)) < len(T) else m.group(0), txt)
    L: list[str] = []
    recs = [(t, st, cls, d, s) for s in res.setups for (t, st, cls, d) in s.trace]
    for title, stage in (("GATE_FAIL:range_filter", "GATE_FAIL:range_filter"), ("NO_ENTRY_ZONE", "NO_ENTRY_ZONE")):
        rs = sorted((r for r in recs if r[1] == stage), key=lambda r: r[0])
        L.append(f"── {title}: {len(rs)} olay, {len({r[4].id for r in rs})} benzersiz kurulum ──")
        byc = Counter(r[2] for r in rs)
        L.append("   sınıf kırılımı: " + ", ".join(f"{k}={v}" for k, v in byc.most_common()))
        if stage == "NO_ENTRY_ZONE":
            legs = [int(m.group(1)) for r in rs if (m := re.search(r"leg_len=(\d+)", r[3]))]
            ret = [int(m.group(1)) for r in rs if (m := re.search(r"retire_after=(\d+)", r[3]))]
            if legs and ret:
                L.append(f"   CHoCH bacağı (origin→kırılım) uzunluğu: min {min(legs)}, medyan {sorted(legs)[len(legs) // 2]}, max {max(legs)} M1 mum; "
                         f"retire_after={ret[0]} aşan: {sum(1 for x in legs if x > ret[0])}")
            zw = [(int(re.search(r'zones_in_window=(\d+)', r[3]).group(1)), int(re.search(r'same_kind=(\d+)', r[3]).group(1))) for r in rs]
            L.append(f"   pencerede hiç zon yok: {sum(1 for a, _ in zw if a == 0)}; zon var ama yön uyumlu yok: {sum(1 for a, b in zw if a > 0 and b == 0)}; "
                     f"yön uyumlu zon var ama CHoCH'a bağlı değil: {sum(1 for _, b in zw if b > 0)}")
        pro = [r for r in rs if r[2] == "PRO"]
        pick = (pro[:per_cat // 2 + 1] + [r for r in rs if r[2] != "PRO"])[:per_cat] if stage != "NO_ENTRY_ZONE" else rs[:per_cat]
        if stage == "NO_ENTRY_ZONE":
            pick = (pro[:3] + [r for r in rs if r[2] != "PRO"])[:per_cat]
        for t, st, cls, d, s in pick:
            L.append(f"   [{cls}] {t.astimezone(tz):%Y-%m-%d %H:%M} ({tz.key}) {s.id} {s.direction.value}: {conv(d)}")
        L.append("")
    return "\n".join(L)


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
    a("── Kurulum hunisi (olay sayıları; ayrıntı ve örnekler: *_diag.txt) ──")
    a(format_funnel(res))
    a("")
    a("── Ay bazında huni (UTC ay; olay sayıları) ──")
    a(format_monthly_funnel(res))
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
    if any(k in fs for k in ("news_exits", "news_orders_cancelled", "blackout_fill_blocked")):
        a(f"Haber penceresi: iptal edilen bekleyen emir {fs.get('news_orders_cancelled', 0)}, piyasadan kapatılan pozisyon {fs.get('news_exits', 0)}; "
          f"rollover saatinde ertelenen dolum denemesi (mum sayısı) {fs.get('blackout_fill_blocked', 0)}")
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


TRADE_COLS = ["no", "id", "side", "poi_tf", "trend_class", "session", "signal_candle_open_utc", "signal_time_utc", "fill_candle_open_utc", "fill_after_signal_min", "close_time_utc",
              "fill_time_istanbul", "entry", "stop", "pip_risk", "lots", "risk_amount", "m15_target_r", "closer_than_4r",
              "r_gross", "r_net", "gross_pnl", "commission", "net_pnl", "balance_before", "balance_after", "outcome",
              "journal_tag", "poi_score", "poi_max_score", "exits", "notes", "news"]


def _trade_row(t: Trade, tz: ZoneInfo) -> dict:
    it = t.intent
    m15r = t.m15_target_r
    return {"no": t.no, "id": t.id, "side": it.side.value, "poi_tf": it.poi_tf.value, "trend_class": it.trend_class, "session": it.session,
            "signal_candle_open_utc": (it.time - timedelta(minutes=1)).isoformat(), "signal_time_utc": it.time.isoformat(),
            "fill_candle_open_utc": t.fill_time.isoformat(), "fill_after_signal_min": int((t.fill_time - it.time).total_seconds() // 60),
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
        w.writerow(["trade_no", "trade_id", "time_utc", "leg", "price", "lots", "r", "reason"])
        for t in res.trades:
            for f in t.position.fills:
                w.writerow([t.no, t.id, f.time.isoformat(), f.leg, f.price, f.lots, f"{f.r:.3f}", f.reason])
    paths["fills"] = p
    p = out / f"{res.pair}_journal.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["trade_no", "trade_id", "journal_tag", "fill_time_utc", "r_gross", "poi_score", "criteria_earned", "criteria_not_earned", "rules"])
        for t in res.trades:
            it = t.intent
            w.writerow([t.no, t.id, t.journal_tag, t.fill_time.isoformat(), f"{t.r_gross:.3f}", it.poi_score,
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
    p = out / f"{res.pair}_diag.txt"
    p.write_text(diagnostics_text(res, tz), encoding="utf-8")
    paths["diag"] = p
    p = out / f"{res.pair}_setups.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["setup_id", "direction", "time_utc", "stage", "trend_class", "detail"])
        for st in res.setups:
            for t, stage, cls, d in st.trace:
                w.writerow([st.id, st.direction.value, t.isoformat(), stage, cls, d])
    paths["setups"] = p
    p = out / f"{res.pair}_report.txt"
    p.write_text(format_report(res, tz) + "\n", encoding="utf-8")
    paths["report"] = p
    return paths


def period_diagnostics(res: BacktestResult, d0: datetime, d1: datetime, tz: ZoneInfo = ISTANBUL, max_lines: int = 600) -> str:
    """Belirli dönem için teşhis: (1) dönem içi huni, (2) gün gün TF trend durumu (00/08/16 UTC), (3) dönemde yaşayan POI'ler ve akıbetleri,
    (4) kurulum izleri (aşama aşama, ayrıntılı). Yalnızca raporlar."""
    L: list[str] = [f"═══ DÖNEM TEŞHİSİ {d0:%Y-%m-%d} → {(d1 - timedelta(seconds=1)):%Y-%m-%d} (UTC) ═══", ""]
    # 1) huni
    cnt: dict[str, Counter] = defaultdict(Counter)
    for s in res.setups:
        for t, stage, cls, _ in s.trace:
            if d0 <= t < d1:
                cnt[stage][cls] += 1
    L.append("── 1. Dönem içi huni (olay sayıları, trend sınıfı kırılımı) ──")
    L.append(f"  {'aşama':<62}" + "".join(f"{c:>13}" for c in CLASSES + ("TOPLAM",)))
    for stage in sorted(cnt, key=lambda k: (["MITIGATED", "PERMISSION", "CHOCH", "NO_ENTRY", "ENTRY_ZONE", "GATE_FAIL", "SIGNAL", "SAME_ENTRY_BOX", "DUPLICATE"].index(
            next((x for x in ["MITIGATED", "PERMISSION", "CHOCH", "NO_ENTRY", "ENTRY_ZONE", "GATE_FAIL", "SIGNAL", "SAME_ENTRY_BOX", "DUPLICATE"] if k.startswith(x)), "DUPLICATE")), k)):
        c = cnt[stage]
        L.append(f"  {stage:<62}" + "".join(f"{c.get(k, 0):>13}" for k in CLASSES) + f"{sum(c.values()):>13}")
    fl = [t for t in res.trades + res.open_trades if d0 <= t.fill_time < d1]
    L.append(f"  dolum (işlem): {len(fl)}   iptal: {sum(1 for e in res.events if e.kind == 'CANCELLED' and d0 <= e.time < d1)}")
    L.append("")
    # 2) gün gün trend
    L.append("── 2. Gün gün trend durumu (swing trendi; [swing_low–swing_high], * = uç onaysız) ──")
    for t, snap in res.trend_log:
        if not (d0 <= t < d1):
            continue
        parts = []
        for tf in ("D1", "H4", "M15"):
            if tf in snap:
                tr, lo, hi, (cl, ch) = snap[tf]
                parts.append(f"{tf} {tr:<9}" + (f"[{lo}{'' if cl else '*'}–{hi}{'' if ch else '*'}]" if lo is not None and hi is not None else "[–]"))
        L.append(f"  {t:%m-%d %H:%M}Z  " + "  ".join(parts) + f"  | icra iç trend {snap.get('exec_internal')}")
    L.append("")
    # 3) POI'ler
    L.append("── 3. Dönemde yaşayan POI kurulumları (POI geçersizleşmediyse / dönem içinde geçersizleştiyse) ──")
    eng = res.runner.model._engines if res.runner is not None else {}
    n = 0
    for s in sorted(res.setups, key=lambda s: s.poi.created_time):
        z = s.poi
        ze = eng.get(s.id)
        inv_t = None
        if z.invalidated_index is not None and ze is not None and z.invalidated_index < len(ze.candles):
            inv_t = ze.candles[z.invalidated_index].open_time
        if z.created_time >= d1 or (inv_t is not None and inv_t < d0):
            continue
        recs = [r for r in s.trace if d0 <= r[0] < d1]
        mit = sum(1 for r in recs if r[1] == "MITIGATED")
        last = recs[-1] if recs else None
        n += 1
        if n > 300:
            L.append("  ... (kısaltıldı)")
            break
        L.append(f"  {z.id:<28}{z.tf.value:<4}{s.direction.value:<5}[{z.bottom}–{z.top}] doğdu {z.created_time:%m-%d %H:%M}Z"
                 f"{' geçersiz ' + inv_t.strftime('%m-%d %H:%M') + 'Z' if inv_t else ''}  geçerli={z.valid}  mitigasyon(dönem) {mit}  "
                 f"sinyal {s.n_signals}  son durum {s.state.value}"
                 + (f"  son aşama: {last[1]} [{last[2]}] {last[0]:%m-%d %H:%M}Z" if last else "  (dönemde hiç mitigasyon olmadı)"))
    L.append("")
    # 4) izler
    L.append("── 4. Kurulum izleri (dönem içi, aşama aşama) ──")
    lines = 0
    for s in sorted(res.setups, key=lambda s: s.poi.created_time):
        recs = [r for r in s.trace if d0 <= r[0] < d1]
        if not recs:
            continue
        L.append(f"  {s.id} ({s.poi.tf.value} {s.direction.value} [{s.poi.bottom}–{s.poi.top}])")
        for t, stage, cls, d in recs:
            L.append(f"      {t.astimezone(tz):%m-%d %H:%M} [{cls}] {stage}: {d[:230]}")
            lines += 1
        if lines > max_lines:
            L.append("  ... (kısaltıldı)")
            break
    return "\n".join(L)


def slice_result(res: BacktestResult, d0: datetime, d1: datetime) -> BacktestResult:
    """[d0, d1) penceresindeki KAPANAN işlemlerden oluşan sonuç (çok yıllı rapor: yıl dilimi). Tek koşuyu keser — motor yeniden başlatılmaz,
    warm-up ve bakiye sürekli kalır. Dilimin başlangıç bakiyesi = penceredeki ilk işlemden önceki son kapanış bakiyesi (yoksa koşunun başlangıcı)."""
    before = [t for t in res.trades if t.close_time is not None and t.close_time < d0]
    inside = [t for t in res.trades if t.close_time is not None and d0 <= t.close_time < d1]
    start_bal = before[-1].balance_after if before else res.initial_balance
    end_bal = inside[-1].balance_after if inside else start_bal
    eq = [(t, b) for t, b in res.equity if d0 <= t < d1]
    return dataclasses.replace(res, trades=inside, equity=eq, initial_balance=start_bal, final_balance=end_bal, start=d0, end=d1)


def year_windows(start: datetime, end: datetime) -> list[tuple[int, datetime, datetime]]:
    """[start, end) aralığını takvim yıllarına böler (UTC)."""
    out, y = [], start.year
    last = (end - timedelta(seconds=1)).year
    while y <= last:
        a = max(start, datetime(y, 1, 1, tzinfo=start.tzinfo))
        b = min(end, datetime(y + 1, 1, 1, tzinfo=start.tzinfo))
        out.append((y, a, b))
        y += 1
    return out


def metrics_row(res: BacktestResult) -> dict:
    """Tablo satırı için düz (picklable) metrik sözlüğü."""
    m = compute_metrics(res)
    risk = sum((t.intent.risk_amount for t in res.trades), D0)
    q5, nl = stop_quick_ratio(res.trades, 5)
    return {"n": m.n, "wins": m.wins, "strike": m.strike_rate, "avg_r_net": m.avg_r_net, "total_r_net": m.total_r_net, "total_r": m.total_r,
            "return_pct": m.return_pct, "max_dd_pct": m.max_dd_pct, "max_consec": m.max_consec_losses,
            "comm_pct_risk": (m.commission / risk * 100) if risk else D0, "q5": q5, "losers": nl,
            "classes": {c: {"n": len(ts), "r_net": sum((t.r_net for t in ts), D0)} for c in CLASSES
                        if (ts := [t for t in res.trades if t.intent.trend_class == c])}}
