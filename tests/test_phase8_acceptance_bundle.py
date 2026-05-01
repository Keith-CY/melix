from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import phase8_acceptance_bundle


class _FakeExecutor:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[list[str]] = []

    def run_json(self, args: list[str]) -> object:
        self.calls.append(["melix", *args])
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _bundle_root(tmp_path: Path) -> Path:
    return tmp_path / "melix-home" / "acceptance" / "phase8" / "cli" / "2026-04-09T120000Z"


def _bundle_config(tmp_path: Path, *, live: bool = True) -> phase8_acceptance_bundle.AcceptanceBundleConfig:
    return phase8_acceptance_bundle.AcceptanceBundleConfig(
        repo_root=tmp_path,
        melix_home=tmp_path / "melix-home",
        model_id="mlx-community/Qwen3.5-0.8B-OptiQ-4bit" if live else "melix-dev-qwen-local",
        training_fixture="services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
        bench_suites=["smoke", "latency"],
        matrix_suites=["smoke"],
        evaluation_suites=["mmlu"],
        evaluation_dataset="mmlu.dev.v1",
        server_session_id="server-session-1",
        local_model_path="" if live else str(tmp_path / "fixture-model"),
        live=live,
        timestamp="2026-04-09T120000Z",
        json_output=True,
    )


def _successful_acceptance_responses(
    tmp_path: Path,
    *,
    source_kind: str = "hub_repo",
    source_locator: str = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
    model_id: str = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
    evaluation_runs: list[dict[str, object]] | None = None,
) -> list[object]:
    export_root = _bundle_root(tmp_path) / "exports"
    bench_csv = export_root / "bench.csv"
    matrix_summary_csv = export_root / "bench-matrix-summary.csv"
    evaluation_summary_csv = export_root / "evaluation-summary.csv"
    evaluation_samples_jsonl = export_root / "evaluation-samples.jsonl"
    for path in [bench_csv, matrix_summary_csv, evaluation_summary_csv, evaluation_samples_jsonl]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")
    return [
        {
            "model_id": model_id,
            "managed_model_path": str(tmp_path / "managed-models" / model_id),
            "source_kind": source_kind,
            "source_locator": source_locator,
        },
        {"registry_roots": ["/tmp/models"]},
        {"selected_server_session_id": "server-session-1"},
        {"server_state": "server_ready"},
        {
            "model_id": model_id,
            "server_session_id": "server-session-1",
            "assistant_text": "Echo: Reply with BASE_OK",
            "finish_reason": "stop",
            "request_id": "chat-base-1",
        },
        {
            "job_id": "model-ops-0001",
            "weights_path": str(tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "adapters.safetensors"),
            "adapter_config_path": str(
                tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "adapter_config.json"
            ),
        },
        {
            "derived_model_id": "melix-dev-qwen-local-lora-phase8",
            "derived_model_alias": "phase8-acceptance-derived",
            "manifest_path": str(
                tmp_path / "model-ops" / "activate_adapter" / "model-ops-0002" / "manifest.json"
            ),
        },
        {
            "model_id": "melix-dev-qwen-local-lora-phase8",
            "server_session_id": "server-session-1",
            "assistant_text": "Echo: Reply with DERIVED_OK",
            "finish_reason": "stop",
            "request_id": "chat-derived-1",
        },
        {
            "job_id": "bench-1",
            "output_dir": str(tmp_path / "bench" / "bench-1"),
            "report_path": str(tmp_path / "bench" / "bench-1" / "report.md"),
            "report_markdown": "# Bench\n",
            "metrics": {"bench.smoke.ttft_ms": 24.45},
        },
        {
            "job": {
                "job_id": "bench-matrix-1",
                "output_dir": str(tmp_path / "bench" / "matrix" / "bench-matrix-1"),
            },
            "summary_rows": [],
        },
        evaluation_runs
        if evaluation_runs is not None
        else [
            {
                "job": {
                    "job_id": "eval-1",
                    "output_dir": str(tmp_path / "eval" / "eval-1"),
                },
                "results": [],
            }
        ],
        {"job_id": "bench-1", "output_path": str(bench_csv), "row_count": 1},
        {"job_id": "bench-matrix-1", "output_path": str(matrix_summary_csv), "row_count": 1},
        {"job_id": "eval-1", "output_path": str(evaluation_summary_csv), "row_count": 1},
        {"job_id": "eval-1", "output_path": str(evaluation_samples_jsonl), "row_count": 1},
    ]


