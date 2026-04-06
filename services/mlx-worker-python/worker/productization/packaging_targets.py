from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PackagingTargetProfile:
    target_id: str
    packaging_kind: str
    distribution_channel: str
    runtime_layout: str
    artifact_format: str
    optimization_intent: str
    state_contract: str
    update_strategy: str
    logical_product_identity: str = "io.melix"
    logical_product_name: str = "Melix"
    platform: str = "macos"
    hardware_family: str = "apple_silicon"
    acceleration_stack: str = "mlx_coreml_local"
    runtime_semantics: str = "shared_control_plane_truth"


_TARGETS: dict[str, PackagingTargetProfile] = {
    "launch_agents_checkout": PackagingTargetProfile(
        target_id="launch_agents_checkout",
        packaging_kind="launch_agents",
        distribution_channel="local_checkout",
        runtime_layout="repo_checkout",
        artifact_format="launchd_user_agents",
        optimization_intent="developer_install_and_same_host_service_reuse",
        state_contract="install_manifest_v1",
        update_strategy="repository_update_channel",
    ),
    "homebrew_service": PackagingTargetProfile(
        target_id="homebrew_service",
        packaging_kind="homebrew",
        distribution_channel="homebrew_formula",
        runtime_layout="repo_checkout_with_installed_binaries",
        artifact_format="brew_services_supervisor",
        optimization_intent="managed_local_service_bundle",
        state_contract="service_manifest_v1",
        update_strategy="brew_upgrade_plus_repository_update_channel_metadata",
    ),
    "macos_app_bundle_preview": PackagingTargetProfile(
        target_id="macos_app_bundle_preview",
        packaging_kind="app_bundle",
        distribution_channel="archive_or_drag_install",
        runtime_layout="self_contained_bundle",
        artifact_format="unsigned_macos_app_bundle",
        optimization_intent="portable_preview_bundle",
        state_contract="embedded_target_manifest_v1",
        update_strategy="manual_bundle_refresh_with_embedded_update_metadata",
    ),
}


def list_packaging_target_profiles() -> list[PackagingTargetProfile]:
    return [*_TARGETS.values()]


def get_packaging_target_profile(target_id: str) -> PackagingTargetProfile:
    try:
        return _TARGETS[target_id]
    except KeyError as error:
        supported = ", ".join(sorted(_TARGETS))
        raise ValueError(
            f"Unsupported Melix packaging target {target_id!r}. Supported targets: {supported}"
        ) from error


def build_packaging_target_metadata(
    target_id: str,
    *,
    product_version: str,
    update_channel_path: str | Path,
    service_instance_name: str = "",
    bundle_id: str = "",
) -> dict[str, Any]:
    profile = get_packaging_target_profile(target_id)
    payload: dict[str, Any] = asdict(profile)
    payload["packaging_target_id"] = payload.pop("target_id")
    payload["product_version"] = product_version
    payload["update_channel_path"] = str(Path(update_channel_path).expanduser().resolve())
    payload["service_instance_name"] = service_instance_name
    if bundle_id:
        payload["bundle_id"] = bundle_id
    return payload
