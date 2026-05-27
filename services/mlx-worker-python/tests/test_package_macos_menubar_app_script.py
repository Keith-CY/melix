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
        r"(?P<body>.*?)(?=^[ \t]*-[ \t]+(?:name:|uses:)|\Z)",
        workflow,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Workflow step not found: {name}"
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


def test_resolve_built_products_use_direct_debug_candidate_before_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    menubar_binary = repo_root / "apps/macos-menubar/.build/debug/melix-menubar"
    cli_binary = repo_root / ".build/debug/melix"
    swift_worker_binary = repo_root / "services/mlx-text-worker-swift/.build/debug/melix-text-worker-swift"
    for binary in (menubar_binary, cli_binary, swift_worker_binary):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fail_glob(self: Path, pattern: str):
        raise AssertionError("direct debug candidate should avoid scanning build triples")

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert module.resolve_built_binary(repo_root) == menubar_binary
    assert module.resolve_built_cli_binary(repo_root) == cli_binary
    assert module.resolve_built_swift_text_worker_binary(repo_root) == swift_worker_binary


def test_resolve_built_product_falls_back_to_sorted_triple_debug_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arm64-apple-macosx/debug/melix-menubar"
    later = build_root / "x86_64-apple-macosx/debug/melix-menubar"
    for binary in (later, expected):
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


def test_resolve_built_product_returns_lex_first_triple_without_sorting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    expected = build_root / "arm64-apple-macosx/debug/melix-menubar"
    later = build_root / "x86_64-apple-macosx/debug/melix-menubar"
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
    expected = build_root / "arm64-apple-macosx/debug/melix-menubar"
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


def test_resolve_built_cli_binary_falls_back_with_scandir_without_path_glob(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    expected = repo_root / ".build/arm64-apple-macosx/debug/melix"
    later = repo_root / ".build/x86_64-apple-macosx/debug/melix"
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
    assert re.search(r'PACKAGE_PYTHON="\$GITHUB_WORKSPACE/\.venv-package/bin/python"', workflow)
    assert "--python-runtime-root" in workflow
    assert "$PYTHON_RUNTIME_ROOT" in workflow
    assert "--python-site-packages-path" in workflow
    assert "$PYTHON_SITE_PACKAGES" in workflow


def test_package_workflow_builds_required_swift_products_before_packaging_app() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    build_steps = [
        find_run_workflow_step(
            workflow,
            "Build CLI executable",
            "swift build --product melix --disable-automatic-resolution",
        ),
        find_run_workflow_step(
            workflow,
            "Build Swift text worker",
            "swift build --package-path services/mlx-text-worker-swift --disable-automatic-resolution",
        ),
        find_run_workflow_step(
            workflow,
            "Build menu bar app executable",
            "swift build --package-path apps/macos-menubar --disable-automatic-resolution",
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


def test_package_workflow_publishes_download_summary_for_uploaded_app_artifact() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert re.search(r"^[ \t]*permissions:[ \t]*$", workflow, flags=re.MULTILINE)
    assert re.search(r"^[ \t]+actions:[ \t]+read[ \t]*$", workflow, flags=re.MULTILINE)

    summary_step = find_workflow_step(workflow, "Publish app artifact download summary")
    assert "github.event_name != 'pull_request' && success()" in summary_step
    assert "github.rest.actions.listWorkflowRunArtifacts" in summary_step
    assert "process.env.GITHUB_STEP_SUMMARY" in summary_step
    assert "Download packaged Melix.app" in summary_step
    assert "Artifact:" in summary_step
    assert "Download:" in summary_step
    assert "Workflow run:" in summary_step
    assert "artifacts/${artifact.id}" in summary_step


def test_main_resolves_default_build_outputs_and_prints_app_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    menubar_binary = repo_root / "apps/macos-menubar/.build/debug/melix-menubar"
    cli_binary = repo_root / ".build/debug/melix"
    swift_worker_binary = (
        repo_root / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/melix-text-worker-swift"
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

    def fake_write_unsigned_macos_app_bundle(**kwargs):
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "packaging_target_id": "macos_app_bundle_preview",
            "timings": {
                "write_total_seconds": 0.25,
            },
        }

    def fake_archive_macos_app_bundle(app_path, requested_archive_path):
        seen["app_path"] = app_path
        seen["archive_path"] = requested_archive_path
        return Path(requested_archive_path)

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write_unsigned_macos_app_bundle)
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
    assert seen["archive_path"] == str(archive_path)
    assert payload["timings"]["write_total_seconds"] == 0.25
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