def test_run_acceptance_bundle_shells_out_in_expected_order(tmp_path: Path) -> None:
    export_root = _bundle_root(tmp_path) / "exports"
    bench_csv = export_root / "bench.csv"
    matrix_summary_csv = export_root / "bench-matrix-summary.csv"
    evaluation_summary_csv = export_root / "evaluation-summary.csv"
    evaluation_samples_jsonl = export_root / "evaluation-samples.jsonl"
    for path in [bench_csv, matrix_summary_csv, evaluation_summary_csv, evaluation_samples_jsonl]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")

    executor = _FakeExecutor(
        [
            {
                "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "managed_model_path": str(tmp_path / "managed-models" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit"),
                "source_kind": "hub_repo",
                "source_locator": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            },
            {"registry_roots": ["/tmp/models"]},
            {"selected_server_session_id": "server-session-1"},
            {"server_state": "server_ready"},
            {
                "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "server_session_id": "server-session-1",
                "assistant_text": "Echo: Reply with BASE_OK",
                "finish_reason": "stop",
                "request_id": "chat-base-1",
            },
            {
                "job_id": "model-ops-0001",
                "weights_path": str(tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "adapters.safetensors"),
                "adapter_config_path": str(
                    tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "adapter_config.json"
                ),
            },
            {
                "derived_model_id": "melix-dev-qwen-local-lora-phase8",
                "derived_model_alias": "phase8-acceptance-derived",
                "manifest_path": str(
                    tmp_path / "model-ops" / "activate_adapter" / "model-ops-0002" / "manifest.json"
                ),
            },
            {
                "model_id": "melix-dev-qwen-local-lora-phase8",
                "server_session_id": "server-session-1",
                "assistant_text": "Echo: Reply with DERIVED_OK",
                "finish_reason": "stop",
                "request_id": "chat-derived-1",
            },
            {
                "job_id": "bench-1",
                "output_dir": str(tmp_path / "bench" / "bench-1"),
                "report_path": str(tmp_path / "bench" / "bench-1" / "report.md"),
                "report_markdown": "# Bench\n",
                "metrics": {"bench.smoke.ttft_ms": 24.45},
            },
            {
                "job": {
                    "job_id": "bench-matrix-1",
                    "output_dir": str(tmp_path / "bench" / "matrix" / "bench-matrix-1"),
                },
                "summary_rows": [],
            },
            [
                {
                    "job": {
                        "job_id": "eval-1",
                        "output_dir": str(tmp_path / "eval" / "eval-1"),
                    },
                    "results": [],
                }
            ],
            {"job_id": "bench-1", "output_path": str(bench_csv), "row_count": 1},
            {"job_id": "bench-matrix-1", "output_path": str(matrix_summary_csv), "row_count": 1},
            {"job_id": "eval-1", "output_path": str(evaluation_summary_csv), "row_count": 1},
            {"job_id": "eval-1", "output_path": str(evaluation_samples_jsonl), "row_count": 1},
        ]
    )
    stale_events_path = _bundle_root(tmp_path) / "events.jsonl"
    stale_events_path.parent.mkdir(parents=True, exist_ok=True)
    stale_events_path.write_text('{"event":"stale"}\n', encoding="utf-8")

    bundle_path, bundle = phase8_acceptance_bundle.run_acceptance_bundle(
        _bundle_config(tmp_path, live=True),
        executor=executor,
    )

    assert executor.calls == [
        ["melix", "model", "hub", "download", "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--json"],
        ["melix", "model", "roots", "rescan", "--json"],
        [
            "melix",
            "server",
            "session",
            "update",
            "--server-session-id",
            "server-session-1",
            "--model-id",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--json",
        ],
        ["melix", "server", "start", "--server-session-id", "server-session-1", "--json"],
        [
            "melix",
            "chat",
            "run",
            "--model-id",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--message",
            "Reply with BASE_OK",
            "--json",
        ],
        [
            "melix",
            "lora",
            "train",
            "--model-id",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--dataset-uri",
            "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
            "--adapter-name",
            "phase8-acceptance",
            "--json",
        ],
        [
            "melix",
            "lora",
            "activate",
            "--model-id",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--adapter-path",
            str(tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"),
            "--alias",
            "phase8-acceptance-derived",
            "--json",
        ],
        [
            "melix",
            "chat",
            "run",
            "--model-id",
            "melix-dev-qwen-local-lora-phase8",
            "--message",
            "Reply with DERIVED_OK",
            "--json",
        ],
        [
            "melix",
            "bench",
            "run",
            "--model-id",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--suite",
            "smoke",
            "--suite",
            "latency",
            "--context-length",
            "1024",
            "--generation-length",
            "64",
            "--batch-size",
            "1",
            "--sample-size",
            "4",
            "--json",
        ],
        [
            "melix",
            "bench",
            "matrix",
            "run",
            "--model-id",
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--suite",
            "smoke",
            "--context-length",
            "1024",
            "--generation-length",
            "64",
            "--batch-size",
            "1",
            "--cache-profile",
            "cold",
            "--reasoning-mode",
            "disabled",
            "--structured-output-mode",
            "plain_text",
            "--concurrency",
            "1",
            "--requests",
            "4",
            "--json",
        ],
        [
            "melix",
            "eval",
            "run",
            "--model-id",
            "melix-dev-qwen-local-lora-phase8",
            "--suite",
            "mmlu",
            "--dataset-id",
            "mmlu.dev.v1",
            "--sample-size",
            "4",
            "--scoring-mode",
            "multiple_choice_accuracy",
            "--json",
        ],
        ["melix", "bench", "export-csv", "--job-id", "bench-1", "--output", str(bench_csv), "--json"],
        [
            "melix",
            "bench",
            "matrix",
            "export-summary-csv",
            "--job-id",
            "bench-matrix-1",
            "--output",
            str(matrix_summary_csv),
            "--json",
        ],
        [
            "melix",
            "eval",
            "export-summary-csv",
            "--job-id",
            "eval-1",
            "--output",
            str(evaluation_summary_csv),
            "--json",
        ],
        [
            "melix",
            "eval",
            "export-samples-jsonl",
            "--job-id",
            "eval-1",
            "--output",
            str(evaluation_samples_jsonl),
            "--json",
        ],
    ]
    assert bundle_path == _bundle_root(tmp_path) / "bundle.json"
    assert bundle_path.is_file()
    assert bundle["jobs"]["lora_train_job_id"] == "model-ops-0001"
    assert bundle["jobs"]["bench_job_id"] == "bench-1"
    assert bundle["jobs"]["bench_matrix_job_id"] == "bench-matrix-1"
    assert bundle["jobs"]["evaluation_job_id"] == "eval-1"
    assert bundle["exports"]["evaluation_samples_jsonl"] == str(evaluation_samples_jsonl)
    assert bundle["diagnostics"]["event_log_jsonl"] == str(_bundle_root(tmp_path) / "events.jsonl")
    events = [
        json.loads(line)
        for line in (_bundle_root(tmp_path) / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["event"] == "cli_step_started"
    assert events[0]["step_label"] == "model hub download"
    assert events[-1]["event"] == "cli_step_completed"
    assert all(event["event"] != "stale" for event in events)


def test_run_acceptance_bundle_bubbles_cli_failures(tmp_path: Path) -> None:
    executor = _FakeExecutor(
        [
            phase8_acceptance_bundle.CLICommandError(
                command=["melix", "model", "hub", "download", "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"],
                returncode=1,
                stderr="download failed",
            )
        ]
    )

    with pytest.raises(phase8_acceptance_bundle.CLICommandError, match="download failed"):
        phase8_acceptance_bundle.run_acceptance_bundle(_bundle_config(tmp_path, live=True), executor=executor)


def test_cli_command_error_formats_negative_return_code_without_output() -> None:
    error = phase8_acceptance_bundle.CLICommandError(
        command=["melix", "model", "import"],
        returncode=-1,
        stderr="",
        stdout="",
    )

    message = str(error)

    assert "terminated by signal 1" in message
    assert "no stderr or stdout captured" in message


def test_run_acceptance_bundle_writes_event_log_before_cli_failure(tmp_path: Path) -> None:
    executor = _FakeExecutor(
        [
            phase8_acceptance_bundle.CLICommandError(
                command=["melix", "model", "hub", "download"],
                returncode=-1,
                stderr="",
                stdout="",
            )
        ]
    )

    with pytest.raises(phase8_acceptance_bundle.CLICommandError):
        phase8_acceptance_bundle.run_acceptance_bundle(_bundle_config(tmp_path, live=True), executor=executor)

    events_path = _bundle_root(tmp_path) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert events[0]["event"] == "cli_step_started"
    assert events[0]["step_label"] == "model hub download"
    assert events[0]["args"] == [
        "model",
        "hub",
        "download",
        "--repo-id",
        "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "--json",
    ]
    assert events[1]["event"] == "cli_step_failed"
    assert events[1]["returncode"] == -1
    assert "terminated by signal 1" in events[1]["failure"]


def test_tracing_executor_records_unexpected_exceptions(tmp_path: Path) -> None:
    class _ExplodingExecutor:
        def run_json(self, args: list[str]) -> object:  # noqa: ARG002
            raise ValueError("unexpected executor failure")

    event_log_path = tmp_path / "events.jsonl"
    executor = phase8_acceptance_bundle._TracingJSONExecutor(
        executor=_ExplodingExecutor(),
        event_log_path=event_log_path,
    )

    with pytest.raises(ValueError, match="unexpected executor failure"):
        executor.run_json(["model", "list", "--json"])

    events = [json.loads(line) for line in event_log_path.read_text(encoding="utf-8").splitlines()]
    assert events[0]["event"] == "cli_step_started"
    assert events[1]["event"] == "cli_step_failed"
    assert events[1]["exception_type"] == "ValueError"
    assert events[1]["failure"] == "unexpected executor failure"


def test_run_acceptance_bundle_rejects_missing_evaluation_export_paths(tmp_path: Path) -> None:
    export_root = _bundle_root(tmp_path) / "exports"
    bench_csv = export_root / "bench.csv"
    matrix_summary_csv = export_root / "bench-matrix-summary.csv"
    evaluation_summary_csv = export_root / "evaluation-summary.csv"
    for path in [bench_csv, matrix_summary_csv, evaluation_summary_csv]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    missing_samples_jsonl = export_root / "evaluation-samples.jsonl"

    executor = _FakeExecutor(
        [
            {
                "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "managed_model_path": str(tmp_path / "managed-models" / "mlx-community" / "Qwen3.5-0.8B-OptiQ-4bit"),
                "source_kind": "hub_repo",
                "source_locator": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            },
            {"registry_roots": ["/tmp/models"]},
            {"selected_server_session_id": "server-session-1"},
            {"server_state": "server_ready"},
            {"assistant_text": "Echo: Reply with BASE_OK", "finish_reason": "stop", "request_id": "chat-base-1"},
            {"job_id": "model-ops-0001", "weights_path": str(tmp_path / "train" / "model-ops-0001" / "adapters.safetensors")},
            {"derived_model_id": "melix-dev-qwen-local-lora-phase8"},
            {"assistant_text": "Echo: Reply with DERIVED_OK", "finish_reason": "stop", "request_id": "chat-derived-1"},
            {
                "job_id": "bench-1",
                "output_dir": str(tmp_path / "bench" / "bench-1"),
                "report_path": str(tmp_path / "bench" / "bench-1" / "report.md"),
                "metrics": {},
            },
            {"job": {"job_id": "bench-matrix-1", "output_dir": str(tmp_path / "bench" / "matrix" / "bench-matrix-1")}, "summary_rows": []},
            [{"job": {"job_id": "eval-1", "output_dir": str(tmp_path / "eval" / "eval-1")}, "results": []}],
            {"job_id": "bench-1", "output_path": str(bench_csv), "row_count": 1},
            {"job_id": "bench-matrix-1", "output_path": str(matrix_summary_csv), "row_count": 1},
            {"job_id": "eval-1", "output_path": str(evaluation_summary_csv), "row_count": 1},
            {"job_id": "eval-1", "output_path": str(missing_samples_jsonl), "row_count": 1},
        ]
    )

    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="Missing required export artifact"):
        phase8_acceptance_bundle.run_acceptance_bundle(_bundle_config(tmp_path, live=True), executor=executor)


def test_cli_json_executor_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(
            args=["melix", "model", "list", "--json"],
            returncode=0,
            stdout="{not-json",
            stderr="",
        )

    monkeypatch.setattr(phase8_acceptance_bundle.subprocess, "run", fake_run)
    executor = phase8_acceptance_bundle.CLIJSONExecutor(repo_root=tmp_path, environment={})

    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="did not return valid JSON"):
        executor.run_json(["model", "list", "--json"])


def test_cli_json_executor_raises_cli_command_error_for_non_zero_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(
            args=["melix", "model", "list", "--json"],
            returncode=2,
            stdout="partial",
            stderr="boom",
        )

    monkeypatch.setattr(phase8_acceptance_bundle.subprocess, "run", fake_run)
    executor = phase8_acceptance_bundle.CLIJSONExecutor(repo_root=tmp_path, environment={}, cli_binary="melix")

    with pytest.raises(phase8_acceptance_bundle.CLICommandError, match="boom"):
        executor.run_json(["model", "list", "--json"])


def test_cli_json_executor_prefers_built_cli_binary(tmp_path: Path) -> None:
    built_binary = tmp_path / ".build" / "arm64-apple-macosx" / "debug" / "melix"
    built_binary.parent.mkdir(parents=True, exist_ok=True)
    built_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    executor = phase8_acceptance_bundle.CLIJSONExecutor(repo_root=tmp_path, environment={})

    assert executor._resolved_cli_binary() == str(built_binary)


def test_run_acceptance_bundle_imports_local_model_when_live_disabled(tmp_path: Path) -> None:
    fixture_model = tmp_path / "fixture-model"
    fixture_model.mkdir(parents=True)
    executor = _FakeExecutor(
        _successful_acceptance_responses(
            tmp_path,
            source_kind="local_path",
            source_locator=str(fixture_model),
            model_id="melix-dev-qwen-local",
        )
    )

    bundle_path, bundle = phase8_acceptance_bundle.run_acceptance_bundle(
        _bundle_config(tmp_path, live=False),
        executor=executor,
    )

    assert bundle_path.is_file()
    assert executor.calls[0] == [
        "melix",
        "model",
        "import",
        "--path",
        str(fixture_model),
        "--model-id",
        "melix-dev-qwen-local",
        "--model-kind",
        "text",
        "--revision",
        "main",
        "--json",
    ]
    assert bundle["model"]["source_kind"] == "local_path"
    assert bundle["model"]["preflight"]["runtime_model_class"] == "deterministic_dev_model"


def test_run_acceptance_bundle_records_real_local_model_preflight(tmp_path: Path) -> None:
    fixture_model = tmp_path / "fixture-model"
    fixture_model.mkdir(parents=True)
    (fixture_model / "config.json").write_text("{}", encoding="utf-8")
    (fixture_model / "model.safetensors").write_text("weights\n", encoding="utf-8")
    config = replace(
        _bundle_config(tmp_path, live=False),
        model_id="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        local_model_path=str(fixture_model),
        source_resolution_mode="explicit_local_path",
    )
    executor = _FakeExecutor(
        _successful_acceptance_responses(
            tmp_path,
            source_kind="local_path",
            source_locator=str(fixture_model),
            model_id="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        )
    )

    _, bundle = phase8_acceptance_bundle.run_acceptance_bundle(config, executor=executor)

    assert bundle["model"]["preflight"] == {
        "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "runtime_model_class": "real_local_model",
        "real_local_model": True,
        "deterministic_dev_model": False,
        "hub_required": False,
        "local_model_path": str(fixture_model.resolve()),
        "source_resolution_mode": "explicit_local_path",
        "warnings": [],
    }


def test_run_acceptance_bundle_rejects_empty_evaluation_runs(tmp_path: Path) -> None:
    executor = _FakeExecutor(_successful_acceptance_responses(tmp_path, evaluation_runs=[]))

    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="did not return any evaluation payloads"):
        phase8_acceptance_bundle.run_acceptance_bundle(_bundle_config(tmp_path, live=True), executor=executor)


@pytest.mark.parametrize(
    ("extra_args", "message"),
    [
        (["--matrix-suite", "smoke", "--evaluation-suite", "mmlu"], "At least one --bench-suite is required."),
        (["--bench-suite", "smoke", "--evaluation-suite", "mmlu"], "At least one --matrix-suite is required."),
        (["--bench-suite", "smoke", "--matrix-suite", "smoke"], "At least one --evaluation-suite is required."),
    ],
)
def test_parse_args_requires_all_suite_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extra_args: list[str],
    message: str,
) -> None:
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "melix-home"))

    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match=message):
        phase8_acceptance_bundle.parse_args(
            [
                "--repo-root",
                str(tmp_path),
                "--model-id",
                "melix-dev-qwen-local",
                "--training-fixture",
                "fixture",
                *extra_args,
                "--evaluation-dataset",
                "mmlu.dev.v1",
            ]
        )


