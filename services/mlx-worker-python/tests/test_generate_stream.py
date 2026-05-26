import json
from types import SimpleNamespace

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, runtime_pb2

from worker.engine import engine_core as engine_core_module
from worker.engine.engine_core import EngineCore
from worker.engine.request_state import RequestState
from worker.grpc_server import WorkerInferenceService, WorkerRuntimeService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry
from worker.runtime import mlx_text_runtime
from worker.runtime.mlx_text_runtime import (
    AutoMLXBackend,
    MLXTextRuntime,
    NativeMTPBatchTimings,
    RuntimeTokenEvent,
    RuntimeToolCallEvent,
)
from worker.runtime.multimodal_attention_policy import (
    MultimodalPrefillAttentionBudgetExceeded,
    choose_attention_prefill_policy,
)


class StreamingFakeBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(text="Hello", prompt_tokens=5, completion_tokens=1)
        yield RuntimeTokenEvent(text=" world", prompt_tokens=5, completion_tokens=2, finish_reason="length")


def test_text_native_mtp_parser_metrics_fast_paths_empty_events() -> None:
    assert engine_core_module._text_native_mtp_parser_metrics(None) == {}
    assert engine_core_module._text_native_mtp_parser_metrics(RuntimeTokenEvent(text="plain")) == {}


def test_text_native_mtp_parser_metrics_preserves_speculative_and_timing_values() -> None:
    metrics = engine_core_module._text_native_mtp_parser_metrics(
        RuntimeTokenEvent(
            text="mtp",
            speculative_accepted_tokens=3,
            speculative_rejected_tokens=1,
            speculative_target_verify_ms=2.5,
            native_mtp_timings=NativeMTPBatchTimings(
                cycle_count=2,
                mtp_head_ms=1.0,
                sample_ms=None,
                cache_ops_ms=None,
                insert_ms=None,
                prepare_ms=None,
                prompt_encode_ms=None,
                prefill_ms=None,
                batch_insert_ms=None,
                first_response_ms=None,
                first_visible_ms=None,
            ),
        )
    )

    assert metrics == {
        "text_batch_generator_speculative_cycle_count_total": "2",
        "text_batch_generator_speculative_accepted_count_total": "3",
        "text_batch_generator_speculative_rejected_count_total": "1",
        "text_batch_generator_speculative_backbone_ms_total": "2.5",
        "text_batch_generator_speculative_mtp_head_ms_total": "1.0",
    }


class TemplateCapturingTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], dict[str, object]]] = []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return "<templated-prompt>"


class TemplateAwareStreamingBackend:
    runtime_name = "fake-mlx"

    def __init__(self) -> None:
        self.tokenizer = TemplateCapturingTokenizer()
        self.prompts: list[str] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "tokenizer": self.tokenizer}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        self.prompts.append(prompt)
        yield RuntimeTokenEvent(text="templated", prompt_tokens=7, completion_tokens=1, finish_reason="stop")


class StructuredStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(
            text="",
            raw_text=(
                '<think>trace</think>'
                '<tool_call>{"name":"search","arguments":{"q":"one"}}</tool_call>'
                "visible"
            ),
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="stop",
        )


class ActionQualifiedToolStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(
            text="",
            raw_text='<|tool_call>call:terminal:run_command{"command":"gh auth status"}<tool_call|>',
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="stop",
        )


class HarmonyChannelStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(
            text="",
            raw_text=(
                '<|channel>thought\n<channel|>\n{"output":"pwd","exit_code":0}'
                "<|channel>final\n<channel|>\nRepository reviewed."
            ),
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="stop",
        )


class ShortPrefixStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        yield RuntimeTokenEvent(
            text="",
            raw_text="OK<",
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="stop",
        )


class MetadataStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        yield RuntimeTokenEvent(
            text="Alpha Beta",
            raw_text="Alpha Beta",
            token_ids=(301, 302),
            token_logprobs=(-0.11, -0.22),
            parser_observation="flush_tokens=2",
            prompt_tokens=3,
            completion_tokens=2,
            finish_reason="stop",
        )


class ThroughputStreamingBackend:
    runtime_name = "fake-mlx"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        yield RuntimeTokenEvent(
            text="fast",
            prompt_tokens=4,
            completion_tokens=1,
            prompt_tps=321.5,
            generation_tps=42.25,
            finish_reason="stop",
        )


