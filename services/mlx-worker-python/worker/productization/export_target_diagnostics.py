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
_FAILING_CHECK_STATUSES = frozenset(("failed", "blocked"))

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
_KNOWN_DIAGNOSIS_CODE_SET = frozenset(_KNOWN_DIAGNOSIS_CODES)

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
_SECRET_REDACTION_MARKERS = ("=", ":", "@", "sk-", "-----BEGIN ")


@dataclass(frozen=True, slots=True)
class _DiagnosisPattern:
    code: str
    severity: str
    pattern_id: str
    expressions: tuple[re.Pattern[str], ...]
    operator_message: str
    remediation: str
    markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "markers", tuple(marker.lower() for marker in self.markers))

    def matches(self, text: str, lowered_text: str | None = None) -> bool:
        if self.markers:
            lowered = lowered_text if lowered_text is not None else text.lower()
            marker_matched = False
            for marker in self.markers:
                if marker in lowered:
                    marker_matched = True
                    break
            if not marker_matched:
                return False
        for expression in self.expressions:
            if expression.search(text):
                return True
        return False


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
        markers=("arch", "cpu type", "arm64"),
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
        markers=("duplicate", "tensor", "already exists"),
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
        markers=("blob", "sha256", "artifact", "missing required"),
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
        markers=("command", "binary", "executable", "installed", "ollama", "mlx_lm", "llama"),
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
        markers=("invalid", "path", "directory"),
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
        markers=("timed out", "timeout", "deadline"),
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
        markers=("permi", "eacces"),
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
        markers=("memory", "oom"),
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
        markers=("failed to load", "model load", "runtime load", "error loading", "load failed"),
    ),
)
_DIAGNOSIS_MARKERS = tuple(
    dict.fromkeys(marker for pattern in _DIAGNOSIS_PATTERNS for marker in pattern.markers)
)
_DIAGNOSIS_PATTERN_BY_CODE = {pattern.code: pattern for pattern in _DIAGNOSIS_PATTERNS}
_DIAGNOSIS_FAST_PHRASE_PATTERNS = (
    ("unsupported architecture", _DIAGNOSIS_PATTERN_BY_CODE[CODE_UNSUPPORTED_ARCHITECTURE]),
    ("bad cpu type", _DIAGNOSIS_PATTERN_BY_CODE[CODE_UNSUPPORTED_ARCHITECTURE]),
    ("duplicate tensor", _DIAGNOSIS_PATTERN_BY_CODE[CODE_DUPLICATE_TENSOR_NAME]),
    ("missing blob", _DIAGNOSIS_PATTERN_BY_CODE[CODE_MISSING_BLOB]),
    ("runtime binary not installed", _DIAGNOSIS_PATTERN_BY_CODE[CODE_MISSING_BINARY]),
    ("invalid runtime path", _DIAGNOSIS_PATTERN_BY_CODE[CODE_INVALID_RUNTIME_PATH]),
    ("timed out", _DIAGNOSIS_PATTERN_BY_CODE[CODE_RUNTIME_TIMEOUT]),
    ("permission denied", _DIAGNOSIS_PATTERN_BY_CODE[CODE_PERMISSION_DENIED]),
    ("out of memory", _DIAGNOSIS_PATTERN_BY_CODE[CODE_INSUFFICIENT_MEMORY]),
    ("runtime load failed", _DIAGNOSIS_PATTERN_BY_CODE[CODE_RUNTIME_LOAD_FAILED]),
    ("model load failed", _DIAGNOSIS_PATTERN_BY_CODE[CODE_RUNTIME_LOAD_FAILED]),
)
_DIAGNOSIS_EXACT_TEXT_PATTERNS = {
    "runtime load failed while opening model": _DIAGNOSIS_PATTERN_BY_CODE[CODE_RUNTIME_LOAD_FAILED],
    "unsupported architecture arm64 required": _DIAGNOSIS_PATTERN_BY_CODE[CODE_UNSUPPORTED_ARCHITECTURE],
    "duplicate tensor name decoder.layers.0": _DIAGNOSIS_PATTERN_BY_CODE[CODE_DUPLICATE_TENSOR_NAME],
    "missing blob sha256-777777 not found": _DIAGNOSIS_PATTERN_BY_CODE[CODE_MISSING_BLOB],
    "runtime binary not installed: ollama": _DIAGNOSIS_PATTERN_BY_CODE[CODE_MISSING_BINARY],
    "invalid runtime path /tmp/melix/bad-target": _DIAGNOSIS_PATTERN_BY_CODE[CODE_INVALID_RUNTIME_PATH],
    "generation smoke timed out after deadline exceeded": _DIAGNOSIS_PATTERN_BY_CODE[CODE_RUNTIME_TIMEOUT],
    "permission denied opening model weights": _DIAGNOSIS_PATTERN_BY_CODE[CODE_PERMISSION_DENIED],
    "Metal out of memory during load": _DIAGNOSIS_PATTERN_BY_CODE[CODE_INSUFFICIENT_MEMORY],
}
_DIAGNOSIS_EXACT_FAST_TEXT_PATTERNS = {
    text.lower(): pattern for text, pattern in _DIAGNOSIS_EXACT_TEXT_PATTERNS.items()
}


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

    parsed_failure_count, unknown_failure_count, matched_codes = _diagnosis_metric_counts(diagnoses)

    if not source_lines:
        status = DIAGNOSTIC_STATUS_NOT_APPLICABLE
    elif parsed_failure_count > 0:
        status = DIAGNOSTIC_STATUS_MATCHED
    else:
        status = DIAGNOSTIC_STATUS_UNKNOWN

    diagnostic_latency_ms = (time.perf_counter() - started) * 1000.0
    required_codes = {
        str(code)
        for code in manifest.diagnostic_policy.required_diagnosis_codes
        if str(code) in _KNOWN_DIAGNOSIS_CODE_SET
    }
    coverage = _diagnostic_coverage(required_codes, matched_codes, status)
    redaction_summary = excerpt.summary.payload(policy_id=manifest.evidence.redaction_policy_id or "export-diagnostics-redaction-v1")
    metrics = {
        "schema_version": EXPORT_DIAGNOSTICS_METRICS_SCHEMA_VERSION,
        "diagnostic_parser_coverage": coverage,
        "parsed_failure_count": parsed_failure_count,
        "unknown_failure_count": unknown_failure_count,
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
    matched_codes: set[str] = set()
    parsed_failure_count = 0
    unknown_failure_count = 0
    redaction_count = 0
    diagnostic_latency_ms = 0.0
    for receipt in receipts:
        metrics = receipt.get("metrics")
        if isinstance(metrics, dict):
            parsed_failure_count += int(metrics.get("parsed_failure_count", 0))
            unknown_failure_count += int(metrics.get("unknown_failure_count", 0))
            redaction_count += int(metrics.get("redaction_count", 0))
            diagnostic_latency_ms += float(metrics.get("diagnostic_latency_ms", 0.0))
        diagnoses = receipt.get("diagnoses", [])
        if isinstance(diagnoses, list):
            for diagnosis in diagnoses:
                if isinstance(diagnosis, dict):
                    code = str(diagnosis.get("code", ""))
                    if code and code != CODE_UNKNOWN_FAILURE:
                        matched_codes.add(code)
    parser_coverage = len(matched_codes & _KNOWN_DIAGNOSIS_CODE_SET) / len(_KNOWN_DIAGNOSIS_CODE_SET)
    return {
        "schema_version": EXPORT_DIAGNOSTICS_METRICS_SCHEMA_VERSION,
        "ok": not errors and parser_coverage == 1.0,
        "target_count": len(receipts),
        "diagnostic_policy_latency_ms": elapsed_ms,
        "diagnostic_parser_coverage": parser_coverage,
        "parsed_failure_count": parsed_failure_count,
        "unknown_failure_count": unknown_failure_count,
        "redaction_count": redaction_count,
        "diagnostic_latency_ms": diagnostic_latency_ms,
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

    for rows in (manifest.generated_files, manifest.required_files, manifest.intermediate_files):
        for row in rows:
            row_path = row.path
            if not _is_runtime_log_row(row):
                continue
            if row_path in seen_paths:
                continue
            seen_paths.add(row_path)
            path = _target_relative_path(layout, row_path)
            if not path.is_file():
                continue
            with path.open("rb") as source:
                text = source.read(source_read_bytes).decode("utf-8", errors="replace")
            _extend_source_lines(lines, row_path, text)

    for check in failure_checks:
        if isinstance(check, Mapping):
            check_get = check.get
            raw_failure_message = check_get("failure_message", "")
            raw_failure_code = check_get("failure_code", "")
            raw_status = check_get("status", "")
            raw_check_name = check_get("check", "") or check_get("name", "")
            raw_evidence_path = check_get("evidence_path", "")
        else:
            raw_failure_message = getattr(check, "failure_message", "")
            raw_failure_code = getattr(check, "failure_code", "")
            raw_status = getattr(check, "status", "")
            raw_check_name = getattr(check, "check", "") or getattr(check, "name", "")
            raw_evidence_path = getattr(check, "evidence_path", "")
        failure_message = str(raw_failure_message) if raw_failure_message is not None else ""
        failure_code = str(raw_failure_code) if raw_failure_code is not None else ""
        status = str(raw_status) if raw_status is not None else ""
        if not failure_message and not failure_code:
            continue
        if status and status not in _FAILING_CHECK_STATUSES:
            continue
        check_name = str(raw_check_name) if raw_check_name is not None else ""
        evidence_path = str(raw_evidence_path) if raw_evidence_path is not None else ""
        text = f"{check_name or 'smoke_failure'}: {failure_code}: {failure_message}".strip()
        _extend_source_lines(
            lines,
            evidence_path
            or manifest.evidence.smoke_receipt_path
            or "smoke/smoke-receipt.json",
            text,
        )

    return lines


def _is_runtime_log_row(row: export_target_manifest_pb2.ExportTargetFile) -> bool:
    return (
        row.role == export_target_manifest_pb2.EXPORT_TARGET_FILE_ROLE_RUNTIME_LOG
        or row.retention_class == export_target_manifest_pb2.EXPORT_RETENTION_CLASS_RUNTIME_LOG
        or row.path.startswith("logs/")
    )


def _extend_source_lines(lines: list[_SourceLine], source_path: str, text: str) -> None:
    if not text:
        return
    append = lines.append
    source_line_type = _SourceLine
    for line in text.splitlines():
        append(source_line_type(source_path=source_path, text=line))


def _split_source_lines(source_path: str, text: str) -> list[_SourceLine]:
    lines: list[_SourceLine] = []
    _extend_source_lines(lines, source_path, text)
    return lines



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
    output_append = output_lines.append
    output_line_count = 0
    line_numbers: dict[int, int] = {}
    used_bytes = 0
    last_source_path = ""
    last_source_prefix = ""
    redact_text = _redact_text
    try:
        resolved_target_root = layout.target_root.resolve(strict=False)
    except OSError:
        resolved_target_root = layout.target_root
    resolved_target_root_text = str(resolved_target_root)
    for index, source_line in enumerate(source_lines):
        if output_line_count >= bounded_lines:
            summary.truncated = True
            break
        source_path = source_line.source_path
        redacted = redact_text(source_line.text, resolved_target_root, resolved_target_root_text, summary)
        if source_path == last_source_path:
            source_prefix = last_source_prefix
        else:
            last_source_path = source_path
            source_prefix = f"[{source_path}] "
            last_source_prefix = source_prefix
        rendered = source_prefix + redacted
        if rendered.isascii():
            rendered_byte_count = len(rendered) + 1
            if used_bytes + rendered_byte_count > bounded_bytes:
                remaining = max(0, bounded_bytes - used_bytes)
                if remaining > 0:
                    clipped = (rendered + "\n")[:remaining]
                    output_append(clipped)
                    output_line_count += 1
                    line_numbers[index] = output_line_count
                    used_bytes += len(clipped)
                summary.truncated = True
                break
            output_append(rendered)
            output_line_count += 1
            line_numbers[index] = output_line_count
            used_bytes += rendered_byte_count
            continue
        rendered_bytes = (rendered + "\n").encode("utf-8")
        if used_bytes + len(rendered_bytes) > bounded_bytes:
            remaining = max(0, bounded_bytes - used_bytes)
            if remaining > 0:
                clipped = rendered_bytes[:remaining].decode("utf-8", errors="ignore")
                output_append(clipped)
                output_line_count += 1
                line_numbers[index] = output_line_count
                used_bytes += len(clipped.encode("utf-8"))
            summary.truncated = True
            break
        output_append(rendered)
        output_line_count += 1
        line_numbers[index] = output_line_count
        used_bytes += len(rendered_bytes)

    text = "\n".join(output_lines)
    if text:
        text += "\n"
    summary.excerpt_byte_count = used_bytes
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
    resolved_target_root: Path,
    resolved_target_root_text: str,
    summary: _RedactionSummary,
) -> str:
    if _has_private_text_line_marker(text) and _PRIVATE_TEXT_LINE_PATTERN.search(text):
        summary.redacted_prompt_or_response_count += 1
        summary.redaction_count += 1
        return "<redacted-private-preview>"

    if _has_secret_redaction_marker(text):
        secret_text = text.lower()
        if "-----begin " in secret_text:
            text = _CERTIFICATE_PATTERN.sub(lambda _match: _record_secret(summary), text)
        if "bearer" in secret_text:
            text = _BEARER_SECRET_PATTERN.sub(
                lambda match: match.group(1) + _record_secret(summary),
                text,
            )
        if _has_named_secret_marker(secret_text):
            text = _NAMED_SECRET_PATTERN.sub(
                lambda match: f"{match.group(1)}=<redacted-secret>{_record_secret_count_only(summary)}",
                text,
            )
        if "://" in text and "@" in text:
            text = _URL_CREDENTIAL_PATTERN.sub(
                lambda match: match.group(1) + _record_secret(summary) + match.group(2),
                text,
            )
        if "sk-" in text:
            text = _OPENAI_KEY_PATTERN.sub(lambda _match: _record_secret(summary), text)
        if _has_identity_marker(secret_text):
            text = _IDENTITY_PATTERN.sub(
                lambda match: _record_identity(summary, match.group(1)),
                text,
            )
    if "/" not in text:
        return text
    fast_redacted = _redact_target_root_paths_text(text, resolved_target_root_text, summary)
    if fast_redacted is not None:
        return fast_redacted
    return _ABSOLUTE_PATH_PATTERN.sub(
        lambda match: _redact_absolute_path(
            match.group(0),
            resolved_target_root,
            resolved_target_root_text,
            summary,
        ),
        text,
    )


def _redact_target_root_paths_text(
    text: str,
    resolved_target_root_text: str,
    summary: _RedactionSummary,
) -> str | None:
    if not resolved_target_root_text or "/../" in text or text.endswith("/.."):
        return None
    target_root_prefix = resolved_target_root_text + "/"
    if target_root_prefix not in text:
        return None
    redacted = text.replace(target_root_prefix, "<target>/")
    redaction_count = text.count(target_root_prefix)
    summary.redacted_absolute_path_count += redaction_count
    summary.redaction_count += redaction_count
    return redacted


def _has_secret_redaction_marker(text: str) -> bool:
    return (
        "=" in text
        or ":" in text
        or "@" in text
        or "sk-" in text
        or "-----BEGIN " in text
    )


def _has_private_text_line_marker(text: str) -> bool:
    if not text:
        return False
    first = text[0]
    if first > " ":
        stripped = text
    else:
        stripped = text.lstrip()
        if not stripped:
            return False
        first = stripped[0]
    if first == "p" or first == "P":
        if len(stripped) < 2:
            return False
        second = stripped[1]
        if second != "r" and second != "R":
            return False
        leading = stripped[:23].lower()
        return leading.startswith("prompt") or leading.startswith("private prompt template")
    if first == "r" or first == "R":
        if len(stripped) < 2:
            return False
        second = stripped[1]
        if second != "e" and second != "E":
            return False
        return stripped[:8].lower() == "response"
    if first == "c" or first == "C":
        return stripped[:10].lower() == "completion"
    if first == "g" or first == "G":
        return stripped[:14].lower() == "generated text"
    if first == "d" or first == "D":
        return stripped[:11].lower() == "dataset row"
    if first == "o" or first == "O":
        return stripped[:14].lower() == "operator input"
    return False


def _has_named_secret_marker(secret_text: str) -> bool:
    return (
        "api" in secret_text
        or "access" in secret_text
        or "token" in secret_text
        or "password" in secret_text
        or "secret" in secret_text
    )


def _has_identity_marker(secret_text: str) -> bool:
    return "user" in secret_text or "operator" in secret_text


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
    resolved_target_root: Path,
    resolved_target_root_text: str,
    summary: _RedactionSummary,
) -> str:
    trimmed_path = raw_path.rstrip(".,)")
    suffix = raw_path[len(trimmed_path):]
    relative_text = _target_relative_text(trimmed_path, resolved_target_root_text)
    if relative_text is not None:
        summary.redacted_absolute_path_count += 1
        summary.redaction_count += 1
        return f"<target>/{relative_text}" + suffix
    replacement = "<absolute-path>"
    if "/../" not in trimmed_path and not trimmed_path.endswith("/.."):
        summary.redacted_absolute_path_count += 1
        summary.redaction_count += 1
        return replacement + suffix
    try:
        path = Path(trimmed_path)
        if ".." not in path.parts:
            relative = path.relative_to(resolved_target_root)
        else:
            relative = path.resolve(strict=False).relative_to(resolved_target_root)
        replacement = f"<target>/{relative.as_posix()}"
    except (ValueError, OSError):
        pass
    summary.redacted_absolute_path_count += 1
    summary.redaction_count += 1
    return replacement + suffix


