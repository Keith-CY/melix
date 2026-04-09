from __future__ import annotations


class DeterministicTextBackend:
    runtime_name = "deterministic-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        return 2_048

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        response = f"Echo: {prompt.strip() or 'empty'}"
        if cancel_event.is_set():
            return
        yield response
