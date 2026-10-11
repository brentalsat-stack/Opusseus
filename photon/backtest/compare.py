"""Varyant karşılaştırma (Aşama 7+): DECISIONS'ta "backtest sonrası karşılaştırılacak" denen seçenekler aynı veriyle, tek tabloda.

Varyantlar `variants.yaml` içinde config OVERRIDE'ı olarak tanımlanır (noktalı yol → değer); varsayılan config.yaml DEĞİŞMEZ.
Her varyant ayrı süreçte (multiprocessing, `--jobs`) kendi BacktestEngine'ini çalıştırır; çıktılar `<out>/<ad>/` altına yazılır.
V7 türü "vshape_report": işlemleri ETKİLEMEZ — taban varyantın işlemleri için V-shape N ∈ {…} ile puan dağılımı yeniden hesaplanır."""
from __future__ import annotations

import copy
import csv
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import yaml

from ..config import load_config
from ..config.loader import Config, _decimalize
from ..liquidity import v_shape_exit
from .engine import BacktestEngine
from .report import CLASSES, compute_metrics, monthly_funnel, stop_quick_ratio, write_outputs, funnel

# varsayılan config'te bulunmayan ama kodda varsayılanı olan (davranışı değiştirmeyen) anahtarlar: override ile eklenebilir
NEW_KEYS_ALLOWED = {"entry_zone_choice"}
D0 = Decimal(0)


@dataclass
class Variant:
    name: str
    desc: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompareSpec:
    variants: list[Variant]
    vshape_n: list[int]
    vshape_base: Optional[str] = None


def load_variants(path: str | Path) -> CompareSpec:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    vs = [Variant(str(v["name"]), str(v.get("desc", "")), dict(v.get("overrides") or {})) for v in raw.get("variants") or []]
    if not vs:
        raise ValueError("variants.yaml: 'variants' listesi boş")
    names = [v.name for v in vs]
    if len(set(names)) != len(names):
        raise ValueError(f"variants.yaml: tekrarlayan varyant adı: {names}")
    vr = raw.get("vshape_report") or {}
    ns = [int(n) for n in vr.get("n_values") or []]
    if vr.get("base") and vr["base"] not in names:
        raise ValueError(f"vshape_report.base={vr['base']!r} varyant listesinde yok")
    return CompareSpec(vs, ns, vr.get("base"))


def apply_overrides(cfg: Config, overrides: dict[str, Any]) -> Config:
    """Config'in derin kopyasında noktalı yolları değiştirir. Var olmayan yol hata (yazım hatası koruması); izinli yeni anahtarlar hariç."""
    raw = copy.deepcopy(dict(cfg.raw))
    for path, val in overrides.items():
        keys = path.split(".")
        node = raw
        for k in keys[:-1]:
            if not isinstance(node.get(k), dict):
                raise KeyError(f"override yolu config'te yok: {path}")
            node = node[k]
        if keys[-1] not in node and path not in NEW_KEYS_ALLOWED:
            raise KeyError(f"override yolu config'te yok: {path}")
        node[keys[-1]] = _decimalize(val)
    return Config(raw, cfg.path)


def _vshape_rows(res) -> list[dict]:
    rows = []
    for t in res.trades:
        crit = {n: (w, e) for n, w, e in t.intent.criteria}
        w, e = crit.get("corrective_or_vshape", (D0, None))
        rows.append({"score": t.intent.poi_score, "weight": w, "earned": e, "win": t.win, "cls": t.intent.trend_class,
                     "gap": t.intent.choch_gap})          # sinyal anındaki değer (kurulum sonradan yeniden kullanıldığı için setup'tan okunmaz)
    return rows


