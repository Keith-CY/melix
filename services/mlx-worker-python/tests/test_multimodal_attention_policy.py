from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.engine.engine_core import EngineCore
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime import deterministic_vlm_runtime as deterministic_vlm_runtime_module
from worker.runtime import mlx_vlm_runtime as mlx_vlm_runtime_module
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.mlx_vlm_runtime import AutoMLXVLMBackend, MLXVLMRuntime
from worker.runtime.multimodal_attention_policy import (
    MultimodalPrefillAttentionBudgetExceeded,
    attention_budget_configured,
    build_attention_budget_receipt,
    choose_attention_prefill_policy,
)


def test_attention_policy_records_whole_prefill_when_cost_is_inside_budget() -> None:
    decision = choose_attention_prefill_policy(
        family_id="llava-v1",
        prompt_tokens=128,
        budget_bytes=536_870_912,
        hidden_size=1024,
        num_hidden_layers=8,
        dtype_bytes=2,
    )

    assert decision.predicted_attention_bytes > 0
    assert decision.prefill_chunk_mode == "whole_prefill"
    assert decision.selected_prefill_step_size == 128
    assert decision.auto_chunk_reason == ""
    assert decision.refusal_count == 0


def test_attention_policy_selects_conservative_chunk_when_prompt_exceeds_budget() -> None:
    decision = choose_attention_prefill_policy(
        family_id="gemma4-v1",
        prompt_tokens=4096,
        budget_bytes=16_777_216,
        hidden_size=1024,
        num_hidden_layers=8,
        dtype_bytes=2,
    )

    assert decision.predicted_attention_bytes > decision.budget_bytes
    assert decision.prefill_chunk_mode == "auto_chunk"
    assert 0 < decision.selected_prefill_step_size < 4096
    assert decision.auto_chunk_reason == "attention_budget_auto_chunked"
    assert decision.refusal_count == 0


def test_attention_policy_returns_typed_refusal_when_minimum_chunk_exceeds_budget() -> None:
    decision = choose_attention_prefill_policy(
        family_id="paligemma-v1",
        prompt_tokens=512,
        budget_bytes=1,
        hidden_size=4096,
        num_hidden_layers=32,
        dtype_bytes=2,
    )

    assert decision.prefill_chunk_mode == "refused"
    assert decision.selected_prefill_step_size == 0
    assert decision.auto_chunk_reason == "attention_budget_exceeded"
    assert decision.refusal_count == 1
    assert decision.error_code == "multimodal_prefill_attention_budget_exceeded"
    assert "predicted_attention_bytes" in decision.error_details
    assert "attention_budget_bytes" in decision.error_details


def test_attention_policy_opts_out_unverified_family_after_recording_cost() -> None:
    decision = choose_attention_prefill_policy(
        family_id="unknown-vlm",
        prompt_tokens=2048,
        budget_bytes=16_777_216,
        hidden_size=1024,
        num_hidden_layers=8,
        dtype_bytes=2,
    )

    assert decision.verified_family is False
    assert decision.predicted_attention_bytes > decision.budget_bytes
    assert decision.prefill_chunk_mode == "family_unverified"
    assert decision.selected_prefill_step_size == 0
    assert decision.auto_chunk_reason == "unverified_family_opt_out"
    assert decision.refusal_count == 0


def test_attention_budget_receipt_preserves_machine_readable_fields() -> None:
    decision = choose_attention_prefill_policy(
        family_id="gemma4-v1",
        prompt_tokens=4096,
        budget_bytes=16_777_216,
        hidden_size=1024,
        num_hidden_layers=8,
        dtype_bytes=2,
    )

    receipt = build_attention_budget_receipt(decision)

    assert receipt == {
        "attention_budget_verified_family": True,
        "attention_budget_family_id": "gemma4-v1",
        "attention_budget_prompt_tokens": 4096,
        "predicted_attention_bytes": decision.predicted_attention_bytes,
        "attention_budget_bytes": 16_777_216,
        "prefill_chunk_mode": "auto_chunk",
        "selected_prefill_step_size": decision.selected_prefill_step_size,
        "auto_chunk_reason": "attention_budget_auto_chunked",
        "attention_budget_refusal_count": 0,
    }


def test_attention_policy_handles_zero_tokens_and_invalid_requested_chunk() -> None:
    decision = choose_attention_prefill_policy(
        family_id="gemma4-v1",
        prompt_tokens=0,
        budget_bytes=16_777_216,
        requested_prefill_step_size="invalid",  # type: ignore[arg-type]
    )

    assert decision.predicted_attention_bytes == 0
    assert decision.prefill_chunk_mode == "whole_prefill"
    assert decision.selected_prefill_step_size == 0


