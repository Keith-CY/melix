from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence


RECEIPT_SCHEMA_VERSION = "melix.local_job_remediation_receipt.v1"
DEFAULT_EXCERPT_BYTES = 16 * 1024

_TOKEN_ARGUMENTS = {
    "--hf-token",
    "--huggingface-token",
    "--token",
}
_ENV_TOKEN_PATTERN = re.compile(
    r"\b(HF_TOKEN|HUGGINGFACE_HUB_TOKEN|MELIX_HF_TOKEN|MELIX_HUGGINGFACE_TOKEN)=([^\s]+)",
    flags=re.IGNORECASE,
)
_HF_TOKEN_PATTERN = re.compile(r"\bhf_[A-Za-z0-9][A-Za-z0-9_\-=]{5,}")


@dataclass(frozen=True, slots=True)
class LocalJobRemediation:
    operation_type: str
    summary: str
    action: str
    retryable: bool
    changed_flags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_type": self.operation_type,
            "summary": self.summary,
            "action": self.action,
            "retryable": self.retryable,
            "changed_flags": dict(self.changed_flags),
        }


@dataclass(frozen=True, slots=True)
class LocalJobFailureDiagnosis:
    code: str
    summary: str
    remediation: LocalJobRemediation
    matched_pattern: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "summary": self.summary,
            "matched_pattern": self.matched_pattern,
        }


@dataclass(frozen=True, slots=True)
class LocalJobRemediationPolicy:
    max_retries: int = 1
    dry_run: bool = False
    auto_remediation_enabled: bool = True
    excerpt_bytes: int = DEFAULT_EXCERPT_BYTES


@dataclass(frozen=True, slots=True)
class _DiagnosisRule:
    code: str
    summary: str
    patterns: tuple[str, ...]
    remediation: LocalJobRemediation


_DIAGNOSIS_RULES: tuple[_DiagnosisRule, ...] = (
    _DiagnosisRule(
        code="memory_oom",
        summary="The local runtime exhausted memory while preparing or running the job.",
        patterns=(
            "kv cache",
            "out of memory",
            "cuda out of memory",
            "metal out of memory",
            "allocation failed",
        ),
        remediation=LocalJobRemediation(
            operation_type="retry_with_changed_flag",
            summary="Retry with a smaller runtime footprint.",
            action="Lower context length, batch size, or parallelism before retrying.",
            retryable=True,
            changed_flags={
                "--max-context-tokens": "lower",
                "--batch-size": "lower",
                "--parallelism": "lower",
            },
        ),
    ),
    _DiagnosisRule(
        code="port_conflict",
        summary="The local service could not bind because the requested port is already in use.",
        patterns=(
            "address already in use",
            "eaddrinuse",
            "bind() failed",
            "port is already in use",
        ),
        remediation=LocalJobRemediation(
            operation_type="retry_with_changed_flag",
            summary="Retry with a different local port.",
            action="Choose an available HTTP port or stop the conflicting process.",
            retryable=True,
            changed_flags={"--port": "available-port"},
        ),
    ),
    _DiagnosisRule(
        code="missing_dependency",
        summary="The job could not start because a required local dependency is missing.",
        patterns=(
            "modulenotfounderror",
            "no module named",
            "command not found",
            "no such file or directory",
        ),
        remediation=LocalJobRemediation(
            operation_type="dependency_install",
            summary="Install or restore the missing dependency before retrying.",
            action="Run the repository bootstrap command or install the named dependency in the job environment.",
            retryable=False,
        ),
    ),
    _DiagnosisRule(
        code="gated_model_access",
        summary="The model repository requires authenticated or approved access.",
        patterns=(
            "gated repo",
            "gated repository",
            "401 client error",
            "403 client error",
            "hf token",
            "hugging face authentication",
            "must be authenticated",
        ),
        remediation=LocalJobRemediation(
            operation_type="manual_action",
            summary="Authenticate and confirm model access before retrying.",
            action="Provide a valid Hugging Face token and accept the model license or access gate.",
            retryable=False,
        ),
    ),
    _DiagnosisRule(
        code="invalid_accelerator_selection",
        summary="The job requested an accelerator device that is not available on this host.",
        patterns=(
            "invalid device ordinal",
            "gpu index",
            "no such device",
            "invalid accelerator",
            "accelerator selection",
        ),
        remediation=LocalJobRemediation(
            operation_type="settings_change",
            summary="Change the requested accelerator settings before retrying.",
            action="Select an available local device or disable the unsupported accelerator override.",
            retryable=False,
        ),
    ),
)