def run_variant(task: dict) -> dict:
    """Tek varyantı çalıştırır (ayrı süreçte çağrılabilir; yalnızca basit/picklable değerler döner)."""
    t0 = time.time()
    from ..data import tools
    cfg = apply_overrides(load_config(task["config"]), task["overrides"])
    pair, start, end = task["pair"], task["start"], task["end"]
    warm = max(cfg.get(f"warmup_period.{tf}") for tf in ("D1", "H4", "M15", "M1"))
    m1 = tools.load_m1(cfg, task["source"], pair, start - timedelta(days=warm), end)
    if not m1:
        raise RuntimeError("önbellekte M1 yok; önce `photon import-histdata` çalıştırın")
    res = BacktestEngine(cfg, pair, start, end, task["balance"]).run(m1)
    out = Path(task["out"]) / task["name"]
    write_outputs(res, out)
    m = compute_metrics(res)
    risk = sum((t.intent.risk_amount for t in res.trades), D0)
    q5, nl = stop_quick_ratio(res.trades, 5)
    classes = {}
    for c in CLASSES:
        ts = [t for t in res.trades if t.intent.trend_class == c]
        if ts:
            classes[c] = {"n": len(ts), "wins": sum(t.win for t in ts), "total_r_net": sum((t.r_net for t in ts), D0),
                          "total_r_gross": sum((t.r_gross for t in ts), D0)}
    return {"name": task["name"], "desc": task["desc"], "overrides": task["overrides"], "metrics": m,
            "commission_pct_of_risk": (m.commission / risk * 100) if risk else D0, "quick": (q5, nl),
            "entry_and_stop_same_candle": res.fill_stats.get("entry_and_stop_same_candle", 0), "classes": classes,
            "funnel": {k: v.get("TOPLAM", 0) for k, v in funnel(res)}, "monthly": monthly_funnel(res),
            "signals": sum(1 for e in res.events if e.kind == "SIGNAL"), "cancelled": sum(1 for e in res.events if e.kind == "CANCELLED"),
            "vshape_rows": _vshape_rows(res), "v_n_config": cfg.get("v_shape_metric.max_candles"),
            "seconds": round(time.time() - t0, 1), "out": str(out)}


def run_compare(config_path: str, spec: CompareSpec, source: str, pair: str, start: datetime, end: datetime, balance: Decimal,
                out: Path, jobs: int = 1, progress=print) -> list[dict]:
    tasks = [{"config": config_path, "name": v.name, "desc": v.desc, "overrides": v.overrides, "source": source, "pair": pair,
              "start": start, "end": end, "balance": balance, "out": str(out)} for v in spec.variants]
    results: dict[str, dict] = {}
    if jobs <= 1 or len(tasks) == 1:
        for t in tasks:
            r = run_variant(t)
            results[r["name"]] = r
            progress(f"  {r['name']} tamam ({r['seconds']} sn): {r['metrics'].n} işlem")
    else:
        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=jobs, mp_context=mp.get_context("spawn")) as ex:
            futs = {ex.submit(run_variant, t): t["name"] for t in tasks}
            for f in as_completed(futs):
                r = f.result()
                results[r["name"]] = r
                progress(f"  {r['name']} tamam ({r['seconds']} sn): {r['metrics'].n} işlem")
    return [results[v.name] for v in spec.variants]


