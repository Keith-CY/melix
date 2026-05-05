from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
from typing import Any

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError


@dataclass(frozen=True)
class PolicyUpdateResult:
    trace_rows: list[dict[str, Any]]
    reward_values: list[float]
    group_margins: list[float]
    group_variances: list[float]
    selected_count: int
    execution_backend: str
    candidate_generation_mode: str
    candidate_scoring_mode: str
    candidate_generation_backend: str = ""
    generated_candidate_count: int = 0


def train_alignment_rl_trace(request: Any, *, policy_runtime: Any | None = None) -> Any:
    from worker.model_ops.mlx_lm_runner import TrainingMetrics, TrainingResult

    alignment = request.config.alignment
    if alignment is None:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="alignment_rl training requires alignment config.",
        )

    started_at = time.perf_counter()
    samples = _load_training_rows(request.normalized_dataset_dir / "train.jsonl")
    if alignment.alignment_algorithm == "grpo":
        if alignment.candidate_generation_mode == "runtime_generate":
            policy_updates = _grpo_runtime_policy_updates(
                request,
                samples,
                candidate_count=alignment.grpo_candidate_count,
                policy_runtime=policy_runtime,
            )
        else:
            policy_updates = _grpo_policy_updates(
                samples,
                candidate_count=alignment.grpo_candidate_count,
            )
    elif alignment.alignment_algorithm == "rlhf":
        policy_updates = _rlhf_policy_updates(samples)
    else:
        raise ModelOperationError(
            code="unsupported_alignment_trainer",
            message=f"Unsupported RL alignment algorithm: {alignment.alignment_algorithm}",
            details={"alignment_algorithm": alignment.alignment_algorithm},
        )

    request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
    weights_path = request.adapter_output_dir / "adapters.safetensors"
    adapter_config_path = request.adapter_output_dir / "adapter_config.json"
    policy_update_trace_path = request.adapter_output_dir / "policy_updates.jsonl"
    checkpoint_dir = request.adapter_output_dir / "checkpoint-1"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    latest_checkpoint_path = checkpoint_dir / "adapters.safetensors"

    _write_jsonl(policy_update_trace_path, policy_updates.trace_rows)
    adapter_config = {
        "fine_tune_type": "lora",
        "alignment_algorithm": alignment.alignment_algorithm,
        "execution_backend": policy_updates.execution_backend,
        "policy_update_trace_path": str(policy_update_trace_path),
        "reward_model_manifest_path": alignment.reward_model_manifest_path,
        "reference_model_path": alignment.reference_model_path,
        "kl_penalty": alignment.kl_penalty,
        "grpo_candidate_count": alignment.grpo_candidate_count,
        "candidate_generation_mode": policy_updates.candidate_generation_mode,
        "candidate_generation_backend": policy_updates.candidate_generation_backend,
        "candidate_scoring_mode": policy_updates.candidate_scoring_mode,
        "lora_parameters": {
            "rank": request.config.rank,
            "dropout": request.config.dropout,
            "scale": request.config.alpha,
            "keys": request.config.expanded_target_modules,
        },
    }
    adapter_config_path.write_text(json.dumps(adapter_config, indent=2) + "\n", encoding="utf-8")
    weights_payload = {
        "schema_version": "melix.scored_alignment_adapter.v1",
        "job_id": request.job_id,
        "base_model_id": request.base_model_id,
        "alignment_algorithm": alignment.alignment_algorithm,
        "policy_update_digest": _trace_digest(policy_updates.trace_rows),
    }
    weights_bytes = json.dumps(weights_payload, sort_keys=True).encode("utf-8")
    weights_path.write_bytes(weights_bytes)
    latest_checkpoint_path.write_bytes(weights_bytes)

    duration_ms = (time.perf_counter() - started_at) * 1000.0
    reward_summary = _reward_summary(policy_updates.reward_values)
    return TrainingResult(
        weights_path=weights_path,
        adapter_config_path=adapter_config_path,
        metrics=TrainingMetrics(
            job_duration_ms=duration_ms,
            tokens_seen=_estimated_tokens_seen(policy_updates.trace_rows),
            examples_seen=len(samples),
            loss_final=-reward_summary["reward_mean"],
            loss_best=-max(policy_updates.reward_values),
            learning_rate_final=request.config.learning_rate,
            checkpoint_count=1,
            resume_ready=True,
            latest_checkpoint_path=str(latest_checkpoint_path),
            resume_source_path=str(request.resume_source_path) if request.resume_source_path is not None else "",
            tokens_per_second=_tokens_per_second(policy_updates.trace_rows, duration_ms),
            peak_memory_gb=0.0,
            reward_mean=reward_summary["reward_mean"],
            reward_p50=reward_summary["reward_p50"],
            reward_p95=reward_summary["reward_p95"],
            policy_update_count=len(policy_updates.trace_rows),
            selected_candidate_count=policy_updates.selected_count,
            candidate_group_count=len(policy_updates.group_margins),
            candidate_group_reward_margin_mean=_mean(policy_updates.group_margins),
            candidate_group_reward_variance_mean=_mean(policy_updates.group_variances),
            policy_update_trace_path=str(policy_update_trace_path),
            candidate_generation_mode=policy_updates.candidate_generation_mode,
            candidate_generation_backend=policy_updates.candidate_generation_backend,
            candidate_scoring_mode=policy_updates.candidate_scoring_mode,
            generated_candidate_count=policy_updates.generated_candidate_count,
        ),
        execution_backend=policy_updates.execution_backend,
    )


