from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Event

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2, runtime_pb2

from worker.engine.maintenance_core import MaintenanceCore
from worker.engine.image_edit_core import _supports_image_edit
from worker.engine.image_generation_core import _supports_image_generation
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_image_generation_runtime import (
    DeterministicImageGenerationRuntime,
    ImageGenerationCancelled,
)
from worker.runtime.mlx_text_runtime import MLXTextRuntime


class PassiveTextBackend:
    runtime_name = "passive-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 1024


def build_services(images_root: Path):
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=PassiveTextBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry, images_root=images_root)
    maintenance_core = MaintenanceCore(registry, jobs_root=images_root / "model-ops")
    return runtime_service, inference_service, maintenance_core


def load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model),
        context=None,
    )
    assert response.ok is True
    return response.model_handle


def test_image_generate_persists_artifacts_and_returns_completed_job(tmp_path: Path) -> None:
    runtime_service, inference_service, maintenance_core = build_services(tmp_path)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_image_model())

    response = inference_service.ImageGenerate(
        inference_pb2.ImageGenerateRequest(
            id=common_pb2.RequestIdentity(request_id="image-generate-1"),
            model_handle=model_handle,
            prompt="red fox in snow",
            size="512x512",
            n=2,
            response_format="png",
            artifact_namespace="tests",
        ),
        context=None,
    )

    assert response.error.code == ""
    assert len(response.images) == 2
    assert response.job.job_id == "image-generate-1::image-generate"
    assert response.job.state == common_pb2.IMAGE_JOB_COMPLETED
    assert response.job.progress.stage == "completed"
    assert response.job.progress.pct == pytest.approx(1.0)
    assert len(response.job.artifacts) == 2
    model_info = maintenance_core.get_model_info(
        maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-image")
    )

    for index, artifact in enumerate(response.job.artifacts):
        artifact_path = Path(artifact.storage_uri)
        assert artifact.job_id == response.job.job_id
        assert artifact.role == common_pb2.IMAGE_ARTIFACT_GENERATED
        assert artifact.mime_type == "image/png"
        assert artifact.format == "png"
        assert artifact.width == 512
        assert artifact.height == 512
        assert artifact.variant_index == index
        assert artifact.byte_length == len(response.images[index])
        assert artifact_path.exists() is True
        assert artifact_path.read_bytes() == response.images[index]

    assert model_info.ok is True
    assert model_info.supported_modalities == ["text", "image"]
    assert model_info.supported_tasks == ["image_generate", "image_edit"]


