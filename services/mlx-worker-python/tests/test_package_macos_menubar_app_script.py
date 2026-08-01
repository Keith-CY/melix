from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import worker.productization.macos_app_bundle as macos_app_bundle_module


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "package_macos_menubar_app.py"
PACKAGE_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "package-self-contained-app.yml"
PACKAGING_RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "platform-packaging-targets.md"


@pytest.fixture(autouse=True)
def stable_codesign_detail_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, target: "flags=0x10000(runtime)\n",
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_verify_codesign_identity_evidence",
        lambda *args, **kwargs: None,
    )


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


def workflow_step_uses(step: str) -> str:
    match = re.search(
        r"^[ \t]*uses:[ \t]+['\"]?(?P<uses>[^'\"\s]+)['\"]?[ \t]*$",
        step,
        flags=re.MULTILINE,
    )
    assert match is not None, "Workflow step missing uses:"
    return match.group("uses")


def checkout_action_ref(step: str) -> str:
    action_ref = workflow_step_uses(step)
    match = re.fullmatch(r"actions/checkout@v(?P<major>[0-9]+)(?:\.[0-9]+)*", action_ref)
    assert match is not None, f"Workflow step should use actions/checkout, got: {action_ref}"
    assert int(match.group("major")) >= 7
    return action_ref


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


def test_resolve_app_code_signing_configuration_separates_preview_and_release(
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    preview = module.resolve_app_code_signing_configuration(
        sparkle_feed_url="",
        sparkle_public_ed_key="",
        bundle_id="io.melix.menubar.preview",
        packaging_target_id="macos_app_bundle_preview",
        codesign_identity="-",
        codesign_keychain="",
    )
    assert preview.mode == "adhoc"
    assert preview.identity == "-"
    assert preview.expected_certificate_sha256 is None
    assert preview.expected_certificate_sha1 is None

    keychain_path = tmp_path / "melix-release-signing.keychain-db"
    keychain_path.write_bytes(b"fixture")
    certificate_sha1 = "0123456789ABCDEF0123456789ABCDEF01234567"
    certificate_sha256 = "AB" * 32
    release = module.resolve_app_code_signing_configuration(
        sparkle_feed_url=(
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml"
        ),
        sparkle_public_ed_key="public-key-fixture",
        bundle_id="io.melix.menubar",
        packaging_target_id="macos_app_bundle_github_release",
        codesign_identity=certificate_sha1,
        codesign_keychain=str(keychain_path),
        codesign_certificate_sha256=certificate_sha256,
    )
    assert release.mode == "stable_self_signed"
    assert release.identity == certificate_sha1.lower()
    assert release.keychain_path == keychain_path.resolve()
    assert release.expected_certificate_sha256 == certificate_sha256.lower()
    assert release.expected_certificate_sha1 == certificate_sha1.lower()
    assert release.expected_authority == "Melix GitHub Release Signing"


@pytest.mark.parametrize(
    (
        "feed_url",
        "public_key",
        "bundle_id",
        "target_id",
        "identity",
        "keychain",
        "message",
    ),
    [
        ("feed", "", "io.melix.menubar.preview", "macos_app_bundle_preview", "-", "", "provided together"),
        ("feed", "key", "io.melix.menubar.preview", "macos_app_bundle_preview", "-", "", "release bundle ID"),
        ("", "", "io.melix.menubar", "macos_app_bundle_github_release", "-", "", "must not be used"),
        ("feed", "key", "io.melix.menubar", "macos_app_bundle_github_release", "-", "", "stable self-signed"),
        ("", "", "io.melix.menubar.preview", "macos_app_bundle_preview", "-", "/tmp/keychain", "must not receive"),
        ("", "", "io.melix.menubar.preview", "macos_app_bundle_preview", "0" * 40, "/tmp/keychain", "must not be used"),
        ("feed", "key", "io.melix.menubar", "macos_app_bundle_github_release", "not-a-sha", "/tmp/keychain", "40 hex digits"),
        ("feed", "key", "io.melix.menubar", "macos_app_bundle_github_release", "0" * 40, "", "explicit ephemeral keychain"),
        ("feed", "key", "io.melix.menubar", "macos_app_bundle_github_release", "0" * 40, "/tmp/missing-keychain", "keychain is missing"),
    ],
)
def test_resolve_app_code_signing_configuration_fails_closed(
    feed_url: str,
    public_key: str,
    bundle_id: str,
    target_id: str,
    identity: str,
    keychain: str,
    message: str,
) -> None:
    module = load_package_macos_app_module()

    with pytest.raises((ValueError, FileNotFoundError), match=message):
        module.resolve_app_code_signing_configuration(
            sparkle_feed_url=feed_url,
            sparkle_public_ed_key=public_key,
            bundle_id=bundle_id,
            packaging_target_id=target_id,
            codesign_identity=identity,
            codesign_keychain=keychain,
            codesign_certificate_sha256="0" * 64,
        )


def test_main_rejects_signed_update_release_without_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    keychain_path = tmp_path / "melix-release-signing.keychain-db"
    keychain_path.write_bytes(b"fixture")
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "package_macos_menubar_app.py",
            "--bundle-id",
            "io.melix.menubar",
            "--packaging-target-id",
            "macos_app_bundle_github_release",
            "--sparkle-feed-url",
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
            "--sparkle-public-ed-key",
            "public-key-fixture",
            "--codesign-identity",
            "0" * 40,
            "--codesign-keychain",
            str(keychain_path),
            "--codesign-certificate-sha256",
            "0" * 64,
        ],
    )

    with pytest.raises(ValueError, match="require an archive path"):
        module.main()


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
        "resolve_built_control_plane_binary",
        lambda repo_root: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "resolve_swift_mlx_metallib",
        lambda repo_root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda repo_root, configured_path=None: tmp_path / "Sparkle.framework",
    )

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
            "--allow-insecure-http-host",
            "192.0.2.10",
            "--json",
        ],
    )

    assert module.main() == 0
    assert seen["cli_executable_path"] == tmp_path / "melix"
    assert seen["control_plane_executable_path"] == tmp_path / "melix-control-plane"
    assert seen["swift_mlx_metallib_path"] == tmp_path / "mlx.metallib"
    assert seen["swift_mlx_metallib_version"] == "0.31.1"
    assert seen["sparkle_framework_path"] == tmp_path / "Sparkle.framework"
    assert seen["code_signing_mode"] == "adhoc"
    assert seen["code_signing_certificate_sha1"] is None
    assert seen["code_signing_authority"] is None
    assert seen["packaging_target_id"] == "macos_app_bundle_preview"
    assert seen["update_channel_path"] == str(tmp_path / "stable.json")
    assert seen["icon_source_path"] == str(tmp_path / "MelixAppIcon.icns")
    assert seen["insecure_http_hosts"] == ["192.0.2.10"]

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
    control_plane_binary = repo_root / "services/control-plane-swift/.build/release/melix-control-plane"
    swift_worker_binary = repo_root / "services/mlx-text-worker-swift/.build/release/melix-text-worker-swift"
    debug_binaries = (
        repo_root / "apps/macos-menubar/.build/debug/melix-menubar",
        repo_root / ".build/debug/melix",
        repo_root / "services/control-plane-swift/.build/debug/melix-control-plane",
        repo_root / "services/mlx-text-worker-swift/.build/debug/melix-text-worker-swift",
    )
    for binary in (menubar_binary, cli_binary, control_plane_binary, swift_worker_binary, *debug_binaries):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def fail_glob(self: Path, pattern: str):
        raise AssertionError("direct release candidate should avoid scanning build triples")

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert module.resolve_built_binary(repo_root) == menubar_binary
    assert module.resolve_built_cli_binary(repo_root) == cli_binary
    assert module.resolve_built_control_plane_binary(repo_root) == control_plane_binary
    assert module.resolve_built_swift_text_worker_binary(repo_root) == swift_worker_binary


