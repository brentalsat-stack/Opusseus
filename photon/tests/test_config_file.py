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


def test_pending_values_stay_required():
    c = load_config()
    for p in ("swing_min_pullback_pips.EURUSD.M1", "blackout.tz", "zone_draw_mode.H4",
              "require_sweep_zone", "counter_htf_require_double_bos",
              "target_allocation.counter_trend.allocation_pct", "news_filter.lead_hours"):
        assert c.get(p) == "REQUIRED", p
