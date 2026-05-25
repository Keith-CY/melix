from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import math


_VERIFIED_ATTENTION_FAMILIES = frozenset({"gemma4-v1", "llava-v1", "paligemma-v1"})
_DEFAULT_HIDDEN_SIZE = 4096
_DEFAULT_NUM_HIDDEN_LAYERS = 32
_DEFAULT_DTYPE_BYTES = 2
_MIN_PREFILL_STEP_SIZE = 1
_MAX_PREFILL_STEP_SIZE = 8192
_ATTENTION_BUDGET_METADATA_KEYS = (
    "melix.vlm.attention_cost_budget_bytes",
    "melix.vlm.prefill_attention_budget_bytes",
)


@dataclass(frozen=True, slots=True)
class AttentionPrefillPolicyDecision:
    family_id: str
    verified_family: bool
    prompt_tokens: int
    predicted_attention_bytes: int
    budget_bytes: int
    prefill_chunk_mode: str
    selected_prefill_step_size: int
    auto_chunk_reason: str
    refusal_count: int
    error_code: str = ""
    error_message: str = ""
    error_details: dict[str, str] = field(default_factory=dict)


class MultimodalPrefillAttentionBudgetExceeded(RuntimeError):
    def __init__(self, decision: AttentionPrefillPolicyDecision) -> None:
        super().__init__(decision.error_message)
        self.decision = decision

    @property
    def code(self) -> str:
        return self.decision.error_code

    @property
    def details(self) -> dict[str, str]:
        return {
            **self.decision.error_details,
            "auto_chunk_reason": self.decision.auto_chunk_reason,
            "prefill_chunk_mode": self.decision.prefill_chunk_mode,
            "selected_prefill_step_size": str(self.decision.selected_prefill_step_size),
        }


def enforce_attention_prefill_policy(decision: AttentionPrefillPolicyDecision | None) -> None:
    if decision is not None and decision.refusal_count:
        raise MultimodalPrefillAttentionBudgetExceeded(decision)


def int_metadata(metadata: object, *keys: str) -> int:
    if not isinstance(metadata, dict):
        return 0
    for key in keys:
        raw_value = metadata.get(key)
        if raw_value is None or str(raw_value).strip() == "":
            continue
        try:
            return max(0, int(str(raw_value).strip()))
        except ValueError:
            return 0
    return 0


def attention_policy_metadata(
    loaded_model: object,
    execution_ext: object | None = None,
) -> dict[str, object]:
    if not isinstance(loaded_model, dict):
        base: dict[str, object] = {}
    else:
        metadata = loaded_model.get("metadata", {})
        base = dict(metadata) if isinstance(metadata, dict) else {}
        base.update(
            {
                key: value
                for key, value in loaded_model.items()
                if key not in {"metadata", "model", "processor"}
            }
        )
    if isinstance(execution_ext, Mapping):
        base.update(execution_ext)
    return base


def attention_budget_configured(
    loaded_model: object,
    execution_ext: object | None = None,
) -> bool:
    if isinstance(execution_ext, Mapping):
        for key in _ATTENTION_BUDGET_METADATA_KEYS:
            value = execution_ext.get(key)
            if value is not None and str(value).strip():
                return True
    if not isinstance(loaded_model, dict):
        return False
    for key in _ATTENTION_BUDGET_METADATA_KEYS:
        value = loaded_model.get(key)
        if value is not None and str(value).strip():
            return True
    metadata = loaded_model.get("metadata")
    if isinstance(metadata, dict):
        for key in _ATTENTION_BUDGET_METADATA_KEYS:
            value = metadata.get(key)
            if value is not None and str(value).strip():
                return True
    return False


def resolve_attention_prefill_policy(
    *,
    loaded_model: object,
    prepared_request: object,
    seq_len: int | None = None,
    requested_prefill_step_size: int = 0,
    family_config: object | None = None,
    family_config_resolver: Callable[[object], object] | None = None,
    prompt_token_counter: Callable[..., int] | None = None,
    cached_signature: tuple[str, ...] | None = None,
    cached_decision: AttentionPrefillPolicyDecision | None = None,
    execution_ext: object | None = None,
) -> tuple[AttentionPrefillPolicyDecision | None, tuple[str, ...] | None, AttentionPrefillPolicyDecision | None]:
    if not attention_budget_configured(loaded_model, execution_ext=execution_ext):
        return None, cached_signature, cached_decision
    metadata = attention_policy_metadata(loaded_model, execution_ext=execution_ext)
    signature = attention_policy_signature(
        loaded_model=loaded_model,
        prepared_request=prepared_request,
        requested_prefill_step_size=requested_prefill_step_size,
        execution_ext=execution_ext,
    )
    if seq_len is None and cached_signature == signature and cached_decision is not None:
        return cached_decision, cached_signature, cached_decision
    if family_config is None:
        if family_config_resolver is not None:
            family_config = family_config_resolver(loaded_model)
        elif seq_len is None:
            raise ValueError("family_config_resolver is required when no family_config is provided")
    if seq_len is None:
        if prompt_token_counter is None:
            raise ValueError("prompt_token_counter is required when seq_len is not provided")
        seq_len = prompt_token_counter(
            prepared_request,
            loaded_model=loaded_model,
            family_config=family_config,
    )
    decision = choose_attention_prefill_policy(
        family_id=str(
            (getattr(family_config, "family_id", "") if family_config is not None else "")
            or metadata.get("vision_family_id", "")
        ),
        prompt_tokens=seq_len,
        budget_bytes=int_metadata(
            metadata,
            "melix.vlm.attention_cost_budget_bytes",
            "melix.vlm.prefill_attention_budget_bytes",
        ),
        hidden_size=int_metadata(metadata, "melix.vlm.hidden_size", "hidden_size"),
        num_hidden_layers=int_metadata(
            metadata,
            "melix.vlm.num_hidden_layers",
            "melix.vlm.layer_count",
            "num_hidden_layers",
        ),
        dtype_bytes=int_metadata(
            metadata,
            "melix.vlm.attention_dtype_bytes",
            "attention_dtype_bytes",
        ),
        requested_prefill_step_size=requested_prefill_step_size,
    )
    return decision, signature, decision


