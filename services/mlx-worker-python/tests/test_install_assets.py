from __future__ import annotations

import json
import plistlib
from pathlib import Path

import worker.productization.install_assets as install_assets
from worker.productization.install_assets import (
    build_launch_agent_specs,
    build_local_product_layout,
    render_launch_agent_plist,
    write_local_product_artifacts,
)


def test_build_local_product_layout_uses_cli_first_melix_home(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    layout = build_local_product_layout(repo_root=repo_root, home_dir=home_dir, http_port=18443)

    assert layout.melix_home_dir == home_dir / ".melix"
    assert layout.install_dir == home_dir / ".melix/install"
    assert layout.runtime_dir == home_dir / ".melix/run"
    assert layout.managed_models_dir == home_dir / ".melix/models/default-managed"
    assert layout.audio_runtime_packs_dir == home_dir / ".melix/runtime-packs/audio"
    assert layout.model_ops_jobs_root == home_dir / ".melix/jobs/model-ops"
    assert layout.evaluation_jobs_root == home_dir / ".melix/jobs/evaluation"
    assert layout.logs_dir == home_dir / ".melix/logs"
    assert layout.launch_agents_dir == home_dir / "Library/LaunchAgents"
    assert layout.python_socket_path == layout.runtime_dir / "python-worker.sock"
    assert layout.swift_text_worker_socket_path == layout.runtime_dir / "swift-text-worker.sock"
    assert layout.python_worker_metrics_path == layout.runtime_dir / "python-worker-metrics.json"
    assert layout.update_channel_path == repo_root / "infra/packaging/update-channels/stable.json"
    assert layout.product_version == "0.1.0"
    assert layout.requested_http_port == 18443
    assert layout.http_port == 18443
    assert layout.install_manifest_path == home_dir / ".melix/install/install-manifest.json"
    assert layout.environment_script_path == home_dir / ".melix/install/melix-product-env.sh"


def test_build_local_product_layout_supports_sidecar_instance_isolation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    layout = build_local_product_layout(
        repo_root=repo_root,
        home_dir=home_dir,
        http_port=19443,
        service_instance_name="team-a",
    )

    assert layout.service_instance_name == "team-a"
    assert layout.melix_home_dir == home_dir / ".melix/sidecars/team-a"
    assert layout.install_dir == layout.melix_home_dir / "install"
    assert layout.runtime_dir == layout.melix_home_dir / "run"
    assert layout.managed_models_dir == layout.melix_home_dir / "models/default-managed"
    assert layout.audio_runtime_packs_dir == layout.melix_home_dir / "runtime-packs/audio"
    assert layout.model_ops_jobs_root == layout.melix_home_dir / "jobs/model-ops"
    assert layout.evaluation_jobs_root == layout.melix_home_dir / "jobs/evaluation"
    assert layout.logs_dir == layout.melix_home_dir / "logs"
    assert layout.install_manifest_path == layout.install_dir / "install-manifest.json"
    assert layout.environment_script_path == layout.install_dir / "melix-sidecar-team-a-env.sh"


def test_build_launch_agent_specs_capture_expected_commands_and_environment(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    layout = build_local_product_layout(repo_root=repo_root, home_dir=home_dir)

    specs = {spec.label: spec for spec in build_launch_agent_specs(
        layout,
        swift_backend_mode="swift",
        python_backend_mode="deterministic",
        dev_text_model_path="/models/dev-text",
    )}

    swift_spec = specs["io.melix.swift-text-worker"]
    assert swift_spec.program_arguments[:3] == ["/usr/bin/env", "swift", "run"]
    assert swift_spec.environment["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] == "swift"
    assert swift_spec.environment["MELIX_DEV_TEXT_MODEL_PATH"] == "/models/dev-text"

    python_spec = specs["io.melix.python-worker"]
    assert python_spec.program_arguments[-2:] == ["--backend-mode", "deterministic"]
    assert "PYTHONPATH" in python_spec.environment
    assert python_spec.environment["UV_CACHE_DIR"] == str(repo_root / ".uv-cache")
    assert python_spec.environment["MELIX_HOME"] == str(layout.melix_home_dir)
    assert python_spec.environment["MELIX_PYTHON_WORKER_METRICS_PATH"] == str(layout.python_worker_metrics_path)
    assert python_spec.environment["MELIX_MANAGED_MODEL_ROOT"] == str(layout.managed_models_dir)
    assert python_spec.environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"] == str(layout.audio_runtime_packs_dir)

    control_spec = specs["io.melix.control-plane"]
    assert control_spec.environment["MELIX_REPO_ROOT"] == str(repo_root)
    assert control_spec.environment["MELIX_HOME"] == str(layout.melix_home_dir)
    assert control_spec.environment["MELIX_HTTP_PORT"] == "12436"
    assert control_spec.environment["MELIX_MANAGED_MODEL_ROOT"] == str(layout.managed_models_dir)
    assert control_spec.environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"] == str(layout.audio_runtime_packs_dir)
    assert control_spec.environment["MELIX_GATEWAY_CONFIG_STORE_PATH"] == str(
        layout.melix_home_dir / "config/gateway-config.json"
    )
    assert control_spec.environment["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"] == str(
        layout.melix_home_dir / "config/gateway-serving-defaults.json"
    )
    assert control_spec.environment["MELIX_IMAGE_DEFAULTS_STORE_PATH"] == str(
        layout.melix_home_dir / "config/image-defaults.json"
    )


def test_build_launch_agent_specs_default_to_real_backends(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    layout = build_local_product_layout(repo_root=repo_root, home_dir=home_dir)

    specs = {spec.label: spec for spec in build_launch_agent_specs(layout)}

    swift_spec = specs["io.melix.swift-text-worker"]
    assert swift_spec.environment["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] == "swift"

    python_spec = specs["io.melix.python-worker"]
    assert python_spec.program_arguments[-2:] == ["--backend-mode", "auto"]


def test_build_launch_agent_specs_uses_absolute_uv_binary_when_available(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    layout = build_local_product_layout(repo_root=repo_root, home_dir=home_dir)
    monkeypatch.setattr(install_assets.shutil, "which", lambda command: "/Users/test/.local/bin/uv" if command == "uv" else None)

    specs = {spec.label: spec for spec in build_launch_agent_specs(layout)}

    python_spec = specs["io.melix.python-worker"]
    assert python_spec.program_arguments[:2] == ["/Users/test/.local/bin/uv", "run"]


def test_build_launch_agent_specs_include_sidecar_instance_labels_and_tooling_roots(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    layout = build_local_product_layout(
        repo_root=repo_root,
        home_dir=home_dir,
        service_instance_name="team-a",
        http_port=20434,
    )

    specs = {spec.label: spec for spec in build_launch_agent_specs(layout)}

    assert set(specs) == {
        "io.melix.team-a.swift-text-worker",
        "io.melix.team-a.python-worker",
        "io.melix.team-a.control-plane",
    }
    python_spec = specs["io.melix.team-a.python-worker"]
    assert python_spec.environment["MELIX_SERVICE_INSTANCE_NAME"] == "team-a"
    assert python_spec.environment["MELIX_MODEL_OPS_JOBS_ROOT"] == str(layout.model_ops_jobs_root)
    assert python_spec.environment["MELIX_EVALUATION_JOBS_ROOT"] == str(layout.evaluation_jobs_root)

    control_spec = specs["io.melix.team-a.control-plane"]
    assert control_spec.environment["MELIX_SERVICE_INSTANCE_NAME"] == "team-a"
    assert control_spec.environment["MELIX_MANAGED_MODEL_ROOT"] == str(layout.managed_models_dir)
    assert control_spec.environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"] == str(layout.audio_runtime_packs_dir)


def test_render_launch_agent_plist_round_trips_through_plistlib(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    layout = build_local_product_layout(repo_root=repo_root, home_dir=home_dir)
    spec = build_launch_agent_specs(layout)[0]

    payload = plistlib.loads(render_launch_agent_plist(spec).encode("utf-8"))

    assert payload["Label"] == spec.label
    assert payload["ProgramArguments"] == spec.program_arguments
    assert payload["EnvironmentVariables"]["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] == str(
        layout.swift_text_worker_socket_path
    )
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True


def test_write_local_product_artifacts_writes_plists_manifest_and_env(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    launch_agents_dir = tmp_path / "LaunchAgents"
    layout = build_local_product_layout(
        repo_root=repo_root,
        home_dir=home_dir,
        launch_agents_dir=launch_agents_dir,
        http_port=19434,
    )

    manifest = write_local_product_artifacts(
        layout,
        swift_backend_mode="deterministic",
        python_backend_mode="deterministic",
    )

    assert len(manifest["plists"]) == 3
    assert Path(manifest["environment_script_path"]).exists()
    assert layout.install_manifest_path.exists()
    assert layout.environment_script_path.read_text().startswith("#!/usr/bin/env bash")

    payload = json.loads(layout.install_manifest_path.read_text())
    assert payload["packaging_target_id"] == "launch_agents_checkout"
    assert payload["packaging_kind"] == "launch_agents"
    assert payload["logical_product_identity"] == "io.melix"
    assert payload["product_version"] == "0.1.0"
    assert payload["requested_http_port"] == 19434
    assert payload["http_port_auto_selected"] is False
    assert payload["ready_probe_url"] == "http://127.0.0.1:19434/v1/models"
    assert payload["update_channel_path"] == str(repo_root / "infra/packaging/update-channels/stable.json")
    assert payload["melix_home_dir"] == str(layout.melix_home_dir)
    assert payload["install_dir"] == str(layout.install_dir)
    assert "app_support_dir" not in payload
    assert payload["control_plane_stderr_path"] == str(layout.control_plane_stderr_path)
    assert payload["python_worker_stderr_path"] == str(layout.python_worker_stderr_path)
    assert len(payload["bootstrap_commands"]) == 3
    assert payload["managed_models_dir"] == str(layout.managed_models_dir)
    assert payload["audio_runtime_packs_dir"] == str(layout.audio_runtime_packs_dir)
    assert any("io.melix.control-plane.plist" in command for command in payload["bootstrap_commands"])
    assert (launch_agents_dir / "io.melix.swift-text-worker.plist").exists()
    assert (launch_agents_dir / "io.melix.python-worker.plist").exists()
    assert (launch_agents_dir / "io.melix.control-plane.plist").exists()
    assert 'MELIX_LOGICAL_PRODUCT_ID="io.melix"' in layout.environment_script_path.read_text()
    assert 'MELIX_PACKAGING_TARGET_ID="launch_agents_checkout"' in layout.environment_script_path.read_text()
    assert f'MELIX_PRODUCT_VERSION="{layout.product_version}"' in layout.environment_script_path.read_text()
    assert f'MELIX_UPDATE_CHANNEL_PATH="{layout.update_channel_path}"' in layout.environment_script_path.read_text()
    assert f'MELIX_HOME="{layout.melix_home_dir}"' in layout.environment_script_path.read_text()
    assert "MELIX_APP_SUPPORT_DIR" not in layout.environment_script_path.read_text()
    assert f'MELIX_PYTHON_WORKER_METRICS_PATH="{layout.python_worker_metrics_path}"' in layout.environment_script_path.read_text()
    assert f'MELIX_MANAGED_MODEL_ROOT="{layout.managed_models_dir}"' in layout.environment_script_path.read_text()
    assert f'MELIX_AUDIO_RUNTIME_PACK_ROOT="{layout.audio_runtime_packs_dir}"' in layout.environment_script_path.read_text()
    assert f'MELIX_PRODUCT_MANIFEST_PATH="{layout.install_manifest_path}"' in layout.environment_script_path.read_text()


def test_write_local_product_artifacts_writes_sidecar_service_instance_into_env(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    launch_agents_dir = tmp_path / "LaunchAgents"
    layout = build_local_product_layout(
        repo_root=repo_root,
        home_dir=home_dir,
        launch_agents_dir=launch_agents_dir,
        http_port=20434,
        service_instance_name="team-a",
    )

    manifest = write_local_product_artifacts(layout)

    assert manifest["service_instance_name"] == "team-a"
    payload = json.loads(layout.install_manifest_path.read_text())
    assert payload["packaging_target_id"] == "launch_agents_checkout"
    assert payload["service_instance_name"] == "team-a"
    env_script = layout.environment_script_path.read_text()
    assert 'export MELIX_SERVICE_INSTANCE_NAME="team-a"' in env_script
    assert f'export MELIX_MODEL_OPS_JOBS_ROOT="{layout.model_ops_jobs_root}"' in env_script
    assert f'export MELIX_EVALUATION_JOBS_ROOT="{layout.evaluation_jobs_root}"' in env_script


def test_write_local_product_artifacts_defaults_to_real_backends(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    launch_agents_dir = tmp_path / "LaunchAgents"
    layout = build_local_product_layout(
        repo_root=repo_root,
        home_dir=home_dir,
        launch_agents_dir=launch_agents_dir,
    )

    write_local_product_artifacts(layout)

    swift_plist = plistlib.loads((launch_agents_dir / "io.melix.swift-text-worker.plist").read_bytes())
    python_plist = plistlib.loads((launch_agents_dir / "io.melix.python-worker.plist").read_bytes())

    assert swift_plist["EnvironmentVariables"]["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] == "swift"
    assert python_plist["ProgramArguments"][-2:] == ["--backend-mode", "auto"]


def test_build_local_product_layout_can_auto_select_an_available_http_port(tmp_path: Path) -> None:
    import socket

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        occupied_port = int(listener.getsockname()[1])
        listener.listen(1)
        layout = build_local_product_layout(
            repo_root=repo_root,
            home_dir=home_dir,
            http_port=occupied_port,
            prefer_available_http_port=True,
        )

    assert layout.requested_http_port == occupied_port
    assert layout.http_port != occupied_port
