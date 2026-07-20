from __future__ import annotations

from importlib import metadata
from pathlib import Path

import pytest
from lab_executor.backends import BackendRegistration

from lab_nidaq_mcp.backend import NiDaqBackend
from lab_nidaq_mcp.discovery import make_backend

try:
    import tomllib
except ImportError:
    import tomli as tomllib


ROOT = Path(__file__).parents[1]


def test_factory_returns_strict_registration():
    registration = make_backend(
        {"devices": {"Dev2": {"model": "USB-6009", "interlock": "none"}}}
    )
    assert isinstance(registration, BackendRegistration)
    assert isinstance(registration.backend, NiDaqBackend)
    assert registration.prefixes == ("DAQ::",)


def test_factory_rejects_unknown_or_malformed_config():
    with pytest.raises(ValueError, match="unknown"):
        make_backend({"reset": True})
    with pytest.raises(TypeError):
        make_backend({"devices": []})
    with pytest.raises(TypeError):
        make_backend([])  # type: ignore[arg-type]


def test_entry_point_when_installed():
    matches = [
        ep
        for ep in metadata.entry_points(group="lab_executor.backends")
        if ep.name == "nidaq"
    ]
    if not matches:
        pytest.skip(
            "lab-nidaq-mcp installation metadata is required for entry-point tests"
        )
    assert len(matches) == 1
    assert matches[0].load() is make_backend


def test_pyproject_metadata_and_strict_sdist_allowlist():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    project = data["project"]
    assert project["name"] == "lab-nidaq-mcp"
    assert any(dep.startswith("nidaqmx") for dep in project["dependencies"])
    assert any(dep.startswith("PyYAML") for dep in project["dependencies"])
    assert (
        project["entry-points"]["lab_executor.backends"]["nidaq"]
        == "lab_nidaq_mcp.discovery:make_backend"
    )
    assert project["scripts"]["lab-nidaq"] == "lab_nidaq_mcp.cli:main"
    include = data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert include and all(path.startswith("/") for path in include)
    assert {"/src/lab_nidaq_mcp", "/tests", "/docs", "/.gitignore"} <= set(include)