def test_image_generate_rejects_non_image_model_handles(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    text_model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    response = inference_service.ImageGenerate(
        inference_pb2.ImageGenerateRequest(
            id=common_pb2.RequestIdentity(request_id="image-generate-wrong-model"),
            model_handle=text_model_handle,
            prompt="should fail",
            size="512x512",
        ),
        context=None,
    )

    assert response.error.code == "invalid_argument"
    assert response.job.state == common_pb2.IMAGE_JOB_FAILED
    assert response.job.operation == "image_generate"


def test_image_generate_rejects_edit_only_image_families(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(
        runtime_service,
        WorkerModelCatalog.dev_image_model(
            {
                "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
                "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
                "MELIX_DEV_IMAGE_MODEL_PATH": "models/flux-fill-dev",
            }
        ),
    )

    response = inference_service.ImageGenerate(
        inference_pb2.ImageGenerateRequest(
            id=common_pb2.RequestIdentity(request_id="image-generate-edit-only"),
            model_handle=model_handle,
            prompt="should fail",
            size="512x512",
        ),
        context=None,
    )

    assert response.error.code == "invalid_argument"
    assert "does not support generation workflows" in response.error.message
    assert response.job.state == common_pb2.IMAGE_JOB_FAILED


def test_image_generation_and_edit_probe_bytes_do_not_rescan_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = DeterministicImageGenerationRuntime()
    loaded_model = {"model_id": "melix-dev-image"}

    def fail_sum(*_args, **_kwargs):
        raise AssertionError("output byte accounting must not rescan generated images")  # pragma: no cover

    monkeypatch.setattr("builtins.sum", fail_sum)

    generate_request = inference_pb2.ImageGenerateRequest(
        prompt="red fox in snow",
        size="128x128",
        response_format="png",
        artifact_namespace="tests",
        n=3,
    )
    generated = runtime.generate_images(
        loaded_model,
        generate_request,
        job_id="image-generate-no-rescan",
        images_root=tmp_path,
        cancel_event=Event(),
    )
    expected_generated_bytes = 0
    for payload in generated.images:
        expected_generated_bytes += len(payload)
    assert runtime.last_probe_snapshot().output_bytes == expected_generated_bytes

    edit_request = inference_pb2.ImageEditRequest(
        prompt="add stars",
        image=b"SOURCE_IMAGE",
        mask=b"MASK_IMAGE",
        size="128x128",
        response_format="png",
        n=3,
    )
    edited = runtime.edit_image(
        loaded_model,
        edit_request,
        job_id="image-edit-no-rescan",
        images_root=tmp_path,
        cancel_event=Event(),
    )
    expected_edited_bytes = 0
    for payload in edited.images:
        expected_edited_bytes += len(payload)
    assert runtime.last_probe_snapshot().output_bytes == expected_edited_bytes


def test_image_artifact_metadata_reuses_supplied_payload_byte_length(tmp_path: Path) -> None:
    class CountingBytes(bytes):
        len_calls = 0

        def __len__(self) -> int:
            type(self).len_calls += 1
            return super().__len__()

    payload = CountingBytes(b"generated-image-payload")
    fallback_artifact = DeterministicImageGenerationRuntime._artifact_metadata(
        job_id="image-byte-length-reuse",
        artifact_id="image-byte-length-reuse::fallback",
        role=common_pb2.IMAGE_ARTIFACT_GENERATED,
        mime_type="image/png",
        image_format="png",
        width=128,
        height=128,
        payload=payload,
        storage_path=tmp_path / "fallback-output-0.png",
        variant_index=0,
    )
    assert fallback_artifact.byte_length == 23
    assert CountingBytes.len_calls == 1

    CountingBytes.len_calls = 0
    artifact = DeterministicImageGenerationRuntime._artifact_metadata(
        job_id="image-byte-length-reuse",
        artifact_id="image-byte-length-reuse::artifact-0",
        role=common_pb2.IMAGE_ARTIFACT_GENERATED,
        mime_type="image/png",
        image_format="png",
        width=128,
        height=128,
        payload=payload,
        payload_byte_length=23,
        storage_path=tmp_path / "output-0.png",
        variant_index=0,
    )

    assert artifact.byte_length == 23
    assert CountingBytes.len_calls == 0


def test_image_edit_persists_lineage_and_generated_artifact(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_image_model())
    source_path = tmp_path / "edit-source.png"
    mask_path = tmp_path / "edit-mask.png"
    source_path.write_bytes(b"SOURCE_IMAGE")
    mask_path.write_bytes(b"MASK_IMAGE")

    response = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-edit-1"),
            model_handle=model_handle,
            prompt="add a comet",
            image_uri=source_path.as_uri(),
            mask_uri=mask_path.as_uri(),
            strength=0.65,
            size="256x256",
            response_format="png",
            n=1,
        ),
        context=None,
    )

    assert response.error.code == ""
    assert len(response.images) == 1
    assert response.job.job_id == "image-edit-1::image-edit"
    assert response.job.state == common_pb2.IMAGE_JOB_COMPLETED
    assert response.job.progress.stage == "completed"
    assert len(response.job.artifacts) == 3

    source_artifact, mask_artifact, generated_artifact = response.job.artifacts
    assert source_artifact.role == common_pb2.IMAGE_ARTIFACT_EDIT_SOURCE
    assert mask_artifact.role == common_pb2.IMAGE_ARTIFACT_MASK
    assert generated_artifact.role == common_pb2.IMAGE_ARTIFACT_GENERATED
    assert Path(source_artifact.storage_uri).read_bytes() == b"SOURCE_IMAGE"
    assert Path(mask_artifact.storage_uri).read_bytes() == b"MASK_IMAGE"
    assert source_artifact.sha256 == hashlib.sha256(b"SOURCE_IMAGE").hexdigest()
    assert mask_artifact.sha256 == hashlib.sha256(b"MASK_IMAGE").hexdigest()
    assert Path(generated_artifact.storage_uri).read_bytes() == response.images[0]