def _load_model(runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec) -> str:
    response = runtime_service.LoadModel(runtime_pb2.LoadModelRequest(model=model), context=None)
    assert response.ok is True
    return response.model_handle


def _vision_message() -> common_pb2.ChatMessage:
    return common_pb2.ChatMessage(
        role="user",
        parts=[
            common_pb2.MessagePart(text="Summarize the image."),
            common_pb2.MessagePart(
                image_bytes=b"attention budget image",
                media=common_pb2.MediaMetadata(
                    media_type=common_pb2.MEDIA_TYPE_IMAGE,
                    source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    mime_type="image/png",
                    filename="attention-budget.png",
                ),
            ),
        ],
    )


def test_deterministic_vlm_prefill_rejects_over_budget_attention_before_decode_session() -> None:
    runtime = DeterministicVLMRuntime()
    registry = WorkerRegistry(vlm_runtime=runtime, model_catalog=WorkerModelCatalog())
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.attention_cost_budget_bytes"] = "1"
    model_handle = _load_model(runtime_service, model)

    request_id = "vlm-prefill-attention-budget"
    response = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id=request_id),
                model_handle=model_handle,
            ),
            messages=[_vision_message()],
            return_decode_handle=True,
            prefill_step_size=16,
        ),
        context=None,
    )

    assert response.ok is False
    assert response.admission_state == common_pb2.ADMISSION_REJECTED
    assert response.error.code == "multimodal_prefill_attention_budget_exceeded"
    assert response.error.details["auto_chunk_reason"] == "attention_budget_exceeded"
    assert int(response.error.details["predicted_attention_bytes"]) > int(
        response.error.details["attention_budget_bytes"]
    )

    decode_events = list(
        inference_service.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                decode_handle=f"vlm:{request_id}",
                sampling=common_pb2.SamplingConfig(max_output_tokens=8),
                max_output_tokens=8,
            ),
            context=None,
        )
    )

    assert decode_events[0].error.error.code == "invalid_decode_handle"


def test_engine_generate_emits_typed_attention_refusal_error() -> None:
    runtime = DeterministicVLMRuntime()
    registry = WorkerRegistry(vlm_runtime=runtime, model_catalog=WorkerModelCatalog())
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.attention_cost_budget_bytes"] = "1"
    model_handle = _load_model(runtime_service, model)

    events = list(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="vlm-generate-attention-budget"),
                    model_handle=model_handle,
                ),
                messages=[_vision_message()],
                sampling=common_pb2.SamplingConfig(max_output_tokens=8),
                stream=True,
                return_usage=True,
            ),
            context=None,
        )
    )

    assert len(events) == 1
    assert events[0].HasField("error")
    assert events[0].error.error.code == "multimodal_prefill_attention_budget_exceeded"
    assert events[0].error.error.details["auto_chunk_reason"] == "attention_budget_exceeded"
    assert int(events[0].error.error.details["predicted_attention_bytes"]) > int(
        events[0].error.error.details["attention_budget_bytes"]
    )


def test_deterministic_vlm_records_attention_policy_before_first_token() -> None:
    runtime = DeterministicVLMRuntime()
    registry = WorkerRegistry(vlm_runtime=runtime, model_catalog=WorkerModelCatalog())
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.attention_cost_budget_bytes"] = "1000000"
    model_handle = _load_model(runtime_service, model)

    first_event = next(
        inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="vlm-generate-attention-policy"),
                    model_handle=model_handle,
                ),
                messages=[_vision_message()],
                sampling=common_pb2.SamplingConfig(max_output_tokens=8),
                stream=True,
                return_usage=True,
            ),
            context=None,
        )
    )
    loaded = registry.get_loaded_model(model_handle)
    assert loaded is not None
    receipt = loaded.runtime.last_probe_snapshot().attention_budget_receipt

    assert first_event.HasField("token_delta")
    assert receipt["predicted_attention_bytes"] > 0
    assert receipt["attention_budget_bytes"] == 1_000_000
    assert receipt["prefill_chunk_mode"] == "auto_chunk"
    assert receipt["auto_chunk_reason"] == "attention_budget_auto_chunked"


