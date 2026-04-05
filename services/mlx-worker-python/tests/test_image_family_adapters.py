from __future__ import annotations

import pytest

from worker.runtime.image_family_adapters import (
    detect_image_family_identity,
    resolve_image_family_config,
)


def test_detect_image_family_identity_supports_explicit_overrides_and_path_inference() -> None:
    explicit = detect_image_family_identity(
        model_path="models/anything",
        explicit_family_id="fill-v1",
        explicit_task_kind="image-text-to-image",
    )
    qwen = detect_image_family_identity(model_path="models/qwen-image-dev")
    fill = detect_image_family_identity(model_path="models/flux-fill-dev")
    kontext = detect_image_family_identity(model_path="models/flux-kontext-dev")
    fibo = detect_image_family_identity(model_path="models/fibo-dev")
    klein = detect_image_family_identity(model_path="models/klein-edit-dev")
    task_kind_fallback = detect_image_family_identity(
        model_path="models/plain-image-dev",
        explicit_task_kind="image-text-to-image",
    )
    fallback = detect_image_family_identity(model_path="models/unknown-image")

    assert explicit.family_id == "fill-v1"
    assert explicit.source == "explicit_override"
    assert explicit.task_kind == "image-text-to-image"
    assert qwen.family_id == "qwenimage-v1"
    assert qwen.task_kind == "text-to-image"
    assert qwen.source == "directory_name"
    assert fill.family_id == "fill-v1"
    assert kontext.family_id == "kontext-v1"
    assert fibo.family_id == "fibo-v1"
    assert klein.family_id == "klein-v1"
    assert task_kind_fallback.family_id == "kontext-v1"
    assert task_kind_fallback.source == "task_kind"
    assert fallback.family_id == "deterministic-v1"
    assert fallback.source == "default"


def test_detect_image_family_identity_rejects_unsupported_values() -> None:
    with pytest.raises(ValueError, match="Unsupported image family adapter"):
        detect_image_family_identity(model_path="models/anything", explicit_family_id="unknown-family")

    with pytest.raises(ValueError, match="Unsupported image task kind"):
        detect_image_family_identity(model_path="models/anything", explicit_task_kind="image-to-text")


def test_resolve_image_family_config_projects_generation_and_edit_roles() -> None:
    qwen = resolve_image_family_config(
        {"melix.image.family_id": "qwenimage-v1"},
        model_path="models/qwen-image-dev",
        default_task_kind="text-to-image",
    )
    fill = resolve_image_family_config(
        {"melix.image.family_id": "fill-v1"},
        model_path="models/flux-fill-dev",
        default_task_kind="image-text-to-image",
    )
    kontext = resolve_image_family_config(
        {"melix.image.family_id": "kontext-v1"},
        model_path="models/flux-kontext-dev",
        default_task_kind="image-text-to-image",
    )

    assert qwen.family_id == "qwenimage-v1"
    assert qwen.task_kind == "text-to-image"
    assert qwen.supports_generation is True
    assert qwen.supports_edit is False
    assert qwen.capability_metadata()["melix.capability.supported_tasks"] == "image_generate"

    assert fill.family_id == "fill-v1"
    assert fill.task_kind == "image-text-to-image"
    assert fill.supports_generation is False
    assert fill.supports_edit is True
    assert fill.capability_metadata()["melix.capability.supported_tasks"] == "image_edit"

    assert kontext.supports_generation is True
    assert kontext.supports_edit is True
    assert kontext.capability_metadata()["melix.capability.supported_tasks"] == "image_generate,image_edit"


def test_resolve_image_family_config_recovers_when_role_flags_are_disabled() -> None:
    edit_only = resolve_image_family_config(
        {
            "melix.image.family_id": "kontext-v1",
            "melix.image.task_kind": "image-text-to-image",
            "melix.image.supports_generation": "false",
            "melix.image.supports_edit": "false",
        },
        model_path="models/flux-kontext-dev",
        default_task_kind="image-text-to-image",
    )
    generate_only = resolve_image_family_config(
        {
            "melix.image.family_id": "deterministic-v1",
            "melix.image.supports_generation": "false",
            "melix.image.supports_edit": "false",
        },
        model_path="models/plain-image-dev",
        default_task_kind="text-to-image",
    )
    bool_false = resolve_image_family_config(
        {
            "melix.image.family_id": "kontext-v1",
            "melix.image.task_kind": "image-text-to-image",
            "melix.image.supports_generation": "false",
            "melix.image.supports_edit": "off",
        },
        model_path="models/flux-kontext-dev",
        default_task_kind="image-text-to-image",
    )

    assert edit_only.supports_generation is False
    assert edit_only.supports_edit is True
    assert generate_only.supports_generation is True
    assert generate_only.supports_edit is False
    assert bool_false.supports_generation is False
    assert bool_false.supports_edit is True