def test_image_edit_reuses_input_digests_across_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_image_model())
    source_path = tmp_path / "edit-source.png"
    mask_path = tmp_path / "edit-mask.png"
    source_path.write_bytes(b"SOURCE_IMAGE")
    mask_path.write_bytes(b"MASK_IMAGE")
    input_sha256_payloads: list[bytes] = []

    def record_input_sha256(payload: bytes) -> str:
        input_sha256_payloads.append(payload)
        return {
            b"SOURCE_IMAGE": "source-once-full-digest",
            b"MASK_IMAGE": "mask-once-full-digest",
        }[payload]

    monkeypatch.setattr(
        DeterministicImageGenerationRuntime,
        "_edit_input_sha256",
        staticmethod(record_input_sha256),
    )

    response = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-edit-digests"),
            model_handle=model_handle,
            prompt="add stars",
            image_uri=source_path.as_uri(),
            mask_uri=mask_path.as_uri(),
            size="256x256",
            response_format="png",
            n=4,
        ),
        context=None,
    )

    assert response.error.code == ""
    assert len(response.images) == 4
    source_artifact, mask_artifact, *_ = response.job.artifacts
    assert input_sha256_payloads == [b"SOURCE_IMAGE", b"MASK_IMAGE"]
    assert source_artifact.sha256 == "source-once-full-digest"
    assert mask_artifact.sha256 == "mask-once-full-digest"
    for payload in response.images:
        assert b"SOURCE_SHA=source-once-" in payload
        assert b"MASK_SHA=mask-once-fu" in payload


def test_image_edit_digest_helper_preserves_short_sha256_prefix() -> None:
    payload = b"SOURCE_IMAGE"
    full_digest = hashlib.sha256(payload).hexdigest()

    assert DeterministicImageGenerationRuntime._edit_input_sha256(payload) == full_digest
    assert DeterministicImageGenerationRuntime._edit_input_digest(payload) == full_digest[:12]
    assert DeterministicImageGenerationRuntime._edit_input_digest_from_sha256(full_digest) == full_digest[:12]


def test_image_iterate_and_variation_preserve_lineage_metadata(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_image_model())
    source_path = tmp_path / "iterate-source.png"
    source_path.write_bytes(b"SOURCE_IMAGE")

    iterate = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-iterate-1"),
            model_handle=model_handle,
            prompt="make the colors warmer",
            image_uri=source_path.as_uri(),
            source_artifact_id="artifact-source",
            prompt_delta="make the colors warmer",
            edit_mode=inference_pb2.IMAGE_EDIT_MODE_ITERATE,
            size="256x256",
            response_format="png",
            n=1,
            ext={"melix.image.source_job_id": "job-source"},
        ),
        context=None,
    )

    assert iterate.error.code == ""
    assert iterate.job.operation == "image_iterate"
    assert iterate.job.source_artifact_id == "artifact-source"
    assert iterate.job.source_job_id == "job-source"
    assert iterate.job.prompt_delta == "make the colors warmer"
    assert iterate.job.edit_mode == inference_pb2.IMAGE_EDIT_MODE_ITERATE
    assert iterate.job.artifacts[0].parent_artifact_id == "artifact-source"
    assert iterate.job.artifacts[0].ext["melix.image.source_artifact_id"] == "artifact-source"
    assert iterate.job.artifacts[0].ext["melix.image.source_job_id"] == "job-source"
    assert iterate.job.artifacts[0].ext["melix.image.prompt_delta"] == "make the colors warmer"
    assert iterate.job.artifacts[0].ext["melix.image.edit_mode"] == "iterate"
    assert iterate.job.artifacts[-1].parent_artifact_id == "artifact-source"
    assert iterate.job.artifacts[-1].ext["melix.image.edit_mode"] == "iterate"

    variation = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-variation-1"),
            model_handle=model_handle,
            prompt="keep composition",
            image_uri=source_path.as_uri(),
            source_artifact_id="artifact-source",
            edit_mode=inference_pb2.IMAGE_EDIT_MODE_VARIATION,
            size="256x256",
            response_format="png",
            n=1,
            ext={"melix.image.source_job_id": "job-source"},
        ),
        context=None,
    )

    assert variation.error.code == ""
    assert variation.job.operation == "image_variation"
    assert variation.job.source_artifact_id == "artifact-source"
    assert variation.job.source_job_id == "job-source"
    assert variation.job.prompt_delta == ""
    assert variation.job.edit_mode == inference_pb2.IMAGE_EDIT_MODE_VARIATION
    assert variation.job.artifacts[0].ext["melix.image.edit_mode"] == "variation"
    assert variation.job.artifacts[-1].parent_artifact_id == "artifact-source"


