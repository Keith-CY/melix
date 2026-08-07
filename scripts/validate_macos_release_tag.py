#!/usr/bin/env python3
"""Validate that a macOS release tag is a monotonic stable release from main."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


_STABLE_TAG_PATTERN = re.compile(
    r"^v(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)$"
)
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_MAIN_REF = "refs/remotes/origin/main"


@dataclass(frozen=True, order=True)
class StableReleaseVersion:
    """A canonical stable SemVer tuple used for numeric ordering."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse_tag(cls, tag_name: str) -> StableReleaseVersion:
        match = _STABLE_TAG_PATTERN.fullmatch(tag_name)
        if match is None:
            raise ValueError(
                "stable release tags must use canonical vMAJOR.MINOR.PATCH format"
            )
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
        )

    @property
    def display_version(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag_name(self) -> str:
        return f"v{self.display_version}"


@dataclass(frozen=True)
class ReleaseTagReceipt:
    schema_version: int
    tag_name: str
    version: str
    source_sha: str
    main_ref: str
    previous_stable_tag: str | None
    previous_stable_version: str | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _run_git(repo_root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _normalize_source_sha(source_sha: str) -> str:
    normalized = source_sha.strip().lower()
    if _FULL_SHA_PATTERN.fullmatch(normalized) is None:
        raise ValueError("expected source SHA must be a full 40-character Git commit SHA")
    return normalized


def _stable_tags(repo_root: Path) -> list[tuple[StableReleaseVersion, str]]:
    result: list[tuple[StableReleaseVersion, str]] = []
    for tag_name in _run_git(repo_root, "tag", "--list").splitlines():
        try:
            version = StableReleaseVersion.parse_tag(tag_name)
        except ValueError:
            continue
        result.append((version, tag_name))
    return sorted(result)


def validate_release_tag(
    *,
    repo_root: Path,
    tag_name: str,
    expected_source_sha: str,
) -> ReleaseTagReceipt:
    """Validate the tag before a protected job is allowed to consume secrets."""

    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise ValueError(f"repository root does not exist: {repo_root}")

    version = StableReleaseVersion.parse_tag(tag_name)
    source_sha = _normalize_source_sha(expected_source_sha)
    tag_commit = _run_git(repo_root, "rev-parse", f"refs/tags/{tag_name}^{{commit}}").lower()
    if tag_commit != source_sha:
        raise ValueError(
            f"tag source SHA mismatch: {tag_name} resolves to {tag_commit}, expected {source_sha}"
        )

    _run_git(repo_root, "rev-parse", "--verify", f"{_MAIN_REF}^{{commit}}")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", tag_commit, _MAIN_REF],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestry.returncode == 1:
        raise ValueError(f"release tag {tag_name} is not reachable from origin/main")
    if ancestry.returncode != 0:
        detail = ancestry.stderr.strip() or ancestry.stdout.strip()
        raise ValueError(f"could not verify origin/main ancestry: {detail}")

    previous_versions = [
        (stable_version, stable_tag)
        for stable_version, stable_tag in _stable_tags(repo_root)
        if stable_tag != tag_name
    ]
    previous_version: StableReleaseVersion | None = None
    previous_tag: str | None = None
    if previous_versions:
        previous_version, previous_tag = max(previous_versions)
        if version <= previous_version:
            raise ValueError(
                f"release version {version.display_version} must be strictly greater than "
                f"existing stable version {previous_version.display_version}"
            )

    return ReleaseTagReceipt(
        schema_version=1,
        tag_name=tag_name,
        version=version.display_version,
        source_sha=tag_commit,
        main_ref=_MAIN_REF,
        previous_stable_tag=previous_tag,
        previous_stable_version=(
            previous_version.display_version if previous_version is not None else None
        ),
    )


def _write_json(payload: dict[str, object], path: Path | None) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(content, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _append_github_output(path: Path, receipt: ReleaseTagReceipt) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"tag_name={receipt.tag_name}\n")
        handle.write(f"version={receipt.version}\n")
        handle.write(f"source_sha={receipt.source_sha}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    arguments = parser.parse_args(argv)

    receipt = validate_release_tag(
        repo_root=arguments.repo_root,
        tag_name=arguments.tag,
        expected_source_sha=arguments.source_sha,
    )
    _write_json(receipt.as_dict(), arguments.output)
    if arguments.github_output is not None:
        _append_github_output(arguments.github_output, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
