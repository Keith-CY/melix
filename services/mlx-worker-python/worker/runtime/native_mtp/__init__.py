from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PATCHED = False
_MTP_ACTIVE = False
_MTP_WEIGHT_ATTACHMENT_ACTIVE = False


def set_mtp_active(active: bool) -> None:
    global _MTP_ACTIVE
    _MTP_ACTIVE = bool(active)


def is_mtp_active() -> bool:
    return _MTP_ACTIVE


def set_mtp_weight_attachment(active: bool) -> None:
    global _MTP_WEIGHT_ATTACHMENT_ACTIVE
    _MTP_WEIGHT_ATTACHMENT_ACTIVE = bool(active)


def should_attach_mtp_head() -> bool:
    return _MTP_WEIGHT_ATTACHMENT_ACTIVE


def apply_native_mtp_patches() -> bool:
    """Apply Melix native-MTP patches for Qwen3.5/Qwen3.6 serving."""
    global _PATCHED
    if _PATCHED:
        return True

    from . import batch_generator, cache_rollback, mlx_lm_loader, qwen35_model, qwen35_vlm_model, qwen35_vlm_runtime

    if not cache_rollback.apply():
        return False
    loader_patched = mlx_lm_loader.apply()
    qwen_text_model_patched = qwen35_model.apply()
    qwen_model_patched = qwen35_vlm_model.apply()
    qwen_runtime_patched = qwen35_vlm_runtime.apply()
    batch_generator_patched = batch_generator.apply()
    if not batch_generator_patched or not loader_patched:
        return False
    if not qwen_text_model_patched and not qwen_runtime_patched:
        return False
    if not qwen_text_model_patched:
        logger.debug("Qwen3.5/Qwen3.6 text MTP model patch did not apply.")
    if not qwen_runtime_patched:
        logger.debug("Qwen3.5/Qwen3.6 VLM runtime MTP patch did not apply.")
    if not qwen_model_patched:
        logger.debug("Qwen3.5/Qwen3.6 VLM sanitize patch did not apply.")

    _PATCHED = True
    logger.info("Melix native MTP patches applied for Qwen3.5/Qwen3.6.")
    return True
