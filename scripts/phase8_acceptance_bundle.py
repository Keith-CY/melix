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


_BASE_CHAT_PROMPT = "Reply with BASE_OK"
_DERIVED_CHAT_PROMPT = "Reply with DERIVED_OK"
_TRAINING_FIXTURE_DATASET_ID = "melix-dev-dataset.v1"
_ADAPTER_NAME = "phase8-acceptance"
_DERIVED_ALIAS = "phase8-acceptance-derived"
_BUNDLE_SCHEMA_VERSION = "melix.phase8.acceptance_bundle.v1"
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
        details = self.stderr.strip() or self.stdout.strip() or f"command exited with {self.returncode}"
        return f"{joined} failed with exit code {self.returncode}: {details}"


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
    server_session_id: str
    local_model_path: str
    live: bool
    timestamp: str
    json_output: bool


class JSONCommandExecuting(Protocol):
    def run_json(self, args: list[str]) -> object:
        ...


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

    timings: dict[str, float] = {}
    bundle_root.mkdir(parents=True, exist_ok=True)
    exports_root.mkdir(parents=True, exist_ok=True)
    cli_receipts_root.mkdir(parents=True, exist_ok=True)

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
    timings["phase8.cli.managed_materialize_ms"] = _elapsed_ms(materialize_started_at)

    model_id = _require_string(materialize_receipt, "model_id", context="managed model receipt")
    managed_model_path = _require_string(materialize_receipt, "managed_model_path", context="managed model receipt")
    source_kind = _require_string(materialize_receipt, "source_kind", context="managed model receipt")
    source_locator = _require_string(materialize_receipt, "source_locator", context="managed model receipt")
    _write_json(cli_receipts_root / "01-materialize.json", materialize_receipt)

    rebind_started_at = time.perf_counter()
    registry_snapshot = _expect_mapping(
        executor.run_json(["model", "roots", "rescan", "--json"]),
        context="melix model roots rescan",
    )
    _write_json(cli_receipts_root / "02-registry-rescan.json", registry_snapshot)

    server_update = _expect_mapping(
        executor.run_json(
            [
                "server",
                "session",
                "update",
                "--server-session-id",
                config.server_session_id,
                "--model-id",
                model_id,
                "--json",
            ]
        ),
        context="melix server session update",
    )
    _write_json(cli_receipts_root / "03-server-session-update.json", server_update)

    server_start = _expect_mapping(
        executor.run_json(
            [
                "server",
                "start",
                "--server-session-id",
                config.server_session_id,
                "--json",
            ]
        ),
        context="melix server start",
    )
    _write_json(cli_receipts_root / "04-server-start.json", server_start)
    timings["phase8.cli.session_rebind_ms"] = _elapsed_ms(rebind_started_at)

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
    lora_train_receipt = _expect_mapping(
        executor.run_json(
            [
                "lora",
                "train",
                "--model-id",
                model_id,
                "--dataset-uri",
                config.training_fixture,
                "--adapter-name",
                _ADAPTER_NAME,
                "--json",
            ]
        ),
        context="melix lora train",
    )
    timings["phase8.cli.lora_train_ms"] = _elapsed_ms(lora_train_started_at)
    _write_json(cli_receipts_root / "06-lora-train.json", lora_train_receipt)

    adapter_manifest_path = _adapter_manifest_path(lora_train_receipt)

    lora_activate_started_at = time.perf_counter()
    lora_activate_receipt = _expect_mapping(
        executor.run_json(
            [
                "lora",
                "activate",
                "--model-id",
                model_id,
                "--adapter-path",
                str(adapter_manifest_path),
                "--alias",
                _DERIVED_ALIAS,
                "--json",
            ]
        ),
        context="melix lora activate",
    )
    timings["phase8.cli.lora_activate_ms"] = _elapsed_ms(lora_activate_started_at)
    _write_json(cli_receipts_root / "07-lora-activate.json", lora_activate_receipt)

    derived_model_id = _require_string(lora_activate_receipt, "derived_model_id", context="lora activation receipt")
    derived_model_alias = str(lora_activate_receipt.get("derived_model_alias", _DERIVED_ALIAS)).strip() or _DERIVED_ALIAS

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
    _write_json(cli_receipts_root / "08-derived-chat.json", derived_chat_receipt)

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
    _write_json(cli_receipts_root / "09-bench-run.json", bench_run_receipt)
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
    _write_json(cli_receipts_root / "10-bench-matrix-run.json", matrix_run_receipt)
    matrix_job = _expect_mapping(matrix_run_receipt.get("job"), context="bench matrix job payload")
    bench_matrix_job_id = _require_string(matrix_job, "job_id", context="bench matrix job payload")

    evaluation_started_at = time.perf_counter()
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
                "--json",
            ]
        ),
        context="melix eval run",
    )
    timings["phase8.cli.evaluation_run_ms"] = _elapsed_ms(evaluation_started_at)
    _write_json(cli_receipts_root / "11-eval-run.json", evaluation_runs)
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
    _write_json(cli_receipts_root / "12-bench-export.json", bench_export_receipt)

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
    _write_json(cli_receipts_root / "13-bench-matrix-export.json", matrix_export_receipt)

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
    _write_json(cli_receipts_root / "14-eval-summary-export.json", evaluation_summary_export)

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
    _write_json(cli_receipts_root / "15-eval-samples-export.json", evaluation_samples_export)

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

    bundle: dict[str, Any] = {
        "schema_version": _BUNDLE_SCHEMA_VERSION,
        "timestamp": config.timestamp,
        "bundle_root": str(bundle_root),
        "model": {
            "model_id": model_id,
            "managed_model_path": managed_model_path,
            "source_kind": source_kind,
            "source_locator": source_locator,
            "warnings": materialize_receipt.get("warnings", []),
        },
        "derived_model": {
            "model_id": derived_model_id,
            "alias": derived_model_alias,
            "manifest_path": str(lora_activate_receipt.get("manifest_path", "")),
        },
        "server": {
            "server_session_id": config.server_session_id,
            "update": server_update,
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
        "exports": {
            "bench_csv": str(bench_csv),
            "matrix_summary_csv": str(matrix_summary_csv),
            "evaluation_summary_csv": str(evaluation_summary_csv),
            "evaluation_samples_jsonl": str(evaluation_samples_jsonl),
        },
        "chats": {
            "base": base_chat_receipt,
            "derived": derived_chat_receipt,
        },
        "cli": {
            "materialize": materialize_receipt,
            "registry_rescan": registry_snapshot,
            "lora_train": lora_train_receipt,
            "lora_activate": lora_activate_receipt,
            "bench_run": bench_run_receipt,
            "bench_matrix_run": matrix_run_receipt,
            "evaluation_runs": evaluation_runs,
            "bench_export": bench_export_receipt,
            "bench_matrix_export": matrix_export_receipt,
            "evaluation_summary_export": evaluation_summary_export,
            "evaluation_samples_export": evaluation_samples_export,
        },
        "metrics": timings,
    }

    bundle_write_started_at = time.perf_counter()
    _write_json(bundle_path, bundle)
    timings["phase8.cli.acceptance_bundle_write_ms"] = _elapsed_ms(bundle_write_started_at)
    _write_json(bundle_path, bundle)
    return bundle_path, bundle


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Phase 8 CLI acceptance bundle flow.")
    parser.add_argument("--repo-root", default="", help="Override the repository root path.")
    parser.add_argument("--melix-home", default="", help="Override MELIX_HOME for bundle output.")
    parser.add_argument("--model-id", required=True, help="Managed or Hub model identifier to validate.")
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
        "--server-session-id",
        default="server-session-1",
        help="Server session to rebind and start during acceptance.",
    )
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
    return AcceptanceBundleConfig(
        repo_root=repo_root,
        melix_home=melix_home,
        model_id=args.model_id,
        training_fixture=args.training_fixture,
        bench_suites=list(args.bench_suite),
        matrix_suites=list(args.matrix_suite),
        evaluation_suites=list(args.evaluation_suite),
        evaluation_dataset=args.evaluation_dataset,
        server_session_id=args.server_session_id,
        local_model_path=args.local_model_path,
        live=bool(args.live),
        timestamp=timestamp,
        json_output=bool(args.json),
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