def _load_training_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ModelOperationError(
                        code="invalid_alignment_dataset",
                        message="alignment_rl train.jsonl rows must be JSON objects.",
                        details={"line_number": str(line_number)},
                    )
                rows.append(payload)
    except FileNotFoundError as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="alignment_rl training requires train.jsonl.",
            details={"path": str(path)},
        ) from exc
    except json.JSONDecodeError as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="alignment_rl train.jsonl must contain valid JSON lines.",
            details={"path": str(path)},
        ) from exc
    if not rows:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="alignment_rl training requires at least one scored row.",
            details={"path": str(path)},
        )
    return rows


def _grpo_policy_updates(
    samples: list[dict[str, Any]],
    *,
    candidate_count: int,
) -> PolicyUpdateResult:
    trace_rows: list[dict[str, Any]] = []
    reward_values: list[float] = []
    group_margins: list[float] = []
    group_variances: list[float] = []
    for sample_index, sample in enumerate(samples):
        candidates = sample.get("candidates")
        if not isinstance(candidates, list) or len(candidates) < candidate_count:
            raise ModelOperationError(
                code="invalid_alignment_dataset",
                message="GRPO scored trace rows must contain enough candidates.",
                details={
                    "sample_index": str(sample_index),
                    "candidate_count": str(len(candidates) if isinstance(candidates, list) else 0),
                    "grpo_candidate_count": str(candidate_count),
                },
            )
        scored_candidates = []
        for candidate_index, candidate in enumerate(candidates[:candidate_count]):
            if not isinstance(candidate, dict) or "score" not in candidate:
                raise ModelOperationError(
                    code="invalid_alignment_dataset",
                    message="GRPO scored trace candidates must include numeric score.",
                    details={
                        "alignment_algorithm": "grpo",
                        "sample_index": str(sample_index),
                        "candidate_index": str(candidate_index),
                        "missing_field": "candidate.score",
                    },
                )
            scored_candidates.append(
                {
                    "index": candidate_index,
                    "text": str(candidate.get("text", "")),
                    "score": float(candidate["score"]),
                }
            )
        scores = [candidate["score"] for candidate in scored_candidates]
        reward_values.extend(scores)
        selected = max(scored_candidates, key=lambda candidate: candidate["score"])
        group_margins.append(max(scores) - min(scores))
        group_mean = sum(scores) / len(scores)
        group_variances.append(sum((score - group_mean) ** 2 for score in scores) / len(scores))
        trace_rows.append(
            {
                "sample_index": sample_index,
                "alignment_algorithm": "grpo",
                "candidate_generation_mode": "scored_trace",
                "candidate_scoring_mode": "dataset_score",
                "prompt": str(sample.get("prompt", "")),
                "selected_candidate_index": selected["index"],
                "selected_reward": selected["score"],
                "group_reward_mean": group_mean,
                "group_reward_margin": group_margins[-1],
                "candidate_count": len(scored_candidates),
            }
        )
    return PolicyUpdateResult(
        trace_rows=trace_rows,
        reward_values=reward_values,
        group_margins=group_margins,
        group_variances=group_variances,
        selected_count=len(trace_rows),
        execution_backend="scored_trace",
        candidate_generation_mode="scored_trace",
        candidate_scoring_mode="dataset_score",
    )


