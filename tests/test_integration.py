from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from lab_executor.backends import (
    BackendRegistration,
    CompositeBackend,
    ResourceRoutingError,
)

from lab_nidaq_mcp.cli import main
from lab_nidaq_mcp.mock_backend import DEFAULT_MOCK_RESOURCE, MockNiDaqBackend


ROOT = Path(__file__).parents[1]


class OtherBackend:
    backend_id = "other"

    async def list_resources(self):
        return ["OTHER::1"]

    async def query(self, resource_name, command, **kwargs):
        return f"{resource_name}:{command}"

    async def write(self, resource_name, command, **kwargs):
        return None

    def close(self):
        pass


@pytest.mark.asyncio
async def test_composite_routes_daq_and_fail_closes_unmatched_resource():
    composite = CompositeBackend(
        [
            BackendRegistration(MockNiDaqBackend(), ("DAQ::",)),
            BackendRegistration(OtherBackend(), ("OTHER::",)),
        ]
    )
    assert await composite.query(DEFAULT_MOCK_RESOURCE, "READ AI ai0") == "1.25"
    assert await composite.query("OTHER::1", "PING") == "OTHER::1:PING"
    with pytest.raises(ResourceRoutingError):
        await composite.query("UNKNOWN::1", "PING")


def test_cli_dry_run(capsys, tmp_path):
    # A pytest tmp dir, not the repo root: a read-only checkout must still run
    # these tests, and parallel runs must not collide on a shared file name.
    config = tmp_path / "nidaq_config.yaml"
    config.write_text(
        "devices:\n  Dev2:\n    model: USB-6009\n    interlock: none\n",
        "utf-8",
        newline="\n",
    )
    assert main(["--config", str(config), "--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backend_id"] == "nidaq"
    assert payload["resources"] == ["DAQ::Dev2"]
    assert {"execute_named_command", "start_recipe_job"} <= set(payload["tools"])


def test_cli_imports_only_two_public_lab_executor_modules():
    tree = ast.parse((ROOT / "src" / "lab_nidaq_mcp" / "cli.py").read_text("utf-8"))
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("lab_executor")
    }
    assert modules == {"lab_executor.control_plane", "lab_executor.server"}


def test_backend_imports_nidaqmx_only_inside_hooks():
    tree = ast.parse((ROOT / "src" / "lab_nidaq_mcp" / "backend.py").read_text("utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.col_offset) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", node.col_offset))
    assert [offset for name, offset in imports if name.split(".")[0] == "nidaqmx"]
    assert all(
        offset > 0 for name, offset in imports if name.split(".")[0] == "nidaqmx"
    )
