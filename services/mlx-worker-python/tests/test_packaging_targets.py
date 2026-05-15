from __future__ import annotations

from pathlib import Path

import pytest

from worker.productization.packaging_targets import (
    build_packaging_target_metadata,
    get_packaging_target_profile,
    list_packaging_target_profiles,
    resolve_local_connect_host,
)


def test_list_packaging_target_profiles_share_one_logical_identity() -> None:
    profiles = list_packaging_target_profiles()

    assert [profile.target_id for profile in profiles] == [
        "launch_agents_checkout",
        "homebrew_service",
        "macos_app_bundle_preview",
    ]
    assert {profile.logical_product_identity for profile in profiles} == {"io.melix"}
    assert {profile.hardware_family for profile in profiles} == {"apple_silicon"}


def test_build_packaging_target_metadata_projects_explicit_target_fields(tmp_path: Path) -> None:
    metadata = build_packaging_target_metadata(
        "macos_app_bundle_preview",
        product_version="0.8.11",
        update_channel_path=tmp_path / "stable.json",
        bundle_id="io.melix.preview",
    )

    assert metadata["packaging_target_id"] == "macos_app_bundle_preview"
    assert metadata["packaging_kind"] == "app_bundle"
    assert metadata["distribution_channel"] == "archive_or_drag_install"
    assert metadata["logical_product_identity"] == "io.melix"
    assert metadata["product_version"] == "0.8.11"
    assert metadata["update_channel_path"] == str((tmp_path / "stable.json").resolve())
    assert metadata["bundle_id"] == "io.melix.preview"


def test_get_packaging_target_profile_rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="Unsupported Melix packaging target"):
        get_packaging_target_profile("linux_pkg")


def test_resolve_local_connect_host_projects_bind_all_to_loopback() -> None:
    assert resolve_local_connect_host("0.0.0.0") == "127.0.0.1"
    assert resolve_local_connect_host("::") == "127.0.0.1"
    assert resolve_local_connect_host(" 192.168.1.20 ") == "192.168.1.20"


def test_worker_productization_exports_packaging_target_helpers() -> None:
    import worker.productization as productization

    assert productization.PackagingTargetProfile.__name__ == "PackagingTargetProfile"
    assert productization.list_packaging_target_profiles()[0].target_id == "launch_agents_checkout"
    assert productization.resolve_local_connect_host("0.0.0.0") == "127.0.0.1"
