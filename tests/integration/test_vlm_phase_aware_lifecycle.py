from __future__ import annotations

from pathlib import Path
import threading
import time

import grpc

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, inference_pb2_grpc, runtime_pb2, runtime_pb2_grpc
from tests.integration.helpers import LiveMelixStack, abort_worker_request
from worker.model_registry.catalog import WorkerModelCatalog


def _load_dev_vlm_model(runtime_stub: runtime_pb2_grpc.RuntimeServiceStub) -> str:
    load_response = runtime_stub.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_vlm_model()),
        timeout=5,
    )
    assert load_response.ok is True
    assert load_response.model_handle
    return load_response.model_handle


def test_python_vlm_worker_supports_phase_aware_prefill_and_decode() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    channel = None

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        channel = grpc.insecure_channel(f"unix://{stack.python_socket_path}")
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)

        model_handle = _load_dev_vlm_model(runtime_stub)

        request_id = "integration-vlm-prefill"
        messages = [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the image."),
                    common_pb2.MessagePart(
                        image_bytes=b"integration phase aware image",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_IMAGE,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="image/png",
                            filename="integration.png",
                        ),
                    ),
                ],
            )
        ]

        prefill_response = inference_stub.Prefill(
            inference_pb2.PrefillRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                messages=messages,
                return_decode_handle=True,
                prefill_step_size=16,
            ),
            timeout=5,
        )
        assert prefill_response.ok is True
        assert prefill_response.decode_handle == f"vlm:{request_id}"
        assert prefill_response.block_table_id.startswith("vlm-block:")
        assert prefill_response.block_table.total_token_count > 0
        assert prefill_response.prompt_tokens > 0
        assert prefill_response.lifecycle_phase == common_pb2.EXECUTION_PREFILLING
        assert prefill_response.admission_state == common_pb2.ADMISSION_ADMITTED

        prefill_stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=5).stats
        assert prefill_stats.active_prefills == 1
        assert prefill_stats.active_decodes == 0

        decode_events = inference_stub.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                decode_handle=prefill_response.decode_handle,
                sampling=common_pb2.SamplingConfig(max_output_tokens=64),
                max_output_tokens=64,
                return_usage=True,
            ),
            timeout=5,
        )
        first_event = next(decode_events)

        assert first_event.decode_started.decode_handle == prefill_response.decode_handle
        assert first_event.decode_started.max_output_tokens == 64
        assert first_event.decode_started.resumed_from_prefill is True
        assert first_event.phase == common_pb2.EXECUTION_DECODING

        remaining_events = list(decode_events)
        token_text = "".join(event.token_delta.text for event in remaining_events if event.HasField("token_delta"))
        usage = next(event.usage_delta for event in remaining_events if event.HasField("usage_delta"))
        completed = next(event.completed for event in remaining_events if event.HasField("completed"))

        assert token_text == "Image content: integration phase aware image\nPrompt: Summarize the image."
        assert usage.prompt_tokens == prefill_response.prompt_tokens
        assert usage.completion_tokens > 0
        assert completed.finish_reason == "stop"
        assert completed.assistant_text == token_text

        final_stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=5).stats
        assert final_stats.active_prefills == 0
        assert final_stats.active_decodes == 0
        assert final_stats.last_probe_kind == "vlm"
    finally:
        if channel is not None:
            channel.close()
        stack.stop()


