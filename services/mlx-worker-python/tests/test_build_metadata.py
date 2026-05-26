from __future__ import annotations

from worker.productization.build_metadata import compute_build_metadata, sanitize_ref_name


def test_compute_build_metadata_uses_release_tag_version() -> None:
    metadata = compute_build_metadata(
        ref_type="tag",
        ref_name="v1.2.3",
        sha="abcdef1234567890",
    )

    assert metadata.version == "1.2.3"
    assert metadata.artifact_name == "Melix-1.2.3"


def test_compute_build_metadata_uses_branch_and_commit_for_non_release() -> None:
    metadata = compute_build_metadata(
        ref_type="branch",
        ref_name="develop",
        sha="abcdef1234567890",
    )

    assert metadata.version == "0.1.0+abcdef1"
    assert metadata.artifact_name == "Melix-develop-abcdef1"


def test_sanitize_ref_name_normalizes_slashes_and_spaces() -> None:
    assert sanitize_ref_name("feature/self contained app") == "feature-self-contained-app"
