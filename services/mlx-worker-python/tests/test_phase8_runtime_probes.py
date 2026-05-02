from __future__ import annotations

import io
import inspect
import json
import runpy
import sys
import urllib.error
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import phase8_metrics_report
import phase8_runtime_probes


def test_wait_for_metrics_returns_requested_values(tmp_path: Path) -> None:
    metrics_path = tmp_path / "control-plane-metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "updated_at_unix_ms": 1,
                "values": {
                    "control_plane.http_ready_ms": 12.5,
                    "control_plane.background_preload_ms": 44.0,
                },
            }
        ),
        encoding="utf-8",
    )

    metrics = phase8_runtime_probes.wait_for_metrics(
        metrics_path,
        [
            "control_plane.http_ready_ms",
            "control_plane.background_preload_ms",
        ],
        timeout_seconds=0.01,
    )

    assert metrics == {
        "control_plane.http_ready_ms": 12.5,
        "control_plane.background_preload_ms": 44.0,
    }


def test_wait_for_metrics_times_out_when_required_keys_never_appear(tmp_path: Path) -> None:
    metrics_path = tmp_path / "control-plane-metrics.json"
    metrics_path.write_text(
        json.dumps({"updated_at_unix_ms": 1, "values": {"control_plane.http_ready_ms": 12.5}}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Timed out waiting for metrics"):
        phase8_runtime_probes.wait_for_metrics(
            metrics_path,
            ["control_plane.background_preload_ms"],
            timeout_seconds=0.01,
        )


def test_wait_for_metric_minimum_returns_when_threshold_is_reached(tmp_path: Path) -> None:
    metrics_path = tmp_path / "swift-text-worker-metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "updated_at_unix_ms": 1,
                "values": {
                    "swift_text.prefill_memory_guard_rejection_count": 1.0,
                },
            }
        ),
        encoding="utf-8",
    )

    value = phase8_runtime_probes.wait_for_metric_minimum(
        metrics_path,
        "swift_text.prefill_memory_guard_rejection_count",
        minimum=1.0,
        timeout_seconds=0.01,
    )

    assert value == 1.0


def test_wait_for_metric_minimum_times_out_when_threshold_never_arrives(tmp_path: Path) -> None:
    metrics_path = tmp_path / "swift-text-worker-metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "updated_at_unix_ms": 1,
                "values": {
                    "swift_text.prefill_memory_guard_rejection_count": 0.0,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Timed out waiting for metric"):
        phase8_runtime_probes.wait_for_metric_minimum(
            metrics_path,
            "swift_text.prefill_memory_guard_rejection_count",
            minimum=1.0,
            timeout_seconds=0.01,
        )


def test_wait_for_metric_minimum_ignores_transient_decode_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "swift-text-worker-metrics.json"
    metrics_path.write_text("{}", encoding="utf-8")

    class FlakyReader:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, path: Path) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise json.JSONDecodeError("bad", "{}", 0)
            return {
                "values": {
                    "swift_text.prefill_memory_guard_rejection_count": 1.0,
                }
            }

    monkeypatch.setattr(phase8_runtime_probes, "read_metrics_export", FlakyReader())
    ticks = iter([0.0, 0.04, 0.08, 0.08])

    assert phase8_runtime_probes.wait_for_metric_minimum(
        metrics_path,
        "swift_text.prefill_memory_guard_rejection_count",
        minimum=1.0,
        timeout_seconds=0.1,
        clock=lambda: next(ticks),
        sleep_fn=lambda _: None,
    ) == 1.0


def test_measure_cold_boot_to_ready_reads_bootstrap_metrics_from_the_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root
            self.control_plane_metrics_path = tmp_path / "control-plane-metrics.json"
            self.swift_text_worker_metrics_path = tmp_path / "swift-text-worker-metrics.json"
            self.python_worker_metrics_path = tmp_path / "python-worker-metrics.json"
            self.startup_timings = {
                "swift_text_worker_ready_ms": 4100.0,
                "python_worker_ready_ms": 5200.0,
                "control_plane_spawn_to_ready_ms": 1100.0,
            }
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True
            self.control_plane_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "control_plane.http_ready_ms": 18.5,
                            "control_plane.background_preload_ms": 640.0,
                            "control_plane.background_preload_success": 1.0,
                            "control_plane.text_first_load_ms": 125.0,
                            "control_plane.text_first_load_estimated_resident_bytes": 4096.0,
                            "control_plane.text_first_load_resident_bytes": 8192.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.swift_text_worker_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "swift_text.spawn_to_bootstrap_ms": 4900.0,
                            "swift_text.registry_init_ms": 6.0,
                            "swift_text.services_init_ms": 4.0,
                            "swift_text.server_construct_ms": 3.0,
                            "swift_text.bootstrap_ms": 15.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.python_worker_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "python_worker.spawn_to_bootstrap_ms": 5000.0,
                            "python_worker.arg_parse_ms": 1.0,
                            "python_worker.registry_init_ms": 7.0,
                            "python_worker.server_build_ms": 5.0,
                            "python_worker.server_start_ms": 2.0,
                            "python_worker.bootstrap_ms": 16.0,
                        },
                    }
                ),
                encoding="utf-8",
            )

        def chat_url(self) -> str:
            return "http://127.0.0.1:11434/v1/chat/completions"

        def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]"},
    )

    report = phase8_runtime_probes.measure_cold_boot_to_ready(tmp_path)

    assert report["cold_boot_to_ready_ms"] >= 0
    assert report["swift_text_worker_ready_ms"] == 4100.0
    assert report["python_worker_ready_ms"] == 5200.0
    assert report["control_plane_spawn_to_ready_ms"] == 1100.0
    assert report["swift_text_worker_spawn_to_bootstrap_ms"] == 4900.0
    assert report["swift_text_worker_registry_init_ms"] == 6.0
    assert report["swift_text_worker_services_init_ms"] == 4.0
    assert report["swift_text_worker_server_construct_ms"] == 3.0
    assert report["swift_text_worker_bootstrap_ms"] == 15.0
    assert report["python_worker_spawn_to_bootstrap_ms"] == 5000.0
    assert report["python_worker_arg_parse_ms"] == 1.0
    assert report["python_worker_registry_init_ms"] == 7.0
    assert report["python_worker_server_build_ms"] == 5.0
    assert report["python_worker_server_start_ms"] == 2.0
    assert report["python_worker_bootstrap_ms"] == 16.0
    assert report["http_ready_ms"] == 18.5
    assert report["background_preload_ms"] == 640.0
    assert report["background_preload_success"] == 1.0
    assert report["first_text_model_warm_ms"] == 125.0
    assert report["text_model_load_estimated_resident_bytes"] == 4096.0
    assert report["text_model_load_resident_bytes"] == 8192.0


