from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dev_app_up.sh"
MODULE_PATH = REPO_ROOT / "scripts" / "dev_app_up.py"


def load_dev_up_module():
    spec = importlib.util.spec_from_file_location("melix_dev_up_for_app", REPO_ROOT / "scripts" / "dev_up.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_dev_app_up_module():
    assert MODULE_PATH.exists(), f"Expected Python dev_app_up entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_dev_app_up", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_layout(tmp_path: Path):
    dev_up = load_dev_up_module()
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
        swift_text_worker_backend_mode="deterministic",
        python_bridge_executable=None,
        uv_cache_dir=tmp_path / "uv-cache",
        swift_home=tmp_path / "swift-home",
        clang_module_cache_path=tmp_path / "module-cache",
    )


def test_dev_app_up_shell_wrapper_delegates_help_to_python_entrypoint() -> None:
    result = subprocess.run(
        ["bash", os.fspath(SCRIPT_PATH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "Usage: bash scripts/dev_app_up.sh",
        "",
        "Incrementally builds the current Swift products, starts the Melix backend stack,",
        "and launches the current melix-menubar app from direct executables.",
    ]


def test_parse_args_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    dev_app_up = load_dev_app_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_app_up.parse_args(["--help"])

    assert exc.value.code == 0
    assert "Usage: bash scripts/dev_app_up.sh" in capsys.readouterr().out


def test_parse_args_rejects_unknown_argument(capsys: pytest.CaptureFixture[str]) -> None:
    dev_app_up = load_dev_app_up_module()

    with pytest.raises(SystemExit) as exc:
        dev_app_up.parse_args(["--nope"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "Unknown argument: --nope" in captured.err
    assert "Usage: bash scripts/dev_app_up.sh" in captured.err


def test_start_full_app_launches_menubar_with_console_startup_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_app_up = load_dev_app_up_module()
    layout = make_layout(tmp_path)
    menubar_binary = tmp_path / "melix-menubar"
    menubar_binary.write_text("", encoding="utf-8")
    mcp_config = tmp_path / "mcp-tools.json"
    mcp_config.write_text(
        """
        {
          "sources": [
            {
              "source_id": "stdio-source",
              "transport": {
                "kind": "stdio",
                "command": "/usr/bin/true",
                "environment_references": {
                  "SERVICE_TOKEN": "MELIX_TEST_STDIO_MCP_TOKEN"
                }
              }
            },
            {
              "source_id": "http-source",
              "transport": {
                "kind": "streamable_http",
                "url": "https://mcp.example.test/rpc",
                "header_environment_references": {
                  "Authorization": "MELIX_TEST_HTTP_MCP_AUTHORIZATION"
                }
              }
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    monkeypatch.setattr(dev_app_up, "ROOT", tmp_path)
    monkeypatch.setattr(dev_app_up.dev_up, "compute_runtime_layout", lambda root: layout)
    for private_key in dev_app_up.dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS:
        monkeypatch.setenv(private_key, f"polluted-{private_key}")
    monkeypatch.setenv("MELIX_MCP_CONFIG_PATH", str(mcp_config))
    monkeypatch.setenv("MELIX_TEST_STDIO_MCP_TOKEN", "stdio-sensitive-value")
    monkeypatch.setenv(
        "MELIX_TEST_HTTP_MCP_AUTHORIZATION",
        "Bearer http-sensitive-value",
    )
    monkeypatch.setenv("MELIX_TEST_ROTATED_MCP_TOKEN", "rotated-sensitive-value")

    def fake_build_swift_launch_command(
        repo_root: Path,
        *,
        package_path: str,
        product_name: str,
        prefer_built: bool,
        build_configuration: str = "debug",
    ) -> list[str]:
        seen["menubar_build"] = {
            "repo_root": repo_root,
            "package_path": package_path,
            "product_name": product_name,
            "prefer_built": prefer_built,
            "build_configuration": build_configuration,
        }
        return [str(menubar_binary)]

    monkeypatch.setattr(
        dev_app_up.dev_up,
        "build_swift_launch_command",
        fake_build_swift_launch_command,
    )

    def fake_start_stack(options):
        seen["options"] = options
        layout.runtime_dir.mkdir(parents=True, exist_ok=True)
        return b"K" * 32

    monkeypatch.setattr(dev_app_up.dev_up, "start_stack", fake_start_stack)

    def fake_spawn_background_process(**kwargs):
        seen["spawn"] = kwargs
        return 404

    monkeypatch.setattr(dev_app_up.dev_up, "spawn_background_process", fake_spawn_background_process)

    dev_app_up.start_full_app()

    assert getattr(seen["options"], "prefer_built", True) is False
    assert seen["menubar_build"] == {
        "repo_root": tmp_path,
        "package_path": "apps/macos-menubar",
        "product_name": "melix-menubar",
        "prefer_built": False,
        "build_configuration": "debug",
    }
    assert (layout.runtime_dir / "menubar.pid").read_text(encoding="utf-8") == "404"
    spawn = seen["spawn"]
    assert isinstance(spawn, dict)
    assert spawn["command"] == [str(menubar_binary)]
    assert spawn["cwd"] == tmp_path
    assert spawn["log_path"] == layout.runtime_dir / "menubar.log"
    base_environment = spawn["base_environment"]
    assert isinstance(base_environment, dict)
    for private_key in dev_app_up.dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS:
        assert private_key not in base_environment
    assert "MELIX_TEST_STDIO_MCP_TOKEN" not in base_environment
    assert "MELIX_TEST_HTTP_MCP_AUTHORIZATION" not in base_environment
    assert "MELIX_TEST_ROTATED_MCP_TOKEN" not in base_environment
    assert base_environment["MELIX_MCP_CONFIG_PATH"] == str(mcp_config)
    assert set(spawn["unset_environment_keys"]) == {
        *dev_app_up.dev_up.PRIVATE_SERVICE_ENVIRONMENT_KEYS,
        "MELIX_TEST_STDIO_MCP_TOKEN",
        "MELIX_TEST_HTTP_MCP_AUTHORIZATION",
    }
    assert spawn["env_overrides"]["MELIX_MENU_BAR_STARTUP_SURFACE"] == "console"
    assert spawn["env_overrides"]["MELIX_MENU_BAR_PRESENTATION_MODE"] == "dock-and-tray"
    assert spawn["env_overrides"]["MELIX_MENU_BAR_TERMINATION_MODE"] == "dev-down-script"
    assert spawn["env_overrides"]["MELIX_HOME"] == str(layout.melix_home_dir)
    assert spawn["env_overrides"]["MELIX_RUNTIME_DIR"] == str(layout.runtime_dir)
    assert spawn["env_overrides"]["MELIX_REPO_ROOT"] == str(tmp_path)
    assert spawn["env_overrides"]["MELIX_CONTROL_PLANE_SOCKET_PATH"] == str(
        layout.control_plane_socket_path
    )
    assert "MELIX_WORKER_SOCKET_PATH" not in spawn["env_overrides"]
    assert "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH" not in spawn["env_overrides"]
    assert "MELIX_COMPUTER_BROKER_SOCKET" not in spawn["env_overrides"]
    assert spawn["pass_fds"] == ()
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD" not in (
        spawn["env_overrides"]
    )
    assert "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_BASE64" not in (
        spawn["env_overrides"]
    )
    assert (b"K" * 32).hex() not in repr(spawn)
    assert "polluted-MELIX_COMPUTER_BROKER" not in repr(spawn)
    assert "stdio-sensitive-value" not in repr(spawn)
    assert "http-sensitive-value" not in repr(spawn)
    assert "rotated-sensitive-value" not in repr(spawn)
    assert spawn["env_overrides"]["MELIX_GATEWAY_CONFIG_STORE_PATH"] == str(layout.gateway_config_store_path)
    assert (
        spawn["env_overrides"]["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"]
        == str(layout.gateway_serving_defaults_store_path)
    )
    assert spawn["env_overrides"]["MELIX_IMAGE_DEFAULTS_STORE_PATH"] == str(layout.image_defaults_store_path)
    output = capsys.readouterr().out
    assert "Melix full app is ready." in output
    assert "Menu bar pid file:" in output


def test_start_full_app_requires_restart_when_mcp_config_adds_source_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_app_up = load_dev_app_up_module()
    layout = make_layout(tmp_path)
    menubar_binary = tmp_path / "melix-menubar"
    menubar_binary.write_text("", encoding="utf-8")
    snapshots = iter((
        ("INITIAL_SECRET",),
        ("INITIAL_SECRET", "NEW_SECRET"),
    ))
    spawned = False

    monkeypatch.setattr(dev_app_up, "ROOT", tmp_path)
    monkeypatch.setattr(dev_app_up.dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "active_mcp_credential_environment_keys",
        lambda **kwargs: next(snapshots),
    )
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "build_swift_launch_command",
        lambda *args, **kwargs: [str(menubar_binary)],
    )
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "start_stack",
        lambda options: layout.runtime_dir.mkdir(parents=True, exist_ok=True),
    )
    rolled_back: list[Path] = []
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "rollback_started_stack",
        lambda current_layout: rolled_back.append(current_layout.runtime_dir),
    )

    def fake_spawn(**kwargs):
        nonlocal spawned
        spawned = True
        return 404

    monkeypatch.setattr(dev_app_up.dev_up, "spawn_background_process", fake_spawn)

    with pytest.raises(RuntimeError, match="restart Melix"):
        dev_app_up.start_full_app()

    assert spawned is False
    assert rolled_back == [layout.runtime_dir]


def test_start_full_app_fails_before_backend_boot_when_menubar_build_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_app_up = load_dev_app_up_module()
    layout = make_layout(tmp_path)
    seen: dict[str, int] = {"start_stack": 0}

    monkeypatch.setattr(dev_app_up, "ROOT", tmp_path)
    monkeypatch.setattr(dev_app_up.dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "build_swift_launch_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("menubar build failed")
        ),
    )
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "start_stack",
        lambda options: seen.__setitem__("start_stack", seen["start_stack"] + 1),
    )

    with pytest.raises(RuntimeError, match="menubar build failed"):
        dev_app_up.start_full_app()

    assert seen["start_stack"] == 0


def test_main_fails_closed_before_backend_boot_for_invalid_mcp_config_without_printing_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_app_up = load_dev_app_up_module()
    layout = make_layout(tmp_path)
    invalid_config = tmp_path / "invalid-mcp.json"
    invalid_config.write_text("{", encoding="utf-8")
    sensitive_value = "never-print-this-mcp-secret"
    start_stack_calls = 0

    monkeypatch.setattr(dev_app_up, "ROOT", tmp_path)
    monkeypatch.setattr(dev_app_up.dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setenv("MELIX_MCP_CONFIG_PATH", str(invalid_config))
    monkeypatch.setenv("MELIX_TEST_MCP_TOKEN", sensitive_value)

    def fake_start_stack(options):
        nonlocal start_stack_calls
        _ = options
        start_stack_calls += 1
        return b"K" * 32

    monkeypatch.setattr(dev_app_up.dev_up, "start_stack", fake_start_stack)

    assert dev_app_up.main([]) == 1
    captured = capsys.readouterr()
    assert start_stack_calls == 0
    assert "Active MCP config is invalid" in captured.err
    assert sensitive_value not in captured.out
    assert sensitive_value not in captured.err


def test_start_full_app_rejects_existing_menubar_pid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dev_app_up = load_dev_app_up_module()
    layout = make_layout(tmp_path)
    layout.runtime_dir.mkdir(parents=True, exist_ok=True)
    (layout.runtime_dir / "menubar.pid").write_text("55", encoding="utf-8")
    seen: dict[str, int] = {"start_stack": 0}

    monkeypatch.setattr(dev_app_up, "ROOT", tmp_path)
    monkeypatch.setattr(dev_app_up.dev_up, "compute_runtime_layout", lambda root: layout)
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "build_swift_launch_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("running stack must be rejected before building")
        ),
    )
    monkeypatch.setattr(
        dev_app_up.dev_up,
        "start_stack",
        lambda options: seen.__setitem__("start_stack", seen["start_stack"] + 1),
    )

    with pytest.raises(RuntimeError, match="Run scripts/dev_down.sh first"):
        dev_app_up.start_full_app()

    assert seen["start_stack"] == 0


def test_main_returns_zero_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    dev_app_up = load_dev_app_up_module()
    seen: dict[str, int] = {"start_full_app": 0}

    monkeypatch.setattr(
        dev_app_up,
        "start_full_app",
        lambda: seen.__setitem__("start_full_app", seen["start_full_app"] + 1),
    )

    assert dev_app_up.main([]) == 0
    assert seen["start_full_app"] == 1


def test_main_returns_one_on_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dev_app_up = load_dev_app_up_module()
    monkeypatch.setattr(
        dev_app_up,
        "start_full_app",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert dev_app_up.main([]) == 1
    assert "boom" in capsys.readouterr().err


def test_dev_down_stops_menubar_pid_file(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    process = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        (runtime_dir / "menubar.pid").write_text(str(process.pid), encoding="utf-8")

        result = subprocess.run(
            ["bash", os.fspath(REPO_ROOT / "scripts" / "dev_down.sh")],
            cwd=REPO_ROOT,
            env={**os.environ, "MELIX_RUNTIME_DIR": os.fspath(runtime_dir)},
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert not (runtime_dir / "menubar.pid").exists()

        deadline = time.time() + 5
        while time.time() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.1)

        assert process.poll() is not None
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