def _grpo_runtime_policy_updates(
    request: Any,
    samples: list[dict[str, Any]],
    *,
    candidate_count: int,
    policy_runtime: Any | None,
) -> PolicyUpdateResult:
    if policy_runtime is None:
        raise ModelOperationError(
            code="unsupported_alignment_trainer",
            message="GRPO runtime candidate generation requires a policy runtime.",
            details={
                "alignment_algorithm": "grpo",
                "candidate_generation_mode": "runtime_generate",
                "required_backend": "policy_runtime",
            },
        )

    loaded_model = policy_runtime.load_model(_runtime_model_spec(request))
    runtime_name = str(getattr(policy_runtime, "runtime_name", "") or "unknown-runtime")
    sampling = _runtime_sampling(request.config.alignment)
    cancel_event = threading.Event()

    trace_rows: list[dict[str, Any]] = []
    reward_values: list[float] = []
    group_margins: list[float] = []
    group_variances: list[float] = []
    generated_candidate_total = 0
    for sample_index, sample in enumerate(samples):
        prompt = str(sample.get("prompt", ""))
        seed_candidates = _scored_seed_candidates(sample, sample_index=sample_index)
        generated_candidates: list[dict[str, Any]] = []
        for candidate_index in range(candidate_count):
            generation_prompt = _runtime_generation_prompt(
                prompt,
                candidate_index=candidate_index,
                candidate_count=candidate_count,
            )
            generated_text = _generate_candidate_text(
                policy_runtime,
                loaded_model,
                generation_prompt,
                sampling,
                cancel_event,
            )
            score = _seed_overlap_proxy_score(generated_text, seed_candidates)
            generated_candidates.append(
                {
                    "index": candidate_index,
                    "text": generated_text,
                    "score": score,
                    "generation_prompt": generation_prompt,
                    "source": "policy_runtime",
                }
            )
        scores = [candidate["score"] for candidate in generated_candidates]
        reward_values.extend(scores)
        selected = max(generated_candidates, key=lambda candidate: candidate["score"])
        group_margins.append(max(scores) - min(scores))
        group_mean = sum(scores) / len(scores)
        group_variances.append(sum((score - group_mean) ** 2 for score in scores) / len(scores))
        generated_candidate_total += len(generated_candidates)
        trace_rows.append(
            {
                "sample_index": sample_index,
                "alignment_algorithm": "grpo",
                "candidate_generation_mode": "runtime_generate",
                "candidate_generation_backend": runtime_name,
                "candidate_scoring_mode": "seed_overlap_proxy",
                "prompt": prompt,
                "selected_candidate_index": selected["index"],
                "selected_candidate_text": selected["text"],
                "selected_reward": selected["score"],
                "group_reward_mean": group_mean,
                "group_reward_margin": group_margins[-1],
                "candidate_count": len(generated_candidates),
                "generated_candidates": generated_candidates,
            }
        )
    return PolicyUpdateResult(
        trace_rows=trace_rows,
        reward_values=reward_values,
        group_margins=group_margins,
        group_variances=group_variances,
        selected_count=len(trace_rows),
        execution_backend="runtime_generated_scored_trace",
        candidate_generation_mode="runtime_generate",
        candidate_generation_backend=runtime_name,
        candidate_scoring_mode="seed_overlap_proxy",
        generated_candidate_count=generated_candidate_total,
    )


def _rlhf_policy_updates(
    samples: list[dict[str, Any]],
) -> PolicyUpdateResult:
    trace_rows: list[dict[str, Any]] = []
    reward_values: list[float] = []
    for sample_index, sample in enumerate(samples):
        if "reward_score" not in sample:
            raise ModelOperationError(
                code="invalid_alignment_dataset",
                message="RLHF scored trace rows must include reward_score.",
                details={
                    "alignment_algorithm": "rlhf",
                    "sample_index": str(sample_index),
                    "missing_field": "reward_score",
                },
            )
        reward = float(sample["reward_score"])
        reward_values.append(reward)
        trace_rows.append(
            {
                "sample_index": sample_index,
                "alignment_algorithm": "rlhf",
                "candidate_generation_mode": "scored_trace",
                "candidate_scoring_mode": "dataset_score",
                "prompt": str(sample.get("prompt", "")),
                "selected_response": str(sample.get("response", "")),
                "selected_reward": reward,
            }
        )
    return PolicyUpdateResult(
        trace_rows=trace_rows,
        reward_values=reward_values,
        group_margins=[],
        group_variances=[],
        selected_count=len(trace_rows),
        execution_backend="scored_trace",
        candidate_generation_mode="scored_trace",
        candidate_scoring_mode="dataset_score",
    )