def test_collect_runtime_core_evidence_reports_multimodel_and_guard_signals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        environments: list[dict[str, str]] = []

        def __init__(
            self,
            repo_root: Path,
            *,
            environment_overrides: dict[str, str] | None = None,
            **_: object,
        ) -> None:
            self.repo_root = repo_root
            self.environment_overrides = dict(environment_overrides or {})
            self.swift_text_worker_metrics_path = tmp_path / f"swift-{len(FakeStack.environments)}.json"
            self.started = False
            self.stopped = False
            FakeStack.environments.append(self.environment_overrides)

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

        def chat_url(self) -> str:
            return "http://127.0.0.1:11434/v1/chat/completions"

        def models_url(self) -> str:
            return "http://127.0.0.1:11434/v1/models"

        def wait_for_models(self, model_ids: list[str], *, timeout_seconds: float = 120) -> None:
            assert model_ids == ["melix-dev-text", "melix-dev-embed", "melix-dev-rerank"]
            assert timeout_seconds == 30

        @property
        def http_port(self) -> int:
            return 11434

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]\n\n"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_post_json",
        lambda url, payload: (
            200,
            {"model": payload["model"], "data": [{"index": 1}, {"index": 0}]},
        ),
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_read_model_states",
        lambda url: {
            "melix-dev-text": "warm",
            "melix-dev-embed": "warm",
            "melix-dev-rerank": "warm",
        },
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_run_prefill_memory_guard_probe",
        lambda stack: {
            "ok": False,
            "error_code": "prefill_memory_guard_exceeded",
            "error_message": "Projected prefill memory would exceed the process budget.",
        },
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "wait_for_metric_minimum",
        lambda *args, **kwargs: 1.0,
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "wait_for_metrics",
        lambda *args, **kwargs: {
            # 16 tokens * 2048 bytes/token + 16384 bytes headroom = 49152 bytes,
            # which is intentionally above the 40960-byte probe budget.
            "swift_text.prefill_guard_last_prompt_tokens": 16.0,
            "swift_text.prefill_guard_last_required_bytes": 49152.0,
            "swift_text.prefill_guard_last_budget_bytes": 40960.0,
        },
    )

    report = phase8_runtime_probes.collect_runtime_core_evidence(tmp_path)

    assert report["multi_model_ready_count"] == 3
    assert report["multi_model_request_success_rate"] == 100.0
    assert report["multi_model_ready_model_ids"] == [
        "melix-dev-text",
        "melix-dev-embed",
        "melix-dev-rerank",
    ]
    assert report["prefill_memory_guard_rejection_count"] == 1.0
    assert report["prefill_memory_guard_success_rate"] == 100.0
    assert report["prefill_memory_guard_last_prompt_tokens"] == 16.0
    assert report["prefill_memory_guard_last_required_bytes"] == 49152.0
    assert report["prefill_memory_guard_last_budget_bytes"] == 40960.0
    assert FakeStack.environments[1]["MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES"] == "40960"
    assert FakeStack.environments[1]["MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES"] == "16384"


def test_collect_multi_model_coexistence_evidence_raises_on_text_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.http_port = 11434

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 503, "body": "worker unavailable"},
    )

    with pytest.raises(SystemExit, match="runtime-core text smoke failed"):
        phase8_runtime_probes._collect_multi_model_coexistence_evidence(tmp_path)


def test_collect_multi_model_coexistence_evidence_raises_on_embedding_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.http_port = 11434

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_post_json",
        lambda url, payload: (500, "embed failed"),
    )

    with pytest.raises(SystemExit, match="runtime-core embedding smoke failed"):
        phase8_runtime_probes._collect_multi_model_coexistence_evidence(tmp_path)


def test_collect_multi_model_coexistence_evidence_raises_on_rerank_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.http_port = 11434

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    post_results = iter(
        [
            (200, {"data": [{"index": 0}]}),
            (500, "rerank failed"),
        ]
    )

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_post_json",
        lambda url, payload: next(post_results),
    )

    with pytest.raises(SystemExit, match="runtime-core rerank smoke failed"):
        phase8_runtime_probes._collect_multi_model_coexistence_evidence(tmp_path)


def test_collect_prefill_memory_guard_evidence_raises_when_probe_does_not_reject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path, **_: object) -> None:
            self.swift_text_worker_metrics_path = tmp_path / "swift-text-worker-metrics.json"

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_run_prefill_memory_guard_probe",
        lambda stack: {"ok": True, "error_code": "", "error_message": ""},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "wait_for_metric_minimum",
        lambda *args, **kwargs: 1.0,
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "wait_for_metrics",
        lambda *args, **kwargs: {
            # Keep this aligned with the successful probe fixture: 16 tokens plus
            # 16384 bytes of headroom must exceed the 40960-byte budget.
            "swift_text.prefill_guard_last_prompt_tokens": 16.0,
            "swift_text.prefill_guard_last_required_bytes": 49152.0,
            "swift_text.prefill_guard_last_budget_bytes": 40960.0,
        },
    )

    with pytest.raises(SystemExit, match="runtime-core prefill guard smoke failed"):
        phase8_runtime_probes._collect_prefill_memory_guard_evidence(tmp_path)


