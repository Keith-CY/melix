from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.mlx_lm_runner import MLXLMRunner, TrainingRequest
from worker.model_ops.training_config import normalize_training_config
from worker.model_ops.training_dataset import (
    HFDatasetFetcher,
    resolve_training_dataset_package,
    write_normalized_dataset_snapshot,
)


@dataclass(frozen=True)
class LoRATrainingPipelineResult:
    manifest: dict[str, Any]
    manifest_path: Path


class LoRATrainingPipeline:
    def __init__(
        self,
        runner: MLXLMRunner | None = None,
        hf_dataset_fetcher: HFDatasetFetcher | None = None,
    ) -> None:
        self._runner = runner or MLXLMRunner()
        self._hf_dataset_fetcher = hf_dataset_fetcher

    def run(
        self,
        *,
        job_id: str,
        request_ext: dict[str, str],
        source_model: common_pb2.ModelSpec,
        output_dir: Path,
        jobs_root: Path,
        progress: Callable[[str, float], None] | None = None,
    ) -> LoRATrainingPipelineResult:
        emit = progress or (lambda stage, pct: None)

        emit("resolve_source", 0.1)
        emit("validate_dataset", 0.2)
        dataset = resolve_training_dataset_package(
            request_ext,
            jobs_root=jobs_root,
            hf_dataset_fetcher=self._hf_dataset_fetcher,
            sample_limit=_int_ext(request_ext, "sample_limit"),
            max_characters_per_sample=_int_ext(request_ext, "max_characters_per_sample"),
        )

        emit("normalize_config", 0.35)
        config = normalize_training_config(
            source_model=source_model,
            ext=request_ext,
            dataset_format=dataset.package.format,
            response_only_supported=dataset.package.response_only_supported,
            sample_count=dataset.package.sample_count,
        )

        emit("prepare_training_data", 0.5)
        normalized_snapshot = write_normalized_dataset_snapshot(dataset.package, output_dir=output_dir)

        emit("apply_lora", 0.65)
        adapter_output_dir = output_dir / "adapter"

        emit("train", 0.8)
        training_result = self._runner.train(
            TrainingRequest(
                job_id=job_id,
                base_model_id=source_model.model_id,
                model_path=Path(source_model.model_path).expanduser(),
                model_revision=source_model.revision,
                adapter_output_dir=adapter_output_dir,
                normalized_dataset_dir=normalized_snapshot.dataset_dir,
                config=config,
                dataset_format=dataset.package.format,
            )
        )

        emit("write_adapter", 0.9)
        adapter_artifact_bytes = training_result.weights_path.stat().st_size
        adapter_set_hash = _content_hash(training_result.weights_path, training_result.adapter_config_path)

        emit("write_manifest", 0.97)
        manifest = {
            "schema_version": "melix.lora_adapter_package.v1",
            "job_id": job_id,
            "operation": "train_lora",
            "artifact_kind": "adapter",
            "adapter_name": config.adapter_name,
            "source_model": source_model.model_id,
            "source_model_revision": source_model.revision,
            "source_model_path": source_model.model_path,
            "dataset_uri": dataset.dataset_uri,
            "dataset_source_kind": dataset.source_kind,
            "dataset_id": dataset.package.dataset_id,
            "dataset_format": dataset.package.format,
            "dataset_version": dataset.package.version,
            "dataset_sample_count": dataset.package.sample_count,
            "dataset_source_manifest_path": str(dataset.package.manifest_path),
            "dataset_materialized_package_path": str(dataset.materialized_package_path),
            "dataset_cache_key": dataset.cache_key,
            "dataset_cache_hit": dataset.cache_hit,
            "training_mode": config.training_mode,
            "training_backend": training_result.execution_backend,
            "adapter_set_hash": adapter_set_hash,
            "weights_path": str(training_result.weights_path),
            "adapter_config_path": str(training_result.adapter_config_path),
            "normalized_dataset_manifest_path": str(normalized_snapshot.manifest_path),
            "target_modules": config.expanded_target_modules,
            "rank": config.rank,
            "alpha": config.alpha,
            "dropout": config.dropout,
            "response_only": config.response_only,
            "gradient_checkpointing": config.gradient_checkpointing,
            "mask_prompt": config.mask_prompt,
            "max_seq_length": config.max_seq_length,
            "training_duration_ms": training_result.metrics.job_duration_ms,
            "training.job_duration_ms": training_result.metrics.job_duration_ms,
            "training.tokens_seen": training_result.metrics.tokens_seen,
            "training.examples_seen": training_result.metrics.examples_seen,
            "training.loss_final": training_result.metrics.loss_final,
            "training.loss_best": training_result.metrics.loss_best,
            "training.learning_rate_final": training_result.metrics.learning_rate_final,
            "training.gradient_checkpointing_enabled": config.gradient_checkpointing,
            "training.response_only_enabled": config.response_only,
            "tokens_seen": training_result.metrics.tokens_seen,
            "examples_seen": training_result.metrics.examples_seen,
            "loss_final": training_result.metrics.loss_final,
            "loss_best": training_result.metrics.loss_best,
            "learning_rate_final": training_result.metrics.learning_rate_final,
            "adapter_artifact_bytes": adapter_artifact_bytes,
            "target_repo": config.target_repo,
        }
        if dataset.hf_reference is not None:
            manifest.update(
                {
                    "hf_dataset_path": dataset.hf_reference.dataset_path,
                    "hf_dataset_name": dataset.hf_reference.dataset_name,
                    "hf_dataset_revision": dataset.hf_reference.dataset_revision,
                    "hf_train_split": dataset.hf_reference.train_split,
                    "chat_feature": dataset.hf_reference.chat_feature,
                    "prompt_feature": dataset.hf_reference.prompt_feature,
                    "completion_feature": dataset.hf_reference.completion_feature,
                    "text_feature": dataset.hf_reference.text_feature,
                }
            )
        manifest_path = output_dir / "train_lora.adapter.json"
        manifest["artifact_path"] = str(manifest_path)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return LoRATrainingPipelineResult(manifest=manifest, manifest_path=manifest_path)


def _int_ext(ext: dict[str, str], key: str) -> int:
    raw_value = ext.get(key, "").strip()
    if not raw_value:
        return 0
    return int(raw_value)


def _content_hash(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
