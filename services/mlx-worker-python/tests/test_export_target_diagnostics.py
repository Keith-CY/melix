from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
from worker.productization import export_target_diagnostics as export_target_diagnostics_module
from worker.productization.export_target_diagnostics import (
    CODE_DUPLICATE_TENSOR_NAME,
    CODE_INSUFFICIENT_MEMORY,
    CODE_INVALID_RUNTIME_PATH,
    CODE_MISSING_BINARY,
    CODE_MISSING_BLOB,
    CODE_PERMISSION_DENIED,
    CODE_RUNTIME_LOAD_FAILED,
    CODE_RUNTIME_TIMEOUT,
    CODE_UNKNOWN_FAILURE,
    CODE_UNSUPPORTED_ARCHITECTURE,
    EXPORT_DIAGNOSTICS_RECEIPT_SCHEMA_VERSION,
    build_diagnostic_metrics_report,
    build_export_diagnostics_receipt,
    write_export_diagnostics_receipt,
    _SourceLine,
    _DiagnosisPattern,
    _build_redacted_excerpt,
    _collect_source_lines,
    _diagnoses_from_excerpt,
    _diagnosis_metric_counts,
    _extend_source_lines,
    _split_source_lines,
)
from worker.productization.export_target_layout import (
    build_export_target_layout,
    materialize_export_target_layout,
)
from worker.productization.export_target_manifest import validate_export_target_manifest_file


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/runtime-export/target-manifests.dev.v1"
)


def test_export_target_diagnostics_source_line_extension_matches_split_helper() -> None:
    lines: list[_SourceLine] = []

    _extend_source_lines(lines, "logs/runtime.log", "first\nsecond\n")

    assert lines == _split_source_lines("logs/runtime.log", "first\nsecond\n")
    assert [line.source_path for line in lines] == ["logs/runtime.log", "logs/runtime.log"]
    assert [line.text for line in lines] == ["first", "second"]

    _extend_source_lines(lines, "logs/empty.log", "")
    assert len(lines) == 2