class DecodeThroughputVLMRuntime:
    runtime_name = "fake-vlm"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 2048

    def last_probe_snapshot(self):
        return SimpleNamespace(
            preprocess_latency_ms=0.0,
            preprocess_input_bytes=0,
            preprocess_peak_memory_bytes=0,
            first_token_latency_ms=0.0,
        )

    def prefill(self, request_id, loaded_model, messages, execution_ext=None):
        _ = loaded_model
        _ = messages
        _ = execution_ext
        return SimpleNamespace(
            decode_handle=f"decode:{request_id}",
            block_table_id="block-table-1",
            block_table=common_pb2.BlockTable(),
            prompt_tokens=9,
        )

    def has_decode_session(self, decode_handle):
        _ = decode_handle
        return True

    def decode_tokens(self, loaded_model, decode_handle, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = decode_handle
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        yield RuntimeTokenEvent(
            text="vision",
            prompt_tokens=9,
            completion_tokens=1,
            prompt_tps=88.5,
            generation_tps=17.25,
            finish_reason="stop",
        )


class StopContractTokenizer:
    eos_token = "</s>"
    eos_token_id = 2


class StopContractStreamingBackend:
    runtime_name = "fake-mlx"

    def __init__(self) -> None:
        self.seen_stop_sequences: list[str] = []

    def load_model(self, model_spec):
        return {
            "model_id": model_spec.model_id,
            "metadata": dict(model_spec.ext),
            "tokenizer": StopContractTokenizer(),
        }

    def estimate_resident_bytes(self, model_spec):
        return 2048

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
        self.seen_stop_sequences = list(sampling.stop)
        yield RuntimeTokenEvent(
            text="keep</turn>drop",
            prompt_tokens=3,
            completion_tokens=1,
            finish_reason="length",
        )


class AccelerationCapturingRuntime:
    runtime_name = "fake-acceleration-runtime"

    def __init__(self) -> None:
        self.seen_acceleration_policies: list[common_pb2.AccelerationPolicy | None] = []

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 0

    def render_prompt(self, messages, loaded_model=None, template_kwargs=None, execution_ext=None):
        _ = messages
        _ = loaded_model
        _ = template_kwargs
        _ = execution_ext
        return "rendered prompt"

    def prompt_token_count(self, prompt):
        _ = prompt
        return 2

    def generate_tokens(
        self,
        loaded_model,
        prompt,
        sampling,
        cancel_event,
        execution_ext=None,
        acceleration_policy=None,
    ):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        self.seen_acceleration_policies.append(acceleration_policy)
        yield RuntimeTokenEvent(text="accelerated", prompt_tokens=2, completion_tokens=1, finish_reason="stop")


class UsageCountingRuntime:
    runtime_name = "fake-usage-counting-runtime"

    def __init__(self, *, prompt_tokens: int = 0) -> None:
        self.prompt_tokens = prompt_tokens
        self.prompt_token_count_calls = 0

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 0

    def render_prompt(self, messages, loaded_model=None, template_kwargs=None, execution_ext=None):
        _ = messages
        _ = loaded_model
        _ = template_kwargs
        _ = execution_ext
        return "count " * 1024

    def prompt_token_count(self, prompt):
        _ = prompt
        self.prompt_token_count_calls += 1
        return 1024

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
        _ = loaded_model
        _ = prompt
        _ = sampling
        _ = cancel_event
        _ = execution_ext
        yield RuntimeTokenEvent(
            text="counted",
            prompt_tokens=self.prompt_tokens,
            completion_tokens=1,
            finish_reason="stop",
        )


class AttentionBudgetFailingRuntime:
    runtime_name = "fake-attention-budget-runtime"

    def __init__(self) -> None:
        self.seen_prefill_step_size: int | None = None

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id}

    def estimate_resident_bytes(self, model_spec):
        _ = model_spec
        return 0

    def render_prompt(self, messages, loaded_model=None, template_kwargs=None, execution_ext=None):
        _ = messages
        _ = loaded_model
        _ = template_kwargs
        _ = execution_ext
        return "blocked prefill"

    def prompt_token_count(self, prompt):
        _ = prompt
        return 512

    def generate_tokens(self, loaded_model, prompt, sampling, cancel_event, execution_ext=None):
        _ = (loaded_model, sampling, cancel_event, execution_ext)
        prompt_tokens = self.prompt_token_count(prompt)
        decision = choose_attention_prefill_policy(
            family_id="gemma4-v1",
            prompt_tokens=prompt_tokens,
            budget_bytes=1,
        )
        raise MultimodalPrefillAttentionBudgetExceeded(decision)

    def prefill(self, request_id, loaded_model, messages, execution_ext=None, prefill_step_size=0):
        _ = (request_id, loaded_model, messages, execution_ext)
        self.seen_prefill_step_size = prefill_step_size
        return SimpleNamespace(
            decode_handle="attention-budget-decode",
            block_table_id="attention-budget-table",
            block_table=common_pb2.BlockTable(),
            prompt_tokens=512,
        )

    def last_probe_snapshot(self):
        return SimpleNamespace(
            preprocess_latency_ms=0.0,
            preprocess_input_bytes=0,
            preprocess_peak_memory_bytes=0,
            first_token_latency_ms=0.0,
        )


def build_services():
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StreamingFakeBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    return runtime_service, inference_service, load_response.model_handle


def build_usage_counting_services(runtime: UsageCountingRuntime):
    registry = WorkerRegistry(
        runtime=runtime,  # type: ignore[arg-type]
        model_catalog=WorkerModelCatalog(environment={}),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    return inference_service, load_response.model_handle


def generate_usage_request(model_handle: str, *, return_usage: bool) -> inference_pb2.GenerateRequest:
    return inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-usage-count"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="count tokens")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
        return_usage=return_usage,
    )


def test_generate_without_usage_skips_prompt_token_count_fallback() -> None:
    runtime = UsageCountingRuntime(prompt_tokens=0)
    inference_service, model_handle = build_usage_counting_services(runtime)

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=False), context=None))

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["counted"]
    assert not any(event.HasField("usage_delta") for event in events)
    assert runtime.prompt_token_count_calls == 0


def test_resolve_generate_stop_contract_uses_empty_tuple_key_without_stops() -> None:
    loaded_model: dict[str, object] = {"model_id": "test"}
    sampling = common_pb2.SamplingConfig(max_output_tokens=4)

    contract = engine_core_module._resolve_generate_stop_contract(loaded_model, sampling, {})

    cache = loaded_model[engine_core_module._ENGINE_STOP_CONTRACT_CACHE_FIELD]
    assert isinstance(cache, dict)
    assert cache[()] is contract


def test_generate_reuses_stop_contract_for_empty_execution_ext(monkeypatch) -> None:
    runtime = UsageCountingRuntime(prompt_tokens=0)
    inference_service, model_handle = build_usage_counting_services(runtime)
    resolve_calls = 0
    original_resolve = engine_core_module.resolve_text_stop_contract

    def counting_resolve(loaded_model, sampling, execution_ext=None):
        nonlocal resolve_calls
        resolve_calls += 1
        return original_resolve(loaded_model, sampling, execution_ext)

    monkeypatch.setattr(engine_core_module, "resolve_text_stop_contract", counting_resolve)

    for index in range(2):
        request = generate_usage_request(model_handle, return_usage=False)
        request.execution.id.request_id = f"req-stop-contract-cache-{index}"
        events = list(inference_service.Generate(request, context=None))
        assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["counted"]

    assert resolve_calls == 1


