from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
from collections.abc import Callable

import pytest

from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
from worker.productization.export_target_manifest import (
    REQUIRED_EXPORT_TARGET_TYPES,
    _contains_parent_path_component,
    _safe_relative_path_error,
    _validate_metrics,
    validate_export_target_manifest_file,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_target_manifest_metrics_report

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/runtime-export/target-manifests.dev.v1"
)


def _fixture_paths() -> list[Path]:
    return sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json"))


def test_export_target_manifest_fixtures_cover_all_target_types() -> None:
    manifests = []
    reports = []
    for path in _fixture_paths():
        manifest, report = validate_export_target_manifest_file(
            path,
            fixture_count=4,
            return_manifest=True,
        )
        manifests.append(manifest)
        reports.append(report)

    assert {report.ok for report in reports} == {True}
    assert {report.schema_error_count for report in reports} == {0}
    assert {report.fixture_count for report in reports} == {4}
    assert {manifest.target_type for manifest in manifests} == {
        export_target_manifest_pb2.ExportTargetType.Value(name)
        for name in REQUIRED_EXPORT_TARGET_TYPES
    }


def test_export_target_manifest_fixture_reports_machine_readable_metrics() -> None:
    path = FIXTURE_ROOT / "melix_managed/export-target-manifest.json"

    report = validate_export_target_manifest_file(path)

    assert report.ok is True
    assert report.schema_version == "melix.export_target_manifest.v1"
    assert report.target_id == "support-chat-melix-managed"
    assert report.target_type == export_target_manifest_pb2.EXPORT_TARGET_TYPE_MELIX_MANAGED
    assert report.manifest_byte_size == path.stat().st_size
    assert report.manifest_validation_latency_ms >= 0
    assert report.generated_file_count == 2
    assert report.required_file_count == 1
    assert report.intermediate_file_count == 1


