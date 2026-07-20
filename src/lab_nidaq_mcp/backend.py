"""Safety-gated NI-DAQmx backend with hardware isolated behind hooks.

``nidaqmx`` is imported lazily inside the hooks. Parsing, configuration,
interlock, and range checks all complete before a hook can create a task.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from lab_nidaq_mcp.config import DeviceConfig, load_devices_config
from lab_nidaq_mcp.resource import NiDaqResource, parse_resource_name
from lab_nidaq_mcp.wire import WireCommand, parse_wire_command


LOGGER = logging.getLogger(__name__)


class NiDaqBackendError(RuntimeError):
    """Base error for backend-level failures."""


class NiDaqReadRejected(NiDaqBackendError):
    """A write command was passed to the query interface."""


class NiDaqWriteRejected(NiDaqBackendError):
    """An output command failed a safety gate."""


class NiDaqTransportError(NiDaqBackendError):
    """DAQmx failed while performing a permitted single-point operation."""


def _format_value(value: float) -> str:
    return f"{value:.10g}"


class NiDaqBackend:
    """Software-timed single-point backend for explicitly configured devices."""

    backend_id = "nidaq"

    def __init__(self, devices: dict[str, Any] | None = None) -> None:
        self._devices = load_devices_config({} if devices is None else devices)
        self._resources = tuple(f"DAQ::{name}" for name in self._devices)
        self._verified_devices: set[str] = set()
        self._closed = False

    async def list_resources(self) -> list[str]:
        """Return configured resources without enumerating hardware."""
        return list(self._resources)

    def _validate(
        self, resource_name: str, command: str
    ) -> tuple[NiDaqResource, DeviceConfig, WireCommand]:
        if self._closed:
            raise NiDaqBackendError("backend is closed")
        resource = parse_resource_name(resource_name)
        config = self._devices.get(resource.device)
        if config is None:
            raise NiDaqBackendError(f"resource is not configured: {resource_name!r}")
        return resource, config, parse_wire_command(command)

    async def query(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> str:
        del timeout_ms, read_termination, write_termination
        resource, config, parsed = self._validate(resource_name, command)
        if not parsed.is_read:
            raise NiDaqReadRejected("query accepts only READ and INFO commands")
        if parsed.opcode == "INFO":
            return self._info(config, parsed.target)
        assert parsed.target is not None
        if parsed.opcode == "ACQUIRE":
            channel = config.analog_inputs.get(parsed.target)
            if channel is None:
                raise NiDaqBackendError(
                    f"analog input is not configured: {parsed.target!r}"
                )
            assert isinstance(parsed.value, int) and parsed.rate_hz is not None
            assert config.artifact_dir is not None and config.max_samples is not None
            if parsed.value > config.max_samples:
                raise NiDaqBackendError("sample count exceeds configured max_samples")
            if parsed.rate_hz > config.maximum_ai_rate:
                raise NiDaqBackendError(
                    "sample rate exceeds the device maximum AI rate"
                )
            try:
                self._ensure_model(resource.device, config)
                return self._acquire_analog(
                    resource.device,
                    config.model,
                    parsed.target,
                    channel.minimum,
                    channel.maximum,
                    parsed.value,
                    parsed.rate_hz,
                    config.artifact_dir,
                )
            except Exception as exc:
                if isinstance(exc, NiDaqBackendError):
                    raise
                raise NiDaqTransportError(f"analog acquisition failed: {exc}") from exc
        if parsed.opcode == "READ_AI":
            channel = config.analog_inputs.get(parsed.target)
            if channel is None:
                raise NiDaqBackendError(
                    f"analog input is not configured: {parsed.target!r}"
                )
            try:
                self._ensure_model(resource.device, config)
                value = self._read_analog(
                    resource.device, parsed.target, channel.minimum, channel.maximum
                )
            except Exception as exc:
                if isinstance(exc, NiDaqBackendError):
                    raise
                raise NiDaqTransportError(f"analog input read failed: {exc}") from exc
            return _format_value(float(value))
        if parsed.target not in config.digital_inputs:
            raise NiDaqBackendError(f"digital input is not physical: {parsed.target!r}")
        try:
            self._ensure_model(resource.device, config)
            return "1" if self._read_digital(resource.device, parsed.target) else "0"
        except Exception as exc:
            if isinstance(exc, NiDaqBackendError):
                raise
            raise NiDaqTransportError(f"digital input read failed: {exc}") from exc

    async def write(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> None:
        del timeout_ms, read_termination, write_termination
        resource, config, parsed = self._validate(resource_name, command)
        if parsed.is_read:
            raise NiDaqWriteRejected("write accepts only WRITE and SAFE commands")
        if parsed.opcode == "SAFE":
            self._drive_safe(resource.device, config, raise_errors=True)
            return
        assert parsed.target is not None and parsed.value is not None
        if parsed.opcode == "WRITE_AO":
            output = config.analog_outputs.get(parsed.target)
            if output is None:
                raise NiDaqWriteRejected(
                    f"analog output is not declared: {parsed.target!r}"
                )
            value = float(parsed.value)
            physical = config.physical_ao_range
            assert physical is not None
            if (
                not output.minimum <= value <= output.maximum
                or not physical[0] <= value <= physical[1]
            ):
                raise NiDaqWriteRejected(
                    "analog output value is outside declared or physical range"
                )
            self._require_interlock(resource.device, config)
            self._call_analog_write(resource.device, config, parsed.target, value)
            return
        output = config.digital_outputs.get(parsed.target)
        if output is None:
            raise NiDaqWriteRejected(
                f"digital output is not declared: {parsed.target!r}"
            )
        self._require_interlock(resource.device, config)
        self._call_digital_write(
            resource.device, config, parsed.target, int(parsed.value)
        )

    @staticmethod
    def _info(config: DeviceConfig, field: str | None) -> str:
        values = {
            "device": config.device,
            "model": config.model,
            "manufacturer": "National Instruments",
        }
        try:
            return values[field]  # type: ignore[index]
        except KeyError as exc:
            raise NiDaqBackendError(f"INFO field is not available: {field!r}") from exc

    def _require_interlock(self, device: str, config: DeviceConfig) -> None:
        if config.interlock is None:
            return
        try:
            self._ensure_model(device, config)
            actual = int(bool(self._read_digital(device, config.interlock.line)))
        except Exception as exc:
            raise NiDaqWriteRejected(
                f"interlock read failed; output refused: {exc}"
            ) from exc
        if actual != config.interlock.require:
            raise NiDaqWriteRejected("interlock state does not permit output")

    def _call_analog_write(
        self, device: str, config: DeviceConfig, channel: str, value: float
    ) -> None:
        try:
            self._ensure_model(device, config)
            physical = config.physical_ao_range
            assert physical is not None
            self._write_analog(device, channel, value, physical[0], physical[1])
        except Exception as exc:
            raise NiDaqTransportError(f"analog output write failed: {exc}") from exc

    def _call_digital_write(
        self, device: str, config: DeviceConfig, line: str, value: int
    ) -> None:
        try:
            self._ensure_model(device, config)
            self._write_digital(device, line, value)
        except Exception as exc:
            raise NiDaqTransportError(f"digital output write failed: {exc}") from exc

    def _drive_safe(
        self, device: str, config: DeviceConfig, *, raise_errors: bool
    ) -> None:
        failures: list[Exception] = []
        for channel, output in config.analog_outputs.items():
            try:
                self._call_analog_write(device, config, channel, output.safe_value)
            except Exception as exc:
                failures.append(exc)
                LOGGER.error("failed to drive %s/%s safe: %s", device, channel, exc)
        for line, output in config.digital_outputs.items():
            try:
                self._call_digital_write(device, config, line, output.safe_value)
            except Exception as exc:
                failures.append(exc)
                LOGGER.error("failed to drive %s/%s safe: %s", device, line, exc)
        if failures and raise_errors:
            raise NiDaqWriteRejected(f"SAFE failed for {len(failures)} output(s)")

    def _ensure_model(self, device: str, config: DeviceConfig) -> None:
        if device in self._verified_devices:
            return
        try:
            actual = self._get_product_type(device)
        except Exception as exc:
            if isinstance(exc, NiDaqBackendError):
                raise
            raise NiDaqTransportError(f"product type read failed: {exc}") from exc
        if actual != config.model:
            raise NiDaqBackendError(
                f"product type mismatch for {device}: declared {config.model!r}, actual {actual!r}"
            )
        self._verified_devices.add(device)

    # --- hardware hooks -------------------------------------------------
    # These are the only methods that import nidaqmx or create DAQmx tasks.

    def _read_analog(
        self, device: str, channel: str, minimum: float, maximum: float
    ) -> float:
        import nidaqmx

        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan(
                f"{device}/{channel}", min_val=minimum, max_val=maximum
            )
            return float(task.read())

    def _read_digital(self, device: str, line: str) -> bool:
        import nidaqmx

        with nidaqmx.Task() as task:
            task.di_channels.add_di_chan(f"{device}/{line}")
            return bool(task.read())

    def _acquire_analog(
        self,
        device: str,
        model: str,
        channel: str,
        minimum: float,
        maximum: float,
        samples: int,
        rate_hz: float,
        artifact_dir: Path,
    ) -> str:
        import nidaqmx
        from nidaqmx.constants import AcquisitionType

        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan(
                f"{device}/{channel}", min_val=minimum, max_val=maximum
            )
            task.timing.cfg_samp_clk_timing(
                rate_hz, sample_mode=AcquisitionType.FINITE, samps_per_chan=samples
            )
            acquired = task.read(number_of_samples_per_channel=samples)
        return self._write_acquisition_artifact(
            acquired,
            device,
            model,
            channel,
            minimum,
            maximum,
            samples,
            rate_hz,
            artifact_dir,
        )

    @staticmethod
    def _write_acquisition_artifact(
        acquired: Any,
        device: str,
        model: str,
        channel: str,
        minimum: float,
        maximum: float,
        samples: int,
        rate_hz: float,
        artifact_dir: Path,
    ) -> str:
        import numpy as np

        acquired_at = datetime.now(timezone.utc)
        array = np.asarray(acquired, dtype=float).reshape(samples, 1)
        meta = {
            "device": device,
            "model": model,
            "channel": channel,
            "samples": samples,
            "rate_hz": rate_hz,
            "unit": "V",
            "acquired_at": acquired_at.isoformat(),
            "range": [minimum, maximum],
        }
        name = f"acq-{acquired_at.strftime('%Y%m%dT%H%M%S.%fZ')}-{device}-{channel}.npz"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / name
        np.savez_compressed(path, samples=array, meta=np.asarray(json.dumps(meta)))
        contents = path.read_bytes()
        return json.dumps(
            {
                "artifact": "v1",
                "name": name,
                "sha256": hashlib.sha256(contents).hexdigest(),
                "bytes": len(contents),
                "shape": list(array.shape),
                "rate_hz": rate_hz,
                "unit": "V",
            },
            separators=(",", ":"),
        )

    def _write_analog(
        self,
        device: str,
        channel: str,
        value: float,
        minimum: float,
        maximum: float,
    ) -> None:
        import nidaqmx

        with nidaqmx.Task() as task:
            task.ao_channels.add_ao_voltage_chan(
                f"{device}/{channel}", min_val=minimum, max_val=maximum
            )
            task.write(value, auto_start=True)

    def _write_digital(self, device: str, line: str, value: int) -> None:
        import nidaqmx

        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(f"{device}/{line}")
            task.write(bool(value), auto_start=True)

    def _get_product_type(self, device: str) -> str:
        import nidaqmx

        return str(nidaqmx.system.System.local().devices[device].product_type)

    def close(self) -> None:
        """Drive every declared output safe, then close, idempotently and silently."""
        if self._closed:
            return
        try:
            for config in self._devices.values():
                self._drive_safe(config.device, config, raise_errors=False)
        except Exception:
            LOGGER.exception("unexpected failure during safe close")
        finally:
            self._closed = True


__all__ = [
    "NiDaqBackend",
    "NiDaqBackendError",
    "NiDaqReadRejected",
    "NiDaqTransportError",
    "NiDaqWriteRejected",
]