def test_resolve_built_control_plane_requires_built_product(tmp_path: Path) -> None:
    module = load_package_macos_app_module()

    with pytest.raises(FileNotFoundError, match="Unable to find built `melix-control-plane`"):
        module.resolve_built_control_plane_binary(tmp_path / "repo")


def _write_complete_sparkle_framework(framework_path: Path) -> None:
    for relative_path in (
        "Versions/B/Sparkle",
        "Versions/B/Autoupdate",
        "Versions/B/Updater.app",
        "Versions/B/XPCServices/Downloader.xpc",
        "Versions/B/XPCServices/Installer.xpc",
    ):
        path = framework_path / relative_path
        if path.suffix in {".app", ".xpc"}:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"sparkle")


def test_resolve_sparkle_framework_accepts_complete_default_artifact(tmp_path: Path) -> None:
    module = load_package_macos_app_module()
    repo_root = tmp_path / "repo"
    framework_path = (
        repo_root
        / "apps/macos-menubar/.build/artifacts/sparkle/Sparkle/Sparkle.xcframework"
        / "macos-arm64_x86_64/Sparkle.framework"
    )
    _write_complete_sparkle_framework(framework_path)

    assert module.resolve_sparkle_framework(repo_root) == framework_path.resolve()


def test_resolve_sparkle_framework_requires_existing_artifact(tmp_path: Path) -> None:
    module = load_package_macos_app_module()

    with pytest.raises(FileNotFoundError, match="Unable to find the complete Sparkle framework"):
        module.resolve_sparkle_framework(tmp_path / "repo")


