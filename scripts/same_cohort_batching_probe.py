#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_PREFIX = "MELIX_SAME_COHORT_BATCHING_PROBE_JSON="


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or analyze the deterministic same-cohort Swift text batching probe."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Analyze an existing raw probe JSON payload instead of running the Swift probe.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the analyzed probe JSON payload to this path.",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Emit flat numeric metrics for the PR-scoped performance runner.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a non-zero exit code when the probe detects admission batching without worker/model batching.",
    )
    parser.add_argument(
        "--swift-filter",
        default=(
            "RequestCoordinatorTests/"
            "sameCohortBatchingProbeEmitsLinkedAdmissionAndWorkerEvidence()"
        ),
        help="Swift test filter used when running the live deterministic probe.",
    )
    return parser.parse_args()


def run_swift_probe(swift_filter: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["MELIX_SAME_COHORT_BATCHING_PROBE"] = "1"
    env.setdefault("HOME", os.fspath(REPO_ROOT / ".swift-home" / "same-cohort-batching-probe"))
    env.setdefault(
        "CLANG_MODULE_CACHE_PATH",
        os.fspath(REPO_ROOT / ".build" / "ModuleCache.noindex" / "same-cohort-batching-probe"),
    )
    command = [
        "swift",
        "test",
        "--package-path",
        os.fspath(REPO_ROOT / "services" / "control-plane-swift"),
        "--filter",
        swift_filter,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Swift CLI ('swift') was not found in PATH. "
            "Install Swift or run this script from a toolchain-enabled shell."
        ) from exc
    swift_output = completed.stdout or ""
    payloads = [
        line.removeprefix(PROBE_PREFIX)
        for line in swift_output.splitlines()
        if line.startswith(PROBE_PREFIX)
    ]
    if completed.returncode != 0:
        raise RuntimeError(
            "same-cohort Swift probe test failed with exit code "
            f"{completed.returncode}\n{swift_output}"
        )
    if not payloads:
        raise RuntimeError(
            "same-cohort Swift probe test passed but did not emit probe JSON. "
            f"Expected prefix {PROBE_PREFIX!r}.\n{swift_output}"
        )
    try:
        return json.loads(payloads[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse same-cohort probe JSON payload: {exc}\n"
            f"Payload: {payloads[-1]}"
        ) from exc


def analyze_probe(raw: dict[str, Any]) -> dict[str, Any]:
    admission = _as_dict(raw.get("admission"))
    worker = _as_dict(raw.get("worker"))
    links = _as_list(raw.get("request_links"))

    scheduler_batch_size = _first_number(
        admission,
        "scheduler_admission_cohort_size",
        "scheduler_continuous_batch_size",
    )
    worker_decode_batch_size = _first_number(worker, "decode_batch_size")
    worker_model_eval_batch_size = _first_number(
        worker,
        "model_eval_batch_size",
        "max_model_step_batch_size",
    )
    worker_max_batch_size = max(worker_decode_batch_size, worker_model_eval_batch_size)
    linked_request_count = len(links)
    worker_decode_request_ids = {
        request_id
        for value in _as_list(worker.get("decode_request_ids"))
        if (request_id := _request_id(value)) is not None
    }
    linked_decode_request_ids = {
        request_id
        for item in links
        if isinstance(item, dict)
        and (request_id := _request_id(item.get("worker_decode_request_id"))) is not None
    }
    missing_decode_links = sorted(linked_decode_request_ids - worker_decode_request_ids)
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    if linked_request_count < 2:
        failures.append({
            "code": "missing_request_links",
            "message": "Probe did not link two same-cohort requests.",
            "linked_request_count": linked_request_count,
        })
    if missing_decode_links:
        failures.append({
            "code": "missing_worker_decode_request_ids",
            "message": "Linked decode request IDs were absent from worker decode observations.",
            "missing_request_ids": missing_decode_links,
        })
    if scheduler_batch_size <= 1:
        failures.append({
            "code": "admission_batch_not_observed",
            "message": "Scheduler did not report a same-cohort admission batch larger than one.",
            "scheduler_continuous_batch_size": scheduler_batch_size,
        })
    if worker_decode_batch_size <= 0:
        failures.append({
            "code": "worker_decode_batch_missing",
            "message": "Worker decode batch-size evidence is missing.",
            "decode_batch_size": worker_decode_batch_size,
        })
    if worker_model_eval_batch_size <= 0:
        failures.append({
            "code": "worker_model_step_batch_missing",
            "message": "Worker/model-step batch-size evidence is missing.",
            "model_eval_batch_size": worker_model_eval_batch_size,
        })
    elif scheduler_batch_size > 1 and worker_max_batch_size == 1:
        warnings.append({
            "code": "admission_batch_without_worker_model_batch",
            "message": (
                "Scheduler admitted a same-cohort batch, but worker/model-step "
                "evidence still shows singleton decode steps."
            ),
            "scheduler_admission_cohort_size": scheduler_batch_size,
            "decode_batch_size": worker_decode_batch_size,
            "model_eval_batch_size": worker_model_eval_batch_size,
        })

    status = "failed" if failures else ("warning" if warnings else "passed")
    return {
        "schema_version": 1,
        "status": status,
        "warnings": warnings,
        "failures": failures,
        "raw_probe": raw,
    }


def probe_metrics(analyzed: dict[str, Any]) -> dict[str, float]:
    raw = _as_dict(analyzed.get("raw_probe"))
    admission = _as_dict(raw.get("admission"))
    worker = _as_dict(raw.get("worker"))
    links = _as_list(raw.get("request_links"))
    warnings = _as_list(analyzed.get("warnings"))
    failures = _as_list(analyzed.get("failures"))
    scheduler_batch_size = _first_number(
        admission,
        "scheduler_admission_cohort_size",
        "scheduler_continuous_batch_size",
    )
    scheduler_active_cohorts = _first_number(
        admission,
        "scheduler_admission_active_cohorts",
        "scheduler_continuous_batch_active_cohorts",
    )
    worker_decode_batch_size = _first_number(worker, "decode_batch_size")
    worker_model_eval_batch_size = _first_number(
        worker,
        "model_eval_batch_size",
        "max_model_step_batch_size",
    )
    worker_batch_size = max(worker_decode_batch_size, worker_model_eval_batch_size)
    decode_loop_iterations = _number(worker.get("decode_loop_iterations"))
    scheduler_to_worker_batch_delta = max(0.0, scheduler_batch_size - worker_batch_size)
    return {
        "status_passed": 1.0 if analyzed.get("status") == "passed" else 0.0,
        "status_warning": 1.0 if analyzed.get("status") == "warning" else 0.0,
        "status_failed": 1.0 if analyzed.get("status") == "failed" else 0.0,
        "warning_count": float(len(warnings)),
        "failure_count": float(len(failures)),
        "scheduler_continuous_batch_size": scheduler_batch_size,
        "scheduler_admission_cohort_size": scheduler_batch_size,
        "scheduler_active_cohorts": scheduler_active_cohorts,
        "scheduler_admission_active_cohorts": scheduler_active_cohorts,
        "worker_decode_batch_size": worker_decode_batch_size,
        "worker_model_eval_batch_size": worker_model_eval_batch_size,
        "worker_max_model_step_batch_size": worker_batch_size,
        "worker_decode_loop_iterations": decode_loop_iterations,
        "worker_decode_batch_observation_count": _number(worker.get("decode_batch_observation_count")),
        "worker_per_batch_output_token_count": _number(worker.get("per_batch_output_token_count")),
        "worker_per_batch_output_tokens_per_second": _number(
            worker.get("per_batch_output_tokens_per_second")
        ),
        "linked_request_count": float(len(links)),
        "scheduler_to_worker_batch_delta": scheduler_to_worker_batch_delta,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _first_number(mapping: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0.0


def _request_id(value: Any) -> str | None:
    if value is None:
        return None
    request_id = str(value).strip()
    return request_id or None


def _read_probe_input(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Input probe JSON file does not exist: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse input probe JSON file {path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"Input probe JSON file must contain a JSON object: {path}")
    return raw


def main() -> int:
    args = parse_args()
    try:
        raw = (
            _read_probe_input(args.input)
            if args.input is not None
            else run_swift_probe(args.swift_filter)
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    analyzed = analyze_probe(raw)
    if args.metrics:
        print(json.dumps(probe_metrics(analyzed), sort_keys=True) + "\n", end="")
        if analyzed["status"] == "failed":
            return 1
        return 0
    rendered = json.dumps(analyzed, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(
                f"error: failed to write output file {args.output}: {exc}",
                file=sys.stderr,
            )
            return 1
    print(rendered, end="")
    if analyzed["status"] == "failed":
        return 1
    if analyzed["status"] == "warning" and args.fail_on_warning:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
