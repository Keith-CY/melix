from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from packages.protocol.python.workspace.v1 import export_target_manifest_pb2
from worker.productization.export_target_layout import (
    ExportTargetLayout,
    build_export_target_layout,
    materialize_export_target_layout,
    _target_relative_path,
)
from worker.productization.export_target_manifest import validate_export_target_manifest_file


EXPORT_DIAGNOSTICS_RECEIPT_SCHEMA_VERSION = "melix.export_diagnostics_receipt.v1"
EXPORT_DIAGNOSTICS_METRICS_SCHEMA_VERSION = "melix.export_diagnostics.metrics.v1"
DEFAULT_PARSER_POLICY_ID = "runtime-export-log-v1"
DEFAULT_BOUNDED_LOG_BYTES = 8192
DEFAULT_BOUNDED_LOG_LINES = 120
_SOURCE_READ_MULTIPLIER = 2

DIAGNOSTIC_STATUS_MATCHED = "matched"
DIAGNOSTIC_STATUS_UNKNOWN = "unknown"
DIAGNOSTIC_STATUS_NOT_APPLICABLE = "not_applicable"

CODE_RUNTIME_LOAD_FAILED = "runtime_load_failed"
CODE_UNSUPPORTED_ARCHITECTURE = "unsupported_architecture"
CODE_DUPLICATE_TENSOR_NAME = "duplicate_tensor_name"
CODE_MISSING_BLOB = "missing_blob"
CODE_MISSING_BINARY = "missing_binary"
CODE_INVALID_RUNTIME_PATH = "invalid_runtime_path"
CODE_RUNTIME_TIMEOUT = "runtime_timeout"
CODE_PERMISSION_DENIED = "permission_denied"
CODE_INSUFFICIENT_MEMORY = "insufficient_memory"
CODE_UNKNOWN_FAILURE = "unknown_failure"

SUPPORTED_DIAGNOSIS_CODES = (
    CODE_RUNTIME_LOAD_FAILED,
    CODE_UNSUPPORTED_ARCHITECTURE,
    CODE_DUPLICATE_TENSOR_NAME,
    CODE_MISSING_BLOB,
    CODE_MISSING_BINARY,
    CODE_INVALID_RUNTIME_PATH,
    CODE_RUNTIME_TIMEOUT,
    CODE_PERMISSION_DENIED,
    CODE_INSUFFICIENT_MEMORY,
    CODE_UNKNOWN_FAILURE,
)
_KNOWN_DIAGNOSIS_CODES = tuple(code for code in SUPPORTED_DIAGNOSIS_CODES if code != CODE_UNKNOWN_FAILURE)