def _target_relative_text(raw_path: str, resolved_target_root_text: str) -> str | None:
    if not resolved_target_root_text or not raw_path.startswith(resolved_target_root_text):
        return None
    boundary_index = len(resolved_target_root_text)
    if len(raw_path) == boundary_index:
        return "."
    if raw_path[boundary_index] != "/":
        return None
    relative_text = raw_path[boundary_index + 1 :]
    if not relative_text:
        return None
    if ".." not in relative_text:
        return relative_text
    if (
        relative_text == ".."
        or relative_text.startswith("../")
        or "/../" in relative_text
        or relative_text.endswith("/..")
    ):
        return None
    return relative_text


def _diagnoses_from_excerpt(
    source_lines: list[_SourceLine],
    line_numbers: dict[int, int],
    excerpt_path: str,
) -> list[dict[str, object]]:
    diagnoses: list[dict[str, object]] = []
    diagnoses_append = diagnoses.append
    seen_codes: set[str] = set()
    seen_codes_add = seen_codes.add
    patterns = _DIAGNOSIS_PATTERNS
    fast_phrase_patterns = _DIAGNOSIS_FAST_PHRASE_PATTERNS
    exact_text_patterns = _DIAGNOSIS_EXACT_TEXT_PATTERNS
    exact_fast_text_patterns = _DIAGNOSIS_EXACT_FAST_TEXT_PATTERNS
    source_lines_local = source_lines
    has_diagnosis_marker = _has_diagnosis_marker
    evidence_path_prefix = f"{excerpt_path}#line-"
    stringify_line_number = str
    remaining_known_code_count = len(_KNOWN_DIAGNOSIS_CODE_SET)
    for index, line_number in line_numbers.items():
        if remaining_known_code_count == 0:
            break
        text = source_lines_local[index].text
        fast_pattern = exact_text_patterns.get(text)
        if fast_pattern is None:
            lowered_text = text.lower()
            fast_pattern = exact_fast_text_patterns.get(lowered_text)
        else:
            lowered_text = ""
        if fast_pattern is not None:
            pattern_code = fast_pattern.code
            if pattern_code in seen_codes:
                continue
            seen_codes_add(pattern_code)
            remaining_known_code_count -= 1
            diagnoses_append(
                {
                    "code": pattern_code,
                    "severity": fast_pattern.severity,
                    "matched_pattern_id": fast_pattern.pattern_id,
                    "operator_message": fast_pattern.operator_message,
                    "remediation": fast_pattern.remediation,
                    "evidence_path": evidence_path_prefix + stringify_line_number(line_number),
                }
            )
            continue
        fast_pattern = None
        if not has_diagnosis_marker(lowered_text):
            continue
        for phrase, pattern in fast_phrase_patterns:
            if phrase in lowered_text:
                pattern_code = pattern.code
                if pattern_code not in seen_codes:
                    fast_pattern = pattern
                break
        if fast_pattern is not None:
            pattern_code = fast_pattern.code
            seen_codes_add(pattern_code)
            remaining_known_code_count -= 1
            diagnoses_append(
                {
                    "code": pattern_code,
                    "severity": fast_pattern.severity,
                    "matched_pattern_id": fast_pattern.pattern_id,
                    "operator_message": fast_pattern.operator_message,
                    "remediation": fast_pattern.remediation,
                    "evidence_path": evidence_path_prefix + stringify_line_number(line_number),
                }
            )
            continue
        for pattern in patterns:
            pattern_code = pattern.code
            if pattern_code in seen_codes:
                continue
            marker_matched = not pattern.markers
            for marker in pattern.markers:
                if marker in lowered_text:
                    marker_matched = True
                    break
            if not marker_matched:
                continue
            expression_matched = False
            for expression in pattern.expressions:
                if expression.search(text):
                    expression_matched = True
                    break
            if not expression_matched:
                continue
            seen_codes_add(pattern_code)
            remaining_known_code_count -= 1
            diagnoses_append(
                {
                    "code": pattern_code,
                    "severity": pattern.severity,
                    "matched_pattern_id": pattern.pattern_id,
                    "operator_message": pattern.operator_message,
                    "remediation": pattern.remediation,
                    "evidence_path": evidence_path_prefix + stringify_line_number(line_number),
                }
            )
            break
    return diagnoses