@pytest.mark.parametrize(
    ("expected_code", "log_line"),
    [
        (CODE_RUNTIME_LOAD_FAILED, "runtime load failed while opening model"),
        (CODE_UNSUPPORTED_ARCHITECTURE, "unsupported architecture arm64 required"),
        (CODE_DUPLICATE_TENSOR_NAME, "duplicate tensor name decoder.layers.0"),
        (CODE_MISSING_BLOB, "missing blob sha256-777777 not found"),
        (CODE_MISSING_BINARY, "runtime binary not installed: ollama"),
        (CODE_INVALID_RUNTIME_PATH, "invalid runtime path /tmp/melix/bad-target"),
        (CODE_RUNTIME_TIMEOUT, "generation smoke timed out after deadline exceeded"),
        (CODE_PERMISSION_DENIED, "permission denied opening model weights"),
        (CODE_INSUFFICIENT_MEMORY, "Metal out of memory during load"),
    ],
)
def test_export_target_diagnostics_parser_matches_common_runtime_failures(
    tmp_path: Path,
    expected_code: str,
    log_line: str,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    (target_root / "logs/ollama-create.log").write_text(log_line + "\n", encoding="utf-8")

    receipt = write_export_diagnostics_receipt(layout, manifest)

    receipt_path = target_root / "diagnostics/diagnostics-receipt.json"
    excerpt_path = target_root / "diagnostics/redacted-log-excerpt.txt"
    assert receipt["schema_version"] == EXPORT_DIAGNOSTICS_RECEIPT_SCHEMA_VERSION
    assert receipt["status"] == "matched"
    assert receipt["diagnoses"][0]["code"] == expected_code
    assert receipt["diagnoses"][0]["evidence_path"].startswith(
        "diagnostics/redacted-log-excerpt.txt#line-"
    )
    assert receipt["operator_remedies"][0]["code"] == expected_code
    assert receipt["metrics"]["parsed_failure_count"] >= 1
    assert receipt_path.is_file()
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert excerpt_path.read_text(encoding="utf-8").startswith("[logs/ollama-create.log]")


def test_export_target_diagnostics_redacts_paths_secrets_private_text_and_identity(
    tmp_path: Path,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    log_text = "\n".join(
        [
            f"failed to load model from {target_root / 'artifacts/blobs/sha256-777777'}",
            "Authorization: Bearer sk-testsecret123456",
            "api_key=super-secret-value",
            "proxy=http://user:secret-proxy-pass@example.test",
            "prompt: private customer prompt that must not leave the log",
            "operator_id=chenyu",
            "certificate -----BEGIN TOKEN-----abc123-----END TOKEN-----",
            "openai key sk-liveexample12345678",
        ]
    )
    (target_root / "logs/ollama-create.log").write_text(log_text + "\n", encoding="utf-8")

    receipt = write_export_diagnostics_receipt(layout, manifest)

    excerpt = (target_root / "diagnostics/redacted-log-excerpt.txt").read_text(
        encoding="utf-8"
    )
    encoded_receipt = json.dumps(receipt, sort_keys=True)
    assert str(target_root) not in excerpt
    assert str(target_root) not in encoded_receipt
    assert "<target>/artifacts/blobs/sha256-777777" in excerpt
    assert "sk-testsecret" not in excerpt
    assert "super-secret-value" not in excerpt
    assert "secret-proxy-pass" not in excerpt
    assert "abc123" not in excerpt
    assert "sk-liveexample12345678" not in excerpt
    assert "private customer prompt" not in excerpt
    assert "chenyu" not in excerpt
    assert receipt["redaction_summary"]["redacted_absolute_path_count"] >= 1
    assert receipt["redaction_summary"]["redacted_secret_count"] >= 3
    assert receipt["redaction_summary"]["redacted_prompt_or_response_count"] == 1
    assert receipt["redaction_summary"]["redacted_identity_count"] >= 1


def test_export_target_diagnostics_resolves_target_root_once_for_many_path_redactions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    source_lines = [
        _SourceLine(
            source_path="logs/ollama-create.log",
            text=f"runtime load failed at {target_root / 'artifacts/model.gguf'}",
        ),
        _SourceLine(
            source_path="logs/ollama-create.log",
            text=f"missing blob at {target_root / 'artifacts/blobs/sha256-777777'}",
        ),
        _SourceLine(
            source_path="logs/ollama-create.log",
            text=f"permission denied at {target_root / 'logs/ollama-create.log'}",
        ),
    ]
    original_resolve = Path.resolve
    target_root_resolves = 0

    def tracking_resolve(path: Path, strict: bool = False) -> Path:
        nonlocal target_root_resolves
        if path == target_root:
            target_root_resolves += 1
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", tracking_resolve)

    excerpt = _build_redacted_excerpt(
        layout,
        source_lines,
        bounded_bytes=4096,
        bounded_lines=20,
    )

    assert target_root_resolves == 1
    assert "<target>/artifacts/model.gguf" in excerpt.text
    assert "<target>/artifacts/blobs/sha256-777777" in excerpt.text
    assert "<target>/logs/ollama-create.log" in excerpt.text


def test_export_target_diagnostics_uses_lexical_target_path_fast_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)

    def fail_path_construction(*_args: object, **_kwargs: object) -> Path:  # pragma: no cover
        raise AssertionError("clean target paths should not allocate fallback Path objects")

    monkeypatch.setattr(export_target_diagnostics_module, "Path", fail_path_construction)

    excerpt = _build_redacted_excerpt(
        layout,
        [
            _SourceLine(
                source_path="logs/ollama-create.log",
                text=f"runtime load failed at {target_root / 'artifacts/model.gguf'}.",
            ),
            _SourceLine(
                source_path="logs/ollama-create.log",
                text=f"missing blob at {target_root / 'artifacts/blobs/sha256-777777'})",
            ),
        ],
        bounded_bytes=4096,
        bounded_lines=20,
    )

    assert "<target>/artifacts/model.gguf." in excerpt.text
    assert "<target>/artifacts/blobs/sha256-777777)" in excerpt.text
    assert excerpt.summary.redacted_absolute_path_count == 2
    assert export_target_diagnostics_module._target_relative_text(
        str(target_root), str(target_root)
    ) == "."
    assert export_target_diagnostics_module._target_relative_text(
        f"{target_root}-sibling/artifact", str(target_root)
    ) is None


def test_export_target_diagnostics_lowercases_source_line_once_per_match_scan() -> None:
    class TrackingText(str):
        lower_calls = 0

        def lower(self) -> str:
            type(self).lower_calls += 1
            return super().lower()

    text = TrackingText("progress line loaded shard metadata without failure")

    diagnoses = _diagnoses_from_excerpt(
        [_SourceLine(source_path="logs/ollama-create.log", text=text)],
        {0: 1},
        "diagnostics/redacted-log-excerpt.txt",
    )

    assert diagnoses == []
    assert text.lower_calls == 1


def test_export_target_diagnostics_runtime_load_markers_skip_progress_regexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_load_pattern = next(
        pattern
        for pattern in export_target_diagnostics_module._DIAGNOSIS_PATTERNS
        if pattern.code == CODE_RUNTIME_LOAD_FAILED
    )
    expressions = tuple(Mock(wraps=expression) for expression in runtime_load_pattern.expressions)
    patched_pattern = _DiagnosisPattern(
        code=runtime_load_pattern.code,
        severity=runtime_load_pattern.severity,
        pattern_id=runtime_load_pattern.pattern_id,
        expressions=expressions,
        operator_message=runtime_load_pattern.operator_message,
        remediation=runtime_load_pattern.remediation,
        markers=runtime_load_pattern.markers,
    )
    monkeypatch.setattr(
        export_target_diagnostics_module,
        "_DIAGNOSIS_PATTERNS",
        (patched_pattern,),
    )

    diagnoses = _diagnoses_from_excerpt(
        [
            _SourceLine(
                source_path="logs/ollama-create.log",
                text="progress line loaded shard metadata without failure",
            ),
            _SourceLine(
                source_path="logs/ollama-create.log",
                text="runtime load failed while opening model",
            ),
        ],
        {0: 1, 1: 2},
        "diagnostics/redacted-log-excerpt.txt",
    )

    assert [diagnosis["code"] for diagnosis in diagnoses] == [CODE_RUNTIME_LOAD_FAILED]
    assert [expression.search.call_count for expression in expressions] == [1, 1, 1, 0, 0]


def test_export_target_diagnostics_skips_secret_regexes_for_plain_path_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)

    class FailingSecretPattern:
        def sub(self, *_args: object, **_kwargs: object) -> str:  # pragma: no cover
            raise AssertionError("secret redaction regex should be skipped")

    for pattern_name in (
        "_CERTIFICATE_PATTERN",
        "_BEARER_SECRET_PATTERN",
        "_NAMED_SECRET_PATTERN",
        "_URL_CREDENTIAL_PATTERN",
        "_OPENAI_KEY_PATTERN",
        "_IDENTITY_PATTERN",
    ):
        monkeypatch.setattr(
            export_target_diagnostics_module,
            pattern_name,
            FailingSecretPattern(),
        )

    excerpt = _build_redacted_excerpt(
        layout,
        [
            _SourceLine(
                source_path="logs/ollama-create.log",
                text=f"runtime load failed at {target_root / 'artifacts/model.gguf'}",
            )
        ],
        bounded_bytes=4096,
        bounded_lines=20,
    )

    assert "<target>/artifacts/model.gguf" in excerpt.text
    assert excerpt.summary.redacted_secret_count == 0


