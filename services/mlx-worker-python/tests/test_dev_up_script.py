from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
import urllib.error
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dev_up.sh"
MODULE_PATH = REPO_ROOT / "scripts" / "dev_up.py"


def load_dev_up_module():
    assert MODULE_PATH.exists(), f"Expected Python dev_up entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_dev_up", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_layout(dev_up, tmp_path: Path):
    return dev_up.RuntimeLayout(
        service_instance_name="",
        runtime_dir=tmp_path / "runtime",
        python_socket_path=tmp_path / "runtime/python.sock",
        swift_text_worker_socket_path=tmp_path / "runtime/swift.sock",
        managed_models_dir=tmp_path / "runtime/models/default-managed",
        audio_runtime_packs_dir=tmp_path / "runtime/runtime-packs/audio",
        model_ops_jobs_root=tmp_path / "runtime/jobs/model-ops",
        evaluation_jobs_root=tmp_path / "runtime/jobs/model-ops/evaluation",
        control_plane_metrics_path=tmp_path / "runtime/control-plane.json",
        swift_text_worker_metrics_path=tmp_path / "runtime/swift-metrics.json",
        python_worker_metrics_path=tmp_path / "runtime/python-metrics.json",
        http_port="11434",
        python_backend_mode="deterministic",
        swift_text_worker_backend_mode="deterministic",
        uv_cache_dir=tmp_path / "uv-cache",
        swift_home=tmp_path / "swift-home",
        clang_module_cache_path=tmp_path / "module-cache",
    )