def test_sampling_with_resolved_stop_reuses_sampling_when_stop_sequences_match() -> None:
    sampling = common_pb2.SamplingConfig(max_output_tokens=4)

    resolved = EngineCore._sampling_with_resolved_stop(sampling, ())

    assert resolved is sampling


def test_sampling_with_resolved_stop_clones_when_stop_sequences_change() -> None:
    sampling = common_pb2.SamplingConfig(max_output_tokens=4, stop=["old"])

    resolved = EngineCore._sampling_with_resolved_stop(sampling, ("new",))

    assert resolved is not sampling
    assert list(resolved.stop) == ["new"]
    assert list(sampling.stop) == ["old"]


def test_generate_usage_reuses_runtime_event_prompt_tokens_without_fallback_count() -> None:
    runtime = UsageCountingRuntime(prompt_tokens=7)
    inference_service, model_handle = build_usage_counting_services(runtime)

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=True), context=None))

    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert usage.prompt_tokens == 7
    assert usage.completion_tokens == 1
    assert runtime.prompt_token_count_calls == 0


def test_generate_usage_counts_prompt_tokens_only_for_missing_event_total() -> None:
    runtime = UsageCountingRuntime(prompt_tokens=0)
    inference_service, model_handle = build_usage_counting_services(runtime)

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=True), context=None))

    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert usage.prompt_tokens == 1024
    assert usage.completion_tokens == 1
    assert runtime.prompt_token_count_calls == 1


def test_whitespace_token_count_matches_split_semantics_and_reuses_shared_cache() -> None:
    text = "  alpha\tbeta\n\u2003gamma\r\n\tdelta  "
    engine_core_module._whitespace_token_count.cache_clear()

    assert engine_core_module._whitespace_token_count(text) == len(text.split())
    assert engine_core_module._whitespace_token_count(text) == len(text.split())
    assert engine_core_module._whitespace_token_count.cache_info().hits == 1


def test_generate_streams_token_and_terminal_completion_without_request_token_accumulation() -> None:
    _, inference_service, model_handle = build_services()
    original_append_token = RequestState.append_token

    def fail_append_token(self: RequestState, token: str) -> None:
        _ = self  # pragma: no cover - regression-only failure path
        _ = token  # pragma: no cover - regression-only failure path
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "generate should use the stream assembler instead of RequestState token accumulation"
        )

    RequestState.append_token = fail_append_token
    try:
        events = list(
            inference_service.Generate(generate_usage_request(model_handle, return_usage=True), context=None)
        )
    finally:
        RequestState.append_token = original_append_token

    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))
    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert token_text == ["Hello", " world"]
    assert completed.assistant_text == "Hello world"
    assert usage.completion_tokens == 2


def test_generate_streams_token_and_terminal_completion_without_usage_preserves_finish_reason() -> None:
    _, inference_service, model_handle = build_services()

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-generate-no-usage-finish"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=False,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == ["Hello", " world"]
    assert completed.finish_reason == "length"
    assert completed.assistant_text == "Hello world"
    assert not any(event.HasField("usage_delta") for event in events)


