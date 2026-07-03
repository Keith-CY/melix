from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from packages.protocol.python.worker.v1 import common_pb2

from worker.runtime.multimodal_preprocessing import PreparedVisionRequest


_FEATURE_GATE_KEYS = (
    "melix.vlm.speculative_probe.enabled",
    "melix.multimodal.speculative_probe.enabled",
)


def speculative_probe_enabled(execution_ext: Mapping[str, str] | None) -> bool:
    if not execution_ext:
        return False
    for key in _FEATURE_GATE_KEYS:
        value = str(execution_ext.get(key, "") or "").strip().lower()
        # Keep the operator-facing flag tolerant of existing truthy spellings.
        if value in {"1", "true", "yes", "on", "enabled"}:
            return True
    return False


def empty_speculative_probe_receipt() -> dict[str, object]:
    return {
        "schema": "melix.multimodal.speculative_probe.v1",
        "enabled": False,
        "status": "not_requested",
        "mode": "disabled",
        "fallback_reason": "",
        "draft_model_id": "",
        "num_draft_tokens": 0,
        "media_present": False,
        "image_count": 0,
        "video_count": 0,
        "position_aligned": False,
        "cache_aligned": False,
        "output_mutation_allowed": False,
        "draft_loaded": False,
        "target_decode_started": False,
        "rounds": 0,
        "accepted_tokens": 0,
        "rejected_tokens": 0,
        "acceptance_rate": None,
        "rollback_rate": None,
        "draft_propose_ms": None,
        "target_verify_ms": None,
        "sampling_matches_baseline": False,
    }


@dataclass(frozen=True, slots=True)
class SpeculativeProbeAdmission:
    receipt: dict[str, object]
    fallback_count: int
    draft_model_configured: bool
    num_draft_tokens: int


def build_speculative_probe_receipt(
    *,
    enabled: bool,
    fallback_reason: str,
    loaded_model: Any,
    prepared_request: PreparedVisionRequest,
    acceleration_policy: common_pb2.AccelerationPolicy | None,
    position_metadata_receipt: Mapping[str, object] | None = None,
    sampling_matches_baseline: bool = False,
) -> dict[str, object]:
    """Build the verification-only receipt without loading a drafter.

    ``cache_aligned`` means any cache-layout evidence is available at receipt
    time: a cache identity, a cache scope id, or media position alignment.
    """
    receipt = empty_speculative_probe_receipt()
    receipt["enabled"] = bool(enabled)
    if not enabled:
        return receipt

    draft_model_id = ""
    num_draft_tokens = 0
    if acceleration_policy is not None:
        draft_model_id = str(getattr(acceleration_policy, "draft_model_id", "") or "").strip()
        num_draft_tokens = int(getattr(acceleration_policy, "num_draft_tokens", 0) or 0)

    image_count = len(prepared_request.images or [])
    video_count = len(prepared_request.videos or [])
    media_present = image_count > 0 or video_count > 0
    position_aligned = _position_metadata_aligned(position_metadata_receipt)
    metadata = loaded_model.get("metadata", {}) if isinstance(loaded_model, dict) else {}
    cache_identity = str(metadata.get("cache_identity", "") or "").strip()
    # ``scope_id`` is accepted as the legacy cache-scope spelling emitted by
    # older fast-path fixtures; new receipts should prefer ``cache_scope_id``.
    cache_scope_id = str(metadata.get("scope_id", "") or metadata.get("cache_scope_id", "") or "").strip()
    # Verification-only probes may run before the target/draft cache identity
    # contract exists. In that case, media position alignment is the narrow
    # cache-layout proof we can report without loading a drafter or mutating
    # output.
    cache_aligned = bool(cache_identity or cache_scope_id or position_aligned)

    receipt.update(
        {
            "status": "fallback" if fallback_reason else "admitted",
            "mode": "verification_only",
            "fallback_reason": str(fallback_reason or ""),
            "draft_model_id": draft_model_id,
            "num_draft_tokens": num_draft_tokens,
            "media_present": media_present,
            "image_count": image_count,
            "video_count": video_count,
            "position_aligned": position_aligned,
            "cache_aligned": cache_aligned,
            "output_mutation_allowed": False,
            "draft_loaded": False,
            "target_decode_started": False,
            "sampling_matches_baseline": bool(sampling_matches_baseline),
        }
    )
    return receipt


