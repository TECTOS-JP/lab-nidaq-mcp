"""Thin CLI wrapper around the public lab-executor server contract."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

import yaml
from lab_executor.control_plane import run_mcp_with_control
from lab_executor.server import compose_server

from lab_nidaq_mcp.backend import NiDaqBackend


def _control_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("control port must be an integer") from exc
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("control port must be between 0 and 65535")
    return port


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lab-nidaq", description="Serve NI-DAQmx devices through lab-executor."
    )
    parser.add_argument(
        "--config", required=True, help="YAML file containing the devices mapping"
    )
    parser.add_argument("--dry-run", action="store_true", help="compose and list tools")
    parser.add_argument("--control-port", type=_control_port, default=0)
    return parser


def _load(path: str) -> dict:
    data = yaml.safe_load(Path(path).read_text("utf-8"))
    if not isinstance(data, dict) or set(data) != {"devices"}:
        raise ValueError("config file must contain exactly a devices mapping")
    return data["devices"]


async def _dry_run(mcp: object, backend: NiDaqBackend) -> None:
    tools = await getattr(mcp, "list_tools")()
    print(
        json.dumps(
            {
                "backend_id": backend.backend_id,
                "resources": await backend.list_resources(),
                "tools": sorted(tool.name for tool in tools),
            },
            indent=2,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        backend = NiDaqBackend(_load(args.config))
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    mcp, job_mgr = compose_server(backend, name="lab-nidaq-mcp")
    try:
        if args.dry_run:
            asyncio.run(_dry_run(mcp, backend))
        else:
            asyncio.run(
                run_mcp_with_control(
                    mcp, job_mgr, args.control_port, backend_id=backend.backend_id
                )
            )
    finally:
        backend.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
