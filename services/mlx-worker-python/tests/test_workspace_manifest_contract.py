from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from packages.protocol.python.workspace.v1 import workspace_manifest_pb2
from worker.productization.workspace_manifest import (
    REQUIRED_WORKSPACE_ARTIFACT_TYPES,
    validate_workspace_manifest_file,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import workspace_manifest_metrics_report

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json"
)


def test_fixture_workspace_manifest_validates_and_reports_machine_readable_summary() -> None:
    report = validate_workspace_manifest_file(FIXTURE)

    assert report.ok is True
    assert report.schema_version == "melix.workspace_manifest.v1"
    assert report.redaction_policy_id == "workspace-local-redacted-v1"
    assert (
        report.redaction_mode
        == workspace_manifest_pb2.REDACTION_MODE_LOCAL_PATHS_AND_SECRETS
    )
    assert report.fixture_count == 1
    assert report.schema_error_count == 0
    assert report.manifest_byte_size == FIXTURE.stat().st_size
    assert report.manifest_validation_latency_ms >= 0


def test_fixture_workspace_manifest_represents_required_artifact_types() -> None:
    manifest, report = validate_workspace_manifest_file(FIXTURE, return_manifest=True)

    assert report.ok is True
    assert {artifact.artifact_type for artifact in manifest.artifacts} == {
        workspace_manifest_pb2.WorkspaceArtifactType.Value(name)
        for name in REQUIRED_WORKSPACE_ARTIFACT_TYPES
    }


def test_metrics_report_keeps_zero_schema_error_count_machine_readable() -> None:
    report = workspace_manifest_metrics_report.build_report(FIXTURE)

    assert report["schema_error_count"] == 0
    assert report["fixture_count"] == 1
    assert report["redaction_policy_id"] == "workspace-local-redacted-v1"


@pytest.mark.parametrize(
    "relative_path",
    [
        "../secret.txt",
        "..\\secret.txt",
        "C:\\secret.txt",
        "\\\\server\\share\\secret.txt",
        "/tmp/secret.txt",
        "raw//secret.txt",
        "raw/../secret.txt",
        "raw\\..\\secret.txt",
    ],
)
def test_workspace_manifest_rejects_unsafe_artifact_relative_paths(
    tmp_path: Path,
    relative_path: str,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        lambda manifest: manifest["artifacts"][0].__setitem__("relative_path", relative_path),
    )

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any("relative_path" in error and "safe relative path" in error for error in report.errors)


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("kind", "ARTIFACT_ROOT_KIND_UNSPECIFIED", "kind must be specified"),
        ("path", "", "path or uri is required"),
        ("path", "/tmp/workspace", "path must be a safe relative path"),
        ("path", "../workspace", "path must be a safe relative path"),
    ],
)
def test_workspace_manifest_rejects_invalid_artifact_roots(
    tmp_path: Path,
    field: str,
    value: str,
    expected_error: str,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        root = manifest["artifact_roots"][0]
        assert isinstance(root, dict)
        if field == "path":
            for artifact_root in manifest["artifact_roots"]:
                assert isinstance(artifact_root, dict)
                artifact_root["uri"] = ""
            root[field] = value
        else:
            root[field] = value

    manifest_path = _write_manifest(tmp_path, mutate)

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any(expected_error in error for error in report.errors)


def test_workspace_manifest_reports_malformed_json(tmp_path: Path) -> None:
    manifest_path = tmp_path / "workspace-manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert report.schema_error_count == 1
    assert report.errors[0].startswith("parse_error:")


def test_workspace_manifest_rejects_wrong_schema_version(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        lambda manifest: manifest.__setitem__("schema_version", "melix.workspace_manifest.v0"),
    )

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any("schema_version must be melix.workspace_manifest.v1" in error for error in report.errors)


def test_workspace_manifest_rejects_duplicate_ids(tmp_path: Path) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        artifacts = manifest["artifacts"]
        roots = manifest["artifact_roots"]
        provenance = manifest["provenance"]
        assert isinstance(artifacts, list)
        assert isinstance(roots, list)
        assert isinstance(provenance, list)
        artifacts[1]["artifact_id"] = artifacts[0]["artifact_id"]
        roots[1]["root_id"] = roots[0]["root_id"]
        provenance[1]["provenance_ref_id"] = provenance[0]["provenance_ref_id"]

    manifest_path = _write_manifest(tmp_path, mutate)

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any("duplicate artifact_id" in error for error in report.errors)
    assert any("artifact_roots.root_id values must be non-empty and unique" in error for error in report.errors)
    assert any("provenance.provenance_ref_id values must be non-empty and unique" in error for error in report.errors)


def test_workspace_manifest_rejects_unknown_provenance_refs(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        lambda manifest: manifest["artifacts"][0].__setitem__(
            "provenance_ref_ids",
            ["missing-provenance"],
        ),
    )

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any("references unknown provenance 'missing-provenance'" in error for error in report.errors)


def test_workspace_manifest_rejects_missing_required_artifact_types(tmp_path: Path) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, list)
        manifest["artifacts"] = [
            artifact
            for artifact in artifacts
            if artifact["artifact_type"] != "WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE"
        ]

    manifest_path = _write_manifest(tmp_path, mutate)

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any(
        "missing required artifact_type: WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE" in error
        for error in report.errors
    )