def test_image_edit_rejects_missing_source_and_invalid_mask_reference(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_image_model())

    missing_source = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-edit-missing-source"),
            model_handle=model_handle,
            prompt="missing source",
            size="256x256",
        ),
        context=None,
    )
    missing_mask = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-edit-missing-mask"),
            model_handle=model_handle,
            prompt="missing mask",
            image=b"SOURCE_IMAGE",
            mask_uri=(tmp_path / "missing-mask.png").as_uri(),
            size="256x256",
        ),
        context=None,
    )

    assert missing_source.error.code == "invalid_argument"
    assert missing_source.job.state == common_pb2.IMAGE_JOB_FAILED
    assert missing_mask.error.code == "invalid_argument"
    assert missing_mask.job.state == common_pb2.IMAGE_JOB_FAILED


def test_image_edit_rejects_non_image_model_handles(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    text_model_handle = load_model(runtime_service, WorkerModelCatalog.dev_text_model())

    response = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-edit-wrong-model"),
            model_handle=text_model_handle,
            prompt="should fail",
            image=b"SOURCE_IMAGE",
            size="256x256",
        ),
        context=None,
    )

    assert response.error.code == "invalid_argument"
    assert response.job.state == common_pb2.IMAGE_JOB_FAILED
    assert response.job.operation == "image_edit"


def test_image_edit_rejects_generate_only_image_families(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(
        runtime_service,
        WorkerModelCatalog.dev_image_model(
            {
                "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
                "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
            }
        ),
    )

    response = inference_service.ImageEdit(
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="image-edit-generate-only"),
            model_handle=model_handle,
            prompt="should fail",
            image=b"SOURCE_IMAGE",
            size="256x256",
        ),
        context=None,
    )

    assert response.error.code == "invalid_argument"
    assert "does not support editing workflows" in response.error.message
    assert response.job.state == common_pb2.IMAGE_JOB_FAILED


def test_image_edit_returns_canceled_job_when_runtime_cancelled(tmp_path: Path) -> None:
    runtime_service, inference_service, _ = build_services(tmp_path)
    model_handle = load_model(runtime_service, WorkerModelCatalog.dev_image_model())
    registry = inference_service._registry
    original_runtime = registry.image_generation_runtime

    class CancelingImageRuntime:
        def edit_image(self, *args, **kwargs):
            raise ImageGenerationCancelled("Image edit was canceled.")

    registry.image_generation_runtime = CancelingImageRuntime()
    try:
        response = inference_service.ImageEdit(
            inference_pb2.ImageEditRequest(
                id=common_pb2.RequestIdentity(request_id="image-edit-cancelled"),
                model_handle=model_handle,
                prompt="cancel this edit",
                image=b"SOURCE_IMAGE",
                size="256x256",
            ),
            context=None,
        )
    finally:
        registry.image_generation_runtime = original_runtime

    assert response.error.code == "cancelled"
    assert response.job.state == common_pb2.IMAGE_JOB_CANCELED
    assert response.job.progress.stage == "canceled"
    assert response.job.operation == "image_edit"


