from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_JSON_LOADS = json.loads
_PATH_READ_BYTES = Path.read_bytes
_STR = str


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
    "agentic_sft_token_metrics",
)

TRAJECTORY_PROVENANCE_CSV_FIELDS = TRAJECTORY_PROVENANCE_FIELDS

_JSON_IMMUTABLE_TYPES = (str, int, float, bool, type(None))
_JSON_IMMUTABLE_TYPE_SET = frozenset(_JSON_IMMUTABLE_TYPES)
def _copy_trajectory_provenance_value(value: Any) -> Any:
    value_type = type(value)
    if value_type in _JSON_IMMUTABLE_TYPE_SET:
        return value
    if value_type is dict:
        return {key: _copy_trajectory_provenance_value(item) for key, item in value.items()}
    if value_type is list:
        return [_copy_trajectory_provenance_value(item) for item in value]
    if value_type is tuple:
        return tuple(_copy_trajectory_provenance_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _copy_trajectory_provenance_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_trajectory_provenance_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_trajectory_provenance_value(item) for item in value)
    if isinstance(value, _JSON_IMMUTABLE_TYPES):
        return value
    return copy.deepcopy(value)


def normalize_trajectory_provenance(
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not provenance:
        return {}
    normalized: dict[str, Any] = {}
    provenance_get = provenance.get
    copy_value = _copy_trajectory_provenance_value
    for field in TRAJECTORY_PROVENANCE_FIELDS:
        value = provenance_get(field)
        if value is None:
            continue
        value_type = type(value)
        if value_type is str:
            if value == "":
                continue
            normalized[field] = value
        elif value_type is dict or value_type is list:
            normalized[field] = copy_value(value)
        elif isinstance(value, (dict, list)):
            normalized[field] = copy_value(value)
        elif value == "":
            continue
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
    return _trajectory_provenance_from_snapshot_manifest(
        manifest,
        snapshot_manifest_path=snapshot_manifest_path,
        copy_nested=True,
    )


def _trajectory_provenance_from_snapshot_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_manifest_path: Path | str | None = None,
    copy_nested: bool,
) -> dict[str, Any]:
    manifest_get = manifest.get
    to_str = _STR
    format_value = manifest_get("format", "")
    if format_value != "agentic_tool_trace":
        if (
            to_str(format_value).strip() != "agentic_tool_trace"
            and not to_str(manifest_get("trajectory_trace_digest", "")).strip()
        ):
            return {}

    provenance: dict[str, Any] = {}
    dataset_id_value = manifest_get("source_dataset_id") or manifest_get("dataset_id") or ""
    if type(dataset_id_value) is str:
        dataset_id = (
            dataset_id_value
            if dataset_id_value
            and dataset_id_value[0] > " "
            and dataset_id_value[-1] > " "
            else dataset_id_value.strip()
        )
    else:
        dataset_id = to_str(dataset_id_value).strip()
    if dataset_id:
        provenance["trajectory_dataset_id"] = dataset_id
    dataset_version_value = manifest_get("version") or ""
    if type(dataset_version_value) is str:
        dataset_version = (
            dataset_version_value
            if dataset_version_value
            and dataset_version_value[0] > " "
            and dataset_version_value[-1] > " "
            else dataset_version_value.strip()
        )
    else:
        dataset_version = to_str(dataset_version_value).strip()
    if dataset_version:
        provenance["trajectory_dataset_version"] = dataset_version
    schema_version_value = manifest_get("trajectory_schema_version") or "melix.agentic_tool_trace.v1"
    if type(schema_version_value) is str:
        schema_version = (
            schema_version_value
            if schema_version_value
            and schema_version_value[0] > " "
            and schema_version_value[-1] > " "
            else schema_version_value.strip()
        )
    else:
        schema_version = to_str(schema_version_value).strip()
    if schema_version:
        provenance["trajectory_schema_version"] = schema_version
    split_value = manifest_get("trajectory_split") or "train"
    if type(split_value) is str:
        split = (
            split_value
            if split_value and split_value[0] > " " and split_value[-1] > " "
            else split_value.strip()
        )
    else:
        split = to_str(split_value).strip()
    if split:
        provenance["trajectory_split"] = split
    trace_digest_value = manifest_get("trajectory_trace_digest") or ""
    if type(trace_digest_value) is str:
        trace_digest = (
            trace_digest_value
            if trace_digest_value
            and trace_digest_value[0] > " "
            and trace_digest_value[-1] > " "
            else trace_digest_value.strip()
        )
    else:
        trace_digest = to_str(trace_digest_value).strip()
    if trace_digest:
        provenance["trajectory_trace_digest"] = trace_digest
    if snapshot_manifest_path is not None:
        provenance["trajectory_snapshot_manifest_path"] = str(snapshot_manifest_path)
    trajectory_toolset_version = manifest_get("trajectory_toolset_version")
    if trajectory_toolset_version is not None and trajectory_toolset_version != "":
        provenance["trajectory_toolset_version"] = trajectory_toolset_version
    trajectory_registry_schema_version = manifest_get("trajectory_registry_schema_version")
    if (
        trajectory_registry_schema_version is not None
        and trajectory_registry_schema_version != ""
    ):
        provenance["trajectory_registry_schema_version"] = trajectory_registry_schema_version
    trajectory_reward_policy_id = manifest_get("trajectory_reward_policy_id")
    if trajectory_reward_policy_id is not None and trajectory_reward_policy_id != "":
        provenance["trajectory_reward_policy_id"] = trajectory_reward_policy_id
    trajectory_leakage_policy_id = manifest_get("trajectory_leakage_policy_id")
    if trajectory_leakage_policy_id is not None and trajectory_leakage_policy_id != "":
        provenance["trajectory_leakage_policy_id"] = trajectory_leakage_policy_id
    source_package_path = manifest_get("source_package_path")
    if source_package_path is not None and source_package_path != "":
        provenance["trajectory_package_path"] = source_package_path
    trajectory_quality_metrics = manifest_get("trajectory_quality_metrics")
    if trajectory_quality_metrics is not None and trajectory_quality_metrics != "":
        provenance["trajectory_quality_metrics"] = trajectory_quality_metrics
    agentic_sft_token_metrics = manifest_get("agentic_sft_token_metrics")
    if agentic_sft_token_metrics is not None and agentic_sft_token_metrics != "":
        provenance["agentic_sft_token_metrics"] = agentic_sft_token_metrics
    if copy_nested:
        return normalize_trajectory_provenance(provenance)
    return provenance