def test_measure_cold_boot_to_ready_raises_when_first_text_warmup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane-metrics.json"
            self.swift_text_worker_metrics_path = tmp_path / "swift-text-worker-metrics.json"
            self.python_worker_metrics_path = tmp_path / "python-worker-metrics.json"
            self.startup_timings = {}

        def start(self) -> None:
            self.swift_text_worker_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "swift_text.spawn_to_bootstrap_ms": 4900.0,
                            "swift_text.registry_init_ms": 6.0,
                            "swift_text.services_init_ms": 4.0,
                            "swift_text.server_construct_ms": 3.0,
                            "swift_text.bootstrap_ms": 15.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.python_worker_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "python_worker.spawn_to_bootstrap_ms": 5000.0,
                            "python_worker.arg_parse_ms": 1.0,
                            "python_worker.registry_init_ms": 7.0,
                            "python_worker.server_build_ms": 5.0,
                            "python_worker.server_start_ms": 2.0,
                            "python_worker.bootstrap_ms": 16.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.control_plane_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "control_plane.http_ready_ms": 18.5,
                            "control_plane.background_preload_ms": 640.0,
                            "control_plane.background_preload_success": 1.0,
                        },
                    }
                ),
                encoding="utf-8",
            )

        def stop(self) -> None:
            return None

        def chat_url(self) -> str:
            return "http://127.0.0.1:11434/v1/chat/completions"

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 503, "body": "worker unavailable"},
    )

    with pytest.raises(SystemExit, match="first text warmup smoke failed"):
        phase8_runtime_probes.measure_cold_boot_to_ready(tmp_path)


def test_collect_restart_recovery_evidence_splits_restart_and_restore_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        start_count = 0

        def __init__(self, repo_root: Path, swift_cache_root: Path | None = None) -> None:
            self.repo_root = repo_root
            self.swift_cache_root = swift_cache_root
            self.control_plane_metrics_path = tmp_path / f"control-plane-{FakeStack.start_count}.json"
            self.swift_socket_path = tmp_path / "swift-text-worker.sock"
            self.startup_timings = {
                "swift_text_worker_ready_ms": 4200.0,
                "python_worker_ready_ms": 5100.0,
                "control_plane_spawn_to_ready_ms": 1292.3,
            }

        def start(self) -> None:
            FakeStack.start_count += 1
            self.control_plane_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "control_plane.http_ready_ms": 19.0,
                            "control_plane.background_preload_ms": 680.0,
                            "control_plane.background_preload_success": 1.0,
                        },
                    }
                ),
                encoding="utf-8",
            )

        def stop(self) -> None:
            pass

    perf_values = iter([100.0, 100.45, 100.45, 100.58, 100.58])

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(phase8_runtime_probes.time, "perf_counter", lambda: next(perf_values))
    monkeypatch.setattr(
        phase8_runtime_probes,
        "get_cache_stats",
        lambda socket_path: SimpleNamespace(
            snapshot=SimpleNamespace(snapshots=[SimpleNamespace(snapshot_id="snap-001")])
        ),
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "wait_for_metrics",
        lambda metrics_path, keys: {
            "control_plane.http_ready_ms": 19.0,
            "control_plane.background_preload_ms": 680.0,
            "control_plane.background_preload_success": 1.0,
        },
    )

    report = phase8_runtime_probes.collect_restart_recovery_evidence(tmp_path)

    assert report["restart_to_ready_ms"] == 450.0
    assert report["restart_swift_text_worker_ready_ms"] == 4200.0
    assert report["restart_python_worker_ready_ms"] == 5100.0
    assert report["restart_control_plane_spawn_to_ready_ms"] == 1292.3
    assert report["snapshot_restore_ms"] == 130.0
    assert report["restart_recovery_ms"] == 580.0
    assert report["restart_recovery_success_rate"] == 100.0
    assert report["http_ready_ms"] == 19.0
    assert report["background_preload_ms"] == 680.0
    assert report["background_preload_success"] == 1.0


def test_collect_restart_recovery_evidence_raises_when_initial_smoke_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path, swift_cache_root: Path | None = None) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane.json"
            self.swift_socket_path = tmp_path / "swift-text-worker.sock"
            self.startup_timings = {}

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

        def chat_url(self) -> str:
            return "http://127.0.0.1:11434/v1/chat/completions"

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 500, "body": "boom"},
    )

    with pytest.raises(SystemExit, match="initial recovery smoke failed"):
        phase8_runtime_probes.collect_restart_recovery_evidence(tmp_path)


def test_collect_restart_recovery_evidence_raises_when_snapshot_id_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        start_count = 0

        def __init__(self, repo_root: Path, swift_cache_root: Path | None = None) -> None:
            self.control_plane_metrics_path = tmp_path / f"control-plane-{FakeStack.start_count}.json"
            self.swift_socket_path = tmp_path / "swift-text-worker.sock"
            self.startup_timings = {}

        def start(self) -> None:
            FakeStack.start_count += 1

        def stop(self) -> None:
            return None

        def chat_url(self) -> str:
            return "http://127.0.0.1:11434/v1/chat/completions"

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 200, "body": "data: [DONE]"},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "get_cache_stats",
        lambda socket_path: SimpleNamespace(
            snapshot=SimpleNamespace(snapshots=[SimpleNamespace(snapshot_id="")])
        ),
    )

    with pytest.raises(SystemExit, match="recovery smoke did not produce a boundary snapshot"):
        phase8_runtime_probes.collect_restart_recovery_evidence(tmp_path)


