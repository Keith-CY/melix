#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import hashlib
import os
import re
import secrets
import select
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path


_WORKER_PYTHON_ROOT = Path(__file__).resolve().parent.parent / "services/mlx-worker-python"
if os.fspath(_WORKER_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_WORKER_PYTHON_ROOT))

from worker.productization.mcp_credential_environment import (  # noqa: E402
    CONTROL_PLANE_PARENT_ENVIRONMENT_KEYS,
    CONTROL_PLANE_SECRET_ENVIRONMENT_KEYS,
    LAUNCHER_INTERNAL_ENVIRONMENT_KEYS,
    MAX_MCP_CONFIG_BYTES as _MAX_MCP_CONFIG_BYTES,
    MCP_CONFIG_PATH_ENV,
    MCP_CREDENTIAL_RESERVED_ENVIRONMENT_KEYS,
    PRIVATE_SERVICE_ENVIRONMENT_KEYS,
    active_mcp_credential_environment_keys,
    app_parent_environment,
    control_plane_parent_environment,
    non_credential_parent_environment,
    normalized_explicit_mcp_config_path,
    python_worker_parent_environment,
    swift_worker_parent_environment,
    validate_frozen_mcp_credential_environment_key_snapshot,
)


ROOT = Path(__file__).resolve().parent.parent
SWIFT_MLX_METALLIB_PATH_ENV = "MELIX_SWIFT_MLX_METALLIB_PATH"
SWIFT_TEXT_WORKER_PACKAGE_DIR = "services/mlx-text-worker-swift"
SWIFT_TURBOQUANT_CANDIDATE_PROBE_ENV = "MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE"
SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE_ENV = "MELIX_SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE"
SWIFT_DFLASH_PROBE_ENV = "MELIX_SWIFT_DFLASH_PROBE"
SWIFT_DFLASH_PROBE_PATH_ENV = "MELIX_SWIFT_DFLASH_PROBE_PATH"
MODEL_ROOTS_ENV = "MELIX_MODEL_ROOTS"
SWIFT_OPTIONAL_PARENT_ENV = (
    SWIFT_TURBOQUANT_CANDIDATE_PROBE_ENV,
    SWIFT_ACTIVE_KV_FORCE_MODEL_EVAL_PROBE_ENV,
    SWIFT_DFLASH_PROBE_ENV,
    SWIFT_DFLASH_PROBE_PATH_ENV,
)
KNOWN_SWIFT_MLX_CORE_VERSION_BY_PACKAGE_VERSION = {
    # These mlx-swift releases vendor MLX core 0.31.1, so their Metal library
    # ABI matches the mlx_metal 0.31.1 wheel rather than the Swift package tag.
    "0.31.3": "0.31.1",
    "0.31.4": "0.31.1",
}
_MLX_METAL_DIST_INFO_VERSION_CACHE: dict[str, str | None] = {}
DEFAULT_SOCKET_DIR = Path("/tmp")
USAGE_TEXT = """Usage: bash scripts/dev_up.sh [--prefer-built] [--build-configuration debug|release]

Options:
  --prefer-built  Start Swift processes from existing built executables under .build/<configuration> when available.
                  This keeps the Python worker on uv run and fails fast if the required Swift binaries are missing."""


@dataclass(frozen=True)
class DevUpOptions:
    prefer_built: bool = False
    build_configuration: str = "debug"


@dataclass(frozen=True)
class RuntimeLayout:
    service_instance_name: str
    melix_home_dir: Path
    runtime_dir: Path
    python_socket_path: Path
    swift_text_worker_socket_path: Path
    swift_vision_worker_socket_path: Path
    control_plane_socket_path: Path
    computer_broker_socket_path: Path
    computer_broker_capability_path: Path
    managed_models_dir: Path
    audio_runtime_packs_dir: Path
    model_ops_jobs_root: Path
    evaluation_jobs_root: Path
    control_plane_metrics_path: Path
    swift_text_worker_metrics_path: Path
    swift_vision_worker_metrics_path: Path
    python_worker_metrics_path: Path
    gateway_config_store_path: Path
    gateway_serving_defaults_store_path: Path
    image_defaults_store_path: Path
    http_port: str
    python_backend_mode: str
    swift_text_worker_backend_mode: str
    python_bridge_executable: Path | None
    uv_cache_dir: Path
    swift_home: Path
    clang_module_cache_path: Path


def print_usage(*, stream) -> None:
    print(USAGE_TEXT, file=stream)


def parse_args(argv: list[str]) -> DevUpOptions:
    prefer_built = False
    build_configuration = "debug"
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--prefer-built":
            prefer_built = True
        elif argument == "--build-configuration":
            index += 1
            if index >= len(argv):
                print("--build-configuration requires a value", file=sys.stderr)
                print_usage(stream=sys.stderr)
                raise SystemExit(2)
            build_configuration = argv[index]
        elif argument in {"-h", "--help"}:
            print_usage(stream=sys.stdout)
            raise SystemExit(0)
        else:
            print(f"Unknown argument: {argument}", file=sys.stderr)
            print_usage(stream=sys.stderr)
            raise SystemExit(2)
        index += 1
    if build_configuration not in {"debug", "release"}:
        print("--build-configuration must be either 'debug' or 'release'", file=sys.stderr)
        print_usage(stream=sys.stderr)
        raise SystemExit(2)
    return DevUpOptions(prefer_built=prefer_built, build_configuration=build_configuration)


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def absolute_path_preserving_symlinks(value: str | Path) -> Path:
    """Return a lexical absolute path without changing an operator-selected alias.

    Foundation's ``standardizedFileURL`` keeps ``/tmp`` as the canonical spelling
    for existing temporary files on macOS.  Resolving that directory through
    Python first rewrites it to ``/private/tmp`` and makes the same path fail the
    broker's canonical-path validation after the capability file is created.
    """
    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


def resolve_executable_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return Path.cwd() / path


def optional_parent_environment_exports(names: tuple[str, ...]) -> dict[str, str]:
    return {
        name: value.strip()
        for name in names
        if (value := os.environ.get(name, "")).strip()
    }


def resolve_python_bridge_executable() -> Path | None:
    configured = os.environ.get("MELIX_PYTHON_BRIDGE_EXECUTABLE", "").strip()
    if configured:
        return resolve_executable_path(configured)

    project_environment = os.environ.get("UV_PROJECT_ENVIRONMENT", "").strip()
    if not project_environment:
        return None

    executable_name = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    candidate = resolve_executable_path(Path(project_environment) / executable_name)
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def optional_python_bridge_environment(layout: RuntimeLayout) -> dict[str, str]:
    if layout.python_bridge_executable is None:
        return {}
    return {"MELIX_PYTHON_BRIDGE_EXECUTABLE": os.fspath(layout.python_bridge_executable)}


