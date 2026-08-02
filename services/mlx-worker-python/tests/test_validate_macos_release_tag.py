from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "validate_macos_release_tag.py"


def load_module():
    spec = importlib.util.spec_from_file_location("melix_validate_release_tag", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def commit(repo: Path, message: str, payload: str) -> str:
    tracked = repo / "tracked.txt"
    tracked.write_text(payload, encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Melix Test")
    git(repo, "config", "user.email", "melix-test@example.invalid")
    git(repo, "config", "commit.gpgSign", "false")
    git(repo, "config", "tag.gpgSign", "false")
    previous_sha = commit(repo, "previous", "previous\n")
    git(repo, "tag", "-a", "v1.2.3", "-m", "v1.2.3", previous_sha)
    release_sha = commit(repo, "release", "release\n")
    git(repo, "tag", "-a", "v1.3.0", "-m", "v1.3.0", release_sha)
    git(repo, "update-ref", "refs/remotes/origin/main", release_sha)
    return repo, previous_sha, release_sha


@pytest.mark.parametrize(
    "tag",
    [
        "v1.2",
        "v1.2.3.4",
        "1.2.3",
        "v01.2.3",
        "v1.02.3",
        "v1.2.03",
        "v1.2.3-alpha",
        "v1.2.3+build",
        "v-1.2.3",
    ],
)
def test_stable_release_tag_rejects_noncanonical_or_prerelease_versions(tag: str) -> None:
    module = load_module()

    with pytest.raises(ValueError, match="vMAJOR.MINOR.PATCH"):
        module.StableReleaseVersion.parse_tag(tag)


def test_stable_release_version_uses_monotonic_numeric_order() -> None:
    module = load_module()

    assert module.StableReleaseVersion.parse_tag("v1.10.0") > module.StableReleaseVersion.parse_tag(
        "v1.9.99"
    )
    assert module.StableReleaseVersion.parse_tag("v2.0.0").display_version == "2.0.0"
    assert module.StableReleaseVersion.parse_tag("v2.0.0").tag_name == "v2.0.0"


def test_validate_release_tag_accepts_annotated_tag_from_origin_main(
    tmp_path: Path,
) -> None:
    module = load_module()
    repo, _, release_sha = release_repo(tmp_path)

    receipt = module.validate_release_tag(
        repo_root=repo,
        tag_name="v1.3.0",
        expected_source_sha=release_sha,
    )

    assert receipt.tag_name == "v1.3.0"
    assert receipt.version == "1.3.0"
    assert receipt.source_sha == release_sha
    assert receipt.main_ref == "refs/remotes/origin/main"
    assert receipt.previous_stable_tag == "v1.2.3"
    assert receipt.previous_stable_version == "1.2.3"


def test_validate_release_tag_rejects_tag_commit_outside_origin_main(
    tmp_path: Path,
) -> None:
    module = load_module()
    repo, _, release_sha = release_repo(tmp_path)
    git(repo, "switch", "--detach", "v1.2.3^{commit}")
    off_main_sha = commit(repo, "off-main", "off-main\n")
    git(repo, "tag", "-a", "v1.4.0", "-m", "v1.4.0", off_main_sha)

    with pytest.raises(ValueError, match="origin/main"):
        module.validate_release_tag(
            repo_root=repo,
            tag_name="v1.4.0",
            expected_source_sha=off_main_sha,
        )

    assert git(repo, "rev-parse", "refs/remotes/origin/main") == release_sha


@pytest.mark.parametrize("tag", ["v1.2.3", "v1.2.2", "v0.99.99"])
def test_validate_release_tag_rejects_equal_or_downgrade_versions(
    tmp_path: Path,
    tag: str,
) -> None:
    module = load_module()
    repo, _, release_sha = release_repo(tmp_path)
    if tag not in {"v1.2.3"}:
        git(repo, "tag", "-a", tag, "-m", tag, release_sha)

    with pytest.raises(ValueError, match="strictly greater"):
        module.validate_release_tag(
            repo_root=repo,
            tag_name=tag,
            expected_source_sha=git(repo, "rev-parse", f"{tag}^{{commit}}"),
        )


def test_validate_release_tag_rejects_source_sha_mismatch(tmp_path: Path) -> None:
    module = load_module()
    repo, previous_sha, _ = release_repo(tmp_path)

    with pytest.raises(ValueError, match="source SHA"):
        module.validate_release_tag(
            repo_root=repo,
            tag_name="v1.3.0",
            expected_source_sha=previous_sha,
        )


def test_validator_rejects_missing_repo_invalid_sha_and_git_failure(tmp_path: Path) -> None:
    module = load_module()

    with pytest.raises(ValueError, match="does not exist"):
        module.validate_release_tag(
            repo_root=tmp_path / "missing",
            tag_name="v1.0.0",
            expected_source_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="40-character"):
        module._normalize_source_sha("short")
    with pytest.raises(ValueError, match="git rev-parse HEAD failed"):
        module._run_git(tmp_path, "rev-parse", "HEAD")


def test_validator_ignores_nonstable_tags_and_surfaces_git_ancestry_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    repo, _, release_sha = release_repo(tmp_path)
    git(repo, "tag", "not-a-release")
    assert module.validate_release_tag(
        repo_root=repo,
        tag_name="v1.3.0",
        expected_source_sha=release_sha,
    ).previous_stable_tag == "v1.2.3"

    real_run = module.subprocess.run

    def fail_ancestry(command, **kwargs):
        if command[:2] == ["git", "merge-base"]:
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="broken graph")
        return real_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", fail_ancestry)
    with pytest.raises(ValueError, match="broken graph"):
        module.validate_release_tag(
            repo_root=repo,
            tag_name="v1.3.0",
            expected_source_sha=release_sha,
        )


def test_validator_main_writes_receipt_and_github_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module()
    repo, _, release_sha = release_repo(tmp_path)
    receipt_path = tmp_path / "nested/receipt.json"
    output_path = tmp_path / "github-output.txt"

    assert module.main(
        [
            "--repo-root",
            str(repo),
            "--tag",
            "v1.3.0",
            "--source-sha",
            release_sha.upper(),
            "--output",
            str(receipt_path),
            "--github-output",
            str(output_path),
        ]
    ) == 0

    assert json.loads(receipt_path.read_text(encoding="utf-8"))["source_sha"] == release_sha
    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "tag_name=v1.3.0",
        "version=1.3.0",
        f"source_sha={release_sha}",
    ]
    module._write_json({"ok": True}, None)
    assert json.loads(capsys.readouterr().out) == {"ok": True}
