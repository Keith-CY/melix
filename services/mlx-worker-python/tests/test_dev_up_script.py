from __future__ import annotations

import importlib.util
import os
import shlex
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


def write_swift_mlx_package_resolved(repo_root: Path, version: str) -> None:
    package_resolved_path = repo_root / "services/mlx-text-worker-swift/Package.resolved"
    package_resolved_path.parent.mkdir(parents=True, exist_ok=True)
    package_resolved_path.write_text(
        (
            "{\n"
            '  "pins": [\n'
            "    {\n"
            '      "identity": "mlx-swift",\n'
            '      "state": {\n'
            f'        "version": "{version}"\n'
            "      }\n"
            "    }\n"
            "  ]\n"
            "}\n"
        ),
        encoding="utf-8",
    )


def write_mlx_metal_fixture(root: Path, version: str) -> Path:
    metallib_path = root / "mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True, exist_ok=True)
    metallib_path.write_text("mlx", encoding="utf-8")
    metadata_path = root / f"mlx_metal-{version}.dist-info/METADATA"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(f"Name: mlx-metal\nVersion: {version}\n", encoding="utf-8")
    return metallib_path


def make_layout(dev_up, tmp_path: Path):
    return dev_up.RuntimeLayout(
        service_instance_name="",
        melix_home_dir=tmp_path / "home",
        runtime_dir=tmp_path / "runtime",
        python_socket_path=tmp_path / "runtime/python.sock",
        swift_text_worker_socket_path=tmp_path / "runtime/swift.sock",
        managed_models_dir=tmp_path / "home/models/default-managed",
        audio_runtime_packs_dir=tmp_path / "home/runtime-packs/audio",
        model_ops_jobs_root=tmp_path / "home/jobs/model-ops",
        evaluation_jobs_root=tmp_path / "home/jobs/evaluation",
        control_plane_metrics_path=tmp_path / "runtime/control-plane.json",
        swift_text_worker_metrics_path=tmp_path / "runtime/swift-metrics.json",
        python_worker_metrics_path=tmp_path / "runtime/python-metrics.json",
        gateway_config_store_path=tmp_path / "home/config/gateway-config.json",
        gateway_serving_defaults_store_path=tmp_path / "home/config/gateway-serving-defaults.json",
        image_defaults_store_path=tmp_path / "home/config/image-defaults.json",
        http_port="12436",
        python_backend_mode="deterministic",
        swift_text_worker_backend_mode="swift",
        python_bridge_executable=None,
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


def test_build_swift_launch_command_uses_direct_debug_binary_without_glob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    binary_path = tmp_path / "services/mlx-text-worker-swift/.build/debug/melix-text-worker-swift"
    make_executable(binary_path)

    def fail_glob(self: Path, pattern: str):
        raise AssertionError("resolve_built_swift_product_binary() should not glob when .build/debug has the product")

    monkeypatch.setattr(dev_up.Path, "glob", fail_glob)

    assert dev_up.build_swift_launch_command(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=True,
    ) == [str(binary_path)]


def test_resolve_built_swift_product_binary_skips_broken_scandir_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    build_root = tmp_path / "services/mlx-text-worker-swift/.build"
    binary_path = build_root / "arm64-apple-macosx/debug/melix-text-worker-swift"
    make_executable(binary_path)

    class BrokenEntry:
        name = "stale"

        def is_dir(self) -> bool:
            raise OSError("stale dirent")

    class GoodEntry:
        name = "arm64-apple-macosx"

        def is_dir(self) -> bool:
            return True

    class FakeScandir:
        def __enter__(self):
            return iter((BrokenEntry(), GoodEntry()))

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    def fake_scandir(path: str):
        assert path == os.fspath(build_root)
        return FakeScandir()

    monkeypatch.setattr(dev_up.os, "scandir", fake_scandir)

    assert dev_up.resolve_built_swift_product_binary(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
    ) == binary_path


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


def test_build_python_worker_launch_command_defaults_to_uv_extra_mlx(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()

    assert dev_up.build_python_worker_launch_command(
        tmp_path,
        python_executable=None,
        socket_path=tmp_path / "worker.sock",
        backend_mode="auto",
    ) == [
        "uv",
        "run",
        "--project",
        f"{tmp_path}/services/mlx-worker-python",
        "--extra",
        "mlx",
        "python",
        "-m",
        "worker.bootstrap",
        "--socket-path",
        f"{tmp_path}/worker.sock",
        "--backend-mode",
        "auto",
    ]


def test_build_python_worker_launch_command_uses_configured_python(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    bridge_python = tmp_path / ".venv/bin/python"

    assert dev_up.build_python_worker_launch_command(
        tmp_path,
        python_executable=bridge_python,
        socket_path=tmp_path / "worker.sock",
        backend_mode="auto",
    ) == [
        os.fspath(bridge_python),
        "-m",
        "worker.bootstrap",
        "--socket-path",
        f"{tmp_path}/worker.sock",
        "--backend-mode",
        "auto",
    ]


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
    assert layout.python_socket_path.parent == Path("/tmp").resolve()
    assert layout.swift_text_worker_socket_path.parent == Path("/tmp").resolve()


def test_compute_runtime_layout_uses_short_default_worker_sockets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / (
        "very/deep/worktree/path/that/would/overflow/the/macos/unix/socket/path/limit"
    )
    repo_root.mkdir(parents=True)
    monkeypatch.setenv("MELIX_SERVICE_INSTANCE_NAME", "team-a")
    monkeypatch.setenv("MELIX_RUNTIME_DIR", os.fspath(repo_root / ".runtime/sidecars/team-a"))

    layout = dev_up.compute_runtime_layout(repo_root)

    assert layout.python_socket_path.parent == Path("/tmp").resolve()
    assert layout.swift_text_worker_socket_path.parent == Path("/tmp").resolve()
    assert "team-a" in layout.python_socket_path.name
    assert layout.python_socket_path.name.endswith("-python.sock")
    assert layout.swift_text_worker_socket_path.name.endswith("-swift.sock")
    assert len(os.fspath(layout.python_socket_path)) < 103
    assert len(os.fspath(layout.swift_text_worker_socket_path)) < 103


def test_compute_runtime_layout_honors_explicit_worker_socket_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    python_socket = tmp_path / "runtime/python-worker.sock"
    swift_socket = tmp_path / "runtime/swift-text-worker.sock"
    monkeypatch.setenv("MELIX_WORKER_SOCKET_PATH", os.fspath(python_socket))
    monkeypatch.setenv("MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH", os.fspath(swift_socket))

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.python_socket_path == python_socket
    assert layout.swift_text_worker_socket_path == swift_socket


def test_compute_runtime_layout_defaults_to_real_backends(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.python_backend_mode == "auto"
    assert layout.swift_text_worker_backend_mode == "swift"


def test_compute_runtime_layout_uses_bridge_executable_from_uv_project_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    venv_root = tmp_path / ".venv"
    bridge_python = venv_root / "bin/python"
    bridge_python.parent.mkdir(parents=True)
    bridge_python.write_text("", encoding="utf-8")
    bridge_python.chmod(bridge_python.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", os.fspath(venv_root))

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.python_bridge_executable == bridge_python.resolve()


def test_compute_runtime_layout_ignores_non_executable_uv_project_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    venv_root = tmp_path / ".venv"
    bridge_python = venv_root / "bin/python"
    bridge_python.parent.mkdir(parents=True)
    bridge_python.write_text("", encoding="utf-8")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", os.fspath(venv_root))

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.python_bridge_executable is None


def test_compute_runtime_layout_prefers_explicit_bridge_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    explicit_python = tmp_path / "custom-python"
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", os.fspath(tmp_path / ".venv"))
    monkeypatch.setenv("MELIX_PYTHON_BRIDGE_EXECUTABLE", os.fspath(explicit_python))

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.python_bridge_executable == explicit_python.resolve()


def test_resolve_python_bridge_executable_preserves_virtualenv_entrypoint_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    venv_root = tmp_path / ".venv"
    real_python = tmp_path / "python-install/bin/python3.14"
    real_python.parent.mkdir(parents=True)
    real_python.write_text("", encoding="utf-8")
    real_python.chmod(real_python.stat().st_mode | stat.S_IXUSR)
    bridge_python = venv_root / "bin/python"
    bridge_python.parent.mkdir(parents=True)
    bridge_python.symlink_to(real_python)
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", os.fspath(venv_root))

    assert dev_up.resolve_python_bridge_executable() == bridge_python


def test_compute_runtime_layout_uses_service_instance_name_for_sidecar_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setenv("MELIX_SERVICE_INSTANCE_NAME", "team-a")

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.runtime_dir == (tmp_path / ".runtime" / "sidecars" / "team-a").resolve()
    assert layout.melix_home_dir == layout.runtime_dir / "home"
    assert layout.managed_models_dir == layout.melix_home_dir / "models/default-managed"
    assert layout.audio_runtime_packs_dir == layout.melix_home_dir / "runtime-packs/audio"
    assert layout.model_ops_jobs_root == layout.melix_home_dir / "jobs/model-ops"
    assert layout.evaluation_jobs_root == layout.melix_home_dir / "jobs/evaluation"
    assert layout.gateway_config_store_path == layout.melix_home_dir / "config/gateway-config.json"
    assert (
        layout.gateway_serving_defaults_store_path
        == layout.melix_home_dir / "config/gateway-serving-defaults.json"
    )
    assert layout.image_defaults_store_path == layout.melix_home_dir / "config/image-defaults.json"


def test_compute_runtime_layout_ignores_blank_melix_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setenv("MELIX_HOME", " ")

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.melix_home_dir == (tmp_path / ".runtime/phase1/home").resolve()
    assert layout.managed_models_dir == layout.melix_home_dir / "models/default-managed"


def test_runtime_layout_helpers_manage_directories_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)

    dev_up.ensure_runtime_directories(layout)
    assert layout.melix_home_dir.is_dir()
    assert (layout.melix_home_dir / "config").is_dir()
    assert (layout.melix_home_dir / "state").is_dir()
    assert (layout.melix_home_dir / "secrets").is_dir()
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
    gateway_config = layout.gateway_config_store_path
    gateway_config.parent.mkdir(parents=True, exist_ok=True)
    gateway_config.write_text("persist", encoding="utf-8")

    dev_up.cleanup_runtime_artifacts(layout)
    assert all(not artifact.exists() for artifact in (
        layout.python_socket_path,
        layout.swift_text_worker_socket_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.python_worker_metrics_path,
    ))
    assert gateway_config.read_text(encoding="utf-8") == "persist"

    (layout.runtime_dir / "swift-text-worker.pid").write_text("12", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Run scripts/dev_down.sh first"):
        dev_up.ensure_runtime_is_stopped(layout)

    (layout.runtime_dir / "swift-text-worker.pid").unlink()
    dev_up.ensure_runtime_is_stopped(layout)


def test_write_runtime_environment_exports_sidecar_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dev_up = load_dev_up_module()
    bridge_python = tmp_path / ".venv/bin/python"
    layout = replace(make_layout(dev_up, tmp_path), service_instance_name="team-a", python_bridge_executable=bridge_python)
    metallib_path = tmp_path / "swift-mlx-0.24.2" / "mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_text("mlx", encoding="utf-8")
    monkeypatch.setenv("MELIX_SWIFT_MLX_METALLIB_PATH", str(metallib_path))
    monkeypatch.setenv("MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE", "1")
    monkeypatch.setenv("MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE", "1")

    env_path = dev_up.write_runtime_environment(layout)
    payload = env_path.read_text(encoding="utf-8")

    assert f'export MELIX_MANAGED_MODEL_ROOT="{layout.managed_models_dir}"' in payload
    assert f'export MELIX_AUDIO_RUNTIME_PACK_ROOT="{layout.audio_runtime_packs_dir}"' in payload
    assert f'export MELIX_MODEL_OPS_JOBS_ROOT="{layout.model_ops_jobs_root}"' in payload
    assert f'export MELIX_EVALUATION_JOBS_ROOT="{layout.evaluation_jobs_root}"' in payload
    assert 'export MELIX_SERVICE_INSTANCE_NAME="team-a"' in payload
    assert f'export MELIX_PYTHON_BRIDGE_EXECUTABLE="{bridge_python}"' in payload
    assert f'export MELIX_SWIFT_MLX_METALLIB_PATH="{metallib_path}"' in payload
    assert 'export MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE="1"' in payload
    assert 'export MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE="1"' in payload


def test_prepare_swift_worker_launch_cwd_symlinks_runtime_local_default_metallib(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    metallib_path = tmp_path / ".venv/lib/python3.13/site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True, exist_ok=True)
    metallib_path.write_text("mlx", encoding="utf-8")

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, tmp_path)

    default_metallib = launch_cwd / "default.metallib"
    assert launch_cwd == layout.runtime_dir / "swift-text-worker-cwd"
    assert default_metallib.is_symlink()
    assert default_metallib.resolve() == metallib_path.resolve()


def test_resolve_local_mlx_metallib_uses_scandir_stack_without_path_rglob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    metallib_path = tmp_path / ".venv/lib/python3.13/site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True, exist_ok=True)
    metallib_path.write_text("mlx", encoding="utf-8")

    def fail_rglob(self: Path, pattern: str):
        raise AssertionError("resolve_local_mlx_metallib() should not allocate a Path.rglob() tree")

    monkeypatch.setattr(dev_up.Path, "rglob", fail_rglob)

    assert dev_up.resolve_local_mlx_metallib(tmp_path, uv_cache_dir=layout.uv_cache_dir) == metallib_path.resolve()


def test_read_mlx_metal_dist_info_version_uses_scandir_without_path_glob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    metallib_path = write_mlx_metal_fixture(tmp_path / "site-packages", "0.29.1")

    def fail_glob(self: Path, pattern: str):  # pragma: no cover - exercised only on regression
        raise AssertionError("read_mlx_metal_dist_info_version() should not allocate Path.glob() results")

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:  # pragma: no cover
        if self.name == "METADATA":
            raise AssertionError("METADATA should be streamed line-by-line, not materialized")
        return original_read_text(self, *args, **kwargs)

    original_read_text = dev_up.Path.read_text
    monkeypatch.setattr(dev_up.Path, "glob", fail_glob)
    monkeypatch.setattr(dev_up.Path, "read_text", fail_read_text)

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) == "0.29.1"


def test_read_mlx_metal_dist_info_version_falls_back_to_dist_info_directory_name(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    metallib_path = tmp_path / "site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_text("mlx", encoding="utf-8")
    dist_info_path = tmp_path / "site-packages/mlx_metal-0.31.1.dist-info"
    dist_info_path.mkdir()
    (dist_info_path / "METADATA").write_text("Name: mlx-metal\nSummary: missing version\n", encoding="utf-8")

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) == "0.31.1"


def test_read_mlx_metal_dist_info_version_falls_back_when_metadata_read_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    metallib_path = tmp_path / "site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_text("mlx", encoding="utf-8")
    dist_info_path = tmp_path / "site-packages/mlx_metal-0.31.2.dist-info"
    dist_info_path.mkdir()

    def fail_metadata_read(metadata_path: Path) -> str | None:
        assert metadata_path == dist_info_path / "METADATA"
        raise OSError("permission denied")

    monkeypatch.setattr(dev_up, "_read_dist_info_metadata_version", fail_metadata_read)

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) == "0.31.2"


def test_read_mlx_metal_dist_info_version_skips_scandir_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    metallib_path = tmp_path / "site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_text("mlx", encoding="utf-8")

    def fail_scandir(path: Path):
        raise OSError("permission denied")

    monkeypatch.setattr(dev_up.os, "scandir", fail_scandir)

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) is None


def test_iter_mlx_metallib_candidates_skips_scandir_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()

    def fail_scandir(path: Path):
        raise OSError("permission denied")

    monkeypatch.setattr(dev_up.os, "scandir", fail_scandir)

    assert list(dev_up.iter_mlx_metallib_candidates(tmp_path)) == []


def test_iter_mlx_metallib_candidates_skips_entry_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()

    class BrokenEntry:
        name = "mlx.metallib"
        path = os.fspath(tmp_path / "mlx.metallib")

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            raise OSError("stale dirent")

    class FakeScandir:
        def __enter__(self):
            return iter((BrokenEntry(),))

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    monkeypatch.setattr(dev_up.os, "scandir", lambda path: FakeScandir())

    assert list(dev_up.iter_mlx_metallib_candidates(tmp_path)) == []


def test_prepare_swift_worker_launch_cwd_uses_configured_uv_cache_dir_for_metallib(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    layout = replace(make_layout(dev_up, tmp_path), uv_cache_dir=tmp_path / "custom-uv-cache")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    metallib_path = layout.uv_cache_dir / "mlx/runtime/mlx.metallib"
    metallib_path.parent.mkdir(parents=True, exist_ok=True)
    metallib_path.write_text("mlx", encoding="utf-8")

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, tmp_path)

    default_metallib = launch_cwd / "default.metallib"
    assert launch_cwd == layout.runtime_dir / "swift-text-worker-cwd"
    assert default_metallib.is_symlink()
    assert default_metallib.resolve() == metallib_path.resolve()


def test_prepare_swift_worker_launch_cwd_prefers_matching_swift_mlx_metallib_from_global_uv_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "0.29.1")
    layout = replace(make_layout(dev_up, repo_root), uv_cache_dir=repo_root / ".uv-cache")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    write_mlx_metal_fixture(layout.uv_cache_dir / "archive-v0/bad", "0.31.1")
    home_dir = tmp_path / "home"
    matching_metallib_path = write_mlx_metal_fixture(home_dir / ".cache/uv/archive-v0/good", "0.29.1")
    monkeypatch.setattr(dev_up.Path, "home", lambda: home_dir)

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, repo_root)

    default_metallib = launch_cwd / "default.metallib"
    assert launch_cwd == layout.runtime_dir / "swift-text-worker-cwd"
    assert default_metallib.is_symlink()
    assert default_metallib.resolve() == matching_metallib_path.resolve()