def test_generate_streams_token_and_terminal_completion() -> None:
    _, inference_service, model_handle = build_services()

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-generate-1"),
            model_handle=model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == ["Hello", " world"]
    assert completed.finish_reason == "length"
    assert completed.assistant_text == "Hello world"
    assert completed.parser_metrics["resolved_stop_token_count"] == "0"
    assert completed.parser_metrics["reasoning_flag_source"] == "unspecified"
    assert completed.parser_metrics["turn_boundary_stop_reason"] == "length"
    assert completed.parser_metrics["channel_state_preferred_source"] == "raw_text"
    assert completed.parser_metrics["open_tool_event_count"] == "0"
    assert completed.parser_metrics["pending_marker_tail_chars"] == "0"
    assert completed.parser_metrics["orphan_tool_event_flush_count"] == "0"
    assert completed.parser_metrics["terminal_marker_tail_flush_count"] == "0"
    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))
    assert usage.prompt_tokens == 5
    assert usage.completion_tokens == 2

    tool_schema_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-generate-tool-schema-receipt"),
            model_handle=model_handle,
            ext={
                "melix.tool_config.source": "openai_chat_tools",
                "melix.tool_config.tool_count": "5",
            },
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(name="   ", json_schema='{"type":"object"}'),
                    common_pb2.ToolDefinition(name="empty", json_schema=""),
                    common_pb2.ToolDefinition(
                        name="search",
                        json_schema='{"type":"object","properties":{"q":{"type":"string"}}}',
                    ),
                    common_pb2.ToolDefinition(
                        name="search",
                        json_schema=(
                            '{\n'
                            '  "properties": {"q": {"type": "string"}},\n'
                            '  "type": "object"\n'
                            "}"
                        ),
                    ),
                    common_pb2.ToolDefinition(name="bad", json_schema='{"type":'),
                    common_pb2.ToolDefinition(name="bad", json_schema='{"type":"object"}'),
                ],
                tool_choice="auto",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="List tools")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    tool_schema_events = list(inference_service.Generate(tool_schema_request, context=None))
    tool_schema_completed = next(
        event.completed for event in tool_schema_events if event.HasField("completed")
    )
    allowed_tools_receipt = json.loads(
        tool_schema_completed.parser_metrics["allowed_tools_receipt_json"]
    )
    assert allowed_tools_receipt["allowed_tool_names"] == ["empty", "search", "bad"]
    assert allowed_tools_receipt["schema_conflict_count"] == 1
    assert allowed_tools_receipt["schema_conflicts"] == ["bad"]

    explicit_empty_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-explicit-empty-tools-receipt"),
            model_handle=model_handle,
            ext={
                "melix.tool_config.source": "openai_chat_tools",
                "melix.tool_config.tool_count": "0",
            },
            tool_config=common_pb2.ToolConfig(),
        )
    )
    explicit_empty_receipt = json.loads(
        EngineCore._allowed_tools_receipt_json(explicit_empty_request)
    )
    assert explicit_empty_receipt["tool_config_state"] == "explicit_empty"
    assert explicit_empty_receipt["allowed_tool_count"] == 0

    suppressed_without_tools_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-suppressed-without-tools-receipt"),
            model_handle=model_handle,
            ext={"melix.tool_parser.suppressed_reason": "partial_json"},
        )
    )
    suppressed_without_tools_receipt = json.loads(
        EngineCore._allowed_tools_receipt_json(suppressed_without_tools_request)
    )
    assert suppressed_without_tools_receipt["tool_config_state"] == "omitted"
    assert suppressed_without_tools_receipt["suppressed_reason"] == "partial_json"

    assert engine_core_module._parser_metric_text(0) is engine_core_module._METRIC_ZERO_TEXT
    assert engine_core_module._parser_metric_text("plain") == "plain"
    assert engine_core_module._parser_metric_text(3) == "3"

    structured_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StructuredStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    structured_runtime_service = WorkerRuntimeService(structured_registry)
    structured_inference_service = WorkerInferenceService(structured_registry)
    structured_handle = structured_runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    ).model_handle
    structured_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-generate-structured-receipts"),
            model_handle=structured_handle,
            ext={
                "melix.compat.policy_receipt_json": (
                    '{"reasoning_mode":"enabled","tool_choice_resolved":"required"}'
                ),
                "melix.reasoning.mode": "enabled",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(enabled=True),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use a tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    structured_events = list(structured_inference_service.Generate(structured_request, context=None))
    structured_completed = next(
        event.completed for event in structured_events if event.HasField("completed")
    )
    token_route_receipt = json.loads(
        structured_completed.parser_metrics["token_route_receipt_json"]
    )

    assert structured_completed.parser_metrics["generated_reasoning_delta_count"] == "1"
    assert structured_completed.parser_metrics["generated_tool_call_delta_count"] == "1"
    assert token_route_receipt["reasoning_mode"] == "enabled"
    assert token_route_receipt["tool_choice_policy"] == "required"
    assert token_route_receipt["visible_text_tokens"] == 1
    assert token_route_receipt["hidden_reasoning_tokens"] == 1

    class RuntimeToolEventBackend:
        runtime_name = "fake-mlx"

        def load_model(self, model_spec):
            return {"model_id": model_spec.model_id}

        def estimate_resident_bytes(self, model_spec):
            _ = model_spec
            return 2048

        def generate_tokens(self, loaded_model, prompt, sampling, cancel_event):
            _ = loaded_model
            _ = prompt
            _ = sampling
            _ = cancel_event
            yield RuntimeToolCallEvent(
                call_id="call-native",
                tool_name="lookup",
                arguments_json_fragment='{"q":"native"}',
            )
            yield RuntimeTokenEvent(text="done", prompt_tokens=4, completion_tokens=1, finish_reason="stop")

    native_tool_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=RuntimeToolEventBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    native_tool_runtime_service = WorkerRuntimeService(native_tool_registry)
    native_tool_inference_service = WorkerInferenceService(native_tool_registry)
    native_tool_handle = native_tool_runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    ).model_handle
    native_tool_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-native-tool-event"),
            model_handle=native_tool_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Call native tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    native_tool_events = list(
        native_tool_inference_service.Generate(native_tool_request, context=None)
    )
    native_tool_call = next(
        event.tool_call_delta for event in native_tool_events if event.HasField("tool_call_delta")
    )
    native_tool_completed = next(
        event.completed for event in native_tool_events if event.HasField("completed")
    )

    assert native_tool_call.tool_name == "lookup"
    assert native_tool_call.arguments_json_fragment == '{"q":"native"}'
    assert native_tool_completed.parser_metrics["generated_tool_call_delta_count"] == "1"
    native_tool_receipt = json.loads(
        native_tool_completed.parser_metrics["token_route_receipt_json"]
    )
    assert native_tool_receipt["route_tracking_enabled"] is True
    assert native_tool_receipt["tool_choice_policy"] == "auto"

    metadata_registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=MetadataStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    metadata_runtime_service = WorkerRuntimeService(metadata_registry)
    metadata_inference_service = WorkerInferenceService(metadata_registry)
    metadata_handle = metadata_runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    ).model_handle
    metadata_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-token-route-token-ids"),
            model_handle=metadata_handle,
            ext={"melix.reasoning.mode": "enabled"},
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Track route token ids")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    metadata_events = list(
        metadata_inference_service.Generate(metadata_request, context=None)
    )
    metadata_completed = next(
        event.completed for event in metadata_events if event.HasField("completed")
    )
    metadata_receipt = json.loads(
        metadata_completed.parser_metrics["token_route_receipt_json"]
    )
    assert metadata_receipt["route_tracking_enabled"] is True
    assert metadata_receipt["route_count"] == 2
    assert [route["token_id"] for route in metadata_receipt["routes"]] == [301, 302]

    inactive_route_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-inactive-route-receipt"),
            model_handle=model_handle,
            ext={"melix.response.created": "123"},
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    inactive_events = list(inference_service.Generate(inactive_route_request, context=None))
    inactive_completed = next(
        event.completed for event in inactive_events if event.HasField("completed")
    )
    inactive_receipt = json.loads(
        inactive_completed.parser_metrics["token_route_receipt_json"]
    )
    assert inactive_receipt["route_tracking_enabled"] is False
    assert inactive_receipt["reasoning_mode"] == "disabled"
    assert inactive_receipt["tool_choice_policy"] == "auto"
    assert EngineCore._token_route_receipt(inactive_route_request, {}) is None
    assert json.loads(
        EngineCore._inactive_token_route_receipt_json(inactive_route_request, {})
    ) == inactive_receipt
    plain_compat_receipt = json.dumps(
        {
            "reasoning_mode": "disabled",
            "tool_choice_resolved": "auto",
        },
        sort_keys=True,
    )
    inactive_compat_request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-inactive-compat-route-receipt"),
            model_handle=model_handle,
            ext={
                "melix.compat.policy_receipt_json": plain_compat_receipt,
                "melix.compat.effective_config_hash": "plain-compat-hash",
                "melix.response.created": "1716500000",
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )
    assert EngineCore._plain_text_fast_path(inactive_compat_request) is True
    inactive_compat_events = list(inference_service.Generate(inactive_compat_request, context=None))
    inactive_compat_completed = next(
        event.completed for event in inactive_compat_events if event.HasField("completed")
    )
    inactive_compat_receipt = json.loads(
        inactive_compat_completed.parser_metrics["token_route_receipt_json"]
    )
    assert inactive_compat_receipt["route_tracking_enabled"] is False
    assert inactive_compat_receipt["reasoning_mode"] == "disabled"
    assert inactive_compat_receipt["tool_choice_policy"] == "auto"
    assert inactive_compat_completed.parser_metrics["compat_policy_receipt_json"] == plain_compat_receipt
    assert inactive_compat_completed.parser_metrics["compat_effective_config_hash"] == "plain-compat-hash"
    assert inactive_compat_completed.parser_metrics["created"] == "1716500000"
    assert EngineCore._ext_requires_token_route_tracking(
        {"melix.structured_output.mode": "json_schema"}
    ) is True
    assert EngineCore._ext_requires_token_route_tracking(
        {"melix.reasoning.mode": "adaptive"}
    ) is True
    assert EngineCore._ext_requires_token_route_tracking(
        {"melix.compat.tool_choice_resolved": "required"}
    ) is True
    assert EngineCore._ext_requires_token_route_tracking(
        {},
        {"reasoning_mode": "enabled"},
    ) is True
    active_receipt = EngineCore._active_token_route_receipt(inactive_route_request)
    assert active_receipt.enabled is True
    assert json.loads(active_receipt.to_json())["route_tracking_enabled"] is True

    class RuntimeWithBlockedAccelerationCache:
        def __setattr__(self, name, value):
            if name == "_melix_accepts_acceleration_policy":
                raise RuntimeError("cache unavailable")

        def generate_tokens(self, acceleration_policy=None):
            return ()

    blocked_runtime = RuntimeWithBlockedAccelerationCache()
    assert engine_core_module._runtime_accepts_acceleration_policy(
        blocked_runtime,
        blocked_runtime.generate_tokens,
    )

    class RuntimeWithBlockedPrefillCache:
        def __setattr__(self, name, value):
            if name == "_melix_accepts_prefill_step_size":
                raise RuntimeError("cache unavailable")

        prefill = lambda self, prefill_step_size=0: None  # noqa: E731

    blocked_prefill_runtime = RuntimeWithBlockedPrefillCache()
    assert engine_core_module._runtime_prefill_accepts_step_size(
        blocked_prefill_runtime,
        blocked_prefill_runtime.prefill,
    )
    assert EngineCore._compat_policy_receipt({}) == {}
    assert EngineCore._compat_policy_receipt({"melix.compat.policy_receipt_json": ""}) == {}
    assert EngineCore._compat_policy_receipt({"melix.compat.policy_receipt_json": "{"}) == {}
    assert EngineCore._compat_policy_receipt({"melix.compat.policy_receipt_json": "[]"}) == {}

    budget_runtime = AttentionBudgetFailingRuntime()
    budget_registry = WorkerRegistry(
        vlm_runtime=budget_runtime,  # type: ignore[arg-type]
        model_catalog=WorkerModelCatalog(),
    )
    budget_runtime_service = WorkerRuntimeService(budget_registry)
    budget_inference_service = WorkerInferenceService(budget_registry)
    budget_handle = budget_runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_vlm_model()),
        context=None,
    ).model_handle
    budget_events = list(
        budget_inference_service.Generate(
            inference_pb2.GenerateRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-attention-budget-error"),
                    model_handle=budget_handle,
                ),
                messages=[
                    common_pb2.ChatMessage(
                        role="user",
                        parts=[common_pb2.MessagePart(text="budget")],
                    )
                ],
                sampling=common_pb2.SamplingConfig(max_output_tokens=4),
                stream=True,
            ),
            context=None,
        )
    )
    budget_error = budget_events[0].error.error
    assert budget_error.code == "multimodal_prefill_attention_budget_exceeded"
    assert budget_error.details["auto_chunk_reason"] == "attention_budget_exceeded"
    assert budget_error.details["selected_prefill_step_size"] == "0"

    budget_prefill = budget_inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id="req-attention-budget-prefill"),
                model_handle=budget_handle,
            ),
            messages=[
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="budget")],
                )
            ],
            return_decode_handle=True,
            prefill_step_size=32,
        ),
        context=None,
    )
    assert budget_prefill.ok is True
    assert budget_runtime.seen_prefill_step_size == 32

    def failing_prefill(*args, **kwargs):
        _ = (args, kwargs)
        decision = choose_attention_prefill_policy(
            family_id="gemma4-v1",
            prompt_tokens=512,
            budget_bytes=1,
        )
        raise MultimodalPrefillAttentionBudgetExceeded(decision)

    budget_runtime.prefill = failing_prefill  # type: ignore[method-assign]
    rejected_prefill = budget_inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id="req-attention-budget-prefill-reject"),
                model_handle=budget_handle,
            ),
            messages=[
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="budget")],
                )
            ],
            return_decode_handle=True,
            prefill_step_size=32,
        ),
        context=None,
    )
    assert rejected_prefill.ok is False
    assert rejected_prefill.admission_state == common_pb2.ADMISSION_REJECTED
    assert rejected_prefill.error.details["auto_chunk_reason"] == "attention_budget_exceeded"


