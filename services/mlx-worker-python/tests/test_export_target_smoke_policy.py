from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys

from google.protobuf import json_format
import pytest
from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
import worker.productization.export_target_smoke as export_target_smoke
from worker.productization.export_target_layout import materialize_export_target_layout
from worker.productization.export_target_manifest import validate_export_target_manifest_file
from worker.productization.export_target_smoke import run_export_target_smoke


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/runtime-export/target-manifests.dev.v1"
)


def test_export_target_smoke_writes_receipt_preview_and_verified_report(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "melix_managed/export-target-manifest.json"
    export_report = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )
    target_root = tmp_path / str(export_report["target_root"])
    manifest, validation_report = validate_export_target_manifest_file(
        target_root / "export-target-manifest.json",
        return_manifest=True,
    )
    assert validation_report.ok is True
    _write_declared_file_payloads(target_root, manifest)

    receipt = run_export_target_smoke(
        target_root / "export-target-manifest.json",
        tmp_path,
    )

    receipt_path = target_root / "smoke/smoke-receipt.json"
    preview_path = target_root / "smoke/generation-preview.txt"
    updated_report = json.loads((target_root / "export-report.json").read_text(encoding="utf-8"))

    assert receipt["schema_version"] == "melix.export_smoke_receipt.v1"
    assert receipt["status"] == "passed"
    assert receipt["metadata_check"]["status"] == "passed"
    assert receipt["load_check"]["status"] == "passed"
    assert receipt["generation_check"]["status"] == "passed"
    assert receipt["output_preview"]["path"] == "smoke/generation-preview.txt"
    assert receipt["output_preview"]["byte_count"] <= 4096
    assert receipt["metrics"]["generation_smoke_latency_ms"] >= 0
    assert receipt_path.is_file()
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert preview_path.read_text(encoding="utf-8")
    assert updated_report["smoke_receipt_path"] == "smoke/smoke-receipt.json"
    assert updated_report["verification_terminal_state"] == "verified"
    assert updated_report["ok"] is True


def test_export_target_smoke_blocks_report_when_required_file_is_missing(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    export_report = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )
    target_root = tmp_path / str(export_report["target_root"])
    manifest, validation_report = validate_export_target_manifest_file(
        target_root / "export-target-manifest.json",
        return_manifest=True,
    )
    assert validation_report.ok is True
    _write_declared_file_payloads(target_root, manifest)
    (target_root / "artifacts/blobs/sha256-777777").unlink()

    receipt = run_export_target_smoke(
        target_root / "export-target-manifest.json",
        tmp_path,
    )

    updated_report = json.loads((target_root / "export-report.json").read_text(encoding="utf-8"))
    diagnostics_receipt = json.loads(
        (target_root / "diagnostics/diagnostics-receipt.json").read_text(encoding="utf-8")
    )
    diagnostics_excerpt = (target_root / "diagnostics/redacted-log-excerpt.txt").read_text(
        encoding="utf-8"
    )

    assert receipt["status"] == "failed"
    assert receipt["metadata_check"]["status"] == "failed"
    assert receipt["metadata_check"]["failure_code"] == "missing_required_file"
    assert receipt["operator_failures"][0]["diagnostics_receipt_path"] == "diagnostics/diagnostics-receipt.json"
    assert receipt["diagnostics_status"] == "matched"
    assert receipt["diagnostic_codes"] == ["missing_blob"]
    assert receipt["operator_remedies"][0]["code"] == "missing_blob"
    assert diagnostics_receipt["diagnoses"][0]["code"] == "missing_blob"
    assert diagnostics_receipt["bounded_log_excerpt_path"] == "diagnostics/redacted-log-excerpt.txt"
    assert str(tmp_path) not in json.dumps(diagnostics_receipt, sort_keys=True)
    assert str(tmp_path) not in diagnostics_excerpt
    assert updated_report["verification_terminal_state"] == "blocked"
    assert updated_report["verification_blocker_code"] == "missing_required_file"
    assert updated_report["diagnostic_codes"] == ["missing_blob"]
    assert updated_report["operator_remedies"][0]["code"] == "missing_blob"
    assert updated_report["ok"] is False


def test_export_target_smoke_records_runtime_unavailable_waiver(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    export_report = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )
    target_root = tmp_path / str(export_report["target_root"])
    manifest, validation_report = validate_export_target_manifest_file(
        target_root / "export-target-manifest.json",
        return_manifest=True,
    )
    assert validation_report.ok is True
    _write_declared_file_payloads(target_root, manifest)

    receipt = run_export_target_smoke(
        target_root / "export-target-manifest.json",
        tmp_path,
        available_runtime_binaries=set(),
        operator_id="ci-smoke",
    )

    updated_report = json.loads((target_root / "export-report.json").read_text(encoding="utf-8"))

    assert receipt["status"] == "waived"
    assert receipt["load_check"]["status"] == "waived"
    assert receipt["load_check"]["failure_code"] == "runtime_not_installed"
    assert receipt["metrics"]["waiver_count"] == 1
    assert updated_report["verification_terminal_state"] == "waived"
    assert updated_report["waiver_id"]
    assert updated_report["ok"] is True