def resolve_built_swift_product_binary(
    repo_root: Path,
    *,
    package_path: str,
    product_name: str,
    build_configuration: str = "debug",
) -> Path:
    build_root = repo_root / package_path / ".build"
    direct_candidate = build_root / build_configuration / product_name
    if direct_candidate.is_file() and os.access(direct_candidate, os.X_OK):
        return direct_candidate

    child_names: list[str] = []
    try:
        with os.scandir(os.fspath(build_root)) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        child_names.append(entry.name)
                except OSError:
                    continue
    except OSError:
        child_names = []

    for child_name in sorted(child_names):
        candidate = build_root / child_name / build_configuration / product_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    raise RuntimeError(
        f"Built Swift product is missing for '{product_name}' under {build_root} "
        f"with configuration '{build_configuration}'.\n"
        f"Run `swift build --package-path {repo_root / package_path} -c {build_configuration}` "
        "before using --prefer-built."
    )


def build_swift_launch_command(
    repo_root: Path,
    *,
    package_path: str,
    product_name: str,
    prefer_built: bool,
    build_configuration: str = "debug",
) -> list[str]:
    if not prefer_built:
        # Build synchronously, then exec the product itself. Launching through
        # `swift run` would insert a SwiftPM parent between pass_fds and the
        # control-plane process, so authorization descriptors could be closed
        # before the service reads them.
        subprocess.run(
            [
                "swift",
                "build",
                "--package-path",
                os.fspath(repo_root / package_path),
                "-c",
                build_configuration,
                "--product",
                product_name,
            ],
            check=True,
            cwd=repo_root,
        )
    return [
        os.fspath(
            resolve_built_swift_product_binary(
                repo_root,
                package_path=package_path,
                product_name=product_name,
                build_configuration=build_configuration,
            )
        )
    ]


def build_python_worker_launch_command(
    repo_root: Path,
    *,
    python_executable: Path | None,
    socket_path: Path,
    backend_mode: str,
) -> list[str]:
    if python_executable is not None:
        return [
            os.fspath(python_executable),
            "-m",
            "worker.bootstrap",
            "--socket-path",
            os.fspath(socket_path),
            "--backend-mode",
            backend_mode,
        ]
    return [
        "uv",
        "run",
        "--project",
        os.fspath(repo_root / "services/mlx-worker-python"),
        "--extra",
        "mlx",
        "python",
        "-m",
        "worker.bootstrap",
        "--socket-path",
        os.fspath(socket_path),
        "--backend-mode",
        backend_mode,
    ]


def default_worker_socket_path(
    repo_root: Path,
    *,
    service_instance_name: str,
    role: str,
    socket_dir: Path | None = None,
) -> Path:
    instance = service_instance_name or "phase1"
    repo_hash = hashlib.sha1(os.fspath(repo_root.resolve()).encode("utf-8")).hexdigest()[:10]
    instance_slug = _short_identifier(instance, max_length=32)
    role_slug = _short_identifier(role, max_length=16)
    return (socket_dir or DEFAULT_SOCKET_DIR) / f"melix-{instance_slug}-{repo_hash}-{role_slug}.sock"


def default_computer_broker_socket_path(
    repo_root: Path,
    *,
    service_instance_name: str,
    socket_dir: Path | None = None,
) -> Path:
    socket_root = socket_dir or DEFAULT_SOCKET_DIR
    instance = service_instance_name or "phase1"
    repo_hash = hashlib.sha1(
        os.fspath(repo_root.resolve()).encode("utf-8")
    ).hexdigest()[:10]
    instance_slug = _short_identifier(instance, max_length=32)
    private_parent = socket_root / (
        f"melix-{instance_slug}-{repo_hash}-computer"
    )
    return private_parent / "broker.sock"


def default_control_plane_socket_path(
    repo_root: Path,
    *,
    service_instance_name: str,
    socket_dir: Path | None = None,
) -> Path:
    socket_root = socket_dir or DEFAULT_SOCKET_DIR
    instance = service_instance_name or "phase1"
    repo_hash = hashlib.sha1(
        os.fspath(repo_root.resolve()).encode("utf-8")
    ).hexdigest()[:10]
    instance_slug = _short_identifier(instance, max_length=32)
    private_parent = socket_root / (
        f"melix-{instance_slug}-{repo_hash}-control"
    )
    return private_parent / "control.sock"


def _short_identifier(value: str, *, max_length: int) -> str:
    normalized = _normalize_service_instance_name(value) or "default"
    if len(normalized) <= max_length:
        return normalized
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    prefix = normalized[: max(1, max_length - len(digest) - 1)].rstrip("-")
    return f"{prefix}-{digest}"