def test_collect_cache_recovery_benchmark_evidence_combines_restart_hot_cold_and_partial_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase8_runtime_probes,
        "collect_restart_recovery_evidence",
        lambda repo_root: {
            "restart_to_ready_ms": 450.0,
            "snapshot_restore_ms": 130.0,
            "restart_recovery_ms": 580.0,
            "restart_recovery_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_collect_hot_tier_recovery_evidence",
        lambda repo_root: {
            "followup_ttft_delta_ms": 12.5,
            "prefix_affinity_hit_rate": 100.0,
            "warm_route_preference_rate": 66.67,
            "restored_route_rate": 66.67,
        },
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_collect_cold_tier_recovery_evidence",
        lambda repo_root: {"l2_hit_rate": 100.0},
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "_collect_partial_restore_recovery_evidence",
        lambda repo_root: {
            "walk_back_count": 1.0,
            "restored_tokens": 18.0,
            "total_tokens": 22.0,
            "restore_ratio_pct": 81.82,
        },
    )

    report = phase8_runtime_probes.collect_cache_recovery_benchmark_evidence(tmp_path)

    assert report["restart"]["restart_recovery_ms"] == 580.0
    assert report["hot_tier"]["followup_ttft_delta_ms"] == 12.5
    assert report["cold_tier"]["l2_hit_rate"] == 100.0
    assert report["partial_restore"]["restore_ratio_pct"] == 81.82
    assert report["metrics"]["bench.recovery.restart_to_ready_ms"] == 450.0
    assert report["metrics"]["bench.recovery.hot_followup_ttft_delta_ms"] == 12.5
    assert report["metrics"]["bench.recovery.cold_l2_hit_rate"] == 100.0
    assert report["metrics"]["bench.recovery.partial_restore_ratio_pct"] == 81.82


def test_collect_hot_tier_recovery_evidence_reports_followup_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane.json"

        def start(self) -> None:
            self.control_plane_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "session.followup_ttft_delta_ms": 15.0,
                            "scheduler.prefix_affinity_hit_rate": 100.0,
                            "scheduler.warm_route_preference_rate": 66.67,
                            "scheduler.restored_route_rate": 66.67,
                        },
                    }
                ),
                encoding="utf-8",
            )

        def stop(self) -> None:
            return None

    calls = iter(
        [
            {"status": 200, "request_id": "req-cold", "ttft_ms": 27.5},
            {"status": 200, "request_id": "req-warm", "ttft_ms": 12.5},
        ]
    )
    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: next(calls),
    )

    report = phase8_runtime_probes._collect_hot_tier_recovery_evidence(tmp_path)

    assert report == {
        "cold_ttft_ms": 27.5,
        "warm_ttft_ms": 12.5,
        "followup_ttft_delta_ms": 15.0,
        "prefix_affinity_hit_rate": 100.0,
        "warm_route_preference_rate": 66.67,
        "restored_route_rate": 66.67,
    }


def test_collect_hot_tier_recovery_evidence_raises_when_cold_baseline_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane.json"

        def start(self) -> None:
            self.control_plane_metrics_path.write_text(
                json.dumps({"updated_at_unix_ms": 1, "values": {}}),
                encoding="utf-8",
            )

        def stop(self) -> None:
            return None

    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: {"status": 503, "body": "worker unavailable"},
    )

    with pytest.raises(SystemExit, match="hot-tier cold baseline failed"):
        phase8_runtime_probes._collect_hot_tier_recovery_evidence(tmp_path)


def test_collect_cold_tier_recovery_evidence_reports_l2_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path, swift_cache_root: Path | None = None) -> None:
            self.swift_cache_root = swift_cache_root
            self.swift_socket_path = tmp_path / "swift.sock"
            self.swift_text_worker_metrics_path = tmp_path / "swift-metrics.json"

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    calls = iter(
        [
            {"status": 200, "body": "data: [DONE]"},
            {"status": 200, "body": "data: [DONE]"},
        ]
    )
    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: next(calls),
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "get_cache_stats",
        lambda socket_path: SimpleNamespace(stats=SimpleNamespace(l2_hit_rate=1.0)),
    )
    monkeypatch.setattr(
        phase8_runtime_probes,
        "read_metrics_export",
        lambda path: {
            "values": {
                "swift_text.cache_l2_hit_rate": 100.0,
                "swift_text.cache_l2_writeback_queue_depth": 0.0,
                "swift_text.cache_l2_restore_queue_depth": 0.0,
            }
        },
    )

    report = phase8_runtime_probes._collect_cold_tier_recovery_evidence(tmp_path)

    assert report == {
        "l2_hit_rate": 100.0,
        "l2_writeback_queue_depth": 0.0,
        "l2_restore_queue_depth": 0.0,
    }


def test_collect_cold_tier_recovery_evidence_raises_when_restore_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path, swift_cache_root: Path | None = None) -> None:
            self.swift_cache_root = swift_cache_root
            self.swift_socket_path = tmp_path / "swift.sock"
            self.swift_text_worker_metrics_path = tmp_path / "swift-metrics.json"

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    calls = iter(
        [
            {"status": 200, "body": "data: [DONE]"},
            {"status": 500, "body": "restore failed"},
        ]
    )
    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: next(calls),
    )

    with pytest.raises(SystemExit, match="cold-tier restore failed"):
        phase8_runtime_probes._collect_cold_tier_recovery_evidence(tmp_path)


def test_collect_partial_restore_recovery_evidence_reports_restore_ratio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane.json"
            self.swift_text_worker_metrics_path = tmp_path / "swift-text-worker.json"

        def start(self) -> None:
            self.control_plane_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "scheduler.partial_restore_walk_back_count": 1.0,
                            "scheduler.restore_plan_restored_tokens": 18.0,
                            "scheduler.restore_plan_total_tokens": 22.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.swift_text_worker_metrics_path.write_text(
                json.dumps(
                    {
                        "updated_at_unix_ms": 1,
                        "values": {
                            "swift_text.cache_exact_hit_count": 3.0,
                            "swift_text.cache_partial_hit_count": 1.0,
                            "swift_text.cache_fallback_count": 2.0,
                            "swift_text.cache_reconstruction_failure_count": 0.0,
                        },
                    }
                ),
                encoding="utf-8",
            )

        def stop(self) -> None:
            return None

    calls = iter(
        [
            {"status": 200, "request_id": "req-base", "body": "data: [DONE]"},
            {"status": 200, "request_id": "req-follow", "body": "data: [DONE]"},
        ]
    )
    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: next(calls),
    )

    report = phase8_runtime_probes._collect_partial_restore_recovery_evidence(tmp_path)

    assert report == {
        "walk_back_count": 1.0,
        "restored_tokens": 18.0,
        "total_tokens": 22.0,
        "restore_ratio_pct": 81.82,
        "cache_hit_taxonomy": {
            "exact_hit_count": 3.0,
            "partial_hit_count": 1.0,
            "fallback_count": 2.0,
            "reconstruction_failure_count": 0.0,
        },
    }


