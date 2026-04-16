from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


_RUN_SCHEMA_VERSION = "melix.lora_experiment_run.v1"
_INDEX_SCHEMA_VERSION = "melix.lora_experiment_index.v1"


class LoraExperimentStore:
    run_record_name = "lora-experiment-run.json"
    index_record_name = "lora-experiments.index.json"

    def persist_training_run(
        self,
        *,
        jobs_root: Path,
        manifest: dict[str, Any],
        manifest_path: Path,
    ) -> dict[str, Path]:
        run_payload = self._build_run_payload(manifest=manifest, manifest_path=manifest_path)
        run_path = manifest_path.parent / self.run_record_name
        run_path.write_text(json.dumps(_json_safe(run_payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        index_path = self._index_path(jobs_root)
        self.rebuild_index(jobs_root)
        return {"run": run_path, "index": index_path}

    def load_index(self, jobs_root: Path) -> dict[str, Any]:
        index_path = self._index_path(jobs_root)
        payload = self._read_payload(index_path)
        if payload:
            return payload
        return self.rebuild_index(jobs_root)

    def rebuild_index(self, jobs_root: Path) -> dict[str, Any]:
        train_root = jobs_root / "train_lora"
        runs_by_id: dict[str, dict[str, Any]] = {}
        if train_root.exists():
            for run_path in sorted(train_root.glob(f"model-ops-*/{self.run_record_name}")):
                payload = self._read_payload(run_path)
                run_id = str(payload.get("run_id", "")).strip()
                if run_id:
                    runs_by_id[run_id] = payload

            for manifest_path in sorted(train_root.glob("model-ops-*/train_lora.adapter.json")):
                payload = self._read_payload(manifest_path)
                run_id = str(payload.get("job_id", "")).strip() or manifest_path.parent.name
                if run_id in runs_by_id:
                    continue
                if str(payload.get("operation", "train_lora")).strip() != "train_lora":
                    continue
                runs_by_id[run_id] = self._build_run_payload(manifest=payload, manifest_path=manifest_path)

        runs = sorted(
            runs_by_id.values(),
            key=lambda item: (int(item.get("updated_at_unix_ms", 0)), str(item.get("run_id", ""))),
            reverse=True,
        )
        groups = self._build_group_payloads(runs)
        payload = {
            "schema_version": _INDEX_SCHEMA_VERSION,
            "groups": groups,
            "runs": runs,
        }
        index_path = self._index_path(jobs_root)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return payload

    def _build_group_payloads(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped_runs: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            group_id = str(run.get("group_id", "")).strip()
            if not group_id:
                continue
            grouped_runs.setdefault(group_id, []).append(run)

        groups: list[dict[str, Any]] = []
        for group_id, group_runs in grouped_runs.items():
            latest_run = max(
                group_runs,
                key=lambda item: (int(item.get("updated_at_unix_ms", 0)), str(item.get("run_id", ""))),
            )
            best_run = min(
                group_runs,
                key=lambda item: (
                    _best_loss_value(item) if _best_loss_value(item) is not None else float("inf"),
                    -int(item.get("updated_at_unix_ms", 0)),
                ),
            )
            best_loss = _best_loss_value(best_run)
            groups.append(
                {
                    "group_id": group_id,
                    "title": str(latest_run.get("group_title", group_id)),
                    "adapter_name": str(latest_run.get("adapter_name", "")),
                    "source_model": str(latest_run.get("source_model", "")),
                    "run_count": len(group_runs),
                    "latest_run_id": str(latest_run.get("run_id", "")),
                    "latest_status": str(latest_run.get("status", "")),
                    "latest_dataset_uri": str(latest_run.get("dataset_uri", "")),
                    "latest_preset_id": str(latest_run.get("preset_id", "")),
                    "latest_preset_title": str(latest_run.get("preset_title", "")),
                    "latest_tokens_per_second": _optional_finite_float(latest_run.get("tokens_per_second")) or 0.0,
                    "latest_peak_memory_gb": _optional_finite_float(latest_run.get("peak_memory_gb")) or 0.0,
                    "latest_checkpoint_count": int(latest_run.get("checkpoint_count", 0)),
                    "latest_checkpoint_path": str(latest_run.get("latest_checkpoint_path", "")),
                    "latest_resume_source_path": str(latest_run.get("resume_source_path", "")),
                    "latest_resume_ready": bool(latest_run.get("resume_ready", False)),
                    "resume_ready_run_ids": [
                        str(run.get("run_id", ""))
                        for run in group_runs
                        if bool(run.get("resume_ready", False)) and str(run.get("run_id", "")).strip()
                    ],
                    "checkpoint_lineage": [self._checkpoint_lineage_entry(run) for run in group_runs],
                    "best_run_id": str(best_run.get("run_id", "")),
                    "best_loss": best_loss if best_loss is not None else 0.0,
                    "recommended_manifest_path": str(best_run.get("manifest_path", "")),
                    "best_known_adapter": {
                        "run_id": str(best_run.get("run_id", "")),
                        "manifest_path": str(best_run.get("manifest_path", "")),
                        "adapter_name": str(best_run.get("adapter_name", "")),
                        "checkpoint_count": int(best_run.get("checkpoint_count", 0)),
                        "latest_checkpoint_path": str(best_run.get("latest_checkpoint_path", "")),
                        "resume_ready": bool(best_run.get("resume_ready", False)),
                        "loss_best": best_loss if best_loss is not None else 0.0,
                    },
                    "updated_at_unix_ms": int(latest_run.get("updated_at_unix_ms", 0)),
                }
            )

        groups.sort(
            key=lambda item: (int(item.get("updated_at_unix_ms", 0)), str(item.get("group_id", ""))),
            reverse=True,
        )
        return groups

    def _build_run_payload(self, *, manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
        manifest_job_id = str(manifest.get("job_id", "")).strip() or manifest_path.parent.name
        adapter_name = str(manifest.get("adapter_name", "")).strip() or "melix-adapter"
        source_model = str(manifest.get("source_model", "")).strip()
        group_id = str(manifest.get("experiment_group_id", "")).strip() or f"{source_model}:{adapter_name}"
        if "created_at_unix_ms" in manifest:
            created_at_unix_ms = int(manifest.get("created_at_unix_ms", 0))
        else:
            created_at_unix_ms = int(manifest_path.stat().st_mtime * 1000)
        updated_at_unix_ms = int(manifest.get("updated_at_unix_ms", created_at_unix_ms))
        return {
            "schema_version": _RUN_SCHEMA_VERSION,
            "run_id": manifest_job_id,
            "group_id": group_id,
            "group_title": str(
                manifest.get(
                    "experiment_group_title",
                    group_id if str(manifest.get("experiment_group_id", "")).strip() else adapter_name,
                )
            ),
            "adapter_name": adapter_name,
            "source_model": source_model,
            "dataset_uri": str(manifest.get("dataset_uri", "")),
            "preset_id": str(manifest.get("preset_id", "")),
            "preset_title": str(manifest.get("preset_title", "")),
            "training_mode": str(manifest.get("training_mode", "")),
            "training_backend": str(manifest.get("training_backend", "")),
            "status": str(manifest.get("status", "completed")),
            "checkpoint_count": int(manifest.get("checkpoint_count", manifest.get("experiment.checkpoint_count", 0))),
            "latest_checkpoint_path": str(
                manifest.get("latest_checkpoint_path", manifest.get("experiment.latest_checkpoint_path", ""))
            ),
            "resume_source_path": str(
                manifest.get("resume_source_path", manifest.get("experiment.resume_source_path", ""))
            ),
            "resume_source_job_id": str(manifest.get("resume_source_job_id", "")),
            "resume_source_manifest_path": str(manifest.get("resume_source_manifest_path", "")),
            "resume_ready": bool(manifest.get("resume_ready", manifest.get("experiment.resume_ready", False))),
            "tokens_per_second": float(
                manifest.get("tokens_per_second", manifest.get("training.tokens_per_second", 0.0))
            ),
            "peak_memory_gb": float(
                manifest.get("peak_memory_gb", manifest.get("training.peak_memory_gb", 0.0))
            ),
            "loss_final": _manifest_optional_float(manifest, "loss_final", "training.loss_final"),
            "loss_best": _manifest_optional_float(manifest, "loss_best", "training.loss_best"),
            "manifest_path": str(manifest_path),
            "output_dir": str(manifest_path.parent),
            "created_at_unix_ms": created_at_unix_ms,
            "updated_at_unix_ms": updated_at_unix_ms,
        }

    @staticmethod
    def _checkpoint_lineage_entry(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": str(run.get("run_id", "")),
            "checkpoint_count": int(run.get("checkpoint_count", 0)),
            "latest_checkpoint_path": str(run.get("latest_checkpoint_path", "")),
            "resume_source_path": str(run.get("resume_source_path", "")),
            "resume_source_job_id": str(run.get("resume_source_job_id", "")),
            "resume_source_manifest_path": str(run.get("resume_source_manifest_path", "")),
            "resume_ready": bool(run.get("resume_ready", False)),
        }

    @staticmethod
    def _read_payload(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _index_path(self, jobs_root: Path) -> Path:
        return jobs_root / "train_lora" / self.index_record_name


def _manifest_optional_float(manifest: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in manifest:
            return _optional_finite_float(manifest.get(key))
    return None


def _best_loss_value(item: dict[str, Any]) -> float | None:
    for key in ("loss_best", "loss_final"):
        value = _optional_finite_float(item.get(key))
        if value is not None:
            return value
    return None


def _optional_finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and math.isfinite(value) is False:
        return None
    return value
