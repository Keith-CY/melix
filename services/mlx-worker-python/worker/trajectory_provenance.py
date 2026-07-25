from __future__ import annotations

import copy
import json
import os
from builtins import open as _builtin_open
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_JSON_LOADS = json.loads
_PATH_READ_BYTES = Path.read_bytes
_OPEN = _builtin_open
_OS_FSPATH = os.fspath
_STR = str
_INT = int
_TYPE = type


def _strip_manifest_text(value: Any) -> str:
    if type(value) is str:
        if value and not value[0].isspace() and not value[-1].isspace():
            return value
        return value.strip()
    return _STR(value).strip()


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
_AGENTIC_SFT_TOKEN_METRIC_FIELDS = (
    "estimator",
    "source_trace_count",
    "trace_tokens",
    "tool_call_tokens",
    "observation_tokens",
    "final_answer_tokens",
)


def _is_clean_manifest_text(value: Any) -> bool:
    return (
        type(value) is str
        and value != ""
        and not value[0].isspace()
        and not value[-1].isspace()
    )


def _copy_json_list(value: list[Any]) -> list[Any]:
    immutable_types = _JSON_IMMUTABLE_TYPE_SET
    value_type = _TYPE
    if len(value) == 7:
        item_0, item_1, item_2, item_3, item_4, item_5, item_6 = value
        if (
            value_type(item_0) in immutable_types
            and value_type(item_1) in immutable_types
            and value_type(item_2) in immutable_types
            and value_type(item_3) in immutable_types
            and value_type(item_4) in immutable_types
            and value_type(item_5) in immutable_types
            and value_type(item_6) in immutable_types
        ):
            return [item_0, item_1, item_2, item_3, item_4, item_5, item_6]
        return [_copy_trajectory_provenance_value(item) for item in value]
    for item in value:
        if value_type(item) not in immutable_types:
            return [_copy_trajectory_provenance_value(item) for item in value]
    return [*value]


def _copy_json_tuple(value: tuple[Any, ...]) -> tuple[Any, ...]:
    immutable_types = _JSON_IMMUTABLE_TYPE_SET
    value_type = _TYPE
    for item in value:
        if value_type(item) not in immutable_types:
            return tuple(_copy_trajectory_provenance_value(item) for item in value)
    return value


def _copy_json_dict(value: dict[str, Any]) -> dict[str, Any]:
    immutable_types = _JSON_IMMUTABLE_TYPE_SET
    value_type = _TYPE
    if len(value) == 6:
        try:
            estimator = value["estimator"]
            source_trace_count = value["source_trace_count"]
            trace_tokens = value["trace_tokens"]
            tool_call_tokens = value["tool_call_tokens"]
            observation_tokens = value["observation_tokens"]
            final_answer_tokens = value["final_answer_tokens"]
        except KeyError:
            pass
        else:
            if (
                value_type(estimator) in immutable_types
                and value_type(source_trace_count) in immutable_types
                and value_type(trace_tokens) in immutable_types
                and value_type(tool_call_tokens) in immutable_types
                and value_type(observation_tokens) in immutable_types
                and value_type(final_answer_tokens) in immutable_types
            ):
                return {
                    "estimator": estimator,
                    "source_trace_count": source_trace_count,
                    "trace_tokens": trace_tokens,
                    "tool_call_tokens": tool_call_tokens,
                    "observation_tokens": observation_tokens,
                    "final_answer_tokens": final_answer_tokens,
                }
    for item in value.values():
        if value_type(item) not in immutable_types:
            return {key: _copy_trajectory_provenance_value(item) for key, item in value.items()}
    return {**value}


