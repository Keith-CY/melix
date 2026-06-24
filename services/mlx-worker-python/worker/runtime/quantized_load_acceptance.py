from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QuantizedLoadAcceptanceReceipt:
    native_quantized_load_count: int = 0
    bridge_quantized_fallback_count: int = 0
    cross_shard_metadata_fixup_count: int = 0


def quantized_load_acceptance_counts(
    *,
    quantized_load_mode: str,
    quantized_load_fallback_reason: str,
    quant_profile_id: str,
    cross_shard_metadata_fixup_count: int = 0,
) -> tuple[int, int, int]:
    normalized_mode = str(quantized_load_mode or "").strip()
    normalized_reason = str(quantized_load_fallback_reason or "").strip()
    normalized_profile = str(quant_profile_id or "").strip().lower()
    is_quantized_artifact = normalized_profile not in {"", "none", "fp16", "float16"}

    native_count = 1 if normalized_mode == "native_quantized" else 0
    bridge_fallback_count = (
        1
        if is_quantized_artifact
        and normalized_mode == "fallback"
        and normalized_reason != "not_quantized"
        else 0
    )
    return (
        native_count,
        bridge_fallback_count,
        max(0, int(cross_shard_metadata_fixup_count or 0)),
    )


def quantized_load_acceptance_receipt(
    *,
    quantized_load_mode: str,
    quantized_load_fallback_reason: str,
    quant_profile_id: str,
    cross_shard_metadata_fixup_count: int = 0,
) -> QuantizedLoadAcceptanceReceipt:
    (
        native_count,
        bridge_fallback_count,
        metadata_fixup_count,
    ) = quantized_load_acceptance_counts(
        quantized_load_mode=quantized_load_mode,
        quantized_load_fallback_reason=quantized_load_fallback_reason,
        quant_profile_id=quant_profile_id,
        cross_shard_metadata_fixup_count=cross_shard_metadata_fixup_count,
    )
    return QuantizedLoadAcceptanceReceipt(
        native_quantized_load_count=native_count,
        bridge_quantized_fallback_count=bridge_fallback_count,
        cross_shard_metadata_fixup_count=metadata_fixup_count,
    )
