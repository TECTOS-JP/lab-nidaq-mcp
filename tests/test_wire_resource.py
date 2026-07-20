from __future__ import annotations

import pytest

from lab_nidaq_mcp.resource import NiDaqResourceError, parse_resource_name
from lab_nidaq_mcp.wire import NiDaqWireError, parse_wire_command


def test_valid_resource_is_device_level_and_case_sensitive():
    assert parse_resource_name("DAQ::Dev2").device == "Dev2"


@pytest.mark.parametrize(
    "resource",
    [
        "",
        "DAQ::",
        "DAQ::Dev2/ai0",
        "daq::Dev2",
        " DAQ::Dev2",
        "DAQ::Dev2 ",
        "DAQ::Dev2\n",
        "DAQ:::Dev2",
        "GPIB::1",
        "DAQ::Dev@2",
        "DAQ::Dev  2",
    ],
)
def test_malformed_resources_are_rejected(resource):
    with pytest.raises(NiDaqResourceError):
        parse_resource_name(resource)


def test_non_string_resource_is_rejected():
    with pytest.raises(NiDaqResourceError):
        parse_resource_name(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "command",
    ["READ AI ai0", "READ DI port0/line7", "INFO model", "ACQUIRE ai0 10 250000"],
)
def test_query_commands_parse_as_reads(command):
    assert parse_wire_command(command).is_read


@pytest.mark.parametrize(
    "command",
    [
        "WRITE AO ao0 2.5",
        "WRITE AO ao1 -1e-3",
        "WRITE DO port1/line0 0",
        "WRITE DO port1/line0 1",
        "SAFE",
    ],
)
def test_write_commands_parse_as_writes(command):
    assert not parse_wire_command(command).is_read


@pytest.mark.parametrize(
    "command",
    [
        "",
        "READ",
        "READ AI",
        "READ AI ao0",
        "READ DI port/line0",
        "INFO Model",
        "WRITE AO ai0 1",
        "WRITE AO ao0 nan",
        "WRITE AO ao0 inf",
        "WRITE DO port0/line0 true",
        "WRITE DO port0/line0 2",
        "safe",
        "SAFE extra",
        " READ AI ai0",
        "READ  AI ai0",
        "READ AI ai0 ",
        "READ AI ai0\n",
        "*IDN?",
        "CONF",
        "ACQUIRE",
        "ACQUIRE ai0",
        "ACQUIRE ai0 1",
        "ACQUIRE ai0 0 1",
        "ACQUIRE ai0 -1 1",
        "ACQUIRE ai0 1.0 1",
        "ACQUIRE ai0 1 0",
        "ACQUIRE ai0 1 -1",
        "ACQUIRE ai0 1 nan",
        "ACQUIRE ai0 1 inf",
        "ACQUIRE ao0 1 1",
        "ACQUIRE ai0 1 1 extra",
        "ACQUIRE  ai0 1 1",
        "ACQUIRE ai0  1 1",
        "ACQUIRE ai0 1  1",
        " ACQUIRE ai0 1 1",
        "ACQUIRE ai0 1 1 ",
    ],
)
def test_malformed_commands_are_rejected(command):
    with pytest.raises(NiDaqWireError):
        parse_wire_command(command)


def test_non_string_command_is_rejected():
    with pytest.raises(NiDaqWireError):
        parse_wire_command(None)  # type: ignore[arg-type]