def test_prepare_swift_worker_launch_cwd_accepts_mlx_swift_0313_compatible_mlx_metal_0311(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "0.31.3")
    layout = replace(make_layout(dev_up, repo_root), uv_cache_dir=repo_root / ".uv-cache")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    compatible_metallib_path = write_mlx_metal_fixture(layout.uv_cache_dir / "archive-v0/good", "0.31.1")
    monkeypatch.setattr(dev_up.Path, "home", lambda: tmp_path / "empty-home")

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, repo_root)

    default_metallib = launch_cwd / "default.metallib"
    assert launch_cwd == layout.runtime_dir / "swift-text-worker-cwd"
    assert default_metallib.is_symlink()
    assert default_metallib.resolve() == compatible_metallib_path.resolve()


def test_prepare_swift_worker_launch_cwd_rejects_incompatible_auto_discovered_metallib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "0.29.1")
    layout = replace(make_layout(dev_up, repo_root), uv_cache_dir=repo_root / ".uv-cache")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    incompatible_metallib_path = write_mlx_metal_fixture(layout.uv_cache_dir / "archive-v0/bad", "0.31.1")
    monkeypatch.setattr(dev_up.Path, "home", lambda: tmp_path / "empty-home")

    with pytest.raises(RuntimeError) as exc:
        dev_up.prepare_swift_worker_launch_cwd(layout, repo_root)

    message = str(exc.value)
    assert "mlx-swift 0.29.1" in message
    assert "mlx_metal 0.29.1" in message
    assert "0.31.1" in message
    assert str(incompatible_metallib_path.resolve()) in message
    assert "MELIX_SWIFT_MLX_METALLIB_PATH" in message


