from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildMetadata:
    version: str
    artifact_name: str


def infer_git_ref_name(repo_root: str | Path) -> str:
    root = Path(repo_root).expanduser().resolve()
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "detached"


def infer_git_sha(repo_root: str | Path) -> str:
    root = Path(repo_root).expanduser().resolve()
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def compute_build_metadata(
    *,
    ref_type: str,
    ref_name: str,
    sha: str,
    base_version: str = "0.1.0",
) -> BuildMetadata:
    short_sha = sha[:7]
    if ref_type == "tag":
        normalized = ref_name[1:] if ref_name.startswith("v") else ref_name
        return BuildMetadata(
            version=normalized,
            artifact_name=f"Melix-{sanitize_ref_name(normalized)}",
        )

    branch = sanitize_ref_name(ref_name or "detached")
    return BuildMetadata(
        version=f"{base_version}+{short_sha}",
        artifact_name=f"Melix-{branch}-{short_sha}",
    )


def sanitize_ref_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "detached"
