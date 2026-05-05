from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import replace
import importlib.util
import inspect
import json
from pathlib import Path
from typing import Any

from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.runtime_utils import (
    callable_accepts_kwarg as _callable_accepts_kwarg,
    installed_package_version as _installed_package_version,
)
from worker.runtime.text_family_adapters import resolve_text_family_config


class RuntimeUnavailableError(RuntimeError):
    pass


@dataclass
class RuntimeTokenEvent:
    text: str
    raw_text: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tps: float | None = None
    generation_tps: float | None = None
    peak_memory: float | None = None
    finish_reason: str | None = None
    speculative_acceptance_rate: float | None = None
    speculative_rollback_rate: float | None = None
    speculative_accepted_tokens: int | None = None
    speculative_rejected_tokens: int | None = None
    speculative_fallback_count: int | None = None
    speculative_num_draft_tokens: int | None = None
    speculative_draft_model_configured: bool | None = None
    speculative_draft_propose_ms: float | None = None
    speculative_target_verify_ms: float | None = None
    dflash_enabled: bool | None = None
    dflash_block_size: int | None = None
    dflash_rollback_count: int | None = None
    dflash_target_hidden_layers: int | None = None


@dataclass
class RuntimeToolCallEvent:
    call_id: str
    tool_name: str
    arguments_json_fragment: str


@dataclass(frozen=True)
class ResolvedTextStopContract:
    sequences: tuple[str, ...]
    resolved_stop_token_count: int
    source: str


def _normalized_ext_value(model_spec, key: str) -> str:
    return str(getattr(model_spec, "ext", {}).get(key, "") or "").strip()


_TEXT_STOP_SEQUENCE_KEYS = (
    "melix.stop_sequences",
    "melix.turn_boundary.stop_sequences",
    "stop_sequences",
)


def _split_stop_sequence_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                return [str(item).strip() for item in payload if str(item).strip()]
        return [part.strip() for part in stripped.split(",") if part.strip()]
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _loaded_model_metadata(loaded_model: Any) -> list[dict[str, Any]]:
    if not isinstance(loaded_model, dict):
        return []
    metadata: list[dict[str, Any]] = []
    for key in ("metadata", "model_ext", "ext"):
        value = loaded_model.get(key)
        if isinstance(value, dict):
            metadata.append(value)
    metadata.append(loaded_model)
    return metadata


def _tokenizer_eos_token_ids(tokenizer: Any) -> tuple[str, ...]:
    eos_token_id = getattr(tokenizer, "eos_token_id", None)
    if eos_token_id is None:
        return ()
    if isinstance(eos_token_id, list | tuple | set):
        return tuple(str(item) for item in eos_token_id if str(item).strip())
    return (str(eos_token_id),) if str(eos_token_id).strip() else ()


def _callable_declares_kwarg(callable_obj: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    parameter = signature.parameters.get(keyword)
    if parameter is None:
        return False
    return parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )


def resolve_text_stop_contract(
    loaded_model: Any,
    sampling: Any,
    execution_ext: dict[str, str] | None = None,
) -> ResolvedTextStopContract:
    ordered_sequences: list[str] = []
    seen_sequences: set[str] = set()
    sources: list[str] = []

    def add_sequences(values: Iterable[str], source: str) -> None:
        added = False
        for value in values:
            sequence = str(value).strip()
            if not sequence or sequence in seen_sequences:
                continue
            seen_sequences.add(sequence)
            ordered_sequences.append(sequence)
            added = True
        if added and source not in sources:
            sources.append(source)

    add_sequences((str(item) for item in getattr(sampling, "stop", [])), "request")

    metadata_sources = _loaded_model_metadata(loaded_model)
    if execution_ext:
        metadata_sources.append(dict(execution_ext))
    for metadata in metadata_sources:
        for key in _TEXT_STOP_SEQUENCE_KEYS:
            add_sequences(_split_stop_sequence_value(metadata.get(key)), "model_metadata")

    tokenizer = loaded_model.get("tokenizer") if isinstance(loaded_model, dict) else None
    eos_token_ids = _tokenizer_eos_token_ids(tokenizer)
    eos_token = str(getattr(tokenizer, "eos_token", "") or "").strip() if tokenizer is not None else ""
    if eos_token:
        add_sequences((eos_token,), "tokenizer_eos")
    elif eos_token_ids and "tokenizer_eos" not in sources:
        sources.append("tokenizer_eos")

    return ResolvedTextStopContract(
        sequences=tuple(ordered_sequences),
        resolved_stop_token_count=len(ordered_sequences) + len(eos_token_ids),
        source="+".join(sources) if sources else "none",
    )