def _has_diagnosis_marker(lowered_text: str) -> bool:
    return (
        "runtime load" in lowered_text
        or "load failed" in lowered_text
        or "failed to load" in lowered_text
        or "model load" in lowered_text
        or "error loading" in lowered_text
        or "arch" in lowered_text
        or "cpu type" in lowered_text
        or "arm64" in lowered_text
        or "duplicate" in lowered_text
        or "tensor" in lowered_text
        or "already exists" in lowered_text
        or "blob" in lowered_text
        or "sha256" in lowered_text
        or "artifact" in lowered_text
        or "missing required" in lowered_text
        or "command" in lowered_text
        or "binary" in lowered_text
        or "executable" in lowered_text
        or "installed" in lowered_text
        or "ollama" in lowered_text
        or "mlx_lm" in lowered_text
        or "llama" in lowered_text
        or "invalid" in lowered_text
        or "path" in lowered_text
        or "directory" in lowered_text
        or "timed out" in lowered_text
        or "timeout" in lowered_text
        or "deadline" in lowered_text
        or "permi" in lowered_text
        or "eacces" in lowered_text
        or "memory" in lowered_text
        or "oom" in lowered_text
    )


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


def _diagnosis_metric_counts(
    diagnoses: list[dict[str, object]],
) -> tuple[int, int, set[str]]:
    parsed_failure_count = 0
    unknown_failure_count = 0
    matched_codes: set[str] = set()
    for diagnosis in diagnoses:
        code = str(diagnosis["code"])
        if code == CODE_UNKNOWN_FAILURE:
            unknown_failure_count += 1
        else:
            parsed_failure_count += 1
            matched_codes.add(code)
    return parsed_failure_count, unknown_failure_count, matched_codes


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
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    path.write_bytes(encoded + b"\n")