def test_generate_streams_reasoning_tool_and_content_channels_from_raw_text() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StructuredStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-structured-stream"),
            model_handle=load_response.model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=True,
                mode_source="request_enable_thinking",
                effort="low",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use a tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    reasoning = next(event.reasoning_delta for event in events if event.HasField("reasoning_delta"))
    tool_call = next(event.tool_call_delta for event in events if event.HasField("tool_call_delta"))
    token = next(event.token_delta for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert reasoning.text == "trace"
    assert reasoning.mode_source == "request_enable_thinking"
    assert tool_call.tool_name == "search"
    assert tool_call.arguments_json_fragment == '{"q":"one"}'
    assert tool_call.fragment_index == 1
    assert tool_call.parser_mode == "qwen"
    assert tool_call.complete is True
    assert token.text == "visible"
    assert completed.assistant_text == "visible"
    assert completed.reasoning_text == "trace"
    assert completed.reasoning_mode_source == "request_enable_thinking"
    assert completed.reasoning_effort == "low"
    assert completed.parser_metrics["duplicate_tool_delta_count"] == "0"


def test_generate_stream_preserves_explicit_tool_parser_with_structured_json_mode() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=StructuredStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-structured-tools"),
            model_handle=load_response.model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.structured_output.mode": "json_schema",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(
                enabled=True,
                mode_source="request_enable_thinking",
                effort="low",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use a tool")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    tool_call = next(event.tool_call_delta for event in events if event.HasField("tool_call_delta"))
    token = next(event.token_delta for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert tool_call.tool_name == "search"
    assert tool_call.arguments_json_fragment == '{"q":"one"}'
    assert token.text == "visible"
    assert completed.assistant_text == "visible"
    assert completed.parser_metrics["stream_parser_request_context_mode"] == "tool_parser"
    assert completed.parser_metrics["tool_call_markup_leak_count"] == "0"
    assert completed.parser_metrics["reasoning_leak_count"] == "0"


def test_generate_stream_normalizes_tool_calls_to_declared_openai_tool_names() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=ActionQualifiedToolStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-normalize-openai-tool-name"),
            model_handle=load_response.model_handle,
            ext={"melix.tool_parser.mode": "xml"},
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="terminal",
                        description="Run commands.",
                        json_schema='{"type":"object"}',
                    )
                ],
                parser="xml",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use the terminal.")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    tool_call = next(event.tool_call_delta for event in events if event.HasField("tool_call_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert tool_call.tool_name == "terminal"
    assert tool_call.arguments_json_fragment == '{"command":"gh auth status"}'
    assert completed.assistant_text == ""
    assert completed.parser_metrics["tool_call_name_normalized_count"] == "1"
    assert completed.parser_metrics["unknown_tool_delta_count"] == "0"


