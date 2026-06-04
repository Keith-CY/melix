from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "package_macos_menubar_app.py"
PACKAGE_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "package-self-contained-app.yml"
PACKAGING_RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "platform-packaging-targets.md"


def find_named_workflow_step(workflow: str, name: str) -> re.Match[str]:
    match = re.search(
        rf"^[ \t]*-[ \t]+name:[ \t]+{re.escape(name)}[ \t]*$",
        workflow,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Workflow step not found: {name}"
    return match


def find_workflow_step(workflow: str, name: str) -> str:
    match = re.search(
        rf"^[ \t]*-[ \t]+name:[ \t]+{re.escape(name)}[ \t]*\n"
        r"(?P<body>.*?)(?=^[ \t]*-[ \t]+|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Workflow step not found: {name}"
    return match.group(0)


def find_workflow_job(workflow: str, job_name: str) -> str:
    match = re.search(
        rf"^  {re.escape(job_name)}:[ \t]*\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Workflow job not found: {job_name}"
    return match.group(0)


def find_run_workflow_step(workflow: str, name: str, command: str) -> re.Match[str]:
    match = re.search(
        rf"^[ \t]*-[ \t]+name:[ \t]+{re.escape(name)}[ \t]*\n"
        r"(?P<body>.*?)(?=^[ \t]*-[ \t]+name:|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Workflow run step not found: {name}"
    step = match.group(0)
    assert re.search(r"^[ \t]*run:", step, flags=re.MULTILINE), f"Workflow run step missing run: {name}"
    assert command in step, f"Workflow run step missing command: {name}"
    return match


def load_package_macos_app_module():
    assert MODULE_PATH.exists(), f"Expected package_macos_menubar_app entrypoint at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("melix_package_macos_app", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_forwards_packaging_target_and_update_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    seen: dict[str, object] = {}

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(module, "resolve_built_cli_binary", lambda repo_root: tmp_path / "melix")
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")

    def fake_write_unsigned_macos_app_bundle(**kwargs):
        seen.update(kwargs)
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "packaging_target_id": "macos_app_bundle_preview",
        }

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write_unsigned_macos_app_bundle)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "package_macos_menubar_app.py",
            "--repo-root",
            str(tmp_path / "repo"),
            "--output-path",
            str(tmp_path / "Melix.app"),
            "--packaging-target-id",
            "macos_app_bundle_preview",
            "--update-channel-path",
            str(tmp_path / "stable.json"),
            "--icon-source-path",
            str(tmp_path / "MelixAppIcon.icns"),
            "--json",
        ],
    )

    assert module.main() == 0
    assert seen["cli_executable_path"] == tmp_path / "melix"
    assert seen["packaging_target_id"] == "macos_app_bundle_preview"
    assert seen["update_channel_path"] == str(tmp_path / "stable.json")
    assert seen["icon_source_path"] == str(tmp_path / "MelixAppIcon.icns")

    payload = json.loads(capsys.readouterr().out)
    assert payload["packaging_target_id"] == "macos_app_bundle_preview"


def test_resolve_built_products_use_direct_release_candidate_before_debug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    menubar_binary = repo_root / "apps/macos-menubar/.build/release/melix-menubar"
    cli_binary = repo_root / ".build/release/melix"
    swift_worker_binary = repo_root / "services/mlx-text-worker-swift/.build/release/melix-text-worker-swift"
    debug_binaries = (
        repo_root / "apps/macos-menubar/.build/debug/melix-menubar",
        repo_root / ".build/debug/melix",
        repo_root / "services/mlx-text-worker-swift/.build/debug/melix-text-worker-swift",
    )
    for binary in (menubar_binary, cli_binary, swift_worker_binary, *debug_binaries):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fail_glob(self: Path, pattern: str):
        raise AssertionError("direct release candidate should avoid scanning build triples")

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert module.resolve_built_binary(repo_root) == menubar_binary
    assert module.resolve_built_cli_binary(repo_root) == cli_binary
    assert module.resolve_built_swift_text_worker_binary(repo_root) == swift_worker_binary