def test_build_swift_launch_command_defaults_to_swift_run(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()

    assert dev_up.build_swift_launch_command(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=False,
    ) == [
        "swift",
        "run",
        "--package-path",
        f"{tmp_path}/services/mlx-text-worker-swift",
        "melix-text-worker-swift",
    ]


def test_build_swift_launch_command_prefers_built_binary_when_requested(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    binary_path = tmp_path / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/melix-text-worker-swift"
    make_executable(binary_path)

    assert dev_up.build_swift_launch_command(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=True,
    ) == [str(binary_path)]


def test_build_swift_launch_command_reports_missing_built_binary(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()

    try:
        dev_up.build_swift_launch_command(
            tmp_path,
            package_path="services/control-plane-swift",
            product_name="melix-control-plane",
            prefer_built=True,
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected build_swift_launch_command to fail when built binary is missing")

    assert "Built Swift product is missing for 'melix-control-plane'" in message
    assert "Run `make swift-test` or `swift build --package-path" in message


def test_dev_up_shell_wrapper_delegates_help_to_python_entrypoint() -> None:
    result = subprocess.run(
        ["bash", os.fspath(SCRIPT_PATH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "Usage: bash scripts/dev_up.sh [--prefer-built]",
        "",
        "Options:",
        "  --prefer-built  Start Swift processes from existing built executables under .build/debug when available.",
        "                  This keeps the Python worker on uv run and fails fast if the required Swift binaries are missing.",
    ]


def test_parse_args_prefers_built() -> None:
    dev_up = load_dev_up_module()

    assert dev_up.parse_args(["--prefer-built"]) == dev_up.DevUpOptions(prefer_built=True)


def test_parse_args_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_up.parse_args(["--help"])

    assert exc.value.code == 0
    assert "Usage: bash scripts/dev_up.sh [--prefer-built]" in capsys.readouterr().out


def test_parse_args_rejects_unknown_argument(capsys: pytest.CaptureFixture[str]) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_up.parse_args(["--nope"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "Unknown argument: --nope" in captured.err
    assert "Usage: bash scripts/dev_up.sh [--prefer-built]" in captured.err


def test_compute_runtime_layout_uses_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    runtime_dir = tmp_path / "custom-runtime"
    monkeypatch.setenv("MELIX_RUNTIME_DIR", os.fspath(runtime_dir))
    monkeypatch.setenv("MELIX_HTTP_PORT", "20001")
    monkeypatch.setenv("MELIX_BACKEND_MODE", "deterministic")
    monkeypatch.setenv("MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE", "swift")

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.runtime_dir == runtime_dir.resolve()
    assert layout.http_port == "20001"
    assert layout.python_backend_mode == "deterministic"
    assert layout.swift_text_worker_backend_mode == "swift"
    assert layout.python_socket_path == runtime_dir / "python-worker.sock"


def test_compute_runtime_layout_uses_service_instance_name_for_sidecar_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setenv("MELIX_SERVICE_INSTANCE_NAME", "team-a")

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.runtime_dir == (tmp_path / ".runtime" / "sidecars" / "team-a").resolve()
    assert layout.managed_models_dir == layout.runtime_dir / "models/default-managed"
    assert layout.audio_runtime_packs_dir == layout.runtime_dir / "runtime-packs/audio"
    assert layout.model_ops_jobs_root == layout.runtime_dir / "jobs/model-ops"
    assert layout.evaluation_jobs_root == layout.model_ops_jobs_root / "evaluation"


def test_runtime_layout_helpers_manage_directories_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)

    dev_up.ensure_runtime_directories(layout)
    assert layout.runtime_dir.is_dir()
    assert layout.uv_cache_dir.is_dir()
    assert layout.swift_home.is_dir()
    assert layout.clang_module_cache_path.is_dir()
    assert layout.managed_models_dir.is_dir()
    assert layout.audio_runtime_packs_dir.is_dir()
    assert layout.model_ops_jobs_root.is_dir()
    assert layout.evaluation_jobs_root.is_dir()

    for artifact in (
        layout.python_socket_path,
        layout.swift_text_worker_socket_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.python_worker_metrics_path,
    ):
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("stale", encoding="utf-8")

    dev_up.cleanup_runtime_artifacts(layout)
    assert all(not artifact.exists() for artifact in (
        layout.python_socket_path,
        layout.swift_text_worker_socket_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.python_worker_metrics_path,
    ))

    (layout.runtime_dir / "swift-text-worker.pid").write_text("12", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Run scripts/dev_down.sh first"):
        dev_up.ensure_runtime_is_stopped(layout)

    (layout.runtime_dir / "swift-text-worker.pid").unlink()
    dev_up.ensure_runtime_is_stopped(layout)


def test_write_runtime_environment_exports_sidecar_roots(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    layout = replace(make_layout(dev_up, tmp_path), service_instance_name="team-a")

    env_path = dev_up.write_runtime_environment(layout)
    payload = env_path.read_text(encoding="utf-8")

    assert f'export MELIX_MANAGED_MODEL_ROOT="{layout.managed_models_dir}"' in payload
    assert f'export MELIX_AUDIO_RUNTIME_PACK_ROOT="{layout.audio_runtime_packs_dir}"' in payload
    assert f'export MELIX_MODEL_OPS_JOBS_ROOT="{layout.model_ops_jobs_root}"' in payload
    assert f'export MELIX_EVALUATION_JOBS_ROOT="{layout.evaluation_jobs_root}"' in payload
    assert 'export MELIX_SERVICE_INSTANCE_NAME="team-a"' in payload


def test_spawn_background_process_and_write_pid_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    log_path = tmp_path / "process.log"
    seen: dict[str, object] = {}

    class FakeProcess:
        pid = 4321

    def fake_popen(command, **kwargs):
        seen["command"] = command
        seen["cwd"] = kwargs["cwd"]
        seen["env"] = kwargs["env"]
        kwargs["stdout"].write(b"1\n")
        kwargs["stdout"].flush()
        return FakeProcess()

    monkeypatch.setattr(dev_up.subprocess, "Popen", fake_popen)

    pid = dev_up.spawn_background_process(
        cwd=tmp_path,
        log_path=log_path,
        env_overrides={"MELIX_TEST_VALUE": "1"},
        command=["python3", "-c", "print('hello')"],
    )
    assert pid == 4321
    assert seen["command"] == ["python3", "-c", "print('hello')"]
    assert seen["cwd"] == tmp_path
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["MELIX_TEST_VALUE"] == "1"
    assert log_path.read_text(encoding="utf-8").strip() == "1"

    pid_path = tmp_path / "worker.pid"
    dev_up.write_pid_file(pid_path, 321)
    assert pid_path.read_text(encoding="utf-8") == "321"


def test_run_wait_for_worker_ready_builds_expected_uv_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["cwd"] = kwargs["cwd"]
        seen["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(dev_up.subprocess, "run", fake_run)
    output_path = tmp_path / "ready.log"
    dev_up.run_wait_for_worker_ready(
        tmp_path,
        uv_cache_dir=tmp_path / "uv-cache",
        socket_path=tmp_path / "worker.sock",
        output_path=output_path,
    )

    assert seen["command"] == [
        "uv",
        "run",
        "--project",
        f"{tmp_path}/services/mlx-worker-python",
        "python",
        f"{tmp_path}/scripts/wait_for_worker_ready.py",
        "--socket-path",
        f"{tmp_path}/worker.sock",
    ]
    assert seen["cwd"] == tmp_path
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["UV_CACHE_DIR"] == f"{tmp_path}/uv-cache"
    assert env["PYTHONPATH"] == f"{tmp_path}:{tmp_path / 'services/mlx-worker-python'}"


def test_run_wait_for_worker_ready_raises_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setattr(
        dev_up.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    with pytest.raises(RuntimeError, match="Worker readiness probe failed"):
        dev_up.run_wait_for_worker_ready(
            tmp_path,
            uv_cache_dir=tmp_path / "uv-cache",
            socket_path=tmp_path / "worker.sock",
            output_path=tmp_path / "ready.log",
        )


def test_wait_for_http_ready_handles_retry_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    dev_up = load_dev_up_module()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    attempts = iter(
        [
            urllib.error.URLError("not yet"),
            Response(),
        ]
    )

    def fake_urlopen(url: str, timeout: int):
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(dev_up.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(dev_up.time, "perf_counter", lambda: 0.0)
    monkeypatch.setattr(dev_up.time, "sleep", lambda _: None)
    dev_up.wait_for_http_ready("11434", timeout_seconds=0.1)

    clock = iter([0.0, 0.2])
    monkeypatch.setattr(
        dev_up.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("still down")),
    )
    monkeypatch.setattr(dev_up.time, "perf_counter", lambda: next(clock))

    with pytest.raises(RuntimeError, match="Melix did not become ready"):
        dev_up.wait_for_http_ready("11434", timeout_seconds=0.1)


def test_write_runtime_environment_emits_export_file(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    layout.runtime_dir.mkdir(parents=True)

    env_path = dev_up.write_runtime_environment(layout)

    content = env_path.read_text(encoding="utf-8")
    assert 'export MELIX_RUNTIME_DIR="' in content
    assert 'export MELIX_PYTHON_WORKER_METRICS_PATH="' in content


def test_start_stack_orchestrates_processes_and_emits_runtime_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_up = load_dev_up_module()
    layout = replace(make_layout(dev_up, tmp_path), service_instance_name="team-a")
    calls: list[tuple[str, object]] = []
    pid_values = iter([101, 202, 303])

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda repo_root, *, package_path, product_name, prefer_built: [product_name],
    )
    monkeypatch.setattr(
        dev_up,
        "spawn_background_process",
        lambda **kwargs: calls.append(("spawn", kwargs)) or next(pid_values),
    )
    monkeypatch.setattr(
        dev_up,
        "run_wait_for_worker_ready",
        lambda repo_root, **kwargs: calls.append(("wait", kwargs)),
    )
    monkeypatch.setattr(
        dev_up,
        "wait_for_http_ready",
        lambda http_port, timeout_seconds=120.0: calls.append(("http", http_port)),
    )
    monkeypatch.setattr(dev_up.time, "perf_counter_ns", lambda: 999)

    dev_up.start_stack(dev_up.DevUpOptions(prefer_built=True))

    assert (layout.runtime_dir / "swift-text-worker.pid").read_text(encoding="utf-8") == "101"
    assert (layout.runtime_dir / "python-worker.pid").read_text(encoding="utf-8") == "202"
    assert (layout.runtime_dir / "control-plane.pid").read_text(encoding="utf-8") == "303"
    output = capsys.readouterr().out
    assert "Melix local stack is ready." in output
    assert "Service instance: team-a" in output
    assert "Swift launch mode: prefer-built" in output
    assert any(kind == "spawn" for kind, _ in calls)
    assert any(kind == "wait" for kind, _ in calls)
    assert ("http", "11434") in calls


def test_start_stack_wraps_http_timeout_with_log_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda repo_root, *, package_path, product_name, prefer_built: [product_name],
    )
    monkeypatch.setattr(dev_up, "spawn_background_process", lambda **kwargs: 1)
    monkeypatch.setattr(dev_up, "run_wait_for_worker_ready", lambda repo_root, **kwargs: None)
    monkeypatch.setattr(dev_up.time, "perf_counter_ns", lambda: 999)

    def fail_ready(http_port: str, timeout_seconds: float = 120.0) -> None:
        raise RuntimeError("Melix did not become ready.")

    monkeypatch.setattr(dev_up, "wait_for_http_ready", fail_ready)

    with pytest.raises(RuntimeError) as exc:
        dev_up.start_stack(dev_up.DevUpOptions(prefer_built=False))

    message = str(exc.value)
    assert "Melix did not become ready." in message
    assert "control-plane.log" in message
    assert "swift-text-worker.log" in message
    assert "python-worker.log" in message


def test_main_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    dev_up = load_dev_up_module()
    seen: dict[str, object] = {}

    monkeypatch.setattr(dev_up, "start_stack", lambda options: seen.setdefault("options", options))

    assert dev_up.main(["--prefer-built"]) == 0
    assert seen["options"] == dev_up.DevUpOptions(prefer_built=True)


def test_main_returns_one_on_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setattr(
        dev_up,
        "start_stack",
        lambda options: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert dev_up.main([]) == 1
    assert "boom" in capsys.readouterr().err
