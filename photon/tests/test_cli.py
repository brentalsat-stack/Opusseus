from photon.__main__ import main


def test_check_exit_codes(capsys):
    assert main(["check"]) == 0
    assert main(["check", "--module", "structure", "--module", "risk"]) == 0
    assert main(["check", "--module", "structure_m1"]) == 2
    assert "swing_min_pullback_pips.EURUSD.M1" in capsys.readouterr().err
    assert main(["check", "--module", "strategy", "--module", "backtest"]) == 0
