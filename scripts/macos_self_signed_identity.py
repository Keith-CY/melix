#!/usr/bin/env python3
"""Prepare and clean up a pinned self-signed macOS code-signing identity.

This entrypoint is intended for an ephemeral GitHub-hosted macOS runner. It
imports the identity into a disposable user keychain without mutating Apple
trust settings, and records enough state for ``cleanup`` to restore the exact
original keychain search list and prove that every temporary artifact was
removed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


DEFAULT_COMMON_NAME = "Melix GitHub Release Signing"
STATE_SCHEMA_VERSION = 2
_SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def require_github_hosted_macos_runner(
    environment: Mapping[str, str] | None = None,
) -> None:
    values = os.environ if environment is None else environment
    if (
        sys.platform != "darwin"
        or values.get("GITHUB_ACTIONS") != "true"
        or values.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise RuntimeError(
            "the isolated release signing keychain may only be prepared on a GitHub-hosted macOS runner"
        )


def normalize_fingerprint(value: str, *, algorithm: str) -> str:
    normalized = value.strip().replace(":", "").lower()
    pattern = _SHA1_PATTERN if algorithm == "sha1" else _SHA256_PATTERN
    if algorithm not in {"sha1", "sha256"} or pattern.fullmatch(normalized) is None:
        width = 40 if algorithm == "sha1" else 64
        raise ValueError(
            f"expected certificate {algorithm.upper()} must contain exactly {width} hex digits"
        )
    return normalized


def parse_security_keychain_list(output: str) -> list[str]:
    try:
        values = shlex.split(output)
    except ValueError as error:
        raise ValueError("security returned a malformed keychain search list") from error
    if any(not value for value in values):
        raise ValueError("security returned an empty keychain path")
    return values


def parse_security_certificate_sha1s(output: str) -> list[str]:
    fingerprints: list[str] = []
    for raw_line in output.splitlines():
        label, separator, value = raw_line.partition(":")
        if separator and label.strip() == "SHA-1 hash":
            fingerprints.append(normalize_fingerprint(value, algorithm="sha1"))
    return fingerprints


def parse_rfc2253_name(output: str, *, prefix: str) -> str:
    stripped = output.strip()
    expected_prefix = f"{prefix}="
    if not stripped.lower().startswith(expected_prefix.lower()):
        raise ValueError(f"openssl did not return an RFC2253 {prefix}")
    return stripped[len(expected_prefix) :].lstrip()


def common_name_from_rfc2253(name: str) -> str:
    match = re.search(r"(?:^|,)CN=([^,]+)(?:,|$)", name)
    if match is None:
        raise ValueError("code-signing certificate subject has no common name")
    return match.group(1)


def _run(
    command: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        list(command),
        input=input_bytes,
        check=False,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        redacted: list[str] = []
        redact_next = False
        for argument in command:
            if redact_next:
                redacted.append("<redacted>")
                redact_next = False
                continue
            redacted.append(argument)
            if argument in {"-P", "-p", "-k"}:
                redact_next = True
        raise RuntimeError(f"command failed ({' '.join(redacted)}): {detail}")
    return completed


def _output(command: Sequence[str], *, input_bytes: bytes | None = None) -> str:
    return _run(command, input_bytes=input_bytes).stdout.decode("utf-8").strip()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as temporary_file:
            descriptor = -1
            temporary_file.write(encoded)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("identity lifecycle state must be a JSON object")
    return payload


def _extract_pkcs12(
    p12_path: Path,
    *,
    password_environment_name: str,
    arguments: Sequence[str],
) -> bytes:
    command = [
        "openssl",
        "pkcs12",
        "-in",
        os.fspath(p12_path),
        *arguments,
        "-passin",
        f"env:{password_environment_name}",
    ]
    first = _run(command, check=False)
    if first.returncode == 0:
        return first.stdout
    legacy = _run([*command[:2], "-legacy", *command[2:]], check=False)
    if legacy.returncode != 0:
        detail = legacy.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"unable to inspect PKCS#12 signing identity: {detail}")
    return legacy.stdout


def inspect_and_pin_certificate(
    *,
    p12_path: Path,
    public_certificate_path: Path,
    password_environment_name: str,
    expected_sha256: str,
    expected_sha1: str,
    expected_common_name: str = DEFAULT_COMMON_NAME,
) -> dict[str, str]:
    """Validate independent pins and private-key ownership before keychain import."""

    if not p12_path.is_file():
        raise FileNotFoundError(f"PKCS#12 identity is missing: {p12_path}")
    if not os.environ.get(password_environment_name):
        raise ValueError(
            f"PKCS#12 password environment variable is empty: {password_environment_name}"
        )
    expected_sha256 = normalize_fingerprint(expected_sha256, algorithm="sha256")
    expected_sha1 = normalize_fingerprint(expected_sha1, algorithm="sha1")
    if not expected_common_name.strip():
        raise ValueError("expected certificate common name must not be empty")

    public_certificate = _extract_pkcs12(
        p12_path,
        password_environment_name=password_environment_name,
        arguments=("-clcerts", "-nokeys"),
    )
    public_certificate_path.parent.mkdir(parents=True, exist_ok=True)
    public_certificate_path.write_bytes(public_certificate)
    os.chmod(public_certificate_path, 0o600)

    subject = parse_rfc2253_name(
        _output(
            [
                "openssl",
                "x509",
                "-in",
                os.fspath(public_certificate_path),
                "-noout",
                "-subject",
                "-nameopt",
                "RFC2253",
            ]
        ),
        prefix="subject",
    )
    issuer = parse_rfc2253_name(
        _output(
            [
                "openssl",
                "x509",
                "-in",
                os.fspath(public_certificate_path),
                "-noout",
                "-issuer",
                "-nameopt",
                "RFC2253",
            ]
        ),
        prefix="issuer",
    )
    if subject != issuer:
        raise ValueError("release code-signing certificate must be self-signed")
    if common_name_from_rfc2253(subject) != expected_common_name:
        raise ValueError("release code-signing certificate common name mismatch")
    _run(
        [
            "openssl",
            "verify",
            "-CAfile",
            os.fspath(public_certificate_path),
            os.fspath(public_certificate_path),
        ]
    )
    certificate_text = _output(
        ["openssl", "x509", "-in", os.fspath(public_certificate_path), "-noout", "-text"]
    )
    if "Code Signing" not in certificate_text:
        raise ValueError("release certificate extended key usage must include code signing")

    observed_sha256 = normalize_fingerprint(
        _output(
            [
                "openssl",
                "x509",
                "-in",
                os.fspath(public_certificate_path),
                "-noout",
                "-fingerprint",
                "-sha256",
            ]
        ).split("=", 1)[-1],
        algorithm="sha256",
    )
    observed_sha1 = normalize_fingerprint(
        _output(
            [
                "openssl",
                "x509",
                "-in",
                os.fspath(public_certificate_path),
                "-noout",
                "-fingerprint",
                "-sha1",
            ]
        ).split("=", 1)[-1],
        algorithm="sha1",
    )
    if observed_sha256 != expected_sha256:
        raise ValueError("release certificate SHA-256 does not match the protected pin")
    if observed_sha1 != expected_sha1:
        raise ValueError("release certificate SHA-1 does not match the protected pin")

    certificate_public_key = _output(
        ["openssl", "x509", "-in", os.fspath(public_certificate_path), "-pubkey", "-noout"]
    )
    private_key = _extract_pkcs12(
        p12_path,
        password_environment_name=password_environment_name,
        arguments=("-nocerts", "-nodes"),
    )
    private_public_key = _output(["openssl", "pkey", "-pubout"], input_bytes=private_key)
    if certificate_public_key != private_public_key:
        raise ValueError("PKCS#12 private key does not match the pinned certificate")

    return {
        "certificate_sha256": observed_sha256,
        "certificate_sha1": observed_sha1,
        "common_name": expected_common_name,
    }


def _current_keychains() -> list[str]:
    return parse_security_keychain_list(_output(["security", "list-keychains", "-d", "user"]))


def _update_state(state_path: Path, state: dict[str, Any], **updates: Any) -> None:
    state.update(updates)
    _write_json(state_path, state)


def prepare_identity(
    *,
    p12_path: Path,
    keychain_path: Path,
    public_certificate_path: Path,
    sentinel_path: Path,
    state_path: Path,
    cleanup_report_path: Path,
    password_environment_name: str,
    p12_base64_environment_name: str | None,
    expected_sha256: str,
    expected_sha1: str,
    expected_common_name: str,
    github_output_path: Path | None,
) -> dict[str, Any]:
    require_github_hosted_macos_runner()
    for path in (keychain_path, public_certificate_path, sentinel_path, state_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite identity lifecycle path: {path}")

    original_keychains = _current_keychains()
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "status": "validating",
        "apple_trust_mutated": False,
        "original_keychains": original_keychains,
        "keychain_path": os.fspath(keychain_path),
        "public_certificate_path": os.fspath(public_certificate_path),
        "sentinel_path": os.fspath(sentinel_path),
        "p12_path": os.fspath(p12_path),
        "cleanup_report_path": os.fspath(cleanup_report_path),
        "keychain_created": False,
        "keychain_create_attempted": False,
        "identity_imported": False,
        "partition_list_configured": False,
        "search_list_changed": False,
        "search_list_change_attempted": False,
        "sentinel_verified": False,
        "material_paths": [
            os.fspath(p12_path),
            os.fspath(public_certificate_path),
            os.fspath(sentinel_path),
        ],
    }
    _write_json(state_path, state)
    try:
        if p12_base64_environment_name is not None:
            encoded_p12 = os.environ.get(p12_base64_environment_name, "")
            if not encoded_p12:
                raise ValueError(
                    f"PKCS#12 base64 environment variable is empty: {p12_base64_environment_name}"
                )
            try:
                decoded_p12 = base64.b64decode(encoded_p12, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("PKCS#12 base64 payload is invalid") from error
            if not decoded_p12:
                raise ValueError("PKCS#12 base64 payload decoded to an empty file")
            p12_path.write_bytes(decoded_p12)
            os.chmod(p12_path, 0o600)
        observations = inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=public_certificate_path,
            password_environment_name=password_environment_name,
            expected_sha256=expected_sha256,
            expected_sha1=expected_sha1,
            expected_common_name=expected_common_name,
        )
        _update_state(state_path, state, status="validated", **observations)

        # The macOS `security` CLI has no stdin or environment indirection for
        # these password flags, so the keychain and PKCS#12 passwords briefly
        # exist in child-process argv. This tradeoff is restricted to the
        # enforced single-tenant GitHub-hosted runner; `_run` redacts them from
        # every error message and workflow log.
        keychain_password = _output(["openssl", "rand", "-hex", "24"])
        _update_state(state_path, state, keychain_create_attempted=True)
        _run(["security", "create-keychain", "-p", keychain_password, os.fspath(keychain_path)])
        _update_state(state_path, state, keychain_created=True)
        _run(["security", "set-keychain-settings", "-lut", "21600", os.fspath(keychain_path)])
        _run(["security", "unlock-keychain", "-p", keychain_password, os.fspath(keychain_path)])
        _run(
            [
                "security",
                "import",
                os.fspath(p12_path),
                "-k",
                os.fspath(keychain_path),
                "-P",
                os.environ[password_environment_name],
                "-T",
                "/usr/bin/codesign",
            ]
        )
        _update_state(state_path, state, status="identity_imported", identity_imported=True)
        _run(
            [
                "security",
                "set-key-partition-list",
                "-S",
                "apple-tool:,apple:",
                "-s",
                "-k",
                keychain_password,
                os.fspath(keychain_path),
            ]
        )
        _update_state(state_path, state, partition_list_configured=True)
        _update_state(state_path, state, search_list_change_attempted=True)
        _run(
            [
                "security",
                "list-keychains",
                "-d",
                "user",
                "-s",
                os.fspath(keychain_path),
                *original_keychains,
            ]
        )
        _update_state(state_path, state, search_list_changed=True)

        certificate_listing = _output(
            [
                "security",
                "find-certificate",
                "-a",
                "-Z",
                "-c",
                expected_common_name,
                os.fspath(keychain_path),
            ]
        )
        if parse_security_certificate_sha1s(certificate_listing) != [
            observations["certificate_sha1"]
        ]:
            raise RuntimeError(
                "pinned release certificate is not unique in the isolated keychain"
            )

        # Copy only the Mach-O bytes: copy2() also propagates Apple file flags
        # from the sealed system volume, which GitHub runners cannot apply in
        # RUNNER_TEMP. The sentinel needs executable mode, not source metadata.
        shutil.copyfile("/usr/bin/true", sentinel_path)
        sentinel_path.chmod(0o700)
        _run(
            [
                "codesign",
                "--force",
                "--options",
                "runtime",
                "--sign",
                observations["certificate_sha1"],
                "--keychain",
                os.fspath(keychain_path),
                "--timestamp=none",
                os.fspath(sentinel_path),
            ]
        )
        _run(["codesign", "--verify", "--strict", "--verbose=4", os.fspath(sentinel_path)])
        sentinel_details = _run(
            ["codesign", "--display", "--verbose=4", os.fspath(sentinel_path)]
        )
        sentinel_output = (sentinel_details.stdout + sentinel_details.stderr).decode(
            "utf-8", errors="replace"
        )
        if "runtime" not in sentinel_output:
            raise RuntimeError("real code-signing sentinel is missing hardened runtime")
        _update_state(state_path, state, status="prepared", sentinel_verified=True)
        if github_output_path is not None:
            with github_output_path.open("a", encoding="utf-8") as handle:
                handle.write(f'certificate_sha1={observations["certificate_sha1"]}\n')
                handle.write(f'certificate_sha256={observations["certificate_sha256"]}\n')
                handle.write(f"keychain_path={keychain_path}\n")
                handle.write(f"state_path={state_path}\n")
        return state
    except BaseException:
        cleanup = cleanup_identity(state_path=state_path, report_path=cleanup_report_path)
        if not cleanup["cleanup_confirmed"]:
            raise RuntimeError("identity preparation failed and cleanup was not confirmed")
        raise


def cleanup_identity(*, state_path: Path, report_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not state_path.is_file():
        report = {
            "schema_version": STATE_SCHEMA_VERSION,
            "cleanup_confirmed": False,
            "apple_trust_mutated": False,
            "errors": ["state file missing"],
        }
        _write_json(report_path, report)
        return report
    state = _read_json(state_path)
    keychain_path = Path(str(state["keychain_path"]))
    original_keychains = [str(path) for path in state.get("original_keychains", [])]
    apple_trust_unchanged = state.get("apple_trust_mutated") is False
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        errors.append("identity lifecycle state schema is unsupported")
    if not apple_trust_unchanged:
        errors.append("identity lifecycle state does not prove Apple trust remained unchanged")

    if state.get("search_list_changed") or state.get("search_list_change_attempted"):
        restore = _run(
            ["security", "list-keychains", "-d", "user", "-s", *original_keychains],
            check=False,
        )
        if restore.returncode != 0:
            errors.append("keychain search list restoration command failed")

    if state.get("keychain_created") or state.get("keychain_create_attempted"):
        _run(["security", "delete-keychain", os.fspath(keychain_path)], check=False)

    original_keychains_restored = False
    try:
        original_keychains_restored = _current_keychains() == original_keychains
        if not original_keychains_restored:
            errors.append("keychain search list does not match its original value")
    except Exception as error:  # pragma: no cover - defensive cleanup reporting
        errors.append(f"keychain search list verification failed: {error}")

    material_paths = [Path(str(path)) for path in state.get("material_paths", [])]
    for material_path in material_paths:
        try:
            material_path.unlink(missing_ok=True)
        except OSError as error:
            errors.append(f"temporary material removal failed for {material_path}: {error}")
    ephemeral_keychain_removed = not keychain_path.exists()
    if not ephemeral_keychain_removed:
        errors.append("temporary keychain remains on disk")
    residual_material = [os.fspath(path) for path in material_paths if path.exists()]
    temporary_material_removed = not residual_material
    if residual_material:
        errors.append(f"temporary identity material remains: {residual_material}")

    report = {
        "schema_version": STATE_SCHEMA_VERSION,
        "cleanup_confirmed": not errors,
        "apple_trust_mutated": not apple_trust_unchanged,
        "certificate_sha256": state.get("certificate_sha256"),
        "certificate_sha1": state.get("certificate_sha1"),
        "original_keychains_restored": original_keychains_restored,
        "ephemeral_keychain_removed": ephemeral_keychain_removed,
        "temporary_material_removed": temporary_material_removed,
        "errors": errors,
    }
    _write_json(report_path, report)
    if not errors:
        state_path.unlink(missing_ok=True)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--p12", type=Path, required=True)
    prepare_parser.add_argument("--keychain", type=Path, required=True)
    prepare_parser.add_argument("--public-certificate", type=Path, required=True)
    prepare_parser.add_argument("--sentinel", type=Path, required=True)
    prepare_parser.add_argument("--state", type=Path, required=True)
    prepare_parser.add_argument("--cleanup-report", type=Path, required=True)
    prepare_parser.add_argument("--password-env", required=True)
    prepare_parser.add_argument("--p12-base64-env")
    prepare_parser.add_argument("--expected-sha256", required=True)
    prepare_parser.add_argument("--expected-sha1", required=True)
    prepare_parser.add_argument("--expected-common-name", default=DEFAULT_COMMON_NAME)
    prepare_parser.add_argument("--github-output", type=Path)

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--state", type=Path, required=True)
    cleanup_parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args(argv)

    if arguments.command == "prepare":
        prepare_identity(
            p12_path=arguments.p12.resolve(),
            keychain_path=arguments.keychain.resolve(),
            public_certificate_path=arguments.public_certificate.resolve(),
            sentinel_path=arguments.sentinel.resolve(),
            state_path=arguments.state.resolve(),
            cleanup_report_path=arguments.cleanup_report.resolve(),
            password_environment_name=arguments.password_env,
            p12_base64_environment_name=arguments.p12_base64_env,
            expected_sha256=arguments.expected_sha256,
            expected_sha1=arguments.expected_sha1,
            expected_common_name=arguments.expected_common_name,
            github_output_path=(
                arguments.github_output.resolve() if arguments.github_output else None
            ),
        )
        return 0

    report = cleanup_identity(
        state_path=arguments.state.resolve(), report_path=arguments.report.resolve()
    )
    return 0 if report["cleanup_confirmed"] else 1


if __name__ == "__main__":  # pragma: no cover - CLI guard
    raise SystemExit(main())