def test_metrics_cli_returns_nonzero_for_invalid_manifest(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        lambda manifest: manifest.__setitem__("schema_version", "melix.workspace_manifest.v0"),
    )

    assert workspace_manifest_metrics_report.main(["--manifest", str(manifest_path)]) == 1


def test_metrics_cli_writes_machine_readable_output(tmp_path: Path) -> None:
    output_path = tmp_path / "metrics/workspace-manifest-validation.json"

    assert workspace_manifest_metrics_report.main(
        ["--manifest", str(FIXTURE), "--output", str(output_path)]
    ) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["schema_version"] == "melix.workspace_manifest.v1"
    assert payload["schema_error_count"] == 0


def test_workspace_manifest_rejects_missing_top_level_required_fields(tmp_path: Path) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        manifest["project"] = {}
        manifest["artifact_roots"] = []
        manifest["artifacts"] = []
        manifest["redaction_policy"] = {}

    manifest_path = _write_manifest(tmp_path, mutate)

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert "project.project_id is required" in report.errors
    assert "artifact_roots must not be empty" in report.errors
    assert "artifacts must not be empty" in report.errors
    assert "redaction_policy.policy_id is required" in report.errors
    assert "redaction_policy.mode must be specified" in report.errors


def test_workspace_manifest_rejects_invalid_artifact_required_fields(tmp_path: Path) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        artifact = manifest["artifacts"][0]
        assert isinstance(artifact, dict)
        artifact["artifact_id"] = ""
        artifact["artifact_type"] = "WORKSPACE_ARTIFACT_TYPE_UNSPECIFIED"
        artifact["root_id"] = "missing-root"
        artifact["relative_path"] = ""

    manifest_path = _write_manifest(tmp_path, mutate)

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert "artifacts.artifact_id is required" in report.errors
    assert any("has unspecified artifact_type" in error for error in report.errors)
    assert any("references unknown root_id 'missing-root'" in error for error in report.errors)
    assert any("relative_path is required" in error for error in report.errors)


@pytest.mark.parametrize(
    "relative_path",
    [
        " raw/dialogues.jsonl",
        "raw/dialogues.jsonl ",
        ".",
    ],
)
def test_workspace_manifest_rejects_artifact_path_boundary_cases(
    tmp_path: Path,
    relative_path: str,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        lambda manifest: manifest["artifacts"][0].__setitem__("relative_path", relative_path),
    )

    report = validate_workspace_manifest_file(manifest_path)

    assert report.ok is False
    assert any("relative_path must be a safe relative path" in error for error in report.errors)


def test_proto_gen_rewrites_workspace_python_imports() -> None:
    proto_gen = (ROOT / "scripts/proto_gen.sh").read_text(encoding="utf-8")

    assert (
        '"from workspace.v1 import ": '
        '"from packages.protocol.python.workspace.v1 import "'
    ) in proto_gen


def _write_manifest(tmp_path: Path, mutate: object) -> Path:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path = tmp_path / "workspace-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path