_ABSOLUTE_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9_.-])/[^\s:'\"<>|]+")
_BEARER_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"
)
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s,;]+['\"]?"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(https?://[^:\s/@]+:)[^@\s]+(@)")
_OPENAI_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_CERTIFICATE_PATTERN = re.compile(r"-----BEGIN [^-]+-----.+?-----END [^-]+-----")
_PRIVATE_TEXT_LINE_PATTERN = re.compile(
    r"(?i)^\s*(prompt|response|completion|generated text|dataset row|private prompt template|operator input)\s*[:=]"
)
_IDENTITY_PATTERN = re.compile(
    r"(?i)\b(user|operator)(?:[_-]?(?:id|name))?\s*[:=]\s*['\"]?[^'\"\s,;]+['\"]?"
)


@dataclass(frozen=True, slots=True)
class _DiagnosisPattern:
    code: str
    severity: str
    pattern_id: str
    expressions: tuple[re.Pattern[str], ...]
    operator_message: str
    remediation: str

    def matches(self, text: str) -> bool:
        return any(expression.search(text) for expression in self.expressions)


@dataclass(frozen=True, slots=True)
class _SourceLine:
    source_path: str
    text: str


@dataclass(slots=True)
class _RedactionSummary:
    excerpt_byte_count: int = 0
    excerpt_line_count: int = 0
    truncated: bool = False
    redaction_count: int = 0
    redacted_absolute_path_count: int = 0
    redacted_secret_count: int = 0
    redacted_prompt_or_response_count: int = 0
    redacted_identity_count: int = 0

    def payload(self, *, policy_id: str) -> dict[str, object]:
        return {
            "policy_id": policy_id,
            "excerpt_byte_count": self.excerpt_byte_count,
            "excerpt_line_count": self.excerpt_line_count,
            "truncated": self.truncated,
            "redaction_count": self.redaction_count,
            "redacted_absolute_path_count": self.redacted_absolute_path_count,
            "redacted_secret_count": self.redacted_secret_count,
            "redacted_prompt_or_response_count": self.redacted_prompt_or_response_count,
            "redacted_identity_count": self.redacted_identity_count,
        }


@dataclass(frozen=True, slots=True)
class _Excerpt:
    path: str
    text: str
    line_numbers: dict[int, int]
    summary: _RedactionSummary


def _compile(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


_DIAGNOSIS_PATTERNS = (
    _DiagnosisPattern(
        code=CODE_UNSUPPORTED_ARCHITECTURE,
        severity="error",
        pattern_id="unsupported-architecture-v1",
        expressions=_compile(
            r"unsupported architecture",
            r"bad cpu type",
            r"mach-o.+wrong architecture",
            r"not supported on this architecture",
            r"arm64.+required",
        ),
        operator_message="The target runtime cannot load this artifact on the current host architecture.",
        remediation="Use an Apple Silicon compatible runtime binary or export for a compatible target architecture.",
    ),
    _DiagnosisPattern(
        code=CODE_DUPLICATE_TENSOR_NAME,
        severity="error",
        pattern_id="duplicate-tensor-name-v1",
        expressions=_compile(
            r"duplicate tensor(?: name)?",
            r"tensor .+ already exists",
            r"duplicated key",
        ),
        operator_message="The runtime reported duplicate tensor names while loading the export.",
        remediation="Regenerate the export from a clean adapter snapshot and inspect the conversion step that writes tensor names.",
    ),
    _DiagnosisPattern(
        code=CODE_MISSING_BLOB,
        severity="error",
        pattern_id="missing-blob-v1",
        expressions=_compile(
            r"missing blob",
            r"blob .+ not found",
            r"no such blob",
            r"sha256[-:][A-Fa-f0-9]+.+not found",
            r"missing required smoke files:.+(blob|sha256|artifact)",
        ),
        operator_message="The target artifact references a blob or required artifact that is not present.",
        remediation="Re-run target materialization and verify required artifact digests before runtime load.",
    ),
    _DiagnosisPattern(
        code=CODE_MISSING_BINARY,
        severity="error",
        pattern_id="missing-runtime-binary-v1",
        expressions=_compile(
            r"command not found",
            r"binary not found",
            r"executable file not found",
            r"runtime binary not installed",
            r"no such file or directory:.+\b(ollama|mlx_lm|llama-cli|llama\.cpp)",
        ),
        operator_message="The target runtime binary is missing or not available on PATH.",
        remediation="Install the required runtime binary or configure the export target to use an available local runtime.",
    ),
    _DiagnosisPattern(
        code=CODE_INVALID_RUNTIME_PATH,
        severity="error",
        pattern_id="invalid-runtime-path-v1",
        expressions=_compile(
            r"invalid runtime path",
            r"invalid model path",
            r"path does not exist",
            r"not a directory",
        ),
        operator_message="The runtime was invoked with a path that is invalid for this target.",
        remediation="Use target-relative manifest paths and regenerate the export report before retrying the runtime load.",
    ),
    _DiagnosisPattern(
        code=CODE_RUNTIME_TIMEOUT,
        severity="error",
        pattern_id="runtime-timeout-v1",
        expressions=_compile(
            r"timed out",
            r"\btimeout\b",
            r"deadline exceeded",
            r"exceeded timeout",
        ),
        operator_message="The runtime did not finish the load or generation smoke check within the configured timeout.",
        remediation="Inspect runtime logs for slow startup, reduce the target artifact size, or increase the verified timeout policy.",
    ),
    _DiagnosisPattern(
        code=CODE_PERMISSION_DENIED,
        severity="error",
        pattern_id="permission-denied-v1",
        expressions=_compile(
            r"permission denied",
            r"operation not permitted",
            r"\bEACCES\b",
        ),
        operator_message="The runtime cannot read or execute a required export path because of local permissions.",
        remediation="Fix file permissions for the target directory and retry the smoke check from the same worktree.",
    ),
    _DiagnosisPattern(
        code=CODE_INSUFFICIENT_MEMORY,
        severity="error",
        pattern_id="insufficient-memory-v1",
        expressions=_compile(
            r"out of memory",
            r"\bOOM\b",
            r"cannot allocate memory",
            r"memory pressure",
            r"metal.+out of memory",
        ),
        operator_message="The host did not have enough memory for the runtime load or generation check.",
        remediation="Free memory, choose a smaller or more quantized target, or retry on a host with more memory.",
    ),
    _DiagnosisPattern(
        code=CODE_RUNTIME_LOAD_FAILED,
        severity="error",
        pattern_id="runtime-load-failed-v1",
        expressions=_compile(
            r"failed to load model",
            r"model load failed",
            r"runtime load failed",
            r"error loading model",
            r"load failed",
        ),
        operator_message="The target runtime failed while loading the exported artifact.",
        remediation="Inspect the redacted runtime evidence, then regenerate or repair the target artifact before retrying.",
    ),
)


def write_export_diagnostics_receipt(
    layout: ExportTargetLayout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    *,
    failure_checks: Iterable[object] = (),
    now: float | None = None,
) -> dict[str, object]:
    receipt = build_export_diagnostics_receipt(
        layout,
        manifest,
        failure_checks=failure_checks,
        now=now,
    )
    receipt_path = _target_relative_path(
        layout,
        manifest.evidence.diagnostics_receipt_path or "diagnostics/diagnostics-receipt.json",
    )
    _write_json(receipt_path, receipt)
    return receipt


def build_export_diagnostics_receipt(
    layout: ExportTargetLayout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    *,
    failure_checks: Iterable[object] = (),
    now: float | None = None,
) -> dict[str, object]:
    del now
    started = time.perf_counter()
    bounded_bytes = int(manifest.diagnostic_policy.bounded_log_excerpt_bytes) or DEFAULT_BOUNDED_LOG_BYTES
    source_lines = _collect_source_lines(
        layout,
        manifest,
        failure_checks=failure_checks,
        bounded_bytes=bounded_bytes,
    )
    excerpt = _build_redacted_excerpt(
        layout,
        source_lines,
        bounded_bytes=bounded_bytes,
        bounded_lines=DEFAULT_BOUNDED_LOG_LINES,
    )
    if excerpt.text:
        excerpt_path = _target_relative_path(layout, excerpt.path)
        excerpt_path.parent.mkdir(parents=True, exist_ok=True)
        excerpt_path.write_text(excerpt.text, encoding="utf-8")

    diagnoses = _diagnoses_from_excerpt(source_lines, excerpt.line_numbers, excerpt.path)
    if not diagnoses and source_lines:
        diagnoses = [
            {
                "code": CODE_UNKNOWN_FAILURE,
                "severity": "error",
                "matched_pattern_id": "unknown-failure-fallback-v1",
                "operator_message": "The export target failed, but no known runtime diagnostic pattern matched.",
                "remediation": "Use the bounded redacted excerpt to extend the parser or inspect target-local runtime logs.",
                "evidence_path": excerpt.path,
            }
        ]

    if not source_lines:
        status = DIAGNOSTIC_STATUS_NOT_APPLICABLE
    elif any(diagnosis["code"] != CODE_UNKNOWN_FAILURE for diagnosis in diagnoses):
        status = DIAGNOSTIC_STATUS_MATCHED
    else:
        status = DIAGNOSTIC_STATUS_UNKNOWN

    diagnostic_latency_ms = (time.perf_counter() - started) * 1000.0
    required_codes = {
        str(code)
        for code in manifest.diagnostic_policy.required_diagnosis_codes
        if str(code) in _KNOWN_DIAGNOSIS_CODES
    }
    matched_codes = {
        str(diagnosis["code"])
        for diagnosis in diagnoses
        if diagnosis["code"] != CODE_UNKNOWN_FAILURE
    }
    coverage = _diagnostic_coverage(required_codes, matched_codes, status)
    redaction_summary = excerpt.summary.payload(policy_id=manifest.evidence.redaction_policy_id or "export-diagnostics-redaction-v1")
    metrics = {
        "schema_version": EXPORT_DIAGNOSTICS_METRICS_SCHEMA_VERSION,
        "diagnostic_parser_coverage": coverage,
        "parsed_failure_count": sum(
            1 for diagnosis in diagnoses if diagnosis["code"] != CODE_UNKNOWN_FAILURE
        ),
        "unknown_failure_count": sum(
            1 for diagnosis in diagnoses if diagnosis["code"] == CODE_UNKNOWN_FAILURE
        ),
        "redaction_count": redaction_summary["redaction_count"],
        "diagnostic_latency_ms": diagnostic_latency_ms,
    }
    return {
        "schema_version": EXPORT_DIAGNOSTICS_RECEIPT_SCHEMA_VERSION,
        "export_id": manifest.export_id,
        "target_id": manifest.target_id,
        "target_type": export_target_manifest_pb2.ExportTargetType.Name(manifest.target_type),
        "parser_policy_id": manifest.diagnostic_policy.parser_policy_id or DEFAULT_PARSER_POLICY_ID,
        "status": status,
        "diagnoses": diagnoses,
        "redaction_summary": redaction_summary,
        "bounded_log_excerpt_path": excerpt.path if excerpt.text else "",
        "operator_remedies": _operator_remedies(diagnoses),
        "metrics": metrics,
    }


def build_diagnostic_metrics_report(
    manifest_paths: Iterable[Path],
    workspace_root: Path | str,
    *,
    now: float | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    receipts: list[dict[str, object]] = []
    errors: list[str] = []
    root = Path(workspace_root)

    for index, manifest_path in enumerate(manifest_paths):
        export_report = materialize_export_target_layout(
            manifest_path,
            root,
            create_placeholder_files=True,
            now=now,
        )
        if export_report.get("ok") is not True:
            errors.extend(str(error) for error in export_report.get("errors", []))
            continue
        target_root = root / str(export_report["target_root"])
        manifest, validation_report = validate_export_target_manifest_file(
            target_root / "export-target-manifest.json",
            return_manifest=True,
        )
        if not validation_report.ok:
            errors.extend(str(error) for error in validation_report.errors)
            continue
        layout = build_export_target_layout(root, manifest)
        try:
            receipts.append(
                write_export_diagnostics_receipt(
                    layout,
                    manifest,
                    failure_checks=_fixture_failure_checks(index),
                    now=now,
                )
            )
        except Exception as exc:  # pragma: no cover - aggregate probe errors
            errors.append(str(exc))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    metrics = [
        receipt["metrics"]
        for receipt in receipts
        if isinstance(receipt.get("metrics"), dict)
    ]
    matched_codes = {
        str(diagnosis["code"])
        for receipt in receipts
        for diagnosis in receipt.get("diagnoses", [])
        if isinstance(diagnosis, dict) and diagnosis.get("code") != CODE_UNKNOWN_FAILURE
    }
    parser_coverage = len(matched_codes & set(_KNOWN_DIAGNOSIS_CODES)) / len(_KNOWN_DIAGNOSIS_CODES)
    return {
        "schema_version": EXPORT_DIAGNOSTICS_METRICS_SCHEMA_VERSION,
        "ok": not errors and parser_coverage == 1.0,
        "target_count": len(receipts),
        "diagnostic_policy_latency_ms": elapsed_ms,
        "diagnostic_parser_coverage": parser_coverage,
        "parsed_failure_count": sum(int(metric.get("parsed_failure_count", 0)) for metric in metrics),
        "unknown_failure_count": sum(int(metric.get("unknown_failure_count", 0)) for metric in metrics),
        "redaction_count": sum(int(metric.get("redaction_count", 0)) for metric in metrics),
        "diagnostic_latency_ms": sum(float(metric.get("diagnostic_latency_ms", 0.0)) for metric in metrics),
        "diagnosis_code_count": len(matched_codes),
        "errors": errors,
        "receipts": receipts,
    }


def _collect_source_lines(
    layout: ExportTargetLayout,
    manifest: export_target_manifest_pb2.ExportTargetManifest,
    *,
    failure_checks: Iterable[object],
    bounded_bytes: int,
) -> list[_SourceLine]:
    lines: list[_SourceLine] = []
    seen_paths: set[str] = set()
    source_read_bytes = max(bounded_bytes * _SOURCE_READ_MULTIPLIER, bounded_bytes)

    for row in (*manifest.generated_files, *manifest.required_files, *manifest.intermediate_files):
        if not _is_runtime_log_row(row):
            continue
        if row.path in seen_paths:
            continue
        seen_paths.add(row.path)
        path = _target_relative_path(layout, row.path)
        if not path.is_file():
            continue
        with path.open("rb") as source:
            text = source.read(source_read_bytes).decode("utf-8", errors="replace")
        lines.extend(_split_source_lines(row.path, text))

    for check in failure_checks:
        failure_message = _check_value(check, "failure_message")
        failure_code = _check_value(check, "failure_code")
        status = _check_value(check, "status")
        if not failure_message and not failure_code:
            continue
        if status and status not in {"failed", "blocked"}:
            continue
        check_name = _check_value(check, "check") or _check_value(check, "name") or "smoke_failure"
        evidence_path = _check_value(check, "evidence_path") or manifest.evidence.smoke_receipt_path
        text = f"{check_name}: {failure_code}: {failure_message}".strip()
        lines.extend(_split_source_lines(evidence_path or "smoke/smoke-receipt.json", text))

    return lines


def _is_runtime_log_row(row: export_target_manifest_pb2.ExportTargetFile) -> bool:
    return (
        row.role == export_target_manifest_pb2.EXPORT_TARGET_FILE_ROLE_RUNTIME_LOG
        or row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_RUNTIME_LOG
        or row.path.startswith("logs/")
    )


def _split_source_lines(source_path: str, text: str) -> list[_SourceLine]:
    if not text:
        return []
    return [_SourceLine(source_path=source_path, text=line) for line in text.splitlines()]


def _check_value(check: object, name: str) -> str:
    if isinstance(check, Mapping):
        value = check.get(name, "")
    else:
        value = getattr(check, name, "")
    return str(value) if value is not None else ""


def _build_redacted_excerpt(
    layout: ExportTargetLayout,
    source_lines: list[_SourceLine],
    *,
    bounded_bytes: int,
    bounded_lines: int,
) -> _Excerpt:
    summary = _RedactionSummary()
    if not source_lines:
        return _Excerpt(path="", text="", line_numbers={}, summary=summary)

    output_lines: list[str] = []
    line_numbers: dict[int, int] = {}
    used_bytes = 0
    for index, source_line in enumerate(source_lines):
        if len(output_lines) >= bounded_lines:
            summary.truncated = True
            break
        redacted = _redact_text(source_line.text, layout, summary)
        rendered = f"[{source_line.source_path}] {redacted}"
        rendered_bytes = (rendered + "\n").encode("utf-8")
        if used_bytes + len(rendered_bytes) > bounded_bytes:
            remaining = max(0, bounded_bytes - used_bytes)
            if remaining > 0:
                clipped = rendered_bytes[:remaining].decode("utf-8", errors="ignore")
                output_lines.append(clipped)
                line_numbers[index] = len(output_lines)
                used_bytes += len(clipped.encode("utf-8"))
            summary.truncated = True
            break
        output_lines.append(rendered)
        line_numbers[index] = len(output_lines)
        used_bytes += len(rendered_bytes)

    text = "\n".join(output_lines)
    if text:
        text += "\n"
    encoded_text = text.encode("utf-8")
    if len(encoded_text) > bounded_bytes:
        text = encoded_text[:bounded_bytes].decode("utf-8", errors="ignore")
        summary.truncated = True
    summary.excerpt_byte_count = len(text.encode("utf-8"))
    summary.excerpt_line_count = len(output_lines)
    if len(source_lines) > len(output_lines):
        summary.truncated = True
    return _Excerpt(
        path="diagnostics/redacted-log-excerpt.txt",
        text=text,
        line_numbers=line_numbers,
        summary=summary,
    )


def _redact_text(
    text: str,
    layout: ExportTargetLayout,
    summary: _RedactionSummary,
) -> str:
    if _PRIVATE_TEXT_LINE_PATTERN.search(text):
        summary.redacted_prompt_or_response_count += 1
        summary.redaction_count += 1
        return "<redacted-private-preview>"

    text = _CERTIFICATE_PATTERN.sub(lambda _match: _record_secret(summary), text)
    text = _BEARER_SECRET_PATTERN.sub(
        lambda match: match.group(1) + _record_secret(summary),
        text,
    )
    text = _NAMED_SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}=<redacted-secret>{_record_secret_count_only(summary)}",
        text,
    )
    text = _URL_CREDENTIAL_PATTERN.sub(
        lambda match: match.group(1) + _record_secret(summary) + match.group(2),
        text,
    )
    text = _OPENAI_KEY_PATTERN.sub(lambda _match: _record_secret(summary), text)
    text = _IDENTITY_PATTERN.sub(
        lambda match: _record_identity(summary, match.group(1)),
        text,
    )
    return _ABSOLUTE_PATH_PATTERN.sub(
        lambda match: _redact_absolute_path(match.group(0), layout, summary),
        text,
    )


def _record_secret(summary: _RedactionSummary) -> str:
    summary.redacted_secret_count += 1
    summary.redaction_count += 1
    return "<redacted-secret>"


def _record_secret_count_only(summary: _RedactionSummary) -> str:
    _record_secret(summary)
    return ""


def _record_identity(summary: _RedactionSummary, key: str) -> str:
    summary.redacted_identity_count += 1
    summary.redaction_count += 1
    return f"{key}=<redacted-identity>"


def _redact_absolute_path(
    raw_path: str,
    layout: ExportTargetLayout,
    summary: _RedactionSummary,
) -> str:
    trimmed_path = raw_path.rstrip(".,)")
    suffix = raw_path[len(trimmed_path):]
    replacement = "<absolute-path>"
    try:
        relative = Path(trimmed_path).resolve(strict=False).relative_to(
            layout.target_root.resolve(strict=False)
        )
        replacement = f"<target>/{relative.as_posix()}"
    except (ValueError, OSError):
        pass
    summary.redacted_absolute_path_count += 1
    summary.redaction_count += 1
    return replacement + suffix


def _diagnoses_from_excerpt(
    source_lines: list[_SourceLine],
    line_numbers: dict[int, int],
    excerpt_path: str,
) -> list[dict[str, object]]:
    diagnoses: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    for index, line_number in line_numbers.items():
        text = source_lines[index].text
        for pattern in _DIAGNOSIS_PATTERNS:
            if pattern.code in seen_codes:
                continue
            if not pattern.matches(text):
                continue
            seen_codes.add(pattern.code)
            diagnoses.append(
                {
                    "code": pattern.code,
                    "severity": pattern.severity,
                    "matched_pattern_id": pattern.pattern_id,
                    "operator_message": pattern.operator_message,
                    "remediation": pattern.remediation,
                    "evidence_path": f"{excerpt_path}#line-{line_number}",
                }
            )
            break
    return diagnoses


def _operator_remedies(diagnoses: list[dict[str, object]]) -> list[dict[str, object]]:
    remedies: list[dict[str, object]] = []
    for diagnosis in diagnoses:
        code = str(diagnosis["code"])
        remedies.append(
            {
                "code": code,
                "title": code.replace("_", " ").title(),
                "message": str(diagnosis["operator_message"]),
                "remediation": str(diagnosis["remediation"]),
                "evidence_path": str(diagnosis["evidence_path"]),
            }
        )
    return remedies


def _diagnostic_coverage(
    required_codes: set[str],
    matched_codes: set[str],
    status: str,
) -> float:
    if required_codes:
        return len(required_codes & matched_codes) / len(required_codes)
    if status == DIAGNOSTIC_STATUS_UNKNOWN:
        return 0.0
    return 1.0


def _fixture_failure_checks(index: int) -> list[dict[str, object]]:
    if index == 1:
        return [
            {
                "check": "load_check",
                "status": "failed",
                "failure_code": CODE_RUNTIME_LOAD_FAILED,
                "failure_message": (
                    "unclassified runtime failure for /tmp/melix/private/export "
                    "Authorization: Bearer sk-testsecret0000 prompt: private"
                ),
                "evidence_path": "smoke/smoke-receipt.json",
            }
        ]
    samples = {
        CODE_RUNTIME_LOAD_FAILED: "runtime load failed while opening model",
        CODE_UNSUPPORTED_ARCHITECTURE: "unsupported architecture arm64 required",
        CODE_DUPLICATE_TENSOR_NAME: "duplicate tensor name decoder.layers.0",
        CODE_MISSING_BLOB: "missing blob sha256-777777 not found",
        CODE_MISSING_BINARY: "runtime binary not installed: ollama",
        CODE_INVALID_RUNTIME_PATH: "invalid runtime path /tmp/melix/bad-target",
        CODE_RUNTIME_TIMEOUT: "generation smoke timed out after deadline exceeded",
        CODE_PERMISSION_DENIED: "permission denied opening model weights",
        CODE_INSUFFICIENT_MEMORY: "Metal out of memory during load",
    }
    return [
        {
            "check": "load_check",
            "status": "failed",
            "failure_code": code,
            "failure_message": message,
            "evidence_path": "smoke/smoke-receipt.json",
        }
        for code, message in samples.items()
    ]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