def test_generate_stream_suppresses_harmony_thought_channel_content() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=HarmonyChannelStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-harmony-channel-output"),
            model_handle=load_response.model_handle,
            ext={"melix.harmony": "true"},
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Review the repo.")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=16),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == ["\nRepository reviewed."]
    assert completed.assistant_text == "\nRepository reviewed."
    assert "pwd" not in completed.assistant_text
    assert completed.parser_metrics["harmony_channel_hidden_count"] == "1"
    assert completed.parser_metrics["harmony_channel_markup_leak_count"] == "0"


def test_generate_stream_flushes_short_visible_prefix_before_marker_hold() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=ShortPrefixStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-short-prefix"),
            model_handle=load_response.model_handle,
            ext={"melix.tool_parser.mode": "qwen"},
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="short")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=4),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert token_text == ["OK"]
    assert completed.assistant_text == "OK<"
    assert completed.parser_metrics["stream_prefix_hold_chars"] == "1"
    assert completed.parser_metrics["stream_short_reply_flush_count"] == "1"


def test_generate_stream_forwards_token_metadata_and_effective_parser_receipt() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=MetadataStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-metadata-stream"),
            model_handle=load_response.model_handle,
            ext={
                "melix.reasoning.mode": "enabled",
                "melix.tool_parser.mode": "qwen",
            },
            reasoning=common_pb2.ReasoningConfig(enabled=True, mode_source="request"),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Emit metadata")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
        return_usage=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token = next(event.token_delta for event in events if event.HasField("token_delta"))
    completed = next(event.completed for event in events if event.HasField("completed"))
    usage = next(event.usage_delta for event in events if event.HasField("usage_delta"))

    assert token.text == "Alpha Beta"
    assert token.parser_observation == "flush_tokens=2"
    assert completed.assistant_text == "Alpha Beta"
    assert completed.parser_metrics["generated_token_count"] == "2"
    assert completed.parser_metrics["logprob_entry_count"] == "2"
    assert completed.parser_metrics["stream_interval_delta_flush_count"] == "1"
    assert '"tool_parser_mode":"qwen"' in completed.parser_metrics["effective_parser_config_json"]
    assert usage.completion_tokens == 2


def test_generate_stream_updates_loaded_model_status_throughput_fields() -> None:
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=ThroughputStreamingBackend()),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-throughput-status"),
            model_handle=load_response.model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Emit throughput")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    listed = runtime_service.ListLoadedModels(runtime_pb2.ListLoadedModelsRequest(), context=None)

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["fast"]
    assert listed.loaded_models[0].prompt_tps == 321.5
    assert listed.loaded_models[0].generation_tps == 42.25


def test_generate_stream_keeps_loaded_model_status_defaults_without_throughput() -> None:
    runtime_service, inference_service, model_handle = build_services()

    events = list(inference_service.Generate(generate_usage_request(model_handle, return_usage=False), context=None))
    listed = runtime_service.ListLoadedModels(runtime_pb2.ListLoadedModelsRequest(), context=None)

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["Hello", " world"]
    assert listed.loaded_models[0].prompt_tps == 0.0
    assert listed.loaded_models[0].generation_tps == 0.0


