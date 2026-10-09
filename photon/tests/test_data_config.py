from datetime import time

import pytest

from photon.config import ConfigError, load_config
from photon.data import BoundarySpec


def test_boundaries_required_failfast():
    cfg = load_config()
    with pytest.raises(ConfigError, match="candle_boundaries.tz"):
        BoundarySpec.from_config(cfg)


def test_boundaries_from_config(tmp_path):
    p = tmp_path / "c.yaml"
    text = open("config.yaml", encoding="utf-8").read()
    text = (text.replace("  tz: REQUIRED          #", "  tz: America/New_York          #")
                .replace("d1_open: REQUIRED", 'd1_open: "17:00"')
                .replace("h4_anchor: REQUIRED", 'h4_anchor: "17:00"')
                .replace("candle_price_side: REQUIRED", "candle_price_side: BID"))
    p.write_text(text, encoding="utf-8")
    spec = BoundarySpec.from_config(load_config(p))
    assert spec.tz.key == "America/New_York" and spec.d1_open == time(17, 0)


def test_live_feed_blocked_until_connection_given():
    cfg = load_config()
    with pytest.raises(ConfigError, match="data.live.port"):
        cfg.require("live_feed")
    cfg.require("hist_dukascopy", "hist_oanda", "data_cache")
