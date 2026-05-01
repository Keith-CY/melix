from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER_PYPROJECT = REPO_ROOT / "services" / "mlx-worker-python" / "pyproject.toml"


def _dependency_names(entries: list[str]) -> set[str]:
    return {Requirement(entry).name.lower() for entry in entries}


def test_worker_base_dependencies_exclude_test_and_codegen_tools() -> None:
    payload = tomllib.loads(WORKER_PYPROJECT.read_text(encoding="utf-8"))

    runtime_dependencies = _dependency_names(payload["project"]["dependencies"])
    dev_dependencies = _dependency_names(payload["dependency-groups"]["dev"])

    assert "coverage" not in runtime_dependencies
    assert "pytest" not in runtime_dependencies
    assert "grpcio-tools" not in runtime_dependencies
    assert {"coverage", "pytest", "grpcio-tools"} <= dev_dependencies