def test_decode_updates_loaded_model_status_throughput_fields() -> None:
    registry = WorkerRegistry(
        vlm_runtime=DecodeThroughputVLMRuntime(),  # type: ignore[arg-type]
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_vlm_model()),
        context=None,
    )
    prefill = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id="req-vlm-throughput"),
                model_handle=load_response.model_handle,
            ),
            messages=[
                common_pb2.ChatMessage(
                    role="user",
                    parts=[common_pb2.MessagePart(text="Describe the image")],
                )
            ],
            return_decode_handle=True,
            prefill_step_size=16,
        ),
        context=None,
    )

    events = list(
        inference_service.Decode(
            inference_pb2.DecodeRequest(
                execution=inference_pb2.ExecutionMetadata(
                    id=common_pb2.RequestIdentity(request_id="req-vlm-throughput"),
                    model_handle=load_response.model_handle,
                ),
                decode_handle=prefill.decode_handle,
                sampling=common_pb2.SamplingConfig(max_output_tokens=8),
            ),
            context=None,
        )
    )
    listed = runtime_service.ListLoadedModels(runtime_pb2.ListLoadedModelsRequest(), context=None)

    assert prefill.ok is True
    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["vision"]
    assert listed.loaded_models[0].prompt_tps == 88.5
    assert listed.loaded_models[0].generation_tps == 17.25


def test_generate_stream_exports_stop_contract_metrics_and_stops_at_turn_boundary() -> None:
    backend = StopContractStreamingBackend()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    model = WorkerModelCatalog.dev_text_model()
    model.ext["melix.stop_sequences"] = "</model>"
    load_response = runtime_service.LoadModel(runtime_pb2.LoadModelRequest(model=model), context=None)
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-stop-contract"),
            model_handle=load_response.model_handle,
            reasoning=common_pb2.ReasoningConfig(mode_source="request"),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="stop at boundary")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8, stop=["</turn>"]),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    token_text = [event.token_delta.text for event in events if event.HasField("token_delta")]
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert backend.seen_stop_sequences == ["</turn>", "</model>", "</s>"]
    assert token_text == ["keep"]
    assert completed.finish_reason == "stop_sequence"
    assert completed.assistant_text == "keep"
    assert completed.parser_metrics["resolved_stop_token_count"] == "4"
    assert completed.parser_metrics["reasoning_flag_source"] == "request"
    assert completed.parser_metrics["turn_boundary_stop_reason"] == "stop_sequence"


def test_text_prefill_returns_structured_unimplemented_error() -> None:
    _, inference_service, model_handle = build_services()

    response = inference_service.Prefill(
        inference_pb2.PrefillRequest(
            execution=inference_pb2.ExecutionMetadata(
                id=common_pb2.RequestIdentity(request_id="req-prefill-1"),
                model_handle=model_handle,
            )
        ),
        context=None,
    )

    assert response.ok is False
    assert response.error.code == "unimplemented"


def test_generate_applies_chat_template_kwargs_from_execution_metadata() -> None:
    backend = TemplateAwareStreamingBackend()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-template-kwargs"),
            model_handle=load_response.model_handle,
            ext={
                "melix.chat_template_kwargs.effective_json": "{\"add_generation_prompt\":false,\"continue_final_message\":true}"
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="assistant",
                name="planner",
                parts=[common_pb2.MessagePart(text="Continue the reply")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["templated"]
    assert backend.prompts == ["<templated-prompt>"]
    assert backend.tokenizer.calls == [
        (
            [{"role": "assistant", "name": "planner", "content": "Continue the reply"}],
            {
                "tokenize": False,
                "add_generation_prompt": False,
                "continue_final_message": True,
            },
        )
    ]


def test_generate_normalizes_non_leading_system_and_developer_messages_before_template_rendering() -> None:
    backend = TemplateAwareStreamingBackend()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-history-normalized"),
            model_handle=load_response.model_handle,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Previous question")],
            ),
            common_pb2.ChatMessage(
                role="assistant",
                parts=[common_pb2.MessagePart(text="Previous answer")],
            ),
            common_pb2.ChatMessage(
                role="developer",
                parts=[common_pb2.MessagePart(text="Prefer native tool calls.")],
            ),
            common_pb2.ChatMessage(
                role="system",
                parts=[common_pb2.MessagePart(text="Keep replies terse.")],
            ),
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Continue")],
            ),
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert backend.tokenizer.calls[0][0] == [
        {"role": "system", "content": "Prefer native tool calls.\n\nKeep replies terse."},
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
        {"role": "user", "content": "Continue"},
    ]
    assert request.execution.ext["melix.response_history.normalized_count"] == "2"
    assert completed.parser_metrics["response_history_normalized_count"] == "2"


def test_generate_injects_tool_config_as_native_template_tools_when_absent() -> None:
    backend = TemplateAwareStreamingBackend()
    registry = WorkerRegistry(
        runtime=MLXTextRuntime(backend=backend),
        model_catalog=WorkerModelCatalog(),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-native-tools"),
            model_handle=load_response.model_handle,
            tool_config=common_pb2.ToolConfig(
                tools=[
                    common_pb2.ToolDefinition(
                        name="search_docs",
                        description="Search local docs.",
                        json_schema='{"type":"object","properties":{"query":{"type":"string"}}}',
                    )
                ],
                parser="qwen",
            ),
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Use the search tool.")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))
    completed = next(event.completed for event in events if event.HasField("completed"))

    assert backend.tokenizer.calls[0][1]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_docs",
                "description": "Search local docs.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        }
    ]
    assert request.execution.ext["melix.tool_config.native_template_tools"] == "injected"
    assert completed.parser_metrics["native_tool_exemplar_injected_count"] == "1"


