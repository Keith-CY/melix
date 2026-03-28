from __future__ import annotations

from collections.abc import Iterator

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2

from worker.registry import WorkerRegistry


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
        state = self._registry.start_request(request_id)
        prompt = runtime.render_prompt(request.messages, loaded_model=loaded_model.runtime_model)
        prompt_tokens_default = (
            runtime.prompt_token_count(prompt)
            if hasattr(runtime, "prompt_token_count")
            else len(prompt.split())
        )
        last_runtime_event = None

        try:
            for runtime_event in runtime.generate_tokens(
                loaded_model.runtime_model,
                prompt,
                request.sampling,
                state.cancel_event,
            ):
                last_runtime_event = runtime_event
                if state.cancel_event.is_set():
                    break
                if runtime_event.text:
                    state.append_token(runtime_event.text)
                    yield inference_pb2.ExecuteEvent(
                        request_id=request_id,
                        execution_kind="generate",
                        seq=state.allocate_seq(),
                        token_delta=inference_pb2.TokenDelta(text=runtime_event.text),
                    )

            if request.return_usage and not state.cancel_event.is_set():
                prompt_tokens = prompt_tokens_default
                completion_tokens = len(state.emitted_tokens)
                if last_runtime_event is not None:
                    prompt_tokens = int(last_runtime_event.prompt_tokens or prompt_tokens)
                    completion_tokens = int(last_runtime_event.completion_tokens or completion_tokens)
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
            elif last_runtime_event is not None and last_runtime_event.finish_reason:
                finish_reason = last_runtime_event.finish_reason

            yield inference_pb2.ExecuteEvent(
                request_id=request_id,
                execution_kind="generate",
                seq=state.allocate_seq(),
                completed=inference_pb2.Completed(
                    finish_reason=finish_reason,
                    assistant_text=state.assistant_text,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            yield self._error_event(request_id, state.allocate_seq(), "runtime_error", str(exc))
        finally:
            self._registry.finish_request(request_id)

    def abort(self, request_id: str) -> bool:
        return self._registry.abort_request(request_id)

    @staticmethod
    def _error_event(
        request_id: str,
        seq: int,
        code: str,
        message: str,
    ) -> inference_pb2.ExecuteEvent:
        return inference_pb2.ExecuteEvent(
            request_id=request_id,
            execution_kind="generate",
            seq=seq,
            error=inference_pb2.ErrorEvent(
                error=common_pb2.ErrorStatus(code=code, message=message)
            ),
        )