def _copy_trajectory_provenance_value(value: Any) -> Any:
    value_type = _TYPE(value)
    if value_type in _JSON_IMMUTABLE_TYPE_SET:
        return value
    if value_type is dict:
        value_len = len(value)
        if value_len == 4:
            try:
                name = value["name"]
                score = value["score"]
                passed = value["passed"]
                labels = value["labels"]
            except KeyError:
                pass
            else:
                if (
                    _TYPE(name) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(score) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(passed) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(labels) is list
                ):
                    if len(labels) == 3:
                        label_0, label_1, label_2 = labels
                        if (
                            _TYPE(label_0) in _JSON_IMMUTABLE_TYPE_SET
                            and _TYPE(label_1) in _JSON_IMMUTABLE_TYPE_SET
                            and _TYPE(label_2) in _JSON_IMMUTABLE_TYPE_SET
                        ):
                            return {
                                "name": name,
                                "score": score,
                                "passed": passed,
                                "labels": [label_0, label_1, label_2],
                            }
                    else:
                        for label in labels:
                            if _TYPE(label) not in _JSON_IMMUTABLE_TYPE_SET:
                                break
                        else:
                            return {
                                "name": name,
                                "score": score,
                                "passed": passed,
                                "labels": [*labels],
                            }
                if (
                    _TYPE(name) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(score) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(passed) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(labels) is tuple
                ):
                    if len(labels) == 3:
                        label_0, label_1, label_2 = labels
                        if (
                            _TYPE(label_0) in _JSON_IMMUTABLE_TYPE_SET
                            and _TYPE(label_1) in _JSON_IMMUTABLE_TYPE_SET
                            and _TYPE(label_2) in _JSON_IMMUTABLE_TYPE_SET
                        ):
                            return {
                                "name": name,
                                "score": score,
                                "passed": passed,
                                "labels": labels,
                            }
                    else:
                        for label in labels:
                            if _TYPE(label) not in _JSON_IMMUTABLE_TYPE_SET:
                                break
                        else:
                            return {
                                "name": name,
                                "score": score,
                                "passed": passed,
                                "labels": labels,
                            }
        if value_len == 2:
            try:
                reward_coverage_count = value["reward_coverage_count"]
                components = value["components"]
            except KeyError:
                pass
            else:
                if (
                    _TYPE(reward_coverage_count) in _JSON_IMMUTABLE_TYPE_SET
                    and _TYPE(components) is list
                ):
                    return {
                        "reward_coverage_count": reward_coverage_count,
                        "components": [
                            _copy_trajectory_provenance_value(component)
                            for component in components
                        ],
                    }
        return {key: _copy_trajectory_provenance_value(item) for key, item in value.items()}
    if value_type is list:
        return _copy_json_list(value)
    if value_type is tuple:
        return _copy_json_tuple(value)
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
    value_type_of = _TYPE
    for field in TRAJECTORY_PROVENANCE_FIELDS:
        value = provenance_get(field)
        if value is None:
            continue
        value_type = value_type_of(value)
        if value_type is str:
            if value == "":
                continue
            normalized[field] = value
        elif value_type is dict:
            if field == "agentic_sft_token_metrics":
                normalized[field] = _copy_json_dict(value)
            else:
                normalized[field] = copy_value(value)
        elif value_type is list:
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


def _fast_trajectory_provenance_from_snapshot_manifest(
    manifest: dict[str, Any],
    *,
    snapshot_manifest_path: str | None,
) -> dict[str, Any] | None:
    manifest_get = manifest.get
    value_type = _TYPE
    if manifest_get("format") != "agentic_tool_trace":
        return None
    dataset_id = manifest_get("source_dataset_id")
    if (
        value_type(dataset_id) is not str
        or dataset_id == ""
        or dataset_id[0].isspace()
        or dataset_id[-1].isspace()
    ):
        return None
    dataset_version = manifest_get("version")
    if (
        value_type(dataset_version) is not str
        or dataset_version == ""
        or dataset_version[0].isspace()
        or dataset_version[-1].isspace()
    ):
        return None
    schema_version = manifest_get("trajectory_schema_version")
    if schema_version is None:
        schema_version = "melix.agentic_tool_trace.v1"
    elif (
        value_type(schema_version) is not str
        or schema_version == ""
        or schema_version[0].isspace()
        or schema_version[-1].isspace()
    ):
        return None
    split = manifest_get("trajectory_split")
    if split is None:
        split = "train"
    elif (
        value_type(split) is not str
        or split == ""
        or split[0].isspace()
        or split[-1].isspace()
    ):
        return None
    trace_digest = manifest_get("trajectory_trace_digest")
    if (
        value_type(trace_digest) is not str
        or trace_digest == ""
        or trace_digest[0].isspace()
        or trace_digest[-1].isspace()
    ):
        return None
    provenance: dict[str, Any] = {
        "trajectory_dataset_id": dataset_id,
        "trajectory_dataset_version": dataset_version,
        "trajectory_schema_version": schema_version,
        "trajectory_split": split,
        "trajectory_trace_digest": trace_digest,
    }
    if snapshot_manifest_path is not None:
        provenance["trajectory_snapshot_manifest_path"] = snapshot_manifest_path
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
    return provenance


