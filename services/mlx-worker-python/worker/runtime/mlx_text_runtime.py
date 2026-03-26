from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class RuntimeUnavailableError(RuntimeError):
    pass


class AutoMLXBackend:
    runtime_name = "mlx-unavailable"

    def __init__(self) -> None:
        try:
            import mlx_lm  # noqa: F401
        except ModuleNotFoundError as exc:
            self._available = False
            self._error = exc
        else:
            self._available = True
            self._error = None
            self.runtime_name = "mlx-lm"

    def load_model(self, model_spec) -> dict[str, Any]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        return 0

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event) -> Iterable[str]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        raise NotImplementedError("Real MLX token streaming is not wired in this phase-0 slice yet.")


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

    def render_prompt(self, messages) -> str:
        chunks: list[str] = []
        for message in messages:
            for part in message.parts:
                if part.WhichOneof("part") == "text":
                    chunks.append(part.text)
        return "\n".join(chunks)

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        yield from self._backend.generate_tokens(loaded_model, prompt, sampling, cancel_event)
