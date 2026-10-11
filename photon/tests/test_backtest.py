"""Aşama 7: backtest motoru (dolum modeli, komisyon, bakiye, rapor, CLI)."""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.__main__ import main
from photon.backtest.engine import BacktestEngine, BacktestResult, CommissionModel
from photon.backtest.report import (compute_metrics, criteria_contribution, format_report, journal_matrix, m15_closer_than_4r,
                                    write_outputs)
from photon.config import load_config
from photon.data import Candle, CandleStore, Timeframe
from photon.execution.management import H4_LEG, M15_LEG, RISK_REMOVAL
from photon.risk.stops import Side
from photon.strategy.state_machine import State
from photon.structure.models import EventType, StructureEvent, Trend
from photon.tests.test_management import intent_for_output
from photon.tests.test_runner import cfg_with_policies, synth

UTC = timezone.utc
PIP = D("0.0001")
T0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)


@pytest.fixture
def eng(tmp_path):
    cfg = cfg_with_policies(tmp_path)
    return BacktestEngine(cfg, "EURUSD", T0, T0 + timedelta(days=1), D(10000))


def arm(eng):
    """Gerçek bir ORDER_PENDING sinyali (giriş modeli testlerinden) motora bekleyen emir olarak verilir."""
    ev = intent_for_output()
    s, it = ev.setup, ev.intent
    assert s.state is State.ORDER_PENDING
    eng.pending[s.id] = s
    return s, it


def cd(i, o, h, l, c):
    f = lambda x: D(str(x))
    return Candle("EURUSD", Timeframe.M1, T0 + timedelta(minutes=i), f(o), f(h), f(l), f(c), True)


def px(it, pips):
    return it.entry + D(str(pips)) * PIP * (1 if it.side is Side.LONG else -1)


def fill_candle(eng, it, i):
    """Yalnızca limit girişe dokunan mum (long: bid low = giriş − spread → ask = giriş)."""
    if it.side is Side.LONG:
        return cd(i, it.entry, it.entry, it.entry - eng.spread, it.entry)
    return cd(i, it.entry, it.entry, it.entry, it.entry)


def candle_at(it, i, o, h, l):                 # pip ofsetleri GİRİŞE göre (yön lehine +)
    s = 1 if it.side is Side.LONG else -1
    pr = [px(it, v) for v in (o, h, l)]
    hi, lo = max(pr[1], pr[2]), min(pr[1], pr[2])
    return cd(i, pr[0], hi, lo, pr[0])


def test_commission_min_and_pct_and_absent_config():
    cfg = load_config()
    cm = CommissionModel.from_config(cfg, "EURUSD")
    assert cm.included and cm.fee(D("0.01"), D("1.18")) == D(2)                       # min 2 USD
    assert cm.fee(D("5"), D("1.18")) == D("5") * 100000 * D("1.18") * D("0.00002")      # 11.80
    assert cm.fee(D(0), D("1.18")) == 0
    raw = cfg.raw.copy()
    raw.pop("costs")
    nocfg = type(cfg)(raw) if callable(type(cfg)) else cfg
    cm0 = CommissionModel.from_config(nocfg, "EURUSD")
    assert not cm0.included and cm0.fee(D("5"), D("1.18")) == 0


def test_limit_fills_only_when_ask_reaches_long_or_bid_reaches_short(eng):
    s, it = arm(eng)
    sp = eng.spread
    if it.side is Side.LONG:                                   # ask = bid + 0.4 pip: bid low entry+0.3 pip → ask 0.7 üstü → dolmaz
        eng._pre_step(cd(0, it.entry + 5 * PIP, it.entry + 6 * PIP, it.entry + D("0.3") * PIP, it.entry + 5 * PIP))
        assert s.id in eng.pending and not eng.positions
        eng._pre_step(cd(1, it.entry + 5 * PIP, it.entry + 6 * PIP, it.entry - sp, it.entry))   # bid low = entry − 0.4 pip → ask = entry
    else:
        eng._pre_step(cd(0, it.entry - 5 * PIP, it.entry - D("0.1") * PIP, it.entry - 6 * PIP, it.entry - 5 * PIP))
        assert s.id in eng.pending
        eng._pre_step(cd(1, it.entry - 5 * PIP, it.entry, it.entry - 6 * PIP, it.entry))
    assert s.id not in eng.pending
    tr = eng.positions.get(s.id) or eng.closed[0]
    assert tr.position.entry == it.entry and tr.fill_time == T0 + timedelta(minutes=1)    # fiyat = limit, slipaj yok


