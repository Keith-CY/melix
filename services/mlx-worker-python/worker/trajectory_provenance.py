from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


TRAJECTORY_PROVENANCE_FIELDS = (
    "trajectory_dataset_id",
    "trajectory_dataset_version",
    "trajectory_schema_version",
    "trajectory_snapshot_manifest_path",
    "trajectory_split",
    "trajectory_trace_digest",
    "trajectory_toolset_version",
    "trajectory_registry_schema_version",
    "trajectory_reward_policy_id",
    "trajectory_leakage_policy_id",
    "trajectory_package_path",
    "trajectory_quality_metrics",
)

TRAJECTORY_PROVENANCE_CSV_FIELDS = (
    "trajectory_dataset_id",
    "trajectory_dataset_version",
    "trajectory_schema_version",
    "trajectory_snapshot_manifest_path",
    "trajectory_split",
    "trajectory_trace_digest",
    "trajectory_toolset_version",
    "trajectory_registry_schema_version",
    "trajectory_reward_policy_id",
    "trajectory_leakage_policy_id",
    "trajectory_package_path",
    "trajectory_quality_metrics",
)


def normalize_trajectory_provenance(
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not provenance:
        return {}
    normalized: dict[str, Any] = {}
    for field in TRAJECTORY_PROVENANCE_FIELDS:
        value = provenance.get(field)
        if value in ("", None):
            continue
        if isinstance(value, (dict, list)):
            normalized[field] = copy.deepcopy(value)
        else:
            normalized[field] = value
    return normalized


def append_trajectory_provenance(
    payload: dict[str, Any],
    provenance: Mapping[str, Any] | None,
) -> None:
    if not provenance:
        return
    normalized = normalize_trajectory_provenance(provenance)
    if normalized:
        payload.update(normalized)


def trajectory_provenance_from_snapshot_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    if (
        str(manifest.get("format", "")).strip() != "agentic_tool_trace"
        and not str(manifest.get("trajectory_trace_digest", "")).strip()
    ):
        return {}

    provenance: dict[str, Any] = {
        "trajectory_dataset_id": str(
            manifest.get("source_dataset_id") or manifest.get("dataset_id") or ""
        ).strip(),
        "trajectory_dataset_version": str(manifest.get("version") or "").strip(),
        "trajectory_schema_version": str(
            manifest.get("trajectory_schema_version") or "melix.agentic_tool_trace.v1"
        ).strip(),
        "trajectory_split": str(manifest.get("trajectory_split") or "train").strip(),
        "trajectory_trace_digest": str(manifest.get("trajectory_trace_digest") or "").strip(),
    }
    if snapshot_manifest_path is not None:
        provenance["trajectory_snapshot_manifest_path"] = str(snapshot_manifest_path)
    for source_field, output_field in (
        ("trajectory_toolset_version", "trajectory_toolset_version"),
        ("trajectory_registry_schema_version", "trajectory_registry_schema_version"),
        ("trajectory_reward_policy_id", "trajectory_reward_policy_id"),
        ("trajectory_leakage_policy_id", "trajectory_leakage_policy_id"),
        ("source_package_path", "trajectory_package_path"),
        ("trajectory_quality_metrics", "trajectory_quality_metrics"),
    ):
        value = manifest.get(source_field)
        if value in ("", None):
            continue
        provenance[output_field] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
    return normalize_trajectory_provenance(provenance)


def load_trajectory_provenance_from_snapshot_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return trajectory_provenance_from_snapshot_manifest(
        payload,
        snapshot_manifest_path=manifest_path,
    )


def load_trajectory_provenance_from_normalized_snapshot(
    *,
    format_name: str,
    manifest_path: Path,
) -> dict[str, Any]:
    if format_name != "agentic_tool_trace":
        return {}
    return load_trajectory_provenance_from_snapshot_manifest(manifest_path)


def load_trajectory_provenance_from_snapshot_dir(
    snapshot_dir: Path,
) -> dict[str, Any]:
    manifest_path = Path(snapshot_dir) / "manifest.json"
    if not manifest_path.is_file():
        return {}
    return load_trajectory_provenance_from_snapshot_manifest(manifest_path)


def adapter_manifest_trajectory_provenance(
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalize_trajectory_provenance(provenance)
    if not normalized:
        return {}
    payload = dict(normalized)
    payload["trajectory_provenance_field_count"] = len(normalized)
    payload["trajectory_reward_policy_present"] = bool(
        normalized.get("trajectory_reward_policy_id")
    )
    return payload


def alignment_metrics_trajectory_provenance(
    provenance: Mapping[str, Any] | None,
) -> dict[str, int]:
    normalized = normalize_trajectory_provenance(provenance)
    if not normalized:
        return {}
    metrics = {
        "trajectory_provenance_field_count": len(normalized),
        "trajectory_reward_policy_present": int(
            bool(normalized.get("trajectory_reward_policy_id"))
        ),
    }
    quality_metrics = normalized.get("trajectory_quality_metrics")
    if isinstance(quality_metrics, Mapping):
        metrics["trajectory_reward_component_coverage"] = int(
            quality_metrics.get("reward_coverage_count", 0) or 0
        )
    return metrics
