#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spawn a detached background process and print its pid.")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("No command was provided.", file=sys.stderr)
        return 1

    environment = os.environ.copy()
    for assignment in args.env:
        key, separator, value = assignment.partition("=")
        if not separator:
            print(f"Invalid environment override: {assignment}", file=sys.stderr)
            return 1
        environment[key] = value

    log_path = Path(args.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("ab") as handle:
        process = subprocess.Popen(
            command,
            cwd=args.cwd,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