def test_entry_and_stop_same_candle_is_a_full_loss_and_counted(eng):
    s, it = arm(eng)
    if it.side is Side.LONG:
        c = cd(0, it.entry + 3 * PIP, it.entry + 3 * PIP, it.stop - PIP, it.entry)
    else:
        c = cd(0, it.entry - 3 * PIP, it.stop - eng.spread + 2 * PIP, it.entry - 3 * PIP, it.entry)
    eng._pre_step(c)
    assert not eng.positions and len(eng.closed) == 1
    tr = eng.closed[0]
    assert tr.r_gross == -1 and tr.outcome == "LOSS" and eng.pm.stats["entry_and_stop_same_candle"] == 1
    assert eng.runner.balance == D(10000) + tr.net_pnl and tr.net_pnl < tr.gross_pnl            # komisyon düşüldü
    assert tr.commission >= 4                                                                    # giriş + çıkış, her biri ≥ 2
    assert s.state is State.WATCHING and eng.model.tracker.losses(T0) == 1                       # RK-R003 net PnL<0 → kayıp


def test_stop_gap_fills_at_open_price_and_counts(eng):
    s, it = arm(eng)
    eng._pre_step(fill_candle(eng, it, 0))
    assert eng.positions
    gap = 6
    if it.side is Side.LONG:
        eng._pre_step(cd(1, it.stop - gap * PIP, it.stop - gap * PIP, it.stop - (gap + 1) * PIP, it.stop - gap * PIP))
        expected = it.stop - gap * PIP
    else:
        o = it.stop + gap * PIP
        eng._pre_step(cd(1, o, o + PIP, o - PIP, o))
        expected = o + eng.spread                               # short: ask açılışı
    tr = eng.closed[0]
    assert tr.position.fills[-1].price == expected and eng.pm.stats["stop_gap_fills"] == 1
    assert tr.r_gross < -1


def test_full_winner_4r_then_m15_without_h4_choch_closes_at_m15_with_hold_rule(eng):
    s, it = arm(eng)
    eng._pre_step(fill_candle(eng, it, 0))
    pos = eng.positions[s.id].position
    legs = {l.name: l for l in it.plan.legs}
    far = max(legs.values(), key=lambda l: abs(l.price - it.entry))
    sign = 1 if it.side is Side.LONG else -1
    k = 1
    for l in sorted(legs.values(), key=lambda l: abs(l.price - it.entry)):          # girişe yakından uzağa
        hi = l.price + (eng.spread if it.side is Side.SHORT else 0)
        eng._pre_step(cd(k, it.entry, max(l.price, it.entry) if it.side is Side.LONG else it.entry,
                         it.entry if it.side is Side.LONG else min(l.price, it.entry) - eng.spread, it.entry))
        k += 1
        if pos.closed:
            break
    assert pos.closed and eng.closed and eng.closed[0].outcome in ("WIN", "LOSS")
    names = [f.leg for f in pos.fills]
    if any(l.name == H4_LEG for l in it.plan.legs):
        assert "NO_HOLD_CONFIRMATION" in names or H4_LEG in names                    # D-26: onay yok → M15 hedefinde kapanır
    assert sum(f.lots for f in pos.fills) == it.lots


def test_h4_choch_after_entry_lets_last_20_percent_run_to_h4_target(eng):
    s, it = arm(eng)
    if not any(l.name == H4_LEG for l in it.plan.legs):
        pytest.skip("sinyalde 4H hedef bacağı yok")
    eng._pre_step(fill_candle(eng, it, 0))
    d = Trend.BULL if it.side is Side.LONG else Trend.BEAR
    eng.runner.struct[Timeframe.H4].events.append(
        StructureEvent(Timeframe.H4, EventType.CHOCH, d, it.entry, 3, T0 + timedelta(minutes=1), False, warmup=False))
    pos = eng.positions[s.id].position
    for k, l in enumerate(sorted(it.plan.legs, key=lambda l: abs(l.price - it.entry)), 1):
        if it.side is Side.LONG:
            eng._pre_step(cd(k, it.entry, l.price, it.entry, it.entry))
        else:
            eng._pre_step(cd(k, it.entry, it.entry, l.price - eng.spread, it.entry))
    assert pos.closed and "NO_HOLD_CONFIRMATION" not in [f.leg for f in pos.fills]
    assert H4_LEG in [f.leg for f in pos.fills]
    assert eng.positions == {} and eng.closed[0].win


