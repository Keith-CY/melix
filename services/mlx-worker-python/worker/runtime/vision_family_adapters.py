from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from worker.runtime.multimodal_preprocessing import PreparedVisionRequest, rebuild_multimodal_hash
from worker.runtime.token_counting import whitespace_token_count as _whitespace_token_count


@dataclass(frozen=True)
class VisionFamilyDescriptor:
    family_id: str
    prompt_profile_id: str
    tokenization_mode: str
    max_images_per_prompt: int
    max_videos_per_prompt: int
    supports_tool_calls: bool
    multimodal_adapter_hash: str
    default_prompt_text: str
    default_video_prompt_text: str
    image_token_divisor: int
    prompt_token_bias: int
    video_frame_token_cost: int


@dataclass(frozen=True)
class ResolvedVisionFamilyConfig:
    family_id: str
    prompt_profile_id: str
    tokenization_mode: str
    max_images_per_prompt: int
    max_videos_per_prompt: int
    supports_tool_calls: bool
    multimodal_adapter_hash: str
    default_prompt_text: str
    default_video_prompt_text: str
    image_token_divisor: int
    prompt_token_bias: int
    video_frame_token_cost: int

    def capability_metadata(self) -> dict[str, str]:
        return {
            "vision_family_id": self.family_id,
            "vision_prompt_profile_id": self.prompt_profile_id,
            "vision_tokenization_mode": self.tokenization_mode,
            "vision_max_images_per_prompt": str(self.max_images_per_prompt),
            "vision_max_videos_per_prompt": str(self.max_videos_per_prompt),
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
        video_count = len(prepared_request.videos)
        if video_count > self.max_videos_per_prompt:
            raise ValueError(
                f"Vision family {self.family_id} supports at most "
                f"{self.max_videos_per_prompt} video input(s) per prompt."
            )

        default_prompt_text = (
            self.default_video_prompt_text
            if prepared_request.videos and not prepared_request.images
            else self.default_prompt_text
        )
        prompt_text = prepared_request.prompt_text.strip() or default_prompt_text
        if prompt_text == prepared_request.prompt_text:
            return prepared_request
        return _with_prompt_text(prepared_request, prompt_text)

    def prompt_token_count(self, prepared_request: PreparedVisionRequest) -> int:
        prompt_tokens = _whitespace_token_count(prepared_request.prompt_text)

        image_token_divisor = self.image_token_divisor
        if image_token_divisor < 1:
            image_token_divisor = 1
        image_tokens = 0
        for image in prepared_request.images:
            token_count = len(image.bytes_data) // image_token_divisor
            image_tokens += token_count if token_count > 1 else 1

        video_frame_token_cost = self.video_frame_token_cost
        if video_frame_token_cost < 1:
            video_frame_token_cost = 1
        video_frame_count = 0
        empty_video_frame_policies = 0
        for policy in prepared_request.video_frame_policies:
            effective_frame_count = policy.effective_frame_count
            if effective_frame_count > 0:
                video_frame_count += effective_frame_count
            else:
                empty_video_frame_policies += 1
        video_tokens = video_frame_count * video_frame_token_cost + empty_video_frame_policies

        total_tokens = prompt_tokens + image_tokens + video_tokens + self.prompt_token_bias
        return total_tokens if total_tokens > 1 else 1


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
            max_videos_per_prompt=_int_value(
                metadata,
                "vision_max_videos_per_prompt",
                self.descriptor.max_videos_per_prompt,
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
            default_video_prompt_text=self.descriptor.default_video_prompt_text,
            image_token_divisor=self.descriptor.image_token_divisor,
            prompt_token_bias=self.descriptor.prompt_token_bias,
            video_frame_token_cost=self.descriptor.video_frame_token_cost,
        )


_DEFAULT_FAMILY_ID = "llava-v1"
_VISION_FAMILY_ADAPTERS: dict[str, VisionFamilyAdapter] = {
    "llava-v1": VisionFamilyAdapter(
        descriptor=VisionFamilyDescriptor(
            family_id="llava-v1",
            prompt_profile_id="llava-chatml-v1",
            tokenization_mode="interleaved",
            max_images_per_prompt=8,
            max_videos_per_prompt=1,
            supports_tool_calls=True,
            multimodal_adapter_hash="vision-family-llava-v1",
            default_prompt_text="Describe the image.",
            default_video_prompt_text="Describe the video.",
            image_token_divisor=8,
            prompt_token_bias=0,
            video_frame_token_cost=4,
        )
    ),
    "paligemma-v1": VisionFamilyAdapter(
        descriptor=VisionFamilyDescriptor(
            family_id="paligemma-v1",
            prompt_profile_id="paligemma-caption-v1",
            tokenization_mode="prefix",
            max_images_per_prompt=1,
            max_videos_per_prompt=1,
            supports_tool_calls=False,
            multimodal_adapter_hash="vision-family-paligemma-v1",
            default_prompt_text="Caption the image.",
            default_video_prompt_text="Caption the video.",
            image_token_divisor=16,
            prompt_token_bias=2,
            video_frame_token_cost=3,
        )
    ),
    "gemma4-v1": VisionFamilyAdapter(
        descriptor=VisionFamilyDescriptor(
            family_id="gemma4-v1",
            prompt_profile_id="gemma4-chatml-v1",
            tokenization_mode="interleaved",
            max_images_per_prompt=8,
            max_videos_per_prompt=1,
            supports_tool_calls=True,
            multimodal_adapter_hash="vision-family-gemma4-v1",
            default_prompt_text="Describe the image.",
            default_video_prompt_text="Describe the video.",
            image_token_divisor=8,
            prompt_token_bias=1,
            video_frame_token_cost=4,
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
    return replace(
        prepared_request,
        prompt_text=normalized_prompt_text,
        prompt_hash_hex=prompt_hash_hex,
        multimodal_hash_hex=rebuild_multimodal_hash(prepared_request, prompt_hash_hex),
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
