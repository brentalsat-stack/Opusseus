"""RK-R001..R004, FM-02, SL-R001..R003, SD-R008/EN-R009, T-RK-01/02, T-EN-06."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from photon.config import ConfigError, load_config
from photon.risk.limits import DayLossTracker
from photon.risk.sizing import SizingParams, SizeResult, position_size
from photon.risk.stops import EntryPlan, Rejected, Side, StopParams, ZoneBounds, plan_entry, stop_price

UTC = timezone.utc
PIP = D("0.0001")


def sp(risk="0.005", **kw):
    base = dict(pip_size=PIP, pip_value_per_lot=D(10), lot_step=D("0.01"), min_lot=D("0.01"), min_sl_pips=D(2),
                units_per_lot=D(100000), risk_pct=D(risk))
    return SizingParams(**{**base, **kw})


def px(p):  # 1.1000 + pips
    return D("1.1000") + D(str(p)) * PIP


# ---------------- sizing ----------------
def test_t_rk_01_position_size_example():
    r = position_size(D(10000), px(0), px(-5), sp())
    assert isinstance(r, SizeResult) and r.lots == D("1.00") and r.units == D(100000)
    assert r.risk_amount == D(50) and r.actual_risk == D(50) and r.pip_risk == D(5)


@pytest.mark.parametrize("sl,lots", [("4.7", "1.06"), ("3", "1.66"), ("13", "0.38")])
def test_lots_always_rounded_down_rk_r004(sl, lots):
    r = position_size(D(10000), px(0), px(0) - D(sl) * PIP, sp())
    assert r.lots == D(lots) and r.actual_risk <= r.risk_amount


def test_one_percent_risk_default_config_values():
    cfg = load_config()
    p = SizingParams.from_config(cfg, "EURUSD")
    assert p.risk_pct == D("0.01") and p.lot_step == D("0.01") and p.units_per_lot == D(100000)
    r = position_size(D(10000), px(0), px(-2), p)          # %1 = 100 USD / (2 pip × 10) = 5.00 lot
    assert r.lots == D("5.00") and r.units == D(500000)


def test_risk_pct_above_one_percent_rejected_rk_r001():
    with pytest.raises(ValueError, match="RK-R001"):
        sp("0.0101")
    with pytest.raises(ValueError):
        sp("0")


def test_sl_below_2_pip_rejected_and_lot_below_min():
    assert position_size(D(10000), px(0), px("-1.6"), sp()).rule == "SL-R003"
    r = position_size(D(100), px(0), px(-50), sp())        # 0.5 USD / (50×10) = 0.001 lot < 0.01
    assert isinstance(r, Rejected) and r.reason == "LOT_BELOW_MIN"
    assert position_size(D(0), px(0), px(-5), sp()).reason == "INVALID_INPUT"


def test_sizing_gate_failfast():
    cfg = load_config()
    SizingParams.from_config(cfg, "EURUSD")
    raw = dict(cfg.raw)
    raw["pair_params"] = {"EURUSD": {**cfg.raw["pair_params"]["EURUSD"], "lot_step": "REQUIRED"}}
    from photon.config import Config
    with pytest.raises(ConfigError, match="lot_step"):
        SizingParams.from_config(Config(raw), "EURUSD")


# ---------------- stops / entries ----------------
def stp(mode="FIXED_SL", **kw):
    base = dict(pip_size=PIP, entry_price_mode=mode, fixed_sl_pips=D(2), sl_buffer_pips=D(0), min_sl_pips=D(2))
    return StopParams(**{**base, **kw})


DEMAND = ZoneBounds(top=px(10), bottom=px(0))     # 10 pip yüksekliğinde talep


def test_stop_is_one_pipette_beyond_zone_extreme_sl_r001():
    assert stop_price(DEMAND, Side.LONG, stp()) == px(0) - D("0.00001")
    sup = ZoneBounds(top=px(10), bottom=px(0))
    assert stop_price(sup, Side.SHORT, stp()) == px(10) + D("0.00001")
    assert stop_price(DEMAND, Side.LONG, stp(sl_buffer_pips=D("1.5"))) == px("-1.6")   # buffer + pipette


def test_fixed_sl_entry_is_stop_plus_2_pip_long_and_minus_short():
    p = plan_entry(DEMAND, Side.LONG, stp())
    assert isinstance(p, EntryPlan) and p.stop == px("-0.1") and p.entry == px("1.9") and p.pip_risk == D(2)
    s = plan_entry(DEMAND, Side.SHORT, stp())
    assert s.stop == px("10.1") and s.entry == px("8.1") and s.pip_risk == D(2)
    assert p.stop < DEMAND.bottom and s.stop > DEMAND.top      # SL-R001: zonun arkasında


def test_fixed_sl_zone_smaller_than_2_pip_uses_distal_with_2_pip_stop():
    tiny = ZoneBounds(top=px("1.5"), bottom=px(0))
    p = plan_entry(tiny, Side.LONG, stp())
    assert p.entry == px("1.5") and p.stop == px("-0.5") and p.pip_risk == D(2) and "distal" in p.note
    assert p.stop < tiny.bottom
    sh = plan_entry(tiny, Side.SHORT, stp())
    assert sh.entry == px(0) and sh.stop == px(2)


def test_zone_exactly_2_pip_is_not_smaller():
    z = ZoneBounds(top=px(2), bottom=px(0))
    p = plan_entry(z, Side.LONG, stp())
    assert p.note == "" and p.entry == px("1.9")


def test_distal_and_eq_modes_and_t_en_06_reject_below_min_sl():
    d = plan_entry(DEMAND, Side.LONG, stp("DISTAL"))
    assert d.entry == px(10) and d.pip_risk == D("10.1")
    e = plan_entry(DEMAND, Side.LONG, stp("EQ"))
    assert e.entry == px(5) and e.pip_risk == D("5.1")
    small = ZoneBounds(top=px("1.5"), bottom=px(0))
    r = plan_entry(small, Side.LONG, stp("DISTAL"))             # 1.5 + 0.1 = 1.6 pip
    assert isinstance(r, Rejected) and r.reason == "SL_BELOW_MIN" and r.rule == "SL-R003"
    assert isinstance(plan_entry(ZoneBounds(top=px("1.9"), bottom=px(0)), Side.LONG, stp("DISTAL")), EntryPlan)  # 2.0 tam


def test_stop_params_from_config():
    p = StopParams.from_config(load_config(), "EURUSD")
    assert (p.entry_price_mode, p.fixed_sl_pips, p.sl_buffer_pips, p.min_sl_pips) == ("FIXED_SL", D(2), D(0), D(2))


# ---------------- günlük kayıp (RK-R003) ----------------
IST = ZoneInfo("Europe/Istanbul")


def tracker():
    return DayLossTracker.from_config(load_config())


def ist(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=IST).astimezone(UTC)


def test_t_rk_02_third_loss_locks_the_day():
    t = tracker()
    assert not t.is_locked(ist(2021, 9, 1, 10))
    t.record_close(ist(2021, 9, 1, 10), D("-1")); t.record_close(ist(2021, 9, 1, 11), D("-1"))
    assert not t.is_locked(ist(2021, 9, 1, 12))
    t.record_close(ist(2021, 9, 1, 13), D("-0.5"))
    assert t.is_locked(ist(2021, 9, 1, 14)) and t.losses(ist(2021, 9, 1, 14)) == 3


def test_reset_at_istanbul_midnight():
    t = tracker()
    for h in (9, 10, 11):
        t.record_close(ist(2021, 9, 1, h), D("-1"))
    assert t.is_locked(ist(2021, 9, 1, 23, 59))
    assert not t.is_locked(ist(2021, 9, 2, 0, 0))              # 00:00 İstanbul → yeni gün
    # UTC 20:59 = İstanbul 23:59 (aynı gün), UTC 21:00 = İstanbul 00:00 (yeni gün)
    assert t.day_key(datetime(2021, 9, 1, 20, 59, tzinfo=UTC)) != t.day_key(datetime(2021, 9, 1, 21, 0, tzinfo=UTC))


def test_only_net_negative_closes_count():
    t = tracker()
    assert t.record_close(ist(2021, 9, 1, 9), D("-0.01")) is True
    assert t.record_close(ist(2021, 9, 1, 9), D("0")) is False       # tam BE kayıp değil
    assert t.record_close(ist(2021, 9, 1, 9), D("3")) is False
    assert t.losses(ist(2021, 9, 1, 9)) == 1


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        tracker().is_locked(datetime(2021, 9, 1, 10))
