from __future__ import annotations

import time


class DeterministicTextBackend:
    runtime_name = "deterministic-text"

    def load_model(self, model_spec):
        return {"model_id": model_spec.model_id, "model_path": model_spec.model_path}

    def estimate_resident_bytes(self, model_spec) -> int:
        return 2_048

    def generate_tokens(self, loaded_model, prompt: str, sampling, cancel_event):
        response = f"Echo: {prompt.strip() or 'empty'}"
        chunks = response.split(" ")
        for index, chunk in enumerate(chunks):
            if cancel_event.is_set():
                return
            suffix = "" if index == len(chunks) - 1 else " "
            yield f"{chunk}{suffix}"
            time.sleep(0.02)
