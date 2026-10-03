"""Adım 29: minimum stop mesafesi girişten ölçülür (distal'den değil)."""
import signals


def main():
    pip = 0.0001
    bear = {"direction": "BEARISH", "low": 1.13493, "high": 1.13797, "distal": 1.13797,
            "proximal": 1.13493, "eq": 1.13645}
    risk = signals.levels(bear, market="forex", symbol="EUR/USD", spread_pips=0.8,
                          entry_type="risk", current_price=1.125, targeted_level=1.12159)
    # Giriş–stop 33 pip: minimum stop devreye girmez, stop = distal + 0.8 pip tampon.
    assert abs(risk["stop"] - (1.13797 + 0.8 * pip)) < 1e-9, risk
    assert abs(risk["stop_pips_or_pct"] - 31.2) < 1e-6, risk

    # Dar bölgede giriş distal'e yakınsa (confirmation) 3 pip girişten uygulanır.
    tight = {"direction": "BULLISH", "low": 1.10000, "high": 1.10050, "distal": 1.10000,
             "proximal": 1.10050, "eq": 1.10025}
    conf = signals.levels(tight, market="forex", symbol="EUR/USD", spread_pips=0.8,
                          entry_type="confirmation", current_price=1.101, targeted_level=1.11)
    assert conf["entry"] == 1.10000
    assert abs(conf["stop_distance"] - 3 * pip) < 1e-9 and abs(conf["stop"] - (1.10000 - 3 * pip)) < 1e-9, conf
    # Risk girişinde proximal'den ölçülür: mesafe 5 pip + tampon > 3 pip, stop distal tamponunda kalır.
    risk2 = signals.levels(tight, market="forex", symbol="EUR/USD", spread_pips=0.8,
                           entry_type="risk", current_price=1.101, targeted_level=1.11)
    assert abs(risk2["stop"] - (1.10000 - 0.8 * pip)) < 1e-9, risk2

    # Kripto: %0.25 girişten ölçülür.
    poi = {"direction": "BULLISH", "low": 99.9, "high": 100.0, "distal": 99.9,
           "proximal": 100.0, "eq": 99.95}
    crypto = signals.levels(poi, market="crypto", symbol="COINUSDT", atr_value=0.1,
                            entry_type="risk", current_price=105.0, targeted_level=120.0)
    assert crypto["stop_distance"] >= 105.0 * 0.0025 - 1e-9
    print("Minimum stop girişten ölçülüyor (forex 3 pip, kripto %0.25): GEÇTİ")
    print("test_step29: OK")


if __name__ == "__main__":
    main()
