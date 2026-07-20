from __future__ import annotations

import hashlib
import inspect
import json

import pytest
from lab_executor.backends import InstrumentBackend
from lab_executor.testing.backend_conformance import assert_backend_contract

from lab_nidaq_mcp.backend import (
    NiDaqBackendError,
    NiDaqReadRejected,
    NiDaqWriteRejected,
)
from lab_nidaq_mcp.mock_backend import DEFAULT_MOCK_RESOURCE, MockNiDaqBackend


OUTPUT_CONFIG = {
    "Dev2": {
        "model": "USB-6009",
        "interlock": {"line": "port0/line7", "require": 1},
        "analog_inputs": {"ai0": {"range": [-10, 10]}},
        "artifact_dir": ".",
        "max_samples": 1000,
        "analog_outputs": {"ao0": {"range": [1, 4], "safe_value": 1.5}},
        "digital_outputs": {"port1/line0": {"safe_value": 0}},
    }
}


def test_backends_satisfy_runtime_protocol():
    assert isinstance(MockNiDaqBackend(), InstrumentBackend)


@pytest.mark.asyncio
async def test_mock_passes_bef_conformance():
    backend = MockNiDaqBackend()
    assert (
        await assert_backend_contract(backend, sample_resource=DEFAULT_MOCK_RESOURCE)
        is backend
    )


@pytest.mark.asyncio
async def test_reads_and_info_are_deterministic():
    backend = MockNiDaqBackend()
    assert await backend.query(DEFAULT_MOCK_RESOURCE, "READ AI ai0") == "1.25"
    assert await backend.query(DEFAULT_MOCK_RESOURCE, "READ DI port0/line0") == "0"
    assert await backend.query(DEFAULT_MOCK_RESOURCE, "INFO model") == "USB-6009"


@pytest.mark.asyncio
async def test_query_and_write_reject_wrong_command_kind():
    backend = MockNiDaqBackend()
    with pytest.raises(NiDaqReadRejected):
        await backend.query(DEFAULT_MOCK_RESOURCE, "SAFE")
    with pytest.raises(NiDaqWriteRejected):
        await backend.write(DEFAULT_MOCK_RESOURCE, "READ AI ai0")
    with pytest.raises(NiDaqWriteRejected):
        await backend.write(DEFAULT_MOCK_RESOURCE, "ACQUIRE ai0 10 1000")
    with pytest.raises(NiDaqReadRejected):
        await backend.query(DEFAULT_MOCK_RESOURCE, "WRITE DO port1/line0 0")


@pytest.mark.asyncio
async def test_mock_acquisition_writes_valid_artifact(tmp_path):
    import numpy as np
    from lab_executor.artifact import parse_artifact_reference

    devices = {
        "Dev2": {
            "model": "USB-6009",
            "interlock": "none",
            "analog_inputs": {"ai0": {"range": [-10, 10]}},
            "artifact_dir": str(tmp_path),
            "max_samples": 100,
        }
    }
    backend = MockNiDaqBackend(devices)
    result = await backend.query(DEFAULT_MOCK_RESOURCE, "ACQUIRE ai0 10 1000")
    reference = parse_artifact_reference(result)
    assert reference is not None
    path = tmp_path / reference.name
    contents = path.read_bytes()
    assert reference.sha256 == hashlib.sha256(contents).hexdigest()
    assert reference.bytes == len(contents)
    assert reference.shape == [10, 1]
    with np.load(path) as artifact:
        assert artifact["samples"].shape == (10, 1)
        meta = json.loads(artifact["meta"].item())
    assert meta["device"] == "Dev2"
    assert meta["model"] == "USB-6009"
    assert meta["channel"] == "ai0"
    assert meta["samples"] == 10
    assert meta["rate_hz"] == 1000.0
    assert meta["unit"] == "V"
    assert meta["range"] == [-10.0, 10.0]
    assert backend.task_constructions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "match"),
    [
        ("ACQUIRE ai1 10 1000", "not configured"),
        ("ACQUIRE ai0 101 1000", "max_samples"),
        ("ACQUIRE ai0 10 48001", "maximum AI rate"),
    ],
)
async def test_acquisition_limits_fail_before_task_creation(tmp_path, command, match):
    devices = {
        "Dev2": {
            "model": "USB-6009",
            "interlock": "none",
            "analog_inputs": {"ai0": {"range": [-10, 10]}},
            "artifact_dir": str(tmp_path),
            "max_samples": 100,
        }
    }
    backend = MockNiDaqBackend(devices)
    with pytest.raises(NiDaqBackendError, match=match):
        await backend.query(DEFAULT_MOCK_RESOURCE, command)
    assert backend.task_constructions == 0


