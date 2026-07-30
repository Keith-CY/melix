from __future__ import annotations

from worker.productization.effective_policy_evidence import (
    effective_policy_csv_value,
    effective_policy_evidence_from_receipt,
    empty_effective_policy_evidence,
)


def test_effective_policy_evidence_defaults_invalid_receipts() -> None:
    assert effective_policy_evidence_from_receipt(None) == empty_effective_policy_evidence()

    evidence = effective_policy_evidence_from_receipt(
        {
            "schema_version": None,
            "effective_config_hash": 123,
            "sampling": "not-a-mapping",
            "chat_template": None,
            "reasoning": [],
        }
    )

    assert evidence["effective_policy_schema"] == ""
    assert evidence["effective_config_hash"] == "123"
    assert evidence["sampling_temperature"] == 0.0
    assert evidence["sampling_max_tokens"] == 0
    assert evidence["sampling_request_override_applied"] is False
    assert evidence["chat_template_source"] == ""
    assert evidence["policy_reasoning_mode"] == ""


def test_effective_policy_evidence_normalizes_typed_fallbacks() -> None:
    evidence = effective_policy_evidence_from_receipt(
        {
            "sampling": {
                "temperature": object(),
                "top_p": "",
                "max_tokens": object(),
                "request_override_applied": "yes",
                "recommended_sampling_required": "0",
                "seed": "",
            },
            "chat_template": {
                "request_override_applied": "on",
                "forced_override_applied": 1,
            },
            "reasoning": {"mode": None, "source": "request"},
        }
    )

    assert evidence["sampling_temperature"] == 0.0
    assert evidence["sampling_top_p"] == 0.0
    assert evidence["sampling_max_tokens"] == 0
    assert evidence["sampling_request_override_applied"] is True
    assert evidence["recommended_sampling_required"] is False
    assert evidence["sampling_seed"] == 0
    assert evidence["chat_template_request_override_applied"] is True
    assert evidence["chat_template_forced_override_applied"] is True
    assert evidence["policy_reasoning_mode"] == ""
    assert evidence["policy_reasoning_source"] == "request"


def test_effective_policy_csv_value_preserves_flat_values() -> None:
    assert effective_policy_csv_value(None) == ""
    assert effective_policy_csv_value("policy") == "policy"
    assert effective_policy_csv_value(True) == "True"
    assert effective_policy_csv_value(42) == "42"
    assert effective_policy_csv_value({"unexpected": "mapping"}) == "{'unexpected': 'mapping'}"
