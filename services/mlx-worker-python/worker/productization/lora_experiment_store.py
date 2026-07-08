from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from worker.productization.lora_adapter_provenance import (
    default_adapter_provenance_manifest_path,
)


_RUN_SCHEMA_VERSION = "melix.lora_experiment_run.v1"
_INDEX_SCHEMA_VERSION = "melix.lora_experiment_index.v1"
_LORA_CANARY_RECEIPT_KEYS = (
    "source_eos_token",
    "saved_eos_token",
    "tokenizer_config_path",
    "base_config_present",
    "processor_resume_mode",
    "aux_modules_restored",
    "merge_export_canary_result",
    "callback_api_drift_result",
    "completion_loss",
    "round_trip_passed",
    "grad_norm",
)
_CHECKPOINT_SELECTION_RECEIPT_KEYS = (
    "checkpoint_step",
    "checkpoint_sort_key",
    "selected_checkpoint_path",
    "selected_checkpoint_loss_source",
)


def _iter_lora_run_dirs(train_root: Path) -> tuple[Path, ...]:
    try:
        with os.scandir(train_root) as entries:
            run_dir_names = []
            append_run_dir_name = run_dir_names.append
            run_dir_prefix = "model-ops-"
            for entry in entries:
                entry_name = entry.name
                if not entry_name.startswith(run_dir_prefix):
                    continue
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                append_run_dir_name(entry_name)
    except OSError:
        return ()

    run_dir_names.sort()
    root_join = train_root.__truediv__
    return tuple(map(root_join, run_dir_names))