def resolve_configured_attention_prefill_policy(
    *,
    loaded_model: object,
    prepared_request: object,
    seq_len: int | None = None,
    requested_prefill_step_size: int = 0,
    family_config: object | None = None,
    family_config_resolver: Callable[[object], object] | None = None,
    prompt_token_counter: Callable[..., int] | None = None,
    cached_signature: tuple[str, ...] | None = None,
    cached_decision: AttentionPrefillPolicyDecision | None = None,
    execution_ext: object | None = None,
) -> tuple[AttentionPrefillPolicyDecision | None, tuple[str, ...] | None, AttentionPrefillPolicyDecision | None]:
    if not loaded_model or not attention_budget_configured(loaded_model, execution_ext=execution_ext):
        return None, cached_signature, cached_decision
    return resolve_attention_prefill_policy(
        loaded_model=loaded_model,
        prepared_request=prepared_request,
        seq_len=seq_len,
        requested_prefill_step_size=requested_prefill_step_size,
        family_config=family_config,
        family_config_resolver=family_config_resolver,
        prompt_token_counter=prompt_token_counter,
        cached_signature=cached_signature,
        cached_decision=cached_decision,
        execution_ext=execution_ext,
    )


def attention_policy_signature(
    *,
    loaded_model: object,
    prepared_request: object,
    requested_prefill_step_size: int,
    execution_ext: object | None = None,
) -> tuple[str, ...]:
    metadata = attention_policy_metadata(loaded_model, execution_ext=execution_ext)
    return (
        str(metadata.get("vision_family_id", "")),
        str(metadata.get("melix.vlm.attention_cost_budget_bytes", "")),
        str(metadata.get("melix.vlm.prefill_attention_budget_bytes", "")),
        str(metadata.get("melix.vlm.hidden_size", "")),
        str(metadata.get("hidden_size", "")),
        str(metadata.get("melix.vlm.num_hidden_layers", "")),
        str(metadata.get("melix.vlm.layer_count", "")),
        str(metadata.get("num_hidden_layers", "")),
        str(metadata.get("melix.vlm.attention_dtype_bytes", "")),
        str(metadata.get("attention_dtype_bytes", "")),
        str(max(0, int(requested_prefill_step_size or 0))),
        str(getattr(prepared_request, "prompt_hash_hex", "")),
        str(getattr(prepared_request, "multimodal_hash_hex", "")),
    )