def test_export_target_diagnostics_redaction_uses_unresolved_root_when_root_resolve_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    source_lines = [
        _SourceLine(
            source_path="logs/ollama-create.log",
            text=f"runtime load failed at {target_root / 'artifacts/model.gguf'}",
        )
    ]
    original_resolve = Path.resolve

    def maybe_raising_resolve(path: Path, strict: bool = False) -> Path:
        if path == target_root:
            raise OSError("target root cannot be resolved")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", maybe_raising_resolve)

    excerpt = _build_redacted_excerpt(
        layout,
        source_lines,
        bounded_bytes=4096,
        bounded_lines=20,
    )

    assert "<target>/artifacts/model.gguf" in excerpt.text


def test_export_target_diagnostics_preserves_bounded_unknown_failure_excerpt(
    tmp_path: Path,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "melix_managed/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    manifest.diagnostic_policy.bounded_log_excerpt_bytes = 160

    receipt = write_export_diagnostics_receipt(
        layout,
        manifest,
        failure_checks=[
            {
                "check": "load_check",
                "status": "failed",
                "failure_code": "opaque_runtime_failure",
                "failure_message": "unclassified runtime symptom " + ("detail " * 80),
                "evidence_path": "smoke/smoke-receipt.json",
            }
        ],
    )

    excerpt = (target_root / "diagnostics/redacted-log-excerpt.txt").read_text(
        encoding="utf-8"
    )
    assert receipt["status"] == "unknown"
    assert receipt["diagnoses"][0]["code"] == CODE_UNKNOWN_FAILURE
    assert receipt["bounded_log_excerpt_path"] == "diagnostics/redacted-log-excerpt.txt"
    assert receipt["redaction_summary"]["truncated"] is True
    assert receipt["redaction_summary"]["excerpt_byte_count"] <= 160
    assert excerpt


def test_export_target_diagnostics_reads_only_bounded_log_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    manifest.diagnostic_policy.bounded_log_excerpt_bytes = 64
    log_path = target_root / "logs/ollama-create.log"
    log_path.write_text("runtime load failed " + ("detail " * 2000), encoding="utf-8")
    original_open = Path.open
    read_sizes: list[int] = []

    class _TrackingBytes(io.BytesIO):
        def __enter__(self) -> "_TrackingBytes":
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return super().read(size)

    def tracking_open(path: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        if path == log_path and mode == "rb":
            return _TrackingBytes(original_open(path, mode, *args, **kwargs).read())
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    receipt = write_export_diagnostics_receipt(layout, manifest)

    assert read_sizes == [128]
    assert receipt["status"] == "matched"


def test_export_target_diagnostics_source_collection_skips_duplicates_and_missing_logs(
    tmp_path: Path,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    log_path = "logs/ollama-create.log"
    (target_root / log_path).write_text("runtime load failed\n", encoding="utf-8")
    duplicate_row = manifest.required_files.add()
    duplicate_row.path = log_path
    duplicate_row.role = export_target_manifest_pb2.EXPORT_TARGET_FILE_ROLE_RUNTIME_LOG
    missing_row = manifest.intermediate_files.add()
    missing_row.path = "logs/missing-runtime.log"
    missing_row.role = export_target_manifest_pb2.EXPORT_TARGET_FILE_ROLE_RUNTIME_LOG

    lines = _collect_source_lines(
        layout,
        manifest,
        failure_checks=(),
        bounded_bytes=1024,
    )

    assert [line.source_path for line in lines].count(log_path) == 1
    assert all(line.source_path != "logs/missing-runtime.log" for line in lines)


def test_export_target_diagnostics_falls_back_when_path_resolution_raises_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "ollama/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)
    raw_path = target_root / "artifacts" / ".." / "artifacts/blobs/sha256-777777"
    (target_root / "logs/ollama-create.log").write_text(
        f"runtime load failed while opening {raw_path}\n",
        encoding="utf-8",
    )
    original_resolve = Path.resolve

    def raising_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path == raw_path:
            raise OSError("path cannot be resolved")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", raising_resolve)

    receipt = write_export_diagnostics_receipt(layout, manifest)

    excerpt = (target_root / "diagnostics/redacted-log-excerpt.txt").read_text(
        encoding="utf-8"
    )
    assert receipt["status"] == "matched"
    assert str(raw_path) not in excerpt
    assert "<absolute-path>" in excerpt


def test_export_target_diagnostics_metric_counts_single_pass() -> None:
    parsed_count, unknown_count, matched_codes = _diagnosis_metric_counts(
        [
            {"code": CODE_RUNTIME_LOAD_FAILED},
            {"code": CODE_UNKNOWN_FAILURE},
            {"code": CODE_MISSING_BINARY},
        ]
    )

    assert parsed_count == 2
    assert unknown_count == 1
    assert matched_codes == {CODE_RUNTIME_LOAD_FAILED, CODE_MISSING_BINARY}


def test_export_target_diagnostics_pattern_markers_skip_unrelated_regex() -> None:
    expression = Mock()
    pattern = _DiagnosisPattern(
        code=CODE_MISSING_BLOB,
        severity="error",
        pattern_id="missing-blob-v1",
        expressions=(expression,),
        operator_message="message",
        remediation="remediation",
        markers=("blob",),
    )

    assert pattern.matches("runtime emitted a harmless progress line") is False
    expression.search.assert_not_called()


def test_export_target_diagnostics_pattern_markers_preserve_matching_regex() -> None:
    expression = Mock()
    expression.search.return_value = object()
    pattern = _DiagnosisPattern(
        code=CODE_MISSING_BLOB,
        severity="error",
        pattern_id="missing-blob-v1",
        expressions=(expression,),
        operator_message="message",
        remediation="remediation",
        markers=("blob",),
    )

    assert pattern.matches("missing blob sha256-777777") is True
    expression.search.assert_called_once_with("missing blob sha256-777777")


def test_export_target_diagnostics_pattern_markers_normalize_case() -> None:
    expression = Mock()
    expression.search.return_value = object()
    pattern = _DiagnosisPattern(
        code=CODE_MISSING_BLOB,
        severity="error",
        pattern_id="missing-blob-v1",
        expressions=(expression,),
        operator_message="message",
        remediation="remediation",
        markers=("BLOB",),
    )

    assert pattern.markers == ("blob",)
    assert pattern.matches("missing blob sha256-777777") is True
    expression.search.assert_called_once_with("missing blob sha256-777777")


def test_export_target_diagnostics_prefilters_unmarked_lines_before_pattern_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pattern = Mock()
    pattern.code = CODE_MISSING_BLOB
    pattern.matches.return_value = True
    monkeypatch.setattr(export_target_diagnostics_module, "_DIAGNOSIS_PATTERNS", (pattern,))
    monkeypatch.setattr(export_target_diagnostics_module, "_DIAGNOSIS_MARKERS", ("blob",))

    diagnoses = export_target_diagnostics_module._diagnoses_from_excerpt(
        [_SourceLine(source_path="logs/runtime.log", text="progress line without diagnostic terms")],
        {0: 1},
        "diagnostics/redacted-log-excerpt.txt",
    )

    assert diagnoses == []
    pattern.matches.assert_not_called()


def test_export_target_diagnostics_skips_path_regex_for_slashless_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path_pattern = Mock()
    monkeypatch.setattr(export_target_diagnostics_module, "_ABSOLUTE_PATH_PATTERN", path_pattern)
    summary = export_target_diagnostics_module._RedactionSummary()

    redacted = export_target_diagnostics_module._redact_text(
        "runtime load failed while opening model",
        tmp_path,
        str(tmp_path),
        summary,
    )

    assert redacted == "runtime load failed while opening model"
    path_pattern.sub.assert_not_called()
    assert summary.redaction_count == 0


def test_export_target_diagnostics_not_applicable_without_logs_or_failures(
    tmp_path: Path,
) -> None:
    _target_root, manifest = _materialized_manifest(
        tmp_path,
        FIXTURE_ROOT / "mlx_runtime/export-target-manifest.json",
    )
    layout = build_export_target_layout(tmp_path, manifest)

    receipt = build_export_diagnostics_receipt(layout, manifest)

    assert receipt["status"] == "not_applicable"
    assert receipt["diagnoses"] == []
    assert receipt["operator_remedies"] == []
    assert receipt["bounded_log_excerpt_path"] == ""
    assert receipt["metrics"]["parsed_failure_count"] == 0


def test_export_target_diagnostics_metrics_report_covers_supported_codes(
    tmp_path: Path,
) -> None:
    payload = build_diagnostic_metrics_report(
        sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json")),
        tmp_path,
    )

    assert payload["ok"] is True
    assert payload["target_count"] == 4
    assert payload["diagnostic_parser_coverage"] == 1.0
    assert payload["diagnosis_code_count"] == 9
    assert payload["parsed_failure_count"] >= 9
    assert payload["unknown_failure_count"] == 1
    assert payload["redaction_count"] >= 2
    assert payload["diagnostic_latency_ms"] >= 0


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