def test_resolve_sparkle_framework_rejects_incomplete_configured_artifact(
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    framework_path = tmp_path / "Sparkle.framework"
    framework_path.mkdir()

    with pytest.raises(FileNotFoundError, match="Sparkle framework is incomplete"):
        module.resolve_sparkle_framework(tmp_path / "repo", framework_path)


def test_resolve_swift_mlx_metallib_requires_a_compatible_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    metallib_path = tmp_path / "mlx_metal-0.31.2/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_bytes(b"metal")
    monkeypatch.setattr(module, "read_mlx_metal_dist_info_version", lambda path: "0.31.2")
    monkeypatch.setattr(
        module,
        "compatible_mlx_metal_versions_for_swift_mlx",
        lambda repo_root: ("0.31.1",),
    )

    with pytest.raises(RuntimeError, match="Incompatible Swift MLX metallib 0.31.2"):
        module.resolve_swift_mlx_metallib(tmp_path / "repo", metallib_path)


def test_resolve_swift_mlx_metallib_returns_discovered_matching_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    metallib_path = tmp_path / "mlx_metal-0.31.1/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_bytes(b"metal")
    monkeypatch.setattr(module, "resolve_local_mlx_metallib", lambda repo_root, uv_cache_dir: metallib_path)
    monkeypatch.setattr(module, "read_mlx_metal_dist_info_version", lambda path: "0.31.1")
    monkeypatch.setattr(
        module,
        "compatible_mlx_metal_versions_for_swift_mlx",
        lambda repo_root: ("0.31.1",),
    )

    assert module.resolve_swift_mlx_metallib(tmp_path / "repo") == (metallib_path, "0.31.1")


def test_resolve_swift_mlx_metallib_rejects_a_version_without_compatibility_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    metallib_path = tmp_path / "mlx_metal-0.31.1/mlx/lib/mlx.metallib"
    metallib_path.parent.mkdir(parents=True)
    metallib_path.write_bytes(b"metal")
    monkeypatch.setattr(module, "read_mlx_metal_dist_info_version", lambda path: "0.31.1")
    monkeypatch.setattr(
        module,
        "compatible_mlx_metal_versions_for_swift_mlx",
        lambda repo_root: (),
    )

    with pytest.raises(RuntimeError, match="Unable to prove Swift MLX metallib compatibility"):
        module.resolve_swift_mlx_metallib(tmp_path / "repo", metallib_path)


def test_resolve_swift_mlx_metallib_rejects_missing_configured_path(tmp_path: Path) -> None:
    module = load_package_macos_app_module()

    with pytest.raises(FileNotFoundError, match="MELIX_SWIFT_MLX_METALLIB_PATH does not point to a file"):
        module.resolve_swift_mlx_metallib(tmp_path / "repo", tmp_path / "missing.metallib")


def test_resolve_swift_mlx_metallib_requires_discovered_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    monkeypatch.setattr(module, "resolve_local_mlx_metallib", lambda repo_root, uv_cache_dir: None)

    with pytest.raises(FileNotFoundError, match="No compatible Swift MLX metallib was found"):
        module.resolve_swift_mlx_metallib(tmp_path / "repo")


def test_resolve_swift_mlx_metallib_requires_version_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    metallib_path = tmp_path / "mlx.metallib"
    metallib_path.write_bytes(b"metal")
    monkeypatch.setattr(module, "read_mlx_metal_dist_info_version", lambda path: None)

    with pytest.raises(RuntimeError, match="Unable to determine the mlx_metal version"):
        module.resolve_swift_mlx_metallib(tmp_path / "repo", metallib_path)


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


def test_resolve_built_product_reuses_initial_scan_for_remaining_debug_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    first_triple = build_root / "arm64-apple-macosx"
    later_debug = build_root / "x86_64-apple-macosx/debug/melix"
    first_triple.mkdir(parents=True)
    later_debug.parent.mkdir(parents=True)
    later_debug.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    original_scandir = module.os.scandir
    scandir_calls = 0

    def counting_scandir(path: Path):
        nonlocal scandir_calls
        scandir_calls += 1
        if scandir_calls > 1:
            raise AssertionError("remaining fallback candidates should reuse the initial os.scandir() results")  # pragma: no cover
        return original_scandir(path)

    monkeypatch.setattr(module.os, "scandir", counting_scandir)

    assert module._resolve_built_product(build_root, "melix") == later_debug
    assert scandir_calls == 1


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


def test_resolve_built_product_keeps_remaining_release_priority_after_debug_candidate(
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    build_root = tmp_path / ".build"
    (build_root / "arch-0000").mkdir(parents=True)
    debug = build_root / "arch-0001/debug/melix"
    release = build_root / "arch-0002/release/melix"
    for binary in (debug, release):
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert module._resolve_built_product(build_root, "melix") == release


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


def test_package_workflow_installs_matching_swift_mlx_metallib() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    runtime_step = find_workflow_step(workflow, "Prepare packaging Python runtime")
    assert "compatible_mlx_metal_versions_for_swift_mlx" in runtime_step
    assert 'uv pip install --target "$SWIFT_MLX_METAL_ROOT"' in runtime_step
    assert '"mlx-metal==$SWIFT_MLX_METAL_VERSION"' in runtime_step
    assert 'SWIFT_MLX_METALLIB_PATH="$SWIFT_MLX_METAL_ROOT/mlx/lib/mlx.metallib"' in runtime_step
    assert "SWIFT_MLX_METALLIB_PATH=%s" in runtime_step

    package_step = find_workflow_step(workflow, "Package self-contained Melix.app")
    assert '--swift-mlx-metallib-path "$SWIFT_MLX_METALLIB_PATH"' in package_step


@pytest.mark.parametrize(
    "path",
    [
        "Makefile",
        "Package.swift",
        "Package.resolved",
        "Sources/**",
        "pyproject.toml",
        "uv.lock",
        "scripts/ci_progress.sh",
        "scripts/compute_build_metadata.py",
        "scripts/dev_up.py",
        "scripts/finalize_macos_release_candidate.py",
        "scripts/m8_packaging_target_smoke.py",
        "scripts/macos_release_candidate.py",
        "scripts/macos_self_signed_identity.py",
        "scripts/validate_macos_release_tag.py",
    ],
)
def test_package_workflow_triggers_for_direct_packaging_inputs(path: str) -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert workflow.count(f'- "{path}"') == 2


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
            "Build control plane executable",
            "swift build -c release --package-path services/control-plane-swift --product melix-control-plane --disable-automatic-resolution",
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


def test_package_workflow_builds_isolated_tag_candidate_without_release_trust() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    package_step = find_workflow_step(workflow, "Package self-contained Melix.app")
    assert "IS_RELEASE_CANDIDATE:" in package_step
    assert 'if [ "$IS_RELEASE_CANDIDATE" = "true" ]; then' in package_step
    assert '"io.melix.menubar.release-candidate"' in package_step
    assert '"macos_app_bundle_github_release_candidate"' in package_step
    for protected_input in ("secrets.", "vars.", "--sparkle-public-ed-key", "--codesign-identity"):
        assert protected_input not in package_step


def test_package_workflow_prepares_and_cleans_identity_only_in_protected_job() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    protected_job = find_workflow_job(workflow, "publish-signed-release")
    assert "environment: github-release" in protected_job
    assert "group: melix-protected-github-release" in protected_job
    assert "cancel-in-progress: false" in protected_job
    assert "Revalidate candidate receipt before protected inputs" in protected_job
    secret_index = protected_job.index("secrets.MELIX_SIGNING_CERTIFICATE_P12")
    variable_index = protected_job.index("vars.SPARKLE_EDDSA_PUBLIC_KEY")
    receipt_index = protected_job.index("macos_release_candidate.py verify")
    assert receipt_index < secret_index
    assert receipt_index < variable_index
    assert "vars.MELIX_SIGNING_CERTIFICATE_SHA256" in protected_job
    assert "vars.MELIX_SIGNING_CERTIFICATE_SHA1" in protected_job
    assert "macos_self_signed_identity.py prepare" in protected_job
    assert "macos_self_signed_identity.py cleanup" in protected_job
    assert "cleanup_confirmed=true" in protected_job
    assert protected_job.index("cleanup_confirmed=true") < protected_job.index("softprops/action-gh-release")
    package_job = find_workflow_job(workflow, "package-app")
    assert "secrets." not in package_job
    assert "vars." not in package_job


def test_package_workflow_exercises_real_trust_only_on_github_hosted_pull_request() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    smoke_job = find_workflow_job(workflow, "self-signed-trust-smoke")
    assert "if: github.event_name == 'pull_request'" in smoke_job
    assert "runs-on: macos-15" in smoke_job
    assert "macos_self_signed_identity.py prepare" in smoke_job
    assert "macos_self_signed_identity.py cleanup" in smoke_job
    assert "cleanup_confirmed" in smoke_job


def test_protected_release_requires_source_minimum_system_version_in_appcast() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    signed_feed_step = find_workflow_step(workflow, "Generate and verify signed update feed")
    assert 'test "$EXPECTED_TAG" = "v$EXPECTED_VERSION"' in signed_feed_step
    assert 'local-name()="item"]/*[local-name()="version"' in signed_feed_step
    assert 'test "$appcast_version" = "$EXPECTED_VERSION"' in signed_feed_step
    assert 'local-name()="item"]/*[local-name()="shortVersionString"' in signed_feed_step
    assert 'test "$appcast_short_version" = "$EXPECTED_VERSION"' in signed_feed_step
    assert "minimumSystemVersion" in signed_feed_step
    assert 'test "$minimum_system_version" = "15.0"' in signed_feed_step


def test_package_workflow_keeps_preview_archives_adhoc_and_update_disabled() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")
    package_step = find_workflow_step(workflow, "Package self-contained Melix.app")
    release_condition = package_step.index('if [ "$IS_RELEASE_CANDIDATE" = "true" ]; then')
    package_command = package_step.index(
        'bash scripts/ci_progress.sh "Package app bundle assembly"',
        release_condition,
    )
    release_only_block = package_step[release_condition:package_command]

    for release_only_argument in (
        "io.melix.menubar.release-candidate",
        "macos_app_bundle_github_release_candidate",
    ):
        assert release_only_argument in release_only_block
        assert package_step.count(release_only_argument) == 1


def test_protected_release_generates_and_verifies_appcast_without_key_files() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    signed_feed_step = find_workflow_step(
        workflow,
        "Generate and verify signed update feed",
    )
    assert "SPARKLE_PRIVATE_KEY: ${{ secrets.SPARKLE_EDDSA_PRIVATE_KEY }}" in signed_feed_step
    assert "SPARKLE_PUBLIC_KEY: ${{ vars.SPARKLE_EDDSA_PUBLIC_KEY }}" in signed_feed_step
    assert "private_key_bytes" in signed_feed_step
    assert "openssl pkey -inform DER -pubout -outform DER" in signed_feed_step
    assert 'test "$derived_public_key" = "$SPARKLE_PUBLIC_KEY"' in signed_feed_step
    assert '"$sparkle_bin/generate_appcast"' in signed_feed_step
    assert signed_feed_step.count("--ed-key-file -") == 3
    assert 'xmllint --noout "$appcast_path"' in signed_feed_step
    assert "edSignature" in signed_feed_step
    assert "private_key_path" not in signed_feed_step
    assert "> \"$private" not in signed_feed_step


def test_package_workflow_publishes_only_final_archive_after_cleanup() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    release_job = find_workflow_job(workflow, "publish-signed-release")
    assert "attach-release-artifact:" not in workflow
    assert "environment: github-release" in release_job
    assert "steps.release-cleanup.outputs.cleanup_confirmed == 'true'" in release_job
    assert "signed-update-release/${{ needs.package-app.outputs.artifact_name }}.zip" in release_job
    assert "release-candidate/${{ needs.package-app.outputs.archive_name }}" in release_job
    assert release_job.index("macos_release_candidate.py verify") < release_job.index("secrets.")
    cleanup_index = release_job.index("cleanup_confirmed=true")
    final_tag_fetch_index = release_job.index("git fetch --force --tags origin", cleanup_index)
    final_validation_index = release_job.index(
        "python3 scripts/validate_macos_release_tag.py", final_tag_fetch_index
    )
    publish_index = release_job.index("softprops/action-gh-release")
    assert cleanup_index < final_tag_fetch_index < final_validation_index < publish_index
    assert release_job.count("python3 scripts/validate_macos_release_tag.py") == 2
    assert "make_latest: true" in release_job


def test_package_workflow_verifies_latest_release_and_published_appcast_before_dispatch() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    release_job = find_workflow_job(workflow, "publish-signed-release")
    publish_index = release_job.index("softprops/action-gh-release")
    latest_index = release_job.index('repos/$RELEASE_REPOSITORY/releases/latest', publish_index)
    download_index = release_job.index('gh release download "$EXPECTED_TAG"', latest_index)
    dispatch_index = release_job.index("melix-release-asset-published", download_index)
    assert publish_index < latest_index < download_index < dispatch_index
    assert 'test "$latest_tag" = "$EXPECTED_TAG"' in release_job
    assert 'test "$appcast_version" = "$EXPECTED_VERSION"' in release_job
    assert 'test "$appcast_short_version" = "$EXPECTED_VERSION"' in release_job
    assert 'test "$minimum_system_version" = "15.0"' in release_job
    assert (
        'releases/download/$EXPECTED_TAG/$RELEASE_ARCHIVE_NAME' in release_job
    )


def test_package_workflow_wraps_long_packaging_steps_with_ci_progress() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    progress_labels = [
        "Package app bootstrap",
        "Package app CLI build",
        "Package app control plane build",
        "Package app Swift text worker build",
        "Package app menubar build",
        "Package app smoke checks",
        "Package app Python runtime sync",
        "Package app Swift MLX metallib",
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
    manual_checkout_action = checkout_action_ref(manual_checkout)
    assert "ref: ${{ inputs.source_ref }}" in manual_checkout

    event_checkout = find_workflow_step(workflow, "Checkout event source")
    assert "if: github.event_name != 'workflow_dispatch'" in event_checkout
    assert checkout_action_ref(event_checkout) == manual_checkout_action
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
    assert (
        "github.event_name != 'pull_request' && github.ref_type != 'tag' && success()"
        in summary_step
    )
    assert "github.rest.actions.listWorkflowRunArtifacts" in summary_step
    assert "process.env.GITHUB_STEP_SUMMARY" in summary_step
    assert "Download packaged Melix.app" in summary_step
    assert "Artifact:" in summary_step
    assert "Download:" in summary_step
    assert "Workflow run:" in summary_step
    assert "artifacts/${artifact.id}" in summary_step


def test_package_workflow_labels_tag_candidate_as_protected_finalizer_input() -> None:
    workflow = PACKAGE_WORKFLOW_PATH.read_text(encoding="utf-8")

    candidate_summary = find_workflow_step(
        workflow,
        "Publish isolated release candidate summary",
    )
    assert (
        "github.event_name == 'push' && github.ref_type == 'tag' && success()"
        in candidate_summary
    )
    assert (
        "CANDIDATE_ARTIFACT_NAME: "
        "${{ steps.package-names.outputs.candidate_artifact_name }}"
        in candidate_summary
    )
    assert (
        "CANDIDATE_ARTIFACT_URL: "
        "${{ steps.upload-release-candidate.outputs.artifact-url }}"
        in candidate_summary
    )
    assert "Candidate artifact link: ${candidateArtifactUrl}" in candidate_summary
    assert "Protected finalizer input: Melix release candidate" in candidate_summary
    assert "Do not install or distribute this artifact" in candidate_summary
    assert "Download packaged Melix.app" not in candidate_summary


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
    preflight_checkout = find_workflow_step(preflight_job, "Checkout scheduled main source")
    assert checkout_action_ref(preflight_checkout) == checkout_action_ref(
        find_workflow_step(workflow, "Checkout manual package source")
    )
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
    assert "github.ref_type != 'tag' || needs.validate-release-tag.result == 'success'" in package_app_job


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
    control_plane_binary = (
        repo_root / "services/control-plane-swift/.build/release/melix-control-plane"
    )
    swift_worker_binary = (
        repo_root / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/release/melix-text-worker-swift"
    )
    python_executable = repo_root / ".venv/bin/python"
    site_packages = repo_root / ".venv/lib/python3.13/site-packages"
    for path in (menubar_binary, cli_binary, control_plane_binary, swift_worker_binary, python_executable):
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
        module,
        "resolve_swift_mlx_metallib",
        lambda root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda root, configured_path=None: tmp_path / "Sparkle.framework",
    )
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
    assert seen["control_plane_executable_path"] == control_plane_binary.resolve()
    assert seen["swift_text_worker_executable_path"] == swift_worker_binary.resolve()
    assert seen["swift_mlx_metallib_path"] == tmp_path / "mlx.metallib"
    assert seen["swift_mlx_metallib_version"] == "0.31.1"
    assert seen["sparkle_framework_path"] == tmp_path / "Sparkle.framework"
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
        "resolve_built_control_plane_binary",
        lambda repo_root: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "resolve_swift_mlx_metallib",
        lambda repo_root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda repo_root, configured_path=None: tmp_path / "Sparkle.framework",
    )
    call_order: list[str] = []

    def fake_write_unsigned_macos_app_bundle(**kwargs):
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "packaging_target_id": "macos_app_bundle_preview",
            "timings": {
                "write_total_seconds": 0.25,
            },
        }

    def fake_sign_macos_app_bundle(app_path, **kwargs):
        call_order.append("sign")
        seen["signed_app_path"] = app_path
        seen["signing_identity"] = kwargs["identity"]
        return True

    def fake_archive_macos_app_bundle(app_path, requested_archive_path):
        call_order.append("archive")
        seen["app_path"] = app_path
        seen["archive_path"] = requested_archive_path
        return Path(requested_archive_path)

    def fake_verify_archived_macos_app_bundle(
        requested_archive_path,
        *,
            expected_app_name,
            require_sparkle_framework=False,
            expected_signing_certificate_sha256=None,
            expected_signing_certificate_sha1=None,
        expected_signing_authority=None,
    ):
        call_order.append("verify")
        seen["verified_archive_path"] = requested_archive_path
        seen["expected_app_name"] = expected_app_name
        seen["require_sparkle_framework"] = require_sparkle_framework
        seen["expected_signing_certificate_sha256"] = expected_signing_certificate_sha256
        seen["expected_signing_certificate_sha1"] = expected_signing_certificate_sha1
        seen["expected_signing_authority"] = expected_signing_authority

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write_unsigned_macos_app_bundle)
    monkeypatch.setattr(module, "sign_macos_app_bundle", fake_sign_macos_app_bundle)
    monkeypatch.setattr(module, "archive_macos_app_bundle", fake_archive_macos_app_bundle)
    monkeypatch.setattr(
        module,
        "verify_archived_macos_app_bundle",
        fake_verify_archived_macos_app_bundle,
    )
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
    assert payload["code_signed"] is True
    assert payload["code_signing_mode"] == "adhoc"
    assert payload["code_signing_certificate_sha1"] is None
    assert payload["code_signing_authority"] is None
    assert seen["signed_app_path"] == str(tmp_path / "Melix.app")
    assert seen["signing_identity"] == "-"
    assert seen["archive_path"] == str(archive_path)
    assert seen["verified_archive_path"] == str(archive_path)
    assert seen["expected_app_name"] == "Melix.app"
    assert seen["require_sparkle_framework"] is True
    assert seen["expected_signing_certificate_sha1"] is None
    assert seen["expected_signing_authority"] is None
    assert call_order == ["sign", "archive", "verify"]
    assert payload["archive_verified"] is True
    assert payload["timings"]["write_total_seconds"] == 0.25
    assert isinstance(payload["timings"]["adhoc_sign_seconds"], float)
    assert payload["timings"]["adhoc_sign_seconds"] >= 0.0
    assert payload["timings"]["code_sign_seconds"] == payload["timings"]["adhoc_sign_seconds"]
    assert isinstance(payload["timings"]["archive_seconds"], float)
    assert payload["timings"]["archive_seconds"] >= 0.0
    assert isinstance(payload["timings"]["archive_verify_seconds"], float)
    assert payload["timings"]["archive_verify_seconds"] >= 0.0
    assert payload["timings"]["total_seconds"] >= payload["timings"]["write_total_seconds"]


