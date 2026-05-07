from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "ci_scope.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ci_scope", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
ci_scope = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(ci_scope)


def test_docs_only_paths_skip_heavy_ci() -> None:
    assert ci_scope.classify_paths(
        [
            "README.md",
            "docs/marketing/copy-kit.md",
            "docs/plans/2026-05-07-melix-lora-storytelling-and-marketing-docs.md",
        ]
    ) == {
        "proto_should_run": False,
        "swift_should_run": False,
        "python_should_run": False,
        "integration_should_run": False,
    }


def test_python_only_paths_run_python_without_swift() -> None:
    assert ci_scope.classify_paths(
        [
            "infra/perf/pr_scoped_probes.json",
            "services/mlx-worker-python/worker/model_ops/hub_catalog.py",
            "services/mlx-worker-python/tests/test_hub_catalog.py",
        ]
    ) == {
        "proto_should_run": False,
        "swift_should_run": False,
        "python_should_run": True,
        "integration_should_run": False,
    }


def test_runtime_python_paths_run_python_and_integration_without_swift() -> None:
    assert ci_scope.classify_paths(
        [
            "services/mlx-worker-python/worker/runtime/mlx_text_runtime.py",
            "services/mlx-worker-python/tests/test_mlx_backend.py",
        ]
    ) == {
        "proto_should_run": False,
        "swift_should_run": False,
        "python_should_run": True,
        "integration_should_run": True,
    }


def test_swift_paths_run_swift_and_integration() -> None:
    assert ci_scope.classify_paths(
        ["services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift"]
    ) == {
        "proto_should_run": False,
        "swift_should_run": True,
        "python_should_run": False,
        "integration_should_run": True,
    }


def test_protocol_paths_run_all_ci_families() -> None:
    assert ci_scope.classify_paths(
        ["packages/protocol/schema/worker/v1/runtime.proto"]
    ) == {
        "proto_should_run": True,
        "swift_should_run": True,
        "python_should_run": True,
        "integration_should_run": True,
    }


def test_workflow_and_toolchain_paths_run_all_ci_families() -> None:
    assert ci_scope.classify_paths([".github/workflows/ci-pr.yml"]) == {
        "proto_should_run": True,
        "swift_should_run": True,
        "python_should_run": True,
        "integration_should_run": True,
    }
    assert ci_scope.classify_paths(["uv.lock"]) == {
        "proto_should_run": True,
        "swift_should_run": True,
        "python_should_run": True,
        "integration_should_run": True,
    }


def test_cli_writes_github_outputs(tmp_path: Path, capsys) -> None:
    changed_files = tmp_path / "changed-files.txt"
    changed_files.write_text("services/mlx-worker-python/worker/runtime/mlx_backend.py\n")
    github_output = tmp_path / "github-output.txt"

    result = ci_scope.main(
        [
            "--changed-files-file",
            str(changed_files),
            "--github-output",
            str(github_output),
            "--json",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "proto_should_run": False,
        "swift_should_run": False,
        "python_should_run": True,
        "integration_should_run": True,
    }
    assert "python_should_run=true\n" in github_output.read_text(encoding="utf-8")