def test_parse_args_uses_repo_root_melix_home_and_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    melix_home = tmp_path / "custom-home"
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "ignored-home"))

    config = phase8_acceptance_bundle.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--melix-home",
            str(melix_home),
            "--model-id",
            "melix-dev-qwen-local",
            "--training-fixture",
            "fixture",
            "--bench-suite",
            "smoke",
            "--matrix-suite",
            "smoke",
            "--evaluation-suite",
            "mmlu",
            "--evaluation-dataset",
            "mmlu.dev.v1",
            "--timestamp",
            "2026-04-09T120000Z",
            "--json",
        ]
    )

    assert config.repo_root == tmp_path.resolve()
    assert config.melix_home == melix_home.resolve()
    assert config.timestamp == "2026-04-09T120000Z"
    assert config.json_output is True


def test_parse_args_applies_real_small_model_profile_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "melix-home"))
    monkeypatch.delenv("MELIX_PHASE8_REAL_SMALL_MODEL_PATH", raising=False)

    config = phase8_acceptance_bundle.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--execution-profile",
            "real_small_model",
            "--training-fixture",
            "fixture",
            "--bench-suite",
            "smoke",
            "--matrix-suite",
            "smoke",
            "--evaluation-suite",
            "mmlu",
            "--evaluation-dataset",
            "mmlu.dev.v1",
            "--json",
        ]
    )

    assert config.execution_profile == "real_small_model"
    assert config.model_id == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert config.acceptance_tier == "cli_real_small_model"
    assert config.runtime_backend_mode == "python_auto"
    assert config.activation_mode == "adapter_backed_runtime"
    assert config.training_preset_id == "debug_fast"
    assert config.training_max_steps == 2
    assert config.experiment_group_id == "phase8-real-small-model"
    assert config.live is True
    assert config.local_model_path == ""
    assert config.source_resolution_mode == "hub_fallback"
    assert config.materialize_warnings == ()
    assert config.publish_mode == "disabled"