def test_main_stable_release_signs_and_reverifies_certificate_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    keychain_path = tmp_path / "melix-release-signing.keychain-db"
    keychain_path.write_bytes(b"fixture")
    certificate_sha1 = "0123456789ABCDEF0123456789ABCDEF01234567"
    seen: dict[str, object] = {}

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(module, "resolve_built_cli_binary", lambda repo_root: tmp_path / "melix")
    monkeypatch.setattr(
        module,
        "resolve_built_control_plane_binary",
        lambda repo_root: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "resolve_swift_mlx_metallib",
        lambda repo_root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda repo_root, configured_path=None: tmp_path / "Sparkle.framework",
    )

    def fake_write(**kwargs):
        seen["write"] = kwargs
        return {
            "app_path": str(tmp_path / "Melix.app"),
            "timings": {"write_total_seconds": 0.1},
        }

    def fake_sign(app_path: str, **kwargs: object) -> bool:
        seen["sign"] = kwargs
        return True

    def fake_archive(app_path: str, requested_archive_path: str) -> Path:
        return Path(requested_archive_path)

    def fake_verify(requested_archive_path: str, **kwargs: object) -> None:
        seen["verify"] = kwargs

    monkeypatch.setattr(module, "write_unsigned_macos_app_bundle", fake_write)
    monkeypatch.setattr(module, "sign_macos_app_bundle", fake_sign)
    monkeypatch.setattr(module, "archive_macos_app_bundle", fake_archive)
    monkeypatch.setattr(module, "verify_archived_macos_app_bundle", fake_verify)
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
            "--bundle-id",
            "io.melix.menubar",
            "--packaging-target-id",
            "macos_app_bundle_github_release",
            "--sparkle-feed-url",
            "https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml",
            "--sparkle-public-ed-key",
            "public-key-fixture",
            "--codesign-identity",
            certificate_sha1,
            "--codesign-keychain",
            str(keychain_path),
            "--codesign-certificate-sha256",
            "a" * 64,
            "--json",
        ],
    )

    assert module.main() == 0

    payload = json.loads(capsys.readouterr().out)
    normalized_sha1 = certificate_sha1.lower()
    assert payload["code_signed"] is True
    assert payload["adhoc_signed"] is False
    assert payload["code_signing_mode"] == "stable_self_signed"
    assert payload["code_signing_certificate_sha256"] == "a" * 64
    assert payload["code_signing_certificate_sha1"] == normalized_sha1
    assert payload["code_signing_authority"] == "Melix GitHub Release Signing"
    assert seen["write"]["bundle_id"] == "io.melix.menubar"
    assert seen["write"]["packaging_target_id"] == "macos_app_bundle_github_release"
    assert seen["write"]["code_signing_mode"] == "stable_self_signed"
    assert seen["write"]["code_signing_certificate_sha256"] == "a" * 64
    assert seen["write"]["code_signing_certificate_sha1"] == normalized_sha1
    assert seen["write"]["code_signing_authority"] == "Melix GitHub Release Signing"
    assert seen["sign"] == {
        "identity": normalized_sha1,
        "keychain_path": keychain_path.resolve(),
        "expected_certificate_sha256": "a" * 64,
        "expected_certificate_sha1": normalized_sha1,
        "expected_authority": "Melix GitHub Release Signing",
    }
    assert seen["verify"]["expected_signing_certificate_sha256"] == "a" * 64
    assert seen["verify"]["expected_signing_certificate_sha1"] == normalized_sha1
    assert seen["verify"]["expected_signing_authority"] == "Melix GitHub Release Signing"
    assert "adhoc_sign_seconds" not in payload["timings"]
    assert payload["timings"]["code_sign_seconds"] >= 0.0


