import copy
from decimal import Decimal

import pytest

from photon.config import (MODULES, Config, ConfigError, find_required, load_config, require,
                           validate_all, validate_module)
from photon.config.loader import get_path


@pytest.fixture
def cfg():
    return load_config()


def mutate(cfg, path, value):
    raw = copy.deepcopy(cfg.raw)
    node = raw
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return Config(raw)


def test_blocker_free_modules_ready_with_pending_fields(cfg):
    for m in ("data", "structure", "risk", "session", "execution", "journal"):
        assert validate_module(cfg, m).ok, m
        require(cfg, m)  # fırlatmamalı


@pytest.mark.parametrize("m", ["structure_m1", "vshape", "strategy", "signals", "backtest"])
def test_pending_modules_blocked(cfg, m):
    assert not validate_module(cfg, m).ok
    with pytest.raises(ConfigError):
        require(cfg, m)


def test_decided_modules_now_ready(cfg):
    for m in ("zones", "management", "risk_sizing", "session_blackout"):
        assert validate_module(cfg, m).ok, m


def test_error_lists_all_missing_fields(cfg):
    c = cfg
    for p in ("zone_draw_mode.H4", "zone_draw_mode.M15", "zone_draw_mode.M1", "reaction_min.pips",
              "range_detection.min_candles", "require_refined_ltf_zone_in_htf_poi"):
        c = mutate(c, p, "REQUIRED")
    with pytest.raises(ConfigError) as ei:
        require(c, "zones")
    msg = str(ei.value)
    for p in ("zone_draw_mode.H4", "zone_draw_mode.M15", "zone_draw_mode.M1", "reaction_min.pips",
              "range_detection.min_candles", "require_refined_ltf_zone_in_htf_poi"):
        assert p in msg


def test_strategy_error_names_dependency_gaps(cfg):
    with pytest.raises(ConfigError) as ei:
        require(cfg, "strategy")
    msg = str(ei.value)
    assert "v_shape_metric" in msg and "vshape" in msg


@pytest.mark.parametrize("bad", [None, "", "REQUIRED", "  "])
def test_blank_or_required_value_blocks(cfg, bad):
    c = mutate(cfg, "risk_pct", bad)
    with pytest.raises(ConfigError, match="risk_pct"):
        require(c, "risk")


def test_missing_key_blocks(cfg):
    raw = copy.deepcopy(cfg.raw)
    del raw["max_losses_per_day"]
    with pytest.raises(ConfigError, match="max_losses_per_day"):
        require(Config(raw), "risk")


def test_blocked_module_does_not_affect_independent_module(cfg):
    c = mutate(cfg, "risk_pct", "REQUIRED")
    assert not validate_module(c, "risk").ok
    assert validate_module(c, "structure").ok and validate_module(c, "session").ok


def test_filling_pending_fields_unblocks(cfg):
    c = mutate(cfg, "v_shape_metric", {"type": "TEST"})
    assert validate_module(c, "vshape").ok and validate_module(c, "strategy").ok
    c = mutate(cfg, "blackout.tz", "REQUIRED")
    assert not validate_module(c, "session_blackout").ok


@pytest.mark.parametrize("path,value", [
    ("risk_pct", Decimal("0.02")),        # RK-R001 tavanı %1
    ("risk_pct", 0),
    ("min_sl_pips", 1),                   # SL-R003
    ("entry_type", "MARKET"),
    ("trend_change_confirmation", "TRIPLE_BOS"),
    ("timezones.session", "Mars/Olympus"),
    ("timezones.storage", "Europe/London"),
    ("sessions_london", [["10:00", "07:00"]]),
    ("swing_threshold_inclusive", "yes"),
    ("mode.auto_order", True),
    ("pair_params.EURUSD.pip_size", 0),
    ("eqh_tolerance.pips", -1),
    ("zone_draw_mode.H4", "MAGIC"),
    ("poi_scoring.weights.pro_trend", 0),
    ("swing_hold_confirmation", "M1_CHOCH"),
    ("costs.commission.rate_pct", -0.1),
])
def test_invalid_values_rejected(cfg, path, value):
    c = mutate(cfg, path, value)
    modules = [m for m, s in MODULES.items() if any(r.path.replace("{pair}", "EURUSD") == path for r in s.requires)]
    assert modules, f"{path} hiçbir modülde denetlenmiyor"
    assert any(not validate_module(c, m).ok for m in modules)


def test_partial_fields_only_required_in_partial_mode(cfg):
    c = mutate(cfg, "risk_removal_method", "BE_AT_FIRST_EXEC_BOS")
    c = mutate(c, "partial_pct", "REQUIRED")
    rep = validate_module(c, "management")
    assert "partial_pct" not in rep.missing


def test_multi_pair_expansion(cfg):
    raw = copy.deepcopy(cfg.raw)
    raw["pairs"] = ["EURUSD", "GBPUSD"]
    rep = validate_module(Config(raw), "data")
    assert "pair_params.GBPUSD.pip_size" in rep.missing
    rep = validate_module(Config(raw), "structure")
    assert "swing_min_pullback_pips.GBPUSD.H4" in rep.missing


def test_every_required_in_config_is_covered_by_a_module(cfg):
    covered = set()
    for spec in MODULES.values():
        for r in spec.requires:
            covered.update(r.path.replace("{pair}", p) for p in cfg.pairs)
    # `when` koşullu olanlar dahil; yaprak REQUIRED yolları kapsanmalı
    assert set(find_required(cfg.raw)) <= covered


def test_no_defaults_injected(cfg):
    assert get_path(cfg.raw, "v_shape_metric") == "REQUIRED"
    assert not validate_all(cfg)["strategy"].ok


def test_loader_uses_decimal_not_float(cfg):
    assert cfg.pip_size("EURUSD") == Decimal("0.0001")
    assert isinstance(cfg.get("risk_pct"), Decimal) and cfg.get("risk_pct") == Decimal("0.01")
    assert cfg.swing_min_pullback_pips("EURUSD", "H4") == Decimal(40)
