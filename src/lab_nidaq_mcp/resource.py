"""Strict resource-name parser for NI-DAQmx device resources."""

from __future__ import annotations

from dataclasses import dataclass
import re


_RESOURCE_RE = re.compile(r"DAQ::(?P<device>[A-Za-z0-9_][A-Za-z0-9 _-]{0,254})\Z")


class NiDaqResourceError(ValueError):
    """The resource name does not belong to the NI-DAQ protocol."""


@dataclass(frozen=True)
class NiDaqResource:
    """Parsed canonical ``DAQ::<DeviceName>`` resource."""

    device: str


def parse_resource_name(resource_name: str) -> NiDaqResource:
    """Parse one exact device-level DAQ resource without normalization."""
    if not isinstance(resource_name, str):
        raise NiDaqResourceError("DAQ resource name must be a string")
    match = _RESOURCE_RE.fullmatch(resource_name)
    if match is None:
        raise NiDaqResourceError("DAQ resource must match DAQ::<DeviceName>")
    device = match.group("device")
    if device.endswith(" ") or "  " in device:
        raise NiDaqResourceError("DAQ device name is not canonical")
    return NiDaqResource(device=device)


__all__ = ["NiDaqResource", "NiDaqResourceError", "parse_resource_name"]