def _trajectory_provenance_from_snapshot_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_manifest_path: Path | str | None = None,
    copy_nested: bool,
) -> dict[str, Any]:
    if not copy_nested and type(manifest) is dict:
        snapshot_manifest_path_text = (
            snapshot_manifest_path
            if type(snapshot_manifest_path) is str
            else _STR(snapshot_manifest_path)
            if snapshot_manifest_path is not None
            else None
        )
        fast_provenance = _fast_trajectory_provenance_from_snapshot_manifest(
            manifest,
            snapshot_manifest_path=snapshot_manifest_path_text,
        )
        if fast_provenance is not None:
            return fast_provenance
    manifest_get = manifest.get
    strip_text = _strip_manifest_text
    format_value = manifest_get("format", "")
    trace_digest_value = manifest_get("trajectory_trace_digest", "")
    if format_value != "agentic_tool_trace" and (
        strip_text(format_value) != "agentic_tool_trace"
        and not strip_text(trace_digest_value)
    ):
        return {}

    provenance: dict[str, Any] = {}
    dataset_id = strip_text(
        manifest_get("source_dataset_id") or manifest_get("dataset_id") or ""
    )
    if dataset_id:
        provenance["trajectory_dataset_id"] = dataset_id
    dataset_version = strip_text(manifest_get("version") or "")
    if dataset_version:
        provenance["trajectory_dataset_version"] = dataset_version
    schema_version = strip_text(
        manifest_get("trajectory_schema_version") or "melix.agentic_tool_trace.v1"
    )
    if schema_version:
        provenance["trajectory_schema_version"] = schema_version
    split = strip_text(manifest_get("trajectory_split") or "train")
    if split:
        provenance["trajectory_split"] = split
    trace_digest = strip_text(trace_digest_value or "")
    if trace_digest:
        provenance["trajectory_trace_digest"] = trace_digest
    if snapshot_manifest_path is not None:
        if type(snapshot_manifest_path) is str:
            provenance["trajectory_snapshot_manifest_path"] = snapshot_manifest_path
        else:
            provenance["trajectory_snapshot_manifest_path"] = _STR(snapshot_manifest_path)
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
    manifest_path: Path | str | os.PathLike[str],
) -> dict[str, Any]:
    open_file = _OPEN
    loads = _JSON_LOADS
    extract_provenance = _trajectory_provenance_from_snapshot_manifest
    if type(manifest_path) is str:
        manifest_path_text = manifest_path
    else:
        manifest_path_text = _OS_FSPATH(manifest_path)
    with open_file(manifest_path_text, "rb") as manifest_file:
        payload = loads(manifest_file.read())
    if type(payload) is dict:
        manifest_get = payload.get
        if manifest_get("format") == "agentic_tool_trace":
            value_type = _TYPE
            dataset_id = manifest_get("source_dataset_id")
            dataset_version = manifest_get("version")
            trace_digest = manifest_get("trajectory_trace_digest")
            if (
                value_type(dataset_id) is str
                and dataset_id != ""
                and not dataset_id[0].isspace()
                and not dataset_id[-1].isspace()
                and value_type(dataset_version) is str
                and dataset_version != ""
                and not dataset_version[0].isspace()
                and not dataset_version[-1].isspace()
                and value_type(trace_digest) is str
                and trace_digest != ""
                and not trace_digest[0].isspace()
                and not trace_digest[-1].isspace()
            ):
                if len(payload) == 6:
                    trajectory_quality_metrics = manifest_get("trajectory_quality_metrics")
                    agentic_sft_token_metrics = manifest_get("agentic_sft_token_metrics")
                    if (
                        trajectory_quality_metrics is not None
                        and trajectory_quality_metrics != ""
                        and agentic_sft_token_metrics is not None
                        and agentic_sft_token_metrics != ""
                    ):
                        return {
                            "trajectory_dataset_id": dataset_id,
                            "trajectory_dataset_version": dataset_version,
                            "trajectory_schema_version": "melix.agentic_tool_trace.v1",
                            "trajectory_snapshot_manifest_path": manifest_path_text,
                            "trajectory_split": "train",
                            "trajectory_trace_digest": trace_digest,
                            "trajectory_quality_metrics": trajectory_quality_metrics,
                            "agentic_sft_token_metrics": agentic_sft_token_metrics,
                        }
                schema_version = manifest_get("trajectory_schema_version")
                if schema_version is None:
                    schema_version = "melix.agentic_tool_trace.v1"
                elif (
                    value_type(schema_version) is not str
                    or schema_version == ""
                    or schema_version[0].isspace()
                    or schema_version[-1].isspace()
                ):
                    schema_version = None
                split = manifest_get("trajectory_split")
                if split is None:
                    split = "train"
                elif (
                    value_type(split) is not str
                    or split == ""
                    or split[0].isspace()
                    or split[-1].isspace()
                ):
                    split = None
                if schema_version is not None and split is not None:
                    provenance: dict[str, Any] = {
                        "trajectory_dataset_id": dataset_id,
                        "trajectory_dataset_version": dataset_version,
                        "trajectory_schema_version": schema_version,
                        "trajectory_snapshot_manifest_path": manifest_path_text,
                        "trajectory_split": split,
                        "trajectory_trace_digest": trace_digest,
                    }
                    trajectory_toolset_version = manifest_get("trajectory_toolset_version")
                    if trajectory_toolset_version is not None and trajectory_toolset_version != "":
                        provenance["trajectory_toolset_version"] = trajectory_toolset_version
                    trajectory_registry_schema_version = manifest_get("trajectory_registry_schema_version")
                    if trajectory_registry_schema_version is not None and trajectory_registry_schema_version != "":
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
                    return provenance
        return extract_provenance(
            payload,
            snapshot_manifest_path=manifest_path_text,
            copy_nested=False,
        )
    if not isinstance(payload, dict):
        return {}
    return extract_provenance(
        payload,
        snapshot_manifest_path=manifest_path_text,
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
    if type(provenance) is dict:
        fast_payload = _fast_adapter_manifest_trajectory_provenance(provenance)
        if fast_payload is not None:
            return fast_payload
    normalized = normalize_trajectory_provenance(provenance)
    if not normalized:
        return {}
    payload = dict(normalized)
    payload["trajectory_provenance_field_count"] = len(normalized)
    payload["trajectory_reward_policy_present"] = bool(
        normalized.get("trajectory_reward_policy_id")
    )
    token_metrics = normalized.get("agentic_sft_token_metrics")
    if type(token_metrics) is dict:
        payload.update(_agentic_sft_token_metric_aliases(token_metrics))
    elif isinstance(token_metrics, Mapping):
        payload.update(_agentic_sft_token_metric_aliases(token_metrics))
    return payload


def _fast_adapter_manifest_trajectory_provenance(
    provenance: dict[str, Any],
) -> dict[str, Any] | None:
    if len(provenance) != 6:
        return None
    provenance_get = provenance.get
    dataset_id = provenance_get("trajectory_dataset_id")
    dataset_version = provenance_get("trajectory_dataset_version")
    schema_version = provenance_get("trajectory_schema_version")
    trace_digest = provenance_get("trajectory_trace_digest")
    quality_metrics = provenance_get("trajectory_quality_metrics")
    token_metrics = provenance_get("agentic_sft_token_metrics")
    value_type = _TYPE
    if (
        value_type(dataset_id) is not str
        or dataset_id == ""
        or value_type(dataset_version) is not str
        or dataset_version == ""
        or value_type(schema_version) is not str
        or schema_version == ""
        or value_type(trace_digest) is not str
        or trace_digest == ""
        or value_type(quality_metrics) is not dict
        or value_type(token_metrics) is not dict
    ):
        return None
    if (
        dataset_id[0].isspace()
        or dataset_id[-1].isspace()
        or dataset_version[0].isspace()
        or dataset_version[-1].isspace()
        or schema_version[0].isspace()
        or schema_version[-1].isspace()
        or trace_digest[0].isspace()
        or trace_digest[-1].isspace()
    ):
        return None
    payload: dict[str, Any] = {
        "trajectory_dataset_id": dataset_id,
        "trajectory_dataset_version": dataset_version,
        "trajectory_schema_version": schema_version,
        "trajectory_trace_digest": trace_digest,
        "trajectory_quality_metrics": _copy_trajectory_provenance_value(
            quality_metrics
        ),
        "agentic_sft_token_metrics": _copy_json_dict(token_metrics),
        "trajectory_provenance_field_count": 6,
        "trajectory_reward_policy_present": False,
    }
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
    int_value = _INT
    value_type = _TYPE
    if type(metrics) is dict and len(metrics) == 6:
        try:
            estimator = metrics["estimator"]
            source_trace_count = metrics["source_trace_count"]
            trace_tokens = metrics["trace_tokens"]
            tool_call_tokens = metrics["tool_call_tokens"]
            observation_tokens = metrics["observation_tokens"]
            final_answer_tokens = metrics["final_answer_tokens"]
        except KeyError:
            pass
        else:
            if type(estimator) is str:
                if estimator and not estimator[0].isspace() and not estimator[-1].isspace():
                    if (
                        value_type(source_trace_count) is int
                        and value_type(trace_tokens) is int
                        and value_type(tool_call_tokens) is int
                        and value_type(observation_tokens) is int
                        and value_type(final_answer_tokens) is int
                    ):
                        return {
                            "training.agentic_sft.token_estimator": estimator,
                            "training.agentic_sft.source_trace_count": source_trace_count,
                            "training.agentic_sft.trace_tokens": trace_tokens,
                            "training.agentic_sft.tool_call_tokens": tool_call_tokens,
                            "training.agentic_sft.observation_tokens": observation_tokens,
                            "training.agentic_sft.final_answer_tokens": final_answer_tokens,
                        }
                    return {
                        "training.agentic_sft.token_estimator": estimator,
                        "training.agentic_sft.source_trace_count": int_value(
                            source_trace_count or 0
                        ),
                        "training.agentic_sft.trace_tokens": int_value(trace_tokens or 0),
                        "training.agentic_sft.tool_call_tokens": int_value(
                            tool_call_tokens or 0
                        ),
                        "training.agentic_sft.observation_tokens": int_value(
                            observation_tokens or 0
                        ),
                        "training.agentic_sft.final_answer_tokens": int_value(
                            final_answer_tokens or 0
                        ),
                    }
                estimator_text = estimator.strip()
            else:
                estimator_text = _STR(estimator).strip()
            if estimator_text:
                return {
                    "training.agentic_sft.token_estimator": estimator_text,
                    "training.agentic_sft.source_trace_count": int_value(
                        source_trace_count or 0
                    ),
                    "training.agentic_sft.trace_tokens": int_value(trace_tokens or 0),
                    "training.agentic_sft.tool_call_tokens": int_value(
                        tool_call_tokens or 0
                    ),
                    "training.agentic_sft.observation_tokens": int_value(
                        observation_tokens or 0
                    ),
                    "training.agentic_sft.final_answer_tokens": int_value(
                        final_answer_tokens or 0
                    ),
                }
            return {
                "training.agentic_sft.source_trace_count": int_value(
                    source_trace_count or 0
                ),
                "training.agentic_sft.trace_tokens": int_value(trace_tokens or 0),
                "training.agentic_sft.tool_call_tokens": int_value(tool_call_tokens or 0),
                "training.agentic_sft.observation_tokens": int_value(
                    observation_tokens or 0
                ),
                "training.agentic_sft.final_answer_tokens": int_value(
                    final_answer_tokens or 0
                ),
            }
    metrics_get = metrics.get
    estimator = _STR(metrics_get("estimator", "")).strip()
    if estimator:
        return {
            "training.agentic_sft.token_estimator": estimator,
            "training.agentic_sft.source_trace_count": int_value(
                metrics_get("source_trace_count", 0) or 0
            ),
            "training.agentic_sft.trace_tokens": int_value(
                metrics_get("trace_tokens", 0) or 0
            ),
            "training.agentic_sft.tool_call_tokens": int_value(
                metrics_get("tool_call_tokens", 0) or 0
            ),
            "training.agentic_sft.observation_tokens": int_value(
                metrics_get("observation_tokens", 0) or 0
            ),
            "training.agentic_sft.final_answer_tokens": int_value(
                metrics_get("final_answer_tokens", 0) or 0
            ),
        }
    return {
        "training.agentic_sft.source_trace_count": int_value(
            metrics_get("source_trace_count", 0) or 0
        ),
        "training.agentic_sft.trace_tokens": int_value(
            metrics_get("trace_tokens", 0) or 0
        ),
        "training.agentic_sft.tool_call_tokens": int_value(
            metrics_get("tool_call_tokens", 0) or 0
        ),
        "training.agentic_sft.observation_tokens": int_value(
            metrics_get("observation_tokens", 0) or 0
        ),
        "training.agentic_sft.final_answer_tokens": int_value(
            metrics_get("final_answer_tokens", 0) or 0
        ),
    }
