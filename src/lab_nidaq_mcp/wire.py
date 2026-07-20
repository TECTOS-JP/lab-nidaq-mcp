"""Fail-closed parser for the single-point NI-DAQ command language."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Literal


_CHANNEL_RE = re.compile(r"(?:ai|ao)[0-9]+\Z")
_LINE_RE = re.compile(r"port[0-9]+/line[0-9]+\Z")
_FIELD_RE = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_NUMBER_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class NiDaqWireError(ValueError):
    """A command is malformed or uses an unsupported operation."""


@dataclass(frozen=True)
class WireCommand:
    """One validated NI-DAQ single-point operation."""

    opcode: Literal[
        "READ_AI", "READ_DI", "ACQUIRE", "INFO", "WRITE_AO", "WRITE_DO", "SAFE"
    ]
    target: str | None = None
    value: float | int | None = None
    rate_hz: float | None = None

    @property
    def is_read(self) -> bool:
        """Whether the command belongs to the query half of the grammar."""
        return self.opcode in {"READ_AI", "READ_DI", "ACQUIRE", "INFO"}


def _tokens(command: str) -> list[str]:
    if not isinstance(command, str):
        raise NiDaqWireError("DAQ command must be a string")
    if not command or command != command.strip() or any(c in command for c in "\r\n\t"):
        raise NiDaqWireError("DAQ command must be one line without outer whitespace")
    parts = command.split(" ")
    if "" in parts:
        raise NiDaqWireError("DAQ command tokens must use single spaces")
    return parts


def parse_wire_command(command: str) -> WireCommand:
    """Parse one exact command without case folding or permissive fallback."""
    parts = _tokens(command)
    if parts == ["SAFE"]:
        return WireCommand("SAFE")
    if len(parts) == 2 and parts[0] == "INFO" and _FIELD_RE.fullmatch(parts[1]):
        return WireCommand("INFO", parts[1])
    if (
        len(parts) == 3
        and parts[:2] == ["READ", "AI"]
        and _CHANNEL_RE.fullmatch(parts[2])
        and parts[2].startswith("ai")
    ):
        return WireCommand("READ_AI", parts[2])
    if len(parts) == 3 and parts[:2] == ["READ", "DI"] and _LINE_RE.fullmatch(parts[2]):
        return WireCommand("READ_DI", parts[2])
    if (
        len(parts) == 4
        and parts[0] == "ACQUIRE"
        and _CHANNEL_RE.fullmatch(parts[1])
        and parts[1].startswith("ai")
    ):
        if re.fullmatch(r"[0-9]+", parts[2]) is None:
            raise NiDaqWireError("sample count must be a positive integer")
        samples = int(parts[2])
        if samples <= 0:
            raise NiDaqWireError("sample count must be positive")
        if _NUMBER_RE.fullmatch(parts[3]) is None:
            raise NiDaqWireError("sample rate must be a finite positive number")
        rate_hz = float(parts[3])
        if not math.isfinite(rate_hz) or rate_hz <= 0:
            raise NiDaqWireError("sample rate must be finite and positive")
        return WireCommand("ACQUIRE", parts[1], samples, rate_hz)
    if (
        len(parts) == 4
        and parts[:2] == ["WRITE", "AO"]
        and _CHANNEL_RE.fullmatch(parts[2])
        and parts[2].startswith("ao")
    ):
        if _NUMBER_RE.fullmatch(parts[3]) is None:
            raise NiDaqWireError("AO voltage must be a finite decimal number")
        value = float(parts[3])
        if not math.isfinite(value):
            raise NiDaqWireError("AO voltage must be finite")
        return WireCommand("WRITE_AO", parts[2], value)
    if (
        len(parts) == 4
        and parts[:2] == ["WRITE", "DO"]
        and _LINE_RE.fullmatch(parts[2])
        and parts[3] in {"0", "1"}
    ):
        return WireCommand("WRITE_DO", parts[2], int(parts[3]))
    raise NiDaqWireError("unknown or malformed DAQ command")


__all__ = ["NiDaqWireError", "WireCommand", "parse_wire_command"]
