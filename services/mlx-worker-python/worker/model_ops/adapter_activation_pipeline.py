from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.mlx_lm_runner import ActivationRequest, MLXLMRunner


@dataclass(frozen=True)
class AdapterActivationPipelineResult:
    manifest: dict[str, Any]
    manifest_path: Path


class AdapterActivationPipeline:
    def __init__(self, runner: MLXLMRunner | None = None) -> None:
        self._runner = runner or MLXLMRunner()

    def run(
        self,
        *,
        job_id: str,
        request_ext: dict[str, str],
        source_model: common_pb2.ModelSpec,
        output_dir: Path,
        progress: Callable[[str, float], None] | None = None,
    ) -> AdapterActivationPipelineResult:
        emit = progress or (lambda stage, pct: None)
        adapter_manifest_path = Path(request_ext.get("artifact_path", "")).expanduser().resolve()
        if not adapter_manifest_path.is_file():
            raise ModelOperationError(
                code="invalid_artifact",
                message="activate_adapter requires a valid adapter manifest artifact_path.",
            )

        try:
            adapter_manifest = json.loads(adapter_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ModelOperationError(
                code="invalid_artifact",
                message="Adapter package manifest is not valid JSON.",
            ) from exc

        if adapter_manifest.get("schema_version") != "melix.lora_adapter_package.v1":
            raise ModelOperationError(
                code="invalid_artifact",
                message="Artifact is not a Melix LoRA adapter package.",
            )

        if adapter_manifest.get("source_model") != source_model.model_id:
            raise ModelOperationError(
                code="activation_failure",
                message="Adapter package source model does not match the requested activation model.",
            )

        activation_mode = request_ext.get("activation_mode", "fused_derived_model").strip() or "fused_derived_model"
        if activation_mode not in {"fused_derived_model", "adapter_backed_runtime"}:
            raise ModelOperationError(
                code="activation_failure",
                message=f"Unsupported activation mode: {activation_mode}",
            )

        emit("read_adapter", 0.2)
        emit("validate_base", 0.4)

        adapter_set_hash = str(adapter_manifest.get("adapter_set_hash", "")).strip()
        if not adapter_set_hash:
            raise ModelOperationError(
                code="activation_failure",
                message="Adapter package is missing adapter_set_hash.",
            )

        derived_model_id = f"{source_model.model_id}-lora-{adapter_set_hash[:8]}"
        derived_model_dir = output_dir / derived_model_id

        emit("activate", 0.75)
        if activation_mode == "fused_derived_model":
            activation_result = self._runner.activate(
                ActivationRequest(
                    job_id=job_id,
                    base_model_id=source_model.model_id,
                    model_path=Path(source_model.model_path).expanduser(),
                    adapter_dir=Path(adapter_manifest["weights_path"]).expanduser().resolve().parent,
                    adapter_manifest_path=adapter_manifest_path,
                    derived_model_dir=derived_model_dir,
                    activation_mode=activation_mode,
                )
            )
            manifest_path = activation_result.manifest_path
            activation_duration_ms = activation_result.metrics.job_duration_ms
            execution_backend = activation_result.execution_backend
        else:
            derived_model_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = derived_model_dir / "manifest.json"
            activation_duration_ms = 0.0
            execution_backend = "internal"

        emit("write_manifest", 0.95)
        derived_model_alias = request_ext.get("derived_model_alias", "").strip() or str(
            adapter_manifest.get("desired_derived_model_alias", "")
        ).strip()
        derived_model_path = (
            source_model.model_path
            if activation_mode == "adapter_backed_runtime"
            else str(derived_model_dir)
        )
        manifest = {
            "schema_version": "melix.derived_text_model.v1",
            "job_id": job_id,
            "operation": "activate_adapter",
            "activation_mode": activation_mode,
            "activation_backend": execution_backend,
            "source_model": source_model.model_id,
            "source_model_revision": source_model.revision,
            "source_model_path": source_model.model_path,
            "base_model_repo_id": source_model.model_id,
            "adapter_manifest_path": str(adapter_manifest_path),
            "adapter_weights_path": str(adapter_manifest.get("weights_path", "")),
            "adapter_name": adapter_manifest.get("adapter_name", ""),
            "adapter_set_hash": adapter_set_hash,
            "source_adapter_job_id": str(adapter_manifest.get("job_id", "")),
            "derived_model_id": derived_model_id,
            "derived_model_path": derived_model_path,
            "activation_duration_ms": activation_duration_ms,
            "remove_supported": True,
            "melix.derived_from_adapter": True,
        }
        if derived_model_alias:
            manifest["derived_model_alias"] = derived_model_alias
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return AdapterActivationPipelineResult(manifest=manifest, manifest_path=manifest_path)
