from __future__ import annotations

from math import ceil
from types import SimpleNamespace

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from backend_identity_support import (
    WorkerInferenceService,
    WorkerRuntimeService,
    bind_backend_identity,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime.deterministic_vlm_runtime import DeterministicVLMRuntime
from worker.runtime.multimodal_preprocessing import PreparedVisionRequest
from worker.runtime.text_prefill_chunk_policy import (
    TEXT_PREFILL_CHUNKED_PREFIX,
    TEXT_PREFILL_FALLBACK_CACHE_UNAVAILABLE,
    TEXT_PREFILL_FALLBACK_MEDIA_PRESENT,
    TEXT_PREFILL_FALLBACK_PARTIAL_ATTENTION_MASK,
    TEXT_PREFILL_FALLBACK_PROMPT_WITHIN_SINGLE_CHUNK,
    TEXT_PREFILL_FALLBACK_SEQUENCE_ALIGNED_EXTRA_INPUTS,
    TEXT_PREFILL_SINGLE_FORWARD,
    build_text_prefill_chunk_receipt,
    normalize_text_prefill_step_size,
    resolve_configured_text_prefill_chunk_policy,
    resolve_text_prefill_chunk_policy,
    text_prefill_chunk_configured,
)


def test_chunked_prefix_splits_prefix_and_runs_final_token_separately() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=20_000,
        requested_prefill_step_size=512,
    )

    assert decision.prefill_mode == TEXT_PREFILL_CHUNKED_PREFIX
    assert decision.effective_prefill_step_size == 512
    assert decision.prefill_chunk_tokens == 512
    assert decision.final_logits_positions == 1
    assert decision.fallback_reason == ""
    # Only the prefix is chunked; the final decoded token is a separate forward.
    assert decision.prefix_chunks == ceil((20_000 - 1) / 512)
    assert decision.prefix_chunks >= 2


def test_prefix_that_crosses_exactly_one_boundary_yields_two_chunks() -> None:
    # prefix_tokens = prompt_tokens - 1 = step_size + 1 -> two chunks.
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=6,
        requested_prefill_step_size=4,
    )

    assert decision.prefill_mode == TEXT_PREFILL_CHUNKED_PREFIX
    assert decision.prefix_chunks == 2
    assert decision.prefill_chunk_tokens == 4
    assert decision.final_logits_positions == 1


def test_prompt_within_single_chunk_keeps_single_forward() -> None:
    # prefix_tokens = 4 which fits inside one step, so short prompts are unchanged.
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=5,
        requested_prefill_step_size=4,
    )

    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_PROMPT_WITHIN_SINGLE_CHUNK
    assert decision.prefill_chunk_tokens == 5
    assert decision.prefix_chunks == 1
    assert decision.final_logits_positions == 1


def test_media_input_forces_single_forward_fallback() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=20_000,
        requested_prefill_step_size=512,
        has_media=True,
    )

    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_MEDIA_PRESENT


def test_sequence_aligned_extra_inputs_force_single_forward_fallback() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=20_000,
        requested_prefill_step_size=512,
        has_sequence_aligned_extra_inputs=True,
    )

    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert (
        decision.fallback_reason == TEXT_PREFILL_FALLBACK_SEQUENCE_ALIGNED_EXTRA_INPUTS
    )


def test_partial_attention_mask_forces_single_forward_fallback() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=20_000,
        requested_prefill_step_size=512,
        attention_mask_all_valid=False,
    )

    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_PARTIAL_ATTENTION_MASK


def test_missing_cache_forces_single_forward_fallback() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=20_000,
        requested_prefill_step_size=512,
        cache_present=False,
    )

    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_CACHE_UNAVAILABLE


def test_media_guard_takes_precedence_over_other_guards() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=20_000,
        requested_prefill_step_size=512,
        has_media=True,
        has_sequence_aligned_extra_inputs=True,
        attention_mask_all_valid=False,
        cache_present=False,
    )

    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_MEDIA_PRESENT


def test_empty_prompt_reports_no_chunks() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=0,
        requested_prefill_step_size=512,
    )

    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert decision.prefix_chunks == 0
    assert decision.final_logits_positions == 0
    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_PROMPT_WITHIN_SINGLE_CHUNK


def test_step_size_normalization_handles_unset_invalid_and_out_of_range() -> None:
    assert normalize_text_prefill_step_size(None) == 512
    assert normalize_text_prefill_step_size("") == 512
    assert normalize_text_prefill_step_size("0") == 512
    assert normalize_text_prefill_step_size("-8") == 512
    assert normalize_text_prefill_step_size("not-a-number") == 512
    assert normalize_text_prefill_step_size("1") == 1
    assert normalize_text_prefill_step_size("999999") == 8192
    assert normalize_text_prefill_step_size(256) == 256


