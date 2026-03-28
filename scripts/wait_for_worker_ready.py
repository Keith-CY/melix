#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import runtime_pb2, runtime_pb2_grpc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait until a Melix worker answers handshake requests.")
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    deadline = time.time() + args.timeout_seconds
    channel = grpc.insecure_channel(f"unix://{args.socket_path}")
    stub = runtime_pb2_grpc.RuntimeServiceStub(channel)

    try:
        while time.time() < deadline:
            try:
                response = stub.Handshake(
                    runtime_pb2.HandshakeRequest(
                        protocol_version="melix.worker.v1",
                        worker_id="scripts.wait_for_worker_ready",
                        controlplane_instance_id="scripts.wait_for_worker_ready",
                    ),
                    timeout=2,
                )
                if response.protocol_version == "melix.worker.v1":
                    print(os.fspath(Path(args.socket_path)))
                    return 0
            except grpc.RpcError:
                pass
            time.sleep(0.2)
    finally:
        channel.close()

    print(f"Worker did not become ready on {args.socket_path} within {args.timeout_seconds:.1f}s.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