def test_main_stops_before_archive_when_adhoc_signing_or_deep_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(module, "resolve_built_cli_binary", lambda repo_root: tmp_path / "melix")
    monkeypatch.setattr(
        module,
        "resolve_built_control_plane_binary",
        lambda repo_root: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "resolve_swift_mlx_metallib",
        lambda repo_root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda repo_root, configured_path=None: tmp_path / "Sparkle.framework",
    )
    monkeypatch.setattr(
        module,
        "write_unsigned_macos_app_bundle",
        lambda **kwargs: {
            "app_path": str(tmp_path / "Melix.app"),
            "timings": {"write_total_seconds": 0.1},
        },
    )
    monkeypatch.setattr(module, "sign_macos_app_bundle", lambda app_path, **kwargs: False)
    monkeypatch.setattr(
        module,
        "archive_macos_app_bundle",
        lambda app_path, requested_archive_path: pytest.fail(
            "archive creation must not run after signing or deep verification fails"
        ),
    )
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

    with pytest.raises(RuntimeError, match="Code signing or signature verification failed"):
        module.main()

    assert archive_path.exists() is False


def test_main_propagates_extracted_archive_verification_failure_before_success_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"

    monkeypatch.setattr(module, "resolve_built_binary", lambda repo_root: tmp_path / "melix-menubar")
    monkeypatch.setattr(module, "resolve_built_cli_binary", lambda repo_root: tmp_path / "melix")
    monkeypatch.setattr(
        module,
        "resolve_built_control_plane_binary",
        lambda repo_root: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "resolve_swift_mlx_metallib",
        lambda repo_root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda repo_root, configured_path=None: tmp_path / "Sparkle.framework",
    )
    monkeypatch.setattr(
        module,
        "write_unsigned_macos_app_bundle",
        lambda **kwargs: {
            "app_path": str(tmp_path / "Melix.app"),
            "timings": {"write_total_seconds": 0.1},
        },
    )
    monkeypatch.setattr(module, "sign_macos_app_bundle", lambda app_path, **kwargs: True)

    def fake_archive_macos_app_bundle(app_path: str, requested_archive_path: str) -> Path:
        archive_path.write_bytes(b"zip")
        return archive_path

    monkeypatch.setattr(module, "archive_macos_app_bundle", fake_archive_macos_app_bundle)
    monkeypatch.setattr(
        module,
        "verify_archived_macos_app_bundle",
        lambda requested_archive_path, expected_app_name, **kwargs: (_ for _ in ()).throw(
            RuntimeError("Archived macOS app deep signature verification failed")
        ),
    )
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

    with pytest.raises(RuntimeError, match="deep signature verification failed"):
        module.main()

    assert capsys.readouterr().out == ""