def _configured_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def compute_runtime_layout(repo_root: Path) -> RuntimeLayout:
    service_instance_name = _normalize_service_instance_name(os.environ.get("MELIX_SERVICE_INSTANCE_NAME", ""))
    default_runtime_dir = repo_root / ".runtime" / "phase1"
    if service_instance_name:
        default_runtime_dir = repo_root / ".runtime" / "sidecars" / service_instance_name
    runtime_dir = resolve_path(os.environ.get("MELIX_RUNTIME_DIR", default_runtime_dir))
    socket_dir = absolute_path_preserving_symlinks(
        os.environ.get("MELIX_SOCKET_DIR", DEFAULT_SOCKET_DIR)
    )
    default_melix_home = runtime_dir / "home"
    melix_home_value = os.environ.get("MELIX_HOME", "").strip()
    melix_home_dir = resolve_path(melix_home_value if melix_home_value else default_melix_home)
    model_ops_jobs_root = Path(
        os.environ.get("MELIX_MODEL_OPS_JOBS_ROOT", melix_home_dir / "jobs" / "model-ops")
    ).expanduser()
    control_plane_socket_path = _configured_path("MELIX_CONTROL_PLANE_SOCKET_PATH")
    if control_plane_socket_path is None:
        control_plane_socket_path = default_control_plane_socket_path(
            repo_root,
            service_instance_name=service_instance_name,
            socket_dir=socket_dir,
        )
    computer_broker_socket_path = _configured_path("MELIX_COMPUTER_BROKER_SOCKET")
    if computer_broker_socket_path is None:
        computer_broker_socket_path = default_computer_broker_socket_path(
            repo_root,
            service_instance_name=service_instance_name,
            socket_dir=socket_dir,
        )
    return RuntimeLayout(
        service_instance_name=service_instance_name,
        melix_home_dir=melix_home_dir,
        runtime_dir=runtime_dir,
        python_socket_path=_configured_path("MELIX_WORKER_SOCKET_PATH")
        or default_worker_socket_path(
            repo_root,
            service_instance_name=service_instance_name,
            role="python",
            socket_dir=socket_dir,
        ),
        swift_text_worker_socket_path=_configured_path("MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH")
        or default_worker_socket_path(
            repo_root,
            service_instance_name=service_instance_name,
            role="swift",
            socket_dir=socket_dir,
        ),
        swift_vision_worker_socket_path=_configured_path("MELIX_SWIFT_VISION_WORKER_SOCKET_PATH")
        or default_worker_socket_path(
            repo_root,
            service_instance_name=service_instance_name,
            role="swift-vision",
            socket_dir=socket_dir,
        ),
        control_plane_socket_path=control_plane_socket_path,
        computer_broker_socket_path=computer_broker_socket_path,
        computer_broker_capability_path=computer_broker_socket_path.parent
        / "verification-capability.bin",
        managed_models_dir=Path(
            os.environ.get("MELIX_MANAGED_MODEL_ROOT", melix_home_dir / "models" / "default-managed")
        ).expanduser(),
        audio_runtime_packs_dir=Path(
            os.environ.get("MELIX_AUDIO_RUNTIME_PACK_ROOT", melix_home_dir / "runtime-packs" / "audio")
        ).expanduser(),
        model_ops_jobs_root=model_ops_jobs_root,
        evaluation_jobs_root=Path(
            os.environ.get("MELIX_EVALUATION_JOBS_ROOT", melix_home_dir / "jobs" / "evaluation")
        ).expanduser(),
        control_plane_metrics_path=Path(
            os.environ.get("MELIX_CONTROL_PLANE_METRICS_PATH", runtime_dir / "control-plane-metrics.json")
        ).expanduser(),
        swift_text_worker_metrics_path=Path(
            os.environ.get("MELIX_SWIFT_TEXT_WORKER_METRICS_PATH", runtime_dir / "swift-text-worker-metrics.json")
        ).expanduser(),
        swift_vision_worker_metrics_path=Path(
            os.environ.get("MELIX_SWIFT_VISION_WORKER_METRICS_PATH", runtime_dir / "swift-vision-worker-metrics.json")
        ).expanduser(),
        python_worker_metrics_path=Path(
            os.environ.get("MELIX_PYTHON_WORKER_METRICS_PATH", runtime_dir / "python-worker-metrics.json")
        ).expanduser(),
        gateway_config_store_path=Path(
            os.environ.get("MELIX_GATEWAY_CONFIG_STORE_PATH", melix_home_dir / "config" / "gateway-config.json")
        ).expanduser(),
        gateway_serving_defaults_store_path=Path(
            os.environ.get(
                "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH",
                melix_home_dir / "config" / "gateway-serving-defaults.json",
            )
        ).expanduser(),
        image_defaults_store_path=Path(
            os.environ.get("MELIX_IMAGE_DEFAULTS_STORE_PATH", melix_home_dir / "config" / "image-defaults.json")
        ).expanduser(),
        http_port=os.environ.get("MELIX_HTTP_PORT", "12436"),
        python_backend_mode=os.environ.get("MELIX_BACKEND_MODE", "auto"),
        swift_text_worker_backend_mode=os.environ.get("MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE", "swift"),
        python_bridge_executable=resolve_python_bridge_executable(),
        uv_cache_dir=resolve_path(os.environ.get("UV_CACHE_DIR", repo_root / ".uv-cache")),
        swift_home=resolve_path(os.environ.get("MELIX_SWIFT_HOME", repo_root / ".swift-home")),
        clang_module_cache_path=resolve_path(
            os.environ.get("MELIX_CLANG_MODULE_CACHE_PATH", repo_root / ".build" / "ModuleCache.noindex")
        ),
    )


def ensure_runtime_directories(layout: RuntimeLayout) -> None:
    for directory in (
        layout.melix_home_dir,
        layout.melix_home_dir / "config",
        layout.melix_home_dir / "state",
        layout.melix_home_dir / "secrets",
        layout.python_socket_path.parent,
        layout.swift_text_worker_socket_path.parent,
        layout.swift_vision_worker_socket_path.parent,
        layout.uv_cache_dir,
        layout.swift_home,
        layout.clang_module_cache_path,
        layout.managed_models_dir,
        layout.audio_runtime_packs_dir,
        layout.model_ops_jobs_root,
        layout.evaluation_jobs_root,
        layout.runtime_dir / "swift-text-worker-cache",
        layout.runtime_dir / "swift-vision-worker-cache",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    ensure_private_directory(layout.runtime_dir, tighten_owned=True)
    for private_socket_parent in {
        layout.control_plane_socket_path.parent,
        layout.computer_broker_socket_path.parent,
    }:
        ensure_private_directory(
            private_socket_parent,
            tighten_owned=private_socket_parent == layout.runtime_dir,
        )


def ensure_private_directory(path: Path, *, tighten_owned: bool) -> None:
    try:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        status = path.lstat()
    except OSError as error:
        raise RuntimeError(
            f"Could not prepare private runtime directory {path}: {error}"
        ) from error
    if not stat.S_ISDIR(status.st_mode) or stat.S_ISLNK(status.st_mode):
        raise RuntimeError(f"Private runtime path is not a directory: {path}")
    if status.st_uid != os.getuid():
        raise RuntimeError(f"Private runtime directory has an unexpected owner: {path}")
    if status.st_mode & 0o077:
        if not tighten_owned:
            raise RuntimeError(
                f"Private runtime directory permissions are too broad: {path}"
            )
        path.chmod(0o700)


def ensure_runtime_is_stopped(layout: RuntimeLayout) -> None:
    for pid_name in (
        "swift-text-worker.pid",
        "swift-vision-worker.pid",
        "python-worker.pid",
        "control-plane.pid",
        "computer-broker.pid",
    ):
        if (layout.runtime_dir / pid_name).exists():
            raise RuntimeError(
                f"Melix runtime metadata already exists in {layout.runtime_dir}. Run scripts/dev_down.sh first."
            )


def cleanup_runtime_artifacts(layout: RuntimeLayout) -> None:
    swift_worker_launch_dir = layout.runtime_dir / "swift-text-worker-cwd"
    swift_vision_worker_launch_dir = layout.runtime_dir / "swift-vision-worker-cwd"
    for artifact in (
        layout.python_socket_path,
        layout.swift_text_worker_socket_path,
        layout.swift_vision_worker_socket_path,
        layout.control_plane_socket_path,
        layout.computer_broker_socket_path,
        layout.computer_broker_capability_path,
        layout.control_plane_metrics_path,
        layout.swift_text_worker_metrics_path,
        layout.swift_vision_worker_metrics_path,
        layout.python_worker_metrics_path,
        swift_worker_launch_dir / "default.metallib",
        swift_vision_worker_launch_dir / "default.metallib",
    ):
        artifact.unlink(missing_ok=True)
    try:
        swift_worker_launch_dir.rmdir()
    except OSError:
        pass
    try:
        swift_vision_worker_launch_dir.rmdir()
    except OSError:
        pass


def rollback_started_stack(layout: RuntimeLayout) -> None:
    rollback_environment = {
        key: value
        for key in ("HOME", "PATH", "TMPDIR")
        if (value := os.environ.get(key)) is not None
    }
    rollback_environment.update(
        {
            "MELIX_RUNTIME_DIR": os.fspath(layout.runtime_dir),
            "MELIX_SERVICE_INSTANCE_NAME": layout.service_instance_name,
            "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(
                layout.swift_text_worker_socket_path
            ),
            "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH": os.fspath(
                layout.swift_vision_worker_socket_path
            ),
            "MELIX_CONTROL_PLANE_SOCKET_PATH": os.fspath(
                layout.control_plane_socket_path
            ),
            "MELIX_COMPUTER_BROKER_SOCKET": os.fspath(
                layout.computer_broker_socket_path
            ),
            "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": os.fspath(
                layout.computer_broker_capability_path
            ),
            "MELIX_CONTROL_PLANE_METRICS_PATH": os.fspath(
                layout.control_plane_metrics_path
            ),
            "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": os.fspath(
                layout.swift_text_worker_metrics_path
            ),
            "MELIX_SWIFT_VISION_WORKER_METRICS_PATH": os.fspath(
                layout.swift_vision_worker_metrics_path
            ),
            "MELIX_PYTHON_WORKER_METRICS_PATH": os.fspath(
                layout.python_worker_metrics_path
            ),
        }
    )
    completed = subprocess.run(
        ["/bin/bash", os.fspath(ROOT / "scripts" / "dev_down.sh")],
        cwd=ROOT,
        env=rollback_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    cleanup_runtime_artifacts(layout)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"Could not roll back the Melix backend stack: {detail}")