def test_parse_args_real_small_model_prefers_env_local_model_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture_model = tmp_path / "fixture-model"
    fixture_model.mkdir(parents=True)
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "melix-home"))
    monkeypatch.setenv("MELIX_PHASE8_REAL_SMALL_MODEL_PATH", str(fixture_model))

    config = phase8_acceptance_bundle.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--execution-profile",
            "real_small_model",
            "--training-fixture",
            "fixture",
            "--bench-suite",
            "smoke",
            "--matrix-suite",
            "smoke",
            "--evaluation-suite",
            "mmlu",
            "--evaluation-dataset",
            "mmlu.dev.v1",
            "--json",
        ]
    )

    assert config.model_id == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert config.live is False
    assert config.local_model_path == str(fixture_model.resolve())
    assert config.source_resolution_mode == "env_local_path"
    assert config.materialize_warnings == ()


def test_parse_args_real_small_model_falls_back_to_hub_when_env_path_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "missing-model"
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "melix-home"))
    monkeypatch.setenv("MELIX_PHASE8_REAL_SMALL_MODEL_PATH", str(invalid_path))

    config = phase8_acceptance_bundle.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--execution-profile",
            "real_small_model",
            "--training-fixture",
            "fixture",
            "--bench-suite",
            "smoke",
            "--matrix-suite",
            "smoke",
            "--evaluation-suite",
            "mmlu",
            "--evaluation-dataset",
            "mmlu.dev.v1",
            "--json",
        ]
    )

    assert config.model_id == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert config.live is True
    assert config.local_model_path == ""
    assert config.source_resolution_mode == "env_invalid_hub_fallback"
    assert config.materialize_warnings == (
        f"Ignored MELIX_PHASE8_REAL_SMALL_MODEL_PATH because it does not point to an existing directory: {invalid_path.resolve()}",
    )