def test_resolve_built_product_falls_back_to_sorted_triple_release_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arm64-apple-macosx/release/melix-menubar"
    later = build_root / "x86_64-apple-macosx/release/melix-menubar"
    debug = build_root / "arm64-apple-macosx/debug/melix-menubar"
    for binary in (later, expected, debug):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.setattr(
        Path,
        "glob",
        lambda self, pattern: (_ for _ in ()).throw(
            AssertionError("fallback build-product resolution should use os.scandir instead of Path.glob")
        ),
    )

    assert module._resolve_built_product(build_root, "melix-menubar") == expected
    assert module._resolve_built_product(build_root, "missing-product") is None
    assert module._resolve_built_product(tmp_path / "missing-build-root", "melix-menubar") is None


def test_resolve_built_product_returns_lex_first_release_triple_without_sorting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arm64-apple-macosx/release/melix-menubar"
    later = build_root / "x86_64-apple-macosx/release/melix-menubar"
    for binary in (later, expected):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.setattr(
        module,
        "sorted",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("lexicographically first triple should avoid sorting fallback candidates")
        ),
        raising=False,
    )

    assert module._resolve_built_product(build_root, "melix-menubar") == expected


def test_resolve_built_product_skips_non_dirs_and_entry_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arm64-apple-macosx/release/melix-menubar"
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    class FakeEntry:
        def __init__(self, name: str, is_dir_result: bool | None) -> None:
            self.name = name
            self._is_dir_result = is_dir_result

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            if self._is_dir_result is None:
                raise OSError("synthetic entry failure")
            return self._is_dir_result

    class FakeScandir:
        def __enter__(self):
            return iter(
                (
                    FakeEntry("broken-entry", None),
                    FakeEntry("not-a-directory", False),
                    FakeEntry("arm64-apple-macosx", True),
                )
            )

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(module.os, "scandir", lambda path: FakeScandir())

    assert module._resolve_built_product(build_root, "melix-menubar") == expected


def test_resolve_built_product_returns_none_without_triple_directories(tmp_path: Path) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    build_root.mkdir()
    (build_root / "README.txt").write_text("not a build triple\n", encoding="utf-8")

    assert module._resolve_built_product(build_root, "melix-menubar") is None


