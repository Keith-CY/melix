from __future__ import annotations

import base64
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "macos_self_signed_identity.py"


def load_module():
    spec = importlib.util.spec_from_file_location("melix_macos_self_signed_identity", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def create_test_identity(tmp_path: Path) -> tuple[Path, Path, str, str, str]:
    config = tmp_path / "certificate.cnf"
    private_key = tmp_path / "identity.key"
    certificate = tmp_path / "identity.pem"
    p12_path = tmp_path / "identity.p12"
    password = "test-password"
    config.write_text(
        """[req]
distinguished_name=dn
prompt=no
x509_extensions=codesign
[dn]
CN=Melix GitHub Release Signing
[codesign]
basicConstraints=critical,CA:TRUE
keyUsage=critical,digitalSignature,keyCertSign
extendedKeyUsage=codeSigning
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-config",
            str(config),
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkcs12",
            "-export",
            "-inkey",
            str(private_key),
            "-in",
            str(certificate),
            "-name",
            "Melix GitHub Release Signing",
            "-passout",
            f"pass:{password}",
            "-out",
            str(p12_path),
        ],
        check=True,
        capture_output=True,
    )

    def fingerprint(algorithm: str) -> str:
        output = subprocess.check_output(
            [
                "openssl",
                "x509",
                "-in",
                str(certificate),
                "-noout",
                "-fingerprint",
                f"-{algorithm}",
            ],
            text=True,
        )
        return output.split("=", 1)[-1].strip().replace(":", "").lower()

    return p12_path, certificate, password, fingerprint("sha256"), fingerprint("sha1")


@pytest.mark.parametrize(
    ("algorithm", "value", "expected"),
    [
        (
            "sha1",
            "01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67",
            "0123456789abcdef0123456789abcdef01234567",
        ),
        ("sha256", "AB" * 32, "ab" * 32),
    ],
)
def test_normalize_fingerprint_accepts_independent_sha_pins(
    algorithm: str, value: str, expected: str
) -> None:
    module = load_module()

    assert module.normalize_fingerprint(value, algorithm=algorithm) == expected


@pytest.mark.parametrize(
    ("algorithm", "value"),
    [("sha1", "0" * 64), ("sha256", "0" * 40), ("md5", "0" * 32), ("sha1", "xyz")],
)
def test_normalize_fingerprint_rejects_wrong_algorithm_or_width(
    algorithm: str, value: str
) -> None:
    module = load_module()

    with pytest.raises(ValueError, match="certificate"):
        module.normalize_fingerprint(value, algorithm=algorithm)


def test_parse_security_keychain_list_preserves_exact_order_and_spaces() -> None:
    module = load_module()

    assert module.parse_security_keychain_list(
        '    "/Users/runner/Library/Keychains/login.keychain-db"\n'
        '    "/private/tmp/a release.keychain-db"\n'
    ) == [
        "/Users/runner/Library/Keychains/login.keychain-db",
        "/private/tmp/a release.keychain-db",
    ]


def test_parse_security_certificate_sha1s_requires_valid_hashes() -> None:
    module = load_module()

    assert module.parse_security_certificate_sha1s(
        f"SHA-256 hash: {'ab' * 32}\nSHA-1 hash: {'01' * 20}\n"
    ) == ["01" * 20]
    with pytest.raises(ValueError, match="certificate"):
        module.parse_security_certificate_sha1s("SHA-1 hash: invalid\n")


def test_rfc2253_certificate_identity_requires_exact_common_name() -> None:
    module = load_module()
    subject = module.parse_rfc2253_name(
        "subject=OU=Release,CN=Melix GitHub Release Signing", prefix="subject"
    )

    assert module.common_name_from_rfc2253(subject) == "Melix GitHub Release Signing"

    with pytest.raises(ValueError, match="RFC2253"):
        module.parse_rfc2253_name("issuer=wrong", prefix="subject")
    with pytest.raises(ValueError, match="common name"):
        module.common_name_from_rfc2253("OU=Release")


def test_command_failure_redacts_password_and_keychain_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, b"", b"expected failure"
        ),
    )

    with pytest.raises(RuntimeError) as error:
        module._run(["security", "import", "input.p12", "-P", "secret", "-k", "private"])

    assert "secret" not in str(error.value)
    assert "private" not in str(error.value)
    assert str(error.value).count("<redacted>") == 2


def test_pkcs12_inspection_falls_back_to_legacy_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    responses = iter(
        [
            subprocess.CompletedProcess([], 1, b"", b"modern failed"),
            subprocess.CompletedProcess([], 0, b"legacy payload", b""),
        ]
    )
    monkeypatch.setattr(module, "_run", lambda *args, **kwargs: next(responses))
    assert module._extract_pkcs12(
        tmp_path / "identity.p12",
        password_environment_name="PASSWORD",
        arguments=("-clcerts",),
    ) == b"legacy payload"

    responses = iter(
        [
            subprocess.CompletedProcess([], 1, b"", b"modern failed"),
            subprocess.CompletedProcess([], 1, b"", b"legacy failed"),
        ]
    )
    monkeypatch.setattr(module, "_run", lambda *args, **kwargs: next(responses))
    with pytest.raises(RuntimeError, match="legacy failed"):
        module._extract_pkcs12(
            tmp_path / "identity.p12",
            password_environment_name="PASSWORD",
            arguments=("-clcerts",),
        )


def test_inspect_and_pin_certificate_validates_real_pkcs12(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    p12_path, _, password, sha256, sha1 = create_test_identity(tmp_path)
    public_certificate = tmp_path / "extracted.pem"
    monkeypatch.setenv("PASSWORD", password)

    observations = module.inspect_and_pin_certificate(
        p12_path=p12_path,
        public_certificate_path=public_certificate,
        password_environment_name="PASSWORD",
        expected_sha256=sha256,
        expected_sha1=sha1,
    )

    assert observations == {
        "certificate_sha256": sha256,
        "certificate_sha1": sha1,
        "common_name": module.DEFAULT_COMMON_NAME,
    }
    assert public_certificate.is_file()

    with pytest.raises(ValueError, match="SHA-256"):
        module.inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=public_certificate,
            password_environment_name="PASSWORD",
            expected_sha256="0" * 64,
            expected_sha1=sha1,
        )
    with pytest.raises(ValueError, match="SHA-1"):
        module.inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=public_certificate,
            password_environment_name="PASSWORD",
            expected_sha256=sha256,
            expected_sha1="0" * 40,
        )
    with pytest.raises(ValueError, match="common name"):
        module.inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=public_certificate,
            password_environment_name="PASSWORD",
            expected_sha256=sha256,
            expected_sha1=sha1,
            expected_common_name="Wrong Name",
        )


def test_inspect_certificate_rejects_missing_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    p12_path = tmp_path / "identity.p12"
    with pytest.raises(FileNotFoundError):
        module.inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=tmp_path / "certificate.pem",
            password_environment_name="PASSWORD",
            expected_sha256="a" * 64,
            expected_sha1="b" * 40,
        )
    p12_path.write_bytes(b"p12")
    monkeypatch.delenv("PASSWORD", raising=False)
    with pytest.raises(ValueError, match="password"):
        module.inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=tmp_path / "certificate.pem",
            password_environment_name="PASSWORD",
            expected_sha256="a" * 64,
            expected_sha1="b" * 40,
        )
    monkeypatch.setenv("PASSWORD", "password")
    with pytest.raises(ValueError, match="common name"):
        module.inspect_and_pin_certificate(
            p12_path=p12_path,
            public_certificate_path=tmp_path / "certificate.pem",
            password_environment_name="PASSWORD",
            expected_sha256="a" * 64,
            expected_sha1="b" * 40,
            expected_common_name=" ",
        )


def test_cleanup_fails_closed_when_state_is_missing(tmp_path: Path) -> None:
    module = load_module()
    report_path = tmp_path / "cleanup.json"

    report = module.cleanup_identity(
        state_path=tmp_path / "missing-state.json", report_path=report_path
    )

    assert report["cleanup_confirmed"] is False
    assert report["schema_version"] == module.STATE_SCHEMA_VERSION
    assert report["apple_trust_mutated"] is False
    assert report_path.is_file()


def test_prepare_identity_rejects_non_github_hosted_runner() -> None:
    module = load_module()

    with pytest.raises(RuntimeError, match="GitHub-hosted macOS runner"):
        module.require_github_hosted_macos_runner({})


def test_prepare_accepts_base64_p12_without_apple_trust_and_cleans_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    p12_path = tmp_path / "identity.p12"
    keychain_path = tmp_path / "identity.keychain-db"
    certificate_path = tmp_path / "identity.pem"
    sentinel_path = tmp_path / "sentinel"
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "cleanup.json"
    github_output_path = tmp_path / "github-output.txt"
    sha256 = "ab" * 32
    sha1 = "01" * 20
    commands: list[list[str]] = []

    monkeypatch.setenv("TEST_P12", base64.b64encode(b"test-p12").decode("ascii"))
    monkeypatch.setenv("TEST_PASSWORD", "test-password")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setattr(module, "_current_keychains", lambda: ["/tmp/login.keychain-db"])
    monkeypatch.setattr(
        module.shutil,
        "copyfile",
        lambda _source, destination: Path(destination).write_bytes(b"sentinel"),
    )

    def fake_inspect(**_: object) -> dict[str, str]:
        certificate_path.write_text("certificate", encoding="utf-8")
        return {
            "certificate_sha256": sha256,
            "certificate_sha1": sha1,
            "common_name": module.DEFAULT_COMMON_NAME,
        }

    def fake_run(
        command: list[str], *, input_bytes: bytes | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        del input_bytes, check
        command = list(command)
        commands.append(command)
        stdout = b""
        stderr = b""
        returncode = 0
        if command[:3] == ["openssl", "rand", "-hex"]:
            stdout = b"keychain-password\n"
        elif command[:3] == ["security", "create-keychain", "-p"]:
            keychain_path.write_bytes(b"keychain")
        elif command[:2] == ["security", "find-certificate"]:
            stdout = f"SHA-1 hash: {sha1.upper()}\n".encode()
        elif command[:2] == ["codesign", "--display"]:
            stderr = b"flags=0x10000(runtime)\n"
        elif command[:2] == ["security", "delete-keychain"]:
            keychain_path.unlink(missing_ok=True)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(module, "inspect_and_pin_certificate", fake_inspect)
    monkeypatch.setattr(module, "_run", fake_run)

    state = module.prepare_identity(
        p12_path=p12_path,
        keychain_path=keychain_path,
        public_certificate_path=certificate_path,
        sentinel_path=sentinel_path,
        state_path=state_path,
        cleanup_report_path=report_path,
        password_environment_name="TEST_PASSWORD",
        p12_base64_environment_name="TEST_P12",
        expected_sha256=sha256,
        expected_sha1=sha1,
        expected_common_name=module.DEFAULT_COMMON_NAME,
        github_output_path=github_output_path,
    )

    assert state["status"] == "prepared"
    assert state["schema_version"] == module.STATE_SCHEMA_VERSION
    assert state["apple_trust_mutated"] is False
    assert state["identity_imported"] is True
    assert state["partition_list_configured"] is True
    assert state["sentinel_verified"] is True
    assert sentinel_path.stat().st_mode & 0o777 == 0o700
    assert p12_path.read_bytes() == b"test-p12"
    assert f"certificate_sha1={sha1}" in github_output_path.read_text(encoding="utf-8")

    report = module.cleanup_identity(state_path=state_path, report_path=report_path)

    assert report["cleanup_confirmed"] is True
    assert report["apple_trust_mutated"] is False
    assert report["original_keychains_restored"] is True
    assert report["ephemeral_keychain_removed"] is True
    assert report["temporary_material_removed"] is True
    assert not any("sudo" in command for command in commands)
    assert not any(
        argument in {"add-trusted-cert", "remove-trusted-cert"}
        for command in commands
        for argument in command
    )
    sentinel_sign = next(
        command for command in commands if command[:2] == ["codesign", "--force"]
    )
    assert "--keychain" in sentinel_sign
    assert str(keychain_path) in sentinel_sign
    assert sentinel_sign[sentinel_sign.index("--options") + 1] == "runtime"
    assert not p12_path.exists()
    assert not certificate_path.exists()
    assert not sentinel_path.exists()
    assert not keychain_path.exists()
    assert not state_path.exists()


@pytest.mark.parametrize(
    "certificate_listing",
    [
        pytest.param("", id="zero-certificates"),
        pytest.param(
            f"SHA-1 hash: {'01' * 20}\nSHA-1 hash: {'01' * 20}\n",
            id="duplicate-certificate",
        ),
        pytest.param(f"SHA-1 hash: {'02' * 20}\n", id="wrong-certificate"),
    ],
)
def test_prepare_rejects_non_unique_pinned_certificate_and_confirms_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    certificate_listing: str,
) -> None:
    module = load_module()
    p12_path = tmp_path / "identity.p12"
    keychain_path = tmp_path / "identity.keychain-db"
    certificate_path = tmp_path / "identity.pem"
    sentinel_path = tmp_path / "sentinel"
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "cleanup.json"
    sha256 = "ab" * 32
    sha1 = "01" * 20
    original_keychains = ["/tmp/login.keychain-db"]
    commands: list[list[str]] = []

    monkeypatch.setenv("TEST_P12", base64.b64encode(b"test-p12").decode("ascii"))
    monkeypatch.setenv("TEST_PASSWORD", "test-password")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setattr(module, "_current_keychains", lambda: original_keychains)

    def fake_inspect(**_: object) -> dict[str, str]:
        certificate_path.write_text("certificate", encoding="utf-8")
        return {
            "certificate_sha256": sha256,
            "certificate_sha1": sha1,
            "common_name": module.DEFAULT_COMMON_NAME,
        }

    def fake_run(
        command: list[str], *, input_bytes: bytes | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        del input_bytes, check
        command = list(command)
        commands.append(command)
        stdout = b""
        if command[:3] == ["openssl", "rand", "-hex"]:
            stdout = b"keychain-password\n"
        elif command[:3] == ["security", "create-keychain", "-p"]:
            keychain_path.write_bytes(b"keychain")
        elif command[:2] == ["security", "find-certificate"]:
            stdout = certificate_listing.encode()
        elif command[:2] == ["security", "delete-keychain"]:
            keychain_path.unlink(missing_ok=True)
        return subprocess.CompletedProcess(command, 0, stdout, b"")

    monkeypatch.setattr(module, "inspect_and_pin_certificate", fake_inspect)
    monkeypatch.setattr(module, "_run", fake_run)

    with pytest.raises(RuntimeError, match="not unique"):
        module.prepare_identity(
            p12_path=p12_path,
            keychain_path=keychain_path,
            public_certificate_path=certificate_path,
            sentinel_path=sentinel_path,
            state_path=state_path,
            cleanup_report_path=report_path,
            password_environment_name="TEST_PASSWORD",
            p12_base64_environment_name="TEST_P12",
            expected_sha256=sha256,
            expected_sha1=sha1,
            expected_common_name=module.DEFAULT_COMMON_NAME,
            github_output_path=None,
        )

    report = module._read_json(report_path)
    assert report["cleanup_confirmed"] is True
    assert report["original_keychains_restored"] is True
    assert report["ephemeral_keychain_removed"] is True
    assert report["temporary_material_removed"] is True
    restore_command = [
        "security",
        "list-keychains",
        "-d",
        "user",
        "-s",
        *original_keychains,
    ]
    assert restore_command in commands
    assert not any(command[:2] == ["codesign", "--force"] for command in commands)
    assert not p12_path.exists()
    assert not certificate_path.exists()
    assert not sentinel_path.exists()
    assert not keychain_path.exists()
    assert not state_path.exists()


@pytest.mark.parametrize("encoded", ["", "not-base64!"])
def test_prepare_rejects_missing_or_invalid_base64_and_confirms_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    encoded: str,
) -> None:
    module = load_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("P12", encoded)
    monkeypatch.setenv("PASSWORD", "password")
    monkeypatch.setattr(module, "_current_keychains", lambda: ["login"])
    monkeypatch.setattr(
        module,
        "cleanup_identity",
        lambda **kwargs: {"cleanup_confirmed": True},
    )

    with pytest.raises(ValueError, match="base64"):
        module.prepare_identity(
            p12_path=tmp_path / "identity.p12",
            keychain_path=tmp_path / "keychain",
            public_certificate_path=tmp_path / "certificate.pem",
            sentinel_path=tmp_path / "sentinel",
            state_path=tmp_path / "state.json",
            cleanup_report_path=tmp_path / "cleanup.json",
            password_environment_name="PASSWORD",
            p12_base64_environment_name="P12",
            expected_sha256="a" * 64,
            expected_sha1="b" * 40,
            expected_common_name=module.DEFAULT_COMMON_NAME,
            github_output_path=None,
        )


def test_prepare_rejects_empty_decoded_p12_and_unconfirmed_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("P12", "encoded")
    monkeypatch.setenv("PASSWORD", "password")
    monkeypatch.setattr(module, "_current_keychains", lambda: ["login"])
    monkeypatch.setattr(module.base64, "b64decode", lambda *args, **kwargs: b"")
    monkeypatch.setattr(
        module,
        "cleanup_identity",
        lambda **kwargs: {"cleanup_confirmed": False},
    )

    with pytest.raises(RuntimeError, match="cleanup was not confirmed"):
        module.prepare_identity(
            p12_path=tmp_path / "identity.p12",
            keychain_path=tmp_path / "keychain",
            public_certificate_path=tmp_path / "certificate.pem",
            sentinel_path=tmp_path / "sentinel",
            state_path=tmp_path / "state.json",
            cleanup_report_path=tmp_path / "cleanup.json",
            password_environment_name="PASSWORD",
            p12_base64_environment_name="P12",
            expected_sha256="a" * 64,
            expected_sha1="b" * 40,
            expected_common_name=module.DEFAULT_COMMON_NAME,
            github_output_path=None,
        )


def test_prepare_refuses_to_overwrite_lifecycle_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    keychain = tmp_path / "existing.keychain"
    keychain.write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="overwrite"):
        module.prepare_identity(
            p12_path=tmp_path / "identity.p12",
            keychain_path=keychain,
            public_certificate_path=tmp_path / "certificate.pem",
            sentinel_path=tmp_path / "sentinel",
            state_path=tmp_path / "state.json",
            cleanup_report_path=tmp_path / "cleanup.json",
            password_environment_name="PASSWORD",
            p12_base64_environment_name=None,
            expected_sha256="a" * 64,
            expected_sha1="b" * 40,
            expected_common_name=module.DEFAULT_COMMON_NAME,
            github_output_path=None,
        )


def test_cleanup_reports_residual_keychain_search_list_and_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    keychain = tmp_path / "keychain"
    keychain.write_bytes(b"keychain")
    material_directory = tmp_path / "material-directory"
    material_directory.mkdir()
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "report.json"
    module._write_json(
        state_path,
        {
            "schema_version": module.STATE_SCHEMA_VERSION,
            "apple_trust_mutated": False,
            "public_certificate_path": str(tmp_path / "missing-certificate.pem"),
            "keychain_path": str(keychain),
            "original_keychains": ["original"],
            "search_list_change_attempted": True,
            "keychain_create_attempted": True,
            "material_paths": [str(material_directory)],
        },
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, b"", b""),
    )
    monkeypatch.setattr(module, "_current_keychains", lambda: ["different"])

    report = module.cleanup_identity(state_path=state_path, report_path=report_path)

    assert report["cleanup_confirmed"] is False
    assert report["apple_trust_mutated"] is False
    assert any("search list" in error for error in report["errors"])
    assert any("keychain remains" in error for error in report["errors"])
    assert any("material removal failed" in error for error in report["errors"])
    assert any("identity material remains" in error for error in report["errors"])


def test_cleanup_rejects_state_that_claims_apple_trust_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    certificate = tmp_path / "certificate.pem"
    certificate.write_text("certificate", encoding="utf-8")
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "report.json"
    module._write_json(
        state_path,
        {
            "schema_version": module.STATE_SCHEMA_VERSION,
            "apple_trust_mutated": True,
            "public_certificate_path": str(certificate),
            "keychain_path": str(tmp_path / "keychain"),
            "original_keychains": ["original"],
            "material_paths": [str(certificate)],
        },
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(
        module,
        "_run",
        fake_run,
    )
    monkeypatch.setattr(module, "_current_keychains", lambda: ["original"])

    report = module.cleanup_identity(state_path=state_path, report_path=report_path)

    assert report["cleanup_confirmed"] is False
    assert report["apple_trust_mutated"] is True
    assert (
        "identity lifecycle state does not prove Apple trust remained unchanged"
        in report["errors"]
    )
    assert not any("sudo" in command for command in commands)
    assert not any("trusted-cert" in argument for command in commands for argument in command)


@pytest.mark.parametrize("schema_version", [1, 999])
def test_cleanup_rejects_unsupported_state_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schema_version: int,
) -> None:
    module = load_module()
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "report.json"
    module._write_json(
        state_path,
        {
            "schema_version": schema_version,
            "apple_trust_mutated": False,
            "keychain_path": str(tmp_path / "keychain"),
            "original_keychains": ["original"],
            "material_paths": [],
        },
    )
    monkeypatch.setattr(module, "_current_keychains", lambda: ["original"])

    report = module.cleanup_identity(state_path=state_path, report_path=report_path)

    assert report["cleanup_confirmed"] is False
    assert "identity lifecycle state schema is unsupported" in report["errors"]
    assert state_path.is_file()


def test_state_and_current_keychain_readers_validate_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    state = tmp_path / "state.json"
    state.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        module._read_json(state)

    monkeypatch.setattr(module, "_output", lambda command: '"login" "release"')
    assert module._current_keychains() == ["login", "release"]


def test_identity_main_forwards_prepare_and_cleanup_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    prepared: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "prepare_identity",
        lambda **kwargs: prepared.update(kwargs) or {"status": "prepared"},
    )
    common = [
        "--p12", str(tmp_path / "identity.p12"),
        "--keychain", str(tmp_path / "keychain"),
        "--public-certificate", str(tmp_path / "certificate.pem"),
        "--sentinel", str(tmp_path / "sentinel"),
        "--state", str(tmp_path / "state.json"),
        "--cleanup-report", str(tmp_path / "cleanup.json"),
        "--password-env", "PASSWORD",
        "--p12-base64-env", "P12",
        "--expected-sha256", "a" * 64,
        "--expected-sha1", "b" * 40,
        "--github-output", str(tmp_path / "github-output.txt"),
    ]
    assert module.main(["prepare", *common]) == 0
    assert prepared["p12_base64_environment_name"] == "P12"

    monkeypatch.setattr(
        module,
        "cleanup_identity",
        lambda **kwargs: {"cleanup_confirmed": False},
    )
    assert module.main(
        [
            "cleanup",
            "--state",
            str(tmp_path / "state.json"),
            "--report",
            str(tmp_path / "report.json"),
        ]
    ) == 1