def test_parse_args_real_small_model_explicit_live_overrides_env_local_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture_model = tmp_path / "fixture-model"
    fixture_model.mkdir(parents=True)
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "melix-home"))
    monkeypatch.setenv("MELIX_PHASE8_REAL_SMALL_MODEL_PATH", str(fixture_model))

    config = phase8_acceptance_bundle.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--execution-profile",
            "real_small_model",
            "--live",
            "--training-fixture",
            "fixture",
            "--bench-suite",
            "smoke",
            "--matrix-suite",
            "smoke",
            "--evaluation-suite",
            "mmlu",
            "--evaluation-dataset",
            "mmlu.dev.v1",
            "--json",
        ]
    )

    assert config.live is True
    assert config.local_model_path == ""
    assert config.source_resolution_mode == "explicit_live_hub"
    assert config.materialize_warnings == ()


def test_parse_args_real_small_model_explicit_local_path_overrides_env_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_fixture_model = tmp_path / "env-model"
    env_fixture_model.mkdir(parents=True)
    explicit_fixture_model = tmp_path / "explicit-model"
    explicit_fixture_model.mkdir(parents=True)
    monkeypatch.setenv("MELIX_HOME", str(tmp_path / "melix-home"))
    monkeypatch.setenv("MELIX_PHASE8_REAL_SMALL_MODEL_PATH", str(env_fixture_model))

    config = phase8_acceptance_bundle.parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--execution-profile",
            "real_small_model",
            "--local-model-path",
            str(explicit_fixture_model),
            "--training-fixture",
            "fixture",
            "--bench-suite",
            "smoke",
            "--matrix-suite",
            "smoke",
            "--evaluation-suite",
            "mmlu",
            "--evaluation-dataset",
            "mmlu.dev.v1",
            "--json",
        ]
    )

    assert config.live is False
    assert config.local_model_path == str(explicit_fixture_model)
    assert config.source_resolution_mode == "explicit_local_path"
    assert config.materialize_warnings == ()


def test_run_acceptance_bundle_real_small_model_hub_fallback_records_resolution_metadata_and_warnings(
    tmp_path: Path,
) -> None:
    config = phase8_acceptance_bundle.AcceptanceBundleConfig(
        repo_root=tmp_path,
        melix_home=tmp_path / "melix-home",
        model_id="mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        training_fixture="services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
        bench_suites=["smoke"],
        matrix_suites=["smoke"],
        evaluation_suites=["mmlu"],
        evaluation_dataset="mmlu.dev.v1",
        server_session_id="server-session-1",
        local_model_path="",
        live=True,
        timestamp="2026-04-09T120000Z",
        json_output=True,
        execution_profile="real_small_model",
        acceptance_tier="cli_real_small_model",
        runtime_backend_mode="python_auto",
        activation_mode="adapter_backed_runtime",
        training_preset_id="debug_fast",
        training_max_steps=2,
        experiment_group_id="phase8-real-small-model",
        publish_mode="disabled",
        publish_target_repo="",
        source_resolution_mode="env_invalid_hub_fallback",
        materialize_warnings=(
            "Ignored MELIX_PHASE8_REAL_SMALL_MODEL_PATH because it does not point to an existing directory: /tmp/missing-model",
        ),
    )
    executor = _FakeExecutor(
        [
            *_successful_acceptance_responses(tmp_path)[:7],
            {"adapters": [], "experiment_groups": []},
            *_successful_acceptance_responses(tmp_path)[7:],
        ]
    )

    _, bundle = phase8_acceptance_bundle.run_acceptance_bundle(config, executor=executor)

    assert executor.calls[0] == [
        "melix",
        "model",
        "hub",
        "download",
        "--repo-id",
        "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "--json",
    ]
    assert bundle["model"]["source_kind"] == "hub_repo"
    assert bundle["model"]["source_resolution_mode"] == "env_invalid_hub_fallback"
    assert bundle["model"]["warnings"] == [
        "Ignored MELIX_PHASE8_REAL_SMALL_MODEL_PATH because it does not point to an existing directory: /tmp/missing-model"
    ]


