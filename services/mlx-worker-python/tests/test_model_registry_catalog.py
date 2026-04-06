from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from worker.model_registry.catalog import WorkerModelCatalog


def _write_registry_manifest(
    variant_dir: Path,
    *,
    model_id: str,
    model_kind: str = "text",
    quant_profile_id: str = "q4",
    max_context: int = 8192,
    ext: dict[str, str] | None = None,
    manifest_fields: dict[str, object] | None = None,
) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "melix.model_registry_manifest.v1",
        "model_id": model_id,
        "model_kind": model_kind,
        "quant_profile_id": quant_profile_id,
        "max_context": max_context,
        "ext": ext or {},
    }
    if manifest_fields:
        payload.update(manifest_fields)
    (variant_dir / "manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _expected_root_id(root: Path) -> str:
    digest = hashlib.sha1(os.fspath(root.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"root-{digest}"


def _write_model_config(variant_dir: Path, payload: dict[str, object]) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "config.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_registry_snapshot_collects_models_from_ordered_roots_and_keeps_first_duplicate(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    duplicate_id = "mlx-community/Qwen2.5-7B-Instruct/4bit"

    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=16384,
        ext={"source_root": "a"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=4096,
        ext={"source_root": "b"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-14B-Instruct" / "8bit",
        model_id="mlx-community/Qwen2.5-14B-Instruct/8bit",
        quant_profile_id="q8",
        max_context=32768,
        ext={"source_root": "b"},
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": f"{root_a}{os.pathsep}{root_b}",
        }
    )

    snapshot = catalog.registry_snapshot()

    assert [root.root_id for root in snapshot.roots] == [_expected_root_id(root_a), _expected_root_id(root_b)]
    assert [root.root_order for root in snapshot.roots] == [1, 2]
    discovered = {model.model_id: model for model in snapshot.models}
    assert duplicate_id in discovered
    assert discovered[duplicate_id].max_context == 16384
    assert discovered[duplicate_id].ext["source_root"] == "a"
    assert discovered[duplicate_id].ext["melix.registry_root_id"] == _expected_root_id(root_a)
    assert discovered[duplicate_id].ext["melix.registry_root_order"] == "1"
    assert discovered[duplicate_id].ext["melix.model_path"].endswith("root-a/mlx-community/Qwen2.5-7B-Instruct/4bit")
    assert "mlx-community/Qwen2.5-14B-Instruct/8bit" in discovered
    assert catalog.get(duplicate_id) == discovered[duplicate_id]


def test_registry_snapshot_reports_invalid_roots_without_poisoning_valid_discovery(tmp_path: Path) -> None:
    root_valid = tmp_path / "root-valid"
    root_missing = tmp_path / "root-missing"

    _write_registry_manifest(
        root_valid / "mlx-community" / "Phi-4-mini" / "4bit",
        model_id="mlx-community/Phi-4-mini/4bit",
        ext={"source_root": "valid"},
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": f"{root_missing}{os.pathsep}{root_valid}",
        }
    )

    snapshot = catalog.registry_snapshot()

    assert len(snapshot.roots) == 2
    assert snapshot.roots[0].root_id == _expected_root_id(root_missing)
    assert snapshot.roots[0].root_order == 1
    assert snapshot.roots[0].accessible is False
    assert snapshot.roots[0].error_code == "not_found"
    assert snapshot.roots[1].root_id == _expected_root_id(root_valid)
    assert snapshot.roots[1].root_order == 2
    assert snapshot.roots[1].accessible is True
    assert [model.model_id for model in snapshot.models] == ["mlx-community/Phi-4-mini/4bit"]


def test_registry_snapshot_keeps_seed_models_alongside_discovered_entries(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    _write_registry_manifest(
        root_a / "mlx-community" / "Llama-3.2-3B" / "q4",
        model_id="mlx-community/Llama-3.2-3B/q4",
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": str(root_a),
        }
    )

    snapshot = catalog.registry_snapshot()
    discovered_ids = {model.model_id for model in snapshot.models}

    assert "mlx-community/Llama-3.2-3B/q4" in discovered_ids
    assert "melix-dev-text" in {model.model_id for model in catalog.all_models()}


def test_registry_snapshot_rescan_refreshes_discovery_and_deduplicates_empty_root_entries(tmp_path: Path) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_b.mkdir(parents=True, exist_ok=True)

    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": f"{os.pathsep}{root_a}{os.pathsep}{root_a}{os.pathsep}{root_b}{os.pathsep}",
        }
    )

    initial_snapshot = catalog.registry_snapshot()
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-14B-Instruct" / "8bit",
        model_id="mlx-community/Qwen2.5-14B-Instruct/8bit",
        quant_profile_id="q8",
    )
    refreshed_snapshot = catalog.registry_snapshot(rescan=True)

    assert [root.root_path for root in initial_snapshot.roots] == [str(root_a), str(root_b)]
    assert [root.root_path for root in refreshed_snapshot.roots] == [str(root_a), str(root_b)]
    assert [root.root_id for root in initial_snapshot.roots] == [root.root_id for root in refreshed_snapshot.roots]
    assert [model.model_id for model in initial_snapshot.models] == ["mlx-community/Qwen2.5-7B-Instruct/4bit"]
    assert [model.model_id for model in refreshed_snapshot.models] == [
        "mlx-community/Qwen2.5-14B-Instruct/8bit",
        "mlx-community/Qwen2.5-7B-Instruct/4bit",
    ]
    assert catalog.get("mlx-community/Qwen2.5-14B-Instruct/8bit") is not None


