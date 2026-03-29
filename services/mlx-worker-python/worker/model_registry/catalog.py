from __future__ import annotations

import os

from packages.protocol.python.worker.v1 import common_pb2


class WorkerModelCatalog:
    def __init__(self, environment: dict[str, str] | None = None) -> None:
        self._environment = dict(environment or os.environ)
        self._models = {
            "melix-dev-text": self.dev_text_model(environment=self._environment),
            "melix-dev-embed": self.dev_embedding_model(environment=self._environment),
            "melix-dev-rerank": self.dev_rerank_model(environment=self._environment),
            "melix-dev-ocr": self.dev_ocr_model(environment=self._environment),
            "melix-dev-vlm": self.dev_vlm_model(environment=self._environment),
            "melix-dev-transcribe": self.dev_transcription_model(environment=self._environment),
            "melix-dev-speech": self.dev_speech_model(environment=self._environment),
            "melix-dev-image": self.dev_image_model(environment=self._environment),
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

    @staticmethod
    def dev_rerank_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-rerank",
            model_path=environment.get("MELIX_DEV_RERANK_MODEL_PATH", "models/melix-dev-rerank"),
            model_kind="rerank",
            revision="dev",
            tokenizer_hash="tok-rerank-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
        )

    @staticmethod
    def dev_ocr_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-ocr",
            model_path=environment.get("MELIX_DEV_OCR_MODEL_PATH", "models/melix-dev-ocr"),
            model_kind="ocr",
            revision="dev",
            tokenizer_hash="tok-ocr-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
        )

    @staticmethod
    def dev_vlm_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-vlm",
            model_path=environment.get("MELIX_DEV_VLM_MODEL_PATH", "models/melix-dev-vlm"),
            model_kind="vlm",
            revision="dev",
            tokenizer_hash="tok-vlm-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
        )

    @staticmethod
    def dev_transcription_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-transcribe",
            model_path=environment.get("MELIX_DEV_TRANSCRIBE_MODEL_PATH", "models/melix-dev-transcribe"),
            model_kind="transcription",
            revision="dev",
            tokenizer_hash="tok-transcribe-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
        )

    @staticmethod
    def dev_speech_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-speech",
            model_path=environment.get("MELIX_DEV_SPEECH_MODEL_PATH", "models/melix-dev-speech"),
            model_kind="speech",
            revision="dev",
            tokenizer_hash="tok-speech-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
        )

    @staticmethod
    def dev_image_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        return common_pb2.ModelSpec(
            model_id="melix-dev-image",
            model_path=environment.get("MELIX_DEV_IMAGE_MODEL_PATH", "models/melix-dev-image"),
            model_kind="image",
            revision="dev",
            tokenizer_hash="tok-image-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=4096,
        )
