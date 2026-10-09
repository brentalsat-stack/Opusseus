from photon.__main__ import main


def test_check_exit_codes(capsys):
    assert main(["check"]) == 0
    assert main(["check", "--module", "structure", "--module", "risk"]) == 0
    assert main(["check", "--module", "strategy"]) == 2
    assert "v_shape_metric" in capsys.readouterr().err