def test_run_acceptance_bundle_real_small_model_records_real_runtime_metadata_and_explicit_publish_skip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    index_path = tmp_path / ".runtime" / "model-ops" / "train_lora" / "lora-experiments.index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_experiment_index.v1",
                "groups": [
                    {
                        "group_id": "phase8-real-small-model",
                        "run_count": 1,
                        "latest_preset_title": "Debug Fast",
                        "recommended_manifest_path": str(
                            tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
                        ),
                    }
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

    config = phase8_acceptance_bundle.AcceptanceBundleConfig(
        repo_root=tmp_path,
        melix_home=tmp_path / "melix-home",
        model_id="melix-dev-qwen-local",
        training_fixture="services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
        bench_suites=["smoke"],
        matrix_suites=["smoke"],
        evaluation_suites=["mmlu"],
        evaluation_dataset="mmlu.dev.v1",
        server_session_id="server-session-1",
        local_model_path=str(tmp_path / "fixture-model"),
        live=False,
        timestamp="2026-04-09T120000Z",
        json_output=True,
        execution_profile="real_small_model",
        acceptance_tier="cli_real_small_model",
        runtime_backend_mode="python_auto",
        activation_mode="adapter_backed_runtime",
        training_preset_id="debug_fast",
        training_max_steps=2,
        experiment_group_id="phase8-real-small-model",
        publish_mode="disabled",
        publish_target_repo="",
        source_resolution_mode="explicit_local_path",
    )
    executor = _FakeExecutor(
        [
            *_successful_acceptance_responses(
                tmp_path,
                source_kind="local_path",
                source_locator=str(tmp_path / "fixture-model"),
                model_id="melix-dev-qwen-local",
            )[:7],
            {
                "adapters": [
                    {
                        "adapter_name": "phase8-acceptance",
                        "status": "activated",
                        "activation_status": "activated",
                        "output_path": str(
                            tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
                        ),
                    }
                ],
                "experiment_groups": [
                    {
                        "group_id": "phase8-real-small-model",
                        "run_count": 1,
                        "latest_preset_title": "Debug Fast",
                        "best_loss": 0.33,
                        "recommended_manifest_path": str(
                            tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
                        ),
                    }
                ],
            },
            *_successful_acceptance_responses(
                tmp_path,
                source_kind="local_path",
                source_locator=str(tmp_path / "fixture-model"),
                model_id="melix-dev-qwen-local",
            )[7:],
        ]
    )

    _, bundle = phase8_acceptance_bundle.run_acceptance_bundle(config, executor=executor)

    assert bundle["execution_profile"] == "real_small_model"
    assert bundle["acceptance_tier"] == "cli_real_small_model"
    assert bundle["runtime"]["backend_mode"] == "python_auto"
    assert bundle["runtime"]["activation_mode"] == "adapter_backed_runtime"
    assert bundle["training"]["preset_id"] == "debug_fast"
    assert bundle["training"]["max_steps"] == 2
    assert bundle["training"]["experiment_group_id"] == "phase8-real-small-model"
    assert bundle["experiment"]["index_path"] == str(index_path)
    assert bundle["experiment"]["index_exists"] is True
    assert bundle["registry"]["experiment_groups"][0]["group_id"] == "phase8-real-small-model"
    assert bundle["model"]["source_resolution_mode"] == "explicit_local_path"
    assert bundle["publish"]["mode"] == "disabled"
    assert bundle["publish"]["status"] == "disabled"
    assert bundle["publish"]["skip_reason"] == "publish_disabled"
    assert not any(call[1:2] == ["upload"] for call in executor.calls)
    assert executor.calls[5] == [
        "melix",
        "lora",
        "train",
        "--model-id",
        "melix-dev-qwen-local",
        "--dataset-uri",
        "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
        "--adapter-name",
        "phase8-acceptance",
        "--preset",
        "debug_fast",
        "--experiment-group",
        "phase8-real-small-model",
        "--max-steps",
        "2",
        "--json",
    ]
    assert executor.calls[6] == [
        "melix",
        "lora",
        "activate",
        "--model-id",
        "melix-dev-qwen-local",
        "--adapter-path",
        str(tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"),
        "--alias",
        "phase8-acceptance-derived",
        "--activation-mode",
        "adapter_backed_runtime",
        "--json",
    ]
    assert executor.calls[7] == [
        "melix",
        "lora",
        "list",
        "--model-id",
        "melix-dev-qwen-local",
        "--json",
    ]


def test_main_prints_json_bundle_when_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = phase8_acceptance_bundle.AcceptanceBundleConfig(
        repo_root=tmp_path,
        melix_home=tmp_path / "melix-home",
        model_id="melix-dev-qwen-local",
        training_fixture="fixture",
        bench_suites=["smoke"],
        matrix_suites=["smoke"],
        evaluation_suites=["mmlu"],
        evaluation_dataset="mmlu.dev.v1",
        server_session_id="server-session-1",
        local_model_path=str(tmp_path / "fixture-model"),
        live=False,
        timestamp="2026-04-09T120000Z",
        json_output=True,
    )
    bundle_path = tmp_path / "bundle.json"

    class _StubExecutor:
        def __init__(self, *, repo_root: Path, environment: dict[str, str]) -> None:
            self.repo_root = repo_root
            self.environment = environment

    monkeypatch.setattr(phase8_acceptance_bundle, "parse_args", lambda argv=None: config)
    monkeypatch.setattr(phase8_acceptance_bundle, "CLIJSONExecutor", _StubExecutor)
    monkeypatch.setattr(
        phase8_acceptance_bundle,
        "run_acceptance_bundle",
        lambda parsed_config, executor: (bundle_path, {"status": "ok"}),
    )

    assert phase8_acceptance_bundle.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"bundle": {"status": "ok"}, "bundle_path": str(bundle_path)}


def test_main_prints_bundle_path_when_json_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = phase8_acceptance_bundle.AcceptanceBundleConfig(
        repo_root=tmp_path,
        melix_home=tmp_path / "melix-home",
        model_id="melix-dev-qwen-local",
        training_fixture="fixture",
        bench_suites=["smoke"],
        matrix_suites=["smoke"],
        evaluation_suites=["mmlu"],
        evaluation_dataset="mmlu.dev.v1",
        server_session_id="server-session-1",
        local_model_path=str(tmp_path / "fixture-model"),
        live=False,
        timestamp="2026-04-09T120000Z",
        json_output=False,
    )
    bundle_path = tmp_path / "bundle.json"

    class _StubExecutor:
        def __init__(self, *, repo_root: Path, environment: dict[str, str]) -> None:
            self.repo_root = repo_root
            self.environment = environment

    monkeypatch.setattr(phase8_acceptance_bundle, "parse_args", lambda argv=None: config)
    monkeypatch.setattr(phase8_acceptance_bundle, "CLIJSONExecutor", _StubExecutor)
    monkeypatch.setattr(
        phase8_acceptance_bundle,
        "run_acceptance_bundle",
        lambda parsed_config, executor: (bundle_path, {"status": "ok"}),
    )

    assert phase8_acceptance_bundle.main([]) == 0
    assert capsys.readouterr().out.strip() == str(bundle_path)


def test_main_prints_errors_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = phase8_acceptance_bundle.AcceptanceBundleConfig(
        repo_root=tmp_path,
        melix_home=tmp_path / "melix-home",
        model_id="melix-dev-qwen-local",
        training_fixture="fixture",
        bench_suites=["smoke"],
        matrix_suites=["smoke"],
        evaluation_suites=["mmlu"],
        evaluation_dataset="mmlu.dev.v1",
        server_session_id="server-session-1",
        local_model_path=str(tmp_path / "fixture-model"),
        live=False,
        timestamp="2026-04-09T120000Z",
        json_output=False,
    )

    class _StubExecutor:
        def __init__(self, *, repo_root: Path, environment: dict[str, str]) -> None:
            self.repo_root = repo_root
            self.environment = environment

    monkeypatch.setattr(phase8_acceptance_bundle, "parse_args", lambda argv=None: config)
    monkeypatch.setattr(phase8_acceptance_bundle, "CLIJSONExecutor", _StubExecutor)
    monkeypatch.setattr(
        phase8_acceptance_bundle,
        "run_acceptance_bundle",
        lambda parsed_config, executor: (_ for _ in ()).throw(
            phase8_acceptance_bundle.AcceptanceBundleError("bundle failed")
        ),
    )

    assert phase8_acceptance_bundle.main([]) == 1
    assert "bundle failed" in capsys.readouterr().err


def test_maybe_publish_adapter_handles_skip_required_and_success_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter_manifest_path = tmp_path / "adapter.json"
    adapter_manifest_path.write_text("{}", encoding="utf-8")
    cli_receipts_root = tmp_path / "cli"

    missing_target_config = replace(
        _bundle_config(tmp_path, live=False),
        publish_mode="auto",
        publish_target_repo="",
    )
    result = phase8_acceptance_bundle._maybe_publish_adapter(
        config=missing_target_config,
        executor=_FakeExecutor([]),
        model_id="melix-dev-qwen-local",
        adapter_manifest_path=adapter_manifest_path,
        cli_receipts_root=cli_receipts_root,
    )
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "publish_target_repo_missing"

    required_missing_target_config = replace(missing_target_config, publish_mode="required")
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="publish target repo is required"):
        phase8_acceptance_bundle._maybe_publish_adapter(
            config=required_missing_target_config,
            executor=_FakeExecutor([]),
            model_id="melix-dev-qwen-local",
            adapter_manifest_path=adapter_manifest_path,
            cli_receipts_root=cli_receipts_root,
        )

    for key in phase8_acceptance_bundle._HF_TOKEN_KEYS:
        monkeypatch.delenv(key, raising=False)
    missing_token_config = replace(
        _bundle_config(tmp_path, live=False),
        publish_mode="auto",
        publish_target_repo="chenyu/adapter",
    )
    result = phase8_acceptance_bundle._maybe_publish_adapter(
        config=missing_token_config,
        executor=_FakeExecutor([]),
        model_id="melix-dev-qwen-local",
        adapter_manifest_path=adapter_manifest_path,
        cli_receipts_root=cli_receipts_root,
    )
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "missing_hf_token"

    required_missing_token_config = replace(missing_token_config, publish_mode="required")
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="Hugging Face token is required"):
        phase8_acceptance_bundle._maybe_publish_adapter(
            config=required_missing_token_config,
            executor=_FakeExecutor([]),
            model_id="melix-dev-qwen-local",
            adapter_manifest_path=adapter_manifest_path,
            cli_receipts_root=cli_receipts_root,
        )

    monkeypatch.setenv("HF_TOKEN", "token")
    executor = _FakeExecutor([{"status": "published", "url": "https://huggingface.co/chenyu/adapter"}])
    result = phase8_acceptance_bundle._maybe_publish_adapter(
        config=missing_token_config,
        executor=executor,
        model_id="melix-dev-qwen-local",
        adapter_manifest_path=adapter_manifest_path,
        cli_receipts_root=cli_receipts_root,
    )
    assert result["status"] == "published"
    assert result["skip_reason"] == ""
    assert (cli_receipts_root / "17-publish.json").is_file()
    assert executor.calls == [
        [
            "melix",
            "upload",
            "--model-id",
            "melix-dev-qwen-local",
            "--artifact-path",
            str(adapter_manifest_path),
            "--artifact-kind",
            "adapter",
            "--target-repo",
            "chenyu/adapter",
            "--json",
        ]
    ]