def test_export_target_manifest_reuses_read_bytes_for_manifest_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = FIXTURE_ROOT / "melix_managed/export-target-manifest.json"
    expected_size = len(path.read_bytes())

    def fail_manifest_stat(self: Path, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("manifest validation should not stat after reading bytes")

    monkeypatch.setattr(Path, "stat", fail_manifest_stat)

    report = validate_export_target_manifest_file(path)

    with pytest.raises(AssertionError):
        path.stat()

    assert report.ok is True
    assert report.manifest_byte_size == expected_size


def test_export_target_manifest_metrics_cli_aggregates_fixture_set(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "metrics/export-target-manifest-validation.json"

    assert export_target_manifest_metrics_report.main(["--output", str(output_path)]) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["schema_version"] == "melix.export_target_manifest.metrics.v1"
    assert payload["fixture_count"] == 4
    assert payload["schema_error_count"] == 0
    assert payload["manifest_byte_size"] > 0
    assert {report["target_type"] for report in payload["reports"]} == {
        "EXPORT_TARGET_TYPE_MELIX_MANAGED",
        "EXPORT_TARGET_TYPE_OLLAMA",
        "EXPORT_TARGET_TYPE_GGUF",
        "EXPORT_TARGET_TYPE_MLX_RUNTIME",
    }


def test_export_target_manifest_rejects_missing_target_type(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "melix_managed",
        lambda manifest: manifest.__setitem__(
            "target_type",
            "EXPORT_TARGET_TYPE_UNSPECIFIED",
        ),
    )

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "target_type must be specified" in report.errors


def test_export_target_manifest_reports_required_field_errors(tmp_path: Path) -> None:
    manifest_path = tmp_path / "export-target-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "export_id is required" in report.errors
    assert "target_id is required" in report.errors
    assert "target_runtime is required" in report.errors
    assert "workspace_project_id is required" in report.errors
    assert "workspace_manifest_path is required" in report.errors
    assert "base_model_id is required" in report.errors
    assert "adapter_id is required" in report.errors
    assert "adapter_snapshot is required" in report.errors
    assert "activation_mode must be specified" in report.errors
    assert "generated_files must not be empty" in report.errors
    assert "required_files must not be empty" in report.errors
    assert "runtime_requirements.runtime_name is required" in report.errors
    assert "runtime_requirements.required_capabilities must not be empty" in report.errors
    assert "verification_policy.policy_id is required" in report.errors
    assert "verification_status.state must be specified" in report.errors
    assert "retention_policy.policy_id is required" in report.errors
    assert "evidence.redaction_policy_id is required" in report.errors


def test_export_target_manifest_rejects_unknown_numeric_target_type(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "melix_managed",
        lambda manifest: manifest.__setitem__("target_type", 99),
    )

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert any("target_type must be one of" in error for error in report.errors)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        ("workspace_manifest_path", "../workspace-manifest.json"),
        ("generated_files.0.path", "/tmp/export.bin"),
        ("required_files.0.path", "artifacts\\adapter.json"),
        ("evidence.export_report_path", "reports//export-report.json"),
    ],
)
def test_export_target_manifest_rejects_unsafe_paths(
    tmp_path: Path,
    field_path: str,
    value: str,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        _set_nested(manifest, field_path, value)

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert any("safe relative path" in error for error in report.errors)


@pytest.mark.parametrize(
    ("path_value", "expected"),
    [
        (" artifacts/model.gguf", "leading or trailing whitespace"),
        ("", "path is empty"),
        ("C:/Models/model.gguf", "Windows absolute"),
        (".", "current-directory paths"),
    ],
)
def test_export_target_manifest_safe_relative_path_rejects_invalid_shapes(
    path_value: str,
    expected: str,
) -> None:
    assert expected in str(_safe_relative_path_error(path_value))


def test_export_target_manifest_safe_relative_path_uses_string_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import worker.productization.export_target_manifest as target

    def fail_pure_path(*_args: object, **_kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("safe relative path checks should not allocate PurePath helpers")

    monkeypatch.setattr(target, "PurePosixPath", fail_pure_path)
    monkeypatch.setattr(target, "PureWindowsPath", fail_pure_path)

    assert target._safe_relative_path_error("artifacts/model.gguf") is None
    assert "parent-directory" in str(target._safe_relative_path_error("artifacts/../model.gguf"))
    assert "Windows absolute" in str(target._safe_relative_path_error("C:/Models/model.gguf"))
    assert "absolute" in str(target._safe_relative_path_error("/tmp/export.bin"))


@pytest.mark.parametrize(
    ("path_value", "expected"),
    [
        ("..", True),
        ("../model.gguf", True),
        ("artifacts/..", True),
        ("artifacts/../model.gguf", True),
        ("artifacts/.../model.gguf", False),
        ("artifacts/model..gguf", False),
        ("artifacts/..model/model.gguf", False),
    ],
)
def test_export_target_manifest_parent_path_component_scan_preserves_split_semantics(
    path_value: str,
    expected: bool,
) -> None:
    assert _contains_parent_path_component(path_value) is expected


def test_export_target_manifest_rejects_file_row_contract_violations(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        generated_files = manifest["generated_files"]
        assert isinstance(generated_files, list)
        duplicate = dict(generated_files[0])
        duplicate["path"] = "artifacts/duplicate.bin"
        generated_files[:] = [
            {
                "path": "",
                "role": "EXPORT_TARGET_FILE_ROLE_UNSPECIFIED",
                "media_type": "",
                "byte_size": 1,
                "sha256": "",
                "retention_class": "EXPORT_RETENTION_CLASS_UNSPECIFIED",
                "source_provenance": "",
                "redaction_class": "EXPORT_REDACTION_CLASS_UNSPECIFIED",
            },
            duplicate,
            dict(duplicate),
        ]

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "generated_files[0].path is required" in report.errors
    assert "generated_files[0].role must be specified" in report.errors
    assert "generated_files[0].media_type is required" in report.errors
    assert "generated_files[0].sha256 is required" in report.errors
    assert "generated_files[0].retention_class must be specified" in report.errors
    assert "generated_files[0].source_provenance is required" in report.errors
    assert "generated_files[0].redaction_class must be specified" in report.errors
    assert any("duplicates another file row" in error for error in report.errors)


def test_export_target_manifest_rejects_duplicate_paths_across_file_sections(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        generated_files = manifest["generated_files"]
        required_files = manifest["required_files"]
        intermediate_files = manifest["intermediate_files"]
        assert isinstance(generated_files, list)
        assert isinstance(required_files, list)
        assert isinstance(intermediate_files, list)
        required_files[0]["path"] = generated_files[0]["path"]
        intermediate_files[0]["path"] = generated_files[1]["path"]

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert any(
        error.startswith("required_files[0].path duplicates another file row")
        for error in report.errors
    )
    assert any(
        error.startswith("intermediate_files[0].path duplicates another file row")
        for error in report.errors
    )


def test_export_target_manifest_rejects_missing_required_file_digest(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        required_files = manifest["required_files"]
        assert isinstance(required_files, list)
        required_files[0]["sha256"] = ""

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "required_files[0].sha256 is required" in report.errors


def test_export_target_manifest_rejects_unsupported_target_runtime(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        manifest["target_runtime"] = "ollama"
        runtime_requirements = manifest["runtime_requirements"]
        assert isinstance(runtime_requirements, dict)
        runtime_requirements["runtime_name"] = "ollama"

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert any("target_runtime 'ollama' is not allowed" in error for error in report.errors)


def test_export_target_manifest_requires_derived_model_for_activation(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "melix_managed",
        lambda manifest: manifest.__setitem__("source_derived_model_manifest_path", ""),
    )

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "source_derived_model_manifest_path is required for derived model activation modes" in report.errors


def test_export_target_manifest_rejects_runtime_requirement_gaps(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        manifest["target_runtime"] = "ollama"
        runtime_requirements = manifest["runtime_requirements"]
        assert isinstance(runtime_requirements, dict)
        runtime_requirements["runtime_name"] = "melix"
        runtime_requirements["runtime_binary_required"] = True
        runtime_requirements["runtime_binary_name"] = ""
        runtime_requirements["required_capabilities"] = []

    manifest_path = _write_manifest(tmp_path, "ollama", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "runtime_requirements.runtime_name must match target_runtime" in report.errors
    assert "runtime_requirements.runtime_binary_name is required when runtime_binary_required is true" in report.errors
    assert "runtime_requirements.required_capabilities must not be empty" in report.errors


def test_export_target_manifest_requires_runtime_binary_flag_for_local_targets(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        runtime_requirements = manifest["runtime_requirements"]
        assert isinstance(runtime_requirements, dict)
        runtime_requirements["runtime_binary_required"] = False

    manifest_path = _write_manifest(tmp_path, "ollama", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "runtime_requirements.runtime_binary_required is required for this target type" in report.errors


def test_export_target_manifest_rejects_verification_policy_gaps(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        verification_policy = manifest["verification_policy"]
        assert isinstance(verification_policy, dict)
        verification_policy["load_check_required"] = False

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "verification_policy.load_check_required must be true for this target type" in report.errors


def test_export_target_manifest_requires_gguf_runtime_waiver(
    tmp_path: Path,
) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        verification_policy = manifest["verification_policy"]
        assert isinstance(verification_policy, dict)
        verification_policy["allowed_waiver_reasons"] = []

    manifest_path = _write_manifest(tmp_path, "gguf", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "gguf verification_policy must allow runtime_not_installed waivers" in report.errors


def test_export_target_manifest_rejects_unknown_side_channel_fields(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "melix_managed",
        lambda manifest: manifest.__setitem__(
            "ollama_side_channel_state",
            {"model": "support-chat"},
        ),
    )

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert report.schema_error_count == 1
    assert report.errors[0].startswith("parse_error:")
    assert "ollama_side_channel_state" in report.errors[0]


def test_export_target_manifest_rejects_metric_mismatches(tmp_path: Path) -> None:
    def mutate(manifest: dict[str, object]) -> None:
        metrics = manifest["metrics"]
        assert isinstance(metrics, dict)
        metrics["generated_file_count"] = 0
        metrics["required_file_count"] = 0
        metrics["intermediate_file_count"] = 0
        metrics["artifact_byte_size"] = 1
        metrics["required_byte_size"] = 1
        metrics["evidence_byte_size"] = 1

    manifest_path = _write_manifest(tmp_path, "melix_managed", mutate)

    report = validate_export_target_manifest_file(manifest_path)

    assert report.ok is False
    assert "metrics.generated_file_count must equal generated_files count" in report.errors
    assert "metrics.required_file_count must equal required_files count" in report.errors
    assert "metrics.intermediate_file_count must equal intermediate_files count" in report.errors
    assert "metrics.artifact_byte_size must equal generated_files byte_size sum" in report.errors
    assert "metrics.required_byte_size must equal required_files byte_size sum" in report.errors
    assert "metrics.evidence_byte_size must equal evidence file byte_size sum" in report.errors


def test_export_target_manifest_metrics_evidence_bytes_cover_all_file_sections() -> None:
    evidence = export_target_manifest_pb2.EXPORT_RETENTION_CLASS_EVIDENCE
    manifest = export_target_manifest_pb2.ExportTargetManifest()
    manifest.generated_files.add(byte_size=11, retention_class=evidence)
    manifest.generated_files.add(
        byte_size=13,
        retention_class=export_target_manifest_pb2.EXPORT_RETENTION_CLASS_REQUIRED,
    )
    manifest.required_files.add(byte_size=17, retention_class=evidence)
    manifest.required_files.add(
        byte_size=19,
        retention_class=export_target_manifest_pb2.EXPORT_RETENTION_CLASS_REQUIRED,
    )
    manifest.intermediate_files.add(byte_size=23, retention_class=evidence)
    manifest.intermediate_files.add(
        byte_size=29,
        retention_class=export_target_manifest_pb2.EXPORT_RETENTION_CLASS_CACHE,
    )
    manifest.metrics.generated_file_count = 2
    manifest.metrics.required_file_count = 2
    manifest.metrics.intermediate_file_count = 2
    manifest.metrics.artifact_byte_size = 24
    manifest.metrics.required_byte_size = 36
    manifest.metrics.evidence_byte_size = 51

    assert _validate_metrics(manifest) == []

    manifest.metrics.evidence_byte_size = 50

    assert "metrics.evidence_byte_size must equal evidence file byte_size sum" in _validate_metrics(manifest)


def test_export_target_manifest_metrics_cli_returns_nonzero_for_invalid_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "melix_managed",
        lambda manifest: manifest.__setitem__("schema_version", "melix.export_target_manifest.v0"),
    )

    assert export_target_manifest_metrics_report.main(["--manifest", str(manifest_path)]) == 1


def test_export_target_manifest_metrics_cli_guard_runs_with_explicit_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = FIXTURE_ROOT / "melix_managed/export-target-manifest.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_target_manifest_metrics_report.py", "--manifest", str(manifest_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(ROOT / "scripts/export_target_manifest_metrics_report.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fixture_count"] == 1


def test_runtime_export_manifest_validation_probe_env_int_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_ITERATIONS", "invalid")
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_manifest_validation_probe.py"))

    assert probe_script["_env_int"]("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_ITERATIONS", 250, 1) == 250


def test_runtime_export_manifest_validation_probe_fails_invalid_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_dir = tmp_path / "broken"
    fixture_dir.mkdir()
    manifest_path = fixture_dir / "export-target-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_ITERATIONS", "1")
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_SAMPLES", "1")
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_manifest_validation_probe.py"))
    probe_script["main"].__globals__["FIXTURE_ROOT"] = tmp_path

    with pytest.raises(SystemExit, match="export target manifest fixture failed validation"):
        probe_script["main"]()


def test_runtime_export_manifest_validation_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_ITERATIONS", "2")
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_MANIFEST_PROBE_SAMPLES", "1")
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_manifest_validation_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["fixture_count"] == 4.0
    assert metrics["schema_error_count"] == 0.0
    assert metrics["manifest_byte_size"] > 0
    assert metrics["elapsed_ms_mean"] >= 0


def test_proto_gen_emits_export_target_manifest_schema() -> None:
    proto_gen = (ROOT / "scripts/proto_gen.sh").read_text(encoding="utf-8")

    assert "$SCHEMA_DIR/workspace/v1/export_target_manifest.proto" in proto_gen


def _write_manifest(
    tmp_path: Path,
    target: str,
    mutate: Callable[[dict[str, object]], None],
) -> Path:
    manifest = json.loads(
        (FIXTURE_ROOT / target / "export-target-manifest.json").read_text(encoding="utf-8")
    )
    mutate(manifest)
    manifest_path = tmp_path / "export-target-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _set_nested(payload: dict[str, object], field_path: str, value: object) -> None:
    current: object = payload
    parts = field_path.split(".")
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:  # pragma: no cover - defensive test helper guard
            raise TypeError(f"cannot descend into {type(current)!r}")
    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        current[int(last)] = value
    else:  # pragma: no cover - defensive test helper guard
        raise TypeError(f"cannot set field on {type(current)!r}")
