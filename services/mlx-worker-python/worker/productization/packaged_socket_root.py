from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Sequence


DARWIN_UNIX_SOCKET_PATH_MAX_BYTES = 103
PACKAGED_SOCKET_ROOT_PARENT = Path("/tmp")
_RUN_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class PackagedSocketRootError(RuntimeError):
    """Raised when a private, bounded packaged socket root cannot be created."""


def packaged_socket_paths(root: str | Path) -> tuple[Path, ...]:
    socket_root = Path(root)
    return (
        socket_root / "python.sock",
        socket_root / "swift.sock",
        socket_root / "control.sock",
        socket_root / "computer-broker/broker.sock",
    )


def validate_packaged_socket_root(
    root: str | Path,
    *,
    effective_uid: int | None = None,
    parent: Path = PACKAGED_SOCKET_ROOT_PARENT,
) -> Path:
    socket_root = Path(root)
    expected_parent = Path(parent)
    expected_uid = os.geteuid() if effective_uid is None else effective_uid
    if not socket_root.is_absolute() or socket_root.parent != expected_parent:
        raise PackagedSocketRootError(
            f"packaged socket root must be a direct child of {expected_parent}"
        )
    try:
        info = os.lstat(socket_root)
    except OSError as error:
        raise PackagedSocketRootError(
            f"unable to inspect packaged socket root: {error}"
        ) from error
    if not stat.S_ISDIR(info.st_mode):
        raise PackagedSocketRootError("packaged socket root is not a real directory")
    if info.st_uid != expected_uid:
        raise PackagedSocketRootError("packaged socket root is not owned by the current user")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise PackagedSocketRootError("packaged socket root must have mode 0700")
    for socket_path in packaged_socket_paths(socket_root):
        path_size = len(os.fsencode(os.fspath(socket_path)))
        if path_size > DARWIN_UNIX_SOCKET_PATH_MAX_BYTES:
            raise PackagedSocketRootError(
                "packaged socket path exceeds the macOS 103-byte Unix-domain limit: "
                f"{socket_path} ({path_size} bytes)"
            )
    return socket_root


def create_packaged_socket_root(
    run_token: str,
    *,
    parent: Path = PACKAGED_SOCKET_ROOT_PARENT,
) -> Path:
    if _RUN_TOKEN_PATTERN.fullmatch(run_token) is None:
        raise PackagedSocketRootError(
            "run token must contain at most 32 letters, numbers, underscores, or hyphens"
        )
    prefix = f"melix-{os.geteuid()}-{run_token}."
    try:
        created = Path(tempfile.mkdtemp(prefix=prefix, dir=os.fspath(parent)))
    except OSError as error:
        raise PackagedSocketRootError(
            f"unable to create packaged socket root under {parent}: {error}"
        ) from error
    try:
        return validate_packaged_socket_root(created, parent=parent)
    except PackagedSocketRootError as validation_error:
        try:
            os.rmdir(created)
        except OSError as cleanup_error:
            raise PackagedSocketRootError(
                "packaged socket root validation failed and the unsafe directory "
                f"could not be removed: {cleanup_error}"
            ) from validation_error
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a private, bounded socket root for a packaged Melix launch."
    )
    parser.add_argument("--run-token", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        socket_root = create_packaged_socket_root(args.run_token)
    except PackagedSocketRootError as error:
        print(f"Melix packaged socket root error: {error}", file=sys.stderr)
        return 1
    print(os.fspath(socket_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