def test_prepare_swift_worker_launch_cwd_skips_metallib_for_deterministic_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "0.29.1")
    layout = replace(
        make_layout(dev_up, repo_root),
        swift_text_worker_backend_mode="deterministic",
        uv_cache_dir=repo_root / ".uv-cache",
    )
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    write_mlx_metal_fixture(layout.uv_cache_dir / "archive-v0/bad", "0.31.1")
    monkeypatch.setattr(dev_up.Path, "home", lambda: tmp_path / "empty-home")

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, repo_root)

    assert launch_cwd == repo_root
    assert not (layout.runtime_dir / "swift-text-worker-cwd" / "default.metallib").exists()


def test_prepare_swift_worker_launch_cwd_prefers_configured_metallib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    layout = replace(make_layout(dev_up, tmp_path), uv_cache_dir=tmp_path / "custom-uv-cache")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    configured_metallib_path = tmp_path / "swift-mlx-0.24.2" / "mlx.metallib"
    configured_metallib_path.parent.mkdir(parents=True, exist_ok=True)
    configured_metallib_path.write_text("swift-mlx", encoding="utf-8")
    cache_metallib_path = layout.uv_cache_dir / "mlx/runtime/mlx.metallib"
    cache_metallib_path.parent.mkdir(parents=True, exist_ok=True)
    cache_metallib_path.write_text("python-mlx", encoding="utf-8")
    monkeypatch.setenv("MELIX_SWIFT_MLX_METALLIB_PATH", str(configured_metallib_path))

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, tmp_path)

    default_metallib = launch_cwd / "default.metallib"
    assert launch_cwd == layout.runtime_dir / "swift-text-worker-cwd"
    assert default_metallib.is_symlink()
    assert default_metallib.resolve() == configured_metallib_path.resolve()