def _write_extracted_archive_fixture(
    extraction_root: Path,
    *,
    expected_app_name: str,
    absolute_metallib_link: bool = False,
) -> Path:
    app_path = extraction_root / expected_app_name
    resources_path = app_path / "Contents/Resources"
    bundled_metallib = resources_path / "swift-mlx/mlx.metallib"
    bundled_metallib.parent.mkdir(parents=True)
    bundled_metallib.write_bytes(b"matching-swift-mlx-metallib")
    metallib_link = resources_path / "mlx.metallib"
    metallib_link.symlink_to(
        bundled_metallib.resolve()
        if absolute_metallib_link
        else Path("swift-mlx/mlx.metallib")
    )
    return app_path


def test_verify_archived_macos_app_bundle_requires_relative_metallib_link_and_strict_signature(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    calls: list[list[str]] = []

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/codesign")

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        calls.append(command)
        if command[0] == "/usr/bin/ditto":
            _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.verify_archived_macos_app_bundle(
        archive_path,
        expected_app_name="Melix.app",
    )

    assert calls[0][:4] == ["/usr/bin/ditto", "-x", "-k", str(archive_path.resolve())]
    assert calls[-1] == [
        "/usr/bin/codesign",
        "--verify",
        "--strict",
        "--verbose=4",
        str((Path(calls[0][-1]) / "Melix.app").resolve()),
    ]


def test_verify_archived_macos_app_bundle_requires_complete_sparkle_linkage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    calls: list[list[str]] = []

    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command: list[str], check: bool, **kwargs: object):
        calls.append(command)
        if command[0] == "/usr/bin/ditto":
            app_path = _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )
            framework = app_path / "Contents/Frameworks/Sparkle.framework/Versions/B"
            (framework / "XPCServices/Downloader.xpc").mkdir(parents=True)
            (framework / "XPCServices/Installer.xpc").mkdir()
            (framework / "Updater.app").mkdir()
            (framework / "Autoupdate").write_bytes(b"autoupdate")
            (framework / "Sparkle").write_bytes(b"framework")
            return None
        if command[:2] == ["/usr/bin/otool", "-L"]:
            return SimpleNamespace(
                stdout="@rpath/Sparkle.framework/Versions/B/Sparkle\n"
            )
        if command[:2] == ["/usr/bin/otool", "-l"]:
            return SimpleNamespace(stdout="path @loader_path/../Frameworks\n")
        return None

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module.verify_archived_macos_app_bundle(
        archive_path,
        expected_app_name="Melix.app",
        require_sparkle_framework=True,
    )

    assert any(command[:2] == ["/usr/bin/otool", "-L"] for command in calls)
    assert any(command[:2] == ["/usr/bin/otool", "-l"] for command in calls)
    assert calls[-1][0] == "/usr/bin/codesign"