# String constants for the ext-field activation_mode signal. Kept as the
# backward-compatible surface — existing manifests, CLI ext overrides, and
# external callers can keep passing these strings. The new authoritative
# signal is the typed ``worker.v1.RuntimeMode`` enum on ``ModelSpec``; this
# module reads the enum first and falls back to the ext string only when the
# enum is unspecified.
ACTIVATION_MODE_ADAPTER_BACKED = "adapter_backed_runtime"
ACTIVATION_MODE_FUSED_DERIVED = "fused_derived_model"


def _runtime_mode_adapter_backed_value() -> int:
    """Return ``worker.v1.RuntimeMode.RUNTIME_MODE_ADAPTER_BACKED`` at call time.

    Lazy import avoids paying a proto dependency at runtime-module load for
    the non-LoRA inference path, and — crucially — avoids the drift hazard
    of hardcoding the enum integer: if the proto ever renumbers the enum,
    this function stays correct without test scaffolding.
    """
    from packages.protocol.python.worker.v1 import common_pb2

    return int(common_pb2.RUNTIME_MODE_ADAPTER_BACKED)


def _runtime_mode_fused_value() -> int:
    from packages.protocol.python.worker.v1 import common_pb2

    return int(common_pb2.RUNTIME_MODE_FUSED_DERIVED_MODEL)


@dataclass(frozen=True)
class AdapterBackedLoadContract:
    """Typed adapter-backed load spec resolved from a ModelSpec.

    All fields are required. Callers that need adapter-backed inference get a
    fully-validated contract or a ``RuntimeError`` describing the missing
    piece. This is the replacement for the prior dict-of-strings return from
    ``_resolve_adapter_backed_metadata``.
    """

    adapter_manifest_path: str
    adapter_weights_path: str
    adapter_dir: str
    adapter_set_hash: str
    derived_from_model_id: str

    def to_runtime_metadata(self) -> dict[str, str]:
        """Return the legacy flat dict shape consumed by ``load_model`` callers."""
        return {
            "activation_mode": ACTIVATION_MODE_ADAPTER_BACKED,
            "adapter_manifest_path": self.adapter_manifest_path,
            "adapter_weights_path": self.adapter_weights_path,
            "adapter_dir": self.adapter_dir,
            "derived_from_model_id": self.derived_from_model_id,
            "adapter_set_hash": self.adapter_set_hash,
        }


def _is_adapter_backed_spec(model_spec) -> bool:
    """Return True iff the ModelSpec declares adapter-backed runtime.

    Prefers the typed ``runtime_mode`` enum when set. Falls back to the
    legacy ``ext["melix.activation_mode"]`` string only when the enum is
    ``RUNTIME_MODE_UNSPECIFIED`` — that is, on pre-enum payloads.
    """
    runtime_mode = int(getattr(model_spec, "runtime_mode", 0) or 0)
    if runtime_mode == _runtime_mode_adapter_backed_value():
        return True
    if runtime_mode == _runtime_mode_fused_value():
        return False
    # Enum unspecified — fall back to the ext string.
    return _normalized_ext_value(model_spec, "melix.activation_mode") == ACTIVATION_MODE_ADAPTER_BACKED


def _resolve_adapter_backed_contract(model_spec) -> AdapterBackedLoadContract | None:
    """Build a validated ``AdapterBackedLoadContract`` from the ModelSpec.

    Returns ``None`` when the spec is NOT adapter-backed (fused or base
    models). Raises ``RuntimeError`` when the spec declares adapter-backed
    mode but is missing required metadata — the error is treated as a hard
    contract violation rather than a silent fallback to base-only load.
    """
    if not _is_adapter_backed_spec(model_spec):
        return None

    adapter_manifest_path = _normalized_ext_value(model_spec, "melix.adapter_manifest_path")
    if not adapter_manifest_path:
        raise RuntimeError(
            "Adapter-backed runtime model is missing adapter_manifest_path metadata."
        )

    adapter_weights_path = _normalized_ext_value(model_spec, "melix.adapter_weights_path")
    if not adapter_weights_path:
        manifest_path = Path(adapter_manifest_path).expanduser()
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            adapter_weights_path = str(payload.get("weights_path", "") or "").strip()

    if not adapter_weights_path:
        raise RuntimeError(
            "Adapter-backed runtime model is missing adapter_weights_path metadata."
        )

    adapter_dir = Path(adapter_weights_path).expanduser().resolve().parent
    return AdapterBackedLoadContract(
        adapter_manifest_path=adapter_manifest_path,
        adapter_weights_path=adapter_weights_path,
        adapter_dir=str(adapter_dir),
        adapter_set_hash=_normalized_ext_value(model_spec, "melix.adapter_set_hash"),
        derived_from_model_id=_normalized_ext_value(model_spec, "melix.derived_from_model_id"),
    )