def load_trajectory_provenance_from_snapshot_manifest(
    manifest_path: Path | str,
) -> dict[str, Any]:
    read_bytes = _PATH_READ_BYTES
    loads = _JSON_LOADS
    extract_provenance = _trajectory_provenance_from_snapshot_manifest
    if not isinstance(manifest_path, Path):
        manifest_path = Path(manifest_path)
    payload = loads(read_bytes(manifest_path))
    if type(payload) is not dict and not isinstance(payload, dict):
        return {}
    return extract_provenance(
        payload,
        snapshot_manifest_path=manifest_path,
        copy_nested=False,
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
    token_metrics = normalized.get("agentic_sft_token_metrics")
    if isinstance(token_metrics, Mapping):
        payload.update(_agentic_sft_token_metric_aliases(token_metrics))
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


def _agentic_sft_token_metric_aliases(metrics: Mapping[str, Any]) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    estimator = str(metrics.get("estimator", "")).strip()
    if estimator:
        aliases["training.agentic_sft.token_estimator"] = estimator
    for source_key, alias_key in (
        ("source_trace_count", "training.agentic_sft.source_trace_count"),
        ("trace_tokens", "training.agentic_sft.trace_tokens"),
        ("tool_call_tokens", "training.agentic_sft.tool_call_tokens"),
        ("observation_tokens", "training.agentic_sft.observation_tokens"),
        ("final_answer_tokens", "training.agentic_sft.final_answer_tokens"),
    ):
        aliases[alias_key] = int(metrics.get(source_key, 0) or 0)
    return aliases
