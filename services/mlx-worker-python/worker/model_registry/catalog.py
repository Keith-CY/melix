from __future__ import annotations

import os

from packages.protocol.python.worker.v1 import common_pb2


def _normalized(value: str | None) -> str:
    return (value or "").strip()


def _infer_embedding_identity(model_path: str) -> dict[str, str]:
    normalized_path = model_path.lower()
    if "mxbai" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "mxbai-embed",
            "backend_id": "bert-v1",
            "source": "directory_name",
        }
    if "bge" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "bge-m3",
            "backend_id": "bert-v1",
            "source": "directory_name",
        }
    if "xlmr" in normalized_path or "xlm-r" in normalized_path:
        return {
            "architecture": "xlmr",
            "family_id": "xlmr",
            "backend_id": "xlmr-v1",
            "source": "directory_name",
        }
    if "bert" in normalized_path:
        return {
            "architecture": "bert",
            "family_id": "bert",
            "backend_id": "bert-v1",
            "source": "directory_name",
        }
    return {
        "architecture": "bert",
        "family_id": "bert",
        "backend_id": "bert-v1",
        "source": "default",
    }


def _embedding_backend_for_family(family_id: str) -> str:
    return "xlmr-v1" if family_id == "xlmr" else "bert-v1"


def _embedding_architecture_for_family(family_id: str) -> str:
    return "xlmr" if family_id == "xlmr" else "bert"


def _default_embedding_family_for_backend(backend_id: str, detected_family_id: str) -> str:
    if backend_id == "xlmr-v1":
        return "xlmr"
    if detected_family_id in {"bert", "bge-m3", "mxbai-embed"}:
        return detected_family_id
    return "bert"


def _default_embedding_pooling_mode(family_id: str) -> str:
    return {
        "bert": "cls",
        "xlmr": "mean",
        "bge-m3": "cls",
        "mxbai-embed": "mean",
    }.get(family_id, "cls")


def _default_embedding_dimensions(family_id: str) -> str:
    return {"mxbai-embed": "10"}.get(family_id, "8")


def _infer_rerank_identity(model_path: str) -> dict[str, str]:
    normalized_path = model_path.lower()
    if "causal-lm" in normalized_path or "causallm" in normalized_path:
        return {
            "architecture": "causal-lm",
            "family_id": "causal-lm",
            "source": "directory_name",
        }
    if "basic" in normalized_path:
        return {
            "architecture": "cross-encoder",
            "family_id": "basic",
            "source": "directory_name",
        }
    if "jina" in normalized_path:
        return {
            "architecture": "cross-encoder",
            "family_id": "jina-v3",
            "source": "directory_name",
        }
    return {
        "architecture": "cross-encoder",
        "family_id": "jina-v3",
        "source": "default",
    }


def _rerank_architecture_for_family(family_id: str) -> str:
    return "causal-lm" if family_id == "causal-lm" else "cross-encoder"