def _resolve_adapter_backed_metadata(model_spec) -> dict[str, str]:
    """Legacy flat-dict surface kept for backward compatibility.

    New callers should prefer ``_resolve_adapter_backed_contract`` to get
    typed fields; this wrapper returns ``{}`` for non-adapter-backed specs
    and the legacy dict shape otherwise.
    """
    contract = _resolve_adapter_backed_contract(model_spec)
    if contract is None:
        return {}
    return contract.to_runtime_metadata()


class AutoMLXBackend:
    runtime_name = "mlx-unavailable"

    def __init__(
        self,
        *,
        load_fn=None,
        stream_generate_fn=None,
        sampler_factory=None,
    ) -> None:
        if load_fn is not None and stream_generate_fn is not None and sampler_factory is not None:
            self._available = True
            self._error = None
            self._load_fn = load_fn
            self._stream_generate_fn = stream_generate_fn
            self._sampler_factory = sampler_factory
            self.runtime_name = "mlx-lm"
            return

        self._load_fn = None
        self._stream_generate_fn = None
        self._sampler_factory = None
        self._available = importlib.util.find_spec("mlx_lm") is not None
        self._error = None if self._available else ModuleNotFoundError("mlx_lm is not installed")
        if self._available:
            self.runtime_name = "mlx-lm"

    def _ensure_runtime(self) -> None:
        if self._load_fn is not None and self._stream_generate_fn is not None and self._sampler_factory is not None:
            return
        try:
            import mlx_lm
            from mlx_lm import load, stream_generate
            from mlx_lm.sample_utils import make_sampler
        except ModuleNotFoundError as exc:
            self._available = False
            self._error = exc
            self.runtime_name = "mlx-unavailable"
            raise RuntimeUnavailableError("mlx-lm is not installed") from exc
        else:
            self._available = True
            self._error = None
            self.runtime_name = "mlx-lm"
            self._load_fn = load
            self._stream_generate_fn = stream_generate
            self._sampler_factory = make_sampler

    def load_model(self, model_spec) -> dict[str, Any]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        self._ensure_runtime()
        adapter_metadata = _resolve_adapter_backed_metadata(model_spec)
        load_kwargs: dict[str, Any] = {"lazy": False}
        if adapter_metadata:
            load_kwargs["adapter_path"] = adapter_metadata["adapter_dir"]
        loaded = self._load_fn(model_spec.model_path, **load_kwargs)
        model, tokenizer = loaded[:2]
        family_config = resolve_text_family_config(
            dict(model_spec.ext),
            model_path=model_spec.model_path,
            default_route_kind=model_spec.ext.get("melix.capability.route_kind", "swift_text") or "swift_text",
        )
        return {
            "model_id": model_spec.model_id,
            "model_path": model_spec.model_path,
            "model_ext": dict(model_spec.ext),
            "metadata": dict(model_spec.ext),
            "model": model,
            "tokenizer": tokenizer,
            "mlx_version": _installed_package_version("mlx"),
            "mlx_lm_version": _installed_package_version("mlx-lm"),
            **adapter_metadata,
            **family_config.runtime_metadata(),
        }

    def estimate_resident_bytes(self, model_spec) -> int:
        return 0

    def generate_tokens(
        self,
        loaded_model,
        prompt: str,
        sampling,
        cancel_event,
        execution_ext: dict[str, str] | None = None,
    ) -> Iterable[str]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        self._ensure_runtime()
        sampler_kwargs: dict[str, Any] = {
            "temp": float(sampling.temperature),
            "top_p": float(sampling.top_p),
            "top_k": int(sampling.top_k),
        }
        for penalty_name in ("frequency_penalty", "presence_penalty"):
            if _callable_accepts_kwarg(self._sampler_factory, penalty_name):
                sampler_kwargs[penalty_name] = float(getattr(sampling, penalty_name, 0.0))
        sampler = self._sampler_factory(**sampler_kwargs)
        max_tokens = int(sampling.max_output_tokens) if int(sampling.max_output_tokens) > 0 else 256
        stop_contract = resolve_text_stop_contract(loaded_model, sampling, execution_ext)
        stream_kwargs: dict[str, Any] = {}
        if stop_contract.sequences:
            for kwarg_name in ("stop", "stop_words", "stop_sequences"):
                if _callable_declares_kwarg(self._stream_generate_fn, kwarg_name):
                    stream_kwargs[kwarg_name] = list(stop_contract.sequences)
                    break

        for response in self._stream_generate_fn(
            loaded_model["model"],
            loaded_model["tokenizer"],
            prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            **stream_kwargs,
        ):
            if cancel_event.is_set():
                return
            text = getattr(response, "text", "")
            finish_reason = getattr(response, "finish_reason", None)
            if not text and finish_reason is None:
                continue
            yield RuntimeTokenEvent(
                text=text,
                raw_text=getattr(response, "raw_text", None),
                prompt_tokens=getattr(response, "prompt_tokens", None),
                completion_tokens=getattr(response, "generation_tokens", None),
                prompt_tps=getattr(response, "prompt_tps", None),
                generation_tps=getattr(response, "generation_tps", None),
                peak_memory=getattr(response, "peak_memory", None),
                finish_reason=finish_reason,
                speculative_acceptance_rate=getattr(response, "speculative_acceptance_rate", None),
                speculative_rollback_rate=getattr(response, "speculative_rollback_rate", None),
                speculative_accepted_tokens=getattr(response, "speculative_accepted_tokens", None),
                speculative_rejected_tokens=getattr(response, "speculative_rejected_tokens", None),
                speculative_fallback_count=getattr(response, "speculative_fallback_count", None),
                speculative_num_draft_tokens=getattr(response, "speculative_num_draft_tokens", None),
                speculative_draft_model_configured=getattr(
                    response,
                    "speculative_draft_model_configured",
                    None,
                ),
                speculative_draft_propose_ms=getattr(response, "speculative_draft_propose_ms", None),
                speculative_target_verify_ms=getattr(response, "speculative_target_verify_ms", None),
                dflash_enabled=getattr(response, "dflash_enabled", None),
                dflash_block_size=getattr(response, "dflash_block_size", None),
                dflash_rollback_count=getattr(response, "dflash_rollback_count", None),
                dflash_target_hidden_layers=getattr(response, "dflash_target_hidden_layers", None),
            )