def test_prepare_swift_worker_launch_cwd_rejects_missing_configured_metallib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MELIX_SWIFT_MLX_METALLIB_PATH", str(tmp_path / "missing.metallib"))

    with pytest.raises(RuntimeError, match="MELIX_SWIFT_MLX_METALLIB_PATH"):
        dev_up.prepare_swift_worker_launch_cwd(layout, tmp_path)


def test_prepare_swift_worker_launch_cwd_falls_back_to_repo_root_without_local_metallib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dev_up.Path, "home", lambda: tmp_path / "empty-home")

    launch_cwd = dev_up.prepare_swift_worker_launch_cwd(layout, tmp_path)

    assert launch_cwd == tmp_path
    assert not (layout.runtime_dir / "swift-text-worker-cwd" / "default.metallib").exists()


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


def test_spawn_background_process_recreates_stale_unwritable_log_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    log_path = tmp_path / "process.log"
    log_path.write_text("stale\n", encoding="utf-8")
    log_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    seen: dict[str, object] = {}

    class FakeProcess:
        pid = 8765

    def fake_popen(command, **kwargs):
        seen["command"] = command
        kwargs["stdout"].write(b"recreated\n")
        kwargs["stdout"].flush()
        return FakeProcess()

    monkeypatch.setattr(dev_up.subprocess, "Popen", fake_popen)

    pid = dev_up.spawn_background_process(
        cwd=tmp_path,
        log_path=log_path,
        env_overrides={"MELIX_TEST_VALUE": "1"},
        command=["python3", "-c", "print('hello')"],
    )

    assert pid == 8765
    assert seen["command"] == ["python3", "-c", "print('hello')"]
    assert log_path.read_text(encoding="utf-8").strip() == "recreated"


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
        "--extra",
        "mlx",
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