def _default_rerank_scoring_mode(family_id: str) -> str:
    return {
        "basic": "set-overlap",
        "causal-lm": "yes-no-logits",
        "jina-v3": "order-aware-overlap",
    }.get(family_id, "order-aware-overlap")


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
        model_path = environment.get("MELIX_DEV_EMBED_MODEL_PATH", "models/melix-dev-embed")
        detected = _infer_embedding_identity(model_path)
        configured_family_id = _normalized(environment.get("MELIX_DEV_EMBED_FAMILY_ID"))
        configured_backend_id = _normalized(environment.get("MELIX_DEV_EMBED_BACKEND_ID"))

        if configured_family_id:
            family_id = configured_family_id
            backend_id = configured_backend_id or _embedding_backend_for_family(family_id)
        else:
            backend_id = configured_backend_id or detected["backend_id"]
            family_id = _default_embedding_family_for_backend(backend_id, detected["family_id"])

        architecture = _embedding_architecture_for_family(family_id)
        default_pooling_mode = _default_embedding_pooling_mode(family_id)
        pooling_mode = environment.get(
            "MELIX_DEV_EMBED_POOLING_MODE",
            default_pooling_mode,
        ).strip() or default_pooling_mode
        normalization = environment.get("MELIX_DEV_EMBED_NORMALIZATION", "l2").strip() or "l2"
        default_dimensions = _default_embedding_dimensions(family_id)
        dimensions = environment.get("MELIX_DEV_EMBED_DIMENSIONS", default_dimensions).strip() or default_dimensions
        identity_override = (
            family_id != detected["family_id"] or architecture != detected["architecture"]
        )
        return common_pb2.ModelSpec(
            model_id="melix-dev-embed",
            model_path=model_path,
            model_kind="embedding",
            revision="dev",
            tokenizer_hash="tok-embed-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
            ext={
                "embedding_backend_id": backend_id,
                "embedding_family_id": family_id,
                "embedding_pooling_mode": pooling_mode,
                "embedding_normalization": normalization,
                "embedding_dimensions": dimensions,
                "model_architecture": architecture,
                "detected_architecture": detected["architecture"],
                "detected_family_id": detected["family_id"],
                "detected_identity_source": detected["source"],
                "identity_override": "true" if identity_override else "false",
            },
        )

    @staticmethod
    def dev_rerank_model(environment: dict[str, str] | None = None) -> common_pb2.ModelSpec:
        environment = dict(environment or os.environ)
        model_path = environment.get("MELIX_DEV_RERANK_MODEL_PATH", "models/melix-dev-rerank")
        detected = _infer_rerank_identity(model_path)
        backend_id = environment.get("MELIX_DEV_RERANK_BACKEND_ID", "token-overlap-v1").strip() or "token-overlap-v1"
        family_id = environment.get("MELIX_DEV_RERANK_FAMILY_ID", detected["family_id"]).strip() or detected["family_id"]
        architecture = _rerank_architecture_for_family(family_id)
        default_scoring_mode = _default_rerank_scoring_mode(family_id)
        scoring_mode = environment.get("MELIX_DEV_RERANK_SCORING_MODE", default_scoring_mode).strip() or default_scoring_mode
        identity_override = (
            family_id != detected["family_id"] or architecture != detected["architecture"]
        )
        ext = {
            "rerank_backend_id": backend_id,
            "rerank_family_id": family_id,
            "rerank_scoring_mode": scoring_mode,
            "model_architecture": architecture,
            "detected_architecture": detected["architecture"],
            "detected_family_id": detected["family_id"],
            "detected_identity_source": detected["source"],
            "identity_override": "true" if identity_override else "false",
        }
        if family_id == "causal-lm":
            yes_no_labels = environment.get("MELIX_DEV_RERANK_YES_NO_LABELS", "yes,no").strip() or "yes,no"
            ext["rerank_yes_no_labels"] = yes_no_labels
        return common_pb2.ModelSpec(
            model_id="melix-dev-rerank",
            model_path=model_path,
            model_kind="rerank",
            revision="dev",
            tokenizer_hash="tok-rerank-dev",
            quant_profile_id="q8",
            parser_mode="text",
            reasoning_mode="off",
            max_context=8192,
            ext=ext,
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
            ext={
                "ocr_prompt_profile_id": "ocr-default-v1",
                "ocr_prompt_template": "OCR instruction: {prompt}",
                "ocr_auto_prompt": "Extract the text from the image exactly as written.",
                "ocr_stop_sequences": "<ocr:end>",
                "ocr_sampling_profile_id": "ocr-deterministic",
                "ocr_default_temperature": "0.0",
                "ocr_default_top_p": "1.0",
                "ocr_default_max_tokens": "256",
            },
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
            ext={
                "vision_family_id": "llava-v1",
                "vision_prompt_profile_id": "llava-chatml-v1",
                "vision_tokenization_mode": "interleaved",
                "vision_max_images_per_prompt": "8",
                "vision_supports_tool_calls": "true",
                "melix.multimodal_adapter_hash": "vision-family-llava-v1",
            },
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