def test_resolve_built_product_uses_debug_fallbacks_after_release_candidates(
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()

    direct_root = tmp_path / "direct/.build"
    direct_debug = direct_root / "debug/melix"
    direct_debug.parent.mkdir(parents=True)
    direct_debug.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    assert module._resolve_built_product(direct_root, "melix") == direct_debug

    lex_root = tmp_path / "lex/.build"
    lex_debug = lex_root / "arm64-apple-macosx/debug/melix"
    lex_debug.parent.mkdir(parents=True)
    lex_debug.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    assert module._resolve_built_product(lex_root, "melix") == lex_debug

    remaining_root = tmp_path / "remaining/.build"
    first_triple = remaining_root / "arm64-apple-macosx"
    later_debug = remaining_root / "x86_64-apple-macosx/debug/melix"
    first_triple.mkdir(parents=True)
    later_debug.parent.mkdir(parents=True)
    later_debug.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    assert module._resolve_built_product(remaining_root, "melix") == later_debug


def test_resolve_built_product_uses_remaining_release_before_remaining_debug(
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    first_triple = build_root / "arch-0000"
    later_release = build_root / "arch-0001/release/melix"
    later_debug = build_root / "arch-0001/debug/melix"
    first_triple.mkdir(parents=True)
    for binary in (later_release, later_debug):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert module._resolve_built_product(build_root, "melix") == later_release


def test_resolve_built_product_uses_lex_debug_before_scanning_remaining_release_triples(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arch-0000/debug/melix"
    expected.parent.mkdir(parents=True)
    expected.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    for index in range(1, 10):
        (build_root / f"arch-{index:04d}" / "debug").mkdir(parents=True)

    original_is_file = module.os.path.isfile

    def guarded_is_file(path: object) -> bool:
        path_value = module.os.fspath(path)
        if "/release/" in path_value and "/arch-0001/" in path_value:
            raise AssertionError("lex-first debug fallback should avoid remaining release probes")  # pragma: no cover
        return original_is_file(path)

    monkeypatch.setattr(module.os.path, "isfile", guarded_is_file)

    assert module._resolve_built_product(build_root, "melix") == expected


def test_resolve_built_product_uses_lex_debug_without_missing_release_file_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arch-0000/debug/melix"
    expected.parent.mkdir(parents=True)
    expected.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    original_is_file = module.os.path.isfile

    def guarded_is_file(path: object) -> bool:
        if module.os.fspath(path) == module.os.fspath(build_root / "arch-0000/release/melix"):  # pragma: no cover
            raise AssertionError("debug-only lex-first triple should not probe missing release file")
        return original_is_file(path)

    monkeypatch.setattr(module.os.path, "isfile", guarded_is_file)

    assert module._resolve_built_product(build_root, "melix") == expected


def test_resolve_built_product_returns_debug_candidate_when_scandir_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    debug_binary = build_root / "debug/melix"
    debug_binary.parent.mkdir(parents=True)
    debug_binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fail_scandir(path: Path):
        raise OSError("synthetic scandir failure")

    monkeypatch.setattr(module.os, "scandir", fail_scandir)

    assert module._resolve_built_product(build_root, "melix") == debug_binary


def test_resolve_built_cli_binary_falls_back_with_scandir_without_path_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    expected = repo_root / ".build/arm64-apple-macosx/release/melix"
    later = repo_root / ".build/x86_64-apple-macosx/release/melix"
    for binary in (later, expected):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    monkeypatch.setattr(
        Path,
        "glob",
        lambda self, pattern: (_ for _ in ()).throw(
            AssertionError("CLI fallback resolution should use os.scandir instead of Path.glob")
        ),
    )

    assert module.resolve_built_cli_binary(repo_root) == expected


def test_package_workflow_uses_runtime_only_python_environment_for_bundle() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    runtime_sync = re.search(
        r"UV_PROJECT_ENVIRONMENT=\"\$GITHUB_WORKSPACE/\.venv-package\".*?uv sync (?P<args>[^\n]+)",
        workflow,
        flags=re.DOTALL,
    )
    assert runtime_sync is not None
    sync_args = runtime_sync.group("args")
    assert "--project services/mlx-worker-python" in sync_args
    assert "--extra mlx" in sync_args
    assert "--no-dev" in sync_args
    assert "--frozen" in sync_args
    assert re.search(r'PACKAGE_VENV_PYTHON="\$GITHUB_WORKSPACE/\.venv-package/bin/python"', workflow)
    assert 'PYTHON_RUNTIME_ROOT="$("$PACKAGE_PYTHON" -c' in workflow
    assert "--python-runtime-root" in workflow
    assert "$PYTHON_RUNTIME_ROOT" in workflow
    assert "--python-site-packages-path" in workflow
    assert "$PYTHON_SITE_PACKAGES" in workflow


def test_package_workflow_uses_uv_managed_python_for_packaged_runtime() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    runtime_step = find_workflow_step(workflow, "Prepare packaging Python runtime")
    assert 'uv python install --install-dir "$RUNNER_TEMP/package-python" 3.12' in runtime_step
    assert "UV_MANAGED_PYTHON=1" in runtime_step
    assert 'find "$RUNNER_TEMP/package-python" -path "*/bin/python3"' in runtime_step
    assert "PACKAGE_PYTHON=%s" in runtime_step
    assert "GITHUB_ENV" in runtime_step
    assert 'UV_PYTHON="$PACKAGE_PYTHON"' in runtime_step

    package_step = find_workflow_step(workflow, "Package self-contained Melix.app")
    assert ": \"${PACKAGE_PYTHON:?PACKAGE_PYTHON must be exported by Prepare packaging Python runtime}\"" in package_step
    assert "uv python find" not in runtime_step
    assert "uv python find" not in package_step
    assert 'PYTHON_RUNTIME_ROOT="$("$PACKAGE_PYTHON" -c' in package_step
    assert "sys.base_prefix" in package_step


def test_package_workflow_builds_required_swift_products_before_packaging_app() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    build_steps = [
        find_run_workflow_step(
            workflow,
            "Build CLI executable",
            "swift build -c release --product melix --disable-automatic-resolution",
        ),
        find_run_workflow_step(
            workflow,
            "Build Swift text worker",
            "swift build -c release --package-path services/mlx-text-worker-swift --disable-automatic-resolution",
        ),
        find_run_workflow_step(
            workflow,
            "Build menu bar app executable",
            "swift build -c release --package-path apps/macos-menubar --disable-automatic-resolution",
        ),
    ]
    package_step = find_named_workflow_step(workflow, "Package self-contained Melix.app")

    previous_step_end = 0
    for build_step in build_steps:
        assert previous_step_end <= build_step.start()
        assert build_step.end() < package_step.start()
        assert "scripts/ci_progress.sh" in build_step.group(0)
        previous_step_end = build_step.end()


def test_package_workflow_wraps_long_packaging_steps_with_ci_progress() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    progress_labels = [
        "Package app bootstrap",
        "Package app CLI build",
        "Package app Swift text worker build",
        "Package app menubar build",
        "Package app smoke checks",
        "Package app Python runtime sync",
        "Package app build metadata",
        "Package app bundle assembly",
    ]

    for label in progress_labels:
        assert f'bash scripts/ci_progress.sh "{label}"' in workflow


def test_find_workflow_step_stops_before_any_next_yaml_list_item() -> None:
    workflow = """
jobs:
  package-app:
    steps:
      - name: Publish app artifact download summary
        if: github.event_name != 'pull_request' && success()
        uses: actions/github-script@v9
      - run: echo should-not-be-included
      - id: next-step
        run: echo also-should-not-be-included
"""

    step = find_workflow_step(workflow, "Publish app artifact download summary")

    assert "uses: actions/github-script@v9" in step
    assert "should-not-be-included" not in step
    assert "next-step" not in step


def test_find_workflow_job_stops_before_any_next_job() -> None:
    workflow = """
jobs:
  detect-main-update:
    runs-on: ubuntu-latest
    steps:
      - name: Decide
        run: echo decide
  unrelated-job:
    runs-on: ubuntu-latest
  package-app:
    runs-on: macos-26
"""

    job = find_workflow_job(workflow, "detect-main-update")

    assert "run: echo decide" in job
    assert "unrelated-job:" not in job
    assert "package-app:" not in job


def test_package_workflow_manual_dispatch_defaults_to_main_checkout() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(r"^[ \t]*workflow_dispatch:[ \t]*$", workflow, flags=re.MULTILINE)
    assert "source_ref:" in workflow
    assert 'default: "main"' in workflow
    assert "type: string" in workflow

    manual_checkout = find_workflow_step(workflow, "Checkout manual package source")
    assert "if: github.event_name == 'workflow_dispatch'" in manual_checkout
    assert "uses: actions/checkout@v6" in manual_checkout
    assert "ref: ${{ inputs.source_ref }}" in manual_checkout

    event_checkout = find_workflow_step(workflow, "Checkout event source")
    assert "if: github.event_name != 'workflow_dispatch'" in event_checkout
    assert "uses: actions/checkout@v6" in event_checkout
    assert "ref:" not in event_checkout


def test_package_workflow_keeps_permissions_minimal_for_artifact_summary() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(r"^[ \t]*permissions:[ \t]*$", workflow, flags=re.MULTILINE)
    assert re.search(r"^[ \t]+actions:[ \t]+read[ \t]*$", workflow, flags=re.MULTILINE)
    assert re.search(r"^[ \t]+contents:[ \t]+read[ \t]*$", workflow, flags=re.MULTILINE)
    assert re.search(r"^[ \t]+pull-requests:[ \t]+write[ \t]*$", workflow, flags=re.MULTILINE)
    assert not re.search(r"^[ \t]+issues:[ \t]+write[ \t]*$", workflow, flags=re.MULTILINE)


def test_package_workflow_passes_manual_source_ref_through_env_before_shell_use() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    compute_step = find_workflow_step(workflow, "Compute build metadata")
    assert "env:" in compute_step
    assert "SOURCE_REF: ${{ inputs.source_ref }}" in compute_step
    run_body = compute_step.split("run: |", maxsplit=1)[1]
    assert "${{ inputs.source_ref }}" not in run_body
    assert 'ref_name="$SOURCE_REF"' in run_body
    assert 'refs/tags/${source_ref_name}' in run_body
    assert 'ref_type="tag"' in run_body


def test_package_workflow_publishes_download_summary_for_uploaded_app_artifact() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    summary_step = find_workflow_step(workflow, "Publish app artifact download summary")
    assert "github.event_name != 'pull_request' && success()" in summary_step
    assert "github.rest.actions.listWorkflowRunArtifacts" in summary_step
    assert "process.env.GITHUB_STEP_SUMMARY" in summary_step
    assert "Download packaged Melix.app" in summary_step
    assert "Artifact:" in summary_step
    assert "Download:" in summary_step
    assert "Workflow run:" in summary_step
    assert "artifacts/${artifact.id}" in summary_step


def test_package_workflow_runs_daily_at_midnight_utc() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(r"^[ \t]*schedule:[ \t]*$", workflow, flags=re.MULTILINE)
    assert re.search(
        r"^[ \t]*-[ \t]+cron:[ \t]+\"0 0 \* \* \*\"[ \t]*$",
        workflow,
        flags=re.MULTILINE,
    )


def test_package_workflow_detects_scheduled_main_updates_before_packaging() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(r"^[ \t]+detect-main-update:[ \t]*$", workflow, flags=re.MULTILINE)
    assert "should_package: ${{ steps.detect-main-update.outputs.should_package }}" in workflow
    preflight_job = find_workflow_job(workflow, "detect-main-update")
    assert "if: github.event_name == 'schedule'" in preflight_job
    assert "actions/checkout@v6" in preflight_job
    assert "ref: main" in preflight_job
    assert "github.rest.actions.listWorkflowRuns" in preflight_job
    assert "event: 'schedule'" in preflight_job
    assert "status: 'success'" in preflight_job
    assert "github.rest.actions.listWorkflowRunArtifacts" in preflight_job
    assert ".name.startsWith('Melix-main-')" in preflight_job
    assert "matchedRun.head_sha === currentSha" in preflight_job


def test_package_workflow_successfully_skips_scheduled_run_without_main_changes() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    preflight_job = find_workflow_job(workflow, "detect-main-update")
    assert "No package needed" in preflight_job
    assert "Current main SHA:" in preflight_job
    assert "Last successful scheduled app package SHA:" in preflight_job
    assert "core.setOutput('should_package', 'false')" in preflight_job


def test_package_workflow_isolates_scheduled_concurrency_from_push_runs() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "package-self-contained-app-${{ github.event_name == 'schedule' && 'schedule-' || '' }}${{ github.ref }}" in workflow


def test_package_workflow_gates_package_job_only_for_scheduled_skip_and_pr_label() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(
        r"^[ \t]+package-app:[ \t]*\n[ \t]+needs:[ \t]*\n[ \t]+-[ \t]+detect-main-update",
        workflow,
        flags=re.MULTILINE,
    )
    package_app_job = find_workflow_job(workflow, "package-app")
    assert "github.event_name != 'schedule' || needs.detect-main-update.outputs.should_package == 'true'" in package_app_job
    assert "github.event_name != 'pull_request' || contains(github.event.pull_request.labels.*.name, 'package-app')" in package_app_job
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow


def test_package_workflow_sets_nightly_artifact_retention() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    upload_step = find_workflow_step(workflow, "Upload app artifact")
    assert "retention-days: 14" in upload_step


def test_packaging_runbook_documents_daily_main_app_archive() -> None:
    runbook = PACKAGING_RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "Daily App Archive From `main`" in runbook
    assert "00:00 UTC" in runbook
    assert "last successful scheduled app artifact" in runbook
    assert "14 days" in runbook


def test_main_resolves_default_build_outputs_and_prints_app_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    menubar_binary = repo_root / "apps/macos-menubar/.build/release/melix-menubar"
    cli_binary = repo_root / ".build/release/melix"
    swift_worker_binary = (
        repo_root / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/release/melix-text-worker-swift"
    )
    python_executable = repo_root / ".venv/bin/python"
    site_packages = repo_root / ".venv/lib/python3.13/site-packages"
    for path in (menubar_binary, cli_binary, swift_worker_binary, python_executable):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    site_packages.mkdir(parents=True)
    seen: dict[str, object] = {}

    def fake_write_unsigned_macos_app_bundle(**kwargs):
        seen.update(kwargs)
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "packaging_target_id": "macos_app_bundle_preview",
            "timings": {
                "write_total_seconds": 0.125,
            },
        }

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write_unsigned_macos_app_bundle)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "package_macos_menubar_app.py",
            "--repo-root",
            str(repo_root),
            "--output-path",
            str(tmp_path / "Melix.app"),
        ],
    )

    assert module.main() == 0

    assert capsys.readouterr().out.strip() == str(tmp_path / "Melix.app")
    assert seen["executable_path"] == menubar_binary.resolve()
    assert seen["cli_executable_path"] == cli_binary.resolve()
    assert seen["swift_text_worker_executable_path"] == swift_worker_binary.resolve()
    assert seen["python_runtime_root"] == python_executable.resolve().parent.parent
    assert seen["python_site_packages_path"] == site_packages.resolve()