def test_has_publish_token_checks_supported_environment_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in phase8_acceptance_bundle._HF_TOKEN_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert phase8_acceptance_bundle._has_publish_token() is False

    monkeypatch.setenv("HUGGING_FACE_HUB_TOKEN", "token")
    assert phase8_acceptance_bundle._has_publish_token() is True


def test_helper_functions_cover_success_and_error_paths(tmp_path: Path) -> None:
    artifact_path = tmp_path / "job" / "train_lora.adapter.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("{}", encoding="utf-8")
    export_path = tmp_path / "exports" / "summary.csv"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text("ok\n", encoding="utf-8")

    assert phase8_acceptance_bundle._adapter_manifest_path({"artifact_path": str(artifact_path)}) == artifact_path
    assert phase8_acceptance_bundle._adapter_manifest_path(
        {"weights_path": str(tmp_path / "job" / "adapter" / "adapters.safetensors")}
    ) == tmp_path / "job" / "train_lora.adapter.json"
    assert phase8_acceptance_bundle._default_repo_root() == Path(phase8_acceptance_bundle.__file__).resolve().parents[1]
    assert phase8_acceptance_bundle._expect_list([{"job": {}}], context="eval") == [{"job": {}}]
    assert phase8_acceptance_bundle._expect_mapping({"ok": True}, context="mapping") == {"ok": True}
    assert phase8_acceptance_bundle._job_id_from_report_path(str(tmp_path / "bench-1" / "report.md")) == "bench-1"
    assert phase8_acceptance_bundle._repeated_flag("--suite", ["smoke", "latency"]) == [
        "--suite",
        "smoke",
        "--suite",
        "latency",
    ]
    assert phase8_acceptance_bundle._require_existing_export(
        {"output_path": str(export_path)},
        "output_path",
        context="export",
    ) == export_path
    assert phase8_acceptance_bundle._require_string({"job_id": "eval-1"}, "job_id", context="job") == "eval-1"
    assert phase8_acceptance_bundle._resolve_model_source(
        execution_profile="deterministic_import",
        model_id="melix-dev-text",
        local_model_path="",
        live=True,
    ) == ("melix-dev-text", True, "", "explicit_live_hub", ())
    assert phase8_acceptance_bundle._resolve_model_source(
        execution_profile="deterministic_import",
        model_id="melix-dev-text",
        local_model_path=str(tmp_path / "model"),
        live=False,
    ) == ("melix-dev-text", False, str(tmp_path / "model"), "explicit_local_path", ())
    assert phase8_acceptance_bundle._default_source_resolution_mode(
        replace(_bundle_config(tmp_path, live=True), live=False, local_model_path="")
    ) == ""
    assert phase8_acceptance_bundle._evaluation_scoring_mode([]) == "normalized_exact_match"
    assert phase8_acceptance_bundle._cli_step_label(["single"]) == "single"
    assert phase8_acceptance_bundle._cli_step_label([]) == "melix"
    assert phase8_acceptance_bundle._trim_diagnostic_text("abc", limit=10) == "abc"
    assert phase8_acceptance_bundle._trim_diagnostic_text("0123456789", limit=4) == "6789"

    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="artifact_path or weights_path"):
        phase8_acceptance_bundle._adapter_manifest_path({})
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="--model-id is required"):
        phase8_acceptance_bundle._resolve_model_source(
            execution_profile="deterministic_import",
            model_id="",
            local_model_path="",
            live=False,
        )
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="did not return a JSON array"):
        phase8_acceptance_bundle._expect_list({"job": {}}, context="eval")
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="payload at index 0 was not a JSON object"):
        phase8_acceptance_bundle._expect_list(["bad"], context="eval")
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="did not return a JSON object"):
        phase8_acceptance_bundle._expect_mapping([], context="mapping")
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="job directory"):
        phase8_acceptance_bundle._job_id_from_report_path("/")
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="Missing required export artifact"):
        phase8_acceptance_bundle._require_existing_export(
            {"output_path": str(tmp_path / "exports" / "missing.csv")},
            "output_path",
            context="export",
        )
    with pytest.raises(phase8_acceptance_bundle.AcceptanceBundleError, match="did not include job_id"):
        phase8_acceptance_bundle._require_string({}, "job_id", context="job")