def test_export_target_smoke_bounds_generation_preview_and_omits_host_paths(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "mlx_runtime/export-target-manifest.json"
    export_report = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )
    target_root = tmp_path / str(export_report["target_root"])
    manifest, validation_report = validate_export_target_manifest_file(
        target_root / "export-target-manifest.json",
        return_manifest=True,
    )
    assert validation_report.ok is True
    manifest.verification_policy.preview_byte_limit = 32
    _write_declared_file_payloads(target_root, manifest)

    receipt = run_export_target_smoke(
        target_root / "export-target-manifest.json",
        tmp_path,
        available_runtime_binaries={"mlx_lm.generate"},
    )

    preview_text = (target_root / "smoke/generation-preview.txt").read_text(encoding="utf-8")

    assert receipt["output_preview"]["path"] == "smoke/generation-preview.txt"
    assert receipt["output_preview"]["byte_count"] == 32
    assert receipt["output_preview"]["truncated"] is True
    assert str(tmp_path) not in preview_text
    assert "prompt=" not in preview_text


def test_export_target_smoke_metrics_report_covers_all_fixtures(tmp_path: Path) -> None:
    from worker.productization.export_target_smoke import build_smoke_metrics_report

    payload = build_smoke_metrics_report(
        sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json")),
        tmp_path,
    )

    assert payload["ok"] is True
    assert payload["target_count"] == 4
    assert payload["metadata_check_latency_ms"] >= 0
    assert payload["load_smoke_latency_ms"] >= 0
    assert payload["generation_smoke_latency_ms"] >= 0
    assert payload["output_preview_byte_count"] > 0
    assert payload["timeout_count"] == 0
    assert payload["waiver_count"] == 0


def test_runtime_export_smoke_policy_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS", "1")
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_SAMPLES", "1")

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(ROOT / "scripts/runtime_export_smoke_policy_probe.py"),
            run_name="__main__",
        )

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["target_count"] == 4.0
    assert metrics["elapsed_ms_mean"] > 0
    assert metrics["load_smoke_latency_ms"] >= 0
    assert metrics["generation_smoke_latency_ms"] >= 0
    assert metrics["output_preview_byte_count"] > 0
    assert metrics["timeout_count"] == 0.0
    assert metrics["waiver_count"] == 0.0


