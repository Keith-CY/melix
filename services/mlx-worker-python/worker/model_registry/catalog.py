from __future__ import annotations

from packages.protocol.python.worker.v1 import common_pb2


class WorkerModelCatalog:
    def __init__(self) -> None:
        self._models = {"melix-dev-text": self.dev_text_model()}

    def get(self, model_id: str) -> common_pb2.ModelSpec | None:
        return self._models.get(model_id)

    @staticmethod
    def dev_text_model() -> common_pb2.ModelSpec:
        return common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path="models/melix-dev-text",
            model_kind="text",
            revision="dev",
            tokenizer_hash="tok-dev",
            quant_profile_id="q4",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
        )