def test_risk_removal_marks_setup_risk_free_then_closed(eng):
    s, it = arm(eng)
    eng._pre_step(fill_candle(eng, it, 0))
    rr = next(l for l in it.plan.legs if l.name == RISK_REMOVAL)
    first = min((l for l in it.plan.legs if l.name != RISK_REMOVAL), key=lambda l: abs(l.price - it.entry))
    if abs(first.price - it.entry) < abs(rr.price - it.entry):
        pytest.skip("M15 hedefi 4R'den yakın: bu sinyalde 4R bacağı ilk bacak değil")
    if it.side is Side.LONG:
        eng._pre_step(cd(1, it.entry, rr.price, it.entry, it.entry))
    else:
        eng._pre_step(cd(1, it.entry, it.entry, rr.price - eng.spread, it.entry))
    assert s.state is State.RISK_FREE


# ---------------- rapor ----------------
@pytest.fixture(scope="module")
def synth_result(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("bt")
    cfg = cfg_with_policies(tmp)
    m1 = synth(datetime(2021, 8, 2, tzinfo=UTC), 35 * 1440, seed=11, amp=18)
    e = BacktestEngine(cfg, "EURUSD", datetime(2021, 8, 30, tzinfo=UTC), datetime(2021, 9, 6, tzinfo=UTC), D(10000))
    return e.run(m1), tmp, m1, cfg


def test_end_to_end_is_deterministic_and_consistent(synth_result):
    res, tmp, m1, cfg = synth_result
    assert res.trades, "sentetik veride işlem beklenir"
    e2 = BacktestEngine(cfg, "EURUSD", res.start, res.end, D(10000)).run(m1)
    key = lambda r: [(t.id, t.fill_time, t.close_time, t.net_pnl) for t in r.trades]
    assert key(res) == key(e2)
    bal = res.initial_balance
    for t in res.trades:
        assert not t.open and t.position.closed and sum(f.lots for f in t.position.fills) == t.intent.lots
        assert t.balance_before >= 0 and t.net_pnl == t.gross_pnl - t.commission
        bal += t.net_pnl
    assert bal == res.final_balance
    assert [b for _, b in res.equity][-1] == res.final_balance
    assert res.trades[0].fill_time >= res.start                  # warm-up'ta işlem yok
    for t in res.trades:                                         # LOOKAHEAD yok: sinyal = M1 mumunun KAPANIŞI; dolum en erken sonraki mumun açılışı
        assert t.fill_time >= t.intent.time and t.signal_time == t.intent.time


def test_metrics_and_journal_from_trades(synth_result):
    res, *_ = synth_result
    m = compute_metrics(res)
    assert m.n == len(res.trades) == m.wins + m.losses
    assert m.total_r == sum((t.r_gross for t in res.trades), D(0))
    assert m.return_pct == (res.final_balance - res.initial_balance) / res.initial_balance * 100
    assert abs(m.expectancy_r - m.avg_r) < D("1e-9")             # FM-04 ≡ ortalama R
    assert m.max_dd_amount >= 0 and m.max_dd_pct >= 0
    jm = journal_matrix(res)
    assert jm["VALID_WIN"] + jm["VALID_LOSS"] == m.n and jm["INVALID_WIN"] == jm["INVALID_LOSS"] == 0
    rows = criteria_contribution(res.trades)
    assert {r["criterion"] for r in rows} >= {"bos_and_flip", "pro_trend", "swing_break"}
    for r in rows:
        assert r["n_yes"] + r["n_no"] + r["n_unknown"] == m.n


def test_q_m5_list_matches_target_distance(synth_result):
    res, *_ = synth_result
    close = m15_closer_than_4r(res.trades)
    for t in close:
        assert t.m15_target_r < 4
    assert {t.id for t in close} == {t.id for t in res.trades if t.m15_target_r is not None and t.m15_target_r < 4}
    txt = format_report(res)
    assert "Q-M5" in txt and f"Sayı: {len(close)} / {len(res.trades)}" in txt and "Q-L3" in txt and "komisyon dahil değil" not in txt


def test_report_without_commission_says_so(synth_result):
    res, *_ = synth_result
    import dataclasses
    r0 = dataclasses.replace(res, commission=CommissionModel(D(0), D(0), "", D(100000), False))
    assert "komisyon dahil değil" in format_report(r0)


def test_write_outputs_files(synth_result, tmp_path):
    res, *_ = synth_result
    paths = write_outputs(res, tmp_path / "o")
    rows = list(csv.DictReader(paths["trades"].open()))
    assert len(rows) == len(res.trades) and {"r_gross", "net_pnl", "closer_than_4r", "journal_tag"} <= set(rows[0])
    assert all(r["journal_tag"].startswith("VALID_") for r in rows)
    assert paths["report"].read_text(encoding="utf-8").startswith("═══ PHOTON BACKTEST RAPORU")
    assert list(csv.DictReader(paths["fills"].open()))
    assert list(csv.DictReader(paths["criteria"].open()))


def test_backtest_cli_end_to_end(tmp_path, capsys):
    from photon.tests.test_cli_structure import synth_m1
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")).replace("M15: 30,", "M15: 5,").replace("D1: 365, H4: 365", "D1: 5, H4: 5")
            .replace("M1: 7}", "M1: 1}"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    store = CandleStore(tmp_path / "c.sqlite")
    store.put_candles("HISTDATA", synth_m1(datetime(2021, 8, 20, tzinfo=UTC), 20 * 1440))
    store.close()
    rc = main(["backtest", "--config", str(cfgp), "--start", "2021-09-01", "--end", "2021-09-08", "--out", str(tmp_path / "o"),
               "--balance", "20000"])
    out = capsys.readouterr().out
    assert rc == 0 and "PHOTON BACKTEST RAPORU" in out and "20000.00" in out and "Strike rate" in out
    assert (tmp_path / "o" / "EURUSD_report.txt").exists() and (tmp_path / "o" / "EURUSD_trades.csv").exists()


def test_backtest_cli_without_data(tmp_path):
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "e.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    assert main(["backtest", "--config", str(cfgp), "--start", "2021-09-01", "--end", "2021-09-02", "--out", str(tmp_path / "o")]) == 2


def test_signal_candle_itself_never_fills_its_own_order(tmp_path):
    """Sinyali üreten mum (kapanışı = sinyal zamanı) emri dolduramaz: bekleyen emir yalnızca on_m1 döndükten SONRA kaydedilir."""
    cfg = cfg_with_policies(tmp_path)
    m1 = synth(datetime(2021, 8, 2, tzinfo=UTC), 35 * 1440, seed=11, amp=18)
    e = BacktestEngine(cfg, "EURUSD", datetime(2021, 8, 30, tzinfo=UTC), datetime(2021, 9, 6, tzinfo=UTC), D(10000))
    seen = []
    orig = e._pre_step

    def spy(c):
        seen.append((c.open_time, set(e.pending)))               # bu mum işlenirken bekleyen emirler
        orig(c)
    for q in m1:
        evs = e.runner.on_m1(q, pre_step=spy)
        for ev in evs:
            if ev.kind == "SIGNAL":
                assert ev.setup.id not in seen[-1][1]              # sinyal mumunun kendi pre_step'inde emir henüz yoktu
                assert ev.time == q.open_time + q.tf.delta         # sinyal zamanı = mum kapanışı
                e.pending[ev.setup.id] = ev.setup
            elif ev.kind == "CANCELLED":
                e.pending.pop(ev.setup.id, None)


def test_funnel_counts_are_consistent_and_split_by_trend_class(synth_result):
    from photon.backtest.report import diagnostics_text, format_funnel, funnel
    res, *_ = synth_result
    rows = dict(funnel(res))
    get = lambda prefix: next(v for k, v in rows.items() if k.startswith(prefix))
    assert get("7.")["TOPLAM"] == len(res.trades) + len(res.open_trades)
    assert get("6.")["TOPLAM"] == sum(1 for e in res.events if e.kind == "SIGNAL")
    assert get("2.")["TOPLAM"] >= get("3.")["TOPLAM"] >= get("4.")["TOPLAM"] >= get("5.")["TOPLAM"] >= get("6.")["TOPLAM"]
    assert get("4.")["TOPLAM"] == get("   giriş zonu YOK")["TOPLAM"] + get("5.")["TOPLAM"]
    for r in rows.values():
        assert sum(r.get(c, 0) for c in ("PRO", "MIXED", "COUNTER_HTF", "UNKNOWN")) in (r["TOPLAM"], 0)
    assert "PRO" in format_funnel(res) and "NO_ENTRY_ZONE" in diagnostics_text(res)