class MLXTextRuntime:
    def __init__(self, backend: Any | None = None, executor: MLXRuntimeExecutor | None = None) -> None:
        self._backend = backend or AutoMLXBackend()
        self._executor = executor

    @property
    def runtime_name(self) -> str:
        return getattr(self._backend, "runtime_name", "unknown-runtime")

    def load_model(self, model_spec):
        if self._executor is None:
            return self._backend.load_model(model_spec)
        return self._executor.run(lambda: self._backend.load_model(model_spec))

    def estimate_resident_bytes(self, model_spec) -> int:
        return int(self._backend.estimate_resident_bytes(model_spec))

    def score_response(
        self,
        loaded_model,
        prompt: str,
        response: str,
        execution_ext: dict[str, str] | None = None,
    ) -> float:
        scorer = getattr(self._backend, "score_response", None)
        if not callable(scorer):
            raise RuntimeUnavailableError("Text runtime backend does not support reward scoring.")

        def call_scorer() -> float:
            if _callable_accepts_kwarg(scorer, "execution_ext"):
                value = scorer(
                    loaded_model,
                    prompt,
                    response,
                    execution_ext=execution_ext,
                )
            else:
                value = scorer(loaded_model, prompt, response)
            return float(value)

        if self._executor is None:
            return call_scorer()
        return self._executor.run(call_scorer)

    def render_prompt(
        self,
        messages,
        loaded_model: Any | None = None,
        template_kwargs: dict[str, Any] | None = None,
        execution_ext: dict[str, str] | None = None,
    ) -> str:
        if self._executor is not None:
            return self._executor.run(
                lambda: self._render_prompt(
                    messages,
                    loaded_model=loaded_model,
                    template_kwargs=template_kwargs,
                    execution_ext=execution_ext,
                )
            )
        return self._render_prompt(
            messages,
            loaded_model=loaded_model,
            template_kwargs=template_kwargs,
            execution_ext=execution_ext,
        )

    def _render_prompt(
        self,
        messages,
        loaded_model: Any | None = None,
        template_kwargs: dict[str, Any] | None = None,
        execution_ext: dict[str, str] | None = None,
    ) -> str:
        _ = execution_ext
        tokenizer = None
        if isinstance(loaded_model, dict):
            tokenizer = loaded_model.get("tokenizer")
        if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
            chat_messages: list[dict[str, str]] = []
            for message in messages:
                text_parts = [part.text for part in message.parts if part.WhichOneof("part") == "text"]
                chat_message = {
                    "role": message.role,
                    "content": "\n".join(text_parts),
                }
                if message.name:
                    chat_message["name"] = message.name
                chat_messages.append(chat_message)
            resolved_template_kwargs: dict[str, Any] = {
                "tokenize": False,
                "add_generation_prompt": True,
            }
            if template_kwargs:
                resolved_template_kwargs.update(template_kwargs)
            return tokenizer.apply_chat_template(chat_messages, **resolved_template_kwargs)

        chunks: list[str] = []
        for message in messages:
            for part in message.parts:
                if part.WhichOneof("part") == "text":
                    chunks.append(part.text)
        return "\n".join(chunks)

    def generate_tokens(
        self,
        loaded_model,
        prompt: str,
        sampling,
        cancel_event,
        execution_ext: dict[str, str] | None = None,
    ):
        stop_contract = resolve_text_stop_contract(loaded_model, sampling, execution_ext)
        if self._executor is None:
            item_iterable = self._backend_generate_tokens(
                loaded_model,
                prompt,
                sampling,
                cancel_event,
                execution_ext,
            )
        else:
            item_iterable = self._executor.iterate(
                lambda: self._backend_generate_tokens(
                    loaded_model,
                    prompt,
                    sampling,
                    cancel_event,
                    execution_ext,
                )
            )
        try:
            normalized_events = (
                item if isinstance(item, (RuntimeTokenEvent, RuntimeToolCallEvent)) else RuntimeTokenEvent(text=str(item))
                for item in item_iterable
            )
            yield from self._apply_stop_sequences(normalized_events, stop_contract.sequences)
        finally:
            close = getattr(item_iterable, "close", None)
            if callable(close):
                close()

    def _backend_generate_tokens(
        self,
        loaded_model,
        prompt: str,
        sampling,
        cancel_event,
        execution_ext: dict[str, str] | None,
    ):
        if _callable_accepts_kwarg(self._backend.generate_tokens, "execution_ext"):
            return self._backend.generate_tokens(
                loaded_model,
                prompt,
                sampling,
                cancel_event,
                execution_ext=execution_ext,
            )
        return self._backend.generate_tokens(loaded_model, prompt, sampling, cancel_event)

    def _apply_stop_sequences(
        self,
        events: Iterable[RuntimeTokenEvent | RuntimeToolCallEvent],
        stop_sequences: tuple[str, ...],
    ):
        if not stop_sequences:
            yield from events
            return

        pending = ""
        last_token_event: RuntimeTokenEvent | None = None
        for event in events:
            if isinstance(event, RuntimeToolCallEvent):
                if pending and last_token_event is not None:
                    yield replace(last_token_event, text=pending, raw_text=pending, finish_reason=None)
                    pending = ""
                yield event
                continue

            last_token_event = event
            candidate = f"{pending}{event.text}"
            stop_index = _first_stop_sequence_index(candidate, stop_sequences)
            if stop_index is not None:
                visible = candidate[:stop_index]
                if visible:
                    yield replace(event, text=visible, raw_text=visible, finish_reason=None)
                yield replace(event, text="", raw_text="", finish_reason="stop_sequence")
                return

            held_suffix = _viable_stop_prefix_suffix(candidate, stop_sequences)
            if held_suffix:
                visible = candidate[: -len(held_suffix)]
                pending = held_suffix
            else:
                visible = candidate
                pending = ""

            if visible:
                yield replace(
                    event,
                    text=visible,
                    raw_text=visible,
                    finish_reason=None if pending else event.finish_reason,
                )
            elif event.finish_reason and not pending:
                yield event

        if pending and last_token_event is not None:
            yield replace(last_token_event, text=pending, raw_text=pending)


def _first_stop_sequence_index(text: str, stop_sequences: tuple[str, ...]) -> int | None:
    indexes = [index for sequence in stop_sequences if (index := text.find(sequence)) >= 0]
    return min(indexes) if indexes else None


def _viable_stop_prefix_suffix(text: str, stop_sequences: tuple[str, ...]) -> str:
    max_prefix_length = min(len(text), max((len(sequence) for sequence in stop_sequences), default=0) - 1)
    for length in range(max_prefix_length, 0, -1):
        suffix = text[-length:]
        if any(sequence.startswith(suffix) for sequence in stop_sequences):
            return suffix
    return ""
