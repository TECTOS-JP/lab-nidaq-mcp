from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
import yaml
from lab_executor.models.instrument_def import InstrumentDefinition

from lab_nidaq_mcp.wire import parse_wire_command


ROOT = Path(__file__).parents[1]
DEFINITIONS = ROOT / "src" / "lab_nidaq_mcp" / "builtin_instruments"
NAMES = ["usb_6009", "usb_6210"]
SUPPORT_LEVELS = {"verified", "tested", "experimental", "draft"}


def raw(name):
    return yaml.safe_load((DEFINITIONS / f"{name}.yaml").read_text("utf-8"))


def definition(name):
    return InstrumentDefinition(**raw(name))


@pytest.mark.parametrize("name", NAMES)
def test_definitions_validate_against_ecosystem_schema(name):
    item = definition(name)
    assert item.metadata.support_level in SUPPORT_LEVELS
    assert item.metadata.support_level == "experimental"
    assert item.commands


def _render(command):
    rendered = command.scpi
    for parameter in command.parameters:
        value = parameter.range[0] if parameter.range else "x"
        if parameter.type == "integer":
            value = int(value)
        rendered = rendered.replace("{" + parameter.name + "}", str(value))
    return rendered


@pytest.mark.parametrize("name", NAMES)
def test_every_command_string_binds_to_wire_grammar(name):
    for command in definition(name).commands.values():
        parsed = parse_wire_command(_render(command))
        assert parsed.is_read == (command.type == "query")


@pytest.mark.parametrize("name", NAMES)
def test_output_definitions_have_nonempty_safe_shutdown(name):
    item = definition(name)
    outputs = [
        command
        for command in item.commands.values()
        if command.type == "write" and command.scpi != "SAFE"
    ]
    assert outputs
    assert item.safe_shutdown
    assert all(step.command in item.commands for step in item.safe_shutdown)


def test_usb_6210_declares_no_analog_output_command():
    assert all(
        "WRITE AO" not in command.scpi
        for command in definition("usb_6210").commands.values()
    )


def test_usb_6009_ao_commands_are_bounded_zero_to_five_volts():
    commands = [
        command
        for command in definition("usb_6009").commands.values()
        if "WRITE AO" in command.scpi
    ]
    assert commands
    assert all(command.parameters[0].range == [0.0, 5.0] for command in commands)


@pytest.mark.parametrize("name", NAMES)
def test_definitions_document_d9_and_are_packaged(name):
    text = (
        files("lab_nidaq_mcp.builtin_instruments")
        .joinpath(f"{name}.yaml")
        .read_text("utf-8")
    )
    assert "high-impedance" in text
    assert "installer" in text
