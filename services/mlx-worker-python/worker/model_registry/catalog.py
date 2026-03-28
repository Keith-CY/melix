from __future__ import annotations

import os

from packages.protocol.python.worker.v1 import common_pb2


class WorkerModelCatalog:
    def __init__(self, environment: dict[str, str] | None = None) -> None:
        self._environment = dict(environment or os.environ)
        self._models = {
            "melix-dev-text": self.dev_text_model(environment=self._environment),
            "melix-dev-embed": self.dev_embedding_model(environment=self._environment),
        }

    def get(self, model_id: str) -> common_pb2.ModelSpec | None:
        return self._models.get(model_id)

    @staticmethod
    def dev_text_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-text",
            model_path=environment.get("MELIX_DEV_TEXT_MODEL_PATH", "models/melix-dev-text"),
            model_kind="text",
            revision="dev",
            tokenizer_hash="tok-dev",
            quant_profile_id="q4",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
        )

    @staticmethod
    def dev_embedding_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-embed",
            model_path=environment.get("MELIX_DEV_EMBED_MODEL_PATH", "models/melix-dev-embed"),
            model_kind="embedding",
            revision="dev",
            tokenizer_hash="tok-embed-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
        )
