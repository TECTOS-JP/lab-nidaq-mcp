"""lab-executor backend entry-point factory."""

from __future__ import annotations

from typing import Any

from lab_executor.backends import BackendRegistration

from lab_nidaq_mcp.backend import NiDaqBackend


def make_backend(config: dict[str, Any] | None = None) -> BackendRegistration:
    """Construct the NI-DAQ backend from strict configuration."""
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise TypeError("nidaq backend config must be a mapping")
    unknown = set(config) - {"devices"}
    if unknown:
        raise ValueError(f"unknown nidaq backend config keys: {sorted(unknown)!r}")
    devices = config.get("devices", {})
    if not isinstance(devices, dict):
        raise TypeError("nidaq backend devices must be a mapping")
    return BackendRegistration(
        backend=NiDaqBackend(devices=devices), prefixes=("DAQ::",)
    )


__all__ = ["make_backend"]
