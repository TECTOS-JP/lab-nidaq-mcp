"""Deterministic NI-DAQ backend with exact BEF conformance probes."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from lab_nidaq_mcp.backend import NiDaqBackend, NiDaqBackendError
from lab_nidaq_mcp.resource import parse_resource_name


DEFAULT_MOCK_RESOURCE = "DAQ::Dev2"
CONFORMANCE_QUERY = "*IDN?"
CONFORMANCE_WRITE = "CONF"
DEFAULT_MOCK_DEVICES = {
    "Dev2": {
        "model": "USB-6009",
        "interlock": "none",
        "analog_inputs": {"ai0": {"range": [-10, 10]}},
        "artifact_dir": ".",
        "max_samples": 100000,
    }
}


class MockNiDaqBackend(NiDaqBackend):
    """In-memory backend for tests; it never imports or constructs DAQmx."""

    backend_id = "mock-nidaq"

    def __init__(
        self,
        devices: dict[str, Any] | None = None,
        *,
        analog_values: dict[tuple[str, str], float] | None = None,
        digital_values: dict[tuple[str, str], int] | None = None,
        allow_conformance_probes: bool = True,
        product_types: dict[str, str] | None = None,
    ) -> None:
        super().__init__(DEFAULT_MOCK_DEVICES if devices is None else devices)
        self.analog_values = dict(analog_values or {("Dev2", "ai0"): 1.25})
        self.digital_values = dict(digital_values or {})
        self.output_writes: list[tuple[str, str, str, float | int]] = []
        self.task_constructions = 0
        self.product_types = dict(
            {"Dev2": "USB-6009"} if product_types is None else product_types
        )
        self.product_type_reads = 0
        self._allow_conformance_probes = allow_conformance_probes
        self.interlock_error: Exception | None = None

    def _require_configured(self, resource_name: str) -> None:
        if self._closed:
            raise NiDaqBackendError("backend is closed")
        parsed = parse_resource_name(resource_name)
        if parsed.device not in self._devices:
            raise NiDaqBackendError(f"resource is not configured: {resource_name!r}")

    async def query(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> str:
        if self._allow_conformance_probes and command == CONFORMANCE_QUERY:
            self._require_configured(resource_name)
            return "TECTOS,MockNiDaqBackend,0,0.1.0"
        return await super().query(
            resource_name, command, timeout_ms, read_termination, write_termination
        )

    async def write(
        self,
        resource_name: str,
        command: str,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ) -> None:
        if self._allow_conformance_probes and command == CONFORMANCE_WRITE:
            self._require_configured(resource_name)
            return None
        return await super().write(
            resource_name, command, timeout_ms, read_termination, write_termination
        )

    def _read_analog(
        self, device: str, channel: str, minimum: float, maximum: float
    ) -> float:
        del minimum, maximum
        try:
            return self.analog_values[(device, channel)]
        except KeyError as exc:
            raise NiDaqBackendError(
                f"no mock analog value for {device}/{channel}"
            ) from exc

    def _read_digital(self, device: str, line: str) -> bool:
        if self.interlock_error is not None:
            raise self.interlock_error
        return bool(self.digital_values.get((device, line), 0))

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
        waveform = [float(index) / rate_hz for index in range(samples)]
        return self._write_acquisition_artifact(
            waveform,
            device,
            model,
            channel,
            minimum,
            maximum,
            samples,
            rate_hz,
            artifact_dir,
        )

    def _write_analog(
        self,
        device: str,
        channel: str,
        value: float,
        minimum: float,
        maximum: float,
    ) -> None:
        del minimum, maximum
        self.output_writes.append(("AO", device, channel, value))

    def _write_digital(self, device: str, line: str, value: int) -> None:
        self.output_writes.append(("DO", device, line, value))

    def _get_product_type(self, device: str) -> str:
        self.product_type_reads += 1
        return self.product_types[device]


__all__ = [
    "CONFORMANCE_QUERY",
    "CONFORMANCE_WRITE",
    "DEFAULT_MOCK_DEVICES",
    "DEFAULT_MOCK_RESOURCE",
    "MockNiDaqBackend",
]
