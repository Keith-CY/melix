from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKER_PYPROJECT = REPO_ROOT / "services" / "mlx-worker-python" / "pyproject.toml"


def _dependency_names(entries: list[str]) -> set[str]:
    return {Requirement(entry).name.lower() for entry in entries}


def _locked_package_names() -> set[str]:
    payload = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {canonicalize_name(package["name"]) for package in payload["package"]}


def test_worker_base_dependencies_exclude_test_and_codegen_tools() -> None:
    payload = tomllib.loads(WORKER_PYPROJECT.read_text(encoding="utf-8"))

    runtime_dependencies = _dependency_names(payload["project"]["dependencies"])
    dev_dependencies = _dependency_names(payload["dependency-groups"]["dev"])

    assert "coverage" not in runtime_dependencies
    assert "pytest" not in runtime_dependencies
    assert "grpcio-tools" not in runtime_dependencies
    assert {"coverage", "pytest", "grpcio-tools"} <= dev_dependencies


def test_worker_mlx_extra_isolates_pyarrow_from_synthetic_data() -> None:
    workspace_payload = tomllib.loads(WORKSPACE_PYPROJECT.read_text(encoding="utf-8"))
    worker_payload = tomllib.loads(WORKER_PYPROJECT.read_text(encoding="utf-8"))

    runtime_dependencies = _dependency_names(worker_payload["project"]["dependencies"])
    mlx_dependencies = worker_payload["project"]["optional-dependencies"]["mlx"]
    mlx_dependency_names = _dependency_names(mlx_dependencies)
    workspace_conflicts = workspace_payload["tool"]["uv"]["conflicts"]

    assert "pyarrow" not in runtime_dependencies
    assert "pyarrow>=23.0.1,<25" in mlx_dependencies
    assert "pyarrow" in mlx_dependency_names
    assert [
        {"package": "melix-mlx-worker", "extra": "mlx"},
        {"package": "melix-mlx-worker", "extra": "synthetic-data"},
    ] in workspace_conflicts


def test_packaged_mlx_extra_remains_multimodal_ready() -> None:
    worker_payload = tomllib.loads(WORKER_PYPROJECT.read_text(encoding="utf-8"))

    mlx_dependency_names = _dependency_names(worker_payload["project"]["optional-dependencies"]["mlx"])
    locked_package_names = _locked_package_names()

    assert {"mlx", "mlx-lm", "mlx-vlm", "pyarrow"} <= mlx_dependency_names
    assert {
        "mlx-audio",
        "opencv-python",
        "pillow",
        "scipy",
        "transformers",
    } <= locked_package_names
