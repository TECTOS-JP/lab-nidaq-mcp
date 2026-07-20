"""Strict device configuration and physical-capability validation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from lab_nidaq_mcp.resource import parse_resource_name
from lab_nidaq_mcp.wire import parse_wire_command


class NiDaqConfigError(ValueError):
    """Configuration is incomplete, inconsistent, or physically impossible."""


@dataclass(frozen=True)
class AnalogInput:
    """Declared analog input and its terminal range."""

    minimum: float
    maximum: float


@dataclass(frozen=True)
class AnalogOutput:
    """Opted-in analog output with an explicit safe value."""

    minimum: float
    maximum: float
    safe_value: float


@dataclass(frozen=True)
class DigitalOutput:
    """Opted-in digital output with an explicit safe value."""

    safe_value: int


@dataclass(frozen=True)
class Interlock:
    """Digital input state required immediately before an output write."""

    line: str
    require: int


@dataclass(frozen=True)
class DeviceConfig:
    """Fully validated configuration for one physical DAQ device."""

    device: str
    model: str
    interlock: Interlock | None
    analog_inputs: dict[str, AnalogInput]
    digital_inputs: frozenset[str]
    analog_outputs: dict[str, AnalogOutput]
    digital_outputs: dict[str, DigitalOutput]
    physical_ao_range: tuple[float, float] | None


_CAPABILITIES = {
    "USB-6210": {
        "ai": range(16),
        "ao": range(0),
        "di": {f"port0/line{i}" for i in range(4)},
        "do": {f"port1/line{i}" for i in range(4)},
        "ao_range": None,
    },
    "USB-6009": {
        "ai": range(8),
        "ao": range(2),
        "di": {
            *(f"port0/line{i}" for i in range(8)),
            *(f"port1/line{i}" for i in range(4)),
        },
        "do": {
            *(f"port0/line{i}" for i in range(8)),
            *(f"port1/line{i}" for i in range(4)),
        },
        "ao_range": (0.0, 5.0),
    },
}


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise NiDaqConfigError(f"{label} must be a mapping")
    return value


def _keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise NiDaqConfigError(f"unknown {label} keys: {sorted(unknown)!r}")


def _range(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)
    ):
        raise NiDaqConfigError(f"{label} range must be [minimum, maximum]")
    low, high = float(value[0]), float(value[1])
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise NiDaqConfigError(f"{label} range must be finite and increasing")
    return low, high


def load_devices_config(value: Any) -> dict[str, DeviceConfig]:
    """Validate a ``devices`` mapping without consulting DAQmx."""
    devices = _mapping(value, "devices")
    result: dict[str, DeviceConfig] = {}
    for device, raw_value in devices.items():
        parse_resource_name(f"DAQ::{device}")
        raw = _mapping(raw_value, f"device {device}")
        _keys(
            raw,
            {
                "model",
                "interlock",
                "analog_inputs",
                "analog_outputs",
                "digital_outputs",
            },
            f"device {device}",
        )
        if "model" not in raw:
            raise NiDaqConfigError(f"device {device} must declare model")
        model = raw["model"]
        if not isinstance(model, str) or model not in _CAPABILITIES:
            raise NiDaqConfigError(f"unsupported model: {model!r}")
        if "interlock" not in raw:
            raise NiDaqConfigError(f"device {device} must explicitly declare interlock")
        caps = _CAPABILITIES[model]
        interlock_raw = raw["interlock"]
        if interlock_raw == "none":
            interlock = None
        else:
            item = _mapping(interlock_raw, f"device {device} interlock")
            _keys(item, {"line", "require"}, "interlock")
            if (
                set(item) != {"line", "require"}
                or item["require"] not in (0, 1)
                or isinstance(item["require"], bool)
            ):
                raise NiDaqConfigError("interlock must be none or {line, require: 0|1}")
            parse_wire_command(f"READ DI {item['line']}")
            if item["line"] not in caps["di"]:
                raise NiDaqConfigError("interlock line is not a physical digital input")
            interlock = Interlock(item["line"], item["require"])
        inputs: dict[str, AnalogInput] = {}
        for channel, item_value in _mapping(
            raw.get("analog_inputs"), "analog_inputs"
        ).items():
            parse_wire_command(f"READ AI {channel}")
            if channel not in {f"ai{i}" for i in caps["ai"]}:
                raise NiDaqConfigError(f"analog input is not physical: {channel!r}")
            item = _mapping(item_value, channel)
            _keys(item, {"range"}, channel)
            if set(item) != {"range"}:
                raise NiDaqConfigError(f"{channel} must declare range")
            inputs[channel] = AnalogInput(*_range(item["range"], channel))
        outputs: dict[str, AnalogOutput] = {}
        for channel, item_value in _mapping(
            raw.get("analog_outputs"), "analog_outputs"
        ).items():
            parse_wire_command(f"WRITE AO {channel} 0")
            if channel not in {f"ao{i}" for i in caps["ao"]}:
                raise NiDaqConfigError(f"analog output is not physical: {channel!r}")
            item = _mapping(item_value, channel)
            _keys(item, {"range", "safe_value"}, channel)
            if set(item) != {"range", "safe_value"}:
                raise NiDaqConfigError(f"{channel} must declare range and safe_value")
            low, high = _range(item["range"], channel)
            physical = caps["ao_range"]
            assert physical is not None
            if low < physical[0] or high > physical[1]:
                raise NiDaqConfigError(f"{channel} range lies outside physical range")
            safe = item["safe_value"]
            if (
                isinstance(safe, bool)
                or not isinstance(safe, (int, float))
                or not math.isfinite(float(safe))
                or not low <= float(safe) <= high
            ):
                raise NiDaqConfigError(
                    f"{channel} safe_value must lie inside its range"
                )
            outputs[channel] = AnalogOutput(low, high, float(safe))
        digital: dict[str, DigitalOutput] = {}
        for line, item_value in _mapping(
            raw.get("digital_outputs"), "digital_outputs"
        ).items():
            parse_wire_command(f"WRITE DO {line} 0")
            if line not in caps["do"]:
                raise NiDaqConfigError(f"digital output is not physical: {line!r}")
            item = _mapping(item_value, line)
            _keys(item, {"safe_value"}, line)
            if (
                set(item) != {"safe_value"}
                or item["safe_value"] not in (0, 1)
                or isinstance(item["safe_value"], bool)
            ):
                raise NiDaqConfigError(f"{line} must declare safe_value 0 or 1")
            digital[line] = DigitalOutput(item["safe_value"])
        if interlock is not None and interlock.line in digital:
            raise NiDaqConfigError("interlock line may not also be a digital output")
        result[device] = DeviceConfig(
            device,
            model,
            interlock,
            inputs,
            frozenset(caps["di"]),
            outputs,
            digital,
            caps["ao_range"],
        )
    return result


__all__ = [
    "AnalogInput",
    "AnalogOutput",
    "DeviceConfig",
    "DigitalOutput",
    "Interlock",
    "NiDaqConfigError",
    "load_devices_config",
]
