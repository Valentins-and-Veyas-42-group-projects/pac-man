import pytest
from delete_me.analyze.coaching_main import run


def test_coaching_demo_composes_real_analysis_algorithms(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run() == 0
    output = capsys.readouterr().out

    assert "RIGHT died=True" in output
    assert "DOWN  died=False" in output
    assert "quality: blunder" in output
    assert "missed_ghost_combo" in output
