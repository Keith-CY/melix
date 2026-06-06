from __future__ import annotations

from worker.model_ops.local_job_remediation import (
    LocalJobRemediationPolicy,
    classify_local_job_failure,
    local_job_remediation_receipt,
)


def test_classifier_maps_common_runtime_logs_to_typed_diagnoses() -> None:
    cases = [
        (
            "RuntimeError: KV cache needs 54.0 GiB but only 8.0 GiB is available",
            "memory_oom",
            "retry_with_changed_flag",
        ),
        (
            "OSError: [Errno 48] Address already in use while binding 127.0.0.1:12436",
            "port_conflict",
            "retry_with_changed_flag",
        ),
        (
            "ModuleNotFoundError: No module named 'sentencepiece'",
            "missing_dependency",
            "dependency_install",
        ),
        (
            "401 Client Error. Cannot access gated repo. You must be authenticated to access this model.",
            "gated_model_access",
            "manual_action",
        ),
        (
            "RuntimeError: invalid device ordinal: GPU index 8 is not available",
            "invalid_accelerator_selection",
            "settings_change",
        ),
    ]

    for log_text, expected_code, expected_operation in cases:
        diagnosis = classify_local_job_failure(log_text, command=["melix", "serve"])

        assert diagnosis is not None
        assert diagnosis.code == expected_code
        assert diagnosis.remediation.operation_type == expected_operation
        assert diagnosis.remediation.summary


def test_remediation_receipt_records_bounded_retry_decision_and_redacts_logs() -> None:
    receipt = local_job_remediation_receipt(
        command=["melix", "serve", "--hf-token", "hf_secret_1234567890"],
        log_text="HF_TOKEN=hf_secret_1234567890\nOSError: [Errno 48] Address already in use",
        policy=LocalJobRemediationPolicy(max_retries=2),
        attempt_index=0,
        outcome="planned",
    )

    assert receipt["schema_version"] == "melix.local_job_remediation_receipt.v1"
    assert receipt["command"] == ["melix", "serve", "--hf-token", "[REDACTED]"]
    assert receipt["diagnosis"]["code"] == "port_conflict"
    assert receipt["remediation"]["operation_type"] == "retry_with_changed_flag"
    assert receipt["decision"] == {
        "mode": "auto",
        "will_retry": True,
        "reason": "retry_budget_available",
        "attempt_index": 0,
        "max_retries": 2,
        "dry_run": False,
        "auto_remediation_enabled": True,
    }
    assert "hf_secret" not in receipt["redacted_log_excerpt"]


def test_retry_budget_dry_run_and_disabled_auto_remediation_stop_execution() -> None:
    log_text = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB"

    exhausted = local_job_remediation_receipt(
        command=["melix", "train"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(max_retries=1),
        attempt_index=1,
        outcome="blocked",
    )
    dry_run = local_job_remediation_receipt(
        command=["melix", "train"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(max_retries=1, dry_run=True),
        attempt_index=0,
        outcome="explained",
    )
    disabled = local_job_remediation_receipt(
        command=["melix", "train"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(max_retries=1, auto_remediation_enabled=False),
        attempt_index=0,
        outcome="blocked",
    )

    assert exhausted["decision"]["will_retry"] is False
    assert exhausted["decision"]["reason"] == "retry_budget_exhausted"
    assert dry_run["decision"]["will_retry"] is False
    assert dry_run["decision"]["mode"] == "dry_run"
    assert dry_run["decision"]["reason"] == "dry_run_explain_only"
    assert disabled["decision"]["will_retry"] is False
    assert disabled["decision"]["mode"] == "disabled"
    assert disabled["decision"]["reason"] == "auto_remediation_disabled"


def test_unclassified_receipt_uses_default_policy_and_requires_manual_action() -> None:
    receipt = local_job_remediation_receipt(
        command=["melix", "inspect", "--token=hf_inline_123456"],
        log_text="custom backend returned an unknown structured error",
        attempt_index=-2,
        outcome="blocked",
    )

    assert classify_local_job_failure("custom backend returned an unknown structured error") is None
    assert receipt["command"] == ["melix", "inspect", "--token=[REDACTED]"]
    assert receipt["diagnosis"] == {
        "code": "unclassified",
        "summary": "The log excerpt did not match a known local-job failure pattern.",
        "matched_pattern": "",
    }
    assert receipt["remediation"]["operation_type"] == "manual_action"
    assert receipt["remediation"]["retryable"] is False
    assert receipt["decision"] == {
        "mode": "manual",
        "will_retry": False,
        "reason": "remediation_requires_operator_action",
        "attempt_index": 0,
        "max_retries": 1,
        "dry_run": False,
        "auto_remediation_enabled": True,
    }


def test_log_excerpt_is_tail_bounded_and_can_be_disabled() -> None:
    bounded = local_job_remediation_receipt(
        command=["melix", "serve", "hf_inline_abcdef"],
        log_text="prefix" + ("a" * 24) + "address already in use",
        policy=LocalJobRemediationPolicy(max_retries=-3, excerpt_bytes=22),
        attempt_index=0,
        outcome="planned",
    )
    disabled = local_job_remediation_receipt(
        command=["melix", "serve"],
        log_text="HF_TOKEN=hf_secret_abcdef address already in use",
        policy=LocalJobRemediationPolicy(excerpt_bytes=0),
        attempt_index=0,
        outcome="planned",
    )

    assert bounded["command"] == ["melix", "serve", "[REDACTED]"]
    assert bounded["redacted_log_excerpt"] == "address already in use"
    assert bounded["decision"]["will_retry"] is False
    assert bounded["decision"]["reason"] == "retry_budget_exhausted"
    assert bounded["decision"]["max_retries"] == 0
    assert disabled["redacted_log_excerpt"] == ""


def test_classifier_and_receipt_diagnosis_use_bounded_tail() -> None:
    log_text = "Address already in use\n" + ("x" * 17000)

    assert classify_local_job_failure(log_text) is None

    receipt = local_job_remediation_receipt(
        command=["melix", "serve"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(excerpt_bytes=64),
        attempt_index=0,
        outcome="blocked",
    )

    assert receipt["redacted_log_excerpt"] == "x" * 64
    assert receipt["diagnosis"]["code"] == "unclassified"
    assert receipt["decision"]["mode"] == "manual"


def test_bounded_tail_does_not_encode_the_full_log() -> None:
    class EncodingTrap(str):
        def __getitem__(self, key: object) -> str:
            return str.__getitem__(self, key)

        def encode(self, *args: object, **kwargs: object) -> bytes:
            raise AssertionError("full log should not be encoded")

    receipt = local_job_remediation_receipt(
        command=["melix", "serve"],
        log_text=EncodingTrap("prefix" + ("a" * 512) + "address already in use"),
        policy=LocalJobRemediationPolicy(excerpt_bytes=22),
        attempt_index=0,
        outcome="planned",
    )

    assert receipt["redacted_log_excerpt"] == "address already in use"