def test_registry_snapshot_explicit_root_override_reorders_precedence_without_changing_root_identity(
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    duplicate_id = "mlx-community/Qwen2.5-7B-Instruct/4bit"

    _write_registry_manifest(
        root_a / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=16384,
        ext={"source_root": "a"},
    )
    _write_registry_manifest(
        root_b / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id=duplicate_id,
        max_context=4096,
        ext={"source_root": "b"},
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root_a)})

    initial_snapshot = catalog.registry_snapshot()
    reordered_snapshot = catalog.registry_snapshot(
        rescan=True,
        registry_roots=[os.fspath(root_b), os.fspath(root_a)],
    )
    discovered = {model.model_id: model for model in reordered_snapshot.models}

    assert [root.root_id for root in reordered_snapshot.roots] == [_expected_root_id(root_b), _expected_root_id(root_a)]
    assert discovered[duplicate_id].ext["source_root"] == "b"
    assert discovered[duplicate_id].ext["melix.registry_root_id"] == _expected_root_id(root_b)
    assert discovered[duplicate_id].ext["melix.registry_root_order"] == "1"
    assert initial_snapshot.roots[0].root_id == _expected_root_id(root_a)


def test_registry_snapshot_derives_structured_identity_from_paths_and_sidecar_overrides(tmp_path: Path) -> None:
    root = tmp_path / "root"

    _write_registry_manifest(
        root / "huggingface" / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
        manifest_fields={
            "provider_id": "hf-mirror",
            "variant_id": "q4f16",
        },
    )
    _write_registry_manifest(
        root / "mlx-community" / "Phi-4-mini" / "q8",
        model_id="mlx-community/Phi-4-mini/q8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    qwen = discovered["mlx-community/Qwen2.5-7B-Instruct/4bit"]
    phi = discovered["mlx-community/Phi-4-mini/q8"]

    assert qwen.ext["melix.registry_provider_id"] == "hf-mirror"
    assert qwen.ext["melix.registry_organization_id"] == "mlx-community"
    assert qwen.ext["melix.registry_model_name"] == "Qwen2.5-7B-Instruct"
    assert qwen.ext["melix.registry_variant_id"] == "q4f16"
    assert qwen.ext["melix.registry_relative_path"] == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit"
    assert phi.ext["melix.registry_provider_id"] == ""
    assert phi.ext["melix.registry_organization_id"] == "mlx-community"
    assert phi.ext["melix.registry_model_name"] == "Phi-4-mini"
    assert phi.ext["melix.registry_variant_id"] == "q8"
    assert phi.ext["melix.registry_relative_path"] == "mlx-community/Phi-4-mini/q8"


def test_registry_snapshot_applies_text_family_adapter_metadata_from_local_config(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Qwen3-MoE-30B-A3B-Instruct" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "qwen3_moe",
            "rope_scaling": {"type": "yarn", "interleaved": True},
            "num_local_experts": 128,
            "moe_gate_dequant": True,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    qwen3moe = discovered["mlx-community/Qwen3-MoE-30B-A3B-Instruct/4bit"]

    assert qwen3moe.ext["text_backend_id"] == "mlx_lm"
    assert qwen3moe.ext["text_family_id"] == "qwen3moe"
    assert qwen3moe.ext["model_architecture"] == "qwen3_moe"
    assert qwen3moe.ext["detected_architecture"] == "qwen3_moe"
    assert qwen3moe.ext["detected_family_id"] == "qwen3moe"
    assert qwen3moe.ext["detected_identity_source"] == "config.model_type"
    assert qwen3moe.ext["melix.adapter_set_hash"] == "text-family-qwen3moe"
    assert qwen3moe.ext["melix.capability.route_kind"] == "python_text_compatibility"
    assert qwen3moe.ext["melix.capability.supported_parsers"] == "text,qwen"
    assert qwen3moe.ext["tool_parser_mode"] == "qwen"
    assert qwen3moe.ext["melix.text.attention_profile"] == "gqa"
    assert qwen3moe.ext["melix.text.rope_profile"] == "yarn_interleaved"
    assert qwen3moe.ext["melix.text.moe.enabled"] == "true"
    assert qwen3moe.ext["melix.text.moe.expert_count"] == "128"
    assert qwen3moe.ext["melix.text.moe.gate_dequant"] == "true"


def test_registry_snapshot_ignores_invalid_model_config_payloads(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Broken-Unknown" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Broken-Unknown/4bit",
    )
    variant_dir.mkdir(parents=True, exist_ok=True)
    (variant_dir / "config.json").write_text("{broken\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    broken = discovered["mlx-community/Broken-Unknown/4bit"]

    assert broken.ext["text_family_id"] == "llama"
    assert broken.ext["detected_identity_source"] == "default"
    assert broken.ext["melix.capability.route_kind"] == "python_text_compatibility"


def test_registry_snapshot_applies_image_family_adapter_metadata_from_path_and_manifest_task_kind(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "FLUX-Kontext" / "8bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/FLUX-Kontext/8bit",
        model_kind="image",
        ext={"melix.image.task_kind": "image-text-to-image"},
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    kontext = discovered["mlx-community/FLUX-Kontext/8bit"]

    assert kontext.ext["melix.image.backend_id"] == "deterministic"
    assert kontext.ext["melix.image.family_id"] == "kontext-v1"
    assert kontext.ext["melix.image.task_kind"] == "image-text-to-image"
    assert kontext.ext["melix.image.default_workflow_role"] == "edit"
    assert kontext.ext["melix.image.supports_generation"] == "true"
    assert kontext.ext["melix.image.supports_edit"] == "true"
    assert kontext.ext["detected_family_id"] == "kontext-v1"
    assert kontext.ext["detected_task_kind"] == "image-text-to-image"
    assert kontext.ext["detected_identity_source"] == "directory_name"
    assert kontext.ext["melix.adapter_set_hash"] == "image-family-kontext-v1"
    assert kontext.ext["melix.capability.route_kind"] == "python_image"
    assert kontext.ext["melix.capability.supported_tasks"] == "image_generate,image_edit"


def test_registry_snapshot_promotes_gemma4_text_manifest_to_vlm_text_backed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "unsloth" / "gemma-4-E4B-it-MLX-8bit" / "snapshot"
    _write_registry_manifest(
        variant_dir,
        model_id="unsloth/gemma-4-E4B-it-MLX-8bit/snapshot",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": None,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["unsloth/gemma-4-E4B-it-MLX-8bit/snapshot"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.backend_id"] == "mlx_vlm"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["vision_prompt_profile_id"] == "gemma4-chatml-v1"
    assert gemma4.ext["melix.capability.route_kind"] == "python_vlm"


def test_registry_snapshot_keeps_multimodal_gemma4_manifest_in_multimodal_mode(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-31b-it-4bit" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-31b-it-4bit/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "gemma4",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": {"model_type": "gemma4_vision"},
        },
    )
    (variant_dir / "processor_config.json").write_text("{}\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-31b-it-4bit/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["melix.vlm.backend_id"] == "mlx_vlm"
    assert gemma4.ext.get("melix.vlm.execution_mode", "") == ""
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"


def test_registry_snapshot_promotes_gemma4_from_architecture_hint(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-12b-it-4bit" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-12b-it-4bit/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "unknown",
            "architectures": ["Gemma4ForConditionalGeneration"],
            "vision_config": None,
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-12b-it-4bit/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext["melix.vlm.execution_mode"] == "text_backed"


def test_registry_snapshot_promotes_gemma4_from_text_config_with_processor_hint(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "gemma-4-12b-it-processor" / "4bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/gemma-4-12b-it-processor/4bit",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "unknown",
            "architectures": [],
            "text_config": {"model_type": "gemma4_text"},
            "vision_config": None,
        },
    )
    (variant_dir / "processor_config.json").write_text("{}\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    gemma4 = discovered["mlx-community/gemma-4-12b-it-processor/4bit"]

    assert gemma4.model_kind == "vlm"
    assert gemma4.ext["vision_family_id"] == "gemma4-v1"
    assert gemma4.ext.get("melix.vlm.execution_mode", "") == ""


def test_registry_snapshot_keeps_non_gemma_text_manifest_as_text(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "example" / "plain-text-model" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="example/plain-text-model/q4",
        model_kind="text",
    )
    _write_model_config(
        variant_dir,
        {
            "model_type": "llama",
            "architectures": ["LlamaForCausalLM"],
            "text_config": {"model_type": "llama"},
        },
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    plain = discovered["example/plain-text-model/q4"]

    assert plain.model_kind == "text"
    assert plain.ext["melix.capability.route_kind"] == "python_text_compatibility"
    assert plain.ext.get("vision_family_id", "") == ""


def test_dev_image_model_reads_family_and_task_overrides() -> None:
    qwen = WorkerModelCatalog.dev_image_model(
        {
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        }
    )
    fill = WorkerModelCatalog.dev_image_model(
        {
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/flux-fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        }
    )

    assert qwen.ext["melix.image.family_id"] == "qwenimage-v1"
    assert qwen.ext["melix.image.task_kind"] == "text-to-image"
    assert qwen.ext["melix.image.supports_generation"] == "true"
    assert qwen.ext["melix.image.supports_edit"] == "false"
    assert qwen.ext["melix.capability.supported_tasks"] == "image_generate"
    assert qwen.ext["detected_identity_source"] == "explicit_override"

    assert fill.ext["melix.image.family_id"] == "fill-v1"
    assert fill.ext["melix.image.task_kind"] == "image-text-to-image"
    assert fill.ext["melix.image.supports_generation"] == "false"
    assert fill.ext["melix.image.supports_edit"] == "true"
    assert fill.ext["melix.capability.supported_tasks"] == "image_edit"


def test_registry_snapshot_skips_manifests_outside_supported_identity_depths(tmp_path: Path) -> None:
    root = tmp_path / "root"

    _write_registry_manifest(
        root / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit",
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
    )
    _write_registry_manifest(
        root / "too-shallow" / "Qwen2.5-7B-Instruct",
        model_id="too-shallow/Qwen2.5-7B-Instruct",
    )
    _write_registry_manifest(
        root / "provider" / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit" / "extra",
        model_id="provider/mlx-community/Qwen2.5-7B-Instruct/4bit/extra",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["mlx-community/Qwen2.5-7B-Instruct/4bit"]


def test_registry_snapshot_skips_invalid_manifests_and_normalizes_non_mapping_ext(tmp_path: Path) -> None:
    root = tmp_path / "root"

    broken_dir = root / "broken-json"
    broken_dir.mkdir(parents=True, exist_ok=True)
    (broken_dir / "manifest.json").write_text("{not-json\n", encoding="utf-8")

    list_dir = root / "list-payload"
    list_dir.mkdir(parents=True, exist_ok=True)
    (list_dir / "manifest.json").write_text(json.dumps(["not", "a", "dict"]) + "\n", encoding="utf-8")

    missing_id_dir = root / "missing-id"
    missing_id_dir.mkdir(parents=True, exist_ok=True)
    (missing_id_dir / "manifest.json").write_text(
        json.dumps({"model_kind": "text", "ext": {"source_root": "missing-id"}}) + "\n",
        encoding="utf-8",
    )

    ext_list_dir = root / "mlx-community" / "Valid-Model" / "4bit"
    ext_list_dir.mkdir(parents=True, exist_ok=True)
    (ext_list_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.model_registry_manifest.v1",
                "model_id": "mlx-community/Valid-Model/4bit",
                "model_kind": "text",
                "quant_profile_id": "q4",
                "max_context": 8192,
                "ext": ["not", "a", "mapping"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(
        environment={
            "MELIX_MODEL_ROOTS": str(root),
        }
    )

    snapshot = catalog.registry_snapshot()

    assert [model.model_id for model in snapshot.models] == ["mlx-community/Valid-Model/4bit"]
    assert dict(snapshot.models[0].ext)["melix.registry_root_id"] == _expected_root_id(root)
    assert "source_root" not in snapshot.models[0].ext


def test_registry_snapshot_imports_generation_config_defaults_and_preserves_manifest_precedence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Vision-OCR" / "8bit"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Vision-OCR/8bit",
        model_kind="ocr",
        ext={
            "melix.generation_config.temperature": "0.25",
            "ocr_sampling_profile_id": "ocr-operator",
        },
    )
    (variant_dir / "generation_config.json").write_text(
        json.dumps(
            {
                "temperature": 0.15,
                "top_p": 0.92,
                "max_new_tokens": 384,
                "do_sample": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    discovered = {model.model_id: model for model in snapshot.models}
    model = discovered["mlx-community/Vision-OCR/8bit"]

    assert model.ext["melix.generation_config.temperature"] == "0.25"
    assert model.ext["melix.generation_config.top_p"] == "0.92"
    assert model.ext["melix.generation_config.max_tokens"] == "384"
    assert model.ext["melix.generation_config.do_sample"] == "false"
    assert model.ext["melix.generation_config.source"].endswith("generation_config.json")
    assert model.ext["ocr_sampling_profile_id"] == "ocr-operator"


def test_registry_snapshot_ignores_invalid_generation_config_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "Broken-Config" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/Broken-Config/q4",
        ext={"source_root": "valid"},
    )
    (variant_dir / "generation_config.json").write_text("{broken\n", encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    model = snapshot.models[0]

    assert model.model_id == "mlx-community/Broken-Config/q4"
    assert "melix.generation_config.source" not in model.ext


def test_registry_snapshot_ignores_non_mapping_generation_config_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "List-Config" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/List-Config/q4",
        ext={"source_root": "valid"},
    )
    (variant_dir / "generation_config.json").write_text('["not", "a", "mapping"]\n', encoding="utf-8")

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    model = snapshot.models[0]

    assert model.model_id == "mlx-community/List-Config/q4"
    assert "melix.generation_config.source" not in model.ext


def test_registry_snapshot_imports_string_generation_config_values_and_skips_blank_entries(tmp_path: Path) -> None:
    root = tmp_path / "root"
    variant_dir = root / "mlx-community" / "String-Config" / "q4"
    _write_registry_manifest(
        variant_dir,
        model_id="mlx-community/String-Config/q4",
        ext={"source_root": "valid"},
    )
    (variant_dir / "generation_config.json").write_text(
        json.dumps(
            {
                "temperature": " 0.33 ",
                "top_p": ["unsupported"],
                "max_new_tokens": " 512 ",
                "do_sample": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = WorkerModelCatalog(environment={"MELIX_MODEL_ROOTS": str(root)})

    snapshot = catalog.registry_snapshot()
    model = snapshot.models[0]

    assert model.model_id == "mlx-community/String-Config/q4"
    assert model.ext["melix.generation_config.temperature"] == "0.33"
    assert "melix.generation_config.top_p" not in model.ext
    assert model.ext["melix.generation_config.max_tokens"] == "512"
    assert model.ext["melix.generation_config.do_sample"] == "true"
    assert model.ext["melix.generation_config.source"].endswith("generation_config.json")