def test_attention_metadata_parsers_handle_invalid_values() -> None:
    assert deterministic_vlm_runtime_module._int_metadata([], "x") == 0
    assert deterministic_vlm_runtime_module._int_metadata({"x": "invalid"}, "x") == 0
    assert deterministic_vlm_runtime_module._int_metadata({"x": "", "y": "32"}, "x", "y") == 32
    assert mlx_vlm_runtime_module._int_metadata([], "x") == 0
    assert mlx_vlm_runtime_module._int_metadata({"x": "invalid"}, "x") == 0
    assert mlx_vlm_runtime_module._int_metadata({"x": "", "y": "32"}, "x", "y") == 32


def test_attention_budget_configured_detects_top_level_and_nested_metadata() -> None:
    assert attention_budget_configured([]) is False
    assert attention_budget_configured({}) is False
    assert attention_budget_configured({"melix.vlm.attention_cost_budget_bytes": "1000"}) is True
    assert (
        attention_budget_configured(
            {"metadata": {"melix.vlm.prefill_attention_budget_bytes": "2000"}}
        )
        is True
    )


def test_engine_error_event_preserves_attention_refusal_details() -> None:
    decision = choose_attention_prefill_policy(
        family_id="gemma4-v1",
        prompt_tokens=512,
        budget_bytes=1,
    )
    error = MultimodalPrefillAttentionBudgetExceeded(decision)

    event = EngineCore._error_event(
        "request-1",
        1,
        error.code,
        str(error),
        details=error.details,
    )

    assert event.error.error.code == "multimodal_prefill_attention_budget_exceeded"
    assert event.error.error.details["auto_chunk_reason"] == "attention_budget_exceeded"
    assert event.error.error.details["selected_prefill_step_size"] == "0"


def test_mlx_vlm_runtime_keeps_attention_receipt_when_backend_lacks_chunk_kwarg() -> None:
    pre_forward_receipts: list[dict[str, object]] = []

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace(
            image_processor=object()
        )

    def fake_apply_chat_template(processor, config, prompt: str, num_images: int = 0, **kwargs):
        _ = processor
        _ = config
        _ = kwargs
        return f"formatted::{prompt}::{num_images}"

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=lambda *args, **kwargs: iter(()),
            apply_chat_template_fn=fake_apply_chat_template,
        )
    )

    def fake_stream_generate(
        model,
        processor,
        prompt: str,
        *,
        image=None,
        max_tokens=64,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        verbose=False,
    ):
        _ = (model, processor, prompt, image, max_tokens, temperature, top_p, top_k, verbose)
        pre_forward_receipts.append(runtime.last_probe_snapshot().attention_budget_receipt)
        yield SimpleNamespace(text="ok", prompt_tokens=32, generation_tokens=1)

    runtime._backend.stream_generate_fn = fake_stream_generate
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.attention_cost_budget_bytes"] = "1000000"
    loaded_model = runtime.load_model(model)
    prepared = runtime.render_prompt([_vision_message()], loaded_model=loaded_model)

    events = list(
        runtime.generate_tokens(
            loaded_model,
            prepared,
            common_pb2.SamplingConfig(max_output_tokens=4),
            Event(),
        )
    )

    assert [event.text for event in events] == ["ok"]
    assert pre_forward_receipts[0]["prefill_chunk_mode"] == "auto_chunk"


def test_mlx_vlm_runtime_refuses_before_backend_stream_generate() -> None:
    stream_called = False

    def fake_load(model_path: str, revision: str = "main"):
        _ = model_path
        _ = revision
        return SimpleNamespace(config=SimpleNamespace(model_type="gemma4")), SimpleNamespace(
            image_processor=object()
        )

    def fake_stream_generate(*args, **kwargs):  # pragma: no cover - must be blocked before backend.
        nonlocal stream_called
        stream_called = True
        _ = (args, kwargs)
        return iter(())

    runtime = MLXVLMRuntime(
        backend=AutoMLXVLMBackend(
            load_fn=fake_load,
            stream_generate_fn=fake_stream_generate,
            apply_chat_template_fn=lambda *args, **kwargs: "formatted::prompt",
        )
    )
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.attention_cost_budget_bytes"] = "1"
    loaded_model = runtime.load_model(model)
    prepared = runtime.render_prompt([_vision_message()], loaded_model=loaded_model)

    with pytest.raises(MultimodalPrefillAttentionBudgetExceeded):
        list(
            runtime.generate_tokens(
                loaded_model,
                prepared,
                common_pb2.SamplingConfig(max_output_tokens=4),
                Event(),
            )
        )

    assert stream_called is False