def test_main_records_archive_timing_in_json_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    seen: dict[str, object] = {}

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(module, "resolve_built_cli_binary", lambda repo_root: tmp_path / "melix")
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    call_order: list[str] = []

    def fake_write_unsigned_macos_app_bundle(**kwargs):
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "packaging_target_id": "macos_app_bundle_preview",
            "timings": {
                "write_total_seconds": 0.25,
            },
        }

    def fake_adhoc_sign_macos_app_bundle(app_path):
        call_order.append("sign")
        seen["signed_app_path"] = app_path
        return True

    def fake_archive_macos_app_bundle(app_path, requested_archive_path):
        call_order.append("archive")
        seen["app_path"] = app_path
        seen["archive_path"] = requested_archive_path
        return Path(requested_archive_path)

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write_unsigned_macos_app_bundle)
    monkeypatch.setattr(module, "adhoc_sign_macos_app_bundle", fake_adhoc_sign_macos_app_bundle)
    monkeypatch.setattr(module, "archive_macos_app_bundle", fake_archive_macos_app_bundle)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "package_macos_menubar_app.py",
            "--repo-root",
            str(tmp_path / "repo"),
            "--output-path",
            str(tmp_path / "Melix.app"),
            "--archive-path",
            str(archive_path),
            "--json",
        ],
    )

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["archive_path"] == str(archive_path)
    assert payload["adhoc_signed"] is True
    assert seen["signed_app_path"] == str(tmp_path / "Melix.app")
    assert seen["archive_path"] == str(archive_path)
    assert call_order == ["sign", "archive"]
    assert payload["timings"]["write_total_seconds"] == 0.25
    assert isinstance(payload["timings"]["adhoc_sign_seconds"], float)
    assert payload["timings"]["adhoc_sign_seconds"] >= 0.0
    assert isinstance(payload["timings"]["archive_seconds"], float)
    assert payload["timings"]["archive_seconds"] >= 0.0
    assert payload["timings"]["total_seconds"] >= payload["timings"]["write_total_seconds"]


def test_main_requires_write_timing_when_archive_is_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(module, "resolve_built_cli_binary", lambda repo_root: tmp_path / "melix")
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "write_unsigned_macos_app_bundle",
        lambda **kwargs: {"app_path": str(tmp_path / "Melix.app"), "timings": {}},
    )
    monkeypatch.setattr(module, "adhoc_sign_macos_app_bundle", lambda app_path: True)
    monkeypatch.setattr(module, "archive_macos_app_bundle", lambda app_path, requested_archive_path: archive_path)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "package_macos_menubar_app.py",
            "--repo-root",
            str(tmp_path / "repo"),
            "--output-path",
            str(tmp_path / "Melix.app"),
            "--archive-path",
            str(archive_path),
            "--json",
        ],
    )

    with pytest.raises(KeyError, match="write_total_seconds missing"):
        module.main()