def test_python_vlm_worker_applies_family_specific_prompt_defaults() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    channel = None

    try:
        stack.start()

        channel = grpc.insecure_channel(f"unix://{stack.python_socket_path}")
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)

        model = WorkerModelCatalog.dev_vlm_model()
        model.model_id = "melix-live-paligemma-vlm"
        model.model_path = "models/melix-live-paligemma-vlm"
        model.ext["vision_family_id"] = "paligemma-v1"
        model.ext["vision_prompt_profile_id"] = "paligemma-caption-v1"
        model.ext["vision_tokenization_mode"] = "prefix"
        model.ext["vision_max_images_per_prompt"] = "1"
        model.ext["vision_supports_tool_calls"] = "false"
        model.ext["melix.multimodal_adapter_hash"] = "vision-family-paligemma-v1"

        load_response = runtime_stub.LoadModel(
            runtime_pb2.LoadModelRequest(model=model),
            timeout=5,
        )
        assert load_response.ok is True
        assert load_response.model_handle

        request_id = "integration-paligemma-prefill"
        prefill_response = inference_stub.Prefill(
            inference_pb2.PrefillRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=load_response.model_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[
                            common_pb2.MessagePart(
                                image_bytes=b"family specific image",
                                media=common_pb2.MediaMetadata(
                                    media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                    source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                                    mime_type="image/png",
                                    filename="family.png",
                                ),
                            ),
                        ],
                    )
                ],
                return_decode_handle=True,
                prefill_step_size=16,
            ),
            timeout=5,
        )
        assert prefill_response.ok is True

        decode_events = inference_stub.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=load_response.model_handle,
                ),
                decode_handle=prefill_response.decode_handle,
                sampling=common_pb2.SamplingConfig(max_output_tokens=64),
                max_output_tokens=64,
                return_usage=True,
            ),
            timeout=5,
        )
        _ = next(decode_events)
        remaining_events = list(decode_events)
        token_text = "".join(event.token_delta.text for event in remaining_events if event.HasField("token_delta"))
        completed = next(event.completed for event in remaining_events if event.HasField("completed"))

        assert token_text == "Image content: family specific image\nPrompt: Caption the image."
        assert completed.assistant_text == token_text
    finally:
        if channel is not None:
            channel.close()
        stack.stop()


def test_python_vlm_worker_supports_phase_aware_prefill_and_decode_for_video_requests() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    channel = None

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        channel = grpc.insecure_channel(f"unix://{stack.python_socket_path}")
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)

        model_handle = _load_dev_vlm_model(runtime_stub)

        request_id = "integration-vlm-video-prefill"
        messages = [
            common_pb2.ChatMessage(
                role="user",
                parts=[
                    common_pb2.MessagePart(text="Summarize the clip."),
                    common_pb2.MessagePart(
                        video_bytes=b"integration video fixture",
                        media=common_pb2.MediaMetadata(
                            media_type=common_pb2.MEDIA_TYPE_VIDEO,
                            source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                            mime_type="video/mp4",
                            format="mp4",
                            filename="integration.mp4",
                            frame_budget=5,
                            start_ms=400,
                            end_ms=2_400,
                        ),
                    ),
                ],
            )
        ]

        prefill_response = inference_stub.Prefill(
            inference_pb2.PrefillRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                messages=messages,
                return_decode_handle=True,
                prefill_step_size=16,
            ),
            timeout=5,
        )
        assert prefill_response.ok is True
        assert prefill_response.decode_handle == f"vlm:{request_id}"
        assert prefill_response.lifecycle_phase == common_pb2.EXECUTION_PREFILLING

        decode_events = inference_stub.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                decode_handle=prefill_response.decode_handle,
                sampling=common_pb2.SamplingConfig(max_output_tokens=64),
                max_output_tokens=64,
                return_usage=True,
            ),
            timeout=5,
        )
        first_event = next(decode_events)
        assert first_event.decode_started.decode_handle == prefill_response.decode_handle
        assert first_event.phase == common_pb2.EXECUTION_DECODING

        remaining_events = list(decode_events)
        token_text = "".join(event.token_delta.text for event in remaining_events if event.HasField("token_delta"))
        completed = next(event.completed for event in remaining_events if event.HasField("completed"))

        assert token_text == (
            "Video content: integration.mp4\n"
            "Frame policy: uniform_sample 5 frame(s) from 400ms to 2400ms\n"
            "Prompt: Summarize the clip."
        )
        assert completed.assistant_text == token_text

        final_stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=5).stats
        assert final_stats.last_probe_kind == "vlm"
        assert final_stats.last_video_effective_frame_count == 5
        assert final_stats.last_video_requested_frame_budget == 5
        assert final_stats.last_video_window_ms == 2_000
    finally:
        if channel is not None:
            channel.close()
        stack.stop()


