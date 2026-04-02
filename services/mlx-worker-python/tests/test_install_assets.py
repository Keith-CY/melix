from __future__ import annotations

import json
import plistlib
from pathlib import Path

from worker.productization.install_assets import (
    build_launch_agent_specs,
    build_local_product_layout,
    render_launch_agent_plist,
    write_local_product_artifacts,
)


def test_build_local_product_layout_uses_library_conventions(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    layout = build_local_product_layout(repo_root=repo_root, home_dir=home_dir, http_port=18443)

    assert layout.app_support_dir == home_dir / "Library/Application Support/Melix"
    assert layout.runtime_dir == home_dir / "Library/Application Support/Melix/runtime"
    assert layout.managed_models_dir == home_dir / "Library/Application Support/Melix/models/default-managed"
    assert layout.audio_runtime_packs_dir == home_dir / "Library/Application Support/Melix/runtime-packs/audio"
    assert layout.logs_dir == home_dir / "Library/Logs/Melix"
    assert layout.launch_agents_dir == home_dir / "Library/LaunchAgents"
    assert layout.python_socket_path == layout.runtime_dir / "python-worker.sock"
    assert layout.swift_text_worker_socket_path == layout.runtime_dir / "swift-text-worker.sock"
    assert layout.python_worker_metrics_path == layout.runtime_dir / "python-worker-metrics.json"
    assert layout.http_port == 18443


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
    assert layout.app_support_dir == home_dir / "Library/Application Support/Melix/sidecars/team-a"
    assert layout.runtime_dir == layout.app_support_dir / "runtime"
    assert layout.managed_models_dir == layout.app_support_dir / "models/default-managed"
    assert layout.audio_runtime_packs_dir == layout.app_support_dir / "runtime-packs/audio"
    assert layout.model_ops_jobs_root == layout.app_support_dir / "jobs/model-ops"
    assert layout.evaluation_jobs_root == layout.model_ops_jobs_root / "evaluation"
    assert layout.logs_dir == home_dir / "Library/Logs/Melix/sidecars/team-a"
    assert layout.install_manifest_path == layout.app_support_dir / "install-manifest.json"
    assert layout.environment_script_path == layout.app_support_dir / "melix-sidecar-team-a-env.sh"


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
    assert python_spec.environment["MELIX_PYTHON_WORKER_METRICS_PATH"] == str(layout.python_worker_metrics_path)
    assert python_spec.environment["MELIX_MANAGED_MODEL_ROOT"] == str(layout.managed_models_dir)
    assert python_spec.environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"] == str(layout.audio_runtime_packs_dir)

    control_spec = specs["io.melix.control-plane"]
    assert control_spec.environment["MELIX_REPO_ROOT"] == str(repo_root)
    assert control_spec.environment["MELIX_HTTP_PORT"] == "11434"
    assert control_spec.environment["MELIX_MANAGED_MODEL_ROOT"] == str(layout.managed_models_dir)
    assert control_spec.environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"] == str(layout.audio_runtime_packs_dir)


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
    assert payload["ready_probe_url"] == "http://127.0.0.1:19434/v1/models"
    assert len(payload["bootstrap_commands"]) == 3
    assert payload["managed_models_dir"] == str(layout.managed_models_dir)
    assert payload["audio_runtime_packs_dir"] == str(layout.audio_runtime_packs_dir)
    assert any("io.melix.control-plane.plist" in command for command in payload["bootstrap_commands"])
    assert (launch_agents_dir / "io.melix.swift-text-worker.plist").exists()
    assert (launch_agents_dir / "io.melix.python-worker.plist").exists()
    assert (launch_agents_dir / "io.melix.control-plane.plist").exists()
    assert f'MELIX_PYTHON_WORKER_METRICS_PATH="{layout.python_worker_metrics_path}"' in layout.environment_script_path.read_text()
    assert f'MELIX_MANAGED_MODEL_ROOT="{layout.managed_models_dir}"' in layout.environment_script_path.read_text()
    assert f'MELIX_AUDIO_RUNTIME_PACK_ROOT="{layout.audio_runtime_packs_dir}"' in layout.environment_script_path.read_text()


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
    assert payload["service_instance_name"] == "team-a"
    env_script = layout.environment_script_path.read_text()
    assert 'export MELIX_SERVICE_INSTANCE_NAME="team-a"' in env_script
    assert f'export MELIX_MODEL_OPS_JOBS_ROOT="{layout.model_ops_jobs_root}"' in env_script
    assert f'export MELIX_EVALUATION_JOBS_ROOT="{layout.evaluation_jobs_root}"' in env_script
