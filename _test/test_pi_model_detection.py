"""Platform detection must recognise Compute Modules, not just consumer boards.

/proc/device-tree/model on a CM5 reads "Raspberry Pi Compute Module 5 Rev 1.0"
-- a string containing neither "Raspberry Pi 5" nor "Raspberry Pi 4". Every
substring check written against the consumer board names alone therefore
classified CineMate's own dev unit as 'other' and sent Pi-5-only code down the
legacy path: the pi_model Redis key reported 'other', and the REC-tone
hardware PWM picked the Pi 4 channel mapping (GPIO18 -> channel 0 instead of
channel 2).
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from module import sensor_detect  # noqa: E402


# The exact strings the kernel reports, trailing NUL included.
MODELS = {
    "Raspberry Pi Compute Module 5 Rev 1.0\x00": "pi5",
    "Raspberry Pi 5 Model B Rev 1.0\x00": "pi5",
    "Raspberry Pi 500\x00": "pi5",
    "Raspberry Pi Compute Module 4 Rev 1.1\x00": "pi4",
    "Raspberry Pi 4 Model B Rev 1.4\x00": "pi4",
    "Raspberry Pi 400 Rev 1.0\x00": "pi4",
    "Raspberry Pi 3 Model B Plus Rev 1.3\x00": "other",
}


@pytest.fixture
def model(monkeypatch):
    def _set(text):
        monkeypatch.setattr(sensor_detect, "read_pi_model", lambda: text)

    return _set


@pytest.mark.parametrize("text,expected", sorted(MODELS.items()))
def test_pi_family_classifies_every_shipped_board(model, text, expected):
    model(text)
    assert sensor_detect.pi_family() == expected


def test_compute_module_5_is_not_classified_as_other(model):
    # The specific regression: this is the board CineMate develops on.
    model("Raspberry Pi Compute Module 5 Rev 1.0\x00")
    assert sensor_detect.pi_family() == "pi5"
    assert sensor_detect.is_pi5_family() is True
    assert sensor_detect.is_pi4_family() is False


def test_unreadable_model_is_unknown_not_a_guess(model):
    model("")
    assert sensor_detect.pi_family() == "unknown"


@pytest.mark.parametrize("text,expected", sorted(MODELS.items()))
def test_families_are_mutually_exclusive(model, text, expected):
    model(text)
    assert not (sensor_detect.is_pi4_family() and sensor_detect.is_pi5_family())


def test_hardware_pwm_accepts_the_pi_model_it_is_given():
    # GPIOOutput passes pi_model= into this constructor. It used not to accept
    # the keyword, so every hardware-PWM REC tone raised TypeError, which the
    # surrounding handler swallowed as "PWM setup failed" and downgraded to
    # software PWM -- hardware PWM could never engage on any board.
    #
    # Parsed rather than imported: module.gpio_output pulls in lgpio, which
    # only exists on a Pi, and stubbing it here would leak into sys.modules
    # for the rest of the suite.
    import ast

    tree = ast.parse((REPO_ROOT / "src/module/gpio_output.py").read_text(encoding="utf-8"))

    ctor = next(
        node
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef) and cls.name == "_HardwarePWMToneOutput"
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    accepted = {arg.arg for arg in ctor.args.args} | {arg.arg for arg in ctor.args.kwonlyargs}

    passed = {
        kw.arg
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_HardwarePWMToneOutput"
        for kw in call.keywords
        if kw.arg
    }

    assert passed, "expected _HardwarePWMToneOutput to be constructed somewhere"
    assert passed <= accepted, f"call site passes {passed - accepted}, constructor accepts {accepted}"