def test_verify_archived_macos_app_bundle_verifies_stable_designated_requirement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    certificate_sha1 = "0123456789abcdef0123456789abcdef01234567"
    calls: list[list[str]] = []
    verified_targets: list[Path] = []
    entitlement_targets: list[Path] = []
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command: list[str], check: bool, **kwargs: object):
        calls.append(command)
        if command[0] == "/usr/bin/ditto":
            app_path = _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )
            _write_complete_sparkle_framework(
                app_path / "Contents/Frameworks/Sparkle.framework"
            )
            return SimpleNamespace(stdout="", stderr="")
        if command[:2] == ["/usr/bin/otool", "-L"]:
            return SimpleNamespace(
                stdout="@rpath/Sparkle.framework/Versions/B/Sparkle\n",
                stderr="",
            )
        if command[:2] == ["/usr/bin/otool", "-l"]:
            return SimpleNamespace(
                stdout="path @loader_path/../Frameworks\n",
                stderr="",
            )
        if command[1:3] == ["--display", "--verbose=4"]:
            return SimpleNamespace(
                stdout="",
                stderr="Authority=Melix GitHub Release Signing\n",
            )
        if command[1:3] == ["-d", "-r-"]:
            return SimpleNamespace(
                stdout="",
                stderr=f'designated => certificate root = H"{certificate_sha1}"\n',
            )
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_verify_codesign_identity_evidence",
        lambda codesign, target, **kwargs: verified_targets.append(target),
    )
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_canonical_codesign_entitlements",
        lambda codesign, target: entitlement_targets.append(target) or b"entitlements",
    )

    module.verify_archived_macos_app_bundle(
        archive_path,
        expected_app_name="Melix.app",
        require_sparkle_framework=True,
        expected_signing_certificate_sha256="a" * 64,
        expected_signing_certificate_sha1=certificate_sha1.upper(),
        expected_signing_authority="Melix GitHub Release Signing",
    )

    assert verified_targets
    assert verified_targets[-1].name == "Melix.app"
    assert [target.name for target in entitlement_targets] == [
        "Downloader.xpc",
    ]


@pytest.mark.parametrize(
    ("authority", "requirement", "message"),
    [
        (
            "Different Signing Authority",
            'certificate root = H"0123456789abcdef0123456789abcdef01234567"',
            "signature verification failed",
        ),
        (
            "Melix GitHub Release Signing",
            "identifier io.melix.menubar",
            "signature verification failed",
        ),
    ],
)
def test_verify_archived_macos_app_bundle_rejects_unstable_designated_requirement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    authority: str,
    requirement: str,
    message: str,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    certificate_sha1 = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command: list[str], check: bool, **kwargs: object):
        if command[0] == "/usr/bin/ditto":
            _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )
            return SimpleNamespace(stdout="", stderr="")
        if command[1:3] == ["--display", "--verbose=4"]:
            return SimpleNamespace(stdout="", stderr=f"Authority={authority}\n")
        if command[1:3] == ["-d", "-r-"]:
            return SimpleNamespace(stdout="", stderr=requirement)
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        macos_app_bundle_module,
        "_verify_codesign_identity_evidence",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("identity mismatch")),
    )

    with pytest.raises(RuntimeError, match=message):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
            expected_signing_certificate_sha256="a" * 64,
            expected_signing_certificate_sha1=certificate_sha1,
            expected_signing_authority="Melix GitHub Release Signing",
        )


