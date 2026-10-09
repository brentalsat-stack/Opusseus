"""config.yaml, DECISIONS.md ile tutarlı mı."""
from decimal import Decimal

from photon.config import load_config


def test_decided_values():
    c = load_config()
    assert c.pairs == ("EURUSD",)
    assert c.get("mode.auto_order") is False
    assert c.get("swing_threshold_inclusive") is True
    assert [c.swing_min_pullback_pips("EURUSD", t) for t in ("D1", "H4", "M15")] == [90, 40, 15]
    assert c.get("trend_change_confirmation") == "SINGLE_BOS"
    assert (c.get("entry_type"), c.get("entry_price_mode"), c.get("fixed_sl_pips")) == ("CONFIRMATION", "FIXED_SL", 2)
    assert c.get("sl_buffer_pips") == 0 and c.get("min_sl_pips") == 2
    assert c.get("risk_pct") == Decimal("0.01") and c.get("max_losses_per_day") == 3
    assert (c.get("risk_removal_method"), c.get("partial_pct"), c.get("partial_at_r")) == ("PARTIAL", 20, 4)
    assert c.get("pro_trend_reference") == "BOTH"
    assert c.get("sessions_london") == [["07:00", "10:00"], ["12:00", "15:00"]]
    assert c.get("day_reset.tz") == "Europe/Istanbul"
    assert c.get("timezones.session") == "Europe/London"
    assert c.get("decisional_flip_requires_sweep") is False


def test_v2_decisions():
    c = load_config()
    assert c.get("blackout.tz") == "UTC" and (c.get("blackout.start"), c.get("blackout.end")) == ("21:00", "23:00")
    assert c.get("counter_htf_require_double_bos") is True
    assert c.get("swing_hold_confirmation") == "H4_CHOCH"
    assert c.get("eqh_tolerance.pips") == 2 and c.get("reaction_min.pips") == 2
    assert c.get("range_detection.min_candles") == 3
    assert c.get("require_liquidation") is True
    assert c.get("zone_draw_mode") == {"H4": "RANGE", "M15": "CANDLE", "M1": "REACTION_BASE_TO_TOP"}
    assert (c.get("require_sweep_zone"), c.get("require_inducement"), c.get("require_pd_alignment")) == (False, False, False)
    assert c.get("range_extreme_filter.allowed_band_pct") == 25
    w = c.get("poi_scoring.weights")
    assert sum(w.values()) == Decimal("16") and w["bos_and_flip"] == 3 and w["sweep_zone"] == Decimal("1.5")
    assert c.get("news_filter.provider") == "FOREXFACTORY" and c.get("news_filter.currencies") == ["EUR", "USD"]
    assert (c.get("target_allocation.counter_trend.allocation_pct"), c.get("target_allocation.range.allocation_pct")) == (80, 100)
    p = c.get("pair_params.EURUSD")
    assert (p["pip_value_per_lot"], p["lot_step"], p["min_lot"]) == (10, Decimal("0.01"), Decimal("0.01"))
    cm = c.get("costs.commission")
    assert cm["rate_pct"] == Decimal("0.002") and cm["min_per_order"] == 2


def test_only_expected_fields_remain_required():
    from photon.config import find_required
    assert sorted(find_required(load_config().raw)) == sorted([
        "swing_min_pullback_pips.EURUSD.M1", "v_shape_metric",                    # Aşama 4 / kalibrasyon
        "candle_boundaries.tz", "candle_boundaries.d1_open", "candle_boundaries.h4_anchor",   # Q-D01
        "candle_price_side",                                                      # Q-D02
        "data.live.host", "data.live.port", "data.live.client_id"])               # IBKR bağlantısı
