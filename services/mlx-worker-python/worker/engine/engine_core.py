from __future__ import annotations

from collections.abc import Iterator
import json

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry
from worker.engine.text_finalizer import (
    TextFinalizationUsage,
    apply_text_response_metrics,
    finalize_text_response,
)
from worker.runtime.mlx_text_runtime import (
    RuntimeAnnotationEvent,
    RuntimeToolCallEvent,
    RuntimeTokenEvent,
    RuntimeToolResultEvent,
)
from worker.runtime.mlx_text_runtime import resolve_text_stop_contract
from worker.runtime.multimodal_attention_policy import MultimodalPrefillAttentionBudgetExceeded
from worker.runtime.runtime_utils import callable_accepts_kwarg as _callable_accepts_kwarg
from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment
from worker.runtime.token_route_receipt import (
    TokenRouteReceipt,
    inactive_token_route_receipt_json,
)
from worker.runtime.token_counting import whitespace_token_count as _whitespace_token_count

_ENGINE_STOP_CONTRACT_CACHE_FIELD = "_melix.engine.resolved_text_stop_contract_cache"
_TOKEN_ROUTER_ID = "melix.worker.token_router"
_TOKEN_ROUTER_VERSION = "1"
_COMPACT_SORTED_JSON_ENCODER = json.JSONEncoder(separators=(",", ":"), sort_keys=True)
_METRIC_ZERO_TEXT = "0"
_DEFAULT_INACTIVE_TOKEN_ROUTE_RECEIPT_JSON = inactive_token_route_receipt_json(
    _TOKEN_ROUTER_ID,
    _TOKEN_ROUTER_VERSION,
    "disabled",
    "auto",
)
_DEFAULT_OMITTED_ALLOWED_TOOLS_RECEIPT_JSON = _COMPACT_SORTED_JSON_ENCODER.encode(
    {
        "allowed_tool_count": 0,
        "allowed_tool_names": [],
        "schema_conflict_count": 0,
        "schema_conflicts": [],
        "suppressed_reason": "",
        "tool_choice_policy": "auto",
        "tool_config_source": "",
        "tool_config_state": "omitted",
        "tool_source_ids": [],
    }
)


def _canonical_json_schema_key(schema: str) -> str:
    stripped = schema.strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    return _COMPACT_SORTED_JSON_ENCODER.encode(parsed)


def _parser_metric_text(value: int | str) -> str:
    if value == 0:
        return _METRIC_ZERO_TEXT
    return str(value)


def _text_native_mtp_parser_metrics(event: RuntimeTokenEvent | None) -> dict[str, str]:
    if event is None:
        return {}

    t = event.native_mtp_timings
    has_timing = t is not None
    has_speculative = (
        event.speculative_accepted_tokens is not None
        or event.speculative_rejected_tokens is not None
        or event.speculative_target_verify_ms is not None
    )
    has_cache = (
        event.cache_hit_mode is not None
        or event.recovered_prefix_tokens is not None
        or event.cache_fallback_reason is not None
    )
    if not has_timing and not has_speculative and not has_cache:
        return {}

    metric_fields: dict[str, object] = {
        "text_batch_generator_speculative_cycle_count_total": t.cycle_count if t else None,
        "text_batch_generator_speculative_accepted_count_total": event.speculative_accepted_tokens,
        "text_batch_generator_speculative_rejected_count_total": event.speculative_rejected_tokens,
        "text_batch_generator_speculative_backbone_ms_total": event.speculative_target_verify_ms,
        "text_batch_generator_speculative_mtp_head_ms_total": t.mtp_head_ms if t else None,
        "text_batch_generator_speculative_sample_ms_total": t.sample_ms if t else None,
        "text_batch_generator_speculative_cache_ops_ms_total": t.cache_ops_ms if t else None,
        "text_batch_generator_insert_ms": t.insert_ms if t else None,
        "text_batch_generator_prepare_ms": t.prepare_ms if t else None,
        "text_batch_generator_prompt_encode_ms": t.prompt_encode_ms if t else None,
        "text_batch_generator_prefill_ms": t.prefill_ms if t else None,
        "text_batch_generator_batch_insert_ms": t.batch_insert_ms if t else None,
        "text_batch_generator_first_response_ms": t.first_response_ms if t else None,
        "text_batch_generator_first_visible_ms": t.first_visible_ms if t else None,
        "cache_hit_mode": event.cache_hit_mode,
        "recovered_prefix_tokens": event.recovered_prefix_tokens,
        "cache_fallback_reason": event.cache_fallback_reason,
    }
    return {key: str(value) for key, value in metric_fields.items() if value is not None}


def _resolve_generate_stop_contract(
    loaded_model: object,
    sampling: common_pb2.SamplingConfig,
    execution_ext: object,
):
    if execution_ext:
        return resolve_text_stop_contract(loaded_model, sampling, execution_ext)  # type: ignore[arg-type]
    if not isinstance(loaded_model, dict):
        return resolve_text_stop_contract(loaded_model, sampling, None)

    cache_key = () if not sampling.stop else tuple(str(item) for item in sampling.stop)
    cache = loaded_model.get(_ENGINE_STOP_CONTRACT_CACHE_FIELD)
    if not isinstance(cache, dict):
        cache = {}
        loaded_model[_ENGINE_STOP_CONTRACT_CACHE_FIELD] = cache
    contract = cache.get(cache_key)
    if contract is None:
        contract = resolve_text_stop_contract(loaded_model, sampling, None)
        cache[cache_key] = contract
    return contract


