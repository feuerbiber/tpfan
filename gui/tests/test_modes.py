from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")


def test_mode_buttons_emit_signal(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=["quiet", "balanced", "performance"])
    qtbot.addWidget(p)

    with qtbot.waitSignal(p.modeRequested, timeout=500) as blocker:
        p.auto_btn.click()
    assert blocker.args == ["auto"]

    with qtbot.waitSignal(p.modeRequested, timeout=500) as blocker:
        p.curve_btn.click()
    assert blocker.args == ["curve"]


def test_failsafe_spinbox_emits(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=[])
    qtbot.addWidget(p)
    p.failsafe_spin.setValue(85.0)
    with qtbot.waitSignal(p.failsafeRequested, timeout=500) as blocker:
        p.failsafe_spin.editingFinished.emit()
    assert blocker.args == [85.0]


def test_profile_change_emits_profile_mode(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=["quiet", "balanced"])
    qtbot.addWidget(p)
    p.profile_combo.setCurrentText("quiet")
    with qtbot.waitSignal(p.modeRequested, timeout=500) as blocker:
        p.apply_profile_btn.click()
    assert blocker.args == ["profile:quiet"]


def test_manual_buttons_disabled_outside_manual(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=[])
    qtbot.addWidget(p)
    p.set_mode_state("auto")
    assert all(not b.isEnabled() for b in p._manual_buttons)
    p.set_mode_state("manual")
    assert all(b.isEnabled() for b in p._manual_buttons)
    p.set_mode_state("curve")
    assert all(not b.isEnabled() for b in p._manual_buttons)


def test_failsafe_no_emit_when_unchanged(qtbot):
    from tpfan_gui.views.modes import ModesPanel
    p = ModesPanel(profiles=[])
    qtbot.addWidget(p)
    received: list[float] = []
    p.failsafeRequested.connect(received.append)
    p.failsafe_spin.editingFinished.emit()
    assert received == []
    p.failsafe_spin.setValue(85.0)
    p.failsafe_spin.editingFinished.emit()
    assert received == [85.0]
    p.failsafe_spin.editingFinished.emit()
    assert received == [85.0]
