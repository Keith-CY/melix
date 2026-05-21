from __future__ import annotations

from collections.abc import Iterator
import json

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import RuntimeToolCallEvent, RuntimeTokenEvent
from worker.runtime.mlx_text_runtime import resolve_text_stop_contract
from worker.runtime.runtime_utils import callable_accepts_kwarg as _callable_accepts_kwarg
from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment
from worker.runtime.token_counting import whitespace_token_count as _whitespace_token_count

_ENGINE_STOP_CONTRACT_CACHE_FIELD = "_melix.engine.resolved_text_stop_contract_cache"


def _resolve_generate_stop_contract(
    loaded_model: object,
    sampling: common_pb2.SamplingConfig,
    execution_ext: object,
):
    if execution_ext:
        return resolve_text_stop_contract(loaded_model, sampling, execution_ext)  # type: ignore[arg-type]
    if not isinstance(loaded_model, dict):
        return resolve_text_stop_contract(loaded_model, sampling, None)

    cache_key = tuple(str(item) for item in sampling.stop)
    cache = loaded_model.get(_ENGINE_STOP_CONTRACT_CACHE_FIELD)
    if not isinstance(cache, dict):
        cache = {}
        loaded_model[_ENGINE_STOP_CONTRACT_CACHE_FIELD] = cache
    contract = cache.get(cache_key)
    if contract is None:
        contract = resolve_text_stop_contract(loaded_model, sampling, None)
        cache[cache_key] = contract
    return contract


class EngineCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def generate(self, request: inference_pb2.GenerateRequest) -> Iterator[inference_pb2.ExecuteEvent]:
        execution = request.execution
        execution_ext = execution.ext
        sampling = request.sampling
        reasoning = execution.reasoning
        request_id = execution.id.request_id
        loaded_model = self._registry.get_loaded_model(execution.model_handle)
        if loaded_model is None:
            yield self._error_event(request_id, 1, "not_found", "Unknown model handle.")
            return

        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        state = self._registry.start_request(request_id, runtime_kind=loaded_model.runtime_kind)
        allocate_seq = state.allocate_seq
        assembler = self._stream_assembler(request)
        stop_contract = _resolve_generate_stop_contract(
            loaded_model.runtime_model,
            sampling,
            execution_ext,
        )
        effective_sampling = self._sampling_with_resolved_stop(sampling, stop_contract.sequences)
        prompt_tokens_default: int | None = None
        track_usage = bool(request.return_usage)
        completion_token_count = 0
        last_token_event: RuntimeTokenEvent | None = None
        last_finish_reason = ""
        turn_boundary_stop_reason = ""
        accept_stream_fragment = assembler.accept

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

            generate_kwargs: dict[str, object] = {"execution_ext": execution_ext}
            if _callable_accepts_kwarg(runtime.generate_tokens, "acceleration_policy"):
                generate_kwargs["acceleration_policy"] = execution.acceleration
            for runtime_event in runtime.generate_tokens(
                loaded_model.runtime_model,
                prompt,
                effective_sampling,
                state.cancel_event,
                **generate_kwargs,
            ):
                if state.cancel_event.is_set():
                    break
                if isinstance(runtime_event, RuntimeToolCallEvent):
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
                for delta in accept_stream_fragment(stream_fragment):
                    if delta.reasoning_text:
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

            if track_usage and not state.cancel_event.is_set():
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
            if state.cancel_event.is_set():
                finish_reason = "cancelled"
            elif last_finish_reason:
                finish_reason = last_finish_reason

            assembled = assembler.completed()
            parser_metrics = {key: str(value) for key, value in assembled.metrics.items()}
            parser_metrics["response_history_normalized_count"] = execution_ext.get(
                "melix.response_history.normalized_count",
                "0",
            )
            parser_metrics["native_tool_exemplar_injected_count"] = (
                "1" if execution_ext.get("melix.tool_config.native_template_tools") == "injected" else "0"
            )
            parser_metrics["resolved_stop_token_count"] = str(stop_contract.resolved_stop_token_count)
            parser_metrics["reasoning_flag_source"] = (
                reasoning.mode_source
                or execution_ext.get("melix.reasoning.mode_source", "")
                or execution_ext.get("melix.reasoning.source", "")
                or "unspecified"
            )
            parser_metrics["turn_boundary_stop_reason"] = turn_boundary_stop_reason or finish_reason
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
            session = runtime.prefill(
                request_id=request_id,
                loaded_model=loaded_model.runtime_model,
                messages=request.messages,
                execution_ext=request.execution.ext,
            )
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
    ) -> inference_pb2.ExecuteEvent:
        return inference_pb2.ExecuteEvent(
            request_id=request_id,
            execution_kind=execution_kind,
            seq=seq,
            error=inference_pb2.ErrorEvent(
                error=common_pb2.ErrorStatus(code=code, message=message)
            ),
        )

    @staticmethod
    def _stream_assembler(request: inference_pb2.GenerateRequest) -> RequestStreamAssembler:
        ext = request.execution.ext
        reasoning_mode = ext.get("melix.reasoning.mode", "").strip().lower()
        reasoning_enabled = bool(request.execution.reasoning.enabled) or reasoning_mode in {
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