def test_unset_step_size_uses_default_for_chunk_decision() -> None:
    decision = resolve_text_prefill_chunk_policy(prompt_tokens=20_000)

    assert decision.effective_prefill_step_size == 512
    assert decision.prefill_mode == TEXT_PREFILL_CHUNKED_PREFIX


def test_receipt_exposes_named_fields() -> None:
    decision = resolve_text_prefill_chunk_policy(
        prompt_tokens=6,
        requested_prefill_step_size=4,
    )

    receipt = build_text_prefill_chunk_receipt(decision)

    assert receipt == {
        "prefill_mode": TEXT_PREFILL_CHUNKED_PREFIX,
        "prompt_tokens": 6,
        "effective_prefill_step_size": 4,
        "prefill_chunk_tokens": 4,
        "prefix_chunks": 2,
        "final_logits_positions": 1,
        "fallback_reason": "",
    }


def test_receipt_is_empty_for_missing_decision() -> None:
    assert build_text_prefill_chunk_receipt(None) == {}


def test_configured_resolver_returns_none_when_step_size_unset() -> None:
    assert (
        resolve_configured_text_prefill_chunk_policy(
            loaded_model={"vision_family_id": "llava-v1"},
            prepared_request=SimpleNamespace(images=(), videos=()),
            seq_len=20_000,
        )
        is None
    )
    assert text_prefill_chunk_configured({"vision_family_id": "llava-v1"}) is False


def test_configured_resolver_reads_top_level_and_nested_and_execution_ext() -> None:
    top_level = resolve_configured_text_prefill_chunk_policy(
        loaded_model={"melix.vlm.text_prefill_step_size": "4"},
        prepared_request=SimpleNamespace(images=(), videos=()),
        seq_len=6,
    )
    assert top_level is not None
    assert top_level.prefill_mode == TEXT_PREFILL_CHUNKED_PREFIX
    assert top_level.effective_prefill_step_size == 4

    nested = resolve_configured_text_prefill_chunk_policy(
        loaded_model={"metadata": {"melix.vlm.text_prefill_chunk_tokens": "4"}},
        prepared_request=SimpleNamespace(images=(), videos=()),
        seq_len=6,
    )
    assert nested is not None
    assert nested.prefill_mode == TEXT_PREFILL_CHUNKED_PREFIX

    overridden = resolve_configured_text_prefill_chunk_policy(
        loaded_model={"melix.vlm.text_prefill_step_size": "999999"},
        prepared_request=SimpleNamespace(images=(), videos=()),
        seq_len=6,
        execution_ext={"melix.vlm.text_prefill_step_size": "4"},
    )
    assert overridden is not None
    assert overridden.effective_prefill_step_size == 4


def test_configured_resolver_forwards_partial_mask_and_cache_and_extra_input_guards() -> (
    None
):
    base_kwargs = dict(
        loaded_model={"melix.vlm.text_prefill_step_size": "4"},
        prepared_request=SimpleNamespace(images=(), videos=()),
        seq_len=20_000,
    )

    # Default (eligible) call still chunks, proving the guards are opt-in.
    eligible = resolve_configured_text_prefill_chunk_policy(**base_kwargs)
    assert eligible is not None
    assert eligible.prefill_mode == TEXT_PREFILL_CHUNKED_PREFIX

    partial_mask = resolve_configured_text_prefill_chunk_policy(
        **base_kwargs, attention_mask_all_valid=False
    )
    assert partial_mask is not None
    assert partial_mask.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert partial_mask.fallback_reason == TEXT_PREFILL_FALLBACK_PARTIAL_ATTENTION_MASK

    missing_cache = resolve_configured_text_prefill_chunk_policy(
        **base_kwargs, cache_present=False
    )
    assert missing_cache is not None
    assert missing_cache.fallback_reason == TEXT_PREFILL_FALLBACK_CACHE_UNAVAILABLE

    extra_inputs = resolve_configured_text_prefill_chunk_policy(
        **base_kwargs, has_sequence_aligned_extra_inputs=True
    )
    assert extra_inputs is not None
    assert (
        extra_inputs.fallback_reason
        == TEXT_PREFILL_FALLBACK_SEQUENCE_ALIGNED_EXTRA_INPUTS
    )


