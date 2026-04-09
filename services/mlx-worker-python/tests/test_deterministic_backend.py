from __future__ import annotations

from threading import Event

from worker.runtime.deterministic_backend import DeterministicTextBackend


class ModelSpec:
    def __init__(self, model_id: str, model_path: str) -> None:
        self.model_id = model_id
        self.model_path = model_path


def test_deterministic_backend_reports_model_metadata_and_tokens() -> None:
    backend = DeterministicTextBackend()
    model_spec = ModelSpec("melix-dev-text", "models/melix-dev-text")

    loaded = backend.load_model(model_spec)
    estimated = backend.estimate_resident_bytes(model_spec)
    cancel_event = Event()
    tokens = list(backend.generate_tokens(loaded, "hello live path", sampling=None, cancel_event=cancel_event))

    assert backend.runtime_name == "deterministic-text"
    assert loaded == {"model_id": "melix-dev-text", "model_path": "models/melix-dev-text"}
    assert estimated == 2048
    assert "".join(tokens) == "Echo: hello live path"


def test_deterministic_backend_compacts_large_prompts_into_one_chunk() -> None:
    backend = DeterministicTextBackend()
    model_spec = ModelSpec("melix-dev-text", "models/melix-dev-text")
    prompt = " ".join(["token"] * 1024)

    tokens = list(
        backend.generate_tokens(
            backend.load_model(model_spec),
            prompt,
            sampling=None,
            cancel_event=Event(),
        )
    )

    assert tokens == [f"Echo: {prompt}"]


def test_deterministic_backend_honors_cancellation() -> None:
    backend = DeterministicTextBackend()
    model_spec = ModelSpec("melix-dev-text", "models/melix-dev-text")
    cancel_event = Event()
    cancel_event.set()

    tokens = list(
        backend.generate_tokens(
            backend.load_model(model_spec),
            "",
            sampling=None,
            cancel_event=cancel_event,
        )
    )

    assert tokens == []