def test_collect_partial_restore_recovery_evidence_raises_when_followup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane.json"

        def start(self) -> None:
            self.control_plane_metrics_path.write_text(
                json.dumps({"updated_at_unix_ms": 1, "values": {}}),
                encoding="utf-8",
            )

        def stop(self) -> None:
            return None

    calls = iter(
        [
            {"status": 200, "request_id": "req-base", "body": "data: [DONE]"},
            {"status": 500, "body": "restore failed"},
        ]
    )
    monkeypatch.setattr(phase8_runtime_probes, "LiveMelixStack", FakeStack)
    monkeypatch.setattr(
        phase8_runtime_probes,
        "stream_chat_completion",
        lambda stack, payload: next(calls),
    )

    with pytest.raises(SystemExit, match="partial-restore follow-up failed"):
        phase8_runtime_probes._collect_partial_restore_recovery_evidence(tmp_path)


def test_stream_chat_completion_reads_http_status_body_request_id_and_ttft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 200

        def __init__(self) -> None:
            self._lines = iter(
                [
                    b'data: {"request_id":"req-123"}\n',
                    b'data: {"id":"req-123","choices":[{"delta":{"content":"hello"},"index":0}]}\n',
                    b"data: [DONE]\n",
                    b"",
                ]
            )

        def readline(self) -> bytes:
            return next(self._lines)

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    ticks = iter([100.0, 100.025, 100.05])

    monkeypatch.setattr(
        phase8_runtime_probes.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )
    monkeypatch.setattr(phase8_runtime_probes.time, "perf_counter", lambda: next(ticks))

    result = phase8_runtime_probes.stream_chat_completion(
        SimpleNamespace(chat_url=lambda: "http://127.0.0.1:11434/v1/chat/completions"),
        {"model": "melix-dev-text"},
    )

    assert result["status"] == 200
    assert result["request_id"] == "req-123"
    assert "data: [DONE]" in result["body"]
    assert result["ttft_ms"] == pytest.approx(25.0)
    assert result["total_ms"] == pytest.approx(50.0)


def test_post_json_returns_decoded_payload_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 202

        def read(self) -> bytes:
            return b'{"ok": true, "count": 2}'

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        phase8_runtime_probes.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )

    status, payload = phase8_runtime_probes._post_json(
        "http://127.0.0.1:11434/v1/embeddings",
        {"model": "melix-dev-embed", "input": ["alpha"]},
    )

    assert status == 202
    assert payload == {"ok": True, "count": 2}


def test_post_json_returns_decoded_http_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            503,
            "service unavailable",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"boom"}'),
        )

    monkeypatch.setattr(phase8_runtime_probes.urllib.request, "urlopen", fake_urlopen)

    status, payload = phase8_runtime_probes._post_json(
        "http://127.0.0.1:11434/v1/rerank",
        {"model": "melix-dev-rerank"},
    )

    assert status == 503
    assert payload == {"error": "boom"}


def test_post_json_returns_plain_text_http_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "server error",
            hdrs=None,
            fp=io.BytesIO(b"internal error"),
        )

    monkeypatch.setattr(phase8_runtime_probes.urllib.request, "urlopen", fake_urlopen)

    status, payload = phase8_runtime_probes._post_json(
        "http://127.0.0.1:11434/v1/rerank",
        {"model": "melix-dev-rerank"},
    )

    assert status == 500
    assert payload == "internal error"


def test_read_model_states_extracts_model_status_by_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(
                {
                    "data": [
                        {"id": "melix-dev-text", "melix_state": "warm"},
                        {"id": "melix-dev-rerank", "melix_state": "pinned"},
                    ]
                }
            ).encode("utf-8")

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        phase8_runtime_probes.urllib.request,
        "urlopen",
        lambda url, timeout: FakeResponse(),
    )

    assert phase8_runtime_probes._read_model_states("http://127.0.0.1:11434/v1/models") == {
        "melix-dev-text": "warm",
        "melix-dev-rerank": "pinned",
    }


def test_run_prefill_memory_guard_probe_returns_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class FakeChannel:
        def close(self) -> None:
            closed.append(True)

    class FakeRuntimeStub:
        def __init__(self, channel: object) -> None:
            pass

        def LoadModel(self, request: object, timeout: float) -> object:
            return SimpleNamespace(
                ok=False,
                model_handle="",
                error=SimpleNamespace(code="", message="could not load"),
            )

    class FakeInferenceStub:
        def __init__(self, channel: object) -> None:
            pass

    monkeypatch.setattr(
        phase8_runtime_probes.grpc,
        "insecure_channel",
        lambda target: FakeChannel(),
    )
    monkeypatch.setattr(phase8_runtime_probes.runtime_pb2_grpc, "RuntimeServiceStub", FakeRuntimeStub)
    monkeypatch.setattr(
        phase8_runtime_probes.inference_pb2_grpc,
        "InferenceServiceStub",
        FakeInferenceStub,
    )

    result = phase8_runtime_probes._run_prefill_memory_guard_probe(
        SimpleNamespace(swift_socket_path="/tmp/swift.sock")
    )

    assert result == {
        "ok": False,
        "error_code": "load_failed",
        "error_message": "could not load",
    }
    assert closed == [True]


