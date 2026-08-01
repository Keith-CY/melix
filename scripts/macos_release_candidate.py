#!/usr/bin/env python3
"""Create and verify receipts for untrusted macOS release candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Iterator, Mapping, Sequence


CANDIDATE_TARGET_ID = "macos_app_bundle_github_release_candidate"
CANDIDATE_BUNDLE_ID = "io.melix.menubar.release-candidate"
_STABLE_TAG_PATTERN = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_RECEIPT_KEYS = {
    "schema_version",
    "candidate_target_id",
    "candidate_bundle_id",
    "tag_name",
    "source_sha",
    "bundle_name",
    "bundle_tree_sha256",
    "artifact_sha256",
}


def _validate_identity(tag_name: str, source_sha: str) -> tuple[str, str]:
    if _STABLE_TAG_PATTERN.fullmatch(tag_name) is None:
        raise ValueError("candidate must be bound to a canonical stable release tag")
    normalized_sha = source_sha.strip().lower()
    if _FULL_SHA_PATTERN.fullmatch(normalized_sha) is None:
        raise ValueError("candidate source SHA must be a full 40-character Git commit SHA")
    return tag_name, normalized_sha


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _tree_entries(root: Path) -> Iterator[Path]:
    def visit(directory: Path) -> Iterator[Path]:
        for entry in sorted(os.scandir(directory), key=lambda item: os.fsencode(item.name)):
            path = Path(entry.path)
            yield path
            if entry.is_dir(follow_symlinks=False):
                yield from visit(path)

    yield from visit(root)


def _bundle_tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _tree_entries(root):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(stat.S_IMODE(metadata.st_mode).to_bytes(4, "big"))
        if stat.S_ISLNK(metadata.st_mode):
            marker = b"L"
            payload = os.readlink(path).encode("utf-8")
        elif stat.S_ISDIR(metadata.st_mode):
            marker = b"D"
            payload = b""
        elif stat.S_ISREG(metadata.st_mode):
            marker = b"F"
            payload = bytes.fromhex(_file_digest(path).removeprefix("sha256:"))
        else:
            raise ValueError(f"unsupported bundle entry type: {relative.decode('utf-8')}")
        digest.update(marker)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def _validate_paths(app_path: Path, archive_path: Path) -> tuple[Path, Path]:
    app_path = app_path.resolve()
    archive_path = archive_path.resolve()
    if not app_path.is_dir():
        raise ValueError(f"candidate app bundle does not exist: {app_path}")
    if not archive_path.is_file():
        raise ValueError(f"candidate archive does not exist: {archive_path}")
    return app_path, archive_path


def create_candidate_receipt(
    *,
    app_path: Path,
    archive_path: Path,
    tag_name: str,
    source_sha: str,
) -> dict[str, object]:
    tag_name, source_sha = _validate_identity(tag_name, source_sha)
    app_path, archive_path = _validate_paths(app_path, archive_path)
    return {
        "schema_version": 1,
        "candidate_target_id": CANDIDATE_TARGET_ID,
        "candidate_bundle_id": CANDIDATE_BUNDLE_ID,
        "tag_name": tag_name,
        "source_sha": source_sha,
        "bundle_name": app_path.name,
        "bundle_tree_sha256": _bundle_tree_digest(app_path),
        "artifact_sha256": _file_digest(archive_path),
    }


def _validate_receipt_shape(receipt: Mapping[str, object]) -> None:
    if set(receipt) != _RECEIPT_KEYS:
        missing = sorted(_RECEIPT_KEYS - set(receipt))
        extra = sorted(set(receipt) - _RECEIPT_KEYS)
        raise ValueError(f"candidate receipt shape mismatch: missing={missing}, extra={extra}")
    if receipt["schema_version"] != 1:
        raise ValueError("unsupported candidate receipt schema version")
    if receipt["candidate_target_id"] != CANDIDATE_TARGET_ID:
        raise ValueError("candidate target identifier mismatch")
    if receipt["candidate_bundle_id"] != CANDIDATE_BUNDLE_ID:
        raise ValueError("candidate bundle identifier mismatch")
    for field in _RECEIPT_KEYS - {"schema_version"}:
        if not isinstance(receipt[field], str):
            raise ValueError(f"candidate receipt field {field} must be a string")


def verify_candidate_receipt(
    receipt: Mapping[str, object],
    *,
    app_path: Path,
    archive_path: Path,
    expected_tag_name: str,
    expected_source_sha: str,
) -> Mapping[str, object]:
    _validate_receipt_shape(receipt)
    expected_tag_name, expected_source_sha = _validate_identity(
        expected_tag_name, expected_source_sha
    )
    app_path, archive_path = _validate_paths(app_path, archive_path)
    if receipt["tag_name"] != expected_tag_name:
        raise ValueError("candidate receipt tag mismatch")
    if receipt["source_sha"] != expected_source_sha:
        raise ValueError("candidate receipt source SHA mismatch")
    if receipt["bundle_name"] != app_path.name:
        raise ValueError("candidate receipt bundle name mismatch")
    if receipt["artifact_sha256"] != _file_digest(archive_path):
        raise ValueError("candidate artifact digest mismatch")
    if receipt["bundle_tree_sha256"] != _bundle_tree_digest(app_path):
        raise ValueError("candidate bundle tree digest mismatch")
    return receipt


def write_candidate_receipt(receipt: Mapping[str, object], path: Path) -> None:
    _validate_receipt_shape(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_receipt(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("candidate receipt must contain a JSON object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--app", type=Path, required=True)
    create_parser.add_argument("--archive", type=Path, required=True)
    create_parser.add_argument("--tag", required=True)
    create_parser.add_argument("--source-sha", required=True)
    create_parser.add_argument("--output", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--receipt", type=Path, required=True)
    verify_parser.add_argument("--app", type=Path, required=True)
    verify_parser.add_argument("--archive", type=Path, required=True)
    verify_parser.add_argument("--tag", required=True)
    verify_parser.add_argument("--source-sha", required=True)

    arguments = parser.parse_args(argv)
    if arguments.command == "create":
        receipt = create_candidate_receipt(
            app_path=arguments.app,
            archive_path=arguments.archive,
            tag_name=arguments.tag,
            source_sha=arguments.source_sha,
        )
        write_candidate_receipt(receipt, arguments.output)
    else:
        receipt = _read_receipt(arguments.receipt)
        verify_candidate_receipt(
            receipt,
            app_path=arguments.app,
            archive_path=arguments.archive,
            expected_tag_name=arguments.tag,
            expected_source_sha=arguments.source_sha,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