def classify_local_job_failure(
    log_text: str,
    *,
    command: Sequence[str] = (),
    excerpt_bytes: int = DEFAULT_EXCERPT_BYTES,
) -> LocalJobFailureDiagnosis | None:
    bounded_log = _bounded_tail(log_text, max_bytes=excerpt_bytes)
    haystack = _normalized_text(" ".join((*command, bounded_log)))
    for rule in _DIAGNOSIS_RULES:
        for pattern in rule.patterns:
            if pattern in haystack:
                return LocalJobFailureDiagnosis(
                    code=rule.code,
                    summary=rule.summary,
                    remediation=rule.remediation,
                    matched_pattern=pattern,
                )
    return None


def local_job_remediation_receipt(
    *,
    command: Sequence[str],
    log_text: str,
    policy: LocalJobRemediationPolicy | None = None,
    attempt_index: int,
    outcome: str,
) -> dict[str, Any]:
    resolved_policy = policy or LocalJobRemediationPolicy()
    bounded_log = _bounded_tail(log_text, max_bytes=resolved_policy.excerpt_bytes)
    redacted_log_excerpt = _redact_log_text(bounded_log)
    diagnosis = classify_local_job_failure(
        bounded_log,
        command=command,
        excerpt_bytes=resolved_policy.excerpt_bytes,
    )
    remediation = diagnosis.remediation if diagnosis is not None else _unclassified_remediation()
    decision = _remediation_decision(
        remediation=remediation,
        policy=resolved_policy,
        attempt_index=attempt_index,
    )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "command": _redacted_command(command),
        "redacted_log_excerpt": redacted_log_excerpt,
        "diagnosis": diagnosis.to_dict() if diagnosis is not None else _unclassified_diagnosis(),
        "remediation": remediation.to_dict(),
        "decision": decision,
        "outcome": str(outcome),
    }


def _remediation_decision(
    *,
    remediation: LocalJobRemediation,
    policy: LocalJobRemediationPolicy,
    attempt_index: int,
) -> dict[str, Any]:
    max_retries = max(0, int(policy.max_retries))
    normalized_attempt = max(0, int(attempt_index))
    base = {
        "attempt_index": normalized_attempt,
        "max_retries": max_retries,
        "dry_run": bool(policy.dry_run),
        "auto_remediation_enabled": bool(policy.auto_remediation_enabled),
    }
    if policy.dry_run:
        return {
            "mode": "dry_run",
            "will_retry": False,
            "reason": "dry_run_explain_only",
            **base,
        }
    if not policy.auto_remediation_enabled:
        return {
            "mode": "disabled",
            "will_retry": False,
            "reason": "auto_remediation_disabled",
            **base,
        }
    if not remediation.retryable:
        return {
            "mode": "manual",
            "will_retry": False,
            "reason": "remediation_requires_operator_action",
            **base,
        }
    if normalized_attempt >= max_retries:
        return {
            "mode": "auto",
            "will_retry": False,
            "reason": "retry_budget_exhausted",
            **base,
        }
    return {
        "mode": "auto",
        "will_retry": True,
        "reason": "retry_budget_available",
        **base,
    }


def _redacted_command(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for raw_part in command:
        part = str(raw_part)
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue
        option, separator, value = part.partition("=")
        if option in _TOKEN_ARGUMENTS:
            if separator:
                redacted.append(f"{option}=[REDACTED]")
            else:
                redacted.append(part)
                redact_next = True
            continue
        if _HF_TOKEN_PATTERN.search(part):
            redacted.append(_HF_TOKEN_PATTERN.sub("[REDACTED]", part))
            continue
        redacted.append(part)
    return redacted


def _redacted_log_excerpt(log_text: str, *, excerpt_bytes: int) -> str:
    return _redact_log_text(_bounded_tail(log_text, max_bytes=excerpt_bytes))


def _bounded_tail(value: str, *, max_bytes: int) -> str:
    limit = max(0, int(max_bytes))
    if limit == 0:
        return ""
    if len(value) > limit:
        value = value[-limit:]
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[-limit:].decode("utf-8", errors="replace")


def _redact_log_text(value: str) -> str:
    value = _ENV_TOKEN_PATTERN.sub(r"\1=[REDACTED]", value)
    return _HF_TOKEN_PATTERN.sub("[REDACTED]", value)


def _normalized_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _unclassified_remediation() -> LocalJobRemediation:
    return LocalJobRemediation(
        operation_type="manual_action",
        summary="No automatic remediation is available for this log excerpt.",
        action="Inspect the redacted log excerpt and rerun with additional diagnostics if needed.",
        retryable=False,
    )


def _unclassified_diagnosis() -> dict[str, str]:
    return {
        "code": "unclassified",
        "summary": "The log excerpt did not match a known local-job failure pattern.",
        "matched_pattern": "",
    }
