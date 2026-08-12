from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


ACTIVE_RUNTIME_SCHEMA_VERSION = "melix.active_runtime.v1"


def write_active_runtime_descriptor(
    *,
    output_path: str | Path,
    app_process_id: int,
    control_plane_process_id: int,
    python_worker_process_id: int,
    swift_text_worker_process_id: int,
    computer_broker_process_id: int = 0,
    python_worker_socket_path: str,
    swift_text_worker_socket_path: str,
    control_plane_socket_path: str = "",
    service_base_url: str,
    now_unix_ms: Callable[[], int] = lambda: int(time.time() * 1_000),
) -> dict[str, Any]:
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": ACTIVE_RUNTIME_SCHEMA_VERSION,
        "app_process_id": int(app_process_id),
        "control_plane_process_id": int(control_plane_process_id),
        "python_worker_process_id": int(python_worker_process_id),
        "swift_text_worker_process_id": int(swift_text_worker_process_id),
        "python_worker_socket_path": python_worker_socket_path,
        "swift_text_worker_socket_path": swift_text_worker_socket_path,
        "service_base_url": service_base_url,
        "updated_at_unix_ms": int(now_unix_ms()),
    }
    normalized_control_plane_socket_path = control_plane_socket_path.strip()
    if normalized_control_plane_socket_path:
        payload["control_plane_socket_path"] = normalized_control_plane_socket_path
    if computer_broker_process_id > 0:
        payload["computer_broker_process_id"] = int(computer_broker_process_id)

    descriptor_file = None
    temporary_path: Path | None = None
    try:
        descriptor_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        )
        temporary_path = Path(descriptor_file.name)
        os.chmod(temporary_path, 0o600)
        json.dump(payload, descriptor_file, indent=2, sort_keys=True)
        descriptor_file.write("\n")
        descriptor_file.flush()
        os.fsync(descriptor_file.fileno())
        descriptor_file.close()
        descriptor_file = None
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if descriptor_file is not None:
            descriptor_file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the active packaged Melix runtime descriptor.")
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--app-process-id", required=True, type=int)
    parser.add_argument("--control-plane-process-id", required=True, type=int)
    parser.add_argument("--python-worker-process-id", required=True, type=int)
    parser.add_argument("--swift-text-worker-process-id", required=True, type=int)
    parser.add_argument("--computer-broker-process-id", type=int, default=0)
    parser.add_argument("--python-worker-socket-path", required=True)
    parser.add_argument("--swift-text-worker-socket-path", required=True)
    parser.add_argument("--control-plane-socket-path", default="")
    parser.add_argument("--service-base-url", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    write_active_runtime_descriptor(
        output_path=args.output_path,
        app_process_id=args.app_process_id,
        control_plane_process_id=args.control_plane_process_id,
        python_worker_process_id=args.python_worker_process_id,
        swift_text_worker_process_id=args.swift_text_worker_process_id,
        computer_broker_process_id=args.computer_broker_process_id,
        python_worker_socket_path=args.python_worker_socket_path,
        swift_text_worker_socket_path=args.swift_text_worker_socket_path,
        control_plane_socket_path=args.control_plane_socket_path,
        service_base_url=args.service_base_url,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
