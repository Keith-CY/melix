from __future__ import annotations

import json
import shutil
from pathlib import Path

from worker.model_ops.mlx_lm_runner import (
    ActivationMetrics,
    ActivationRequest,
    ActivationResult,
    MLXLMRunner,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)


class DeterministicLoRARunner(MLXLMRunner):
    def supports_alignment_training(self, config) -> bool:
        del config
        return True

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-deterministic-adapter")
        adapter_config_path.write_text(
            json.dumps(
                {
                    "fine_tune_type": "lora",
                    "num_layers": request.config.num_layers,
                    "tokenizer_config": self._source_tokenizer_config(request.model_path),
                    "round_trip_passed": True,
                    "callback_arity": 2,
                    "expected_callback_arity": 2,
                    "lora_parameters": {
                        "rank": request.config.rank,
                        "dropout": request.config.dropout,
                        "scale": request.config.alpha,
                        "keys": request.config.expanded_target_modules,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1234.0,
                tokens_seen=1024,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
                checkpoint_count=1,
                resume_ready=True,
                tokens_per_second=96.0,
                peak_memory_gb=2.5,
            ),
            execution_backend="native",
        )

    def _source_tokenizer_config(self, model_path: Path) -> dict[str, object]:
        try:
            payload = json.loads((model_path / "tokenizer_config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        request.derived_model_dir.mkdir(parents=True, exist_ok=True)
        self._copy_runtime_bundle(source_root=request.model_path, destination_root=request.derived_model_dir)
        manifest_path = request.derived_model_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps({"schema_version": "melix.derived_text_model.v1"}) + "\n",
            encoding="utf-8",
        )
        return ActivationResult(
            derived_model_dir=request.derived_model_dir,
            manifest_path=manifest_path,
            metrics=ActivationMetrics(job_duration_ms=321.0),
            execution_backend="native",
        )

    def _copy_runtime_bundle(self, *, source_root: Path, destination_root: Path) -> None:
        copied = False
        for relative_path in (
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "generation_config.json",
            "model.safetensors",
            "model.safetensors.index.json",
        ):
            source_path = source_root / relative_path
            if not source_path.is_file():
                continue
            target_path = destination_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            copied = True

        if copied:
            return

        (destination_root / "config.json").write_text('{"model_type":"melix-deterministic"}\n', encoding="utf-8")
        (destination_root / "tokenizer.json").write_text('{"version":"1.0"}\n', encoding="utf-8")
        (destination_root / "model.safetensors").write_bytes(b"melix-deterministic-model")
