#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

try:
    from scripts.real_model_support import (
        REAL_SMALL_TEXT_MODEL_ID,
        REAL_SMALL_TEXT_MODEL_PATH_ENV,
        build_runtime_model_preflight,
        resolve_real_small_text_model_source,
    )
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/...` execution fallback.
    from real_model_support import (  # type: ignore[no-redef]
        REAL_SMALL_TEXT_MODEL_ID,
        REAL_SMALL_TEXT_MODEL_PATH_ENV,
        build_runtime_model_preflight,
        resolve_real_small_text_model_source,
    )


_BASE_CHAT_PROMPT = "Reply with BASE_OK"
_DERIVED_CHAT_PROMPT = "Reply with DERIVED_OK"
_TRAINING_FIXTURE_DATASET_ID = "melix-dev-dataset.v1"
_ADAPTER_NAME = "phase8-acceptance"
_DERIVED_ALIAS = "phase8-acceptance-derived"
_BUNDLE_SCHEMA_VERSION = "melix.phase8.acceptance_bundle.v1"
_REAL_SMALL_MODEL_ID = REAL_SMALL_TEXT_MODEL_ID
_REAL_SMALL_MODEL_PATH_ENV = REAL_SMALL_TEXT_MODEL_PATH_ENV
_BENCH_CONTEXT_LENGTH = "1024"
_BENCH_GENERATION_LENGTH = "64"
_BENCH_BATCH_SIZE = "1"
_BENCH_SAMPLE_SIZE = "4"
_MATRIX_CACHE_PROFILE = "cold"
_MATRIX_REASONING_MODE = "disabled"
_MATRIX_STRUCTURED_OUTPUT_MODE = "plain_text"
_MATRIX_CONCURRENCY = "1"
_MATRIX_REQUESTS = "4"
_EVALUATION_SAMPLE_SIZE = "4"
_EXPERIMENT_INDEX_NAME = "lora-experiments.index.json"
_HF_TOKEN_KEYS = ("hf_token", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN")
_EVALUATION_SCORING_MODES = {
    "mmlu": "multiple_choice_accuracy",
    "arc_challenge": "multiple_choice_accuracy",
    "hellaswag": "multiple_choice_accuracy",
    "winogrande": "multiple_choice_accuracy",
    "truthfulqa_mc": "multiple_choice_accuracy",
    "gsm8k": "exact_match",
    "imagenette": "exact_match",
    "humaneval": "pass_at_1",
    "mbpp": "pass_at_1",
}

_PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "deterministic_import": {
        "acceptance_tier": "cli_regression",
        "runtime_backend_mode": "mixed_default",
        "activation_mode": "",
        "training_preset_id": "",
        "training_max_steps": 0,
        "experiment_group_id": "",
        "publish_mode": "disabled",
    },
    "live_hub": {
        "acceptance_tier": "cli_regression",
        "runtime_backend_mode": "mixed_default",
        "activation_mode": "",
        "training_preset_id": "",
        "training_max_steps": 0,
        "experiment_group_id": "",
        "publish_mode": "disabled",
    },
    "real_small_model": {
        "acceptance_tier": "cli_real_small_model",
        "runtime_backend_mode": "python_auto",
        "activation_mode": "adapter_backed_runtime",
        "training_preset_id": "debug_fast",
        "training_max_steps": 2,
        "experiment_group_id": "phase8-real-small-model",
        "publish_mode": "disabled",
    },
}


class AcceptanceBundleError(RuntimeError):
    pass


@dataclass(slots=True)
class CLICommandError(AcceptanceBundleError):
    command: list[str]
    returncode: int
    stderr: str
    stdout: str = ""

    def __str__(self) -> str:
        joined = " ".join(self.command)
        status = _return_code_description(self.returncode)
        details = self.stderr.strip() or self.stdout.strip() or "no stderr or stdout captured"
        return f"{joined} failed ({status}): {details}"


@dataclass(frozen=True, slots=True)
class AcceptanceBundleConfig:
    repo_root: Path
    melix_home: Path
    model_id: str
    training_fixture: str
    bench_suites: list[str]
    matrix_suites: list[str]
    evaluation_suites: list[str]
    evaluation_dataset: str
    provider_id: str
    local_model_path: str
    live: bool
    timestamp: str
    json_output: bool
    execution_profile: str = "deterministic_import"
    acceptance_tier: str = "cli_regression"
    runtime_backend_mode: str = "mixed_default"
    activation_mode: str = ""
    training_preset_id: str = ""
    training_max_steps: int = 0
    experiment_group_id: str = ""
    publish_mode: str = "disabled"
    publish_target_repo: str = ""
    source_resolution_mode: str = ""
    materialize_warnings: tuple[str, ...] = ()


class JSONCommandExecuting(Protocol):
    def run_json(self, args: list[str]) -> object:
        ...


class _TracingJSONExecutor:
    def __init__(self, *, executor: JSONCommandExecuting, event_log_path: Path) -> None:
        self._executor = executor
        self._event_log_path = event_log_path
        self._step_index = 0

    def run_json(self, args: list[str]) -> object:
        self._step_index += 1
        step_id = f"{self._step_index:02d}"
        step_label = _cli_step_label(args)
        started_at = time.perf_counter()
        _append_jsonl(
            self._event_log_path,
            {
                "event": "cli_step_started",
                "timestamp": _utc_event_timestamp(),
                "step_id": step_id,
                "step_label": step_label,
                "args": list(args),
            },
        )
        try:
            payload = self._executor.run_json(args)
        except CLICommandError as error:
            _append_jsonl(
                self._event_log_path,
                {
                    "event": "cli_step_failed",
                    "timestamp": _utc_event_timestamp(),
                    "step_id": step_id,
                    "step_label": step_label,
                    "args": list(args),
                    "command": list(error.command),
                    "returncode": error.returncode,
                    "returncode_description": _return_code_description(error.returncode),
                    "failure": str(error),
                    "stderr": _trim_diagnostic_text(error.stderr),
                    "stdout": _trim_diagnostic_text(error.stdout),
                    "duration_ms": _elapsed_ms(started_at),
                },
            )
            raise
        except Exception as error:
            _append_jsonl(
                self._event_log_path,
                {
                    "event": "cli_step_failed",
                    "timestamp": _utc_event_timestamp(),
                    "step_id": step_id,
                    "step_label": step_label,
                    "args": list(args),
                    "exception_type": type(error).__name__,
                    "failure": str(error),
                    "duration_ms": _elapsed_ms(started_at),
                },
            )
            raise

        _append_jsonl(
            self._event_log_path,
            {
                "event": "cli_step_completed",
                "timestamp": _utc_event_timestamp(),
                "step_id": step_id,
                "step_label": step_label,
                "args": list(args),
                "duration_ms": _elapsed_ms(started_at),
            },
        )
        return payload


class CLIJSONExecutor:
    def __init__(
        self,
        *,
        repo_root: Path,
        environment: dict[str, str],
        cli_binary: str | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.environment = dict(environment)
        self._cli_binary = cli_binary or self.environment.get("MELIX_CLI", "").strip()

    def run_json(self, args: list[str]) -> object:
        command = [self._resolved_cli_binary(), *args]
        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            env=self.environment,
            check=False,
        )
        if completed.returncode != 0:
            raise CLICommandError(
                command=command,
                returncode=completed.returncode,
                stderr=completed.stderr,
                stdout=completed.stdout,
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AcceptanceBundleError(
                f"{' '.join(command)} did not return valid JSON: {error.msg}"
            ) from error

    def _resolved_cli_binary(self) -> str:
        if self._cli_binary:
            return self._cli_binary
        built_binary = self.repo_root / ".build" / "arm64-apple-macosx" / "debug" / "melix"
        if built_binary.is_file():
            self._cli_binary = str(built_binary)
            return self._cli_binary
        discovered = shutil.which("melix")
        self._cli_binary = discovered or "melix"
        return self._cli_binary


def run_acceptance_bundle(
    config: AcceptanceBundleConfig,
    *,
    executor: JSONCommandExecuting,
) -> tuple[Path, dict[str, Any]]:
    bundle_root = config.melix_home / "acceptance" / "phase8" / "cli" / config.timestamp
    exports_root = bundle_root / "exports"
    cli_receipts_root = bundle_root / "cli"
    bundle_path = bundle_root / "bundle.json"
    bench_csv_path = exports_root / "bench.csv"
    matrix_summary_csv_path = exports_root / "bench-matrix-summary.csv"
    evaluation_summary_csv_path = exports_root / "evaluation-summary.csv"
    evaluation_samples_jsonl_path = exports_root / "evaluation-samples.jsonl"
    event_log_path = bundle_root / "events.jsonl"

    timings: dict[str, float] = {}
    bundle_root.mkdir(parents=True, exist_ok=True)
    exports_root.mkdir(parents=True, exist_ok=True)
    cli_receipts_root.mkdir(parents=True, exist_ok=True)
    if event_log_path.exists():
        event_log_path.unlink()
    executor = _TracingJSONExecutor(executor=executor, event_log_path=event_log_path)

    materialize_started_at = time.perf_counter()
    if config.live:
        materialize_receipt = _expect_mapping(
            executor.run_json(
                [
                    "model",
                    "hub",
                    "download",
                    "--repo-id",
                    config.model_id,
                    "--json",
                ]
            ),
            context="melix model hub download",
        )
    else:
        if not config.local_model_path.strip():
            raise AcceptanceBundleError("--local-model-path is required when --live is not set.")
        materialize_receipt = _expect_mapping(
            executor.run_json(
                [
                    "model",
                    "import",
                    "--path",
                    config.local_model_path,
                    "--model-id",
                    config.model_id,
                    "--model-kind",
                    "text",
                    "--revision",
                    "main",
                    "--json",
                ]
            ),
            context="melix model import",
        )
    if config.materialize_warnings:
        materialize_receipt = dict(materialize_receipt)
        existing_warnings = materialize_receipt.get("warnings", [])
        warnings: list[str] = []
        if isinstance(existing_warnings, list):
            warnings.extend(str(item) for item in existing_warnings if str(item).strip())
        warnings.extend(config.materialize_warnings)
        materialize_receipt["warnings"] = warnings
    timings["phase8.cli.managed_materialize_ms"] = _elapsed_ms(materialize_started_at)

    model_id = _require_string(materialize_receipt, "model_id", context="managed model receipt")
    managed_model_path = _require_string(materialize_receipt, "managed_model_path", context="managed model receipt")
    source_kind = _require_string(materialize_receipt, "source_kind", context="managed model receipt")
    source_locator = _require_string(materialize_receipt, "source_locator", context="managed model receipt")
    source_resolution_mode = config.source_resolution_mode or _default_source_resolution_mode(config)
    model_preflight = build_runtime_model_preflight(
        model_id=model_id,
        live=config.live,
        local_model_path=config.local_model_path,
        source_resolution_mode=source_resolution_mode,
    ).to_dict()
    _write_json(cli_receipts_root / "01-materialize.json", materialize_receipt)

    rebind_started_at = time.perf_counter()
    registry_rescan_receipt = _expect_mapping(
        executor.run_json(["model", "roots", "rescan", "--json"]),
        context="melix model roots rescan",
    )
    _write_json(cli_receipts_root / "02-registry-rescan.json", registry_rescan_receipt)

    provider_update = _expect_mapping(
        executor.run_json(
            [
                "provider",
                "update",
                "--provider-id",
                config.provider_id,
                "--model",
                model_id,
                "--json",
            ]
        ),
        context="melix provider update",
    )
    _write_json(cli_receipts_root / "03-provider-update.json", provider_update)

    server_start = _expect_mapping(
        executor.run_json(
            [
                "server",
                "start",
                "--provider-id",
                config.provider_id,
                "--json",
            ]
        ),
        context="melix server start",
    )
    _write_json(cli_receipts_root / "04-server-start.json", server_start)
    timings["phase8.cli.provider_rebind_ms"] = _elapsed_ms(rebind_started_at)

    base_chat_started_at = time.perf_counter()
    base_chat_receipt = _expect_mapping(
        executor.run_json(
            [
                "chat",
                "run",
                "--model-id",
                model_id,
                "--message",
                _BASE_CHAT_PROMPT,
                "--json",
            ]
        ),
        context="melix chat run (base model)",
    )
    timings["phase8.cli.base_chat_roundtrip_ms"] = _elapsed_ms(base_chat_started_at)
    _write_json(cli_receipts_root / "05-base-chat.json", base_chat_receipt)

    lora_train_started_at = time.perf_counter()
    train_args = [
        "lora",
        "train",
        "--model-id",
        model_id,
        "--dataset-uri",
        config.training_fixture,
        "--adapter-name",
        _ADAPTER_NAME,
    ]
    if config.training_preset_id:
        train_args.extend(["--preset", config.training_preset_id])
    if config.experiment_group_id:
        train_args.extend(["--experiment-group", config.experiment_group_id])
    if config.training_max_steps > 0:
        train_args.extend(["--max-steps", str(config.training_max_steps)])
    train_args.append("--json")
    lora_train_receipt = _expect_mapping(
        executor.run_json(train_args),
        context="melix lora train",
    )
    timings["phase8.cli.lora_train_ms"] = _elapsed_ms(lora_train_started_at)
    _write_json(cli_receipts_root / "06-lora-train.json", lora_train_receipt)

    adapter_manifest_path = _adapter_manifest_path(lora_train_receipt)

    lora_activate_started_at = time.perf_counter()
    activate_args = [
        "lora",
        "activate",
        "--model-id",
        model_id,
        "--adapter-path",
        str(adapter_manifest_path),
        "--alias",
        _DERIVED_ALIAS,
    ]
    if config.activation_mode:
        activate_args.extend(["--activation-mode", config.activation_mode])
    activate_args.append("--json")
    lora_activate_receipt = _expect_mapping(
        executor.run_json(activate_args),
        context="melix lora activate",
    )
    timings["phase8.cli.lora_activate_ms"] = _elapsed_ms(lora_activate_started_at)
    _write_json(cli_receipts_root / "07-lora-activate.json", lora_activate_receipt)

    derived_model_id = _require_string(lora_activate_receipt, "derived_model_id", context="lora activation receipt")
    derived_model_alias = str(lora_activate_receipt.get("derived_model_alias", _DERIVED_ALIAS)).strip() or _DERIVED_ALIAS
    lora_registry_snapshot = {"adapters": [], "experiment_groups": []}
    if _should_capture_lora_registry(config):
        lora_registry_snapshot = _expect_mapping(
            executor.run_json(
                [
                    "lora",
                    "list",
                    "--model-id",
                    model_id,
                    "--json",
                ]
            ),
            context="melix lora list",
        )
        _write_json(cli_receipts_root / "08-lora-list.json", lora_registry_snapshot)

    derived_chat_started_at = time.perf_counter()
    derived_chat_receipt = _expect_mapping(
        executor.run_json(
            [
                "chat",
                "run",
                "--model-id",
                derived_model_id,
                "--message",
                _DERIVED_CHAT_PROMPT,
                "--json",
            ]
        ),
        context="melix chat run (derived model)",
    )
    timings["phase8.cli.derived_chat_roundtrip_ms"] = _elapsed_ms(derived_chat_started_at)
    timings["phase8.cli.chat_roundtrip_ms"] = round(
        timings["phase8.cli.base_chat_roundtrip_ms"] + timings["phase8.cli.derived_chat_roundtrip_ms"],
        2,
    )
    _write_json(cli_receipts_root / "09-derived-chat.json", derived_chat_receipt)

    bench_started_at = time.perf_counter()
    bench_run_receipt = _expect_mapping(
        executor.run_json(
            [
                "bench",
                "run",
                "--model-id",
                model_id,
                *_repeated_flag("--suite", config.bench_suites),
                "--context-length",
                _BENCH_CONTEXT_LENGTH,
                "--generation-length",
                _BENCH_GENERATION_LENGTH,
                "--batch-size",
                _BENCH_BATCH_SIZE,
                "--sample-size",
                _BENCH_SAMPLE_SIZE,
                "--json",
            ]
        ),
        context="melix bench run",
    )
    timings["phase8.cli.bench_run_ms"] = _elapsed_ms(bench_started_at)
    _write_json(cli_receipts_root / "10-bench-run.json", bench_run_receipt)
    bench_report_path = _require_string(bench_run_receipt, "report_path", context="bench run receipt")
    bench_job_id = _job_id_from_report_path(bench_report_path)

    matrix_started_at = time.perf_counter()
    matrix_run_receipt = _expect_mapping(
        executor.run_json(
            [
                "bench",
                "matrix",
                "run",
                "--model-id",
                model_id,
                *_repeated_flag("--suite", config.matrix_suites),
                "--context-length",
                _BENCH_CONTEXT_LENGTH,
                "--generation-length",
                _BENCH_GENERATION_LENGTH,
                "--batch-size",
                _BENCH_BATCH_SIZE,
                "--cache-profile",
                _MATRIX_CACHE_PROFILE,
                "--reasoning-mode",
                _MATRIX_REASONING_MODE,
                "--structured-output-mode",
                _MATRIX_STRUCTURED_OUTPUT_MODE,
                "--concurrency",
                _MATRIX_CONCURRENCY,
                "--requests",
                _MATRIX_REQUESTS,
                "--json",
            ]
        ),
        context="melix bench matrix run",
    )
    timings["phase8.cli.bench_matrix_run_ms"] = _elapsed_ms(matrix_started_at)
    _write_json(cli_receipts_root / "11-bench-matrix-run.json", matrix_run_receipt)
    matrix_job = _expect_mapping(matrix_run_receipt.get("job"), context="bench matrix job payload")
    bench_matrix_job_id = _require_string(matrix_job, "job_id", context="bench matrix job payload")

    evaluation_started_at = time.perf_counter()
    evaluation_scoring_mode = _evaluation_scoring_mode(config.evaluation_suites)
    evaluation_runs = _expect_list(
        executor.run_json(
            [
                "eval",
                "run",
                "--model-id",
                derived_model_id,
                *_repeated_flag("--suite", config.evaluation_suites),
                "--dataset-id",
                config.evaluation_dataset,
                "--sample-size",
                _EVALUATION_SAMPLE_SIZE,
                "--scoring-mode",
                evaluation_scoring_mode,
                "--json",
            ]
        ),
        context="melix eval run",
    )
    timings["phase8.cli.evaluation_run_ms"] = _elapsed_ms(evaluation_started_at)
    _write_json(cli_receipts_root / "12-eval-run.json", evaluation_runs)
    if not evaluation_runs:
        raise AcceptanceBundleError("melix eval run did not return any evaluation payloads.")
    evaluation_job = _expect_mapping(evaluation_runs[0].get("job"), context="evaluation job payload")
    evaluation_job_id = _require_string(evaluation_job, "job_id", context="evaluation job payload")

    bench_export_receipt = _expect_mapping(
        executor.run_json(
            [
                "bench",
                "export-csv",
                "--job-id",
                bench_job_id,
                "--output",
                str(bench_csv_path),
                "--json",
            ]
        ),
        context="melix bench export-csv",
    )
    _write_json(cli_receipts_root / "13-bench-export.json", bench_export_receipt)

    matrix_export_receipt = _expect_mapping(
        executor.run_json(
            [
                "bench",
                "matrix",
                "export-summary-csv",
                "--job-id",
                bench_matrix_job_id,
                "--output",
                str(matrix_summary_csv_path),
                "--json",
            ]
        ),
        context="melix bench matrix export-summary-csv",
    )
    _write_json(cli_receipts_root / "14-bench-matrix-export.json", matrix_export_receipt)

    evaluation_summary_export = _expect_mapping(
        executor.run_json(
            [
                "eval",
                "export-summary-csv",
                "--job-id",
                evaluation_job_id,
                "--output",
                str(evaluation_summary_csv_path),
                "--json",
            ]
        ),
        context="melix eval export-summary-csv",
    )
    _write_json(cli_receipts_root / "15-eval-summary-export.json", evaluation_summary_export)

    evaluation_samples_export = _expect_mapping(
        executor.run_json(
            [
                "eval",
                "export-samples-jsonl",
                "--job-id",
                evaluation_job_id,
                "--output",
                str(evaluation_samples_jsonl_path),
                "--json",
            ]
        ),
        context="melix eval export-samples-jsonl",
    )
    _write_json(cli_receipts_root / "16-eval-samples-export.json", evaluation_samples_export)

    bench_csv = _require_existing_export(bench_export_receipt, "output_path", context="bench export receipt")
    matrix_summary_csv = _require_existing_export(
        matrix_export_receipt,
        "output_path",
        context="bench matrix export receipt",
    )
    evaluation_summary_csv = _require_existing_export(
        evaluation_summary_export,
        "output_path",
        context="evaluation summary export receipt",
    )
    evaluation_samples_jsonl = _require_existing_export(
        evaluation_samples_export,
        "output_path",
        context="evaluation samples export receipt",
    )
    experiment_index_path = _experiment_index_path(config)
    experiment_index_payload = _read_json_mapping(experiment_index_path)
    publish_result = _maybe_publish_adapter(
        config=config,
        executor=executor,
        model_id=model_id,
        adapter_manifest_path=adapter_manifest_path,
        cli_receipts_root=cli_receipts_root,
    )

    bundle: dict[str, Any] = {
        "schema_version": _BUNDLE_SCHEMA_VERSION,
        "timestamp": config.timestamp,
        "bundle_root": str(bundle_root),
        "execution_profile": config.execution_profile,
        "acceptance_tier": config.acceptance_tier,
        "model": {
            "model_id": model_id,
            "managed_model_path": managed_model_path,
            "source_kind": source_kind,
            "source_locator": source_locator,
            "source_resolution_mode": source_resolution_mode,
            "warnings": materialize_receipt.get("warnings", []),
            "preflight": model_preflight,
        },
        "runtime": {
            "backend_mode": config.runtime_backend_mode,
            "activation_mode": config.activation_mode or "fused_derived_model",
        },
        "training": {
            "preset_id": config.training_preset_id,
            "max_steps": config.training_max_steps,
            "experiment_group_id": config.experiment_group_id,
        },
        "derived_model": {
            "model_id": derived_model_id,
            "alias": derived_model_alias,
            "manifest_path": str(lora_activate_receipt.get("manifest_path", "")),
        },
        "server": {
            "provider_id": config.provider_id,
            "update": provider_update,
            "start": server_start,
        },
        "datasets": {
            "training_fixture": _TRAINING_FIXTURE_DATASET_ID,
            "training_fixture_path": config.training_fixture,
            "evaluation_dataset": config.evaluation_dataset,
        },
        "suites": {
            "bench": list(config.bench_suites),
            "matrix": list(config.matrix_suites),
            "evaluation": list(config.evaluation_suites),
        },
        "jobs": {
            "lora_train_job_id": _require_string(lora_train_receipt, "job_id", context="lora train receipt"),
            "bench_job_id": bench_job_id,
            "bench_matrix_job_id": bench_matrix_job_id,
            "evaluation_job_id": evaluation_job_id,
        },
        "registry": lora_registry_snapshot,
        "experiment": {
            "index_path": str(experiment_index_path),
            "index_exists": experiment_index_path.is_file(),
            "index": experiment_index_payload,
        },
        "exports": {
            "bench_csv": str(bench_csv),
            "matrix_summary_csv": str(matrix_summary_csv),
            "evaluation_summary_csv": str(evaluation_summary_csv),
            "evaluation_samples_jsonl": str(evaluation_samples_jsonl),
        },
        "publish": publish_result,
        "lora_capability": {
            "adapter_artifact": {
                "job_id": _require_string(lora_train_receipt, "job_id", context="lora train receipt"),
                "weights_path": str(lora_train_receipt.get("weights_path", "")),
                "adapter_config_path": str(lora_train_receipt.get("adapter_config_path", "")),
            },
            "activation_artifact": {
                "derived_model_id": derived_model_id,
                "derived_model_alias": derived_model_alias,
                "manifest_path": str(lora_activate_receipt.get("manifest_path", "")),
            },
            "compare_artifact": {
                "evaluation_job_id": evaluation_job_id,
                "model_id": derived_model_id,
                "suites": list(config.evaluation_suites),
            },
            "publish_artifact": {
                "mode": publish_result.get("mode", "disabled"),
                "status": publish_result.get("status", "disabled"),
                "target_repo": publish_result.get("target_repo", ""),
            },
            "runtime_mode": config.activation_mode or "fused_derived_model",
        },
        "chats": {
            "base": base_chat_receipt,
            "derived": derived_chat_receipt,
        },
        "cli": {
            "materialize": materialize_receipt,
            "registry_rescan": registry_rescan_receipt,
            "lora_train": lora_train_receipt,
            "lora_activate": lora_activate_receipt,
            "lora_list": lora_registry_snapshot,
            "bench_run": bench_run_receipt,
            "bench_matrix_run": matrix_run_receipt,
            "evaluation_runs": evaluation_runs,
            "bench_export": bench_export_receipt,
            "bench_matrix_export": matrix_export_receipt,
            "evaluation_summary_export": evaluation_summary_export,
            "evaluation_samples_export": evaluation_samples_export,
            "publish": publish_result.get("receipt", {}),
        },
        "metrics": timings,
        "diagnostics": {
            "event_log_jsonl": str(event_log_path),
        },
    }

    bundle_write_started_at = time.perf_counter()
    # First write measures bundle persistence latency; the second write persists that metric.
    _write_json(bundle_path, bundle)
    timings["phase8.cli.acceptance_bundle_write_ms"] = _elapsed_ms(bundle_write_started_at)
    _write_json(bundle_path, bundle)
    return bundle_path, bundle


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 8 CLI acceptance bundle flow.")
    parser.add_argument("--repo-root", default="", help="Override the repository root path.")
    parser.add_argument("--melix-home", default="", help="Override MELIX_HOME for bundle output.")
    parser.add_argument("--model-id", default="", help="Managed or Hub model identifier to validate.")
    parser.add_argument(
        "--execution-profile",
        choices=sorted(_PROFILE_DEFAULTS.keys()),
        default="",
        help="Apply a named acceptance profile.",
    )
    parser.add_argument("--live", action="store_true", help="Use melix model hub download instead of local import.")
    parser.add_argument("--local-model-path", default="", help="Local model directory for deterministic acceptance runs.")
    parser.add_argument(
        "--training-fixture",
        required=True,
        help="Dataset fixture path or URI passed into melix lora train.",
    )
    parser.add_argument("--bench-suite", action="append", default=[], help="Benchmark suite to execute.")
    parser.add_argument("--matrix-suite", action="append", default=[], help="Benchmark matrix suite to execute.")
    parser.add_argument("--evaluation-suite", action="append", default=[], help="Evaluation suite to execute.")
    parser.add_argument("--evaluation-dataset", required=True, help="Evaluation dataset identifier.")
    parser.add_argument(
        "--provider-id",
        default="provider-1",
        help="Provider to rebind and start during acceptance.",
    )
    parser.add_argument("--activation-mode", default="", help="Override melix lora activate mode.")
    parser.add_argument("--training-preset", default="", help="Override melix lora train preset.")
    parser.add_argument("--max-steps", type=int, default=0, help="Clamp LoRA training iterations.")
    parser.add_argument("--experiment-group", default="", help="Override the training experiment group.")
    parser.add_argument(
        "--publish-mode",
        choices=["disabled", "auto", "required"],
        default="",
        help="Control adapter publish behavior for the acceptance run.",
    )
    parser.add_argument("--publish-target-repo", default="", help="Target repository for adapter publish.")
    parser.add_argument("--timestamp", default="", help="Fixed UTC timestamp label for reproducible evidence paths.")
    parser.add_argument("--json", action="store_true", help="Emit JSON with bundle metadata.")
    return parser


def parse_args(argv: list[str] | None = None) -> AcceptanceBundleConfig:
    args = build_argument_parser().parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else _default_repo_root()
    melix_home = (
        Path(args.melix_home).expanduser().resolve()
        if args.melix_home
        else Path(os.environ.get("MELIX_HOME", repo_root / ".melix")).expanduser().resolve()
    )
    if not args.bench_suite:
        raise AcceptanceBundleError("At least one --bench-suite is required.")
    if not args.matrix_suite:
        raise AcceptanceBundleError("At least one --matrix-suite is required.")
    if not args.evaluation_suite:
        raise AcceptanceBundleError("At least one --evaluation-suite is required.")
    timestamp = args.timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    execution_profile = args.execution_profile or ("live_hub" if args.live else "deterministic_import")
    profile = _PROFILE_DEFAULTS.get(execution_profile)
    if profile is None:
        raise AcceptanceBundleError(f"Unknown execution profile: {execution_profile}")
    model_id, live, local_model_path, source_resolution_mode, materialize_warnings = _resolve_model_source(
        execution_profile=execution_profile,
        model_id=str(args.model_id or "").strip(),
        local_model_path=str(args.local_model_path or "").strip(),
        live=bool(args.live),
    )
    return AcceptanceBundleConfig(
        repo_root=repo_root,
        melix_home=melix_home,
        model_id=model_id,
        training_fixture=args.training_fixture,
        bench_suites=list(args.bench_suite),
        matrix_suites=list(args.matrix_suite),
        evaluation_suites=list(args.evaluation_suite),
        evaluation_dataset=args.evaluation_dataset,
        provider_id=args.provider_id,
        local_model_path=local_model_path,
        live=live,
        timestamp=timestamp,
        json_output=bool(args.json),
        execution_profile=execution_profile,
        acceptance_tier=str(profile["acceptance_tier"]),
        runtime_backend_mode=str(profile["runtime_backend_mode"]),
        activation_mode=args.activation_mode or str(profile["activation_mode"]),
        training_preset_id=args.training_preset or str(profile["training_preset_id"]),
        training_max_steps=int(args.max_steps or int(profile["training_max_steps"])),
        experiment_group_id=args.experiment_group or str(profile["experiment_group_id"]),
        publish_mode=args.publish_mode or str(profile["publish_mode"]),
        publish_target_repo=args.publish_target_repo,
        source_resolution_mode=source_resolution_mode,
        materialize_warnings=materialize_warnings,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        executor = CLIJSONExecutor(
            repo_root=config.repo_root,
            environment=os.environ.copy(),
        )
        bundle_path, bundle = run_acceptance_bundle(config, executor=executor)
    except (AcceptanceBundleError, CLICommandError) as error:
        print(str(error), file=sys.stderr)
        return 1

    if config.json_output:
        print(
            json.dumps(
                {
                    "bundle_path": str(bundle_path),
                    "bundle": bundle,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(bundle_path)
    return 0


def _adapter_manifest_path(lora_train_receipt: dict[str, Any]) -> Path:
    artifact_path = str(lora_train_receipt.get("artifact_path", "")).strip()
    if artifact_path:
        return Path(artifact_path)
    weights_path = str(lora_train_receipt.get("weights_path", "")).strip()
    if not weights_path:
        raise AcceptanceBundleError("lora train receipt did not include artifact_path or weights_path.")
    weights_parent = Path(weights_path).expanduser().resolve().parent
    job_root = weights_parent.parent if weights_parent.name == "adapter" else weights_parent
    return job_root / "train_lora.adapter.json"


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_model_source(
    *,
    execution_profile: str,
    model_id: str,
    local_model_path: str,
    live: bool,
) -> tuple[str, bool, str, str, tuple[str, ...]]:
    if execution_profile != "real_small_model":
        if not model_id:
            raise AcceptanceBundleError("--model-id is required.")
        if live:
            return model_id, True, "", "explicit_live_hub", ()
        if local_model_path:
            return model_id, False, local_model_path, "explicit_local_path", ()
        return model_id, False, "", "", ()

    source = resolve_real_small_text_model_source(
        model_id=model_id,
        local_model_path=local_model_path,
        live=live,
        environment=os.environ,
        allow_managed_root=False,
        allow_hf_cache=False,
    )
    return (
        source.model_id,
        source.live,
        source.local_model_path,
        source.source_resolution_mode,
        source.warnings,
    )


def _default_source_resolution_mode(config: AcceptanceBundleConfig) -> str:
    if config.live:
        return "explicit_live_hub"
    if config.local_model_path.strip():
        return "explicit_local_path"
    return ""


def _should_capture_lora_registry(config: AcceptanceBundleConfig) -> bool:
    return bool(
        config.execution_profile == "real_small_model"
        or config.experiment_group_id
        or config.publish_mode != "disabled"
    )


def _experiment_index_path(config: AcceptanceBundleConfig) -> Path:
    jobs_root_env = os.environ.get("MELIX_MODEL_OPS_JOBS_ROOT", "").strip()
    jobs_root = (
        Path(jobs_root_env).expanduser().resolve()
        if jobs_root_env
        else (config.repo_root / ".runtime" / "model-ops").resolve()
    )
    return jobs_root / "train_lora" / _EXPERIMENT_INDEX_NAME


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _evaluation_scoring_mode(suites: list[str]) -> str:
    if not suites:
        return "normalized_exact_match"
    return _EVALUATION_SCORING_MODES.get(suites[0], "normalized_exact_match")


def _maybe_publish_adapter(
    *,
    config: AcceptanceBundleConfig,
    executor: JSONCommandExecuting,
    model_id: str,
    adapter_manifest_path: Path,
    cli_receipts_root: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "mode": config.publish_mode,
        "status": "disabled",
        "skip_reason": "publish_disabled",
        "target_repo": config.publish_target_repo,
    }
    if config.publish_mode == "disabled":
        return result
    if not config.publish_target_repo.strip():
        if config.publish_mode == "required":
            raise AcceptanceBundleError("publish target repo is required when publish mode is required.")
        result["status"] = "skipped"
        result["skip_reason"] = "publish_target_repo_missing"
        return result
    if _has_publish_token() is False:
        if config.publish_mode == "required":
            raise AcceptanceBundleError("Hugging Face token is required when publish mode is required.")
        result["status"] = "skipped"
        result["skip_reason"] = "missing_hf_token"
        return result

    publish_receipt = _expect_mapping(
        executor.run_json(
            [
                "upload",
                "--model-id",
                model_id,
                "--artifact-path",
                str(adapter_manifest_path),
                "--artifact-kind",
                "adapter",
                "--target-repo",
                config.publish_target_repo,
                "--json",
            ]
        ),
        context="melix upload",
    )
    _write_json(cli_receipts_root / "17-publish.json", publish_receipt)
    return {
        "mode": config.publish_mode,
        "status": str(publish_receipt.get("status", "published")),
        "skip_reason": "",
        "target_repo": config.publish_target_repo,
        "receipt": publish_receipt,
    }


def _has_publish_token() -> bool:
    for key in _HF_TOKEN_KEYS:
        if os.environ.get(key, "").strip():
            return True
    return False


def _return_code_description(returncode: int) -> str:
    if returncode < 0:
        return f"terminated by signal {-returncode}"
    return f"exit code {returncode}"


def _utc_event_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _cli_step_label(args: list[str]) -> str:
    if len(args) >= 3 and args[0] == "bench" and args[1] == "matrix":
        return f"bench matrix {args[2]}"
    if len(args) >= 3 and args[0] == "model" and args[1] in {"hub", "roots"}:
        return f"model {args[1]} {args[2]}"
    if len(args) >= 2 and args[0] == "provider":
        return f"provider {args[1]}"
    if len(args) >= 2:
        return f"{args[0]} {args[1]}"
    if args:
        return args[0]
    return "melix"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")


def _trim_diagnostic_text(value: str, *, limit: int = 4_096) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1_000.0, 2)


def _expect_list(payload: object, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise AcceptanceBundleError(f"{context} did not return a JSON array.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AcceptanceBundleError(f"{context} payload at index {index} was not a JSON object.")
        rows.append(item)
    return rows


def _expect_mapping(payload: object | None, *, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AcceptanceBundleError(f"{context} did not return a JSON object.")
    return payload


def _job_id_from_report_path(report_path: str) -> str:
    report_parent = Path(report_path).expanduser().resolve().parent
    job_id = report_parent.name.strip()
    if not job_id:
        raise AcceptanceBundleError("bench run receipt did not include a report path with a job directory.")
    return job_id


def _repeated_flag(flag: str, values: list[str]) -> list[str]:
    args: list[str] = []
    for value in values:
        args.extend([flag, value])
    return args


def _require_existing_export(payload: dict[str, Any], key: str, *, context: str) -> Path:
    output_path = _require_string(payload, key, context=context)
    path = Path(output_path)
    if not path.is_file():
        raise AcceptanceBundleError(f"Missing required export artifact: {path}")
    return path


def _require_string(payload: dict[str, Any], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AcceptanceBundleError(f"{context} did not include {key}.")
    return value


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
