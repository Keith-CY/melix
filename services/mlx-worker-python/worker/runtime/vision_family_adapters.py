from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from worker.runtime.multimodal_preprocessing import PreparedVisionRequest


@dataclass(frozen=True)
class VisionFamilyDescriptor:
    family_id: str
    prompt_profile_id: str
    tokenization_mode: str
    max_images_per_prompt: int
    supports_tool_calls: bool
    multimodal_adapter_hash: str
    default_prompt_text: str
    image_token_divisor: int
    prompt_token_bias: int


@dataclass(frozen=True)
class ResolvedVisionFamilyConfig:
    family_id: str
    prompt_profile_id: str
    tokenization_mode: str
    max_images_per_prompt: int
    supports_tool_calls: bool
    multimodal_adapter_hash: str
    default_prompt_text: str
    image_token_divisor: int
    prompt_token_bias: int

    def capability_metadata(self) -> dict[str, str]:
        return {
            "vision_family_id": self.family_id,
            "vision_prompt_profile_id": self.prompt_profile_id,
            "vision_tokenization_mode": self.tokenization_mode,
            "vision_max_images_per_prompt": str(self.max_images_per_prompt),
            "vision_supports_tool_calls": "true" if self.supports_tool_calls else "false",
            "multimodal_adapter_hash": self.multimodal_adapter_hash,
        }

    def shape_request(self, prepared_request: PreparedVisionRequest) -> PreparedVisionRequest:
        image_count = len(prepared_request.images)
        if image_count > self.max_images_per_prompt:
            raise ValueError(
                f"Vision family {self.family_id} supports at most "
                f"{self.max_images_per_prompt} image(s) per prompt."
            )

        prompt_text = prepared_request.prompt_text.strip() or self.default_prompt_text
        if prompt_text == prepared_request.prompt_text:
            return prepared_request
        return _with_prompt_text(prepared_request, prompt_text)

    def prompt_token_count(self, prepared_request: PreparedVisionRequest) -> int:
        prompt_tokens = len(prepared_request.prompt_text.split())
        image_tokens = sum(
            max(1, image.byte_length // max(1, self.image_token_divisor))
            for image in prepared_request.images
        )
        return max(1, prompt_tokens + image_tokens + self.prompt_token_bias)


@dataclass(frozen=True)
class VisionFamilyAdapter:
    descriptor: VisionFamilyDescriptor

    def resolve(self, metadata: dict[str, str] | None = None) -> ResolvedVisionFamilyConfig:
        metadata = dict(metadata or {})
        return ResolvedVisionFamilyConfig(
            family_id=self.descriptor.family_id,
            prompt_profile_id=_string_value(
                metadata,
                "vision_prompt_profile_id",
                self.descriptor.prompt_profile_id,
            ),
            tokenization_mode=_string_value(
                metadata,
                "vision_tokenization_mode",
                self.descriptor.tokenization_mode,
            ),
            max_images_per_prompt=_int_value(
                metadata,
                "vision_max_images_per_prompt",
                self.descriptor.max_images_per_prompt,
            ),
            supports_tool_calls=_bool_value(
                metadata,
                "vision_supports_tool_calls",
                self.descriptor.supports_tool_calls,
            ),
            multimodal_adapter_hash=_string_value(
                metadata,
                "melix.multimodal_adapter_hash",
                self.descriptor.multimodal_adapter_hash,
            ),
            default_prompt_text=self.descriptor.default_prompt_text,
            image_token_divisor=self.descriptor.image_token_divisor,
            prompt_token_bias=self.descriptor.prompt_token_bias,
        )


_DEFAULT_FAMILY_ID = "llava-v1"
_VISION_FAMILY_ADAPTERS: dict[str, VisionFamilyAdapter] = {
    "llava-v1": VisionFamilyAdapter(
        descriptor=VisionFamilyDescriptor(
            family_id="llava-v1",
            prompt_profile_id="llava-chatml-v1",
            tokenization_mode="interleaved",
            max_images_per_prompt=8,
            supports_tool_calls=True,
            multimodal_adapter_hash="vision-family-llava-v1",
            default_prompt_text="Describe the image.",
            image_token_divisor=8,
            prompt_token_bias=0,
        )
    ),
    "paligemma-v1": VisionFamilyAdapter(
        descriptor=VisionFamilyDescriptor(
            family_id="paligemma-v1",
            prompt_profile_id="paligemma-caption-v1",
            tokenization_mode="prefix",
            max_images_per_prompt=1,
            supports_tool_calls=False,
            multimodal_adapter_hash="vision-family-paligemma-v1",
            default_prompt_text="Caption the image.",
            image_token_divisor=16,
            prompt_token_bias=2,
        )
    ),
}


def resolve_vision_family_config(metadata: dict[str, str] | None = None) -> ResolvedVisionFamilyConfig:
    metadata = dict(metadata or {})
    family_id = _string_value(metadata, "vision_family_id", _DEFAULT_FAMILY_ID)
    adapter = _VISION_FAMILY_ADAPTERS.get(family_id)
    if adapter is None:
        raise ValueError(f"Unsupported vision family adapter: {family_id}")
    return adapter.resolve(metadata)


def _with_prompt_text(
    prepared_request: PreparedVisionRequest,
    prompt_text: str,
) -> PreparedVisionRequest:
    normalized_prompt_text = prompt_text.strip()
    prompt_hash_hex = hashlib.sha256(normalized_prompt_text.encode("utf-8")).hexdigest()
    multimodal_hash = hashlib.sha256()
    multimodal_hash.update(prompt_hash_hex.encode("ascii"))
    for image in prepared_request.images:
        multimodal_hash.update(image.sha256_hex.encode("ascii"))
    return replace(
        prepared_request,
        prompt_text=normalized_prompt_text,
        prompt_hash_hex=prompt_hash_hex,
        multimodal_hash_hex=multimodal_hash.hexdigest(),
    )


def _string_value(metadata: dict[str, str], key: str, default: str) -> str:
    value = metadata.get(key, "").strip()
    return value or default


def _int_value(metadata: dict[str, str], key: str, default: int) -> int:
    raw_value = metadata.get(key, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return max(1, parsed)


def _bool_value(metadata: dict[str, str], key: str, default: bool) -> bool:
    raw_value = metadata.get(key, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default
