from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


ROLLOUT_MANIFEST_SCHEMA_VERSION = "melix.alignment_rollout_manifest.v1"
DEFAULT_GRPO_REWARD_POLICY_ID = "melix.agentic_grpo_reward_components.v1"
DEFAULT_REWARD_MODEL_POLICY_ID = "melix.reward_model_scoring.v1"
DEFAULT_RLHF_DATASET_REWARD_POLICY_ID = "melix.rlhf_dataset_reward.v1"
DEFAULT_DATASET_REWARD_POLICY_ID = "melix.dataset_score_reward.v1"


def build_alignment_rollout_manifest_fields(
    *,
    alignment_algorithm: str,
    configured_candidate_count: int,
    candidate_scoring_mode: str,
    explicit_reference_model_path: str,
    default_reference_model_path: str,
    trajectory_provenance: Mapping[str, Any] | None,
    trace_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "rollout_manifest_schema_version": ROLLOUT_MANIFEST_SCHEMA_VERSION,
        "rollout_candidate_count": _rollout_candidate_count(
            alignment_algorithm=alignment_algorithm,
            configured_candidate_count=configured_candidate_count,
        ),
        "rollout_reward_policy_id": _rollout_reward_policy_id(
            alignment_algorithm=alignment_algorithm,
            candidate_scoring_mode=candidate_scoring_mode,
            trajectory_provenance=trajectory_provenance,
        ),
        "rollout_reference_model_path": _rollout_reference_model_path(
            explicit_reference_model_path=explicit_reference_model_path,
            default_reference_model_path=default_reference_model_path,
        ),
        "rollout_trajectory_digest": _rollout_trajectory_digest(
            trajectory_provenance=trajectory_provenance,
            trace_rows=trace_rows,
        ),
    }


def build_alignment_rollout_manifest_fields_from_training_metrics(
    *,
    metrics: Any,
    alignment_algorithm: str,
    configured_candidate_count: int,
    candidate_scoring_mode: str,
    explicit_reference_model_path: str,
    default_reference_model_path: str,
    trajectory_provenance: Mapping[str, Any] | None,
    trace_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    schema_version = str(getattr(metrics, "rollout_manifest_schema_version", "") or "")
    if schema_version:
        return {
            "rollout_manifest_schema_version": schema_version,
            "rollout_candidate_count": int(getattr(metrics, "rollout_candidate_count")),
            "rollout_reward_policy_id": str(getattr(metrics, "rollout_reward_policy_id")),
            "rollout_reference_model_path": str(getattr(metrics, "rollout_reference_model_path")),
            "rollout_trajectory_digest": str(getattr(metrics, "rollout_trajectory_digest")),
        }
    return build_alignment_rollout_manifest_fields(
        alignment_algorithm=alignment_algorithm,
        configured_candidate_count=configured_candidate_count,
        candidate_scoring_mode=candidate_scoring_mode,
        explicit_reference_model_path=explicit_reference_model_path,
        default_reference_model_path=default_reference_model_path,
        trajectory_provenance=trajectory_provenance,
        trace_rows=trace_rows,
    )


def _rollout_candidate_count(
    *,
    alignment_algorithm: str,
    configured_candidate_count: int,
) -> int:
    if alignment_algorithm == "grpo":
        return int(configured_candidate_count)
    if alignment_algorithm == "rlhf":
        return 1
    return max(0, int(configured_candidate_count))


def _rollout_reward_policy_id(
    *,
    alignment_algorithm: str,
    candidate_scoring_mode: str,
    trajectory_provenance: Mapping[str, Any] | None,
) -> str:
    if trajectory_provenance:
        policy_id = str(trajectory_provenance.get("trajectory_reward_policy_id") or "").strip()
        if policy_id:
            return policy_id
    if candidate_scoring_mode == "reward_model":
        return DEFAULT_REWARD_MODEL_POLICY_ID
    if alignment_algorithm == "grpo":
        return DEFAULT_GRPO_REWARD_POLICY_ID
    if alignment_algorithm == "rlhf":
        return DEFAULT_RLHF_DATASET_REWARD_POLICY_ID
    return DEFAULT_DATASET_REWARD_POLICY_ID


def _rollout_reference_model_path(
    *,
    explicit_reference_model_path: str,
    default_reference_model_path: str,
) -> str:
    explicit = explicit_reference_model_path.strip()
    if explicit:
        return explicit
    return default_reference_model_path.strip()


def _rollout_trajectory_digest(
    *,
    trajectory_provenance: Mapping[str, Any] | None,
    trace_rows: Sequence[Mapping[str, Any]],
) -> str:
    if trajectory_provenance:
        trace_digest = str(trajectory_provenance.get("trajectory_trace_digest") or "").strip()
        if trace_digest:
            return trace_digest
    digest = hashlib.sha256()
    for row in trace_rows:
        digest.update(
            json.dumps(
                row,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()