def test_export_target_smoke_failure_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_manifest_path = tmp_path / "bad-export-target-manifest.json"
    bad_manifest_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="export target manifest failed validation"):
        run_export_target_smoke(bad_manifest_path, tmp_path)

    metrics_report = export_target_smoke.build_smoke_metrics_report(
        [bad_manifest_path],
        tmp_path,
    )
    assert metrics_report["ok"] is False
    assert metrics_report["errors"]

    mismatch_root, mismatch_manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "melix_managed/export-target-manifest.json",
    )
    _write_declared_file_payloads(mismatch_root, mismatch_manifest)
    (mismatch_root / "artifacts/adapter/adapter.safetensors").write_bytes(
        b"corrupted payload"
    )

    mismatch_receipt = run_export_target_smoke(
        mismatch_root / "export-target-manifest.json",
        tmp_path,
    )
    assert mismatch_receipt["metadata_check"]["failure_code"] == "digest_mismatch"

    zero_preview_root, zero_preview_manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "melix_managed/export-target-manifest.json",
    )
    zero_preview_manifest.verification_policy.preview_byte_limit = 0
    _write_declared_file_payloads(zero_preview_root, zero_preview_manifest)

    zero_preview_receipt = run_export_target_smoke(
        zero_preview_root / "export-target-manifest.json",
        tmp_path,
    )
    assert zero_preview_receipt["output_preview"]["byte_count"] == 0
    assert (zero_preview_root / "smoke/generation-preview.txt").read_text(
        encoding="utf-8"
    ) == ""

    missing_runtime_name_root, missing_runtime_name_manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "mlx_runtime/export-target-manifest.json",
    )
    missing_runtime_name_manifest.runtime_requirements.runtime_name = ""

    with pytest.raises(RuntimeError, match="runtime requirement is missing runtime_name"):
        export_target_smoke._check_runtime_preflight(
            missing_runtime_name_manifest,
            available_runtime_binaries={"mlx_lm.generate"},
        )

    missing_binary_root, missing_binary_manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "mlx_runtime/export-target-manifest.json",
    )
    missing_binary_manifest.runtime_requirements.runtime_binary_name = ""

    with pytest.raises(
        RuntimeError,
        match="runtime binary is required but runtime_binary_name is empty",
    ):
        export_target_smoke._check_runtime_preflight(
            missing_binary_manifest,
            available_runtime_binaries=set(),
        )

    non_waivable_runtime_root, non_waivable_runtime_manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    non_waivable_runtime_manifest.verification_policy.waiver_allowed = False
    _write_declared_file_payloads(
        non_waivable_runtime_root,
        non_waivable_runtime_manifest,
    )

    non_waivable_runtime_receipt = run_export_target_smoke(
        non_waivable_runtime_root / "export-target-manifest.json",
        tmp_path,
        available_runtime_binaries=set(),
    )
    assert non_waivable_runtime_receipt["load_check"]["failure_code"] == "runtime_not_installed"
    assert non_waivable_runtime_receipt["diagnostic_codes"] == ["missing_binary"]
    assert non_waivable_runtime_receipt["waiver"] == {}

    perf_counter_values = iter((0.0, 0.02))
    monkeypatch.setattr(
        export_target_smoke.time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )
    timeout_result = export_target_smoke._run_measured_check(
        timeout_ms=1,
        diagnostics_receipt_path="diagnostics/diagnostics-receipt.json",
        evidence_path="smoke/smoke-receipt.json",
        now=0.0,
        check=lambda: None,
    )
    assert timeout_result.failure_code == "runtime_timeout"

    blocked_result = export_target_smoke._CheckResult(
        status=export_target_smoke.CHECK_STATUS_BLOCKED,
        started_at="1970-01-01T00:00:00Z",
        ended_at="1970-01-01T00:00:00Z",
        duration_ms=0.0,
        timeout_ms=1,
        failure_code="",
        failure_message="",
        evidence_path="",
        diagnostics_receipt_path="",
    )
    assert export_target_smoke._terminal_status((blocked_result,)) == "blocked"
    assert export_target_smoke._waiver_id({"waiver": []}) == ""
    assert export_target_smoke._diagnostic_codes({"diagnoses": "invalid"}) == []
    assert export_target_smoke._diagnostic_codes(
        {"diagnoses": ["invalid", {"code": "missing_blob"}, {"code": "missing_blob"}]}
    ) == ["missing_blob"]
    assert export_target_smoke._operator_remedies({"operator_remedies": "invalid"}) == []


def test_runtime_export_smoke_policy_probe_failure_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_script = _load_runtime_export_smoke_policy_probe()

    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS", "not-an-int")
    assert probe_script._env_int(
        "MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS",
        7,
        1,
    ) == 7

    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS", "-4")
    assert probe_script._env_int(
        "MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS",
        7,
        1,
    ) == 1

    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_ITERATIONS", "1")
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_SMOKE_PROBE_SAMPLES", "1")
    monkeypatch.setattr(probe_script, "FIXTURE_ROOT", tmp_path)
    monkeypatch.setattr(
        probe_script,
        "build_smoke_metrics_report",
        lambda manifests, workspace_root: {"ok": False},
    )

    with pytest.raises(SystemExit, match="export smoke policy probe failed"):
        probe_script.main()


def _load_runtime_export_smoke_policy_probe():
    script_path = ROOT / "scripts/runtime_export_smoke_policy_probe.py"
    spec = importlib.util.spec_from_file_location(
        "runtime_export_smoke_policy_probe_test_module",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialized_manifest(
    workspace_root: Path,
    manifest_path: Path,
) -> tuple[Path, export_target_manifest_pb2.ExportTargetManifest]:
    export_report = materialize_export_target_layout(
        manifest_path,
        workspace_root,
        create_placeholder_files=True,
    )
    target_root = workspace_root / str(export_report["target_root"])
    manifest, validation_report = validate_export_target_manifest_file(
        target_root / "export-target-manifest.json",
        return_manifest=True,
    )
    assert validation_report.ok is True
    return target_root, manifest


def _write_declared_file_payloads(
    target_root: Path,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
) -> None:
    for row in (*manifest.generated_files, *manifest.required_files):
        if row.path == "export-target-manifest.json":
            continue
        path = target_root / row.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"smoke fixture payload for {row.path}\n".encode("utf-8")
        path.write_bytes(payload)
        row.sha256 = hashlib.sha256(payload).hexdigest()
    (target_root / "export-target-manifest.json").write_text(
        json_format.MessageToJson(
            manifest,
            preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True,
        ),
        encoding="utf-8",
    )
