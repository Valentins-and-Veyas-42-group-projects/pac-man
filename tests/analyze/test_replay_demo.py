import pytest
from delete_me.analyze.replay_main import run


def test_replay_demo_processes_multiple_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run() == 0
    output = capsys.readouterr().out

    assert "tick 100" in output
    assert "tick 200" in output
    assert "tick 300" in output
    assert "reconstructed collectibles=3" in output
    assert "reconstructed collectibles=2" in output
    assert "reconstructed collectibles=0" in output
    assert "replay summary" in output
