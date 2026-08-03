from __future__ import annotations

import copy
import json
import os
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
    "agentic_sft_token_metrics",
)

TRAJECTORY_PROVENANCE_CSV_FIELDS = TRAJECTORY_PROVENANCE_FIELDS

_JSON_IMMUTABLE_TYPES = (str, int, float, bool, type(None))

# Optional manifest fields copied verbatim onto the provenance payload when
# present and non-empty, keyed by manifest key -> provenance field.
_OPTIONAL_MANIFEST_FIELDS = (
    ("trajectory_toolset_version", "trajectory_toolset_version"),
    ("trajectory_registry_schema_version", "trajectory_registry_schema_version"),
    ("trajectory_reward_policy_id", "trajectory_reward_policy_id"),
    ("trajectory_leakage_policy_id", "trajectory_leakage_policy_id"),
    ("source_package_path", "trajectory_package_path"),
    ("trajectory_quality_metrics", "trajectory_quality_metrics"),
    ("agentic_sft_token_metrics", "agentic_sft_token_metrics"),
)

_AGENTIC_SFT_TOKEN_COUNT_FIELDS = (
    "source_trace_count",
    "trace_tokens",
    "tool_call_tokens",
    "observation_tokens",
    "final_answer_tokens",
)


def _manifest_text(value: Any) -> str:
    return str(value).strip()


def _copy_trajectory_provenance_value(value: Any) -> Any:
    """Return a deep copy of a JSON-shaped provenance value.

    Containers are rebuilt as plain ``dict``/``list``/``tuple`` so callers can
    mutate the result without aliasing the source manifest. Anything that is
    not JSON-shaped falls back to ``copy.deepcopy``.
    """
    if isinstance(value, _JSON_IMMUTABLE_TYPES):
        return value
    if isinstance(value, Mapping):
        return {key: _copy_trajectory_provenance_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_copy_trajectory_provenance_value(item) for item in value)
    if isinstance(value, list):
        return [_copy_trajectory_provenance_value(item) for item in value]
    return copy.deepcopy(value)


def normalize_trajectory_provenance(
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the known provenance fields in canonical order.

    Container values are deeply copied so the result never aliases the source
    manifest; scalars (and anything that is not JSON-shaped) are kept as-is.
    """
    if not provenance:
        return {}
    normalized: dict[str, Any] = {}
    for field in TRAJECTORY_PROVENANCE_FIELDS:
        value = provenance.get(field)
        if value is None or value == "":
            continue
        if isinstance(value, (Mapping, list, tuple)):
            value = _copy_trajectory_provenance_value(value)
        normalized[field] = value
    return normalized


def append_trajectory_provenance(
    payload: dict[str, Any],
    provenance: Mapping[str, Any] | None,
) -> None:
    payload.update(normalize_trajectory_provenance(provenance))


def trajectory_provenance_from_snapshot_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    return normalize_trajectory_provenance(
        _trajectory_provenance_from_snapshot_manifest(
            manifest,
            snapshot_manifest_path=snapshot_manifest_path,
        )
    )


def _trajectory_provenance_from_snapshot_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    """Extract provenance from a snapshot manifest without copying nested values.

    The result aliases ``manifest``; callers that hand the payload to code
    which may mutate it must run it through ``normalize_trajectory_provenance``.
    """
    manifest_get = manifest.get
    # ``or ""`` matters: ``.get`` returns the default only for an absent key, so an
    # explicit ``"trajectory_trace_digest": null`` would otherwise reach
    # ``_manifest_text(None)`` and be stored as the literal string ``"None"``.
    trace_digest = _manifest_text(manifest_get("trajectory_trace_digest") or "")
    if _manifest_text(manifest_get("format", "")) != "agentic_tool_trace" and not trace_digest:
        return {}

    provenance: dict[str, Any] = {}
    dataset_id = _manifest_text(
        manifest_get("source_dataset_id") or manifest_get("dataset_id") or ""
    )
    if dataset_id:
        provenance["trajectory_dataset_id"] = dataset_id
    dataset_version = _manifest_text(manifest_get("version") or "")
    if dataset_version:
        provenance["trajectory_dataset_version"] = dataset_version
    schema_version = _manifest_text(
        manifest_get("trajectory_schema_version") or "melix.agentic_tool_trace.v1"
    )
    if schema_version:
        provenance["trajectory_schema_version"] = schema_version
    split = _manifest_text(manifest_get("trajectory_split") or "train")
    if split:
        provenance["trajectory_split"] = split
    if trace_digest:
        provenance["trajectory_trace_digest"] = trace_digest
    if snapshot_manifest_path is not None:
        provenance["trajectory_snapshot_manifest_path"] = str(snapshot_manifest_path)
    for manifest_key, field in _OPTIONAL_MANIFEST_FIELDS:
        value = manifest_get(manifest_key)
        if value is not None and value != "":
            provenance[field] = value
    return provenance


def load_trajectory_provenance_from_snapshot_manifest(
    manifest_path: Path | str | os.PathLike[str],
) -> dict[str, Any]:
    manifest_path_text = os.fspath(manifest_path)
    with open(manifest_path_text, "rb") as manifest_file:
        payload = json.loads(manifest_file.read())
    if not isinstance(payload, Mapping):
        return {}
    # ``payload`` was just parsed and is referenced by nothing else, so the
    # aliasing extractor is safe here.
    return _trajectory_provenance_from_snapshot_manifest(
        payload,
        snapshot_manifest_path=manifest_path_text,
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
    for field in _AGENTIC_SFT_TOKEN_COUNT_FIELDS:
        aliases[f"training.agentic_sft.{field}"] = int(metrics.get(field, 0) or 0)
    return aliases
