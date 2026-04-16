from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
from typing import Any

from worker.runtime.text_family_adapters import resolve_text_family_config


class RuntimeUnavailableError(RuntimeError):
    pass


@dataclass
class RuntimeTokenEvent:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tps: float | None = None
    generation_tps: float | None = None
    peak_memory: float | None = None
    finish_reason: str | None = None


@dataclass
class RuntimeToolCallEvent:
    call_id: str
    tool_name: str
    arguments_json_fragment: str


def _normalized_ext_value(model_spec, key: str) -> str:
    return str(getattr(model_spec, "ext", {}).get(key, "") or "").strip()


def _resolve_adapter_backed_metadata(model_spec) -> dict[str, str]:
    activation_mode = _normalized_ext_value(model_spec, "melix.activation_mode")
    if activation_mode != "adapter_backed_runtime":
        return {}

    adapter_manifest_path = _normalized_ext_value(model_spec, "melix.adapter_manifest_path")
    adapter_weights_path = _normalized_ext_value(model_spec, "melix.adapter_weights_path")
    if not adapter_weights_path and adapter_manifest_path:
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
    return {
        "activation_mode": activation_mode,
        "adapter_manifest_path": adapter_manifest_path,
        "adapter_weights_path": adapter_weights_path,
        "adapter_dir": str(adapter_dir),
        "derived_from_model_id": _normalized_ext_value(model_spec, "melix.derived_from_model_id"),
        "adapter_set_hash": _normalized_ext_value(model_spec, "melix.adapter_set_hash"),
    }


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
            "model": model,
            "tokenizer": tokenizer,
            **adapter_metadata,
            **family_config.runtime_metadata(),
        }

    def estimate_resident_bytes(self, model_spec) -> int:
        return 0

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event) -> Iterable[str]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        self._ensure_runtime()
        sampler = self._sampler_factory(
            temp=float(sampling.temperature),
            top_p=float(sampling.top_p),
            top_k=int(sampling.top_k),
        )
        max_tokens = int(sampling.max_output_tokens) if int(sampling.max_output_tokens) > 0 else 256

        for response in self._stream_generate_fn(
            loaded_model["model"],
            loaded_model["tokenizer"],
            prompt,
            max_tokens=max_tokens,
            sampler=sampler,
        ):
            if cancel_event.is_set():
                return
            text = getattr(response, "text", "")
            finish_reason = getattr(response, "finish_reason", None)
            if not text and finish_reason is None:
                continue
            yield RuntimeTokenEvent(
                text=text,
                prompt_tokens=getattr(response, "prompt_tokens", None),
                completion_tokens=getattr(response, "generation_tokens", None),
                prompt_tps=getattr(response, "prompt_tps", None),
                generation_tps=getattr(response, "generation_tps", None),
                peak_memory=getattr(response, "peak_memory", None),
                finish_reason=finish_reason,
            )


class MLXTextRuntime:
    def __init__(self, backend: Any | None = None) -> None:
        self._backend = backend or AutoMLXBackend()

    @property
    def runtime_name(self) -> str:
        return getattr(self._backend, "runtime_name", "unknown-runtime")

    def load_model(self, model_spec):
        return self._backend.load_model(model_spec)

    def estimate_resident_bytes(self, model_spec) -> int:
        return int(self._backend.estimate_resident_bytes(model_spec))

    def render_prompt(
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
        _ = execution_ext
        for item in self._backend.generate_tokens(loaded_model, prompt, sampling, cancel_event):
            if isinstance(item, (RuntimeTokenEvent, RuntimeToolCallEvent)):
                yield item
            else:
                yield RuntimeTokenEvent(text=str(item))