def _runtime_accepts_acceleration_policy(runtime: object, generate_tokens: object) -> bool:
    cached = getattr(runtime, "_melix_accepts_acceleration_policy", None)
    if cached is not None:
        return bool(cached)
    accepts = _callable_accepts_kwarg(generate_tokens, "acceleration_policy")
    try:
        setattr(runtime, "_melix_accepts_acceleration_policy", accepts)
    except Exception:
        pass
    return accepts


def _runtime_prefill_accepts_step_size(runtime: object, prefill: object) -> bool:
    cached = getattr(runtime, "_melix_accepts_prefill_step_size", None)
    if cached is not None:
        return bool(cached)
    accepts = _callable_accepts_kwarg(prefill, "prefill_step_size")
    try:
        setattr(runtime, "_melix_accepts_prefill_step_size", accepts)
    except Exception:
        pass
    return accepts


class EngineCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def generate(self, request: inference_pb2.GenerateRequest) -> Iterator[inference_pb2.ExecuteEvent]:
        execution = request.execution
        execution_ext = execution.ext
        _routing_ext: dict[str, str] = dict(execution_ext) if execution_ext else {}
        _routing_ext["_melix.session_id"] = execution.id.session_id
        _routing_ext["_melix.model_id"] = execution.scope.model_id
        _routing_ext["_melix.model_revision"] = execution.scope.revision
        # Only forward a block size when the client set one; an unset proto field
        # is 0, which the runtime must treat as "use the default", not block_size=1.
        if execution.cache_hints.preferred_block_size > 0:
            _routing_ext["_melix.block_size"] = str(execution.cache_hints.preferred_block_size)
        _routing_ext["_melix.acceleration_mode"] = str(execution.acceleration.mode)
        _routing_ext["_melix.cache_mode"] = str(execution.cache_hints.cache_mode)
        sampling = request.sampling
        reasoning = execution.reasoning
        request_id = execution.id.request_id
        loaded_model = self._registry.get_loaded_model(execution.model_handle)
        if loaded_model is None:
            yield self._error_event(request_id, 1, "not_found", "Unknown model handle.")
            return

        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        generate_tokens = runtime.generate_tokens
        state = self._registry.start_request(request_id, runtime_kind=loaded_model.runtime_kind)
        cancel_event = state.cancel_event
        allocate_seq = state.allocate_seq
        plain_text_fast_path = self._plain_text_fast_path(request)
        compat_receipt = None if plain_text_fast_path else self._compat_policy_receipt(execution_ext)
        assembler = (
            self._plain_stream_assembler(request)
            if plain_text_fast_path
            else self._stream_assembler(request, compat_receipt)
        )
        stop_contract = _resolve_generate_stop_contract(
            loaded_model.runtime_model,
            sampling,
            execution_ext,
        )
        effective_sampling = self._sampling_with_resolved_stop(sampling, stop_contract.sequences)
        prompt_tokens_default: int | None = None
        track_usage = bool(request.return_usage)
        completion_token_count = 0
        finalized_prompt_tokens = 0
        finalized_completion_tokens = 0
        usage_trailer_emitted = False
        last_token_event: RuntimeTokenEvent | None = None
        last_finish_reason = ""
        turn_boundary_stop_reason = ""
        generated_reasoning_delta_count = 0
        generated_tool_call_delta_count = 0
        annotation_delta_count = 0
        tool_result_delta_count = 0
        accept_stream_fragment = assembler.accept
        token_route_receipt: TokenRouteReceipt | None = None
        if plain_text_fast_path:
            token_route_receipt_json = _DEFAULT_INACTIVE_TOKEN_ROUTE_RECEIPT_JSON
        else:
            reasoning_mode, tool_choice_policy, route_tracking_enabled = self._token_route_config(
                request,
                compat_receipt,
            )
            if not route_tracking_enabled:
                token_route_receipt_json = inactive_token_route_receipt_json(
                    _TOKEN_ROUTER_ID,
                    _TOKEN_ROUTER_VERSION,
                    (reasoning_mode or "disabled").strip().lower(),
                    (tool_choice_policy or "auto").strip().lower(),
                )
            else:
                token_route_receipt_json = ""
                token_route_receipt = self._active_token_route_receipt(
                    request,
                    reasoning_mode=reasoning_mode,
                    tool_choice_policy=tool_choice_policy,
                )

        try:
            template_kwargs = self._chat_template_kwargs(request) if execution_ext else None
            if execution.tool_config.tools:
                self._prepare_native_template_tools(execution)
            prompt = runtime.render_prompt(
                request.messages,
                loaded_model=loaded_model.runtime_model,
                template_kwargs=template_kwargs,
                execution_ext=execution_ext,
            )

            if _runtime_accepts_acceleration_policy(runtime, generate_tokens):
                runtime_events = generate_tokens(
                    loaded_model.runtime_model,
                    prompt,
                    effective_sampling,
                    cancel_event,
                    execution_ext=_routing_ext,
                    acceleration_policy=execution.acceleration,
                )
            else:
                runtime_events = generate_tokens(
                    loaded_model.runtime_model,
                    prompt,
                    effective_sampling,
                    cancel_event,
                    execution_ext=_routing_ext,
                )
            for runtime_event in runtime_events:
                if cancel_event.is_set():
                    break
                if isinstance(runtime_event, RuntimeToolCallEvent):
                    generated_tool_call_delta_count += 1
                    if token_route_receipt is None:
                        token_route_receipt = self._active_token_route_receipt(request, compat_receipt)
                    token_route_receipt.activate()
                    yield inference_pb2.ExecuteEvent(
                        request_id=request_id,
                        execution_kind="generate",
                        seq=allocate_seq(),
                        tool_call_delta=inference_pb2.ToolCallDelta(
                            call_id=runtime_event.call_id,
                            tool_name=runtime_event.tool_name,
                            arguments_json_fragment=runtime_event.arguments_json_fragment,
                        ),
                    )
                    continue

                if isinstance(runtime_event, RuntimeAnnotationEvent):
                    annotation_delta_count += 1
                    assembler.channel_state.open_annotation_span(
                        runtime_event.annotation_id,
                        start_offset=runtime_event.start_offset,
                        end_offset=runtime_event.end_offset,
                    )
                    assembler.channel_state.resolve_annotation_payload(
                        runtime_event.annotation_id,
                        payload_json=runtime_event.payload_json,
                    )
                    yield inference_pb2.ExecuteEvent(
                        request_id=request_id,
                        execution_kind="generate",
                        seq=allocate_seq(),
                        annotation_delta=inference_pb2.AnnotationDelta(
                            annotation_id=runtime_event.annotation_id,
                            kind=runtime_event.kind,
                            start_offset=max(0, int(runtime_event.start_offset)),
                            end_offset=max(0, int(runtime_event.end_offset)),
                            payload_json=runtime_event.payload_json,
                        ),
                    )
                    continue

                if isinstance(runtime_event, RuntimeToolResultEvent):
                    tool_result_delta_count += 1
                    assembler.channel_state.buffer_tool_result_payload()
                    yield inference_pb2.ExecuteEvent(
                        request_id=request_id,
                        execution_kind="generate",
                        seq=allocate_seq(),
                        tool_result_delta=inference_pb2.ToolResultDelta(
                            call_id=runtime_event.call_id,
                            status=runtime_event.status,
                            result_json=runtime_event.result_json,
                        ),
                    )
                    continue

                prompt_tps = runtime_event.prompt_tps
                generation_tps = runtime_event.generation_tps
                if prompt_tps is not None or generation_tps is not None:
                    self._registry.record_loaded_model_throughput(
                        loaded_model.handle,
                        prompt_tps=prompt_tps,
                        generation_tps=generation_tps,
                    )
                finish_reason = runtime_event.finish_reason
                if finish_reason:
                    last_finish_reason = finish_reason
                    if finish_reason == "stop_sequence":
                        turn_boundary_stop_reason = "stop_sequence"
                if track_usage:
                    last_token_event = runtime_event
                if (
                    runtime_event.token_ids
                    or runtime_event.token_logprobs
                    or runtime_event.token_bytes is not None
                    or runtime_event.parser_observation
                ):
                    stream_fragment = StreamFragment(
                        text=runtime_event.text,
                        raw_text=runtime_event.raw_text,
                        token_ids=runtime_event.token_ids,
                        token_logprobs=runtime_event.token_logprobs,
                        token_bytes=runtime_event.token_bytes,
                        parser_observation=runtime_event.parser_observation,
                    )
                else:
                    stream_fragment = StreamFragment(runtime_event.text, runtime_event.raw_text)
                if token_route_receipt is not None and runtime_event.token_ids:
                    token_route_receipt.append_token_ids(runtime_event.token_ids)
                for delta in accept_stream_fragment(stream_fragment):
                    if delta.reasoning_text:
                        generated_reasoning_delta_count += 1
                        if token_route_receipt is not None:
                            token_route_receipt.activate()
                            token_route_receipt.record_span(
                                channel="hidden_reasoning",
                                channel_source="reasoning_tag",
                                token_count=delta.token_count,
                            )
                        yield inference_pb2.ExecuteEvent(
                            request_id=request_id,
                            execution_kind="generate",
                            seq=allocate_seq(),
                            reasoning_delta=inference_pb2.ReasoningDelta(
                                text=delta.reasoning_text,
                                raw_text=delta.raw_text,
                                mode_source=reasoning.mode_source,
                            ),
                        )
                    if delta.tool_call is not None:
                        generated_tool_call_delta_count += 1
                        if token_route_receipt is not None:
                            token_route_receipt.activate()
                            token_route_receipt.record_span(
                                channel="tool_call",
                                channel_source="tool_call_tag",
                                token_count=delta.token_count,
                            )
                        yield inference_pb2.ExecuteEvent(
                            request_id=request_id,
                            execution_kind="generate",
                            seq=allocate_seq(),
                            tool_call_delta=inference_pb2.ToolCallDelta(
                                call_id=delta.tool_call.call_id,
                                tool_name=delta.tool_call.tool_name,
                                arguments_json_fragment=delta.tool_call.arguments_json_fragment,
                                fragment_index=delta.tool_call.fragment_index,
                                parser_mode=delta.tool_call.parser_mode,
                                complete=delta.tool_call.complete,
                            ),
                        )
                    if delta.content_text:
                        if token_route_receipt is not None:
                            token_route_receipt.record_span(
                                channel="visible_text",
                                channel_source="raw_text",
                                token_count=delta.token_count,
                                consume_all_available=True,
                            )
                        if track_usage:
                            completion_token_count += 1
                        yield inference_pb2.ExecuteEvent(
                            request_id=request_id,
                            execution_kind="generate",
                            seq=allocate_seq(),
                            token_delta=inference_pb2.TokenDelta(
                                text=delta.content_text,
                                raw_text=delta.raw_text,
                                parser_observation=delta.parser_observation,
                            ),
                        )

            if track_usage and not cancel_event.is_set():
                completion_tokens = completion_token_count
                if last_token_event is not None and last_token_event.prompt_tokens:
                    prompt_tokens = int(last_token_event.prompt_tokens)
                else:
                    if prompt_tokens_default is None:
                        prompt_tokens_default = (
                            runtime.prompt_token_count(prompt)
                            if hasattr(runtime, "prompt_token_count")
                            else _whitespace_token_count(prompt)
                        )
                    prompt_tokens = prompt_tokens_default
                if last_token_event is not None:
                    completion_tokens = int(last_token_event.completion_tokens or completion_tokens)
                finalized_prompt_tokens = prompt_tokens
                finalized_completion_tokens = completion_tokens
                usage_trailer_emitted = bool(request.stream)
                yield inference_pb2.ExecuteEvent(
                    request_id=request_id,
                    execution_kind="generate",
                    seq=allocate_seq(),
                    usage_delta=inference_pb2.UsageDelta(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    ),
                )

            finish_reason = "stop"
            if cancel_event.is_set():
                finish_reason = "cancelled"
            elif last_finish_reason:
                finish_reason = last_finish_reason

            assembled = assembler.completed()
            parser_metrics = {key: _parser_metric_text(value) for key, value in assembled.metrics.items()}
            parser_metrics.update(_text_native_mtp_parser_metrics(last_token_event))
            resolved_stop_token_count = str(stop_contract.resolved_stop_token_count)
            created = execution_ext.get("melix.response.created", "")
            allowed_tools_receipt_json = self._allowed_tools_receipt_json(request)
            if plain_text_fast_path:
                response_history_normalized_count = execution_ext.get(
                    "melix.response_history.normalized_count",
                    "0",
                )
                compat_policy_receipt_json = execution_ext.get(
                    "melix.compat.policy_receipt_json",
                    "",
                )
                compat_effective_config_hash = execution_ext.get(
                    "melix.compat.effective_config_hash",
                    "",
                )
                generated_tool_call_delta_count_text = str(generated_tool_call_delta_count)
                if token_route_receipt is not None:
                    token_route_receipt_json = token_route_receipt.to_json()
                parser_metrics.update(
                    {
                        "resolved_stop_token_count": resolved_stop_token_count,
                        "response_history_normalized_count": response_history_normalized_count,
                        "native_tool_exemplar_injected_count": "0",
                        "reasoning_flag_source": reasoning.mode_source or "unspecified",
                        "compat_policy_receipt_json": compat_policy_receipt_json,
                        "compat_effective_config_hash": compat_effective_config_hash,
                        "turn_boundary_stop_reason": turn_boundary_stop_reason or finish_reason,
                        "generated_reasoning_delta_count": "0",
                        "generated_tool_call_delta_count": generated_tool_call_delta_count_text,
                        "annotation_delta_count": str(annotation_delta_count),
                        "tool_result_delta_count": str(tool_result_delta_count),
                        "token_route_receipt_json": token_route_receipt_json,
                        "allowed_tools_receipt_json": allowed_tools_receipt_json,
                    }
                )
            else:
                parser_metrics["resolved_stop_token_count"] = resolved_stop_token_count
                parser_metrics["response_history_normalized_count"] = execution_ext.get(
                    "melix.response_history.normalized_count",
                    "0",
                )
                parser_metrics["native_tool_exemplar_injected_count"] = (
                    "1" if execution_ext.get("melix.tool_config.native_template_tools") == "injected" else "0"
                )
                parser_metrics["reasoning_flag_source"] = self._reasoning_flag_source(request)
                parser_metrics["compat_policy_receipt_json"] = execution_ext.get(
                    "melix.compat.policy_receipt_json",
                    "",
                )
                parser_metrics["compat_effective_config_hash"] = execution_ext.get(
                    "melix.compat.effective_config_hash",
                    "",
                )
                parser_metrics["turn_boundary_stop_reason"] = turn_boundary_stop_reason or finish_reason
                parser_metrics["generated_reasoning_delta_count"] = str(generated_reasoning_delta_count)
                parser_metrics["generated_tool_call_delta_count"] = str(generated_tool_call_delta_count)
                parser_metrics["annotation_delta_count"] = str(annotation_delta_count)
                parser_metrics["tool_result_delta_count"] = str(tool_result_delta_count)
                if token_route_receipt is not None:
                    token_route_receipt_json = token_route_receipt.to_json()
                parser_metrics["token_route_receipt_json"] = token_route_receipt_json
                parser_metrics["allowed_tools_receipt_json"] = allowed_tools_receipt_json
            finalization_receipt = finalize_text_response(
                response_id=request_id,
                created=created,
                stream_mode=bool(request.stream),
                finish_reason=finish_reason,
                usage=TextFinalizationUsage(
                    prompt_tokens=finalized_prompt_tokens,
                    completion_tokens=finalized_completion_tokens,
                ),
                usage_trailer_emitted=usage_trailer_emitted,
                reasoning_text=assembled.reasoning_text,
                tool_call_count=assembled.tool_call_count,
                parser_metrics=parser_metrics,
            )
            apply_text_response_metrics(
                parser_metrics,
                receipt=finalization_receipt,
            )
            yield inference_pb2.ExecuteEvent(
                request_id=request_id,
                execution_kind="generate",
                seq=allocate_seq(),
                completed=inference_pb2.Completed(
                    finish_reason=finish_reason,
                    assistant_text=assembled.assistant_text,
                    reasoning_text=assembled.reasoning_text,
                    raw_assistant_text=assembled.raw_text,
                    reasoning_mode_source=reasoning.mode_source,
                    reasoning_effort=reasoning.effort,
                    reasoning_continuity_preserved=reasoning.continuity_rehydrated,
                    parser_metrics=parser_metrics,
                ),
            )
        except MultimodalPrefillAttentionBudgetExceeded as exc:
            yield self._error_event(
                request_id,
                allocate_seq(),
                exc.code,
                str(exc),
                details=exc.details,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            yield self._error_event(request_id, allocate_seq(), "runtime_error", str(exc))
        finally:
            if loaded_model.runtime_kind in {"ocr", "vlm"} and hasattr(runtime, "last_probe_snapshot"):
                self._registry.record_vision_probe(loaded_model.runtime_kind, runtime.last_probe_snapshot())
            self._registry.finish_request(request_id)

    def prefill(self, request: inference_pb2.PrefillRequest) -> inference_pb2.PrefillResponse:
        request_id = request.execution.id.request_id
        loaded_model = self._registry.get_loaded_model(request.execution.model_handle)
        if loaded_model is None:
            return inference_pb2.PrefillResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="not_found", message="Unknown model handle."),
            )

        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        if loaded_model.runtime_kind != "vlm" or not hasattr(runtime, "prefill"):
            return inference_pb2.PrefillResponse(
                ok=False,
                error=common_pb2.ErrorStatus(
                    code="unimplemented",
                    message="Prefill is only implemented for the native VLM runtime.",
                ),
            )

        self._registry.start_request(request_id, runtime_kind=loaded_model.runtime_kind)
        self._registry.set_request_phase(request_id, "prefill")

        try:
            prefill_kwargs = {
                "request_id": request_id,
                "loaded_model": loaded_model.runtime_model,
                "messages": request.messages,
                "execution_ext": request.execution.ext,
            }
            if _runtime_prefill_accepts_step_size(runtime, runtime.prefill):
                prefill_kwargs["prefill_step_size"] = request.prefill_step_size
            session = runtime.prefill(**prefill_kwargs)
            response = inference_pb2.PrefillResponse(
                ok=True,
                decode_handle=session.decode_handle if request.return_decode_handle else "",
                block_table_id=session.block_table_id,
                block_table=session.block_table,
                prompt_tokens=session.prompt_tokens,
                lifecycle_phase=common_pb2.EXECUTION_PREFILLING,
                admission_state=common_pb2.ADMISSION_ADMITTED,
                applied_acceleration=common_pb2.AccelerationPolicy(
                    mode=common_pb2.ACCELERATION_MODE_BASELINE
                ),
            )
            self._registry.record_vision_probe(loaded_model.runtime_kind, runtime.last_probe_snapshot())
            return response
        except MultimodalPrefillAttentionBudgetExceeded as exc:
            self._registry.record_vision_probe(loaded_model.runtime_kind, runtime.last_probe_snapshot())
            self._registry.finish_request(request_id)
            return inference_pb2.PrefillResponse(
                ok=False,
                admission_state=common_pb2.ADMISSION_REJECTED,
                error=common_pb2.ErrorStatus(
                    code=exc.code,
                    message=str(exc),
                    details=exc.details,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            self._registry.finish_request(request_id)
            return inference_pb2.PrefillResponse(
                ok=False,
                error=common_pb2.ErrorStatus(code="runtime_error", message=str(exc)),
            )

    def decode(self, request: inference_pb2.DecodeRequest) -> Iterator[inference_pb2.ExecuteEvent]:
        request_id = request.execution.id.request_id
        loaded_model = self._registry.get_loaded_model(request.execution.model_handle)
        if loaded_model is None:
            yield self._error_event(request_id, 1, "not_found", "Unknown model handle.", execution_kind="decode")
            return

        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        if loaded_model.runtime_kind != "vlm" or not hasattr(runtime, "decode_tokens"):
            yield self._error_event(
                request_id,
                1,
                "unimplemented",
                "Decode is only implemented for the native VLM runtime.",
                execution_kind="decode",
            )
            return
        state = self._registry.get_request(request_id)
        if state is None:
            yield self._error_event(
                request_id,
                1,
                "invalid_decode_handle",
                "Decode requires a prior prefill lifecycle.",
                execution_kind="decode",
            )
            return
        if not hasattr(runtime, "has_decode_session") or not runtime.has_decode_session(request.decode_handle):
            yield self._error_event(
                request_id,
                state.allocate_seq(),
                "invalid_decode_handle",
                "Unknown decode handle.",
                execution_kind="decode",
            )
            self._registry.finish_request(request_id)
            return

        self._registry.set_request_phase(request_id, "decode")
        last_token_event: RuntimeTokenEvent | None = None

        try:
            yield inference_pb2.ExecuteEvent(
                request_id=request_id,
                execution_kind="decode",
                seq=state.allocate_seq(),
                phase=common_pb2.EXECUTION_DECODING,
                admission_state=common_pb2.ADMISSION_ADMITTED,
                decode_started=inference_pb2.DecodeStarted(
                    decode_handle=request.decode_handle,
                    max_output_tokens=request.max_output_tokens,
                    resumed_from_prefill=True,
                ),
            )
            for runtime_event in runtime.decode_tokens(
                loaded_model.runtime_model,
                request.decode_handle,
                request.sampling,
                state.cancel_event,
                execution_ext=request.execution.ext,
            ):
                if state.cancel_event.is_set():
                    break
                if isinstance(runtime_event, RuntimeToolCallEvent):
                    yield inference_pb2.ExecuteEvent(
                        request_id=request_id,
                        execution_kind="decode",
                        seq=state.allocate_seq(),
                        phase=common_pb2.EXECUTION_DECODING,
                        admission_state=common_pb2.ADMISSION_ADMITTED,
                        tool_call_delta=inference_pb2.ToolCallDelta(
                            call_id=runtime_event.call_id,
                            tool_name=runtime_event.tool_name,
                            arguments_json_fragment=runtime_event.arguments_json_fragment,
                        ),
                    )
                    continue

                last_token_event = runtime_event
                prompt_tps = runtime_event.prompt_tps
                generation_tps = runtime_event.generation_tps
                if prompt_tps is not None or generation_tps is not None:
                    self._registry.record_loaded_model_throughput(
                        loaded_model.handle,
                        prompt_tps=prompt_tps,
                        generation_tps=generation_tps,
                    )
                if runtime_event.text:
                    state.append_token(runtime_event.text)
                    yield inference_pb2.ExecuteEvent(
                        request_id=request_id,
                        execution_kind="decode",
                        seq=state.allocate_seq(),
                        phase=common_pb2.EXECUTION_DECODING,
                        admission_state=common_pb2.ADMISSION_ADMITTED,
                        token_delta=inference_pb2.TokenDelta(text=runtime_event.text),
                    )

            if request.return_usage and not state.cancel_event.is_set():
                yield inference_pb2.ExecuteEvent(
                    request_id=request_id,
                    execution_kind="decode",
                    seq=state.allocate_seq(),
                    phase=common_pb2.EXECUTION_DECODING,
                    admission_state=common_pb2.ADMISSION_ADMITTED,
                    usage_delta=inference_pb2.UsageDelta(
                        prompt_tokens=int(last_token_event.prompt_tokens or 0) if last_token_event is not None else 0,
                        completion_tokens=(
                            int(last_token_event.completion_tokens or len(state.emitted_tokens))
                            if last_token_event is not None
                            else len(state.emitted_tokens)
                        ),
                    ),
                )

            finish_reason = "stop"
            if state.cancel_event.is_set():
                finish_reason = "cancelled"
            elif last_token_event is not None and last_token_event.finish_reason:
                finish_reason = last_token_event.finish_reason

            yield inference_pb2.ExecuteEvent(
                request_id=request_id,
                execution_kind="decode",
                seq=state.allocate_seq(),
                phase=common_pb2.EXECUTION_COMPLETED,
                admission_state=common_pb2.ADMISSION_ADMITTED,
                completed=inference_pb2.Completed(
                    finish_reason=finish_reason,
                    assistant_text=state.assistant_text,
                ),
            )
        except KeyError:
            yield self._error_event(
                request_id,
                state.allocate_seq(),
                "invalid_decode_handle",
                "Unknown decode handle.",
                execution_kind="decode",
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            yield self._error_event(
                request_id,
                state.allocate_seq(),
                "runtime_error",
                str(exc),
                execution_kind="decode",
            )
        finally:
            if loaded_model.runtime_kind in {"ocr", "vlm"} and hasattr(runtime, "last_probe_snapshot"):
                self._registry.record_vision_probe(loaded_model.runtime_kind, runtime.last_probe_snapshot())
            self._registry.finish_request(request_id)

    def abort(self, request_id: str) -> bool:
        return self._registry.abort_request(request_id)

    @staticmethod
    def _error_event(
        request_id: str,
        seq: int,
        code: str,
        message: str,
        execution_kind: str = "generate",
        details: dict[str, str] | None = None,
    ) -> inference_pb2.ExecuteEvent:
        return inference_pb2.ExecuteEvent(
            request_id=request_id,
            execution_kind=execution_kind,
            seq=seq,
            error=inference_pb2.ErrorEvent(
                error=common_pb2.ErrorStatus(code=code, message=message, details=details or {})
            ),
        )

    @staticmethod
    def _plain_text_fast_path(request: inference_pb2.GenerateRequest) -> bool:
        execution = request.execution
        return (
            not EngineCore._ext_requires_token_route_tracking(execution.ext)
            and not execution.reasoning.enabled
            and not execution.reasoning.mode
            and not execution.tool_config.tools
            and not execution.tool_config.tool_choice
        )

    @staticmethod
    def _plain_stream_assembler(request: inference_pb2.GenerateRequest) -> RequestStreamAssembler:
        return RequestStreamAssembler(
            request_id=request.execution.id.request_id,
            reasoning_enabled=False,
        )

    @staticmethod
    def _allowed_tools_receipt_json(request: inference_pb2.GenerateRequest) -> str:
        execution = request.execution
        ext = execution.ext
        if (
            not execution.tool_config.tools
            and not execution.tool_config.tool_choice
            and not ext.get("melix.compat.tool_choice_resolved", "").strip()
            and not ext.get("melix.tool_config.source", "").strip()
            and not ext.get("melix.tool_config.tool_count", "").strip()
            and not ext.get("melix.mcp.source_ids", "").strip()
            and not ext.get("melix.tool_parser.suppressed_reason", "").strip()
        ):
            return _DEFAULT_OMITTED_ALLOWED_TOOLS_RECEIPT_JSON
        seen_tools: dict[str, str] = {}
        allowed_names: list[str] = []
        schema_conflicts: list[str] = []
        for tool in execution.tool_config.tools:
            name = tool.name.strip()
            if not name:
                continue
            schema = _canonical_json_schema_key(tool.json_schema)
            previous_schema = seen_tools.get(name)
            if previous_schema is None:
                seen_tools[name] = schema
                allowed_names.append(name)
            elif previous_schema != schema and name not in schema_conflicts:
                schema_conflicts.append(name)

        raw_tool_count = ext.get("melix.tool_config.tool_count", "").strip()
        explicit_empty = (
            not allowed_names
            and execution.HasField("tool_config")
            and (raw_tool_count == "0" or bool(ext.get("melix.tool_config.source", "").strip()))
        )
        if allowed_names:
            tool_config_state = "declared"
        elif explicit_empty:
            tool_config_state = "explicit_empty"
        else:
            tool_config_state = "omitted"

        tool_choice_policy = (
            execution.tool_config.tool_choice.strip()
            or ext.get("melix.compat.tool_choice_resolved", "").strip()
            or "auto"
        )
        source_ids = [
            item.strip()
            for item in ext.get("melix.mcp.source_ids", "").split(",")
            if item.strip()
        ]
        payload = {
            "allowed_tool_names": allowed_names,
            "allowed_tool_count": len(allowed_names),
            "tool_choice_policy": tool_choice_policy,
            "tool_config_source": ext.get("melix.tool_config.source", "").strip(),
            "tool_source_ids": source_ids,
            "tool_config_state": tool_config_state,
            "schema_conflict_count": len(schema_conflicts),
            "schema_conflicts": schema_conflicts,
            "suppressed_reason": ext.get("melix.tool_parser.suppressed_reason", "").strip(),
        }
        return _COMPACT_SORTED_JSON_ENCODER.encode(payload)

    @staticmethod
    def _stream_assembler(
        request: inference_pb2.GenerateRequest,
        compat_receipt: dict[str, object] | None = None,
    ) -> RequestStreamAssembler:
        ext = request.execution.ext
        reasoning_mode = ext.get("melix.reasoning.mode", "").strip().lower()
        compat_receipt = compat_receipt if compat_receipt is not None else EngineCore._compat_policy_receipt(ext)
        compat_reasoning_mode = str(compat_receipt.get("reasoning_mode", "")).strip().lower()
        reasoning_enabled = bool(request.execution.reasoning.enabled) or reasoning_mode in {
            "enabled",
            "adaptive",
        } or compat_reasoning_mode in {
            "enabled",
            "adaptive",
        }
        return RequestStreamAssembler(
            request_id=request.execution.id.request_id,
            reasoning_enabled=reasoning_enabled,
            structured_output_mode=ext.get("melix.structured_output.mode", ""),
            tool_parser_mode=ext.get("melix.tool_parser.mode", ""),
            allowed_tool_names=(
                tuple(tool.name for tool in request.execution.tool_config.tools)
                if request.execution.tool_config.tools else None
            ),
        )

    @staticmethod
    def _token_route_config(
        request: inference_pb2.GenerateRequest,
        compat_receipt: dict[str, object] | None = None,
    ) -> tuple[str, str, bool]:
        ext = request.execution.ext
        compat_receipt = compat_receipt if compat_receipt is not None else EngineCore._compat_policy_receipt(ext)
        compat_reasoning_mode = str(compat_receipt.get("reasoning_mode", "")).strip().lower()
        compat_tool_choice = str(compat_receipt.get("tool_choice_resolved", "")).strip().lower()
        reasoning_mode = (
            ext.get("melix.reasoning.mode", "").strip().lower()
            or request.execution.reasoning.mode
            or compat_reasoning_mode
        )
        tool_choice_policy = (
            ext.get("melix.compat.tool_choice_resolved", "")
            or request.execution.tool_config.tool_choice
            or compat_tool_choice
        )
        route_tracking_enabled = (
            bool(request.execution.reasoning.enabled)
            or bool(reasoning_mode and reasoning_mode != "disabled")
            or EngineCore._ext_requires_token_route_tracking(ext, compat_receipt)
            or bool(request.execution.tool_config.tools)
            or bool(tool_choice_policy and tool_choice_policy != "auto")
        )
        return reasoning_mode, tool_choice_policy, route_tracking_enabled

    @staticmethod
    def _ext_requires_token_route_tracking(
        ext: object,
        compat_receipt: dict[str, object] | None = None,
    ) -> bool:
        if not ext and not compat_receipt:
            return False
        getter = getattr(ext, "get", lambda _key, _default="": "")
        if str(getter("melix.tool_parser.mode", "")).strip():
            return True
        if str(getter("melix.structured_output.mode", "")).strip():
            return True
        reasoning_mode = str(getter("melix.reasoning.mode", "")).strip().lower()
        if reasoning_mode and reasoning_mode != "disabled":
            return True
        tool_choice = str(getter("melix.compat.tool_choice_resolved", "")).strip().lower()
        if tool_choice and tool_choice != "auto":
            return True
        compat_receipt = compat_receipt if compat_receipt is not None else EngineCore._compat_policy_receipt(ext)
        compat_reasoning_mode = str(compat_receipt.get("reasoning_mode", "")).strip().lower()
        if compat_reasoning_mode and compat_reasoning_mode != "disabled":
            return True
        compat_tool_choice = str(compat_receipt.get("tool_choice_resolved", "")).strip().lower()
        return bool(compat_tool_choice and compat_tool_choice != "auto")

    @staticmethod
    def _token_route_receipt(
        request: inference_pb2.GenerateRequest,
        compat_receipt: dict[str, object] | None = None,
    ) -> TokenRouteReceipt | None:
        reasoning_mode, tool_choice_policy, route_tracking_enabled = EngineCore._token_route_config(
            request,
            compat_receipt,
        )
        if not route_tracking_enabled:
            return None
        return EngineCore._active_token_route_receipt(
            request,
            compat_receipt,
            reasoning_mode=reasoning_mode,
            tool_choice_policy=tool_choice_policy,
        )

    @staticmethod
    def _active_token_route_receipt(
        request: inference_pb2.GenerateRequest,
        compat_receipt: dict[str, object] | None = None,
        *,
        reasoning_mode: str = "",
        tool_choice_policy: str = "",
    ) -> TokenRouteReceipt:
        if not reasoning_mode and not tool_choice_policy:
            reasoning_mode, tool_choice_policy, _ = EngineCore._token_route_config(
                request,
                compat_receipt,
            )
        return TokenRouteReceipt(
            router_id=_TOKEN_ROUTER_ID,
            router_version=_TOKEN_ROUTER_VERSION,
            reasoning_enabled=bool(request.execution.reasoning.enabled),
            reasoning_mode=reasoning_mode,
            tool_choice_policy=tool_choice_policy,
            enabled=True,
        )

    @staticmethod
    def _inactive_token_route_receipt_json(
        request: inference_pb2.GenerateRequest,
        compat_receipt: dict[str, object] | None = None,
    ) -> str:
        reasoning_mode, tool_choice_policy, _ = EngineCore._token_route_config(
            request,
            compat_receipt,
        )
        return inactive_token_route_receipt_json(
            _TOKEN_ROUTER_ID,
            _TOKEN_ROUTER_VERSION,
            (reasoning_mode or "disabled").strip().lower(),
            (tool_choice_policy or "auto").strip().lower(),
        )

    @staticmethod
    def _compat_policy_receipt(execution_ext: object) -> dict[str, object]:
        if not execution_ext:
            return {}
        raw_receipt = str(
            getattr(execution_ext, "get", lambda _key, _default="": "")(
                "melix.compat.policy_receipt_json",
                "",
            )
        ).strip()
        if not raw_receipt:
            return {}
        try:
            payload = json.loads(raw_receipt)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _sampling_with_resolved_stop(
        sampling: common_pb2.SamplingConfig,
        stop_sequences: tuple[str, ...],
    ) -> common_pb2.SamplingConfig:
        if not stop_sequences and not sampling.stop:
            return sampling
        if tuple(sampling.stop) == stop_sequences:
            return sampling
        resolved = common_pb2.SamplingConfig()
        resolved.CopyFrom(sampling)
        del resolved.stop[:]
        resolved.stop.extend(stop_sequences)
        return resolved

    @staticmethod
    def _reasoning_flag_source(request: inference_pb2.GenerateRequest) -> str:
        return (
            request.execution.reasoning.mode_source
            or request.execution.ext.get("melix.reasoning.mode_source", "")
            or request.execution.ext.get("melix.reasoning.source", "")
            or "unspecified"
        )

    @staticmethod
    def _chat_template_kwargs(
        request: inference_pb2.GenerateRequest,
    ) -> dict[str, object] | None:
        raw_value = request.execution.ext.get("melix.chat_template_kwargs.effective_json", "").strip()
        if not raw_value:
            return None
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive branch
            raise RuntimeError("Invalid melix.chat_template_kwargs.effective_json payload.") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("melix.chat_template_kwargs.effective_json must decode to an object.")
        return parsed

    @staticmethod
    def _prepare_native_template_tools(execution: inference_pb2.ExecutionMetadata) -> None:
        if execution.ext.get("melix.tool_config.tools_json") or not execution.tool_config.tools:
            return
        tools: list[dict[str, object]] = []
        for tool in execution.tool_config.tools:
            name = tool.name.strip()
            if not name:
                continue
            parameters: object = {}
            if tool.json_schema.strip():
                try:
                    parsed_schema = json.loads(tool.json_schema)
                except json.JSONDecodeError:
                    parsed_schema = {}
                if isinstance(parsed_schema, dict):
                    parameters = parsed_schema
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                }
            )
        if tools:
            execution.ext["melix.tool_config.tools_json"] = json.dumps(
                tools,
                separators=(",", ":"),
                sort_keys=True,
            )