def test_deterministic_image_runtime_reports_probe_snapshot_and_validates_inputs(tmp_path: Path) -> None:
    runtime = DeterministicImageGenerationRuntime()
    loaded_model = runtime.load_model(WorkerModelCatalog.dev_image_model())
    request = inference_pb2.ImageGenerateRequest(
        id=common_pb2.RequestIdentity(request_id="probe-image-generate"),
        prompt="blueprint tower",
        size="320x240",
        n=1,
        response_format="png",
    )

    result = runtime.generate_images(
        loaded_model,
        request,
        job_id="probe-image-generate::image-generate",
        images_root=tmp_path,
        cancel_event=Event(),
    )
    probe = runtime.last_probe_snapshot()

    assert len(result.images) == 1
    assert probe.job_latency_ms >= 0.0
    assert probe.artifact_publish_ms >= 0.0
    assert probe.output_bytes == len(result.images[0])
    assert probe.peak_memory_bytes >= probe.output_bytes

    with pytest.raises(ValueError, match="Unsupported image size"):
        runtime.generate_images(
            loaded_model,
            inference_pb2.ImageGenerateRequest(
                id=common_pb2.RequestIdentity(request_id="bad-size"),
                prompt="invalid size",
                size="bad-size",
                response_format="png",
            ),
            job_id="bad-size::image-generate",
            images_root=tmp_path,
            cancel_event=Event(),
        )

    with pytest.raises(ValueError, match="Unsupported image response format"):
        runtime.generate_images(
            loaded_model,
            inference_pb2.ImageGenerateRequest(
                id=common_pb2.RequestIdentity(request_id="bad-format"),
                prompt="invalid format",
                size="320x240",
                response_format="gif",
            ),
            job_id="bad-format::image-generate",
            images_root=tmp_path,
            cancel_event=Event(),
        )

    edit_result = runtime.edit_image(
        loaded_model,
        inference_pb2.ImageEditRequest(
            id=common_pb2.RequestIdentity(request_id="edit-probe"),
            prompt="mask edit",
            image=b"SOURCE",
            mask=b"MASK",
            size="320x240",
            response_format="png",
        ),
        job_id="edit-probe::image-edit",
        images_root=tmp_path,
        cancel_event=Event(),
    )
    edit_probe = runtime.last_probe_snapshot()

    assert len(edit_result.images) == 1
    assert edit_probe.job_latency_ms >= 0.0
    assert edit_probe.artifact_publish_ms >= 0.0

    cancelled = Event()
    cancelled.set()
    with pytest.raises(Exception, match="canceled"):
        runtime.edit_image(
            loaded_model,
            inference_pb2.ImageEditRequest(
                id=common_pb2.RequestIdentity(request_id="edit-cancelled"),
                prompt="cancelled",
                image=b"SOURCE",
                size="320x240",
                response_format="png",
            ),
            job_id="edit-cancelled::image-edit",
            images_root=tmp_path,
            cancel_event=cancelled,
        )


def test_image_role_helpers_fall_back_to_supported_tasks_and_task_kind() -> None:
    generate_from_tasks = common_pb2.ModelSpec(
        model_id="image-generate-from-tasks",
        model_kind="image",
        ext={"melix.capability.supported_tasks": "image_generate"},
    )
    generate_from_task_kind = common_pb2.ModelSpec(
        model_id="image-generate-from-task-kind",
        model_kind="image",
        ext={"melix.image.task_kind": "text-to-image"},
    )
    edit_from_tasks = common_pb2.ModelSpec(
        model_id="image-edit-from-tasks",
        model_kind="image",
        ext={"melix.capability.supported_tasks": "image_edit"},
    )
    edit_from_task_kind = common_pb2.ModelSpec(
        model_id="image-edit-from-task-kind",
        model_kind="image",
        ext={"melix.image.task_kind": "image-text-to-image"},
    )

    assert _supports_image_generation(generate_from_tasks) is True
    assert _supports_image_generation(generate_from_task_kind) is True
    assert _supports_image_edit(edit_from_tasks) is True
    assert _supports_image_edit(edit_from_task_kind) is True