def build_speculative_runtime_receipt(
    *,
    loaded_model: Any,
    prepared_request: PreparedVisionRequest,
    acceleration_policy: common_pb2.AccelerationPolicy | None,
    position_metadata_receipt: Mapping[str, object] | None = None,
    sampling_matches_baseline: bool,
    rounds: int | None,
    accepted_tokens: int | None,
    rejected_tokens: int | None,
    acceptance_rate: float | None,
    rollback_rate: float | None,
    draft_propose_ms: float | None,
    target_verify_ms: float | None,
) -> dict[str, object]:
    receipt = build_speculative_probe_receipt(
        enabled=True,
        fallback_reason="",
        loaded_model=loaded_model,
        prepared_request=prepared_request,
        acceleration_policy=acceleration_policy,
        position_metadata_receipt=position_metadata_receipt,
        sampling_matches_baseline=sampling_matches_baseline,
    )
    receipt.update(
        {
            "mode": "speculative_decode",
            "output_mutation_allowed": True,
            "draft_loaded": True,
            "target_decode_started": True,
            "rounds": max(0, int(rounds or 0)),
            "accepted_tokens": max(0, int(accepted_tokens or 0)),
            "rejected_tokens": max(0, int(rejected_tokens or 0)),
            "acceptance_rate": acceptance_rate,
            "rollback_rate": rollback_rate,
            "draft_propose_ms": draft_propose_ms,
            "target_verify_ms": target_verify_ms,
        }
    )
    return receipt


def speculative_probe_admission(
    *,
    enabled: bool,
    fallback_reason: str,
    loaded_model: Any,
    prepared_request: PreparedVisionRequest,
    acceleration_policy: common_pb2.AccelerationPolicy | None,
    position_metadata_receipt: Mapping[str, object] | None = None,
    sampling_matches_baseline: bool = False,
) -> SpeculativeProbeAdmission:
    receipt = build_speculative_probe_receipt(
        enabled=enabled,
        fallback_reason=fallback_reason,
        loaded_model=loaded_model,
        prepared_request=prepared_request,
        acceleration_policy=acceleration_policy,
        position_metadata_receipt=position_metadata_receipt,
        sampling_matches_baseline=sampling_matches_baseline,
    )
    return SpeculativeProbeAdmission(
        receipt=receipt,
        fallback_count=1 if enabled and fallback_reason else 0,
        draft_model_configured=bool(receipt["draft_model_id"]),
        num_draft_tokens=int(receipt["num_draft_tokens"] or 0),
    )


def _position_metadata_aligned(position_metadata_receipt: Mapping[str, object] | None) -> bool:
    if not position_metadata_receipt:
        return False
    if str(position_metadata_receipt.get("fallback_reason", "") or "").strip():
        return False
    status = str(position_metadata_receipt.get("status", "") or "").strip()
    # Older position receipts may omit status; positive counters still provide
    # the alignment proof. The counters are independent OR signals because a
    # receipt may report only aggregate media positions or only typed media
    # counts, depending on the fast-path stage that produced it.
    if status and status not in {"ok", "aligned", "not_applicable"}:
        return False
    media_position_count = int(position_metadata_receipt.get("media_position_count", 0) or 0)
    image_count = int(position_metadata_receipt.get("image_count", 0) or 0)
    video_count = int(position_metadata_receipt.get("video_count", 0) or 0)
    return media_position_count > 0 or image_count > 0 or video_count > 0