def test_verify_archived_macos_app_bundle_requires_complete_signing_expectations(
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")

    with pytest.raises(ValueError, match="must be provided together"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
            expected_signing_certificate_sha1="0" * 40,
        )


def test_verify_archived_macos_app_bundle_rejects_incomplete_sparkle_framework(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        if command[0] == "/usr/bin/ditto":
            _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Archived Sparkle framework is incomplete"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
            require_sparkle_framework=True,
        )


@pytest.mark.parametrize(
    ("otool_available", "linked_libraries", "load_commands", "message"),
    [
        (False, "", "", "otool is required"),
        (True, "", "path @loader_path/../Frameworks", "not linked to Sparkle"),
        (
            True,
            "@rpath/Sparkle.framework/Versions/B/Sparkle",
            "",
            "cannot resolve Contents/Frameworks",
        ),
    ],
)
def test_verify_archived_macos_app_bundle_rejects_invalid_sparkle_linkage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    otool_available: bool,
    linked_libraries: str,
    load_commands: str,
    message: str,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")

    def fake_which(name: str) -> str | None:
        if name == "otool" and not otool_available:
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(module.shutil, "which", fake_which)

    def fake_run(command: list[str], check: bool, **kwargs: object):
        if command[0] == "/usr/bin/ditto":
            app_path = _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )
            _write_complete_sparkle_framework(
                app_path / "Contents/Frameworks/Sparkle.framework"
            )
            return None
        if command[:2] == ["/usr/bin/otool", "-L"]:
            return SimpleNamespace(stdout=linked_libraries)
        if command[:2] == ["/usr/bin/otool", "-l"]:
            return SimpleNamespace(stdout=load_commands)
        return None

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=message):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
            require_sparkle_framework=True,
        )


def test_verify_archived_macos_app_bundle_rejects_absolute_metallib_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/codesign")

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        if command[0] == "/usr/bin/ditto":
            _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
                absolute_metallib_link=True,
            )
            return
        pytest.fail("deep signature verification must not run for an invalid metallib link")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="must be relative"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
        )


def test_verify_archived_macos_app_bundle_propagates_strict_signature_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/codesign")

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        if command[0] == "/usr/bin/ditto":
            _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )
            return
        raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="signature verification failed"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
        )


def test_verify_archived_macos_app_bundle_rejects_missing_hardened_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        module.macos_app_bundle_module,
        "_codesign_details",
        lambda codesign, target: "flags=none",
    )

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        if command[0] == "/usr/bin/ditto":
            _write_extracted_archive_fixture(
                Path(command[-1]),
                expected_app_name="Melix.app",
            )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="signature verification failed"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
        )


def test_verify_archived_macos_app_bundle_requires_archive_and_codesign(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    missing_archive = tmp_path / "missing.zip"

    with pytest.raises(FileNotFoundError, match="archive is missing"):
        module.verify_archived_macos_app_bundle(
            missing_archive,
            expected_app_name="Melix.app",
        )

    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(module.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="codesign is required"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
        )


@pytest.mark.parametrize("expected_app_name", ("Melix", "../Melix.app"))
def test_verify_archived_macos_app_bundle_rejects_invalid_expected_app_name(
    tmp_path: Path,
    expected_app_name: str,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")

    with pytest.raises(ValueError, match="single .app name"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name=expected_app_name,
        )


def test_verify_archived_macos_app_bundle_propagates_extraction_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/codesign")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, check, **kwargs: (_ for _ in ()).throw(
            module.subprocess.CalledProcessError(returncode=1, cmd=command)
        ),
    )

    with pytest.raises(RuntimeError, match="archive extraction failed"):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
        )


@pytest.mark.parametrize(
    ("archive_fixture", "message"),
    (
        ("missing-app", "bundle is missing after extraction"),
        ("plain-metallib", "must remain a symbolic link"),
        ("unexpected-target", "link target is unexpected"),
        ("missing-target", "link target is missing"),
    ),
)
def test_verify_archived_macos_app_bundle_rejects_invalid_extracted_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    archive_fixture: str,
    message: str,
) -> None:
    module = load_package_macos_app_module()
    archive_path = tmp_path / "Melix.zip"
    archive_path.write_bytes(b"zip")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/codesign")

    def fake_run(command: list[str], check: bool, **kwargs: object) -> None:
        if command[0] != "/usr/bin/ditto":
            pytest.fail("deep signature verification must not run for an invalid archive layout")
        if archive_fixture == "missing-app":
            return

        resources_path = Path(command[-1]) / "Melix.app/Contents/Resources"
        resources_path.mkdir(parents=True)
        metallib_link = resources_path / "mlx.metallib"
        if archive_fixture == "plain-metallib":
            metallib_link.write_bytes(b"not-a-link")
        elif archive_fixture == "unexpected-target":
            metallib_link.symlink_to(Path("other/mlx.metallib"))
        else:
            metallib_link.symlink_to(Path("swift-mlx/mlx.metallib"))

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=message):
        module.verify_archived_macos_app_bundle(
            archive_path,
            expected_app_name="Melix.app",
        )


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
        "resolve_built_control_plane_binary",
        lambda repo_root: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        module,
        "resolve_built_swift_text_worker_binary",
        lambda repo_root: tmp_path / "melix-text-worker-swift",
    )
    monkeypatch.setattr(module, "resolve_python_runtime_root", lambda executable: tmp_path / "python-runtime")
    monkeypatch.setattr(module, "resolve_site_packages_root", lambda repo_root: tmp_path / "site-packages")
    monkeypatch.setattr(
        module,
        "resolve_swift_mlx_metallib",
        lambda repo_root, configured_path=None: (tmp_path / "mlx.metallib", "0.31.1"),
    )
    monkeypatch.setattr(
        module,
        "resolve_sparkle_framework",
        lambda repo_root, configured_path=None: tmp_path / "Sparkle.framework",
    )
    monkeypatch.setattr(
        module,
        "write_unsigned_macos_app_bundle",
        lambda **kwargs: {"app_path": str(tmp_path / "Melix.app"), "timings": {}},
    )
    monkeypatch.setattr(module, "sign_macos_app_bundle", lambda app_path, **kwargs: True)
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