def test_run_prefill_memory_guard_probe_returns_prefill_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class FakeChannel:
        def close(self) -> None:
            closed.append(True)

    class FakeRuntimeStub:
        def __init__(self, channel: object) -> None:
            pass

        def LoadModel(self, request: object, timeout: float) -> object:
            return SimpleNamespace(
                ok=True,
                model_handle="handle-123",
                error=SimpleNamespace(code="", message=""),
            )

    class FakeInferenceStub:
        def __init__(self, channel: object) -> None:
            pass

        def Prefill(self, request: object, timeout: float) -> object:
            return SimpleNamespace(
                ok=False,
                error=SimpleNamespace(
                    code="prefill_memory_guard_exceeded",
                    message="Projected prefill memory would exceed the process budget.",
                ),
            )

    monkeypatch.setattr(
        phase8_runtime_probes.grpc,
        "insecure_channel",
        lambda target: FakeChannel(),
    )
    monkeypatch.setattr(phase8_runtime_probes.runtime_pb2_grpc, "RuntimeServiceStub", FakeRuntimeStub)
    monkeypatch.setattr(
        phase8_runtime_probes.inference_pb2_grpc,
        "InferenceServiceStub",
        FakeInferenceStub,
    )

    result = phase8_runtime_probes._run_prefill_memory_guard_probe(
        SimpleNamespace(swift_socket_path="/tmp/swift.sock")
    )

    assert result == {
        "ok": False,
        "error_code": "prefill_memory_guard_exceeded",
        "error_message": "Projected prefill memory would exceed the process budget.",
    }
    assert closed == [True]


def test_wait_for_metrics_ignores_transient_decode_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "control-plane-metrics.json"
    metrics_path.write_text("{}", encoding="utf-8")

    class FlakyReader:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, path: Path) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise json.JSONDecodeError("bad", "{}", 0)
            return {
                "values": {
                    "control_plane.http_ready_ms": 12.5,
                }
            }

    monkeypatch.setattr(phase8_runtime_probes, "read_metrics_export", FlakyReader())

    parameters = inspect.signature(phase8_runtime_probes.wait_for_metrics).parameters
    assert "clock" in parameters
    assert "sleep_fn" in parameters

    ticks = iter([0.0, 0.04, 0.08, 0.08])

    def fake_clock() -> float:
        return next(ticks)

    assert phase8_runtime_probes.wait_for_metrics(
        metrics_path,
        ["control_plane.http_ready_ms"],
        timeout_seconds=0.1,
        clock=fake_clock,
        sleep_fn=lambda _: None,
    ) == {"control_plane.http_ready_ms": 12.5}


