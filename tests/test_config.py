from __future__ import annotations

import pytest

from lab_nidaq_mcp.config import NiDaqConfigError, load_devices_config


def base():
    return {
        "Dev2": {
            "model": "USB-6009",
            "interlock": "none",
            "analog_outputs": {"ao0": {"range": [0, 5], "safe_value": 1.0}},
            "digital_outputs": {"port1/line0": {"safe_value": 0}},
        }
    }


def test_valid_config_preserves_explicit_zero_safe_value():
    config = load_devices_config(base())["Dev2"]
    assert config.digital_outputs["port1/line0"].safe_value == 0


def test_missing_safe_value_is_rejected_not_defaulted():
    data = base()
    del data["Dev2"]["analog_outputs"]["ao0"]["safe_value"]
    with pytest.raises(NiDaqConfigError, match="safe_value"):
        load_devices_config(data)


def test_missing_interlock_is_rejected():
    with pytest.raises(NiDaqConfigError, match="interlock"):
        load_devices_config({"Dev2": {"model": "USB-6009"}})


def test_missing_model_is_rejected():
    with pytest.raises(NiDaqConfigError, match="model"):
        load_devices_config({"RenamedDevice": {"interlock": "none"}})


def test_interlock_line_cannot_be_an_output():
    data = base()
    data["Dev2"]["interlock"] = {"line": "port1/line0", "require": 1}
    with pytest.raises(NiDaqConfigError, match="interlock line"):
        load_devices_config(data)


def test_ao_range_outside_physical_range_is_rejected():
    data = base()
    data["Dev2"]["analog_outputs"]["ao0"]["range"] = [-1, 5]
    with pytest.raises(NiDaqConfigError, match="physical"):
        load_devices_config(data)


def test_analog_inputs_do_not_require_artifact_dir():
    """Single-point reads must not demand waveform storage.

    ``artifact_dir`` exists to hold an acquired waveform. Requiring it merely
    to declare an analog input would force a directory on the ``READ AI`` user,
    who never produces an artifact.
    """
    data = {
        "Dev2": {
            "model": "USB-6009",
            "interlock": "none",
            "analog_inputs": {"ai0": {"range": [-10, 10]}},
        }
    }
    config = load_devices_config(data)["Dev2"]
    assert "ai0" in config.analog_inputs
    assert config.artifact_dir is None
    assert config.max_samples is None


def test_artifact_dir_requires_max_samples(tmp_path):
    data = {
        "Dev2": {
            "model": "USB-6009",
            "interlock": "none",
            "artifact_dir": str(tmp_path),
        }
    }
    with pytest.raises(NiDaqConfigError, match="max_samples"):
        load_devices_config(data)


@pytest.mark.parametrize(
    "mutation",
    [
        {
            "Dev1": {
                "model": "USB-6210",
                "interlock": "none",
                "analog_outputs": {"ao0": {"range": [0, 5], "safe_value": 0}},
            }
        },
        {"Dev2": {"model": "USB-6009", "interlock": None}},
        {"Dev2": {"model": "USB-6009", "interlock": {"line": "port0/line0"}}},
        {
            "Dev2": {
                "model": "USB-6009",
                "interlock": "none",
                "digital_outputs": {"port0/line0": {}},
            }
        },
    ],
)
def test_other_incomplete_or_impossible_configs_fail_closed(mutation):
    with pytest.raises((NiDaqConfigError, TypeError, ValueError)):
        load_devices_config(mutation)
