"""Adım 30: kaldıraçlı token elemesi sonek kuralıyla; EXCLUDED_SYMBOLS config listesi."""
import config
import data_binance


def main():
    listed = {"BTCUSDT", "BTCUPUSDT", "ETHUSDT", "ETHDOWNUSDT", "SUPERUSDT", "JUPUSDT", "SYRUPUSDT",
              "BNBBULLUSDT", "BNBUSDT", "SOLBEARUSDT", "SOLUSDT", "UUSDT", "XAUTUSDT", "PAXGUSDT",
              "CRCLBUSDT", "SPCXBUSDT", "SNDKBUSDT", "USDCUSDT", "USD1USDT", "RLUSDUSDT", "BTCETH"}
    excluded = {symbol for symbol in listed if data_binance._excluded_symbol(symbol, listed)}
    assert {"BTCUPUSDT", "ETHDOWNUSDT", "BNBBULLUSDT", "SOLBEARUSDT"} <= excluded, excluded
    assert not ({"SUPERUSDT", "JUPUSDT", "SYRUPUSDT", "BTCUSDT", "BNBUSDT", "SOLUSDT"} & excluded), excluded
    assert {"UUSDT", "XAUTUSDT", "PAXGUSDT", "CRCLBUSDT", "SPCXBUSDT", "SNDKBUSDT",
            "USDCUSDT", "USD1USDT", "RLUSDUSDT", "BTCETH"} <= excluded, excluded
    for symbol in ("UUSDT", "XAUTUSDT", "PAXGUSDT"):
        assert symbol in config.EXCLUDED_SYMBOLS
    # Config'e eklenen sembol hemen elenir.
    config.EXCLUDED_SYMBOLS.append("TESTXUSDT")
    try:
        assert data_binance._excluded_symbol("TESTXUSDT", listed | {"TESTXUSDT"})
    finally:
        config.EXCLUDED_SYMBOLS.remove("TESTXUSDT")
    print("Sonek kuralı (BTCUP elenir; SUPER/JUP/SYRUP kalır) ve EXCLUDED_SYMBOLS: GEÇTİ")
    print("test_step30: OK")


if __name__ == "__main__":
    main()
