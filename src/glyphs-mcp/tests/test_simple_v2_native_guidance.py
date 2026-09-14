"""Execute the focused guidance examples; native qualification remains separate."""
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
REFERENCES = ROOT / "skills/glyphs-mcp-development/references"


def blocks(name):
    return re.findall(r"```python\n(.*?)```", (REFERENCES / name).read_text(), re.S)


class Layer:
    def __init__(self, flag=False):
        self.flag = flag
        self.writes = []

    def temporarilyDisableRounding(self):
        return self.flag

    def setTemporarilyDisableRounding_(self, value):
        self.writes.append(value)
        self.flag = value


def run_precision(layers, operation):
    exec(blocks("native-precision.md")[0], {
        "target_layers": layers, "perform_requested_operation": operation,
        "verify_exact_requested_values": lambda targets: None,
    })


@pytest.mark.parametrize("fail", [False, True])
def test_precision_restores_each_previous_flag(fail):
    layers = [Layer(False), Layer(True), Layer(False)]

    def operation(targets):
        assert all(layer.flag for layer in targets)
        if fail:
            raise ValueError("injected operation failure")

    if fail:
        with pytest.raises(ValueError, match="injected"):
            run_precision(layers, operation)
    else:
        run_precision(layers, operation)
    assert [layer.flag for layer in layers] == [False, True, False]
    assert [layer.writes for layer in layers] == [[True, False], [True, True], [True, False]]


def test_precision_preflights_all_layers_before_mutation():
    first = Layer()
    with pytest.raises(RuntimeError, match="unavailable"):
        run_precision([first, object()], lambda _: pytest.fail("must not edit"))
    assert first.writes == []


def test_precision_attempts_other_restorations_if_one_fails():
    layers = [Layer(), Layer(), Layer()]
    original = layers[1].setTemporarilyDisableRounding_

    def setter(value):
        if value is False:
            raise RuntimeError("injected restoration failure")
        original(value)

    layers[1].setTemporarilyDisableRounding_ = setter
    with pytest.raises(RuntimeError, match="restoration failure"):
        run_precision(layers, lambda _: None)
    assert layers[0].flag is False and layers[2].flag is False
    assert layers[1].flag is True  # A restoration error must remain visible.


@pytest.mark.parametrize("callable_flags", [False, True])
def test_feature_flags_use_the_native_value(callable_flags):
    def field(value):
        return (lambda: value) if callable_flags else value
    namespace = {"feature": SimpleNamespace(automatic=field(False), disabled=field(True))}
    exec(blocks("glyphs4-api-notes.md")[1], namespace)
    assert namespace["automatic"] is False and namespace["disabled"] is True


@pytest.mark.parametrize("result,message", [
    ((False, "missing glyph in ss20 line 1"), "missing glyph in ss20 line 1"),
    (None, "Unverified compile result shape"),
    (True, "Unverified compile result shape"),
])
def test_compile_example_rejects_failure_and_unknown_shape(result, message):
    with pytest.raises(RuntimeError, match=message):
        exec(blocks("glyphs4-api-notes.md")[2],
             {"font": SimpleNamespace(compileFeatures=lambda: result)})


def test_compile_example_accepts_observed_native_success():
    exec(blocks("glyphs4-api-notes.md")[2],
         {"font": SimpleNamespace(compileFeatures=lambda: (True, None))})