def _runtime_model_spec(request: Any) -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id=request.base_model_id,
        model_path=str(request.model_path),
        model_kind=str(getattr(request, "source_model_kind", "") or "text"),
        revision=request.model_revision,
    )
    source_model_ext = getattr(request, "source_model_ext", None)
    if isinstance(source_model_ext, dict):
        model.ext.update({str(key): str(value) for key, value in source_model_ext.items()})
    return model


def _runtime_sampling(alignment: Any) -> SimpleNamespace:
    return SimpleNamespace(
        temperature=alignment.candidate_generation_temperature,
        top_p=alignment.candidate_generation_top_p,
        top_k=alignment.candidate_generation_top_k,
        max_output_tokens=alignment.candidate_generation_max_tokens,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        stop=[],
    )


def _runtime_generation_prompt(prompt: str, *, candidate_index: int, candidate_count: int) -> str:
    return (
        f"{prompt.strip()}\n\n"
        f"Generate candidate {candidate_index + 1} of {candidate_count}. "
        "Return only the candidate response."
    )


def _generate_candidate_text(
    policy_runtime: Any,
    loaded_model: Any,
    generation_prompt: str,
    sampling: SimpleNamespace,
    cancel_event: threading.Event,
) -> str:
    chunks: list[str] = []
    for event in policy_runtime.generate_tokens(
        loaded_model,
        generation_prompt,
        sampling,
        cancel_event,
        execution_ext={"melix.alignment.candidate_generation": "grpo"},
    ):
        text = str(getattr(event, "text", event) or "")
        if text:
            chunks.append(text)
    generated_text = "".join(chunks).strip()
    if not generated_text:
        raise ModelOperationError(
            code="alignment_generation_failed",
            message="GRPO runtime candidate generation returned an empty candidate.",
            details={"candidate_generation_mode": "runtime_generate"},
        )
    return generated_text


def _scored_seed_candidates(sample: dict[str, Any], *, sample_index: int) -> list[dict[str, Any]]:
    candidates = sample.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
    scored_candidates: list[dict[str, Any]] = []
    for candidate_index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or "score" not in candidate:
            continue
        scored_candidates.append(
            {
                "index": candidate_index,
                "text": str(candidate.get("text", "")),
                "score": float(candidate["score"]),
            }
        )
    if not scored_candidates:
        raise ModelOperationError(
            code="invalid_alignment_dataset",
            message="GRPO runtime candidate generation requires at least one scored seed candidate.",
            details={
                "alignment_algorithm": "grpo",
                "candidate_generation_mode": "runtime_generate",
                "sample_index": str(sample_index),
                "missing_field": "candidate.score",
            },
        )
    return scored_candidates


def _seed_overlap_proxy_score(generated_text: str, seed_candidates: list[dict[str, Any]]) -> float:
    best_seed = max(seed_candidates, key=lambda candidate: candidate["score"])
    reference_tokens = _normalized_token_set(str(best_seed.get("text", "")))
    if not reference_tokens:
        return float(best_seed["score"])
    generated_tokens = _normalized_token_set(generated_text)
    overlap_ratio = len(generated_tokens & reference_tokens) / len(reference_tokens)
    return float(best_seed["score"]) * overlap_ratio


def _normalized_token_set(text: str) -> set[str]:
    return {
        token
        for token in "".join(
            character.lower() if character.isalnum() else " "
            for character in text
        ).split()
        if token
    }


def _reward_summary(reward_values: list[float]) -> dict[str, float]:
    if not reward_values:
        raise ModelOperationError(
            code="invalid_alignment_dataset",
            message="alignment_rl training requires at least one reward score.",
        )
    ordered = sorted(reward_values)
    return {
        "reward_mean": sum(ordered) / len(ordered),
        "reward_p50": _percentile_value(ordered, 0.5),
        "reward_p95": _percentile_value(ordered, 0.95),
    }


def _percentile_value(ordered_values: list[float], percentile: float) -> float:
    if len(ordered_values) == 1:
        return ordered_values[0]
    position = (len(ordered_values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered_values) - 1)
    fraction = position - lower_index
    return ordered_values[lower_index] * (1 - fraction) + ordered_values[upper_index] * fraction


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _trace_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _estimated_tokens_seen(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        total += len(str(row.get("prompt", "")).split())
        selected_text = (
            row.get("selected_response", "")
            or row.get("selected_candidate_text", "")
            or row.get("selected_candidate_index", "")
        )
        total += len(str(selected_text).split())
    return total


def _tokens_per_second(rows: list[dict[str, Any]], duration_ms: float) -> float:
    if duration_ms <= 0.0:
        return 0.0
    return _estimated_tokens_seen(rows) / (duration_ms / 1000.0)
