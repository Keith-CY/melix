from __future__ import annotations

import json
import sys
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

    with pytest.raises(RuntimeError, match="Timed out waiting for control plane metrics"):
        phase8_runtime_probes.wait_for_metrics(
            metrics_path,
            ["control_plane.background_preload_ms"],
            timeout_seconds=0.01,
        )


def test_measure_cold_boot_to_ready_reads_bootstrap_metrics_from_the_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root
            self.control_plane_metrics_path = tmp_path / "control-plane-metrics.json"
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
    assert report["http_ready_ms"] == 18.5
    assert report["background_preload_ms"] == 640.0
    assert report["background_preload_success"] == 1.0
    assert report["first_text_model_warm_ms"] == 125.0
    assert report["text_model_load_estimated_resident_bytes"] == 4096.0
    assert report["text_model_load_resident_bytes"] == 8192.0


def test_measure_cold_boot_to_ready_raises_when_first_text_warmup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStack:
        def __init__(self, repo_root: Path) -> None:
            self.control_plane_metrics_path = tmp_path / "control-plane-metrics.json"
            self.startup_timings = {}

        def start(self) -> None:
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


def test_stream_chat_completion_reads_http_status_and_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 200

        def read(self) -> bytes:
            return b"data: [DONE]"

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(
        phase8_runtime_probes.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )

    result = phase8_runtime_probes.stream_chat_completion(
        SimpleNamespace(chat_url=lambda: "http://127.0.0.1:11434/v1/chat/completions"),
        {"model": "melix-dev-text"},
    )

    assert result == {"status": 200, "body": "data: [DONE]"}


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

    assert phase8_runtime_probes.wait_for_metrics(
        metrics_path,
        ["control_plane.http_ready_ms"],
        timeout_seconds=0.1,
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
        "load_release_gate_policy",
        lambda path: policy,
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_release_gate_report",
        lambda repo_root, policy, recovery: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1420.0, "adapter_publish_ms": 118.0},
            "recovery": recovery,
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
        ["phase8_metrics_report.py", "--repo-root", str(tmp_path), "--json"],
    )

    assert phase8_metrics_report.main() == 0

    payload = json.loads(capsys.readouterr().out)
    metrics = payload["metrics"]
    assert metrics["desktop.cold_boot_to_ready_ms"] == 801.2
    assert metrics["desktop.swift_text_worker_ready_ms"] == 4100.0
    assert metrics["desktop.python_worker_ready_ms"] == 5200.0
    assert metrics["desktop.control_plane_spawn_to_ready_ms"] == 1100.0
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
        "load_release_gate_policy",
        lambda path: {
            "benchmarks": {},
            "install": {},
            "recovery": {"restart_recovery_ms": {"max": 15_000.0}, "restart_recovery_success_rate": {"min": 100.0}},
            "training": {
                "training_duration_ms": {"max": 2_000.0},
                "adapter_publish_ms": {"max": 150.0},
            },
        },
    )
    monkeypatch.setattr(
        phase8_metrics_report,
        "build_release_gate_report",
        lambda repo_root, policy, recovery: {
            "install": {"checks": {"manifest_exists": True, "environment_script_exists": True, "all_plists_exist": True}},
            "benchmarks": {"report_exists": True, "metrics": {}},
            "training": {"training_duration_ms": 1420.0, "adapter_publish_ms": 118.0},
            "recovery": recovery,
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