def test_configured_resolver_detects_media_on_prepared_request() -> None:
    decision = resolve_configured_text_prefill_chunk_policy(
        loaded_model={"melix.vlm.text_prefill_step_size": "4"},
        prepared_request=SimpleNamespace(images=(object(),), videos=()),
        seq_len=20_000,
    )

    assert decision is not None
    assert decision.prefill_mode == TEXT_PREFILL_SINGLE_FORWARD
    assert decision.fallback_reason == TEXT_PREFILL_FALLBACK_MEDIA_PRESENT


def _load_model(
    runtime_service: WorkerRuntimeService, model: common_pb2.ModelSpec
) -> str:
    response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=model), context=None
    )
    assert response.ok is True
    return response.model_handle


def _text_only_prepared_request(prompt_text: str) -> PreparedVisionRequest:
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=[],
        videos=[],
        video_frame_policies=[],
        preprocess_latency_ms=0.0,
        preprocess_input_bytes=0,
        preprocess_peak_memory_bytes=0,
        prompt_hash_hex="text-prefill-prompt",
        multimodal_hash_hex="text-prefill-media",
    )


def _vision_message() -> common_pb2.ChatMessage:
    return common_pb2.ChatMessage(
        role="user",
        parts=[
            common_pb2.MessagePart(text="Describe the image."),
            common_pb2.MessagePart(
                image_bytes=b"text prefill chunk image",
                media=common_pb2.MediaMetadata(
                    media_type=common_pb2.MEDIA_TYPE_IMAGE,
                    source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                    mime_type="image/png",
                    filename="text-prefill-chunk.png",
                ),
            ),
        ],
    )


def _first_generate_receipt(
    model: common_pb2.ModelSpec,
    message: common_pb2.ChatMessage,
    request_id: str,
) -> tuple[object, dict[str, object]]:
    runtime = DeterministicVLMRuntime()
    registry = WorkerRegistry(vlm_runtime=runtime, model_catalog=WorkerModelCatalog())
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model_handle = _load_model(runtime_service, model)

    first_event = next(
        inference_service.Generate(
            bind_backend_identity(
                inference_service,
                inference_pb2.GenerateRequest(
                    execution=inference_pb2.ExecutionMetadata(
                        id=common_pb2.RequestIdentity(request_id=request_id),
                        model_handle=model_handle,
                    ),
                    messages=[message],
                    sampling=common_pb2.SamplingConfig(max_output_tokens=8),
                    stream=True,
                    return_usage=True,
                ),
            ),
            context=None,
        )
    )
    loaded = registry.get_loaded_model(model_handle)
    assert loaded is not None
    return first_event, loaded.runtime.last_probe_snapshot().text_prefill_chunk_receipt


def test_deterministic_vlm_runtime_records_chunked_text_prefill_receipt() -> None:
    # A text-backed VLM decode never carries media, so drive the probe directly:
    # the shared preprocessor rejects media-free requests before Generate runs.
    runtime = DeterministicVLMRuntime()
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.text_prefill_step_size"] = "4"
    loaded_model = runtime.load_model(model)
    prepared = _text_only_prepared_request(" ".join(f"token{i}" for i in range(40)))

    runtime._ensure_fast_path_probe(loaded_model, prepared, seq_len=6000)
    receipt = runtime.last_probe_snapshot().text_prefill_chunk_receipt

    assert receipt["prefill_mode"] == TEXT_PREFILL_CHUNKED_PREFIX
    assert receipt["effective_prefill_step_size"] == 4
    assert receipt["prompt_tokens"] == 6000
    assert receipt["final_logits_positions"] == 1
    assert receipt["fallback_reason"] == ""
    assert receipt["prefix_chunks"] == ceil((6000 - 1) / 4)
    assert receipt["prefix_chunks"] >= 2


def test_deterministic_vlm_runtime_leaves_receipt_empty_when_unconfigured() -> None:
    runtime = DeterministicVLMRuntime()
    model = WorkerModelCatalog.dev_vlm_model()
    loaded_model = runtime.load_model(model)
    prepared = _text_only_prepared_request(" ".join(f"token{i}" for i in range(40)))

    runtime._ensure_fast_path_probe(loaded_model, prepared, seq_len=6000)

    assert runtime.last_probe_snapshot().text_prefill_chunk_receipt == {}


def test_deterministic_vlm_reports_media_present_fallback_for_image_request() -> None:
    model = WorkerModelCatalog.dev_vlm_model()
    model.ext["melix.vlm.text_prefill_step_size"] = "4"

    _, receipt = _first_generate_receipt(
        model, _vision_message(), "vlm-text-prefill-media"
    )

    assert receipt["prefill_mode"] == TEXT_PREFILL_SINGLE_FORWARD
    assert receipt["fallback_reason"] == TEXT_PREFILL_FALLBACK_MEDIA_PRESENT