def test_run_wait_for_worker_ready_uses_configured_python_executable(
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
    bridge_python = tmp_path / ".venv/bin/python"
    dev_up.run_wait_for_worker_ready(
        tmp_path,
        uv_cache_dir=tmp_path / "uv-cache",
        socket_path=tmp_path / "worker.sock",
        output_path=tmp_path / "ready.log",
        python_executable=bridge_python,
    )

    assert seen["command"] == [
        os.fspath(bridge_python),
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
    assert f'export MELIX_REPO_ROOT="{REPO_ROOT}"' in content
    assert f'export MELIX_HOME="{layout.melix_home_dir}"' in content
    assert 'export MELIX_RUNTIME_DIR="' in content
    assert 'export MELIX_PYTHON_WORKER_METRICS_PATH="' in content
    assert f'export MELIX_GATEWAY_CONFIG_STORE_PATH="{layout.gateway_config_store_path}"' in content
    assert (
        f'export MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH="{layout.gateway_serving_defaults_store_path}"'
        in content
    )
    assert f'export MELIX_IMAGE_DEFAULTS_STORE_PATH="{layout.image_defaults_store_path}"' in content
    assert "MELIX_PYTHON_BRIDGE_EXECUTABLE" not in content


def test_dev_down_sources_runtime_env_for_socket_cleanup(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    python_socket = tmp_path / "short-python.sock"
    swift_socket = tmp_path / "short-swift.sock"
    control_metrics = tmp_path / "control-plane-metrics.json"
    swift_metrics = tmp_path / "swift-text-worker-metrics.json"
    python_metrics = tmp_path / "python-worker-metrics.json"
    for artifact in (python_socket, swift_socket, control_metrics, swift_metrics, python_metrics):
        artifact.write_text("stale", encoding="utf-8")
    (runtime_dir / "env.sh").write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                f"export MELIX_WORKER_SOCKET_PATH={shlex.quote(os.fspath(python_socket))}",
                f"export MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH={shlex.quote(os.fspath(swift_socket))}",
                f"export MELIX_CONTROL_PLANE_METRICS_PATH={shlex.quote(os.fspath(control_metrics))}",
                f"export MELIX_SWIFT_TEXT_WORKER_METRICS_PATH={shlex.quote(os.fspath(swift_metrics))}",
                f"export MELIX_PYTHON_WORKER_METRICS_PATH={shlex.quote(os.fspath(python_metrics))}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", os.fspath(REPO_ROOT / "scripts" / "dev_down.sh")],
        cwd=REPO_ROOT,
        env={**os.environ, "MELIX_RUNTIME_DIR": os.fspath(runtime_dir)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "Melix local stack is stopped."
    assert not python_socket.exists()
    assert not swift_socket.exists()
    assert not control_metrics.exists()
    assert not swift_metrics.exists()
    assert not python_metrics.exists()
    assert not (runtime_dir / "env.sh").exists()


def test_start_stack_orchestrates_processes_and_emits_runtime_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_up = load_dev_up_module()
    bridge_python = tmp_path / ".venv/bin/python"
    layout = replace(
        make_layout(dev_up, tmp_path),
        service_instance_name="team-a",
        python_bridge_executable=bridge_python,
    )
    calls: list[tuple[str, object]] = []
    pid_values = iter([101, 202, 303])
    monkeypatch.setenv("MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE", "1")
    monkeypatch.setenv("MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE", "1")

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda repo_root, *, package_path, product_name, prefer_built: [product_name],
    )
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root: layout.runtime_dir / "swift-text-worker-cwd",
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
    assert ("http", "12436") in calls
    wait_calls = [payload for kind, payload in calls if kind == "wait"]
    assert len(wait_calls) == 2
    assert all(payload["python_executable"] == bridge_python for payload in wait_calls)
    swift_spawn = next(
        payload for kind, payload in calls if kind == "spawn" and payload["command"] == ["melix-text-worker-swift"]
    )
    assert swift_spawn["cwd"] == layout.runtime_dir / "swift-text-worker-cwd"
    assert swift_spawn["env_overrides"]["MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE"] == "1"
    assert swift_spawn["env_overrides"]["MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE"] == "1"
    python_spawn = next(
        payload for kind, payload in calls if kind == "spawn" and "worker.bootstrap" in payload["command"]
    )
    assert python_spawn["env_overrides"]["MELIX_HOME"] == str(layout.melix_home_dir)
    assert python_spawn["command"][0] == os.fspath(bridge_python)
    assert "uv" not in python_spawn["command"]
    control_plane_spawn = next(
        payload for kind, payload in calls if kind == "spawn" and payload["command"] == ["melix-control-plane"]
    )
    assert control_plane_spawn["env_overrides"]["MELIX_HOME"] == str(layout.melix_home_dir)
    assert control_plane_spawn["env_overrides"]["MELIX_GATEWAY_CONFIG_STORE_PATH"] == str(
        layout.gateway_config_store_path
    )
    assert control_plane_spawn["env_overrides"]["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"] == str(
        layout.gateway_serving_defaults_store_path
    )
    assert control_plane_spawn["env_overrides"]["MELIX_IMAGE_DEFAULTS_STORE_PATH"] == str(
        layout.image_defaults_store_path
    )
    assert control_plane_spawn["env_overrides"]["MELIX_PYTHON_BRIDGE_EXECUTABLE"] == str(bridge_python)


def test_start_stack_wraps_http_timeout_with_log_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root: layout.runtime_dir / "swift-text-worker-cwd",
    )
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


def test_start_stack_control_plane_gateway_config_store_overrides_parent_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    captured_env: dict[tuple[str, ...], dict[str, str]] = {}
    pid_values = iter([101, 202, 303])

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_popen(command, **kwargs):
        captured_env[tuple(command)] = kwargs["env"]
        return FakeProcess(next(pid_values))

    monkeypatch.setenv("MELIX_GATEWAY_CONFIG_STORE_PATH", "/tmp/global-gateway-config.json")
    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root: layout.runtime_dir / "swift-text-worker-cwd",
    )
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda repo_root, *, package_path, product_name, prefer_built: [product_name],
    )
    monkeypatch.setattr(dev_up.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dev_up, "run_wait_for_worker_ready", lambda repo_root, **kwargs: None)
    monkeypatch.setattr(dev_up, "wait_for_http_ready", lambda http_port, timeout_seconds=120.0: None)
    monkeypatch.setattr(dev_up.time, "perf_counter_ns", lambda: 999)

    dev_up.start_stack(dev_up.DevUpOptions(prefer_built=True))

    control_plane_env = captured_env[("melix-control-plane",)]
    assert control_plane_env["MELIX_HOME"] == str(layout.melix_home_dir)
    assert control_plane_env["MELIX_GATEWAY_CONFIG_STORE_PATH"] == str(layout.gateway_config_store_path)


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