def test_run_acceptance_bundle_captures_lora_capability_evidence(tmp_path: Path) -> None:
    fixture_model = tmp_path / "fixture-model"
    fixture_model.mkdir(parents=True)
    executor = _FakeExecutor(
        _successful_acceptance_responses(
            tmp_path,
            source_kind="local_path",
            source_locator=str(fixture_model),
            model_id="melix-dev-qwen-local",
        )
    )

    _, bundle = phase8_acceptance_bundle.run_acceptance_bundle(
        _bundle_config(tmp_path, live=False),
        executor=executor,
    )

    assert "lora_capability" in bundle
    lora_cap = bundle["lora_capability"]

    adapter_artifact = lora_cap["adapter_artifact"]
    assert adapter_artifact["job_id"] == "model-ops-0001"
    assert "weights_path" in adapter_artifact
    assert "adapter_config_path" in adapter_artifact

    activation_artifact = lora_cap["activation_artifact"]
    assert activation_artifact["derived_model_id"] == "melix-dev-qwen-local-lora-phase8"
    assert activation_artifact["derived_model_alias"] == "phase8-acceptance-derived"
    assert "manifest_path" in activation_artifact

    compare_artifact = lora_cap["compare_artifact"]
    assert compare_artifact["evaluation_job_id"] == "eval-1"
    assert compare_artifact["model_id"] == "melix-dev-qwen-local-lora-phase8"
    assert compare_artifact["suites"] == ["mmlu"]

    publish_artifact = lora_cap["publish_artifact"]
    assert "mode" in publish_artifact
    assert "status" in publish_artifact
    assert "target_repo" in publish_artifact

    assert lora_cap["runtime_mode"] == "fused_derived_model"
