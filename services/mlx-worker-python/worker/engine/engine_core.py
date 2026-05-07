from __future__ import annotations

from collections.abc import Iterator
import json

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry
from worker.runtime.mlx_text_runtime import RuntimeToolCallEvent, RuntimeTokenEvent
from worker.runtime.mlx_text_runtime import resolve_text_stop_contract
from worker.runtime.runtime_utils import callable_accepts_kwarg as _callable_accepts_kwarg
from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


class EngineCore:
    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def generate(self, request: inference_pb2.GenerateRequest) -> Iterator[inference_pb2.ExecuteEvent]:
        request_id = request.execution.id.request_id
        loaded_model = self._registry.get_loaded_model(request.execution.model_handle)
        if loaded_model is None:
            yield self._error_event(request_id, 1, "not_found", "Unknown model handle.")
            return

        runtime = self._registry.runtime_for_loaded_model(loaded_model)
        state = self._registry.start_request(request_id, runtime_kind=loaded_model.runtime_kind)
        assembler = self._stream_assembler(request)
        stop_contract = resolve_text_stop_contract(
            loaded_model.runtime_model,
            request.sampling,
            request.execution.ext,
        )
        effective_sampling = self._sampling_with_resolved_stop(request.sampling, stop_contract.sequences)
        prompt_tokens_default: int | None = None
        last_token_event: RuntimeTokenEvent | None = None
        turn_boundary_stop_reason = ""

        try:
            template_kwargs = self._chat_template_kwargs(request)
            prompt = runtime.render_prompt(
                request.messages,
                loaded_model=loaded_model.runtime_model,
                template_kwargs=template_kwargs,
                execution_ext=request.execution.ext,
            )

            def prompt_token_default() -> int:
                nonlocal prompt_tokens_default
                if prompt_tokens_default is None:
                    prompt_tokens_default = (
                        runtime.prompt_token_count(prompt)
                        if hasattr(runtime, "prompt_token_count")
                        else len(prompt.split())
                    )
                return prompt_tokens_default

            generate_kwargs: dict[str, object] = {"execution_ext": request.execution.ext}
            if _callable_accepts_kwarg(runtime.generate_tokens, "acceleration_policy"):
                generate_kwargs["acceleration_policy"] = request.execution.acceleration
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
                        seq=state.allocate_seq(),
                        tool_call_delta=inference_pb2.ToolCallDelta(
                            call_id=runtime_event.call_id,
                            tool_name=runtime_event.tool_name,
                            arguments_json_fragment=runtime_event.arguments_json_fragment,
                        ),
                    )
                    continue

                last_token_event = runtime_event
                if runtime_event.finish_reason == "stop_sequence":
                    turn_boundary_stop_reason = "stop_sequence"
                for delta in assembler.accept(
                    StreamFragment(text=runtime_event.text, raw_text=runtime_event.raw_text)
                ):
                    if delta.reasoning_text:
                        yield inference_pb2.ExecuteEvent(
                            request_id=request_id,
                            execution_kind="generate",
                            seq=state.allocate_seq(),
                            reasoning_delta=inference_pb2.ReasoningDelta(
                                text=delta.reasoning_text,
                                raw_text=delta.raw_text,
                                mode_source=request.execution.reasoning.mode_source,
                            ),
                        )
                    if delta.tool_call is not None:
                        yield inference_pb2.ExecuteEvent(
                            request_id=request_id,
                            execution_kind="generate",
                            seq=state.allocate_seq(),
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
                        state.append_token(delta.content_text)
                        yield inference_pb2.ExecuteEvent(
                            request_id=request_id,
                            execution_kind="generate",
                            seq=state.allocate_seq(),
                            token_delta=inference_pb2.TokenDelta(
                                text=delta.content_text,
                                raw_text=delta.raw_text,
                            ),
                        )

            if request.return_usage and not state.cancel_event.is_set():
                completion_tokens = len(state.emitted_tokens)
                if last_token_event is not None and last_token_event.prompt_tokens:
                    prompt_tokens = int(last_token_event.prompt_tokens)
                else:
                    prompt_tokens = prompt_token_default()
                if last_token_event is not None:
                    completion_tokens = int(last_token_event.completion_tokens or completion_tokens)
                yield inference_pb2.ExecuteEvent(
                    request_id=request_id,
                    execution_kind="generate",
                    seq=state.allocate_seq(),
                    usage_delta=inference_pb2.UsageDelta(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    ),
                )

            finish_reason = "stop"
            if state.cancel_event.is_set():
                finish_reason = "cancelled"
            elif last_token_event is not None and last_token_event.finish_reason:
                finish_reason = last_token_event.finish_reason

            assembled = assembler.completed()
            parser_metrics: dict[str, object] = dict(assembled.metrics)
            parser_metrics.update(
                {
                    "resolved_stop_token_count": stop_contract.resolved_stop_token_count,
                    "reasoning_flag_source": self._reasoning_flag_source(request),
                    "turn_boundary_stop_reason": turn_boundary_stop_reason or finish_reason,
                }
            )
            yield inference_pb2.ExecuteEvent(
                request_id=request_id,
                execution_kind="generate",
                seq=state.allocate_seq(),
                completed=inference_pb2.Completed(
                    finish_reason=finish_reason,
                    assistant_text=assembled.assistant_text,
                    reasoning_text=assembled.reasoning_text,
                    raw_assistant_text=assembled.raw_text,
                    reasoning_mode_source=request.execution.reasoning.mode_source,
                    reasoning_effort=request.execution.reasoning.effort,
                    reasoning_continuity_preserved=request.execution.reasoning.continuity_rehydrated,
                    parser_metrics={key: str(value) for key, value in parser_metrics.items()},
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            yield self._error_event(request_id, state.allocate_seq(), "runtime_error", str(exc))
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
        )

    @staticmethod
    def _sampling_with_resolved_stop(
        sampling: common_pb2.SamplingConfig,
        stop_sequences: tuple[str, ...],
    ) -> common_pb2.SamplingConfig:
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