def test_phase8_metrics_report_main_emits_split_bootstrap_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy = {
        "benchmarks": {},
        "install": {},
        "recovery": {"restart_recovery_ms": {"max": 15_000.0}, "restart_recovery_success_rate": {"min": 100.0}},
        "training": {
            "training_duration_ms": {"max": 2_000.0},
            "adapter_publish_ms": {"max": 150.0},
        },
    }
    recovery = {
        "restart_to_ready_ms": 612.3,
        "restart_swift_text_worker_ready_ms": 4200.0,
        "restart_python_worker_ready_ms": 5100.0,
        "restart_control_plane_spawn_to_ready_ms": 1292.3,
        "snapshot_restore_ms": 98.4,
        "restart_recovery_ms": 710.7,
        "restart_recovery_success_rate": 100.0,
        "http_ready_ms": 17.0,
        "background_preload_ms": 644.0,
        "background_preload_success": 1.0,
    }

    monkeypatch.setattr(
        phase8_metrics_report,
        "measure_cold_boot_to_ready",
        lambda repo_root: {
            "cold_boot_to_ready_ms": 801.2,
            "swift_text_worker_ready_ms": 4100.0,
            "python_worker_ready_ms": 5200.0,
            "control_plane_spawn_to_ready_ms": 1100.0,
            "swift_text_worker_spawn_to_bootstrap_ms": 4900.0,
            "swift_text_worker_registry_init_ms": 6.0,
            "swift_text_worker_services_init_ms": 4.0,
            "swift_text_worker_server_construct_ms": 3.0,
            "swift_text_worker_bootstrap_ms": 15.0,
            "python_worker_spawn_to_bootstrap_ms": 5000.0,
            "python_worker_arg_parse_ms": 1.0,
            "python_worker_registry_init_ms": 7.0,
            "python_worker_server_build_ms": 5.0,
            "python_worker_server_start_ms": 2.0,
            "python_worker_bootstrap_ms": 16.0,
            "http_ready_ms": 801.2,
            "background_preload_ms": 622.4,
            "background_preload_success": 1.0,
            "first_text_model_warm_ms": 141.8,
            "text_model_load_estimated_resident_bytes": 4096.0,
            "text_model_load_resident_bytes": 8192.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_restart_recovery_evidence",
        lambda repo_root: recovery,
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 3,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "load_release_gate_policy",
        lambda path: policy,
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1420.0, "adapter_publish_ms": 118.0},
            "recovery": recovery,
            "runtime_core": runtime_core,
            "m9": {
                "summary": {
                    "required_probe_count": 23.0,
                    "missing_probe_count": 0.0,
                    "failed_threshold_count": 0.0,
                }
            },
            "passed": True,
            "failures": [],
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_closure_audit",
        lambda repo_root: type(
            "FakeClosureAudit",
            (),
            {
                "to_dict": staticmethod(
                    lambda: {
                        "metrics": {
                            "closure_audit.blocker_count": 0.0,
                            "closure_audit.accepted_risk_count": 1.0,
                            "closure_audit.evidence_gap_count": 0.0,
                            "closure_audit.deferred_work_count": 1.0,
                        },
                        "summary": {
                            "top_unresolved_findings": [
                                "M9.8 release-gate wiring remains deferred until ecosystem evidence is consumed by the release gate."
                            ]
                        },
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_operator_action_evidence",
        lambda jobs_root: {
            "operator_action_latency_ms": 0.5,
            "registry_job_count": 2,
            "registry_adapter_count": 1,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_metrics_report.py", "--repo-root", str(tmp_path), "--json"],
    )

    assert phase8_metrics_report.main() == 0

    payload = json.loads(capsys.readouterr().out)
    metrics = payload["metrics"]
    assert metrics["desktop.cold_boot_to_ready_ms"] == 801.2
    assert metrics["desktop.swift_text_worker_ready_ms"] == 4100.0
    assert metrics["desktop.python_worker_ready_ms"] == 5200.0
    assert metrics["desktop.control_plane_spawn_to_ready_ms"] == 1100.0
    assert metrics["desktop.swift_text_worker_spawn_to_bootstrap_ms"] == 4900.0
    assert metrics["desktop.swift_text_worker_registry_init_ms"] == 6.0
    assert metrics["desktop.swift_text_worker_services_init_ms"] == 4.0
    assert metrics["desktop.swift_text_worker_server_construct_ms"] == 3.0
    assert metrics["desktop.swift_text_worker_bootstrap_ms"] == 15.0
    assert metrics["desktop.python_worker_spawn_to_bootstrap_ms"] == 5000.0
    assert metrics["desktop.python_worker_arg_parse_ms"] == 1.0
    assert metrics["desktop.python_worker_registry_init_ms"] == 7.0
    assert metrics["desktop.python_worker_server_build_ms"] == 5.0
    assert metrics["desktop.python_worker_server_start_ms"] == 2.0
    assert metrics["desktop.python_worker_bootstrap_ms"] == 16.0
    assert metrics["desktop.http_ready_ms"] == 801.2
    assert metrics["desktop.background_preload_ms"] == 622.4
    assert metrics["desktop.first_text_model_warm_ms"] == 141.8
    assert metrics["desktop.text_model_load_estimated_resident_bytes"] == 4096.0
    assert metrics["desktop.text_model_load_resident_bytes"] == 8192.0
    assert metrics["desktop.restart_to_ready_ms"] == 612.3
    assert metrics["desktop.restart_swift_text_worker_ready_ms"] == 4200.0
    assert metrics["desktop.restart_python_worker_ready_ms"] == 5100.0
    assert metrics["desktop.restart_control_plane_spawn_to_ready_ms"] == 1292.3
    assert metrics["desktop.snapshot_restore_ms"] == 98.4
    assert metrics["desktop.restart_recovery_ms"] == 710.7
    assert metrics["runtime.multi_model_ready_count"] == 3.0
    assert metrics["runtime.multi_model_request_success_rate"] == 100.0
    assert metrics["runtime.prefill_memory_guard_rejection_count"] == 1.0
    assert metrics["runtime.prefill_memory_guard_success_rate"] == 100.0
    assert metrics["release_gate.m9_required_probe_count"] == 23.0
    assert metrics["release_gate.m9_missing_probe_count"] == 0.0
    assert metrics["release_gate.m9_failed_threshold_count"] == 0.0


def test_phase8_metrics_report_main_reuses_embedded_closure_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    embedded_closure_audit = {
        "metrics": {
            "closure_audit.blocker_count": 0.0,
            "closure_audit.accepted_risk_count": 2.0,
            "closure_audit.evidence_gap_count": 1.0,
            "closure_audit.deferred_work_count": 3.0,
        },
        "summary": {
            "top_unresolved_findings": [
                "Embedded closure-audit evidence should be reused."
            ]
        },
    }

    monkeypatch.setattr(
        phase8_metrics_report,
        "measure_cold_boot_to_ready",
        lambda repo_root: {"cold_boot_to_ready_ms": 801.2},
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_restart_recovery_evidence",
        lambda repo_root: {"restart_recovery_ms": 710.7, "restart_recovery_success_rate": 100.0},
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_runtime_core_evidence",
        lambda repo_root: {"multi_model_ready_count": 3, "multi_model_request_success_rate": 100.0},
    )
    monkeypatch.setattr(phase8_metrics_report, "load_release_gate_policy", lambda path: {})
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1420.0, "adapter_publish_ms": 118.0},
            "recovery": recovery,
            "runtime_core": runtime_core,
            "m9": {
                "summary": {
                    "required_probe_count": 23.0,
                    "missing_probe_count": 0.0,
                    "failed_threshold_count": 0.0,
                },
                "closure_audit": embedded_closure_audit,
            },
            "passed": True,
            "failures": [],
        },
    )

    def fail_build_closure_audit(repo_root: Path) -> object:
        raise AssertionError("build_closure_audit should not be called when release gate embeds closure_audit")

    monkeypatch.setattr(phase8_metrics_report, "build_closure_audit", fail_build_closure_audit)
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_operator_action_evidence",
        lambda jobs_root: {
            "operator_action_latency_ms": 0.5,
            "registry_job_count": 2,
            "registry_adapter_count": 1,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_metrics_report.py", "--repo-root", str(tmp_path), "--json"],
    )

    assert phase8_metrics_report.main() == 0

    payload = json.loads(capsys.readouterr().out)
    metrics = payload["metrics"]
    assert metrics["closure_audit.blocker_count"] == 0.0
    assert metrics["closure_audit.accepted_risk_count"] == 2.0
    assert metrics["closure_audit.evidence_gap_count"] == 1.0
    assert metrics["closure_audit.deferred_work_count"] == 3.0
    assert payload["closure_audit"] == embedded_closure_audit



def test_phase8_metrics_report_main_returns_nonzero_when_release_gate_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        phase8_metrics_report,
        "measure_cold_boot_to_ready",
        lambda repo_root: {
            "cold_boot_to_ready_ms": 801.2,
            "swift_text_worker_ready_ms": 4100.0,
            "python_worker_ready_ms": 5200.0,
            "control_plane_spawn_to_ready_ms": 1100.0,
            "swift_text_worker_spawn_to_bootstrap_ms": 4900.0,
            "swift_text_worker_registry_init_ms": 6.0,
            "swift_text_worker_services_init_ms": 4.0,
            "swift_text_worker_server_construct_ms": 3.0,
            "swift_text_worker_bootstrap_ms": 15.0,
            "python_worker_spawn_to_bootstrap_ms": 5000.0,
            "python_worker_arg_parse_ms": 1.0,
            "python_worker_registry_init_ms": 7.0,
            "python_worker_server_build_ms": 5.0,
            "python_worker_server_start_ms": 2.0,
            "python_worker_bootstrap_ms": 16.0,
            "http_ready_ms": 801.2,
            "background_preload_ms": 622.4,
            "background_preload_success": 1.0,
            "first_text_model_warm_ms": 141.8,
            "text_model_load_estimated_resident_bytes": 4096.0,
            "text_model_load_resident_bytes": 8192.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_restart_recovery_evidence",
        lambda repo_root: {
            "restart_to_ready_ms": 612.3,
            "restart_swift_text_worker_ready_ms": 4200.0,
            "restart_python_worker_ready_ms": 5100.0,
            "restart_control_plane_spawn_to_ready_ms": 1292.3,
            "snapshot_restore_ms": 98.4,
            "restart_recovery_ms": 710.7,
            "restart_recovery_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 3,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "load_release_gate_policy",
        lambda path: {
            "benchmarks": {},
            "install": {},
            "recovery": {"restart_recovery_ms": {"max": 15_000.0}, "restart_recovery_success_rate": {"min": 100.0}},
            "runtime_core": {
                "multi_model_ready_count": {"min": 3.0},
                "multi_model_request_success_rate": {"min": 100.0},
                "prefill_memory_guard_rejection_count": {"min": 1.0},
                "prefill_memory_guard_success_rate": {"min": 100.0},
            },
            "training": {
                "training_duration_ms": {"max": 2_000.0},
                "adapter_publish_ms": {"max": 150.0},
            },
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1420.0, "adapter_publish_ms": 118.0},
            "recovery": recovery,
            "runtime_core": runtime_core,
            "passed": False,
            "failures": ["restart_recovery_ms exceeded"],
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_operator_action_evidence",
        lambda jobs_root: {
            "operator_action_latency_ms": 0.5,
            "registry_job_count": 2,
            "registry_adapter_count": 1,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_metrics_report.py", "--repo-root", str(tmp_path), "--json"],
    )

    assert phase8_metrics_report.main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["release_gate"]["passed"] is False


def test_phase8_metrics_report_main_emits_output_without_json_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        phase8_metrics_report,
        "measure_cold_boot_to_ready",
        lambda repo_root: {
            "cold_boot_to_ready_ms": 700.0,
            "http_ready_ms": 700.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_restart_recovery_evidence",
        lambda repo_root: {
            "restart_recovery_ms": 500.0,
            "restart_recovery_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "load_release_gate_policy",
        lambda path: {
            "benchmarks": {},
            "install": {},
            "recovery": {"restart_recovery_ms": {"max": 15_000.0}, "restart_recovery_success_rate": {"min": 100.0}},
            "runtime_core": {
                "multi_model_ready_count": {"min": 3.0},
                "multi_model_request_success_rate": {"min": 100.0},
                "prefill_memory_guard_rejection_count": {"min": 1.0},
                "prefill_memory_guard_success_rate": {"min": 100.0},
            },
            "training": {
                "training_duration_ms": {"max": 2_000.0},
                "adapter_publish_ms": {"max": 150.0},
            },
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1000.0, "adapter_publish_ms": 100.0},
            "recovery": recovery,
            "runtime_core": runtime_core,
            "passed": True,
            "failures": [],
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "collect_operator_action_evidence",
        lambda jobs_root: {
            "operator_action_latency_ms": 0.5,
            "registry_job_count": 2,
            "registry_adapter_count": 1,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_metrics_report.py", "--repo-root", str(tmp_path)],
    )

    assert phase8_metrics_report.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["release_gate"]["passed"] is True


def test_phase8_metrics_report_run_path_exits_through_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import phase8_runtime_probes as runtime_probes_module
    from worker.productization import acceptance_metrics as acceptance_metrics_module
    from worker.productization import release_gates as release_gates_module

    monkeypatch.setattr(
        runtime_probes_module,
        "measure_cold_boot_to_ready",
        lambda repo_root: {
            "cold_boot_to_ready_ms": 700.0,
            "http_ready_ms": 700.0,
        },
    )
    monkeypatch.setattr(
        runtime_probes_module,
        "collect_restart_recovery_evidence",
        lambda repo_root: {
            "restart_recovery_ms": 500.0,
            "restart_recovery_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        runtime_probes_module,
        "collect_runtime_core_evidence",
        lambda repo_root: {
            "multi_model_ready_count": 3.0,
            "multi_model_request_success_rate": 100.0,
            "prefill_memory_guard_rejection_count": 1.0,
            "prefill_memory_guard_success_rate": 100.0,
        },
    )
    monkeypatch.setattr(
        acceptance_metrics_module,
        "collect_operator_action_evidence",
        lambda jobs_root: {
            "operator_action_latency_ms": 0.5,
            "registry_job_count": 2,
            "registry_adapter_count": 1,
        },
    )
    monkeypatch.setattr(
        release_gates_module,
        "load_release_gate_policy",
        lambda path: {
            "benchmarks": {},
            "install": {},
            "recovery": {"restart_recovery_ms": {"max": 15_000.0}, "restart_recovery_success_rate": {"min": 100.0}},
            "runtime_core": {
                "multi_model_ready_count": {"min": 3.0},
                "multi_model_request_success_rate": {"min": 100.0},
                "prefill_memory_guard_rejection_count": {"min": 1.0},
                "prefill_memory_guard_success_rate": {"min": 100.0},
            },
            "training": {
                "training_duration_ms": {"max": 2_000.0},
                "adapter_publish_ms": {"max": 150.0},
            },
        },
    )
    monkeypatch.setattr(
        release_gates_module,
        "build_release_gate_report",
        lambda repo_root, policy, recovery, runtime_core: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1000.0, "adapter_publish_ms": 100.0},
            "recovery": recovery,
            "runtime_core": runtime_core,
            "passed": True,
            "failures": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase8_metrics_report.py", "--repo-root", str(tmp_path), "--json"],
    )

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(ROOT / "scripts" / "phase8_metrics_report.py"), run_name="__main__")

    assert excinfo.value.code == 0