def test_python_vlm_worker_records_temp_media_cleanup_metrics_for_generate() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    channel = None

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        channel = grpc.insecure_channel(f"unix://{stack.python_socket_path}")
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)
        model_handle = _load_dev_vlm_model(runtime_stub)

        request_id = "integration-vlm-temp-media-success"
        events = list(
            inference_stub.Generate(
                inference_pb2.GenerateRequest(
                    execution=inference_pb2.ExecutionMetadata(
                        id=common_pb2.RequestIdentity(request_id=request_id),
                        model_handle=model_handle,
                    ),
                    messages=[
                        common_pb2.ChatMessage(
                            role="user",
                            parts=[
                                common_pb2.MessagePart(text="Describe the image."),
                                common_pb2.MessagePart(
                                    image_bytes=b"integration temp image",
                                    media=common_pb2.MediaMetadata(
                                        media_type=common_pb2.MEDIA_TYPE_IMAGE,
                                        source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                                        mime_type="image/png",
                                        filename="integration.png",
                                    ),
                                ),
                            ],
                        )
                    ],
                    sampling=common_pb2.SamplingConfig(max_output_tokens=32),
                    stream=True,
                    return_usage=True,
                ),
                timeout=5,
            )
        )

        completed = next(event.completed for event in events if event.HasField("completed"))
        final_stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=5).stats

        assert completed.finish_reason == "stop"
        assert final_stats.last_probe_kind == "vlm"
        assert final_stats.last_temp_media_artifact_count == 1
        assert final_stats.last_temp_media_artifact_bytes == len(b"integration temp image")
        assert final_stats.last_temp_media_cleanup_latency_ms >= 0.0
        assert final_stats.last_temp_media_cleanup_failure_count == 0
    finally:
        if channel is not None:
            channel.close()
        stack.stop()


def test_python_vlm_worker_cleans_temp_media_on_cancelled_generate() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        environment_overrides={"MELIX_DETERMINISTIC_VLM_DELAY_MS": "200"},
    )
    channel = None

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        channel = grpc.insecure_channel(f"unix://{stack.python_socket_path}")
        runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        inference_stub = inference_pb2_grpc.InferenceServiceStub(channel)
        model_handle = _load_dev_vlm_model(runtime_stub)

        request_id = "integration-vlm-temp-media-cancel"
        response_stream = inference_stub.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id=request_id),
                    model_handle=model_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[
                            common_pb2.MessagePart(text="Summarize the clip."),
                            common_pb2.MessagePart(
                                video_bytes=b"integration temp video",
                                media=common_pb2.MediaMetadata(
                                    media_type=common_pb2.MEDIA_TYPE_VIDEO,
                                    source_kind=common_pb2.MEDIA_SOURCE_INLINE_BYTES,
                                    mime_type="video/mp4",
                                    format="mp4",
                                    filename="cancel.mp4",
                                    frame_budget=5,
                                    start_ms=400,
                                    end_ms=2_400,
                                ),
                            ),
                        ],
                    )
                ],
                sampling=common_pb2.SamplingConfig(max_output_tokens=32),
                stream=True,
                return_usage=True,
            ),
            timeout=5,
        )

        events: list[inference_pb2.ExecuteEvent] = []
        errors: list[BaseException] = []

        def consume_stream() -> None:
            try:
                events.extend(list(response_stream))
            except BaseException as exc:  # pragma: no cover - defensive thread capture
                errors.append(exc)

        consumer = threading.Thread(target=consume_stream, daemon=True)
        consumer.start()
        time.sleep(0.05)
        assert abort_worker_request(stack.python_socket_path, request_id) is True
        consumer.join(timeout=5)

        assert not errors
        assert consumer.is_alive() is False
        completed = next(event.completed for event in events if event.HasField("completed"))
        final_stats = runtime_stub.GetRuntimeStats(runtime_pb2.GetRuntimeStatsRequest(), timeout=5).stats

        assert completed.finish_reason == "cancelled"
        assert final_stats.last_probe_kind == "vlm"
        assert final_stats.last_temp_media_artifact_count == 1
        assert final_stats.last_temp_media_artifact_bytes == len(b"integration temp video")
        assert final_stats.last_temp_media_cleanup_latency_ms >= 0.0
        assert final_stats.last_temp_media_cleanup_failure_count == 0
    finally:
        if channel is not None:
            channel.close()
        stack.stop()