@pytest.mark.asyncio
async def test_interlock_mismatch_and_read_failure_refuse_output():
    backend = MockNiDaqBackend(OUTPUT_CONFIG)
    with pytest.raises(NiDaqWriteRejected, match="interlock"):
        await backend.write(DEFAULT_MOCK_RESOURCE, "WRITE AO ao0 2")
    backend.interlock_error = OSError("broken wire")
    with pytest.raises(NiDaqWriteRejected, match="read failed"):
        await backend.write(DEFAULT_MOCK_RESOURCE, "WRITE DO port1/line0 1")
    assert backend.output_writes == []


@pytest.mark.asyncio
async def test_outputs_write_once_when_interlock_matches():
    backend = MockNiDaqBackend(
        OUTPUT_CONFIG, digital_values={("Dev2", "port0/line7"): 1}
    )
    await backend.write(DEFAULT_MOCK_RESOURCE, "WRITE AO ao0 2")
    await backend.write(DEFAULT_MOCK_RESOURCE, "WRITE DO port1/line0 1")
    assert backend.output_writes == [
        ("AO", "Dev2", "ao0", 2.0),
        ("DO", "Dev2", "port1/line0", 1),
    ]


@pytest.mark.asyncio
async def test_ao_range_is_rejected_before_any_hook_call():
    backend = MockNiDaqBackend(
        OUTPUT_CONFIG, digital_values={("Dev2", "port0/line7"): 1}
    )
    with pytest.raises(NiDaqWriteRejected, match="range"):
        await backend.write(DEFAULT_MOCK_RESOURCE, "WRITE AO ao0 0.5")
    assert backend.output_writes == []
    assert backend.task_constructions == 0


@pytest.mark.asyncio
async def test_safe_drives_every_declared_output():
    backend = MockNiDaqBackend(
        OUTPUT_CONFIG, digital_values={("Dev2", "port0/line7"): 1}
    )
    await backend.write(DEFAULT_MOCK_RESOURCE, "SAFE")
    assert backend.output_writes == [
        ("AO", "Dev2", "ao0", 1.5),
        ("DO", "Dev2", "port1/line0", 0),
    ]


@pytest.mark.asyncio
async def test_safe_bypasses_unsatisfied_interlock():
    backend = MockNiDaqBackend(OUTPUT_CONFIG)
    await backend.write(DEFAULT_MOCK_RESOURCE, "SAFE")
    assert backend.output_writes == [
        ("AO", "Dev2", "ao0", 1.5),
        ("DO", "Dev2", "port1/line0", 0),
    ]


@pytest.mark.asyncio
async def test_close_is_sync_idempotent_never_raises_and_blocks_io():
    backend = MockNiDaqBackend(
        OUTPUT_CONFIG, digital_values={("Dev2", "port0/line7"): 1}
    )
    assert not inspect.iscoroutinefunction(backend.close)
    assert backend.close() is None
    first = list(backend.output_writes)
    assert backend.close() is None
    assert backend.output_writes == first
    with pytest.raises(NiDaqBackendError, match="closed"):
        await backend.query(DEFAULT_MOCK_RESOURCE, "READ AI ai0")


def test_close_swallows_safe_write_failure():
    backend = MockNiDaqBackend(OUTPUT_CONFIG, product_types={})
    assert backend.close() is None


def test_close_bypasses_unsatisfied_interlock_and_drives_all_outputs():
    backend = MockNiDaqBackend(OUTPUT_CONFIG)
    assert backend.close() is None
    assert backend.output_writes == [
        ("AO", "Dev2", "ao0", 1.5),
        ("DO", "Dev2", "port1/line0", 0),
    ]


@pytest.mark.asyncio
async def test_declared_model_mismatch_is_refused_and_not_cached():
    backend = MockNiDaqBackend(
        OUTPUT_CONFIG,
        digital_values={("Dev2", "port0/line7"): 1},
        product_types={"Dev2": "USB-6210"},
    )
    with pytest.raises(NiDaqBackendError, match="product type mismatch"):
        await backend.write(DEFAULT_MOCK_RESOURCE, "WRITE AO ao0 2")
    assert backend.output_writes == []
    assert backend.product_type_reads == 1


@pytest.mark.asyncio
async def test_successful_product_type_check_is_cached():
    backend = MockNiDaqBackend()
    await backend.query(DEFAULT_MOCK_RESOURCE, "READ AI ai0")
    await backend.query(DEFAULT_MOCK_RESOURCE, "READ DI port0/line0")
    assert backend.product_type_reads == 1


def test_backend_contains_no_usb_6009_physical_range_literal():
    import lab_nidaq_mcp.backend as backend_module

    source = inspect.getsource(backend_module)
    assert "5.0" not in source


def test_test_suite_mock_cannot_construct_a_real_task():
    backend = MockNiDaqBackend()
    assert backend.task_constructions == 0
    assert "nidaqmx" not in inspect.getmodule(backend).__dict__
