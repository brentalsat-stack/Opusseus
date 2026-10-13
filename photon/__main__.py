"""`python -m photon check [--config PATH] [--module M ...]` — config durum raporu."""
from __future__ import annotations

import argparse
import sys
from datetime import date

from .config import DEFAULT_PATH, MODULES, find_required, load_config, validate_all
from .config.validator import collect_failures, format_errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="photon")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="config doğrula, modül durumlarını listele")
    ck.add_argument("--config", default=str(DEFAULT_PATH))
    ck.add_argument("--module", action="append", choices=list(MODULES),
                    help="verilirse bu modüller hazır değilse çıkış kodu 2")
    for name, helptext in (("fetch", "M1 bid/ask indir → önbellek (+ isteğe bağlı CSV)"),
                           ("data-check", "önbellekteki M1/M15 serisini doğrula (düzeltmeden raporla)")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--config", default=str(DEFAULT_PATH))
        sp.add_argument("--source", choices=["HISTDATA", "OANDA_PRACTICE", "DUKASCOPY"],
                        help="verilmezse config data.backtest.primary")
        sp.add_argument("--pair", default=None, help="verilmezse config pairs[0]")
        sp.add_argument("--start", type=date.fromisoformat, required=True)
        sp.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
        if name == "fetch":
            sp.add_argument("--csv", help="indirilen aralığı CSV'ye yaz")
    ih = sub.add_parser("import-histdata", help="HistData M1 bid CSV'sini önbelleğe al (UTC'ye çevirir, ask=bid+spread)")
    ih.add_argument("--config", default=str(DEFAULT_PATH))
    ih.add_argument("--pair")
    ih.add_argument("--path", help="dosya, dizin (DAT_ASCII_<PAIR>_M1_<YYYY>.csv) veya glob; verilmezse config data.backtest.histdata.path")
    ih.add_argument("--years", help="yalnız bu yıl aralığı, örn. 2016-2023")
    st = sub.add_parser("structure", help="yapı olaylarını bul: CSV + işaretli grafik (doğrulama)")
    st.add_argument("--config", default=str(DEFAULT_PATH))
    st.add_argument("--source", choices=["HISTDATA", "OANDA_PRACTICE", "DUKASCOPY"])
    st.add_argument("--pair")
    st.add_argument("--tf", required=True, choices=["D1", "H4", "M15", "M1"])
    st.add_argument("--start", type=date.fromisoformat, required=True)
    st.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
    st.add_argument("--seed", help="elle başlangıç yapısı YAML; verilmezse otomatik warm-up (config warmup_period)")
    st.add_argument("--out", default="structure_out")
    zn = sub.add_parser("zones", help="zonları bul (SD-R001..R007): CSV + grafik (doğrulama)")
    zn.add_argument("--config", default=str(DEFAULT_PATH))
    zn.add_argument("--source", choices=["HISTDATA", "OANDA_PRACTICE", "DUKASCOPY"])
    zn.add_argument("--pair")
    zn.add_argument("--tf", required=True, choices=["D1", "H4", "M15"])
    zn.add_argument("--start", type=date.fromisoformat, required=True)
    zn.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
    zn.add_argument("--out", default="zones_out")
    zn.add_argument("--all", action="store_true", help="grafikte geçersiz zonları da çiz")
    bt = sub.add_parser("backtest", help="backtest: sinyal + simüle dolum/yönetim; rapor + CSV (emir gönderilmez)")
    bt.add_argument("--config", default=str(DEFAULT_PATH))
    bt.add_argument("--source", choices=["HISTDATA", "OANDA_PRACTICE", "DUKASCOPY"])
    bt.add_argument("--pair")
    bt.add_argument("--start", type=date.fromisoformat, required=True)
    bt.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
    bt.add_argument("--balance", help="başlangıç bakiyesi (verilmezse config backtest.initial_balance)")
    bt.add_argument("--out", default="backtest_out")
    tb = sub.add_parser("trace-bos", help="bir TF'de BOS/CHoCH olaylarının zon bağlamasını adım adım izle (SD-R005 teşhisi)")
    tb.add_argument("--config", default=str(DEFAULT_PATH))
    tb.add_argument("--source", choices=["HISTDATA", "OANDA_PRACTICE", "DUKASCOPY"])
    tb.add_argument("--pair")
    tb.add_argument("--tf", required=True, choices=["D1", "H4", "M15"])
    tb.add_argument("--start", type=date.fromisoformat, required=True)
    tb.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
    tb.add_argument("--type", default="BOS", choices=["BOS", "CHOCH", "BOTH"])
    tb.add_argument("--dir", choices=["BULL", "BEAR"])
    tb.add_argument("--max-events", type=int, default=12)
    tb.add_argument("--out", help="verilirse metin dosyaya da yazılır")
    bc = sub.add_parser("backtest-compare", help="varyant karşılaştırma: variants.yaml override'ları, aynı veri, tek tablo")
    bc.add_argument("--config", default=str(DEFAULT_PATH))
    bc.add_argument("--source", choices=["HISTDATA", "OANDA_PRACTICE", "DUKASCOPY"])
    bc.add_argument("--pair")
    bc.add_argument("--start", type=date.fromisoformat, help="--periods YYYY..YYYY verilmediyse zorunlu")
    bc.add_argument("--end", type=date.fromisoformat, help="dahil; --periods YYYY..YYYY verilmediyse zorunlu")
    bc.add_argument("--periods", help="'year' (yıl bazında ayrı satırlar + toplam) veya 'YYYY..YYYY' (aralığı ve yıl kırılımını birlikte verir, örn. 2016..2023)")
    bc.add_argument("--variants", required=True, help="variants.yaml")
    bc.add_argument("--balance", help="başlangıç bakiyesi (verilmezse config backtest.initial_balance)")
    bc.add_argument("--out", default="backtest_compare")
    bc.add_argument("--only", help="virgülle ayrılmış varyant adları (yalnız bunlar çalışır), örn. V0,V8a")
    bc.add_argument("--jobs", type=int, default=0, help="paralel süreç sayısı (0 = min(CPU, varyant sayısı); 1 = sırayla)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd == "import-histdata":
        from .data import tools
        from .logging_setup import setup_from_config
        setup_from_config(cfg)
        yrs = None
        if args.years:
            a, _, b = args.years.partition("-")
            yrs = (int(a), int(b or a))
        try:
            rep = tools.import_histdata(cfg, args.pair or cfg.pairs[0], args.path, yrs)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(rep.summary())
        for n, why in rep.invalid[:10]:
            print(f"  geçersiz satır {n}: {why}")
        return 0 if rep.clean else 3
    if args.cmd in ("fetch", "data-check"):
        return _data_cmd(cfg, args)
    if args.cmd == "structure":
        return _structure_cmd(cfg, args)
    if args.cmd == "zones":
        return _zones_cmd(cfg, args)
    if args.cmd == "backtest":
        return _backtest_cmd(cfg, args)
    if args.cmd == "trace-bos":
        return _trace_cmd(cfg, args)
    if args.cmd == "backtest-compare":
        return _compare_cmd(cfg, args)
    reports = validate_all(cfg)
    for name, r in reports.items():
        print(f"{'READY  ' if r.ok else 'BLOCKED'} {name}")
    pending = find_required(cfg.raw)
    print(f"\nBekleyen (REQUIRED) alanlar: {len(pending)}")
    for p in pending:
        print(f"  - {p}")
    if args.module:
        bad = collect_failures(cfg, *args.module)
        if bad:
            print("\n" + format_errors(bad), file=sys.stderr)
            return 2
    return 0


def _structure_cmd(cfg, args) -> int:
    from datetime import timedelta
    from pathlib import Path

    from .data import tools
    from .data.models import PriceSide, Timeframe
    from .data.resample import BoundarySpec, resample
    from .data.resolver import SubTfResolver
    from .logging_setup import setup_from_config
    from .structure.params import StructureParams
    from .structure.report import (load_seed_yaml, plot_events, run_structure, run_structure_auto,
                                   summarize_diagnostics, write_diagnostics_csv, write_events_csv)

    setup_from_config(cfg)
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    tf = Timeframe(args.tf)
    cfg.require("data_boundaries")
    start, end = tools.day_range(args.start, args.end)
    warm_days = 0
    if not args.seed:
        cfg.require("structure_warmup")
        warm_days = cfg.get(f"warmup_period.{tf.value}")
    m1 = tools.load_m1(cfg, source, pair, start - timedelta(days=warm_days), end)
    if not m1:
        print("önbellekte M1 yok; önce `photon fetch` çalıştırın", file=sys.stderr)
        return 2
    spec = BoundarySpec.from_config(cfg)
    qc = m1 if tf is Timeframe.M1 else resample(m1, tf, spec)
    side = PriceSide(cfg.get("candle_price_side"))
    candles = [c.to_candle(side) for c in qc if c.complete]   # yalnızca kapanmış mumlar
    resolver = SubTfResolver(m1, side)                        # Q-S04: outside bar → M1 (tick Aşama 7'de)
    params = StructureParams.from_config(cfg, pair, tf)
    if args.seed:
        seed, hist = load_seed_yaml(args.seed, candles)
        eng = run_structure(candles, params, seed, hist, resolver, start)
    else:
        have = (start - candles[0].open_time).days
        if have < warm_days:
            print(f"UYARI warm-up: {tf.value} için {warm_days} gün gerekli, veri {candles[0].open_time:%Y-%m-%d} "
                  f"tarihinde başlıyor ({max(have, 0)} gün) → mevcut verinin tamamı warm-up", file=sys.stderr)
        eng = run_structure_auto(candles, params, start, resolver)
    first = next((i for i, c in enumerate(candles) if c.open_time >= start), 0)
    out = Path(args.out)
    n = write_events_csv(eng.events, out / f"{pair}_{tf.value}_structure.csv")
    plot_events(candles, eng.events, out / f"{pair}_{tf.value}_structure.png", first_index=first)
    live = sum(1 for e in eng.events if not e.warmup)
    print(f"{n} olay ({live} canlı, {n - live} warm-up) → {out}/; trend={eng.state().swing_trend.value}")
    write_diagnostics_csv(eng.diagnostics, out / f"{pair}_{tf.value}_diagnostics.csv")
    print(summarize_diagnostics(eng.diagnostics))
    return 0


def _zones_cmd(cfg, args) -> int:
    from datetime import timedelta
    from pathlib import Path

    from .data import tools
    from .data.models import PriceSide, Timeframe
    from .data.resample import BoundarySpec, resample
    from .data.resolver import SubTfResolver
    from .logging_setup import setup_from_config
    from .structure.params import StructureParams
    from .structure.report import summarize_diagnostics
    from .zones.engine import ZoneParams
    from .zones.report import plot_zones, run_zones, summarize, write_zones_csv

    setup_from_config(cfg)
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    tf = Timeframe(args.tf)
    cfg.require("data_boundaries", "structure_warmup")
    start, end = tools.day_range(args.start, args.end)
    warm_days = cfg.get(f"warmup_period.{tf.value}")
    m1 = tools.load_m1(cfg, source, pair, start - timedelta(days=warm_days), end)
    if not m1:
        print("önbellekte M1 yok; önce `photon import-histdata` / `photon fetch` çalıştırın", file=sys.stderr)
        return 2
    side = PriceSide(cfg.get("candle_price_side"))
    qc = resample(m1, tf, BoundarySpec.from_config(cfg))
    candles = [c.to_candle(side) for c in qc if c.complete]
    have = (start - candles[0].open_time).days
    if have < warm_days:
        print(f"UYARI warm-up: {tf.value} için {warm_days} gün gerekli, veri {candles[0].open_time:%Y-%m-%d} tarihinde "
              f"başlıyor ({max(have, 0)} gün) → mevcut verinin tamamı warm-up", file=sys.stderr)
    st, ze = run_zones(candles, StructureParams.from_config(cfg, pair, tf), ZoneParams.from_config(cfg, pair, tf),
                       start, SubTfResolver(m1, side))
    first = next((i for i, c in enumerate(candles) if c.open_time >= start), 0)
    zones = ze.zones
    live = [z for z in zones if not z.warmup]
    out = Path(args.out)
    n = write_zones_csv(zones, candles, out / f"{pair}_{tf.value}_zones.csv", ze)
    plot_zones(candles, zones, out / f"{pair}_{tf.value}_zones.png", first, only_valid=not args.all)
    print(f"{n} zon ({len(live)} canlı dönemde doğan) → {out}/")
    print(summarize(live))
    print(summarize_diagnostics(st.diagnostics, 0))
    return 0


def _backtest_cmd(cfg, args) -> int:
    from datetime import timedelta
    from decimal import Decimal
    from pathlib import Path

    from .backtest.engine import BacktestEngine
    from .backtest.report import format_report, write_outputs
    from .data import tools
    from .logging_setup import setup_from_config
    from .signals.output import SignalPublisher

    setup_from_config(cfg)
    cfg.require("backtest", "strategy", "management", "data_boundaries", "structure_warmup")
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    start, end = tools.day_range(args.start, args.end)
    warm = max(cfg.get(f"warmup_period.{tf}") for tf in ("D1", "H4", "M15", "M1"))
    m1 = tools.load_m1(cfg, source, pair, start - timedelta(days=warm), end)
    if not m1:
        print("önbellekte M1 yok; önce `photon import-histdata` / `photon fetch` çalıştırın", file=sys.stderr)
        return 2
    have = (start - m1[0].open_time).days
    if have < warm:
        print(f"UYARI warm-up: {warm} gün istendi, veri {m1[0].open_time:%Y-%m-%d} tarihinde başlıyor ({max(have, 0)} gün) "
              "→ mevcut verinin tamamı warm-up", file=sys.stderr)
    bal = Decimal(args.balance) if args.balance else Decimal(str(cfg.get("backtest.initial_balance")))
    if cfg.get("costs.commission") is None:
        print("komisyon dahil değil (config'de costs.commission yok)")
    eng = BacktestEngine(cfg, pair, start, end, bal, publisher=SignalPublisher(["LOG_FILE"]))   # sinyal metni log'a; ekrana yalnızca rapor
    res = eng.run(m1)
    print(format_report(res))
    paths = write_outputs(res, Path(args.out))
    print("\nDosyalar: " + ", ".join(str(p) for p in paths.values()))
    return 0


def _trace_cmd(cfg, args) -> int:
    from datetime import timedelta
    from pathlib import Path

    from .data import tools
    from .data.models import PriceSide, Timeframe
    from .data.resample import BoundarySpec, resample
    from .data.resolver import SubTfResolver
    from .structure.models import EventType, Trend
    from .structure.params import StructureParams
    from .zones.engine import ZoneParams
    from .zones.report import run_zones
    from .zones.trace import trace_events

    cfg.require("data_boundaries", "structure_warmup")
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    tf = Timeframe(args.tf)
    start, end = tools.day_range(args.start, args.end)
    warm_days = cfg.get(f"warmup_period.{tf.value}")
    m1 = tools.load_m1(cfg, source, pair, start - timedelta(days=warm_days), end)
    if not m1:
        print("önbellekte M1 yok; önce `photon import-histdata` çalıştırın", file=sys.stderr)
        return 2
    side = PriceSide(cfg.get("candle_price_side"))
    candles = [c.to_candle(side) for c in resample(m1, tf, BoundarySpec.from_config(cfg)) if c.complete]
    st, ze = run_zones(candles, StructureParams.from_config(cfg, pair, tf), ZoneParams.from_config(cfg, pair, tf), start, SubTfResolver(m1, side))
    types = {"BOS": (EventType.BOS,), "CHOCH": (EventType.CHOCH,), "BOTH": (EventType.BOS, EventType.CHOCH)}[args.type]
    text = trace_events(st, ze, candles, start, end, types, Trend(args.dir) if args.dir else None, args.max_events)
    print(text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


def _compare_cmd(cfg, args) -> int:
    import os
    from datetime import timedelta
    from decimal import Decimal
    from pathlib import Path

    from .backtest.compare import (CompareSpec, apply_overrides, format_compare, load_variants, missing_inputs, run_compare,
                                   write_compare)
    from .data import tools

    cfg.require("backtest", "strategy", "management", "data_boundaries", "structure_warmup")
    spec = load_variants(args.variants)
    periods = None
    if args.periods:
        import re
        m = re.fullmatch(r"(\d{4})\.\.(\d{4})", args.periods)
        if args.periods == "year":
            periods = "year"
        elif m:
            periods = "year"
            args.start, args.end = date(int(m.group(1)), 1, 1), date(int(m.group(2)), 12, 31)
        else:
            print("--periods: 'year' veya 'YYYY..YYYY' olmalı", file=sys.stderr)
            return 2
    if args.start is None or args.end is None:
        print("--start/--end gerekli (ya da --periods YYYY..YYYY)", file=sys.stderr)
        return 2
    if args.only:
        want = [x.strip() for x in args.only.split(",") if x.strip()]
        unknown = [x for x in want if x not in {v.name for v in spec.variants}]
        if unknown:
            print(f"bilinmeyen varyant: {unknown}", file=sys.stderr)
            return 2
        spec = CompareSpec([v for v in spec.variants if v.name in want], spec.vshape_n, spec.vshape_base, spec.detail)
    for v in spec.variants:                                   # hatalı override'ları çalıştırmadan önce yakala
        apply_overrides(cfg, v.overrides).require("backtest", "strategy", "management")
    skipped = {v.name: why for v in spec.variants if (why := missing_inputs(v))}
    if skipped:
        print("UYARI atlanan varyantlar: " + "; ".join(f"{k} ({w})" for k, w in skipped.items()), file=sys.stderr)
        spec = CompareSpec([v for v in spec.variants if v.name not in skipped], spec.vshape_n, spec.vshape_base, spec.detail)
        if not spec.variants:
            return 2
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    start, end = tools.day_range(args.start, args.end)
    warm = max(cfg.get(f"warmup_period.{tf}") for tf in ("D1", "H4", "M15", "M1"))
    bounds = tools.data_bounds(cfg, source, pair)           # önbellek sınırları (start'tan önce veri olmayabilir: ilk yıl)
    if bounds is None:
        print("önbellekte M1 yok; önce `photon import-histdata` çalıştırın", file=sys.stderr)
        return 2
    first, last = bounds
    if last < start or first >= end:
        print(f"önbellekteki veri ({first:%Y-%m-%d} → {last:%Y-%m-%d}) istenen aralıkla ({start:%Y-%m-%d} → {end:%Y-%m-%d}) kesişmiyor", file=sys.stderr)
        return 2
    have = (start - first).days
    if first > start:
        print(f"UYARI: veri {first:%Y-%m-%d} tarihinde başlıyor (istenen başlangıç {start:%Y-%m-%d}); warm-up yok, koşu veri başından başlar", file=sys.stderr)
    elif have < warm:
        print(f"UYARI warm-up: {warm} gün istendi, veri {first:%Y-%m-%d} tarihinde başlıyor ({max(have, 0)} gün) → mevcut verinin tamamı warm-up", file=sys.stderr)
    bal = Decimal(args.balance) if args.balance else Decimal(str(cfg.get("backtest.initial_balance")))
    jobs = args.jobs or min(os.cpu_count() or 1, len(spec.variants))
    print(f"{len(spec.variants)} varyant, {jobs} süreç ...")
    out = Path(args.out)
    results = run_compare(args.config, spec, source, pair, start, end, bal, out, jobs, periods=periods)
    text = format_compare(results, spec, start, end, bal, source, pair, skipped)
    print("\n" + text)
    paths = write_compare(results, spec, out, text)
    print("\nDosyalar: " + ", ".join(str(p) for p in paths.values()) + f"; varyant çıktıları: {out}/<ad>/")
    return 0


def _data_cmd(cfg, args) -> int:
    import logging

    from .data import tools
    from .data.models import Timeframe
    from .data.resample import resample
    from .data.validate import check_series
    from .logging_setup import setup_from_config

    setup_from_config(cfg)
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    start, end = tools.day_range(args.start, args.end)
    if args.cmd == "fetch":
        n = tools.fetch(cfg, source, pair, start, end)
        print(f"{source} {pair}: {n} yeni M1 mum önbelleğe yazıldı")
        if args.csv:
            print(f"CSV: {tools.export_csv(tools.load_m1(cfg, source, pair, start, end), args.csv)} satır → {args.csv}")
        return 0
    m1 = tools.load_m1(cfg, source, pair, start, end)
    rep1 = check_series(m1, Timeframe.M1)
    print(rep1.format())
    rep1.log()
    rep15 = check_series(resample(m1, Timeframe.M15), Timeframe.M15)
    print(rep15.summary())
    logging.getLogger("photon").info("data-check %s %s tamam", source, pair)
    return 0 if rep1.ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