def resolve_swift_mlx_package_version(repo_root: Path) -> str | None:
    package_resolved_path = repo_root / SWIFT_TEXT_WORKER_PACKAGE_DIR / "Package.resolved"
    if not package_resolved_path.is_file():
        return None

    try:
        payload = json.loads(package_resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    for pin in payload.get("pins", []):
        if not isinstance(pin, dict) or pin.get("identity") != "mlx-swift":
            continue
        state = pin.get("state", {})
        if isinstance(state, dict):
            version = state.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
    return None


def read_swift_mlx_core_version(package_swift_path: Path) -> str | None:
    try:
        payload = package_swift_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in payload.splitlines():
        if "MLX_VERSION" not in line:
            continue
        match = re.search(r"(?P<version>[0-9]+(?:\.[0-9]+){1,2})", line)
        if match:
            return match.group("version")
    return None


def resolve_swift_mlx_core_version(repo_root: Path) -> str | None:
    for package_swift_path in (
        repo_root / SWIFT_TEXT_WORKER_PACKAGE_DIR / ".build/checkouts/mlx-swift/Package.swift",
        repo_root / ".build/checkouts/mlx-swift/Package.swift",
    ):
        core_version = read_swift_mlx_core_version(package_swift_path)
        if core_version is not None:
            return core_version
    return None


def compatible_mlx_metal_versions_for_swift_mlx(repo_root: Path) -> tuple[str, ...]:
    vendored_core_version = resolve_swift_mlx_core_version(repo_root)
    if vendored_core_version is not None:
        return (vendored_core_version,)

    package_version = resolve_swift_mlx_package_version(repo_root)
    if package_version is None:
        return ()

    mapped_core_version = KNOWN_SWIFT_MLX_CORE_VERSION_BY_PACKAGE_VERSION.get(package_version)
    if mapped_core_version is not None:
        return (mapped_core_version,)
    return ()


def _read_dist_info_metadata_version(metadata_path: Path) -> str | None:
    version_prefix = "Version:"
    version_prefix_length = len(version_prefix)
    with metadata_path.open("r", encoding="utf-8") as metadata_file:
        for line in metadata_file:
            if line.startswith(version_prefix):
                version = line[version_prefix_length:].strip()
                if version:
                    return version
    return None


def _read_mlx_metal_dist_info_version_from_ancestor(
    ancestor: Path,
    *,
    dist_info_prefix: str,
    dist_info_suffix: str,
    dist_info_prefix_length: int,
    dist_info_suffix_length: int,
) -> str | None:
    fallback_version: str | None = None
    with os.scandir(ancestor) as entries:
        for entry in entries:
            entry_name = entry.name
            if entry_name[:1] != "m":
                continue
            if not (
                entry_name.startswith(dist_info_prefix)
                and entry_name.endswith(dist_info_suffix)
            ):
                continue

            metadata_path = Path(entry.path) / "METADATA"
            try:
                version = _read_dist_info_metadata_version(metadata_path)
            except OSError:
                version = None
            if version is not None:
                return version

            if fallback_version is None and entry.is_dir(follow_symlinks=False):
                fallback_candidate = entry_name[
                    dist_info_prefix_length:-dist_info_suffix_length
                ]
                if fallback_candidate:
                    fallback_version = fallback_candidate
    return fallback_version


def _common_mlx_metal_site_packages_ancestor(resolved_metallib_path: Path) -> Path | None:
    parts = resolved_metallib_path.parts
    if len(parts) >= 4 and parts[-3:] == ("mlx", "lib", "mlx.metallib"):
        return resolved_metallib_path.parents[2]
    return None


def read_mlx_metal_dist_info_version(metallib_path: Path) -> str | None:
    dist_info_prefix = "mlx_metal-"
    dist_info_suffix = ".dist-info"
    dist_info_prefix_length = len(dist_info_prefix)
    dist_info_suffix_length = len(dist_info_suffix)
    resolved_metallib_path = metallib_path.resolve()
    cache_key = os.fspath(resolved_metallib_path)
    if cache_key in _MLX_METAL_DIST_INFO_VERSION_CACHE:
        return _MLX_METAL_DIST_INFO_VERSION_CACHE[cache_key]

    common_site_packages = _common_mlx_metal_site_packages_ancestor(resolved_metallib_path)
    if common_site_packages is not None:
        try:
            version = _read_mlx_metal_dist_info_version_from_ancestor(
                common_site_packages,
                dist_info_prefix=dist_info_prefix,
                dist_info_suffix=dist_info_suffix,
                dist_info_prefix_length=dist_info_prefix_length,
                dist_info_suffix_length=dist_info_suffix_length,
            )
        except OSError:
            version = None
        if version is not None:
            _MLX_METAL_DIST_INFO_VERSION_CACHE[cache_key] = version
            return version

    for ancestor in resolved_metallib_path.parents:
        if ancestor == common_site_packages:
            continue
        try:
            version = _read_mlx_metal_dist_info_version_from_ancestor(
                ancestor,
                dist_info_prefix=dist_info_prefix,
                dist_info_suffix=dist_info_suffix,
                dist_info_prefix_length=dist_info_prefix_length,
                dist_info_suffix_length=dist_info_suffix_length,
            )
        except OSError:
            continue
        if version is not None:
            _MLX_METAL_DIST_INFO_VERSION_CACHE[cache_key] = version
            return version
    _MLX_METAL_DIST_INFO_VERSION_CACHE[cache_key] = None
    return None



def iter_mlx_metallib_candidates(root: Path):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.name == "mlx.metallib" and entry.is_file(follow_symlinks=False):
                            yield Path(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue


def resolve_local_mlx_metallib(repo_root: Path, *, uv_cache_dir: Path | None = None) -> Path | None:
    swift_mlx_package_version = resolve_swift_mlx_package_version(repo_root)
    compatible_mlx_metal_versions = compatible_mlx_metal_versions_for_swift_mlx(repo_root)
    if not compatible_mlx_metal_versions:
        return None

    candidate_search_roots: list[Path] = []
    if uv_cache_dir is not None:
        candidate_search_roots.append(uv_cache_dir)

    candidate_roots = [repo_root, repo_root.parent, repo_root.parent.parent]
    candidate_prefixes = [".venv", ".uv-cache"]
    for root in candidate_roots:
        for prefix in candidate_prefixes:
            candidate_search_roots.append(root / prefix)
    candidate_search_roots.append(Path.home() / ".cache" / "uv")

    seen: set[Path] = set()
    rejected_versions: dict[str, list[Path]] = {}
    for search_root in candidate_search_roots:
        resolved_root = search_root.expanduser().resolve()
        if resolved_root in seen or not resolved_root.exists():
            continue
        seen.add(resolved_root)
        for candidate in iter_mlx_metallib_candidates(resolved_root):
            resolved_candidate = candidate.resolve()
            candidate_version = read_mlx_metal_dist_info_version(resolved_candidate)
            if candidate_version in compatible_mlx_metal_versions:
                return resolved_candidate

            rejected_versions.setdefault(candidate_version or "unknown", []).append(resolved_candidate)

    if swift_mlx_package_version is not None and rejected_versions:
        observed = ", ".join(
            f"{version} at {paths[0]}" for version, paths in sorted(rejected_versions.items())
        )
        compatible_display = " or ".join(
            f"mlx_metal {version}" for version in compatible_mlx_metal_versions
        )
        raise RuntimeError(
            "No compatible Swift MLX metallib was found. "
            f"{SWIFT_TEXT_WORKER_PACKAGE_DIR}/Package.resolved pins mlx-swift {swift_mlx_package_version}, "
            f"so the Swift text worker needs {compatible_display} mlx.metallib. "
            f"Observed incompatible candidates: {observed}. "
            f"Set {SWIFT_MLX_METALLIB_PATH_ENV} to a matching mlx.metallib or install the matching mlx_metal wheel."
        )

    return None


def resolve_configured_mlx_metallib() -> Path | None:
    raw_path = os.environ.get(SWIFT_MLX_METALLIB_PATH_ENV, "").strip()
    if not raw_path:
        return None

    metallib_path = resolve_path(raw_path)
    if not metallib_path.is_file():
        raise RuntimeError(f"{SWIFT_MLX_METALLIB_PATH_ENV} does not point to a file: {metallib_path}")
    return metallib_path


def swift_text_backend_requires_mlx_metallib(backend_mode: str) -> bool:
    return backend_mode.strip().lower() != "deterministic"


def prepare_swift_worker_launch_cwd(
    layout: RuntimeLayout,
    repo_root: Path,
    *,
    worker_name: str = "swift-text-worker",
) -> Path:
    if not swift_text_backend_requires_mlx_metallib(layout.swift_text_worker_backend_mode):
        return repo_root

    metallib_path = resolve_configured_mlx_metallib()
    if metallib_path is None:
        metallib_path = resolve_local_mlx_metallib(repo_root, uv_cache_dir=layout.uv_cache_dir)
    if metallib_path is None:
        return repo_root

    launch_dir = layout.runtime_dir / f"{worker_name}-cwd"
    launch_dir.mkdir(parents=True, exist_ok=True)
    default_metallib_path = launch_dir / "default.metallib"
    default_metallib_path.unlink(missing_ok=True)
    default_metallib_path.symlink_to(metallib_path)
    return launch_dir


def spawn_background_process(
    *,
    cwd: Path,
    log_path: Path,
    env_overrides: dict[str, str],
    command: list[str],
    pass_fds: tuple[int, ...] = (),
    base_environment: Mapping[str, str] | None = None,
    unset_environment_keys: Iterable[str] = (),
) -> int:
    environment = sanitized_process_environment(
        base_environment=base_environment,
        unset_environment_keys=unset_environment_keys,
    )
    environment.update(env_overrides)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        handle = log_path.open("ab")
    except PermissionError:
        # Recover from stale logs created by a prior privileged run.
        log_path.unlink()
        handle = log_path.open("ab")

    with handle:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=pass_fds,
            close_fds=True,
        )

    return process.pid


def sanitized_process_environment(
    *,
    base_environment: Mapping[str, str] | None = None,
    unset_environment_keys: Iterable[str] = (),
) -> dict[str, str]:
    environment = dict(os.environ if base_environment is None else base_environment)
    for key in unset_environment_keys:
        environment.pop(key, None)
    return environment


def write_private_capability(path: Path, capability: bytes) -> None:
    if not 32 <= len(capability) <= 4_096:
        raise RuntimeError("Computer broker capability must be bounded.")
    descriptor = os.open(
        os.fspath(path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        write_all_descriptor(descriptor, capability)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def write_all_descriptor(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise RuntimeError("Could not write the complete private descriptor payload.")
        remaining = remaining[written:]


def private_key_read_pipe(private_key: bytes) -> int:
    if len(private_key) != 32:
        raise RuntimeError("Computer authorization private key must contain 32 bytes.")
    read_descriptor, write_descriptor = os.pipe()
    try:
        write_all_descriptor(write_descriptor, private_key)
    finally:
        os.close(write_descriptor)
    return read_descriptor


def read_exact_descriptor(
    descriptor: int,
    byte_count: int,
    *,
    timeout_seconds: float,
) -> bytes:
    deadline = time.monotonic() + timeout_seconds
    chunks: list[bytes] = []
    remaining = byte_count
    try:
        while remaining > 0:
            timeout = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([descriptor], [], [], timeout)
            if not readable:
                raise RuntimeError(
                    "Timed out waiting for the control-plane authorization public key."
                )
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise RuntimeError(
                    "Control plane closed the authorization key channel before publishing a key."
                )
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def wait_for_private_socket(path: Path, *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            mode = path.stat().st_mode
            if stat.S_ISSOCK(mode) and mode & 0o077 == 0:
                return
        except FileNotFoundError:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Computer Use broker socket did not become ready: {path}")
        time.sleep(0.1)


def write_pid_file(path: Path, pid: int) -> None:
    path.write_text(f"{pid}", encoding="utf-8")


def run_wait_for_worker_ready(
    repo_root: Path,
    *,
    uv_cache_dir: Path,
    socket_path: Path,
    output_path: Path,
    python_executable: Path | None = None,
    unset_environment_keys: Iterable[str] = (),
) -> None:
    environment = sanitized_process_environment(
        base_environment=non_credential_parent_environment(),
        unset_environment_keys=unset_environment_keys,
    )
    environment["PYTHONPATH"] = f"{repo_root}:{repo_root / 'services/mlx-worker-python'}"
    environment["UV_CACHE_DIR"] = os.fspath(uv_cache_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wait_script_path = repo_root / "scripts" / "wait_for_worker_ready.py"
    if python_executable is not None:
        command = [
            os.fspath(python_executable),
            os.fspath(wait_script_path),
            "--socket-path",
            os.fspath(socket_path),
        ]
    else:
        command = [
            "uv",
            "run",
            "--project",
            os.fspath(repo_root / "services/mlx-worker-python"),
            "--extra",
            "mlx",
            "python",
            os.fspath(wait_script_path),
            "--socket-path",
            os.fspath(socket_path),
        ]
    with output_path.open("wb") as handle:
        result = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Worker readiness probe failed for {socket_path}. See {output_path}.")


def wait_for_http_ready(http_port: str, *, timeout_seconds: float = 120.0) -> None:
    deadline = time.perf_counter() + timeout_seconds
    url = f"http://127.0.0.1:{http_port}/v1/models"

    while True:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except (urllib.error.URLError, OSError):
            pass
        if time.perf_counter() >= deadline:
            raise RuntimeError("Melix did not become ready.")
        time.sleep(0.5)


def write_runtime_environment(layout: RuntimeLayout) -> Path:
    env_path = layout.runtime_dir / "env.sh"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    exports = {
        "MELIX_REPO_ROOT": os.fspath(ROOT),
        "MELIX_HOME": os.fspath(layout.melix_home_dir),
        "MELIX_RUNTIME_DIR": os.fspath(layout.runtime_dir),
        "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
        "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
        "MELIX_MODEL_OPS_JOBS_ROOT": os.fspath(layout.model_ops_jobs_root),
        "MELIX_EVALUATION_JOBS_ROOT": os.fspath(layout.evaluation_jobs_root),
        "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
        "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
        "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH": os.fspath(layout.swift_vision_worker_socket_path),
        "MELIX_CONTROL_PLANE_SOCKET_PATH": os.fspath(layout.control_plane_socket_path),
        "MELIX_COMPUTER_BROKER_SOCKET": os.fspath(layout.computer_broker_socket_path),
        "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID": (
            layout.service_instance_name or "melix-local"
        ),
        "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID": "io.melix.worker",
        "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID": "MELIXLOCAL",
        "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": os.fspath(
            layout.computer_broker_capability_path
        ),
        "MELIX_HTTP_PORT": layout.http_port,
        "MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY": "environment",
        "MELIX_BACKEND_MODE": layout.python_backend_mode,
        "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": layout.swift_text_worker_backend_mode,
        "MELIX_CONTROL_PLANE_METRICS_PATH": os.fspath(layout.control_plane_metrics_path),
        "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": os.fspath(layout.swift_text_worker_metrics_path),
        "MELIX_SWIFT_VISION_WORKER_METRICS_PATH": os.fspath(layout.swift_vision_worker_metrics_path),
        "MELIX_PYTHON_WORKER_METRICS_PATH": os.fspath(layout.python_worker_metrics_path),
        "MELIX_GATEWAY_CONFIG_STORE_PATH": os.fspath(layout.gateway_config_store_path),
        "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH": os.fspath(layout.gateway_serving_defaults_store_path),
        "MELIX_IMAGE_DEFAULTS_STORE_PATH": os.fspath(layout.image_defaults_store_path),
    }
    if layout.service_instance_name:
        exports["MELIX_SERVICE_INSTANCE_NAME"] = layout.service_instance_name
    exports.update(optional_parent_environment_exports((MODEL_ROOTS_ENV,)))
    exports.update(optional_python_bridge_environment(layout))
    if os.environ.get(SWIFT_MLX_METALLIB_PATH_ENV, "").strip():
        exports[SWIFT_MLX_METALLIB_PATH_ENV] = os.fspath(resolve_configured_mlx_metallib())
    exports.update(optional_parent_environment_exports(SWIFT_OPTIONAL_PARENT_ENV))
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    lines.extend(f'export {key}="{value}"' for key, value in exports.items())
    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return env_path


def _start_owned_stack(
    options: DevUpOptions,
    *,
    computer_authorization_private_key: bytes | None = None,
    on_ownership_acquired: Callable[[], None],
) -> bytes:
    repo_root = ROOT
    if normalized_mcp_config_path := normalized_explicit_mcp_config_path(os.environ):
        os.environ[MCP_CONFIG_PATH_ENV] = normalized_mcp_config_path
    layout = compute_runtime_layout(repo_root)
    initial_mcp_credential_environment_keys = active_mcp_credential_environment_keys(
        environment=os.environ,
        melix_home_dir=layout.melix_home_dir,
    )
    non_python_base_environment = non_credential_parent_environment()
    swift_worker_base_environment = swift_worker_parent_environment()
    python_worker_base_environment = python_worker_parent_environment(
        credential_keys=initial_mcp_credential_environment_keys,
    )

    def non_python_private_environment_keys() -> tuple[str, ...]:
        current_mcp_credential_environment_keys = active_mcp_credential_environment_keys(
            environment=os.environ,
            melix_home_dir=layout.melix_home_dir,
        )
        return (
            *PRIVATE_SERVICE_ENVIRONMENT_KEYS,
            *validate_frozen_mcp_credential_environment_key_snapshot(
                initial_mcp_credential_environment_keys,
                current_mcp_credential_environment_keys,
            ),
        )

    ensure_runtime_directories(layout)
    ensure_runtime_is_stopped(layout)
    on_ownership_acquired()
    cleanup_runtime_artifacts(layout)
    computer_authorization_private_key = (
        computer_authorization_private_key or secrets.token_bytes(32)
    )
    if len(computer_authorization_private_key) != 32:
        raise RuntimeError(
            "Computer authorization private key must contain exactly 32 bytes."
        )
    write_private_capability(
        layout.computer_broker_capability_path,
        secrets.token_bytes(32),
    )

    swift_text_command = build_swift_launch_command(
        repo_root,
        package_path="services/mlx-text-worker-swift",
        product_name="melix-text-worker-swift",
        prefer_built=options.prefer_built,
        build_configuration=options.build_configuration,
    )
    swift_text_cwd = prepare_swift_worker_launch_cwd(layout, repo_root)
    swift_text_pid = spawn_background_process(
        cwd=swift_text_cwd,
        log_path=layout.runtime_dir / "swift-text-worker.log",
        base_environment=swift_worker_base_environment,
        unset_environment_keys=non_python_private_environment_keys(),
        env_overrides={
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE": layout.swift_text_worker_backend_mode,
            "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH": os.fspath(layout.swift_text_worker_metrics_path),
            "MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS": str(time.perf_counter_ns()),
            "MELIX_DEV_TEXT_MODEL_PATH": os.environ.get("MELIX_DEV_TEXT_MODEL_PATH", ""),
            "HOME": os.fspath(layout.swift_home),
            "CLANG_MODULE_CACHE_PATH": os.fspath(layout.clang_module_cache_path),
            **optional_parent_environment_exports(SWIFT_OPTIONAL_PARENT_ENV),
        },
        command=swift_text_command,
    )
    write_pid_file(layout.runtime_dir / "swift-text-worker.pid", swift_text_pid)
    run_wait_for_worker_ready(
        repo_root,
        uv_cache_dir=layout.uv_cache_dir,
        socket_path=layout.swift_text_worker_socket_path,
        output_path=layout.runtime_dir / "swift-text-worker.ready.log",
        python_executable=layout.python_bridge_executable,
        unset_environment_keys=non_python_private_environment_keys(),
    )

    swift_vision_cwd = prepare_swift_worker_launch_cwd(layout, repo_root, worker_name="swift-vision-worker")
    swift_vision_pid = spawn_background_process(
        cwd=swift_vision_cwd,
        log_path=layout.runtime_dir / "swift-vision-worker.log",
        base_environment=swift_worker_base_environment,
        unset_environment_keys=non_python_private_environment_keys(),
        env_overrides={
            "MELIX_SWIFT_WORKER_FAMILY": "vision",
            "MELIX_SWIFT_VISION_WORKER_ID": "swift-vision-worker-001",
            "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH": os.fspath(layout.swift_vision_worker_socket_path),
            "MELIX_SWIFT_VISION_WORKER_BACKEND_MODE": "deterministic",
            "MELIX_SWIFT_VISION_WORKER_METRICS_PATH": os.fspath(layout.swift_vision_worker_metrics_path),
            "MELIX_SWIFT_VISION_WORKER_CACHE_ROOT": os.fspath(layout.runtime_dir / "swift-vision-worker-cache"),
            "MELIX_SWIFT_VISION_PAYLOAD_RECEIPT_PATH": os.fspath(
                layout.runtime_dir / "receipts" / "vision-payload.jsonl"
            ),
            "MELIX_SWIFT_TEXT_WORKER_STARTUP_T0_NS": str(time.perf_counter_ns()),
            "MELIX_DEV_VLM_MODEL_PATH": os.environ.get("MELIX_DEV_VLM_MODEL_PATH", ""),
            "HOME": os.fspath(layout.swift_home),
            "CLANG_MODULE_CACHE_PATH": os.fspath(layout.clang_module_cache_path),
            **optional_parent_environment_exports(SWIFT_OPTIONAL_PARENT_ENV),
        },
        command=swift_text_command,
    )
    write_pid_file(layout.runtime_dir / "swift-vision-worker.pid", swift_vision_pid)
    run_wait_for_worker_ready(
        repo_root,
        uv_cache_dir=layout.uv_cache_dir,
        socket_path=layout.swift_vision_worker_socket_path,
        output_path=layout.runtime_dir / "swift-vision-worker.ready.log",
        python_executable=layout.python_bridge_executable,
        unset_environment_keys=non_python_private_environment_keys(),
    )

    python_worker_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "python-worker.log",
        base_environment=python_worker_base_environment,
        unset_environment_keys=(
            *PRIVATE_SERVICE_ENVIRONMENT_KEYS,
            *CONTROL_PLANE_SECRET_ENVIRONMENT_KEYS,
            *LAUNCHER_INTERNAL_ENVIRONMENT_KEYS,
        ),
        env_overrides={
            "PYTHONPATH": f"{repo_root}:{repo_root / 'services/mlx-worker-python'}",
            "UV_CACHE_DIR": os.fspath(layout.uv_cache_dir),
            "MELIX_PYTHON_WORKER_METRICS_PATH": os.fspath(layout.python_worker_metrics_path),
            "MELIX_PYTHON_WORKER_STARTUP_T0_NS": str(time.perf_counter_ns()),
            "MELIX_HOME": os.fspath(layout.melix_home_dir),
            "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
            **optional_parent_environment_exports((MODEL_ROOTS_ENV,)),
            "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
            "MELIX_MODEL_OPS_JOBS_ROOT": os.fspath(layout.model_ops_jobs_root),
            "MELIX_EVALUATION_JOBS_ROOT": os.fspath(layout.evaluation_jobs_root),
            "MELIX_COMPUTER_BROKER_SOCKET": os.fspath(
                layout.computer_broker_socket_path
            ),
            "MELIX_COMPUTER_BROKER_CLIENT_INSTANCE_ID": (
                layout.service_instance_name or "melix-local"
            ),
            "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID": "io.melix.worker",
            "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID": "MELIXLOCAL",
            "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": os.fspath(
                layout.computer_broker_capability_path
            ),
        },
        command=build_python_worker_launch_command(
            repo_root,
            python_executable=layout.python_bridge_executable,
            socket_path=layout.python_socket_path,
            backend_mode=layout.python_backend_mode,
        ),
    )
    write_pid_file(layout.runtime_dir / "python-worker.pid", python_worker_pid)
    run_wait_for_worker_ready(
        repo_root,
        uv_cache_dir=layout.uv_cache_dir,
        socket_path=layout.python_socket_path,
        output_path=layout.runtime_dir / "python-worker.ready.log",
        python_executable=layout.python_bridge_executable,
        unset_environment_keys=non_python_private_environment_keys(),
    )

    control_plane_command = build_swift_launch_command(
        repo_root,
        package_path="services/control-plane-swift",
        product_name="melix-control-plane",
        prefer_built=options.prefer_built,
        build_configuration=options.build_configuration,
    )
    private_key_read_descriptor = private_key_read_pipe(
        computer_authorization_private_key
    )
    public_key_read_descriptor, public_key_write_descriptor = os.pipe()
    try:
        control_plane_pid = spawn_background_process(
            cwd=repo_root,
            log_path=layout.runtime_dir / "control-plane.log",
            base_environment=control_plane_parent_environment(),
            unset_environment_keys=non_python_private_environment_keys(),
            env_overrides={
                "MELIX_HTTP_PORT": layout.http_port,
                "MELIX_GATEWAY_RUNTIME_BINDING_AUTHORITY": "environment",
                "MELIX_HOME": os.fspath(layout.melix_home_dir),
                "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
                "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH": os.fspath(layout.swift_vision_worker_socket_path),
                "MELIX_CONTROL_PLANE_SOCKET_PATH": os.fspath(layout.control_plane_socket_path),
                "MELIX_REPO_ROOT": os.fspath(repo_root),
                "MELIX_CONTROL_PLANE_METRICS_PATH": os.fspath(layout.control_plane_metrics_path),
                "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
                **optional_parent_environment_exports((MODEL_ROOTS_ENV,)),
                "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
                "MELIX_GATEWAY_CONFIG_STORE_PATH": os.fspath(layout.gateway_config_store_path),
                "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH": os.fspath(layout.gateway_serving_defaults_store_path),
                "MELIX_IMAGE_DEFAULTS_STORE_PATH": os.fspath(layout.image_defaults_store_path),
                "MELIX_COMPUTER_BROKER_SOCKET": os.fspath(
                    layout.computer_broker_socket_path
                ),
                "MELIX_COMPUTER_BROKER_AUTHORIZATION_PRIVATE_KEY_FD": str(
                    private_key_read_descriptor
                ),
                "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_FD": str(
                    public_key_write_descriptor
                ),
                "HOME": os.fspath(layout.swift_home),
                "CLANG_MODULE_CACHE_PATH": os.fspath(layout.clang_module_cache_path),
                **optional_python_bridge_environment(layout),
            },
            command=control_plane_command,
            pass_fds=(
                private_key_read_descriptor,
                public_key_write_descriptor,
            ),
        )
    except BaseException:
        os.close(public_key_read_descriptor)
        raise
    finally:
        os.close(private_key_read_descriptor)
        os.close(public_key_write_descriptor)
    write_pid_file(layout.runtime_dir / "control-plane.pid", control_plane_pid)

    authorization_public_key = read_exact_descriptor(
        public_key_read_descriptor,
        32,
        timeout_seconds=300.0,
    )
    computer_broker_command = build_swift_launch_command(
        repo_root,
        package_path="services/computer-use-broker-swift",
        product_name="melix-computer-broker",
        prefer_built=options.prefer_built,
        build_configuration=options.build_configuration,
    ) + [
        "serve",
        "--socket",
        os.fspath(layout.computer_broker_socket_path),
    ]
    computer_broker_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "computer-broker.log",
        base_environment=non_python_base_environment,
        unset_environment_keys=non_python_private_environment_keys(),
        env_overrides={
            "MELIX_RUNTIME_DIR": os.fspath(layout.runtime_dir),
            "MELIX_SERVICE_INSTANCE_NAME": (
                layout.service_instance_name or "melix-local"
            ),
            "MELIX_COMPUTER_BROKER_CALLER_BUNDLE_ID": "io.melix.worker",
            "MELIX_COMPUTER_BROKER_CALLER_TEAM_ID": "MELIXLOCAL",
            "MELIX_COMPUTER_BROKER_VERIFICATION_CAPABILITY_FILE": os.fspath(
                layout.computer_broker_capability_path
            ),
            "MELIX_COMPUTER_BROKER_AUTHORIZATION_PUBLIC_KEY_BASE64": (
                base64.b64encode(authorization_public_key).decode("ascii")
            ),
            "HOME": os.fspath(layout.swift_home),
            "CLANG_MODULE_CACHE_PATH": os.fspath(
                layout.clang_module_cache_path
            ),
        },
        command=computer_broker_command,
    )
    write_pid_file(
        layout.runtime_dir / "computer-broker.pid",
        computer_broker_pid,
    )
    wait_for_private_socket(
        layout.computer_broker_socket_path,
        timeout_seconds=300.0,
    )

    env_path = write_runtime_environment(layout)
    try:
        wait_for_http_ready(layout.http_port)
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc} See {layout.runtime_dir / 'control-plane.log'}, "
            f"{layout.runtime_dir / 'computer-broker.log'}, "
            f"{layout.runtime_dir / 'swift-text-worker.log'}, and {layout.runtime_dir / 'python-worker.log'}."
        ) from exc

    print("Melix local stack is ready.")
    print(f"HTTP: http://127.0.0.1:{layout.http_port}")
    print(f"Swift text worker socket: {layout.swift_text_worker_socket_path}")
    print(f"Swift vision worker socket: {layout.swift_vision_worker_socket_path}")
    print(f"Python compatibility worker socket: {layout.python_socket_path}")
    print(f"Control plane IPC socket: {layout.control_plane_socket_path}")
    print(f"Computer Use broker socket: {layout.computer_broker_socket_path}")
    print(f"Control plane metrics: {layout.control_plane_metrics_path}")
    print(f"Swift text worker metrics: {layout.swift_text_worker_metrics_path}")
    print(f"Swift vision worker metrics: {layout.swift_vision_worker_metrics_path}")
    print(f"Python worker metrics: {layout.python_worker_metrics_path}")
    print(f"Runtime env file: {env_path}")
    if layout.service_instance_name:
        print(f"Service instance: {layout.service_instance_name}")
    if options.prefer_built:
        print(f"Swift launch mode: prefer-built ({options.build_configuration})")
    else:
        print(f"Swift build configuration: {options.build_configuration}")
    return computer_authorization_private_key


def start_stack(
    options: DevUpOptions,
    *,
    computer_authorization_private_key: bytes | None = None,
) -> bytes:
    layout = compute_runtime_layout(ROOT)
    ownership_acquired = False

    def mark_ownership_acquired() -> None:
        nonlocal ownership_acquired
        ownership_acquired = True

    try:
        return _start_owned_stack(
            options,
            computer_authorization_private_key=computer_authorization_private_key,
            on_ownership_acquired=mark_ownership_acquired,
        )
    except BaseException as startup_error:
        if not ownership_acquired:
            raise
        try:
            rollback_started_stack(layout)
        except RuntimeError as rollback_error:
            raise RuntimeError(f"{startup_error} {rollback_error}") from startup_error
        raise


def _normalize_service_instance_name(value: str) -> str:
    value = value.strip().lower()
    normalized = "".join(character if character.isalnum() or character == "-" else "-" for character in value)
    return normalized.strip("-")


def main(argv: list[str] | None = None) -> int:
    options = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        start_stack(options)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