class LoraExperimentStore:
    run_record_name = "lora-experiment-run.json"
    index_record_name = "lora-experiments.index.json"

    def __init__(self) -> None:
        self._cached_index_path: Path | None = None
        self._cached_index_signature: tuple[int, int] | None = None
        self._cached_index_payload: dict[str, Any] | None = None
        self._cached_payloads: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}

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
        self._cache_payload(path=run_path, payload=run_payload)
        index_path = self._index_path(jobs_root)
        self.rebuild_index(jobs_root)
        return {"run": run_path, "index": index_path}

    def load_index(self, jobs_root: Path) -> dict[str, Any]:
        index_path = self._index_path(jobs_root)
        if self._cached_index_path == index_path:
            signature = self._path_signature(index_path)
            if signature is not None and signature == self._cached_index_signature and self._cached_index_payload is not None:
                return self._cached_index_payload
        payload = self._load_payload(index_path)
        if payload:
            self._cache_index(index_path=index_path, payload=payload)
            return payload
        return self.rebuild_index(jobs_root)

    def rebuild_index(self, jobs_root: Path) -> dict[str, Any]:
        train_root = jobs_root / "train_lora"
        runs_by_id: dict[str, dict[str, Any]] = {}
        for run_dir in _iter_lora_run_dirs(train_root):
            run_path = run_dir / self.run_record_name
            payload = self._load_payload(run_path)
            run_id = str(payload.get("run_id", "")).strip()
            if run_id:
                runs_by_id[run_id] = payload
                continue

            manifest_path = run_dir / "train_lora.adapter.json"
            payload = self._load_payload(manifest_path)
            if payload == {}:
                continue
            run_id = str(payload.get("job_id", "")).strip() or manifest_path.parent.name
            if run_id in runs_by_id:
                continue
            if str(payload.get("operation", "train_lora")).strip() != "train_lora":
                continue
            runs_by_id[run_id] = self._build_run_payload(manifest=payload, manifest_path=manifest_path)

        runs = sorted(
            runs_by_id.values(),
            key=lambda item: (_int_value(item.get("updated_at_unix_ms")), str(item.get("run_id", ""))),
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
        self._cache_index(index_path=index_path, payload=payload)
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
            latest_run = group_runs[0]
            latest_key = (
                _int_value(latest_run.get("updated_at_unix_ms")),
                str(latest_run.get("run_id", "")),
            )
            best_run = latest_run
            best_loss = _best_loss_value(best_run)
            best_key = (
                best_loss if best_loss is not None else float("inf"),
                -latest_key[0],
            )
            for run in group_runs[1:]:
                run_updated_at = _int_value(run.get("updated_at_unix_ms"))
                run_key_latest = (run_updated_at, str(run.get("run_id", "")))
                if run_key_latest > latest_key:
                    latest_run = run
                    latest_key = run_key_latest
                run_loss = _best_loss_value(run)
                run_key = (
                    run_loss if run_loss is not None else float("inf"),
                    -run_updated_at,
                )
                if run_key < best_key:
                    best_run = run
                    best_loss = run_loss
                    best_key = run_key
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
                    "latest_heldout_test_loss": _optional_finite_float(
                        latest_run.get("heldout_test_loss")
                    ),
                    "latest_heldout_test_perplexity": _optional_finite_float(
                        latest_run.get("heldout_test_perplexity")
                    ),
                    "latest_heldout_test_sample_count": _int_value(
                        latest_run.get("heldout_test_sample_count")
                    ),
                    "latest_checkpoint_count": _int_value(latest_run.get("checkpoint_count")),
                    "latest_checkpoint_path": _str_value(latest_run.get("latest_checkpoint_path")),
                    "latest_checkpoint_step": _int_value(latest_run.get("checkpoint_step")),
                    "latest_checkpoint_sort_key": _str_value(
                        latest_run.get("checkpoint_sort_key")
                    ),
                    "latest_selected_checkpoint_path": _str_value(
                        latest_run.get("selected_checkpoint_path")
                    ),
                    "latest_selected_checkpoint_loss_source": _str_value(
                        latest_run.get("selected_checkpoint_loss_source")
                    ),
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
                    "recommended_provenance_manifest_path": str(
                        best_run.get("adapter_provenance_manifest_path", "")
                    ),
                    "latest_provenance_manifest_path": str(
                        latest_run.get("adapter_provenance_manifest_path", "")
                    ),
                    "latest_export_eligible": bool(latest_run.get("export_eligible", False)),
                    "best_export_eligible": bool(best_run.get("export_eligible", False)),
                    "latest_loss_series_row_count": _int_value(latest_run.get("loss_series_row_count")),
                    "latest_operator_note_count": _int_value(latest_run.get("operator_note_count")),
                    "best_known_adapter": {
                        "run_id": str(best_run.get("run_id", "")),
                        "manifest_path": str(best_run.get("manifest_path", "")),
                        "provenance_manifest_path": str(
                            best_run.get("adapter_provenance_manifest_path", "")
                        ),
                        "adapter_name": str(best_run.get("adapter_name", "")),
                        "checkpoint_count": _int_value(best_run.get("checkpoint_count")),
                        "latest_checkpoint_path": _str_value(
                            best_run.get("latest_checkpoint_path")
                        ),
                        "checkpoint_step": _int_value(best_run.get("checkpoint_step")),
                        "checkpoint_sort_key": _str_value(best_run.get("checkpoint_sort_key")),
                        "selected_checkpoint_path": _str_value(
                            best_run.get("selected_checkpoint_path")
                        ),
                        "selected_checkpoint_loss_source": _str_value(
                            best_run.get("selected_checkpoint_loss_source")
                        ),
                        "resume_ready": bool(best_run.get("resume_ready", False)),
                        "loss_best": best_loss if best_loss is not None else 0.0,
                        "heldout_test_loss": _optional_finite_float(
                            best_run.get("heldout_test_loss")
                        ),
                        "heldout_test_perplexity": _optional_finite_float(
                            best_run.get("heldout_test_perplexity")
                        ),
                        "heldout_test_sample_count": _int_value(
                            best_run.get("heldout_test_sample_count")
                        ),
                        "export_eligible": bool(best_run.get("export_eligible", False)),
                    },
                    "updated_at_unix_ms": _int_value(latest_run.get("updated_at_unix_ms")),
                }
            )

        groups.sort(
            key=lambda item: (_int_value(item.get("updated_at_unix_ms")), str(item.get("group_id", ""))),
            reverse=True,
        )
        return groups

    def _build_run_payload(self, *, manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
        provenance = self._load_adapter_provenance(
            manifest=manifest,
            manifest_path=manifest_path,
        )
        adapter = _dict_value(provenance.get("adapter"))
        base_model = _dict_value(provenance.get("base_model"))
        dataset = _dict_value(provenance.get("dataset"))
        hyperparameters = _dict_value(provenance.get("hyperparameters"))
        training = _dict_value(provenance.get("training"))
        final_metrics = _dict_value(provenance.get("final_metrics"))
        operator_notes = _dict_value(provenance.get("operator_notes"))
        export_eligibility = _dict_value(provenance.get("export_eligibility"))

        manifest_job_id = (
            str(adapter.get("job_id", "")).strip()
            or str(manifest.get("job_id", "")).strip()
            or manifest_path.parent.name
        )
        adapter_name = (
            str(adapter.get("adapter_name", "")).strip()
            or str(manifest.get("adapter_name", "")).strip()
            or "melix-adapter"
        )
        source_model = (
            str(base_model.get("model_id", "")).strip()
            or str(manifest.get("source_model", "")).strip()
        )
        group_id = (
            str(adapter.get("experiment_group_id", "")).strip()
            or str(manifest.get("experiment_group_id", "")).strip()
            or f"{source_model}:{adapter_name}"
        )
        if "created_at_unix_ms" in manifest:
            created_at_unix_ms = _int_value(manifest.get("created_at_unix_ms"))
        else:
            created_at_unix_ms = int(manifest_path.stat().st_mtime * 1000)
        updated_at_unix_ms = _int_value(manifest.get("updated_at_unix_ms"), default=created_at_unix_ms)
        payload = {
            "schema_version": _RUN_SCHEMA_VERSION,
            "run_id": manifest_job_id,
            "group_id": group_id,
            "group_title": str(
                adapter.get("experiment_group_title")
                or manifest.get(
                    "experiment_group_title",
                    group_id
                    if str(adapter.get("experiment_group_id") or manifest.get("experiment_group_id", "")).strip()
                    else adapter_name,
                )
            ),
            "adapter_name": adapter_name,
            "source_model": source_model,
            "dataset_uri": str(dataset.get("uri") or manifest.get("dataset_uri", "")),
            "dataset_version": str(dataset.get("version") or manifest.get("dataset_version", "")),
            "train_sample_count": _int_value(
                dataset.get("train_sample_count"),
                manifest.get("trainer_dataset_sample_count"),
            ),
            "validation_sample_count": _int_value(
                dataset.get(
                    "validation_sample_count",
                    manifest.get("trainer_dataset_validation_sample_count", manifest.get("validation_sample_count", 0)),
                ),
            ),
            "heldout_test_sample_count": _int_value(
                final_metrics.get("heldout_test_sample_count"),
                dataset.get("test_sample_count"),
                manifest.get("heldout_test_sample_count"),
                manifest.get("trainer_dataset_test_sample_count"),
            ),
            "preset_id": str(hyperparameters.get("preset_id") or manifest.get("preset_id", "")),
            "preset_title": str(hyperparameters.get("preset_title") or manifest.get("preset_title", "")),
            "training_mode": str(hyperparameters.get("training_mode") or manifest.get("training_mode", "")),
            "training_backend": str(training.get("backend") or manifest.get("training_backend", "")),
            "status": str(training.get("status") or manifest.get("status", "completed")),
            "checkpoint_count": _int_value(
                _first_present_value(
                    adapter,
                    manifest,
                    "checkpoint_count",
                    "experiment.checkpoint_count",
                    default=0,
                )
            ),
            "latest_checkpoint_path": _str_value(
                _first_present_value(
                    adapter,
                    manifest,
                    "latest_checkpoint_path",
                    "experiment.latest_checkpoint_path",
                )
            ),
            "checkpoint_step": _int_value(
                _first_present_value(
                    adapter,
                    manifest,
                    "checkpoint_step",
                    "experiment.checkpoint_step",
                    default=0,
                )
            ),
            "checkpoint_sort_key": _str_value(
                _first_present_value(
                    adapter,
                    manifest,
                    "checkpoint_sort_key",
                    "experiment.checkpoint_sort_key",
                )
            ),
            "selected_checkpoint_path": _str_value(
                _first_present_value(
                    adapter,
                    manifest,
                    "selected_checkpoint_path",
                    "experiment.selected_checkpoint_path",
                )
            ),
            "selected_checkpoint_loss_source": _str_value(
                _first_present_value(
                    adapter,
                    manifest,
                    "selected_checkpoint_loss_source",
                    "experiment.selected_checkpoint_loss_source",
                )
            ),
            "resume_source_path": str(
                adapter.get(
                    "resume_source_path",
                    manifest.get("resume_source_path", manifest.get("experiment.resume_source_path", "")),
                )
            ),
            "resume_source_job_id": str(adapter.get("resume_source_job_id") or manifest.get("resume_source_job_id", "")),
            "resume_source_manifest_path": str(
                adapter.get("resume_source_manifest_path") or manifest.get("resume_source_manifest_path", "")
            ),
            "resume_ready": bool(adapter.get("resume_ready", manifest.get("resume_ready", manifest.get("experiment.resume_ready", False)))),
            "tokens_per_second": _optional_finite_float(
                training.get(
                    "tokens_per_second",
                    manifest.get("tokens_per_second", manifest.get("training.tokens_per_second", 0.0)),
                )
            )
            or 0.0,
            "peak_memory_gb": _optional_finite_float(
                training.get(
                    "peak_memory_gb",
                    manifest.get("peak_memory_gb", manifest.get("training.peak_memory_gb", 0.0)),
                )
            )
            or 0.0,
            "loss_final": _optional_finite_float(
                final_metrics.get("loss_final"),
                _manifest_optional_float(manifest, "loss_final", "training.loss_final"),
            ),
            "loss_best": _optional_finite_float(
                final_metrics.get("loss_best"),
                _manifest_optional_float(manifest, "loss_best", "training.loss_best"),
            ),
            "validation_loss_best": _optional_finite_float(final_metrics.get("validation_loss_best")),
            "heldout_test_loss": _optional_finite_float(
                final_metrics.get("heldout_test_loss"),
                _manifest_optional_float(manifest, "heldout_test_loss"),
            ),
            "heldout_test_perplexity": _optional_finite_float(
                final_metrics.get("heldout_test_perplexity"),
                _manifest_optional_float(manifest, "heldout_test_perplexity"),
            ),
            "heldout_baseline_loss": _optional_finite_float(
                _manifest_optional_float(manifest, "heldout_baseline_loss")
            ),
            "heldout_loss_delta": _optional_finite_float(
                _manifest_optional_float(manifest, "heldout_loss_delta")
            ),
            "loss_series_row_count": _int_value(training.get("loss_series_row_count")),
            "loss_series": _list_value(training.get("loss_series")),
            "base_model": base_model,
            "dataset_provenance": dataset,
            "hyperparameters": hyperparameters,
            "export_eligibility": export_eligibility,
            "export_eligible": bool(export_eligibility.get("eligible", False)),
            "export_blocking_reasons": _list_value(export_eligibility.get("blocking_reasons")),
            "adapter_provenance_manifest_path": str(
                provenance.get("adapter_provenance_manifest_path")
                or manifest.get("adapter_provenance_manifest_path", "")
                or (default_adapter_provenance_manifest_path(manifest_path) if provenance else "")
            ),
            "adapter_operator_notes_path": str(
                operator_notes.get("path")
                or manifest.get("adapter_operator_notes_path", "")
            ),
            "operator_note_count": _int_value(
                operator_notes.get("note_count"),
                manifest.get("adapter_operator_note_count"),
            ),
            "manifest_path": str(manifest_path),
            "output_dir": str(manifest_path.parent),
            "created_at_unix_ms": created_at_unix_ms,
            "updated_at_unix_ms": updated_at_unix_ms,
        }
        for key in _LORA_CANARY_RECEIPT_KEYS:
            if key in manifest:
                payload[key] = manifest[key]
        if manifest.get("checkpoint_step") not in (None, ""):
            payload["checkpoint_step"] = _int_value(manifest.get("checkpoint_step"))
        for key in _CHECKPOINT_SELECTION_RECEIPT_KEYS[1:]:
            if manifest.get(key) not in (None, ""):
                payload[key] = _str_value(manifest.get(key))
        return payload

    def _load_adapter_provenance(
        self,
        *,
        manifest: dict[str, Any],
        manifest_path: Path,
    ) -> dict[str, Any]:
        provenance_path = str(manifest.get("adapter_provenance_manifest_path", "")).strip()
        candidate_path = Path(provenance_path) if provenance_path else default_adapter_provenance_manifest_path(manifest_path)
        payload = self._load_payload(candidate_path)
        if payload.get("schema_version") != "melix.lora_adapter_provenance.v1":
            return {}
        payload["adapter_provenance_manifest_path"] = str(candidate_path)
        return payload

    @staticmethod
    def _checkpoint_lineage_entry(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": str(run.get("run_id", "")),
            "checkpoint_count": _int_value(run.get("checkpoint_count")),
            "latest_checkpoint_path": _str_value(run.get("latest_checkpoint_path")),
            "checkpoint_step": _int_value(run.get("checkpoint_step")),
            "checkpoint_sort_key": _str_value(run.get("checkpoint_sort_key")),
            "selected_checkpoint_path": _str_value(run.get("selected_checkpoint_path")),
            "selected_checkpoint_loss_source": _str_value(
                run.get("selected_checkpoint_loss_source")
            ),
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

    def _load_payload(self, path: Path) -> dict[str, Any]:
        signature = self._path_signature(path)
        if signature is None:
            self._cached_payloads.pop(path, None)
            return {}

        cached_payload = self._cached_payloads.get(path)
        if cached_payload is not None:
            cached_signature, payload = cached_payload
            if cached_signature == signature:
                return payload

        payload = self._read_payload(path)
        self._cached_payloads[path] = (signature, payload)
        return payload

    def _index_path(self, jobs_root: Path) -> Path:
        return jobs_root / "train_lora" / self.index_record_name

    @staticmethod
    def _path_signature(path: Path) -> tuple[int, int] | None:
        try:
            stat_result = path.stat()
        except OSError:
            return None
        return (stat_result.st_mtime_ns, stat_result.st_size)

    def _cache_index(self, *, index_path: Path, payload: dict[str, Any]) -> None:
        self._cached_index_path = index_path
        self._cached_index_signature = self._path_signature(index_path)
        self._cached_index_payload = payload

    def _cache_payload(self, *, path: Path, payload: dict[str, Any]) -> None:
        signature = self._path_signature(path)
        if signature is None:
            self._cached_payloads.pop(path, None)
            return
        self._cached_payloads[path] = (signature, payload)


def _int_value(*values: Any, default: int = 0) -> int:
    for candidate in values:
        if candidate is None or candidate == "":
            continue
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return default


def _str_value(raw_value: Any) -> str:
    return "" if raw_value is None else str(raw_value)


def _first_present_value(
    primary: dict[str, Any],
    fallback: dict[str, Any],
    *keys: str,
    default: Any = "",
) -> Any:
    if not keys:
        return default
    primary_value = primary.get(keys[0])
    if primary_value is not None and primary_value != "":
        return primary_value
    for key in keys:
        fallback_value = fallback.get(key)
        if fallback_value is not None and fallback_value != "":
            return fallback_value
    return default


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


def _optional_finite_float(*values: Any) -> float | None:
    for candidate in values:
        if candidate is None or candidate == "":
            continue
        try:
            parsed = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return None


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and math.isfinite(value) is False:
        return None
    return value