def test_runtime_metadata_helper_defensive_branches_are_stable() -> None:
    assert mlx_text_runtime._int_tuple(None) == ()
    assert mlx_text_runtime._int_tuple(["7", "bad", 8]) == (7, 8)
    assert mlx_text_runtime._int_tuple("9") == (9,)
    assert mlx_text_runtime._int_tuple("bad") == ()

    assert mlx_text_runtime._float_tuple(None) == ()
    assert mlx_text_runtime._float_tuple(["-0.5", "bad", 1]) == (-0.5, 1.0)
    assert mlx_text_runtime._float_tuple({"-0.5", "bad"}) == (-0.5,)
    assert mlx_text_runtime._float_tuple("-1.25") == (-1.25,)
    assert mlx_text_runtime._float_tuple("bad") == ()

    assert mlx_text_runtime._bytes_value(None) is None
    assert mlx_text_runtime._bytes_value(b"x") == b"x"
    assert mlx_text_runtime._bytes_value(b"") is None
    assert mlx_text_runtime._bytes_value(bytearray(b"y")) == b"y"
    assert mlx_text_runtime._bytes_value(bytearray()) is None
    assert mlx_text_runtime._bytes_value("z") is None

    assert mlx_text_runtime._first_present(None, 0, "fallback") == 0
    assert mlx_text_runtime._first_present(None, 0.0, "fallback") == 0.0
    assert mlx_text_runtime._first_present(None, b"", b"fallback") == b""
    assert mlx_text_runtime._first_present(None, None) is None

    assert mlx_text_runtime._native_template_tools(None) == []
    assert mlx_text_runtime._native_template_tools({}) == []
    assert mlx_text_runtime._native_template_tools({"melix.tool_config.tools_json": "not-json"}) == []
    assert mlx_text_runtime._native_template_tools({"melix.tool_config.tools_json": "{}"}) == []
    assert mlx_text_runtime._native_template_tools(
        {"melix.tool_config.tools_json": '[{"type":"function"}, "ignored"]'}
    ) == [{"type": "function"}]


def test_auto_mlx_backend_extracts_stream_response_token_metadata() -> None:
    class Response:
        text = "x"
        raw_text = "x"
        token_ids = [0]
        token_logprobs = [0.0]
        token_bytes = b"x"
        parser_observation = "token=42"
        finish_reason = "stop"

    def load_fn(model_path, **kwargs):
        _ = model_path
        _ = kwargs
        return "model", "tokenizer"

    def sampler_factory(**kwargs):
        return {"sampler": kwargs}

    def stream_generate_fn(model, tokenizer, prompt, **kwargs):
        _ = model
        _ = tokenizer
        _ = prompt
        _ = kwargs
        yield Response()

    backend = AutoMLXBackend(
        load_fn=load_fn,
        stream_generate_fn=stream_generate_fn,
        sampler_factory=sampler_factory,
    )
    event = next(
        iter(
            backend.generate_tokens(
                {"model": "model", "tokenizer": "tokenizer"},
                "prompt",
                common_pb2.SamplingConfig(max_output_tokens=1),
                cancel_event=type("Cancel", (), {"is_set": lambda self: False})(),
            )
        )
    )

    assert event.token_ids == (0,)
    assert event.token_logprobs == (0.0,)
    assert event.token_bytes == b"x"
    assert event.parser_observation == "token=42"


def test_prepare_native_template_tools_preserves_existing_payload_and_skips_invalid_tools() -> None:
    existing = inference_pb2.ExecutionMetadata(
        ext={"melix.tool_config.tools_json": '[{"type":"function"}]'}
    )
    EngineCore._prepare_native_template_tools(existing)
    assert existing.ext["melix.tool_config.tools_json"] == '[{"type":"function"}]'

    invalid = inference_pb2.ExecutionMetadata(
        tool_config=common_pb2.ToolConfig(
            tools=[
                common_pb2.ToolDefinition(name=" ", description="skip blank"),
                common_pb2.ToolDefinition(name="bad_schema", json_schema="{not-json"),
            ]
        )
    )
    EngineCore._prepare_native_template_tools(invalid)
    assert '"name":"bad_schema"' in invalid.ext["melix.tool_config.tools_json"]
    assert '"parameters":{}' in invalid.ext["melix.tool_config.tools_json"]


def test_generate_rejects_non_object_chat_template_kwargs_payloads() -> None:
    _, inference_service, model_handle = build_services()

    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-template-invalid-root"),
            model_handle=model_handle,
            ext={
                "melix.chat_template_kwargs.effective_json": "[1,2,3]"
            },
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Continue the reply")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))

    error = next(event.error.error for event in events if event.HasField("error"))
    assert error.code == "runtime_error"
    assert "must decode to an object" in error.message


def test_generate_forwards_acceleration_policy_to_runtimes_that_accept_it() -> None:
    runtime = AccelerationCapturingRuntime()
    registry = WorkerRegistry(
        runtime=runtime,  # type: ignore[arg-type]
        model_catalog=WorkerModelCatalog(environment={}),
    )
    runtime_service = WorkerRuntimeService(registry)
    inference_service = WorkerInferenceService(registry)
    load_response = runtime_service.LoadModel(
        runtime_pb2.LoadModelRequest(model=WorkerModelCatalog.dev_text_model()),
        context=None,
    )
    policy = common_pb2.AccelerationPolicy(
        mode=common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE,
        draft_model_id="mlx-community/gemma-4-E2B-it-assistant-bf16",
        num_draft_tokens=6,
        allow_baseline_fallback=True,
    )
    request = inference_pb2.GenerateRequest(
        execution=inference_pb2.ExecutionMetadata(
            id=common_pb2.RequestIdentity(request_id="req-acceleration-policy"),
            model_handle=load_response.model_handle,
            acceleration=policy,
        ),
        messages=[
            common_pb2.ChatMessage(
                role="user",
                parts=[common_pb2.MessagePart(text="Say hello")],
            )
        ],
        sampling=common_pb2.SamplingConfig(max_output_tokens=8),
        stream=True,
    )

    events = list(inference_service.Generate(request, context=None))

    assert [event.token_delta.text for event in events if event.HasField("token_delta")] == ["accelerated"]
    assert len(runtime.seen_acceleration_policies) == 1
    seen_policy = runtime.seen_acceleration_policies[0]
    assert seen_policy is not None
    assert seen_policy.mode == common_pb2.ACCELERATION_MODE_SPECULATIVE_DECODE
    assert seen_policy.draft_model_id == "mlx-community/gemma-4-E2B-it-assistant-bf16"
    assert seen_policy.num_draft_tokens == 6
    assert seen_policy.allow_baseline_fallback is True
