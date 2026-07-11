from __future__ import annotations

from collections.abc import Mapping


EFFECTIVE_POLICY_EVIDENCE_FIELDS: tuple[str, ...] = (
    "effective_policy_schema",
    "effective_config_hash",
    "sampling_temperature",
    "sampling_temperature_source",
    "sampling_top_p",
    "sampling_top_p_source",
    "sampling_max_tokens",
    "sampling_max_tokens_source",
    "sampling_policy_lookup_status",
    "sampling_policy_canonical_model",
    "sampling_policy_matched_alias",
    "sampling_policy_source_url",
    "sampling_request_override_applied",
    "recommended_sampling_required",
    "sampling_seed",
    "sampling_seed_source",
    "chat_template_source",
    "chat_template_effective_kwargs_hash",
    "chat_template_request_override_applied",
    "chat_template_forced_override_applied",
    "policy_reasoning_mode",
    "policy_reasoning_source",
)

_EFFECTIVE_POLICY_DEFAULTS: dict[str, object] = {
    "effective_policy_schema": "",
    "effective_config_hash": "",
    "sampling_temperature": 0.0,
    "sampling_temperature_source": "",
    "sampling_top_p": 0.0,
    "sampling_top_p_source": "",
    "sampling_max_tokens": 0,
    "sampling_max_tokens_source": "",
    "sampling_policy_lookup_status": "",
    "sampling_policy_canonical_model": "",
    "sampling_policy_matched_alias": "",
    "sampling_policy_source_url": "",
    "sampling_request_override_applied": False,
    "recommended_sampling_required": False,
    "sampling_seed": 0,
    "sampling_seed_source": "",
    "chat_template_source": "",
    "chat_template_effective_kwargs_hash": "",
    "chat_template_request_override_applied": False,
    "chat_template_forced_override_applied": False,
    "policy_reasoning_mode": "",
    "policy_reasoning_source": "",
}


def empty_effective_policy_evidence() -> dict[str, object]:
    return dict(_EFFECTIVE_POLICY_DEFAULTS)


def effective_policy_evidence_from_receipt(
    receipt: Mapping[str, object] | None,
) -> dict[str, object]:
    evidence = empty_effective_policy_evidence()
    if not isinstance(receipt, Mapping):
        return evidence

    sampling = _mapping(receipt.get("sampling"))
    chat_template = _mapping(receipt.get("chat_template"))
    reasoning = _mapping(receipt.get("reasoning"))

    evidence.update(
        {
            "effective_policy_schema": _string(receipt.get("schema_version")),
            "effective_config_hash": _string(receipt.get("effective_config_hash")),
            "sampling_temperature": _float(sampling.get("temperature")),
            "sampling_temperature_source": _string(sampling.get("temperature_source")),
            "sampling_top_p": _float(sampling.get("top_p")),
            "sampling_top_p_source": _string(sampling.get("top_p_source")),
            "sampling_max_tokens": _int(sampling.get("max_tokens")),
            "sampling_max_tokens_source": _string(sampling.get("max_tokens_source")),
            "sampling_policy_lookup_status": _string(sampling.get("policy_lookup_status")),
            "sampling_policy_canonical_model": _string(sampling.get("policy_canonical_model")),
            "sampling_policy_matched_alias": _string(sampling.get("policy_matched_alias")),
            "sampling_policy_source_url": _string(sampling.get("policy_source_url")),
            "sampling_request_override_applied": _bool(
                sampling.get("request_override_applied")
            ),
            "recommended_sampling_required": _bool(
                sampling.get("recommended_sampling_required")
            ),
            "sampling_seed": _int(sampling.get("seed")),
            "sampling_seed_source": _string(sampling.get("seed_source")),
            "chat_template_source": _string(chat_template.get("source")),
            "chat_template_effective_kwargs_hash": _string(
                chat_template.get("effective_kwargs_hash")
            ),
            "chat_template_request_override_applied": _bool(
                chat_template.get("request_override_applied")
            ),
            "chat_template_forced_override_applied": _bool(
                chat_template.get("forced_override_applied")
            ),
            "policy_reasoning_mode": _string(reasoning.get("mode")),
            "policy_reasoning_source": _string(reasoning.get("source")),
        }
    )
    return evidence


def effective_policy_csv_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return str(value)
    return str(value)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
