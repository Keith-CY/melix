#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


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
    # mlx-swift 0.31.3 vendors MLX core 0.31.1, so its Metal library ABI
    # matches the mlx_metal 0.31.1 wheel rather than the Swift package tag.
    "0.31.3": "0.31.1",
}
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
    if prefer_built:
        return [os.fspath(resolve_built_swift_product_binary(
            repo_root,
            package_path=package_path,
            product_name=product_name,
            build_configuration=build_configuration,
        ))]
    return [
        "swift",
        "run",
        "-c",
        build_configuration,
        "--package-path",
        os.fspath(repo_root / package_path),
        product_name,
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
    socket_dir = resolve_path(os.environ.get("MELIX_SOCKET_DIR", DEFAULT_SOCKET_DIR))
    default_melix_home = runtime_dir / "home"
    melix_home_value = os.environ.get("MELIX_HOME", "").strip()
    melix_home_dir = resolve_path(melix_home_value if melix_home_value else default_melix_home)
    model_ops_jobs_root = Path(
        os.environ.get("MELIX_MODEL_OPS_JOBS_ROOT", melix_home_dir / "jobs" / "model-ops")
    ).expanduser()
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
        layout.runtime_dir,
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


def ensure_runtime_is_stopped(layout: RuntimeLayout) -> None:
    for pid_name in ("swift-text-worker.pid", "swift-vision-worker.pid", "python-worker.pid", "control-plane.pid"):
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
    package_version = resolve_swift_mlx_package_version(repo_root)
    if package_version is None:
        return ()

    candidates = (
        resolve_swift_mlx_core_version(repo_root),
        KNOWN_SWIFT_MLX_CORE_VERSION_BY_PACKAGE_VERSION.get(package_version),
        package_version,
    )
    compatible_versions: list[str] = []
    for candidate in candidates:
        if candidate is None or candidate in compatible_versions:
            continue
        compatible_versions.append(candidate)
    return tuple(compatible_versions)


def _read_dist_info_metadata_version(metadata_path: Path) -> str | None:
    with metadata_path.open("r", encoding="utf-8") as metadata_file:
        for line in metadata_file:
            if line.startswith("Version:"):
                version = line.removeprefix("Version:").strip()
                if version:
                    return version
    return None


def read_mlx_metal_dist_info_version(metallib_path: Path) -> str | None:
    for ancestor in metallib_path.resolve().parents:
        fallback_version: str | None = None
        try:
            with os.scandir(ancestor) as entries:
                for entry in entries:
                    if not (
                        entry.name.startswith("mlx_metal-")
                        and entry.name.endswith(".dist-info")
                        and entry.is_dir(follow_symlinks=False)
                    ):
                        continue

                    metadata_path = ancestor / entry.name / "METADATA"
                    try:
                        version = _read_dist_info_metadata_version(metadata_path)
                    except OSError:
                        version = None
                    if version is not None:
                        return version

                    if fallback_version is None:
                        match = re.fullmatch(r"mlx_metal-(?P<version>.+)\.dist-info", entry.name)
                        if match:
                            fallback_version = match.group("version")
        except OSError:
            continue

        if fallback_version is not None:
            return fallback_version

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
            if not compatible_mlx_metal_versions:
                return resolved_candidate

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
) -> int:
    environment = os.environ.copy()
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
        )

    return process.pid


def write_pid_file(path: Path, pid: int) -> None:
    path.write_text(f"{pid}", encoding="utf-8")


def run_wait_for_worker_ready(
    repo_root: Path,
    *,
    uv_cache_dir: Path,
    socket_path: Path,
    output_path: Path,
    python_executable: Path | None = None,
) -> None:
    environment = os.environ.copy()
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
        "MELIX_HTTP_PORT": layout.http_port,
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


def start_stack(options: DevUpOptions) -> None:
    repo_root = ROOT
    layout = compute_runtime_layout(repo_root)
    ensure_runtime_directories(layout)
    ensure_runtime_is_stopped(layout)
    cleanup_runtime_artifacts(layout)

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
    )

    swift_vision_cwd = prepare_swift_worker_launch_cwd(layout, repo_root, worker_name="swift-vision-worker")
    swift_vision_pid = spawn_background_process(
        cwd=swift_vision_cwd,
        log_path=layout.runtime_dir / "swift-vision-worker.log",
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
    )

    python_worker_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "python-worker.log",
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
    )

    control_plane_command = build_swift_launch_command(
        repo_root,
        package_path="services/control-plane-swift",
        product_name="melix-control-plane",
        prefer_built=options.prefer_built,
        build_configuration=options.build_configuration,
    )
    control_plane_pid = spawn_background_process(
        cwd=repo_root,
        log_path=layout.runtime_dir / "control-plane.log",
        env_overrides={
            "MELIX_HTTP_PORT": layout.http_port,
            "MELIX_HOME": os.fspath(layout.melix_home_dir),
            "MELIX_WORKER_SOCKET_PATH": os.fspath(layout.python_socket_path),
            "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": os.fspath(layout.swift_text_worker_socket_path),
            "MELIX_SWIFT_VISION_WORKER_SOCKET_PATH": os.fspath(layout.swift_vision_worker_socket_path),
            "MELIX_REPO_ROOT": os.fspath(repo_root),
            "MELIX_CONTROL_PLANE_METRICS_PATH": os.fspath(layout.control_plane_metrics_path),
            "MELIX_MANAGED_MODEL_ROOT": os.fspath(layout.managed_models_dir),
            **optional_parent_environment_exports((MODEL_ROOTS_ENV,)),
            "MELIX_AUDIO_RUNTIME_PACK_ROOT": os.fspath(layout.audio_runtime_packs_dir),
            "MELIX_GATEWAY_CONFIG_STORE_PATH": os.fspath(layout.gateway_config_store_path),
            "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH": os.fspath(layout.gateway_serving_defaults_store_path),
            "MELIX_IMAGE_DEFAULTS_STORE_PATH": os.fspath(layout.image_defaults_store_path),
            "HOME": os.fspath(layout.swift_home),
            "CLANG_MODULE_CACHE_PATH": os.fspath(layout.clang_module_cache_path),
            **optional_python_bridge_environment(layout),
        },
        command=control_plane_command,
    )
    write_pid_file(layout.runtime_dir / "control-plane.pid", control_plane_pid)

    env_path = write_runtime_environment(layout)
    try:
        wait_for_http_ready(layout.http_port)
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc} See {layout.runtime_dir / 'control-plane.log'}, "
            f"{layout.runtime_dir / 'swift-text-worker.log'}, and {layout.runtime_dir / 'python-worker.log'}."
        ) from exc

    print("Melix local stack is ready.")
    print(f"HTTP: http://127.0.0.1:{layout.http_port}")
    print(f"Swift text worker socket: {layout.swift_text_worker_socket_path}")
    print(f"Swift vision worker socket: {layout.swift_vision_worker_socket_path}")
    print(f"Python compatibility worker socket: {layout.python_socket_path}")
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
