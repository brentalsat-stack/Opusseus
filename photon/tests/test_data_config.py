from datetime import time

import pytest

from photon.config import ConfigError, load_config
from photon.data import BoundarySpec


def test_boundaries_from_config():
    spec = BoundarySpec.from_config(load_config())
    assert spec.tz.key == "America/New_York" and spec.d1_open == time(17, 0) and spec.h4_anchor == time(17, 0)


def test_boundaries_failfast_when_required(tmp_path):
    p = tmp_path / "c.yaml"
    text = open("config.yaml", encoding="utf-8").read().replace("tz: America/New_York", "tz: REQUIRED")
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="candle_boundaries.tz"):
        BoundarySpec.from_config(load_config(p))


def test_ny_h4_opens_match_tradingview():
    from datetime import datetime, timezone
    from photon.data import Timeframe, bin_bounds
    spec = BoundarySpec.from_config(load_config())
    # yaz (EDT): NY 17,21,01,05,09,13 = 21,01,05,09,13,17 UTC
    opens = []
    for h in range(0, 24):
        s, _ = bin_bounds(datetime(2021, 9, 1, h, 30, tzinfo=timezone.utc), Timeframe.H4, spec)
        opens.append(s.hour)
    assert sorted(set(opens)) == [1, 5, 9, 13, 17, 21]


def test_pending_modules_still_blocked_only_by_v_shape_and_m1():
    cfg = load_config()
    cfg.require("data", "data_boundaries", "live_feed", "hist_dukascopy", "hist_oanda")
