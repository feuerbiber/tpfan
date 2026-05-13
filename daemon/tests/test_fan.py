from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.hw.fan import Fan, FanState


FAKE_PROC = """status:\t\tenabled
speed:\t\t2754
level:\t\tauto
commands:\tlevel <level> (<level> is 0-7, auto, disengaged, full-speed)
"""


def _write_fan(tmp: Path, content: str) -> Path:
    p = tmp / "fan"
    p.write_text(content)
    return p


def test_read_state(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    fan = Fan(path=p)
    st = fan.read()
    assert st == FanState(speed_rpm=2754, level="auto", enabled=True)


def test_set_level_writes_command(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    written: list[str] = []
    fan = Fan(path=p, _writer=lambda s: written.append(s))
    fan.set_level("3")
    assert written == ["level 3"]


def test_set_level_rejects_invalid(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    fan = Fan(path=p, _writer=lambda s: None)
    with pytest.raises(ValueError):
        fan.set_level("99")
    with pytest.raises(ValueError):
        fan.set_level("full-speed")


def test_set_level_retries_on_oserror(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    calls = {"n": 0}

    def flaky(s: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("EBUSY")

    fan = Fan(path=p, _writer=flaky, _sleep=lambda _: None)
    fan.set_level("2")
    assert calls["n"] == 3


def test_set_level_gives_up_after_three(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)

    def always_fail(s: str) -> None:
        raise OSError("EBUSY")

    fan = Fan(path=p, _writer=always_fail, _sleep=lambda _: None)
    with pytest.raises(OSError):
        fan.set_level("2")