# ---------------------------------------------------------------- rapor
def _f(x: Decimal, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def format_table(results: list[dict]) -> str:
    hdr = (f"{'varyant':<8}{'işlem':>6}{'strike%':>9}{'ort R net':>10}{'top R net':>10}{'top R brüt':>11}{'getiri%':>9}"
           f"{'maxDD%':>8}{'maks kayıp serisi':>18}{'komisyon/risk%':>15}{'≤5dk stop':>12}{'giriş+stop aynı mum':>20}")
    L = [hdr]
    for r in results:
        m = r["metrics"]
        q5, nl = r["quick"]
        L.append(f"{r['name']:<8}{m.n:>6}{_f(m.strike_rate, 1):>9}{_f(m.avg_r_net):>10}{_f(m.total_r_net):>10}{_f(m.total_r):>11}"
                 f"{_f(m.return_pct, 1):>9}{_f(m.max_dd_pct, 1):>8}{m.max_consec_losses:>18}{_f(r['commission_pct_of_risk'], 1):>15}"
                 f"{(f'{q5}/{nl} %{q5 / nl * 100:.0f}' if nl else '-'):>12}{r['entry_and_stop_same_candle']:>20}")
    return "\n".join(L)


def format_classes(results: list[dict]) -> str:
    L = [f"{'varyant':<8}{'sınıf':<13}{'işlem':>6}{'win%':>7}{'ort R net':>10}{'top R net':>10}{'top R brüt':>11}"]
    for r in results:
        for c, d in r["classes"].items():
            L.append(f"{r['name']:<8}{c:<13}{d['n']:>6}{d['wins'] / d['n'] * 100:>7.1f}{_f(d['total_r_net'] / d['n']):>10}"
                     f"{_f(d['total_r_net']):>10}{_f(d['total_r_gross']):>11}")
    return "\n".join(L)


def vshape_distribution(rows: list[dict], ns: list[int], n_config: int) -> str:
    """V7: işlemleri değiştirmeden `corrective_or_vshape` kriterinin N'e göre dağılımı ve toplam POI puanı."""
    rows = [r for r in rows if r["earned"] is not None and r["gap"] is not None]
    L = [f"{'N':>4}{'kazanan(var)':>14}{'win% var':>10}{'win% yok':>10}{'ort puan':>10}{'medyan':>8}{'puanı değişen':>15}"]
    for n in [n_config] + [x for x in ns if x != n_config]:
        e_new = [v_shape_exit(0, r["gap"], n) for r in rows]
        sc = [r["score"] + (r["weight"] if e else D0) - (r["weight"] if r["earned"] else D0) for r, e in zip(rows, e_new)]
        yes = [r for r, e in zip(rows, e_new) if e]
        no = [r for r, e in zip(rows, e_new) if not e]
        wr = lambda xs: f"{sum(x['win'] for x in xs) / len(xs) * 100:.1f}" if xs else "-"
        ch = sum(1 for r, e in zip(rows, e_new) if bool(r["earned"]) != e)
        tag = " (config)" if n == n_config else ""
        L.append(f"{n:>4}{len(yes):>14}{wr(yes):>10}{wr(no):>10}{_f(sum(sc, D0) / len(sc)) if sc else '-':>10}"
                 f"{_f(Decimal(statistics.median(sc))) if sc else '-':>8}{ch:>15}{tag}")
    return "\n".join(L)


def format_compare(results: list[dict], spec: CompareSpec, start: datetime, end: datetime, balance: Decimal, source: str, pair: str) -> str:
    L = [f"═══ PHOTON VARYANT KARŞILAŞTIRMA ═══  {pair} {source}  {start:%Y-%m-%d} → {(end - timedelta(seconds=1)):%Y-%m-%d}  "
         f"başlangıç bakiyesi {balance} (aynı veri, aynı warm-up; komisyon dahil: R/getiri 'net')", ""]
    for r in results:
        ov = ", ".join(f"{k}={v}" for k, v in r["overrides"].items()) or "(override yok = mevcut config)"
        L.append(f"  {r['name']}: {r['desc']}  [{ov}]  ({r['seconds']} sn)")
    L += ["", "── Özet ──", format_table(results), "",
          "(≤5dk stop: kaybeden işlemlerden dolumdan ≤5 dk içinde kapananlar / kaybeden; komisyon/risk: Σkomisyon / Σhedef risk)", "",
          "── Trend sınıfı kırılımı ──", format_classes(results), ""]
    if spec.vshape_n:
        base = next((r for r in results if r["name"] == spec.vshape_base), None) or results[0]
        L += [f"── V7: V-shape N dağılımı (işlemleri ETKİLEMEZ; taban varyant {base['name']}, {base['metrics'].n} işlem) ──",
              vshape_distribution(base["vshape_rows"], spec.vshape_n, int(base["v_n_config"])),
              "(puan = POI puanı; yalnızca `corrective_or_vshape` kriteri N'e göre yeniden hesaplanır; küçük örneklemde win% anlamsızdır)", ""]
    L += ["── Huni toplamları (varyant başına) ──"]
    keys = list(results[0]["funnel"])
    L.append(f"{'aşama':<80}" + "".join(f"{r['name']:>8}" for r in results))
    for k in keys:
        L.append(f"{k.strip():<80}" + "".join(f"{r['funnel'].get(k, 0):>8}" for r in results))
    return "\n".join(L)


def write_compare(results: list[dict], spec: CompareSpec, out: Path, text: str) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    p1 = out / "compare.txt"
    p1.write_text(text + "\n", encoding="utf-8")
    p2 = out / "compare.csv"
    with p2.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "overrides", "trades", "strike_pct", "avg_r_net", "total_r_net", "total_r_gross", "return_pct", "max_dd_pct",
                    "max_consec_losses", "commission_pct_of_risk", "quick_stops_5min", "losers", "entry_and_stop_same_candle"])
        for r in results:
            m = r["metrics"]
            w.writerow([r["name"], ";".join(f"{k}={v}" for k, v in r["overrides"].items()), m.n, f"{m.strike_rate:.2f}", f"{m.avg_r_net:.3f}",
                        f"{m.total_r_net:.3f}", f"{m.total_r:.3f}", f"{m.return_pct:.2f}", f"{m.max_dd_pct:.2f}", m.max_consec_losses,
                        f"{r['commission_pct_of_risk']:.2f}", r["quick"][0], r["quick"][1], r["entry_and_stop_same_candle"]])
    return {"compare": p1, "csv": p2}
