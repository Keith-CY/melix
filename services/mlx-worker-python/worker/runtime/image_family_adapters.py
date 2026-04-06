from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ImageFamilyDescriptor:
    family_id: str
    default_backend_id: str
    default_task_kind: str
    supports_generation: bool
    supports_edit: bool
    default_workflow_role: str


@dataclass(frozen=True)
class ImageFamilyDetection:
    family_id: str
    source: str
    task_kind: str


@dataclass(frozen=True)
class ResolvedImageFamilyConfig:
    family_id: str
    backend_id: str
    task_kind: str
    supports_generation: bool
    supports_edit: bool
    default_workflow_role: str

    def capability_metadata(self) -> dict[str, str]:
        supported_tasks: list[str] = []
        if self.supports_generation:
            supported_tasks.append("image_generate")
        if self.supports_edit:
            supported_tasks.append("image_edit")

        return {
            "melix.image.backend_id": self.backend_id,
            "melix.image.family_id": self.family_id,
            "melix.image.task_kind": self.task_kind,
            "melix.image.default_workflow_role": self.default_workflow_role,
            "melix.image.supports_generation": "true" if self.supports_generation else "false",
            "melix.image.supports_edit": "true" if self.supports_edit else "false",
            "melix.adapter_set_hash": f"image-family-{self.family_id}",
            "melix.capability.route_kind": "python_image",
            "melix.capability.class": "image_generation",
            "melix.capability.supported_modalities": "text,image",
            "melix.capability.supported_tasks": ",".join(supported_tasks),
            "melix.capability.supported_parsers": "text",
        }


_DEFAULT_IMAGE_FAMILY_ID = "deterministic-v1"
_SUPPORTED_IMAGE_TASK_KINDS = {"text-to-image", "image-text-to-image"}
_IMAGE_FAMILY_ADAPTERS: dict[str, ImageFamilyDescriptor] = {
    "deterministic-v1": ImageFamilyDescriptor(
        family_id="deterministic-v1",
        default_backend_id="deterministic",
        default_task_kind="text-to-image",
        supports_generation=True,
        supports_edit=True,
        default_workflow_role="generate",
    ),
    "kontext-v1": ImageFamilyDescriptor(
        family_id="kontext-v1",
        default_backend_id="deterministic",
        default_task_kind="image-text-to-image",
        supports_generation=True,
        supports_edit=True,
        default_workflow_role="edit",
    ),
    "fill-v1": ImageFamilyDescriptor(
        family_id="fill-v1",
        default_backend_id="deterministic",
        default_task_kind="image-text-to-image",
        supports_generation=False,
        supports_edit=True,
        default_workflow_role="edit",
    ),
    "qwenimage-v1": ImageFamilyDescriptor(
        family_id="qwenimage-v1",
        default_backend_id="deterministic",
        default_task_kind="text-to-image",
        supports_generation=True,
        supports_edit=False,
        default_workflow_role="generate",
    ),
    "fibo-v1": ImageFamilyDescriptor(
        family_id="fibo-v1",
        default_backend_id="deterministic",
        default_task_kind="text-to-image",
        supports_generation=True,
        supports_edit=False,
        default_workflow_role="generate",
    ),
    "klein-v1": ImageFamilyDescriptor(
        family_id="klein-v1",
        default_backend_id="deterministic",
        default_task_kind="image-text-to-image",
        supports_generation=False,
        supports_edit=True,
        default_workflow_role="edit",
    ),
}