def choose_attention_prefill_policy(
    *,
    family_id: str,
    prompt_tokens: int,
    budget_bytes: int = 0,
    hidden_size: int = _DEFAULT_HIDDEN_SIZE,
    num_hidden_layers: int = _DEFAULT_NUM_HIDDEN_LAYERS,
    dtype_bytes: int = _DEFAULT_DTYPE_BYTES,
    requested_prefill_step_size: int = 0,
) -> AttentionPrefillPolicyDecision:
    normalized_family_id = str(family_id or "").strip()
    normalized_prompt_tokens = max(0, int(prompt_tokens or 0))
    normalized_budget_bytes = max(0, int(budget_bytes or 0))
    predicted_attention_bytes = _predict_attention_bytes(
        token_count=normalized_prompt_tokens,
        hidden_size=hidden_size,
        num_hidden_layers=num_hidden_layers,
        dtype_bytes=dtype_bytes,
    )
    if normalized_family_id not in _VERIFIED_ATTENTION_FAMILIES:
        return AttentionPrefillPolicyDecision(
            family_id=normalized_family_id,
            verified_family=False,
            prompt_tokens=normalized_prompt_tokens,
            predicted_attention_bytes=predicted_attention_bytes,
            budget_bytes=normalized_budget_bytes,
            prefill_chunk_mode="family_unverified",
            selected_prefill_step_size=0,
            auto_chunk_reason="unverified_family_opt_out",
            refusal_count=0,
        )

    requested_step_size = _normalized_requested_step_size(requested_prefill_step_size, normalized_prompt_tokens)
    if normalized_budget_bytes <= 0 or predicted_attention_bytes <= normalized_budget_bytes:
        return AttentionPrefillPolicyDecision(
            family_id=normalized_family_id,
            verified_family=True,
            prompt_tokens=normalized_prompt_tokens,
            predicted_attention_bytes=predicted_attention_bytes,
            budget_bytes=normalized_budget_bytes,
            prefill_chunk_mode="whole_prefill",
            selected_prefill_step_size=requested_step_size or normalized_prompt_tokens,
            auto_chunk_reason="",
            refusal_count=0,
        )

    conservative_step_size = _conservative_step_size(
        budget_bytes=normalized_budget_bytes,
        hidden_size=hidden_size,
        num_hidden_layers=num_hidden_layers,
        dtype_bytes=dtype_bytes,
    )
    if requested_step_size:
        conservative_step_size = min(conservative_step_size, requested_step_size)
    if conservative_step_size >= _MIN_PREFILL_STEP_SIZE:
        return AttentionPrefillPolicyDecision(
            family_id=normalized_family_id,
            verified_family=True,
            prompt_tokens=normalized_prompt_tokens,
            predicted_attention_bytes=predicted_attention_bytes,
            budget_bytes=normalized_budget_bytes,
            prefill_chunk_mode="auto_chunk",
            selected_prefill_step_size=conservative_step_size,
            auto_chunk_reason="attention_budget_auto_chunked",
            refusal_count=0,
        )

    details = {
        "family_id": normalized_family_id,
        "prompt_tokens": str(normalized_prompt_tokens),
        "predicted_attention_bytes": str(predicted_attention_bytes),
        "attention_budget_bytes": str(normalized_budget_bytes),
    }
    return AttentionPrefillPolicyDecision(
        family_id=normalized_family_id,
        verified_family=True,
        prompt_tokens=normalized_prompt_tokens,
        predicted_attention_bytes=predicted_attention_bytes,
        budget_bytes=normalized_budget_bytes,
        prefill_chunk_mode="refused",
        selected_prefill_step_size=0,
        auto_chunk_reason="attention_budget_exceeded",
        refusal_count=1,
        error_code="multimodal_prefill_attention_budget_exceeded",
        error_message="Predicted multimodal prefill attention memory exceeds the active budget.",
        error_details=details,
    )


def build_attention_budget_receipt(decision: AttentionPrefillPolicyDecision | None) -> dict[str, object]:
    if decision is None:
        return {}
    return {
        "attention_budget_verified_family": decision.verified_family,
        "attention_budget_family_id": decision.family_id,
        "attention_budget_prompt_tokens": decision.prompt_tokens,
        "predicted_attention_bytes": decision.predicted_attention_bytes,
        "attention_budget_bytes": decision.budget_bytes,
        "prefill_chunk_mode": decision.prefill_chunk_mode,
        "selected_prefill_step_size": decision.selected_prefill_step_size,
        "auto_chunk_reason": decision.auto_chunk_reason,
        "attention_budget_refusal_count": decision.refusal_count,
    }


def _predict_attention_bytes(
    *,
    token_count: int,
    hidden_size: int,
    num_hidden_layers: int,
    dtype_bytes: int,
) -> int:
    normalized_token_count = max(0, int(token_count or 0))
    if normalized_token_count <= 0:
        return 0
    per_token_bytes = _per_token_attention_bytes(
        hidden_size=hidden_size,
        num_hidden_layers=num_hidden_layers,
        dtype_bytes=dtype_bytes,
    )
    return normalized_token_count * normalized_token_count * per_token_bytes


def _conservative_step_size(
    *,
    budget_bytes: int,
    hidden_size: int,
    num_hidden_layers: int,
    dtype_bytes: int,
) -> int:
    normalized_budget_bytes = max(0, int(budget_bytes or 0))
    if normalized_budget_bytes <= 0:
        return 0
    per_token_bytes = _per_token_attention_bytes(
        hidden_size=hidden_size,
        num_hidden_layers=num_hidden_layers,
        dtype_bytes=dtype_bytes,
    )
    if per_token_bytes <= 0:
        return 0
    return min(_MAX_PREFILL_STEP_SIZE, max(0, int(math.sqrt(normalized_budget_bytes / per_token_bytes))))


def _per_token_attention_bytes(*, hidden_size: int, num_hidden_layers: int, dtype_bytes: int) -> int:
    normalized_hidden_size = max(1, int(hidden_size or _DEFAULT_HIDDEN_SIZE))
    normalized_layers = max(1, int(num_hidden_layers or _DEFAULT_NUM_HIDDEN_LAYERS))
    normalized_dtype_bytes = max(1, int(dtype_bytes or _DEFAULT_DTYPE_BYTES))
    return normalized_hidden_size * normalized_layers * normalized_dtype_bytes


def _normalized_requested_step_size(value: int, prompt_tokens: int) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    if parsed <= 0:
        return 0
    prompt_limit = max(1, int(prompt_tokens or 0))
    return min(_MAX_PREFILL_STEP_SIZE, prompt_limit, parsed)
