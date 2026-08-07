from __future__ import annotations

import logging

from worker.runtime.native_mtp.capability import NativeMTPCapabilityDecision


def apply_native_mtp_preload_decision(
    decision: NativeMTPCapabilityDecision,
    *,
    model_path: str,
    failure_logger: logging.Logger | None = None,
) -> dict[str, str]:
    active = False
    patch_applied = False
    reason: str | None = None
    native_mtp_module = None
    try:
        from worker.runtime import native_mtp as native_mtp_module

        native_mtp_module.set_mtp_active(False)
        native_mtp_module.set_mtp_weight_attachment(False)
        patch_allowed = (
            decision.patchable
            and decision.enabled
            and decision.weights_present
            and decision.refusal_reason == ""
            and decision.hardware_gate == "admitted"
        )
        if patch_allowed:
            native_mtp_module.set_mtp_weight_attachment(decision.weights_present)
            patch_applied = native_mtp_module.apply_native_mtp_patches()
            active = bool(patch_applied)
        native_mtp_module.set_mtp_active(active)
    except Exception as exc:  # pragma: no cover - defensive runtime guard.
        if failure_logger is not None:
            failure_logger.warning("Native MTP preload patch failed for %s: %s", model_path, exc)
        reason = "patch_error"
        if native_mtp_module is not None:
            try:
                native_mtp_module.set_mtp_active(False)
                native_mtp_module.set_mtp_weight_attachment(False)
            except Exception:
                pass

    return decision.to_metadata(patch_applied=patch_applied, active=active, reason=reason)