def detect_image_family_identity(
    *,
    model_path: str,
    explicit_family_id: str = "",
    explicit_task_kind: str = "",
) -> ImageFamilyDetection:
    normalized_task_kind = _normalized_task_kind(explicit_task_kind)
    normalized_family_id = explicit_family_id.strip().lower()
    if normalized_family_id:
        descriptor = _IMAGE_FAMILY_ADAPTERS.get(normalized_family_id)
        if descriptor is None:
            raise ValueError(f"Unsupported image family adapter: {normalized_family_id}")
        return ImageFamilyDetection(
            family_id=normalized_family_id,
            source="explicit_override",
            task_kind=normalized_task_kind or descriptor.default_task_kind,
        )

    normalized_path = model_path.lower()
    if "kontext" in normalized_path:
        return ImageFamilyDetection(
            family_id="kontext-v1",
            source="directory_name",
            task_kind=normalized_task_kind or "image-text-to-image",
        )
    if "fill" in normalized_path or "inpaint" in normalized_path:
        return ImageFamilyDetection(
            family_id="fill-v1",
            source="directory_name",
            task_kind=normalized_task_kind or "image-text-to-image",
        )
    if "qwenimage" in normalized_path or "qwen-image" in normalized_path:
        return ImageFamilyDetection(
            family_id="qwenimage-v1",
            source="directory_name",
            task_kind=normalized_task_kind or "text-to-image",
        )
    if "fibo" in normalized_path:
        return ImageFamilyDetection(
            family_id="fibo-v1",
            source="directory_name",
            task_kind=normalized_task_kind or "text-to-image",
        )
    if "klein" in normalized_path:
        return ImageFamilyDetection(
            family_id="klein-v1",
            source="directory_name",
            task_kind=normalized_task_kind or "image-text-to-image",
        )
    if normalized_task_kind == "image-text-to-image":
        return ImageFamilyDetection(
            family_id="kontext-v1",
            source="task_kind",
            task_kind=normalized_task_kind,
        )
    return ImageFamilyDetection(
        family_id=_DEFAULT_IMAGE_FAMILY_ID,
        source="default",
        task_kind=normalized_task_kind or "text-to-image",
    )


def resolve_image_family_config(
    metadata: Mapping[str, str] | None = None,
    *,
    model_path: str = "",
    default_task_kind: str = "text-to-image",
) -> ResolvedImageFamilyConfig:
    metadata = dict(metadata or {})
    detection = detect_image_family_identity(
        model_path=model_path,
        explicit_family_id=metadata.get("melix.image.family_id", ""),
        explicit_task_kind=metadata.get("melix.image.task_kind", ""),
    )
    descriptor = _IMAGE_FAMILY_ADAPTERS[detection.family_id]

    supports_generation = _bool_value(
        metadata,
        "melix.image.supports_generation",
        default=descriptor.supports_generation,
    )
    supports_edit = _bool_value(
        metadata,
        "melix.image.supports_edit",
        default=descriptor.supports_edit,
    )
    if supports_generation is False and supports_edit is False:
        if detection.task_kind == "image-text-to-image":
            supports_edit = True
        else:
            supports_generation = True

    resolved_task_kind = _normalized_task_kind(metadata.get("melix.image.task_kind", ""))
    if not resolved_task_kind:
        if supports_generation and not supports_edit:
            resolved_task_kind = "text-to-image"
        elif supports_edit and not supports_generation:
            resolved_task_kind = "image-text-to-image"
        else:
            resolved_task_kind = detection.task_kind or descriptor.default_task_kind

    return ResolvedImageFamilyConfig(
        family_id=detection.family_id,
        backend_id=_string_value(
            metadata,
            "melix.image.backend_id",
            descriptor.default_backend_id,
        ),
        task_kind=resolved_task_kind,
        supports_generation=supports_generation,
        supports_edit=supports_edit,
        default_workflow_role=_string_value(
            metadata,
            "melix.image.default_workflow_role",
            descriptor.default_workflow_role,
        ),
    )


def _normalized_task_kind(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        return ""
    if normalized not in _SUPPORTED_IMAGE_TASK_KINDS:
        raise ValueError(f"Unsupported image task kind: {value}")
    return normalized


def _string_value(metadata: Mapping[str, str], key: str, default: str) -> str:
    value = metadata.get(key, "").strip()
    return value or default


def _bool_value(metadata: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw = metadata.get(key, "").strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off"}:
        return False
    return default
