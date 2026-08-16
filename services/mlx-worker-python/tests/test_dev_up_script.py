from __future__ import annotations

import base64
import importlib.util
import io
import json
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


def write_swift_mlx_core_package(repo_root: Path, version: str) -> None:
    package_swift_path = repo_root / "services/mlx-text-worker-swift/.build/checkouts/mlx-swift/Package.swift"
    package_swift_path.parent.mkdir(parents=True, exist_ok=True)
    package_swift_path.write_text(
        f'cxxSettings: [.define("MLX_VERSION", to: "\\"{version}\\"")]\n',
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


def test_compatible_mlx_metal_versions_use_only_the_vendored_core_version(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "0.31.4")
    write_swift_mlx_core_package(repo_root, "0.31.1")

    assert dev_up.compatible_mlx_metal_versions_for_swift_mlx(repo_root) == ("0.31.1",)


def test_compatible_mlx_metal_versions_use_an_explicit_mapping_without_a_checkout(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "0.31.4")

    assert dev_up.compatible_mlx_metal_versions_for_swift_mlx(repo_root) == ("0.31.1",)


def test_compatible_mlx_metal_versions_do_not_assume_the_package_tag_matches_core(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    repo_root = tmp_path / "repo"
    write_swift_mlx_package_resolved(repo_root, "9.8.7")

    assert dev_up.compatible_mlx_metal_versions_for_swift_mlx(repo_root) == ()


def make_layout(dev_up, tmp_path: Path):
    return dev_up.RuntimeLayout(
        service_instance_name="",
        melix_home_dir=tmp_path / "home",
        runtime_dir=tmp_path / "runtime",
        python_socket_path=tmp_path / "runtime/python.sock",
        swift_text_worker_socket_path=tmp_path / "runtime/swift.sock",
        swift_vision_worker_socket_path=tmp_path / "runtime/swift-vision.sock",
        control_plane_socket_path=tmp_path / "runtime/control-plane.sock",
        computer_broker_socket_path=tmp_path / "runtime/computer.sock",
        computer_broker_capability_path=tmp_path
        / "runtime/computer-broker-capability.bin",
        managed_models_dir=tmp_path / "home/models/default-managed",
        audio_runtime_packs_dir=tmp_path / "home/runtime-packs/audio",
        model_ops_jobs_root=tmp_path / "home/jobs/model-ops",
        evaluation_jobs_root=tmp_path / "home/jobs/evaluation",
        control_plane_metrics_path=tmp_path / "runtime/control-plane.json",
        swift_text_worker_metrics_path=tmp_path / "runtime/swift-metrics.json",
        swift_vision_worker_metrics_path=tmp_path / "runtime/swift-vision-metrics.json",
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


def stub_computer_broker_startup(
    dev_up,
    monkeypatch: pytest.MonkeyPatch,
    *,
    public_key: bytes = b"P" * 32,
    calls: list[tuple[str, object]] | None = None,
) -> None:
    def fake_read_exact_descriptor(
        descriptor: int,
        byte_count: int,
        *,
        timeout_seconds: float,
    ) -> bytes:
        os.close(descriptor)
        assert byte_count == 32
        assert timeout_seconds == 300.0
        if calls is not None:
            calls.append(("public-key", public_key))
        return public_key

    def fake_wait_for_private_socket(
        path: Path,
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        assert timeout_seconds == 300.0
        if calls is not None:
            calls.append(("computer-socket", path))

    monkeypatch.setattr(dev_up, "read_exact_descriptor", fake_read_exact_descriptor)
    monkeypatch.setattr(dev_up, "wait_for_private_socket", fake_wait_for_private_socket)


def test_build_swift_launch_command_builds_then_launches_direct_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    binary_path = (
        tmp_path
        / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/melix-text-worker-swift"
    )
    make_executable(binary_path)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dev_up.subprocess, "run", fake_run)

    assert dev_up.build_swift_launch_command(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=False,
    ) == [str(binary_path)]
    assert calls == [
        (
            [
                "swift",
                "build",
                "--package-path",
                f"{tmp_path}/services/mlx-text-worker-swift",
                "-c",
                "debug",
                "--product",
                "melix-text-worker-swift",
            ],
            {"check": True, "cwd": tmp_path},
        )
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


def test_build_swift_launch_command_uses_requested_release_configuration(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    binary_path = (
        tmp_path
        / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/release/melix-text-worker-swift"
    )
    make_executable(binary_path)

    assert dev_up.build_swift_launch_command(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=True,
        build_configuration="release",
    ) == [str(binary_path)]


def test_build_swift_launch_command_passes_configuration_to_swift_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    binary_path = (
        tmp_path
        / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/release/melix-text-worker-swift"
    )
    make_executable(binary_path)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dev_up.subprocess, "run", fake_run)

    assert dev_up.build_swift_launch_command(
        tmp_path,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=False,
        build_configuration="release",
    ) == [str(binary_path)]
    assert calls[0][0] == [
        "swift",
        "build",
        "--package-path",
        f"{tmp_path}/services/mlx-text-worker-swift",
        "-c",
        "release",
        "--product",
        "melix-text-worker-swift",
    ]
    assert calls[0][1] == {"check": True, "cwd": tmp_path}


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
    assert "with configuration 'debug'" in message
    assert "Run `swift build --package-path" in message


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
        "Usage: bash scripts/dev_up.sh [--prefer-built] [--build-configuration debug|release]",
        "",
        "Options:",
        "  --prefer-built  Start Swift processes from existing built executables under .build/<configuration> when available.",
        "                  This keeps the Python worker on uv run and fails fast if the required Swift binaries are missing.",
    ]


def test_parse_args_prefers_built() -> None:
    dev_up = load_dev_up_module()

    assert dev_up.parse_args(["--prefer-built"]) == dev_up.DevUpOptions(
        prefer_built=True,
        build_configuration="debug",
    )


def test_parse_args_accepts_release_build_configuration() -> None:
    dev_up = load_dev_up_module()

    assert dev_up.parse_args(["--prefer-built", "--build-configuration", "release"]) == dev_up.DevUpOptions(
        prefer_built=True,
        build_configuration="release",
    )


def test_parse_args_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_up.parse_args(["--help"])

    assert exc.value.code == 0
    assert "Usage: bash scripts/dev_up.sh [--prefer-built] [--build-configuration debug|release]" in capsys.readouterr().out


def test_parse_args_rejects_unknown_argument(capsys: pytest.CaptureFixture[str]) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_up.parse_args(["--nope"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "Unknown argument: --nope" in captured.err
    assert "Usage: bash scripts/dev_up.sh [--prefer-built] [--build-configuration debug|release]" in captured.err


def test_parse_args_rejects_missing_build_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_up.parse_args(["--build-configuration"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "--build-configuration requires a value" in captured.err


def test_parse_args_rejects_unsupported_build_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_up.parse_args(["--build-configuration", "profile"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "--build-configuration must be either 'debug' or 'release'" in captured.err


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
    assert layout.python_socket_path.parent == Path("/tmp")
    assert layout.swift_text_worker_socket_path.parent == Path("/tmp")
    assert layout.swift_vision_worker_socket_path.parent == Path("/tmp")
    assert layout.control_plane_socket_path.parent.parent == Path("/tmp")
    assert layout.control_plane_socket_path.name == "control.sock"
    assert layout.computer_broker_socket_path.parent.parent == Path("/tmp")
    assert layout.computer_broker_socket_path.name == "broker.sock"
    assert (
        layout.computer_broker_capability_path.parent
        == layout.computer_broker_socket_path.parent
    )


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

    assert layout.python_socket_path.parent == Path("/tmp")
    assert layout.swift_text_worker_socket_path.parent == Path("/tmp")
    assert layout.swift_vision_worker_socket_path.parent == Path("/tmp")
    assert layout.control_plane_socket_path.parent.parent == Path("/tmp")
    assert layout.control_plane_socket_path.name == "control.sock"
    assert layout.control_plane_socket_path.parent.name.endswith("-control")
    assert layout.computer_broker_socket_path.parent.parent == Path("/tmp")
    assert layout.computer_broker_socket_path.name == "broker.sock"
    assert layout.computer_broker_socket_path.parent.name.endswith("-computer")
    assert "team-a" in layout.python_socket_path.name
    assert layout.python_socket_path.name.endswith("-python.sock")
    assert layout.swift_text_worker_socket_path.name.endswith("-swift.sock")
    assert layout.swift_vision_worker_socket_path.name.endswith("-swift-vision.sock")
    assert len(os.fspath(layout.python_socket_path)) < 103
    assert len(os.fspath(layout.swift_text_worker_socket_path)) < 103
    assert len(os.fspath(layout.swift_vision_worker_socket_path)) < 103
    assert len(os.fspath(layout.control_plane_socket_path)) < 103
    assert len(os.fspath(layout.computer_broker_socket_path)) < 103
    assert layout.computer_broker_capability_path == (
        layout.computer_broker_socket_path.parent / "verification-capability.bin"
    )


def test_compute_runtime_layout_preserves_tmp_alias_for_secure_runtime_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setenv("MELIX_SOCKET_DIR", "/tmp")

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert os.fspath(layout.control_plane_socket_path).startswith("/tmp/")
    assert os.fspath(layout.computer_broker_socket_path).startswith("/tmp/")
    assert os.fspath(layout.computer_broker_capability_path).startswith("/tmp/")
    assert not os.fspath(layout.computer_broker_capability_path).startswith(
        "/private/tmp/"
    )


def test_compute_runtime_layout_honors_explicit_worker_socket_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    python_socket = tmp_path / "runtime/python-worker.sock"
    swift_socket = tmp_path / "runtime/swift-text-worker.sock"
    swift_vision_socket = tmp_path / "runtime/swift-vision-worker.sock"
    computer_socket = tmp_path / "runtime/computer-broker.sock"
    monkeypatch.setenv("MELIX_WORKER_SOCKET_PATH", os.fspath(python_socket))
    monkeypatch.setenv("MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH", os.fspath(swift_socket))
    monkeypatch.setenv("MELIX_SWIFT_VISION_WORKER_SOCKET_PATH", os.fspath(swift_vision_socket))
    monkeypatch.setenv("MELIX_COMPUTER_BROKER_SOCKET", os.fspath(computer_socket))

    layout = dev_up.compute_runtime_layout(tmp_path)

    assert layout.python_socket_path == python_socket
    assert layout.swift_text_worker_socket_path == swift_socket
    assert layout.swift_vision_worker_socket_path == swift_vision_socket
    assert layout.computer_broker_socket_path == computer_socket


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
    assert stat.S_IMODE(layout.runtime_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(
        layout.computer_broker_socket_path.parent.stat().st_mode
    ) == 0o700
    assert stat.S_IMODE(
        layout.control_plane_socket_path.parent.stat().st_mode
    ) == 0o700
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
        layout.swift_vision_worker_socket_path,
        layout.computer_broker_socket_path,
        layout.computer_broker_capability_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.swift_vision_worker_metrics_path,
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
        layout.swift_vision_worker_socket_path,
        layout.computer_broker_socket_path,
        layout.computer_broker_capability_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.swift_vision_worker_metrics_path,
        layout.python_worker_metrics_path,
    ))
    assert gateway_config.read_text(encoding="utf-8") == "persist"

    (layout.runtime_dir / "swift-text-worker.pid").write_text("12", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Run scripts/dev_down.sh first"):
        dev_up.ensure_runtime_is_stopped(layout)

    (layout.runtime_dir / "swift-text-worker.pid").unlink()
    dev_up.ensure_runtime_is_stopped(layout)


def test_runtime_layout_creates_default_secure_socket_parents_private(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    monkeypatch.setenv("MELIX_RUNTIME_DIR", os.fspath(tmp_path / "runtime"))
    monkeypatch.setenv("MELIX_SOCKET_DIR", os.fspath(tmp_path / "sockets"))
    layout = dev_up.compute_runtime_layout(tmp_path)

    dev_up.ensure_runtime_directories(layout)

    assert stat.S_IMODE(
        layout.control_plane_socket_path.parent.stat().st_mode
    ) == 0o700
    assert stat.S_IMODE(
        layout.computer_broker_socket_path.parent.stat().st_mode
    ) == 0o700
    assert (
        layout.computer_broker_capability_path.parent
        == layout.computer_broker_socket_path.parent
    )


def test_rollback_started_stack_uses_exact_layout_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    artifacts = (
        layout.python_socket_path,
        layout.computer_broker_socket_path,
        layout.computer_broker_capability_path,
    )
    for artifact in artifacts:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("owned", encoding="utf-8")

    calls: list[tuple[list[str], dict[str, object]]] = []

    def successful_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="stopped", stderr="")

    monkeypatch.setattr(dev_up.subprocess, "run", successful_run)
    dev_up.rollback_started_stack(layout)

    assert calls[0][0] == [
        "/bin/bash",
        os.fspath(dev_up.ROOT / "scripts" / "dev_down.sh"),
    ]
    rollback_environment = calls[0][1]["env"]
    assert rollback_environment["MELIX_RUNTIME_DIR"] == os.fspath(layout.runtime_dir)
    assert rollback_environment["MELIX_SERVICE_INSTANCE_NAME"] == layout.service_instance_name
    assert rollback_environment["MELIX_WORKER_SOCKET_PATH"] == os.fspath(
        layout.python_socket_path
    )
    assert rollback_environment["MELIX_COMPUTER_BROKER_SOCKET"] == os.fspath(
        layout.computer_broker_socket_path
    )
    assert all(not artifact.exists() for artifact in artifacts)

    layout.python_socket_path.parent.mkdir(parents=True, exist_ok=True)
    layout.python_socket_path.write_text("owned-again", encoding="utf-8")
    monkeypatch.setattr(
        dev_up.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=7,
            stdout="",
            stderr="rollback failed",
        ),
    )
    with pytest.raises(RuntimeError, match="rollback failed"):
        dev_up.rollback_started_stack(layout)
    assert not layout.python_socket_path.exists()


def test_runtime_layout_rejects_broad_computer_broker_socket_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    broad_parent = tmp_path / "broad"
    broad_parent.mkdir(mode=0o755)
    broad_parent.chmod(0o755)
    layout = replace(
        make_layout(dev_up, tmp_path),
        computer_broker_socket_path=broad_parent / "broker.sock",
    )

    with pytest.raises(RuntimeError, match="permissions are too broad"):
        dev_up.ensure_runtime_directories(layout)


def test_runtime_layout_rejects_broad_control_plane_socket_parent(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    broad_parent = tmp_path / "broad-control"
    broad_parent.mkdir(mode=0o755)
    broad_parent.chmod(0o755)
    layout = replace(
        make_layout(dev_up, tmp_path),
        control_plane_socket_path=broad_parent / "control.sock",
    )

    with pytest.raises(RuntimeError, match="permissions are too broad"):
        dev_up.ensure_runtime_directories(layout)


def test_private_directory_validation_maps_files_symlinks_and_foreign_owners(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    regular_file = tmp_path / "not-a-directory"
    regular_file.write_text("file", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Could not prepare private runtime"):
        dev_up.ensure_private_directory(regular_file, tighten_owned=False)

    directory = tmp_path / "real-directory"
    directory.mkdir(mode=0o700)
    symlink = tmp_path / "directory-link"
    symlink.symlink_to(directory, target_is_directory=True)
    with pytest.raises(RuntimeError, match="is not a directory"):
        dev_up.ensure_private_directory(symlink, tighten_owned=False)

    foreign = tmp_path / "foreign-directory"
    foreign.mkdir(mode=0o700)
    original_lstat = dev_up.Path.lstat

    def foreign_owner_lstat(path: Path):
        status = original_lstat(path)
        if path == foreign:
            return SimpleNamespace(
                st_mode=status.st_mode,
                st_uid=os.getuid() + 1,
            )
        return status

    monkeypatch.setattr(dev_up.Path, "lstat", foreign_owner_lstat)
    with pytest.raises(RuntimeError, match="unexpected owner"):
        dev_up.ensure_private_directory(foreign, tighten_owned=False)


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
    monkeypatch.setenv("MELIX_MODEL_ROOTS", str(tmp_path / "model-roots"))

    env_path = dev_up.write_runtime_environment(layout)
    payload = env_path.read_text(encoding="utf-8")

    assert f'export MELIX_MANAGED_MODEL_ROOT="{layout.managed_models_dir}"' in payload
    assert f'export MELIX_MODEL_ROOTS="{tmp_path / "model-roots"}"' in payload
    assert f'export MELIX_AUDIO_RUNTIME_PACK_ROOT="{layout.audio_runtime_packs_dir}"' in payload
    assert f'export MELIX_MODEL_OPS_JOBS_ROOT="{layout.model_ops_jobs_root}"' in payload
    assert f'export MELIX_EVALUATION_JOBS_ROOT="{layout.evaluation_jobs_root}"' in payload
    assert f'export MELIX_COMPUTER_BROKER_SOCKET="{layout.computer_broker_socket_path}"' in payload
    assert (
        'export MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE='
        f'"{layout.computer_broker_capability_path}"'
    ) in payload
    assert 'export MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY="environment"' in payload
    assert 'export MELIX_SERVICE_INSTANCE_NAME="team-a"' in payload
    assert f'export MELIX_PYTHON_BRIDGE_EXECUTABLE="{bridge_python}"' in payload
    assert f'export MELIX_SWIFT_MLX_METALLIB_PATH="{metallib_path}"' in payload
    assert 'export MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE="1"' in payload
    assert 'export MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE="1"' in payload


def test_prepare_swift_worker_launch_cwd_symlinks_runtime_local_default_metallib(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    write_swift_mlx_package_resolved(tmp_path, "0.29.1")
    write_swift_mlx_core_package(tmp_path, "0.29.1")
    layout = make_layout(dev_up, tmp_path)
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    metallib_path = write_mlx_metal_fixture(
        tmp_path / ".venv/lib/python3.13/site-packages",
        "0.29.1",
    )

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
    write_swift_mlx_package_resolved(tmp_path, "0.29.1")
    write_swift_mlx_core_package(tmp_path, "0.29.1")
    layout = make_layout(dev_up, tmp_path)
    metallib_path = write_mlx_metal_fixture(
        tmp_path / ".venv/lib/python3.13/site-packages",
        "0.29.1",
    )

    def fail_rglob(self: Path, pattern: str):
        raise AssertionError("resolve_local_mlx_metallib() should not allocate a Path.rglob() tree")

    monkeypatch.setattr(dev_up.Path, "rglob", fail_rglob)

    assert dev_up.resolve_local_mlx_metallib(tmp_path, uv_cache_dir=layout.uv_cache_dir) == metallib_path.resolve()


def test_read_mlx_metal_dist_info_version_uses_scandir_without_path_glob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_up = load_dev_up_module()

    def tmp_case(name: str) -> Path:
        path = tmp_path / name
        path.mkdir()
        return path

    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_compute_runtime_layout_uses_environment_overrides(
            nested_monkeypatch,
            tmp_case("layout-env"),
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_build_swift_launch_command_builds_then_launches_direct_binary(
            tmp_case("swift-build-debug"),
            nested_monkeypatch,
        )
    test_build_swift_launch_command_prefers_built_binary_when_requested(tmp_case("swift-built-debug"))
    test_build_swift_launch_command_uses_requested_release_configuration(tmp_case("swift-built-release"))
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_build_swift_launch_command_passes_configuration_to_swift_build(
            tmp_case("swift-build-release"),
            nested_monkeypatch,
        )
    test_build_swift_launch_command_reports_missing_built_binary(tmp_case("swift-built-missing"))
    test_dev_up_shell_wrapper_delegates_help_to_python_entrypoint()
    test_parse_args_prefers_built()
    test_parse_args_accepts_release_build_configuration()
    test_parse_args_help_exits_zero(capsys)
    test_parse_args_rejects_unknown_argument(capsys)
    test_parse_args_rejects_missing_build_configuration(capsys)
    test_parse_args_rejects_unsupported_build_configuration(capsys)
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_compute_runtime_layout_uses_short_default_worker_sockets(
            nested_monkeypatch,
            tmp_case("layout-sockets"),
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_compute_runtime_layout_honors_explicit_worker_socket_overrides(
            nested_monkeypatch,
            tmp_case("layout-explicit-sockets"),
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_runtime_layout_helpers_manage_directories_and_artifacts(
            nested_monkeypatch,
            tmp_case("runtime-artifacts"),
        )
    test_dev_down_sources_runtime_env_for_socket_cleanup(tmp_case("dev-down"))
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_start_stack_orchestrates_processes_and_emits_runtime_env(
            nested_monkeypatch,
            tmp_case("start-stack"),
            capsys,
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_start_stack_emits_default_swift_build_configuration(
            nested_monkeypatch,
            tmp_case("start-stack-debug"),
            capsys,
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_start_stack_wraps_http_timeout_with_log_paths(
            nested_monkeypatch,
            tmp_case("http-timeout"),
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        test_start_stack_control_plane_gateway_config_store_overrides_parent_environment(
            nested_monkeypatch,
            tmp_case("control-plane-env"),
        )
    with pytest.MonkeyPatch.context() as nested_monkeypatch:
        launch_root = tmp_case("launch-cwd")
        launch_layout = make_layout(dev_up, launch_root)
        launch_layout.runtime_dir.mkdir(parents=True)
        configured_metallib = launch_root / "configured.metallib"
        configured_metallib.write_text("mlx", encoding="utf-8")
        nested_monkeypatch.setenv(dev_up.SWIFT_MLX_METALLIB_PATH_ENV, os.fspath(configured_metallib))

        assert dev_up.prepare_swift_worker_launch_cwd(
            launch_layout,
            launch_root,
            worker_name="swift-vision-worker",
        ) == launch_layout.runtime_dir / "swift-vision-worker-cwd"

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


def test_read_mlx_metal_dist_info_version_ignores_empty_dist_info_version(tmp_path: Path) -> None:
    dev_up = load_dev_up_module()
    metallib_path = tmp_path / "site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_text("mlx", encoding="utf-8")
    dist_info_path = tmp_path / "site-packages/mlx_metal-.dist-info"
    dist_info_path.mkdir()
    (dist_info_path / "METADATA").write_text("Name: mlx-metal\nSummary: missing version\n", encoding="utf-8")

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) is None


def test_read_mlx_metal_dist_info_version_checks_common_site_packages_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    site_packages = tmp_path / "site-packages"
    metallib_path = write_mlx_metal_fixture(site_packages, "0.31.1")
    scanned: list[Path] = []
    original_scandir = dev_up.os.scandir

    def tracked_scandir(path: Path):
        scanned.append(Path(path))
        return original_scandir(path)

    monkeypatch.setattr(dev_up.os, "scandir", tracked_scandir)

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) == "0.31.1"
    assert scanned == [site_packages]


def test_read_mlx_metal_dist_info_version_caches_resolved_metallib_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    site_packages = tmp_path / "site-packages"
    metallib_path = write_mlx_metal_fixture(site_packages, "0.31.1")
    scanned: list[Path] = []
    original_scandir = dev_up.os.scandir

    def tracked_scandir(path: Path):
        scanned.append(Path(path))
        return original_scandir(path)

    monkeypatch.setattr(dev_up.os, "scandir", tracked_scandir)

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) == "0.31.1"
    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) == "0.31.1"
    assert scanned == [site_packages]


def test_read_mlx_metal_dist_info_version_caches_missing_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    metallib_path = tmp_path / "site-packages/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_text("mlx", encoding="utf-8")
    scanned: list[Path] = []
    original_scandir = dev_up.os.scandir

    def tracked_scandir(path: Path):
        scanned.append(Path(path))
        return original_scandir(path)

    monkeypatch.setattr(dev_up.os, "scandir", tracked_scandir)

    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) is None
    first_scan_count = len(scanned)
    assert first_scan_count > 0
    assert dev_up.read_mlx_metal_dist_info_version(metallib_path) is None
    assert len(scanned) == first_scan_count


def test_read_mlx_metal_dist_info_version_skips_is_dir_when_metadata_has_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    site_packages = tmp_path / "site-packages"
    metallib_path = write_mlx_metal_fixture(site_packages, "0.31.1")
    dist_info_path = site_packages / "mlx_metal-0.31.1.dist-info"

    class FakeEntry:
        name = dist_info_path.name
        path = os.fspath(dist_info_path)

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:  # pragma: no cover - regression sentinel
            raise AssertionError("metadata hits should not stat dist-info directories")

    class FakeScandir:
        def __enter__(self):
            return iter((FakeEntry(),))

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    monkeypatch.setattr(dev_up.os, "scandir", lambda path: FakeScandir())

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
    write_swift_mlx_package_resolved(tmp_path, "0.29.1")
    write_swift_mlx_core_package(tmp_path, "0.29.1")
    layout = replace(make_layout(dev_up, tmp_path), uv_cache_dir=tmp_path / "custom-uv-cache")
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    metallib_path = write_mlx_metal_fixture(layout.uv_cache_dir / "archive-v0/good", "0.29.1")

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
    write_swift_mlx_core_package(repo_root, "0.29.1")
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
    write_swift_mlx_core_package(repo_root, "0.29.1")
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
        seen["pass_fds"] = kwargs["pass_fds"]
        seen["close_fds"] = kwargs["close_fds"]
        kwargs["stdout"].write(b"1\n")
        kwargs["stdout"].flush()
        return FakeProcess()

    monkeypatch.setattr(dev_up.subprocess, "Popen", fake_popen)

    pid = dev_up.spawn_background_process(
        cwd=tmp_path,
        log_path=log_path,
        env_overrides={
            "MELIX_TEST_VALUE": "1",
            "MELIX_CONTROL_PLANE_SOCKET_PATH": "/tmp/approved-control-plane.sock",
        },
        command=["python3", "-c", "print('hello')"],
        pass_fds=(17,),
        base_environment={
            "PATH": "/usr/bin:/bin",
            "MELIX_WORKER_SOCKET_PATH": "/tmp/polluted-worker.sock",
            "MELIX_CONTROL_PLANE_SOCKET_PATH": "/tmp/polluted-control-plane.sock",
            "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD": "99",
        },
        unset_environment_keys=dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS,
    )
    assert pid == 4321
    assert seen["command"] == ["python3", "-c", "print('hello')"]
    assert seen["cwd"] == tmp_path
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["MELIX_TEST_VALUE"] == "1"
    assert env["MELIX_CONTROL_PLANE_SOCKET_PATH"] == "/tmp/approved-control-plane.sock"
    assert "MELIX_WORKER_SOCKET_PATH" not in env
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD" not in env
    assert seen["pass_fds"] == (17,)
    assert seen["close_fds"] is True
    assert log_path.read_text(encoding="utf-8").strip() == "1"

    pid_path = tmp_path / "worker.pid"
    dev_up.write_pid_file(pid_path, 321)
    assert pid_path.read_text(encoding="utf-8") == "321"


def test_spawn_background_process_closes_polluted_private_key_descriptor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    read_descriptor, write_descriptor = os.pipe()
    os.set_inheritable(read_descriptor, True)
    monkeypatch.setenv(
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD",
        str(read_descriptor),
    )
    log_path = tmp_path / "private-fd-probe.log"
    probe = (
        "import os, sys; fd = int(sys.argv[1]); "
        "env_visible = 'MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD' in os.environ; "
        "\ntry:\n os.fstat(fd); fd_open = True\nexcept OSError:\n fd_open = False\n"
        "print(f'env_visible={env_visible} fd_open={fd_open}', flush=True)"
    )
    try:
        pid = dev_up.spawn_background_process(
            cwd=tmp_path,
            log_path=log_path,
            env_overrides={},
            command=[sys.executable, "-c", probe, str(read_descriptor)],
            pass_fds=(),
            unset_environment_keys=dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS,
        )
        _, status = os.waitpid(pid, 0)
    finally:
        os.close(read_descriptor)
        os.close(write_descriptor)

    assert os.waitstatus_to_exitcode(status) == 0
    assert log_path.read_text(encoding="utf-8").strip() == (
        "env_visible=False fd_open=False"
    )


def test_active_mcp_credential_environment_keys_resolves_stdio_and_http_references(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    explicit_config = tmp_path / "explicit-mcp.json"
    explicit_config.write_text(
        json.dumps(
            {
                "sources": [
                    {"source_id": "legacy", "namespaces": ["tools.read"]},
                    {
                        "source_id": "stdio",
                        "transport": {
                            "kind": "stdio",
                            "command": "/usr/bin/true",
                            "environment_references": {
                                "CHILD_TOKEN": "PARENT_STDIO_TOKEN",
                            },
                        },
                    },
                    {
                        "source_id": "http",
                        "transport": {
                            "kind": "streamable_http",
                            "url": "https://mcp.example.test/rpc",
                            "header_environment_references": {
                                "Authorization": "PARENT_HTTP_AUTH",
                                "X-API-Key": "PARENT_HTTP_API_KEY",
                            },
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    default_config = tmp_path / "home/config/mcp-tools.json"
    default_config.parent.mkdir(parents=True)
    default_config.write_text("not-json", encoding="utf-8")

    keys = dev_up.active_mcp_credential_environment_keys(
        environment={
            "MELIX_MCP_CONFIG_PATH": str(explicit_config),
            "MELIX_HOME": str(tmp_path / "home"),
            "PARENT_STDIO_TOKEN": "sensitive-but-never-returned",
        },
    )

    assert keys == (
        "PARENT_HTTP_API_KEY",
        "PARENT_HTTP_AUTH",
        "PARENT_STDIO_TOKEN",
    )
    assert "sensitive-but-never-returned" not in repr(keys)


def test_active_mcp_credential_environment_keys_uses_melix_home_and_allows_missing_values(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    config_path = tmp_path / "home/config/mcp-tools.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "stdio",
                        "transport": {
                            "kind": "stdio",
                            "command": "/usr/bin/true",
                            "environment_references": {
                                "CHILD_TOKEN": "UNSET_PARENT_TOKEN",
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert dev_up.active_mcp_credential_environment_keys(
        environment={"MELIX_HOME": str(tmp_path / "home")},
    ) == ("UNSET_PARENT_TOKEN",)
    assert dev_up.active_mcp_credential_environment_keys(
        environment={},
        melix_home_dir=tmp_path / "no-config-home",
    ) == ()


def test_active_mcp_config_path_uses_mapping_home_and_standardizes_tilde(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    config_path = tmp_path / "operator/config/mcp-tools.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"sources":[]}', encoding="utf-8")
    environment = {
        "HOME": str(tmp_path / "operator"),
        "MELIX_MCP_CONFIG_PATH": "~/config/../config/mcp-tools.json",
    }

    assert dev_up.normalized_explicit_mcp_config_path(environment) == str(config_path)
    assert dev_up.active_mcp_credential_environment_keys(environment=environment) == ()
    environment["MELIX_MCP_CONFIG_PATH"] = "~//config/mcp-tools.json"
    assert dev_up.normalized_explicit_mcp_config_path(environment) == str(config_path)
    environment["MELIX_MCP_CONFIG_PATH"] = f"/{config_path}"
    assert dev_up.normalized_explicit_mcp_config_path(environment) == str(config_path)


def test_default_mcp_config_discovery_rejects_relative_mapping_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.productization import mcp_credential_environment

    fallback_home = tmp_path / "current-user"
    config_path = fallback_home / ".melix/config/mcp-tools.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"sources":[{"source_id":"fallback","transport":{"kind":"stdio","command":"/usr/bin/true","environment_references":{"TOKEN":"FALLBACK_SECRET"}}}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mcp_credential_environment,
        "_current_user_home",
        lambda: fallback_home,
    )

    assert mcp_credential_environment.active_mcp_credential_environment_keys(
        environment={"HOME": "relative-home"},
    ) == ("FALLBACK_SECRET",)


def test_mcp_credential_environment_cli_prints_keys_and_normalized_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from worker.productization import mcp_credential_environment

    config_path = tmp_path / "config/mcp-tools.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"sources":[{"source_id":"cli","transport":{"kind":"stdio","command":"/usr/bin/true","environment_references":{"TOKEN":"CLI_SECRET"}}}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MELIX_MCP_CONFIG_PATH", str(config_path))

    assert mcp_credential_environment.main(
        ["--melix-home", str(tmp_path)]
    ) == 0
    assert capsys.readouterr().out == "CLI_SECRET\n"
    assert mcp_credential_environment.main(
        ["--melix-home", str(tmp_path), "--normalize-explicit-path"]
    ) == 0
    assert capsys.readouterr().out == f"{config_path}\n"
    assert mcp_credential_environment._current_user_home().is_absolute()


@pytest.mark.parametrize(
    "fixture_kind",
    (
        "source-key",
        "source-key-aggregate",
        "child-key",
        "child-key-aggregate",
        "http-header",
        "http-header-syntax",
        "static-header-syntax",
        "static-credential-header",
        "static-header-aggregate",
        "static-header-count",
        "mixed-http-header-count",
        "http-header-name-conflict",
        "reference-count",
    ),
)
def test_mcp_credential_environment_rejects_exec_unsafe_key_bytes(
    tmp_path: Path,
    fixture_kind: str,
) -> None:
    from worker.productization import mcp_credential_environment

    field_name = "environment_references"
    if fixture_kind == "source-key-aggregate":
        references = {
            f"TOKEN_{index}": f"KEY_{index}_" + "A" * (247 - len(str(index)))
            for index in range(130)
        }
    elif fixture_kind == "source-key":
        references = {"TOKEN": "A" * 256}
    elif fixture_kind == "child-key":
        references = {"A" * 256: "SECRET"}
    elif fixture_kind == "child-key-aggregate":
        references = {
            f"KEY_{index}_" + "A" * (247 - len(str(index))): "SECRET"
            for index in range(130)
        }
    elif fixture_kind == "reference-count":
        references = {
            f"TOKEN_{index}": "SECRET"
            for index in range(1_025)
        }
    elif fixture_kind == "http-header":
        field_name = "header_environment_references"
        references = {"X" * 256: "SECRET"}
    elif fixture_kind == "http-header-syntax":
        field_name = "header_environment_references"
        references = {"Bad Header": "SECRET"}
    elif fixture_kind == "static-header-syntax":
        field_name = "headers"
        references = {"Bad\r\nHeader": "visible"}
    elif fixture_kind == "static-credential-header":
        field_name = "headers"
        references = {"Authorization": "visible"}
    elif fixture_kind == "static-header-aggregate":
        field_name = "headers"
        references = {
            f"X-Key-{index}-" + "A" * (245 - len(str(index))): "visible"
            for index in range(130)
        }
    elif fixture_kind == "mixed-http-header-count":
        config_path = tmp_path / "mcp-tools.json"
        config_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_id": "mixed-http-headers",
                            "transport": {
                                "kind": "streamable_http",
                                "url": "https://mcp.example.test/rpc",
                                "headers": {
                                    f"X-Static-{index}": "visible"
                                    for index in range(600)
                                },
                                "header_environment_references": {
                                    f"X-Secret-{index}": "SECRET"
                                    for index in range(600)
                                },
                            }
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="invalid"):
            mcp_credential_environment.active_mcp_credential_environment_keys(
                environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
            )
        return
    elif fixture_kind == "http-header-name-conflict":
        config_path = tmp_path / "mcp-tools.json"
        config_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_id": "conflicting-http-headers",
                            "transport": {
                                "kind": "streamable_http",
                                "url": "https://mcp.example.test/rpc",
                                "headers": {"X-Custom": "visible"},
                                "header_environment_references": {
                                    "x-custom": "SECRET"
                                },
                            }
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(RuntimeError, match="invalid"):
            mcp_credential_environment.active_mcp_credential_environment_keys(
                environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
            )
        return
    else:
        field_name = "headers"
        references = {
            f"X-Key-{index}": "visible"
            for index in range(1_025)
        }
    config_path = tmp_path / "mcp-tools.json"
    if field_name == "environment_references":
        transport = {
            "kind": "stdio",
            "command": "/usr/bin/true",
            field_name: references,
        }
    else:
        transport = {
            "kind": "streamable_http",
            "url": "https://mcp.example.test/rpc",
            field_name: references,
        }
    config_path.write_text(
        json.dumps(
            {"sources": [{"source_id": "bounded-fixture", "transport": transport}]}
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="invalid"):
        mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


def test_mcp_credential_key_union_deduplicates_and_revalidates_aggregate() -> None:
    from worker.productization import mcp_credential_environment

    assert mcp_credential_environment.bounded_mcp_credential_environment_key_union(
        ("FIRST_SECRET", "SHARED_SECRET"),
        ("SHARED_SECRET", "SECOND_SECRET"),
    ) == ("FIRST_SECRET", "SHARED_SECRET", "SECOND_SECRET")
    initial = tuple(
        f"INITIAL_{index}_" + "A" * (240 - len(f"INITIAL_{index}_"))
        for index in range(70)
    )
    current = tuple(
        f"CURRENT_{index}_" + "B" * (240 - len(f"CURRENT_{index}_"))
        for index in range(70)
    )
    with pytest.raises(RuntimeError, match="invalid"):
        mcp_credential_environment.bounded_mcp_credential_environment_key_union(
            initial,
            current,
        )


def test_python_worker_parent_environment_is_allowlisted_and_adds_only_initial_refs() -> None:
    from worker.productization import mcp_credential_environment

    environment = {
        "PATH": "/usr/bin",
        "MELIX_DEV_SPEECH_MODEL_PATH": "/models/speech",
        "INITIAL_MCP_SECRET": "credential-value",
        "AWS_SECRET_ACCESS_KEY": "aws-sensitive-value",
        "GITHUB_TOKEN": "github-sensitive-value",
        "UNREFERENCED_SECRET": "other-sensitive-value",
        "MELIX_GATEWAY_API_KEYS_JSON": "gateway-sensitive-value",
    }

    result = mcp_credential_environment.python_worker_parent_environment(
        environment,
        credential_keys=("INITIAL_MCP_SECRET",),
    )

    assert result == {
        "PATH": "/usr/bin",
        "MELIX_DEV_SPEECH_MODEL_PATH": "/models/speech",
        "INITIAL_MCP_SECRET": "credential-value",
        "MELIX_MCP_CREDENTIAL_ENV_KEYS": "INITIAL_MCP_SECRET",
    }


def test_frozen_mcp_credential_snapshot_requires_restart_for_new_source_key() -> None:
    from worker.productization import mcp_credential_environment

    assert mcp_credential_environment.validate_frozen_mcp_credential_environment_key_snapshot(
        ("FIRST_SECRET", "SECOND_SECRET"),
        ("SECOND_SECRET",),
    ) == ("FIRST_SECRET", "SECOND_SECRET")
    with pytest.raises(RuntimeError, match="restart Melix"):
        mcp_credential_environment.validate_frozen_mcp_credential_environment_key_snapshot(
            ("FIRST_SECRET",),
            ("FIRST_SECRET", "NEW_SECRET"),
        )


def test_mcp_credential_preflight_rejects_uncovered_invalid_shapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from worker.productization import mcp_credential_environment

    with pytest.raises(ValueError, match="lone surrogate"):
        mcp_credential_environment._validate_json_tree({"\ud800": "value"})
    with pytest.raises(RuntimeError, match="invalid"):
        mcp_credential_environment.bounded_mcp_credential_environment_key_union(
            ("not a valid key",)
        )

    invalid_payloads = (
        {"default_parser_mode": 1, "sources": []},
        {
            "sources": [
                {
                    "source_id": "headers-not-object",
                    "transport": {
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "headers": [],
                    },
                }
            ]
        },
        {
            "sources": [
                {
                    "source_id": "duplicate-header",
                    "transport": {
                        "kind": "streamable_http",
                        "url": "https://mcp.example.test/rpc",
                        "headers": {"X-Test": "first", "x-test": "second"},
                    },
                }
            ]
        },
        {
            "sources": [
                {
                    "source_id": "references-not-object",
                    "transport": {
                        "kind": "stdio",
                        "command": "/usr/bin/true",
                        "environment_references": [],
                    },
                }
            ]
        },
        {
            "sources": [
                {
                    "source_id": "reference-value-not-string",
                    "transport": {
                        "kind": "stdio",
                        "command": "/usr/bin/true",
                        "environment_references": {"TOKEN": 1},
                    },
                }
            ]
        },
    )
    config_path = tmp_path / "mcp-tools.json"
    for payload in invalid_payloads:
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RuntimeError, match="invalid"):
            mcp_credential_environment.active_mcp_credential_environment_keys(
                environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
            )

    config_path.write_text('{"sources": []}', encoding="utf-8")
    original_open = mcp_credential_environment.os.open
    resolved_config_path = config_path.resolve()

    def fail_config_open(
        path: os.PathLike[str] | str,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        if Path(path) == resolved_config_path:
            raise OSError("read failed")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(mcp_credential_environment.os, "open", fail_config_open)
    with pytest.raises(RuntimeError, match="unreadable"):
        mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


def test_mcp_credential_cli_covers_frozen_snapshot_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from worker.productization import mcp_credential_environment

    monkeypatch.setenv("MELIX_MCP_CONFIG_PATH", str(tmp_path / "mcp-tools.json"))
    assert mcp_credential_environment.main(["--normalize-explicit-path"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "mcp-tools.json")

    monkeypatch.setattr(
        mcp_credential_environment.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(b"FIRST_SECRET\nSECOND_SECRET\n")),
    )
    assert mcp_credential_environment.main(["--validate-key-union"]) == 0
    assert capsys.readouterr().out.splitlines() == ["FIRST_SECRET", "SECOND_SECRET"]

    monkeypatch.setattr(
        mcp_credential_environment.sys,
        "stdin",
        SimpleNamespace(
            buffer=io.BytesIO(b"FIRST_SECRET\nSECOND_SECRET\0SECOND_SECRET\n")
        ),
    )
    assert mcp_credential_environment.main(["--validate-frozen-key-snapshot"]) == 0
    assert capsys.readouterr().out.splitlines() == ["FIRST_SECRET", "SECOND_SECRET"]

    with pytest.raises(SystemExit):
        mcp_credential_environment.main([])


@pytest.mark.parametrize(
    "source_payload",
    (
        {"transport": None},
        {"source_id": "null-transport", "transport": None},
        {"source_id": "bad source"},
        {"source_id": " MCP-Source ", "transport": None},
        {
            "source_id": "unknown-kind",
            "transport": {"kind": "unknown"},
        },
        {
            "source_id": "missing-command",
            "transport": {"kind": "stdio"},
        },
        {
            "source_id": "invalid-arguments",
            "transport": {
                "kind": "stdio",
                "command": "/usr/bin/true",
                "arguments": [1],
            },
        },
        {
            "source_id": "invalid-working-directory",
            "transport": {
                "kind": "stdio",
                "command": "/usr/bin/true",
                "working_directory": 1,
            },
        },
        {
            "source_id": "nul-command",
            "transport": {"kind": "stdio", "command": "/usr/bin/true\0bad"},
        },
        {
            "source_id": "relative-working-directory",
            "transport": {
                "kind": "stdio",
                "command": "/usr/bin/true",
                "working_directory": "relative",
            },
        },
        {
            "source_id": "missing-url",
            "transport": {"kind": "streamable_http"},
        },
        {
            "source_id": "stdio-with-http-field",
            "transport": {
                "kind": "stdio",
                "command": "/usr/bin/true",
                "header_environment_references": {
                    "Authorization": "CROSS_KIND_SECRET"
                },
            },
        },
        {
            "source_id": "http-with-stdio-field",
            "transport": {
                "kind": "streamable_http",
                "url": "https://mcp.example.test/rpc",
                "environment_references": {"TOKEN": "CROSS_KIND_SECRET"},
            },
        },
        {
            "source_id": "public-cleartext-http",
            "transport": {
                "kind": "streamable_http",
                "url": "http://example.com/mcp",
            },
        },
        {
            "source_id": "http-userinfo",
            "transport": {
                "kind": "streamable_http",
                "url": "https://user@example.com/mcp",
            },
        },
        {
            "source_id": "http-fragment",
            "transport": {
                "kind": "streamable_http",
                "url": "https://example.com/mcp#fragment",
            },
        },
        {
            "source_id": "http-empty-fragment",
            "transport": {
                "kind": "streamable_http",
                "url": "https://example.com/mcp#",
            },
        },
        {
            "source_id": "malformed-ipv6",
            "transport": {
                "kind": "streamable_http",
                "url": "http://[::1/mcp",
            },
        },
        {"source_id": "invalid-enabled", "enabled": "yes"},
        {"source_id": "invalid-namespaces", "namespaces": [1]},
        {"source_id": "invalid-timeout", "request_timeout_ms": -1},
        {"source_id": "invalid-redaction", "redaction_terms": [1]},
        {"source_id": "invalid-revision", "configuration_revision": 1},
    ),
)
def test_mcp_credential_preflight_rejects_invalid_source_transport_schema(
    tmp_path: Path,
    source_payload: dict[str, object],
) -> None:
    from worker.productization import mcp_credential_environment

    sources = [source_payload]
    if source_payload.get("source_id") == " MCP-Source ":
        sources.append({"source_id": "mcp-source"})
    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text(json.dumps({"sources": sources}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="invalid"):
        mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


def test_mcp_credential_preflight_accepts_ipv6_loopback_http(
    tmp_path: Path,
) -> None:
    from worker.productization import mcp_credential_environment

    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "ipv6-loopback",
                        "transport": {
                            "kind": "streamable_http",
                            "url": "http://[::1]:12436/mcp",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert mcp_credential_environment.active_mcp_credential_environment_keys(
        environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
    ) == ()


@pytest.mark.parametrize(
    "encoded_payload",
    (
        b'{"sources":[{"source_id":"duplicate","source_id":"other"}]}',
        b'{"sources":[],"unknown":NaN}',
        b'{"sources":[],"unknown":1.0}',
        b'{"sources":[],"unknown":1e0}',
        b'{"sources":[],"unknown":1e400}',
        b'{"sources":[],"unknown":"\\ud800"}',
    ),
)
def test_mcp_credential_preflight_rejects_noncanonical_json(
    tmp_path: Path,
    encoded_payload: bytes,
) -> None:
    from worker.productization import mcp_credential_environment

    config_path = tmp_path / "mcp-tools.json"
    config_path.write_bytes(encoded_payload)

    with pytest.raises(RuntimeError, match="invalid"):
        mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


@pytest.mark.parametrize("budget_kind", ("depth", "tokens", "members"))
def test_mcp_credential_preflight_rejects_json_structure_over_budget(
    tmp_path: Path,
    budget_kind: str,
) -> None:
    from worker.productization import mcp_credential_environment

    if budget_kind == "depth":
        unknown: object = 0
        for _ in range(140):
            unknown = [unknown]
    elif budget_kind == "tokens":
        unknown = list(range(16_384))
    else:
        unknown = {f"key-{index}": 0 for index in range(8_193)}
    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text(
        json.dumps({"sources": [], "unknown": unknown}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="invalid"):
        mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


def test_mcp_credential_preflight_accepts_json_structure_below_budget(
    tmp_path: Path,
) -> None:
    from worker.productization import mcp_credential_environment

    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text(
        json.dumps({"sources": [], "unknown": list(range(16_000))}),
        encoding="utf-8",
    )

    assert mcp_credential_environment.active_mcp_credential_environment_keys(
        environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
    ) == ()


@pytest.mark.parametrize(
    ("array_layers", "accepted"),
    ((126, True), (127, False)),
)
def test_mcp_credential_preflight_enforces_exact_json_depth_budget(
    tmp_path: Path,
    array_layers: int,
    accepted: bool,
) -> None:
    from worker.productization import mcp_credential_environment

    unknown: object = 0
    for _ in range(array_layers):
        unknown = [unknown]
    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text(
        json.dumps({"sources": [], "unknown": unknown}),
        encoding="utf-8",
    )

    if accepted:
        assert mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        ) == ()
    else:
        with pytest.raises(RuntimeError, match="invalid"):
            mcp_credential_environment.active_mcp_credential_environment_keys(
                environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
            )




@pytest.mark.parametrize(
    ("fixture_kind", "expected_message"),
    (
        ("missing", "unreadable"),
        ("directory", "unreadable"),
        ("invalid-json", "invalid"),
        ("invalid-reference", "invalid"),
        ("reserved-config-reference", "invalid"),
        ("reserved-private-reference", "invalid"),
        ("non-object", "invalid"),
        ("missing-sources", "invalid"),
        ("bad-source", "invalid"),
        ("bad-transport", "invalid"),
        ("bad-reference-map", "invalid"),
        ("non-string-reference", "invalid"),
        ("invalid-child-key", "invalid"),
        ("oversized", "too large"),
    ),
)
def test_active_mcp_credential_environment_keys_fails_closed_for_bad_config(
    tmp_path: Path,
    fixture_kind: str,
    expected_message: str,
) -> None:
    dev_up = load_dev_up_module()
    config_path = tmp_path / "mcp-tools.json"
    if fixture_kind == "directory":
        config_path.mkdir()
    elif fixture_kind == "invalid-json":
        config_path.write_text("{", encoding="utf-8")
    elif fixture_kind == "invalid-reference":
        config_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_id": "stdio",
                            "transport": {
                                "kind": "stdio",
                                "command": "/usr/bin/true",
                                "environment_references": {
                                    "CHILD_TOKEN": "invalid-parent-key",
                                },
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    elif fixture_kind in {"reserved-config-reference", "reserved-private-reference"}:
        reserved_key = (
            "MELIX_MCP_CONFIG_PATH"
            if fixture_kind == "reserved-config-reference"
            else "MELIX_WORKER_SOCKET_PATH"
        )
        config_path.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_id": "stdio",
                            "transport": {
                                "kind": "stdio",
                                "command": "/usr/bin/true",
                                "environment_references": {
                                    "CHILD_TOKEN": reserved_key,
                                },
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    elif fixture_kind == "non-object":
        config_path.write_text("[]", encoding="utf-8")
    elif fixture_kind == "missing-sources":
        config_path.write_text("{}", encoding="utf-8")
    elif fixture_kind == "bad-source":
        config_path.write_text('{"sources":[1]}', encoding="utf-8")
    elif fixture_kind == "bad-transport":
        config_path.write_text(
            '{"sources":[{"source_id":"bad","transport":1}]}',
            encoding="utf-8",
        )
    elif fixture_kind == "bad-reference-map":
        config_path.write_text(
            '{"sources":[{"source_id":"bad","transport":{"kind":"stdio","environment_references":[]}}]}',
            encoding="utf-8",
        )
    elif fixture_kind == "non-string-reference":
        config_path.write_text(
            '{"sources":[{"source_id":"bad","transport":{"kind":"stdio","environment_references":{"TOKEN":1}}}]}',
            encoding="utf-8",
        )
    elif fixture_kind == "invalid-child-key":
        config_path.write_text(
            '{"sources":[{"source_id":"bad","transport":{"kind":"stdio","environment_references":{"bad-child":"PARENT_TOKEN"}}}]}',
            encoding="utf-8",
        )
    elif fixture_kind == "oversized":
        config_path.write_bytes(b" " * (dev_up._MAX_MCP_CONFIG_BYTES + 1))

    with pytest.raises(RuntimeError, match=expected_message):
        dev_up.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


def test_active_mcp_config_descriptor_rejects_fifo_substituted_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worker.productization import mcp_credential_environment

    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text('{"sources":[]}', encoding="utf-8")
    original_open = mcp_credential_environment.os.open
    did_substitute = False

    def substitute_then_open(path: os.PathLike[str] | str, flags: int) -> int:
        nonlocal did_substitute
        if not did_substitute:
            config_path.unlink()
            os.mkfifo(config_path)
            did_substitute = True
        return original_open(path, flags)

    monkeypatch.setattr(mcp_credential_environment.os, "open", substitute_then_open)

    with pytest.raises(RuntimeError, match="unreadable"):
        mcp_credential_environment.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )
    assert did_substitute is True


def test_active_mcp_config_descriptor_accepts_regular_symlink_target(
    tmp_path: Path,
) -> None:
    from worker.productization import mcp_credential_environment

    target_path = tmp_path / "mcp-tools-target.json"
    target_path.write_text('{"sources":[]}', encoding="utf-8")
    config_path = tmp_path / "mcp-tools.json"
    config_path.symlink_to(target_path)

    assert mcp_credential_environment.active_mcp_credential_environment_keys(
        environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
    ) == ()


@pytest.mark.parametrize("configured_path", ("relative/mcp-tools.json", "~someone/mcp-tools.json"))
def test_active_mcp_credential_environment_keys_rejects_relative_explicit_path(
    configured_path: str,
) -> None:
    dev_up = load_dev_up_module()

    with pytest.raises(RuntimeError, match="invalid"):
        dev_up.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": configured_path},
        )


@pytest.mark.parametrize(
    "reserved_key",
    (
        "MELIX_GATEWAY_API_KEYS_JSON",
        "MELIX_GATEWAY_BEARER_TOKEN",
        "MELIX_MCP_HIGH_RISK_ALLOWLIST",
        "MELIX_DEV_TEXT_MODEL_PATH",
        "MELIX_DEV_VLM_MODEL_PATH",
        "MELIX_ACTIVE_RUNTIME_PATH",
        "MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT",
    ),
)
def test_active_mcp_credential_environment_keys_rejects_role_contract_collisions(
    tmp_path: Path,
    reserved_key: str,
) -> None:
    dev_up = load_dev_up_module()
    config_path = tmp_path / "mcp-tools.json"
    config_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "transport": {
                            "environment_references": {"TOKEN": reserved_key}
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="invalid"):
        dev_up.active_mcp_credential_environment_keys(
            environment={"MELIX_MCP_CONFIG_PATH": str(config_path)},
        )


def test_computer_authorization_helpers_keep_capabilities_private(
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    capability_path = tmp_path / "broker-capability.bin"
    capability = b"C" * 32

    dev_up.write_private_capability(capability_path, capability)

    assert capability_path.read_bytes() == capability
    assert stat.S_IMODE(capability_path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        dev_up.write_private_capability(capability_path, b"D" * 32)

    descriptor = dev_up.private_key_read_pipe(b"K" * 32)
    assert dev_up.read_exact_descriptor(
        descriptor,
        32,
        timeout_seconds=1.0,
    ) == b"K" * 32

    with pytest.raises(RuntimeError, match="32 bytes"):
        dev_up.private_key_read_pipe(b"short")


def test_computer_authorization_helpers_fail_closed_on_io_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    with pytest.raises(RuntimeError, match="must be bounded"):
        dev_up.write_private_capability(tmp_path / "short.bin", b"short")

    monkeypatch.setattr(dev_up.os, "write", lambda descriptor, payload: 0)
    with pytest.raises(RuntimeError, match="complete private descriptor payload"):
        dev_up.write_all_descriptor(17, b"payload")


def test_computer_authorization_public_key_channel_times_out_and_rejects_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_up = load_dev_up_module()
    read_descriptor, write_descriptor = os.pipe()
    monkeypatch.setattr(dev_up.select, "select", lambda *args: ([], [], []))
    try:
        with pytest.raises(RuntimeError, match="Timed out"):
            dev_up.read_exact_descriptor(
                read_descriptor,
                32,
                timeout_seconds=0.0,
            )
    finally:
        os.close(write_descriptor)

    eof_read_descriptor, eof_write_descriptor = os.pipe()
    os.close(eof_write_descriptor)
    monkeypatch.setattr(
        dev_up.select,
        "select",
        lambda descriptors, *_: (descriptors, [], []),
    )
    with pytest.raises(RuntimeError, match="closed the authorization key channel"):
        dev_up.read_exact_descriptor(
            eof_read_descriptor,
            32,
            timeout_seconds=1.0,
        )


def test_wait_for_private_socket_accepts_private_socket_and_bounds_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    socket_path = tmp_path / "broker.sock"
    original_stat = dev_up.Path.stat

    def private_socket_stat(path: Path):
        if path == socket_path:
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600)
        return original_stat(path)

    monkeypatch.setattr(dev_up.Path, "stat", private_socket_stat)
    dev_up.wait_for_private_socket(socket_path, timeout_seconds=0.1)
    monkeypatch.setattr(dev_up.Path, "stat", original_stat)

    clock = iter([0.0, 0.0, 1.0])
    monkeypatch.setattr(dev_up.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(dev_up.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="did not become ready"):
        dev_up.wait_for_private_socket(
            tmp_path / "missing.sock",
            timeout_seconds=0.1,
        )


def test_start_stack_rejects_invalid_computer_authorization_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(dev_up, "rollback_started_stack", lambda current_layout: None)

    with pytest.raises(RuntimeError, match="exactly 32 bytes"):
        dev_up.start_stack(
            dev_up.DevUpOptions(),
            computer_authorization_private_key=b"invalid",
        )


def test_start_stack_rolls_back_partial_runtime_when_credentials_drift_after_first_spawn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    snapshots = iter(
        (
            ("INITIAL_SECRET",),
            ("INITIAL_SECRET",),
            ("INITIAL_SECRET", "NEW_SECRET"),
        )
    )
    spawned: list[dict[str, object]] = []
    rolled_back: list[Path] = []

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "active_mcp_credential_environment_keys",
        lambda **kwargs: next(snapshots),
    )
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda *args, **kwargs: ["melix-text-worker-swift"],
    )
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda *args, **kwargs: layout.runtime_dir / "swift-text-worker-cwd",
    )
    monkeypatch.setattr(
        dev_up,
        "spawn_background_process",
        lambda **kwargs: spawned.append(kwargs) or 4242,
    )
    monkeypatch.setattr(
        dev_up,
        "rollback_started_stack",
        lambda current_layout: rolled_back.append(current_layout.runtime_dir),
    )
    monkeypatch.setattr(dev_up.time, "perf_counter_ns", lambda: 123)

    with pytest.raises(RuntimeError, match="restart Melix"):
        dev_up.start_stack(
            dev_up.DevUpOptions(),
            computer_authorization_private_key=b"K" * 32,
        )

    assert len(spawned) == 1
    assert (layout.runtime_dir / "swift-text-worker.pid").read_text(encoding="utf-8") == "4242"
    assert rolled_back == [layout.runtime_dir]


def test_start_stack_does_not_roll_back_an_existing_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    (layout.runtime_dir / "swift-text-worker.pid").write_text("999", encoding="utf-8")
    rolled_back: list[Path] = []

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_up,
        "rollback_started_stack",
        lambda current_layout: rolled_back.append(current_layout.runtime_dir),
    )

    with pytest.raises(RuntimeError, match="Run scripts/dev_down.sh first"):
        dev_up.start_stack(dev_up.DevUpOptions())

    assert rolled_back == []
    assert (layout.runtime_dir / "swift-text-worker.pid").read_text(encoding="utf-8") == "999"


def test_start_stack_preserves_startup_and_rollback_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)

    def fail_after_ownership(*args: object, **kwargs: object) -> bytes:
        kwargs["on_ownership_acquired"]()
        raise RuntimeError("startup failed")

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(dev_up, "_start_owned_stack", fail_after_ownership)
    monkeypatch.setattr(
        dev_up,
        "rollback_started_stack",
        lambda current_layout: (_ for _ in ()).throw(RuntimeError("rollback failed")),
    )

    with pytest.raises(RuntimeError, match="startup failed rollback failed"):
        dev_up.start_stack(dev_up.DevUpOptions())


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

    original_open = dev_up.Path.open
    first_append_attempt = True

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object):
        nonlocal first_append_attempt
        if self == log_path and mode == "ab" and first_append_attempt:
            first_append_attempt = False
            raise PermissionError("stale root-owned log")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(dev_up.Path, "open", fake_open)
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
    monkeypatch.setenv("MELIX_TEST_MCP_TOKEN", "ready-probe-secret")

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
        unset_environment_keys=("MELIX_TEST_MCP_TOKEN",),
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
    assert "MELIX_TEST_MCP_TOKEN" not in env
    assert "ready-probe-secret" not in repr(seen)


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
    assert f'export MELIX_COMPUTER_BROKER_SOCKET="{layout.computer_broker_socket_path}"' in content
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY" not in content
    assert "MELIX_PYTHON_BRIDGE_EXECUTABLE" not in content


def test_dev_down_sources_runtime_env_for_socket_cleanup(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    python_socket = tmp_path / "short-python.sock"
    swift_socket = tmp_path / "short-swift.sock"
    swift_vision_socket = tmp_path / "short-swift-vision.sock"
    control_plane_socket = tmp_path / "short-control-plane.sock"
    computer_dir = tmp_path / "short-computer"
    computer_dir.mkdir()
    computer_socket = computer_dir / "broker.sock"
    computer_capability = computer_dir / "verification-capability.bin"
    control_plane_lock = Path(f"{control_plane_socket}.lock")
    computer_lock = Path(f"{computer_socket}.lock")
    control_metrics = tmp_path / "control-plane-metrics.json"
    swift_metrics = tmp_path / "swift-text-worker-metrics.json"
    swift_vision_metrics = tmp_path / "swift-vision-worker-metrics.json"
    python_metrics = tmp_path / "python-worker-metrics.json"
    for artifact in (
        python_socket,
        swift_socket,
        swift_vision_socket,
        control_plane_socket,
        control_plane_lock,
        computer_socket,
        computer_lock,
        computer_capability,
        control_metrics,
        swift_metrics,
        swift_vision_metrics,
        python_metrics,
    ):
        artifact.write_text("stale", encoding="utf-8")
    (runtime_dir / "env.sh").write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                f"export MELIX_WORKER_SOCKET_PATH={shlex.quote(os.fspath(python_socket))}",
                f"export MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH={shlex.quote(os.fspath(swift_socket))}",
                f"export MELIX_SWIFT_VISION_WORKER_SOCKET_PATH={shlex.quote(os.fspath(swift_vision_socket))}",
                f"export MELIX_CONTROL_PLANE_SOCKET_PATH={shlex.quote(os.fspath(control_plane_socket))}",
                f"export MELIX_COMPUTER_BROKER_SOCKET={shlex.quote(os.fspath(computer_socket))}",
                f"export MELIX_CONTROL_PLANE_METRICS_PATH={shlex.quote(os.fspath(control_metrics))}",
                f"export MELIX_SWIFT_TEXT_WORKER_METRICS_PATH={shlex.quote(os.fspath(swift_metrics))}",
                f"export MELIX_SWIFT_VISION_WORKER_METRICS_PATH={shlex.quote(os.fspath(swift_vision_metrics))}",
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
    assert not swift_vision_socket.exists()
    assert not control_plane_socket.exists()
    assert not control_plane_lock.exists()
    assert not computer_socket.exists()
    assert not computer_lock.exists()
    assert not computer_capability.exists()
    assert not computer_dir.exists()
    assert not control_metrics.exists()
    assert not swift_metrics.exists()
    assert not swift_vision_metrics.exists()
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
    pid_values = iter([101, 202, 303, 404, 505])
    private_key = b"K" * 32
    public_key = b"P" * 32
    mcp_config = tmp_path / "mcp-tools.json"
    mcp_config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "stdio",
                        "transport": {
                            "kind": "stdio",
                            "command": "/usr/bin/true",
                            "environment_references": {
                                "TOKEN": "MELIX_TEST_STDIO_MCP_TOKEN",
                            },
                        },
                    },
                    {
                        "source_id": "http",
                        "transport": {
                            "kind": "streamable_http",
                            "url": "https://mcp.example.test/rpc",
                            "header_environment_references": {
                                "Authorization": "MELIX_TEST_HTTP_MCP_AUTH",
                            },
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE", "1")
    monkeypatch.setenv("MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE", "1")
    monkeypatch.setenv("MELIX_MCP_CONFIG_PATH", str(mcp_config))
    monkeypatch.setenv("MELIX_TEST_STDIO_MCP_TOKEN", "stdio-sensitive-value")
    monkeypatch.setenv("MELIX_TEST_HTTP_MCP_AUTH", "http-sensitive-value")
    monkeypatch.setenv("MELIX_TEST_FUTURE_MCP_TOKEN", "future-sensitive-value")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-sensitive-value")
    monkeypatch.setenv("GITHUB_TOKEN", "github-sensitive-value")
    monkeypatch.setenv("MELIX_GATEWAY_AUTH_MODE", "api-key")
    monkeypatch.setenv("MELIX_GATEWAY_API_KEYS_JSON", '[{"id":"test","secret":"gateway-secret"}]')
    monkeypatch.setenv("MELIX_MCP_HIGH_RISK_ALLOWLIST", "trusted.exec")
    monkeypatch.setenv("MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT", "1")

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    stub_computer_broker_startup(
        dev_up,
        monkeypatch,
        public_key=public_key,
        calls=calls,
    )
    def fake_build_swift_launch_command(
        repo_root: Path,
        *,
        package_path: str,
        product_name: str,
        prefer_built: bool,
        build_configuration: str = "debug",
    ) -> list[str]:
        calls.append(
            (
                "swift-launch",
                {
                    "build_configuration": build_configuration,
                    "package_path": package_path,
                    "prefer_built": prefer_built,
                    "product_name": product_name,
                    "repo_root": repo_root,
                },
            )
        )
        return [product_name]

    monkeypatch.setattr(dev_up, "build_swift_launch_command", fake_build_swift_launch_command)
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root, worker_name="swift-text-worker": layout.runtime_dir / f"{worker_name}-cwd",
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

    returned_key = dev_up.start_stack(
        dev_up.DevUpOptions(
            prefer_built=True,
            build_configuration="release",
        ),
        computer_authorization_private_key=private_key,
    )

    assert returned_key == private_key
    assert (layout.runtime_dir / "swift-text-worker.pid").read_text(encoding="utf-8") == "101"
    assert (layout.runtime_dir / "swift-vision-worker.pid").read_text(encoding="utf-8") == "202"
    assert (layout.runtime_dir / "python-worker.pid").read_text(encoding="utf-8") == "303"
    assert (layout.runtime_dir / "control-plane.pid").read_text(encoding="utf-8") == "404"
    assert (layout.runtime_dir / "computer-broker.pid").read_text(encoding="utf-8") == "505"
    output = capsys.readouterr().out
    assert "Melix local stack is ready." in output
    assert "Service instance: team-a" in output
    assert "Swift launch mode: prefer-built (release)" in output
    assert any(kind == "spawn" for kind, _ in calls)
    assert any(kind == "wait" for kind, _ in calls)
    assert ("http", "12436") in calls
    service_spawns = [payload for kind, payload in calls if kind == "spawn"]
    python_spawn = next(
        payload for payload in service_spawns if "worker.bootstrap" in payload["command"]
    )
    assert tuple(python_spawn["unset_environment_keys"]) == (
        *dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS,
        *dev_up.CONTROL_PLANE_SECRET_ENVIRONMENT_KEYS,
        *dev_up.LAUNCHER_INTERNAL_ENVIRONMENT_KEYS,
    )
    assert "MELIX_TEST_STDIO_MCP_TOKEN" not in python_spawn["unset_environment_keys"]
    assert "MELIX_TEST_HTTP_MCP_AUTH" not in python_spawn["unset_environment_keys"]
    non_python_spawns = [payload for payload in service_spawns if payload is not python_spawn]
    python_base_environment = python_spawn["base_environment"]
    assert python_base_environment["MELIX_TEST_STDIO_MCP_TOKEN"] == (
        "stdio-sensitive-value"
    )
    assert python_base_environment["MELIX_TEST_HTTP_MCP_AUTH"] == (
        "http-sensitive-value"
    )
    assert "MELIX_TEST_FUTURE_MCP_TOKEN" not in python_base_environment
    assert "MELIX_GATEWAY_API_KEYS_JSON" not in python_base_environment
    assert "AWS_SECRET_ACCESS_KEY" not in python_base_environment
    assert "GITHUB_TOKEN" not in python_base_environment
    assert all(
        "MELIX_TEST_FUTURE_MCP_TOKEN" not in payload["base_environment"]
        for payload in non_python_spawns
    )
    assert all(
        payload["base_environment"]["MELIX_MCP_CONFIG_PATH"] == str(mcp_config)
        for payload in non_python_spawns
    )
    assert all(
        {
            "MELIX_TEST_STDIO_MCP_TOKEN",
            "MELIX_TEST_HTTP_MCP_AUTH",
        }.issubset(set(payload["unset_environment_keys"]))
        for payload in non_python_spawns
    )
    swift_launch_calls = [payload for kind, payload in calls if kind == "swift-launch"]
    assert [payload["product_name"] for payload in swift_launch_calls] == [
        "melix-text-worker-swift",
        "melix-control-plane",
        "melix-computer-broker",
    ]
    assert {payload["build_configuration"] for payload in swift_launch_calls} == {"release"}
    assert {payload["prefer_built"] for payload in swift_launch_calls} == {True}
    wait_calls = [payload for kind, payload in calls if kind == "wait"]
    assert len(wait_calls) == 3
    assert all(payload["python_executable"] == bridge_python for payload in wait_calls)
    assert all(
        {
            "MELIX_TEST_STDIO_MCP_TOKEN",
            "MELIX_TEST_HTTP_MCP_AUTH",
        }.issubset(set(payload["unset_environment_keys"]))
        for payload in wait_calls
    )
    swift_spawns = [
        payload for kind, payload in calls if kind == "spawn" and payload["command"] == ["melix-text-worker-swift"]
    ]
    assert len(swift_spawns) == 2
    swift_spawn = next(payload for payload in swift_spawns if payload["env_overrides"].get("MELIX_SWIFT_WORKER_FAMILY") != "vision")
    swift_vision_spawn = next(payload for payload in swift_spawns if payload["env_overrides"].get("MELIX_SWIFT_WORKER_FAMILY") == "vision")
    assert swift_spawn["cwd"] == layout.runtime_dir / "swift-text-worker-cwd"
    assert swift_vision_spawn["cwd"] == layout.runtime_dir / "swift-vision-worker-cwd"
    assert swift_spawn["env_overrides"]["MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE"] == "1"
    assert swift_spawn["env_overrides"]["MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE"] == "1"
    assert swift_spawn["base_environment"]["MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT"] == "1"
    assert swift_vision_spawn["env_overrides"]["MELIX_SWIFT_VISION_WORKER_SOCKET_PATH"] == str(
        layout.swift_vision_worker_socket_path
    )
    assert swift_vision_spawn["env_overrides"]["MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH"].endswith(
        "receipts/vision-payload.jsonl"
    )
    assert python_spawn["env_overrides"]["MELIX_HOME"] == str(layout.melix_home_dir)
    assert python_spawn["env_overrides"]["MELIX_COMPUTER_BROKER_SOCKET"] == str(
        layout.computer_broker_socket_path
    )
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD" not in python_spawn[
        "env_overrides"
    ]
    assert python_spawn["command"][0] == os.fspath(bridge_python)
    assert "uv" not in python_spawn["command"]
    control_plane_spawn = next(
        payload for kind, payload in calls if kind == "spawn" and payload["command"] == ["melix-control-plane"]
    )
    assert control_plane_spawn["base_environment"]["MELIX_GATEWAY_AUTH_MODE"] == "api-key"
    assert "gateway-secret" in control_plane_spawn["base_environment"]["MELIX_GATEWAY_API_KEYS_JSON"]
    assert control_plane_spawn["base_environment"]["MELIX_MCP_HIGH_RISK_ALLOWLIST"] == "trusted.exec"
    assert all(
        "MELIX_GATEWAY_API_KEYS_JSON" not in payload["base_environment"]
        for payload in non_python_spawns
        if payload is not control_plane_spawn
    )
    assert control_plane_spawn["env_overrides"]["MELIX_HOME"] == str(layout.melix_home_dir)
    assert control_plane_spawn["env_overrides"]["MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY"] == "environment"
    assert control_plane_spawn["env_overrides"]["MELIX_SWIFT_VISION_WORKER_SOCKET_PATH"] == str(
        layout.swift_vision_worker_socket_path
    )
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
    assert control_plane_spawn["env_overrides"]["MELIX_COMPUTER_BROKER_SOCKET"] == str(
        layout.computer_broker_socket_path
    )
    private_key_fd = int(
        control_plane_spawn["env_overrides"][
            "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD"
        ]
    )
    public_key_fd = int(
        control_plane_spawn["env_overrides"][
            "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_FD"
        ]
    )
    assert control_plane_spawn["pass_fds"] == (private_key_fd, public_key_fd)
    assert private_key.hex() not in repr(control_plane_spawn["env_overrides"])
    computer_broker_spawn = next(
        payload
        for kind, payload in calls
        if kind == "spawn" and payload["command"][0] == "melix-computer-broker"
    )
    assert computer_broker_spawn["command"][1:] == [
        "serve",
        "--socket",
        str(layout.computer_broker_socket_path),
    ]
    assert computer_broker_spawn["env_overrides"][
        "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64"
    ] == base64.b64encode(public_key).decode("ascii")
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD" not in (
        computer_broker_spawn["env_overrides"]
    )
    assert ("computer-socket", layout.computer_broker_socket_path) in calls


def test_start_stack_emits_default_swift_build_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    calls: list[tuple[str, object]] = []
    pid_values = iter([101, 202, 303, 404, 505])

    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    stub_computer_broker_startup(dev_up, monkeypatch, calls=calls)

    def fake_build_swift_launch_command(
        repo_root: Path,
        *,
        package_path: str,
        product_name: str,
        prefer_built: bool,
        build_configuration: str = "debug",
    ) -> list[str]:
        calls.append(
            (
                "swift-launch",
                {
                    "build_configuration": build_configuration,
                    "prefer_built": prefer_built,
                    "product_name": product_name,
                    "repo_root": repo_root,
                },
            )
        )
        return [product_name]

    monkeypatch.setattr(dev_up, "build_swift_launch_command", fake_build_swift_launch_command)
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root, worker_name="swift-text-worker": layout.runtime_dir / f"{worker_name}-cwd",
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

    dev_up.start_stack(dev_up.DevUpOptions())

    output = capsys.readouterr().out
    assert "Swift build configuration: debug" in output
    swift_launch_calls = [payload for kind, payload in calls if kind == "swift-launch"]
    assert [payload["product_name"] for payload in swift_launch_calls] == [
        "melix-text-worker-swift",
        "melix-control-plane",
        "melix-computer-broker",
    ]
    assert {payload["build_configuration"] for payload in swift_launch_calls} == {"debug"}
    assert {payload["prefer_built"] for payload in swift_launch_calls} == {False}


def test_start_stack_wraps_http_timeout_with_log_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_up = load_dev_up_module()
    layout = make_layout(dev_up, tmp_path)
    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(dev_up, "rollback_started_stack", lambda current_layout: None)
    stub_computer_broker_startup(dev_up, monkeypatch)
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root, worker_name="swift-text-worker": layout.runtime_dir / f"{worker_name}-cwd",
    )
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda repo_root, *, package_path, product_name, prefer_built, build_configuration="debug": [product_name],
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
    pid_values = iter([101, 202, 303, 404, 505])

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

    def fake_popen(command, **kwargs):
        captured_env[tuple(command)] = kwargs["env"]
        return FakeProcess(next(pid_values))

    monkeypatch.setenv("MELIX_GATEWAY_CONFIG_STORE_PATH", "/tmp/global-gateway-config.json")
    monkeypatch.setattr(dev_up, "compute_runtime_layout", lambda root: layout)
    stub_computer_broker_startup(dev_up, monkeypatch)
    monkeypatch.setattr(
        dev_up,
        "prepare_swift_worker_launch_cwd",
        lambda layout, repo_root, worker_name="swift-text-worker": layout.runtime_dir / f"{worker_name}-cwd",
    )
    monkeypatch.setattr(
        dev_up,
        "build_swift_launch_command",
        lambda repo_root, *, package_path, product_name, prefer_built, build_configuration="debug": [product_name],
    )
    monkeypatch.setattr(dev_up.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dev_up, "run_wait_for_worker_ready", lambda repo_root, **kwargs: None)
    monkeypatch.setattr(dev_up, "wait_for_http_ready", lambda http_port, timeout_seconds=120.0: None)
    monkeypatch.setattr(dev_up.time, "perf_counter_ns", lambda: 999)

    dev_up.start_stack(dev_up.DevUpOptions(prefer_built=True))

    control_plane_env = captured_env[("melix-control-plane",)]
    assert control_plane_env["MELIX_HOME"] == str(layout.melix_home_dir)
    assert control_plane_env["MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY"] == "environment"
    assert control_plane_env["MELIX_GATEWAY_CONFIG_STORE_PATH"] == str(layout.gateway_config_store_path)
    assert control_plane_env["MELIX_SWIFT_VISION_WORKER_SOCKET_PATH"] == str(
        layout.swift_vision_worker_socket_path
    )


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
