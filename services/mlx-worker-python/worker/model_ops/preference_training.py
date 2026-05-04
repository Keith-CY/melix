from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_config import LoRATrainingConfig


@dataclass(frozen=True)
class PreferencePair:
    prompt: str
    chosen: str
    rejected: str


@dataclass(frozen=True)
class PreferenceObjectiveConfig:
    algorithm: str
    beta: float
    margin_target: float = 0.0


def load_preference_pairs(dataset_dir: Path) -> list[PreferencePair]:
    path = dataset_dir / "train.jsonl"
    pairs: list[PreferencePair] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                sample = json.loads(line)
                try:
                    pairs.append(
                        PreferencePair(
                            prompt=str(sample["prompt"]),
                            chosen=str(sample["chosen"]),
                            rejected=str(sample["rejected"]),
                        )
                    )
                except KeyError as exc:
                    raise ModelOperationError(
                        code="invalid_dataset_package",
                        message="preference_pair training rows must include prompt, chosen, and rejected.",
                        details={
                            "line_number": str(line_number),
                            "missing_field": str(exc.args[0]),
                        },
                    ) from exc
    except FileNotFoundError as exc:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="preference_pair training requires train.jsonl.",
            details={"path": str(path)},
        ) from exc

    if not pairs:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="preference_pair training requires at least one training pair.",
        )
    return pairs


def resolve_preference_objective(config: LoRATrainingConfig) -> PreferenceObjectiveConfig:
    if config.alignment is None:
        raise ModelOperationError(
            code="invalid_alignment_config",
            message="preference training requires alignment config.",
        )
    beta = config.alignment.kl_penalty if config.alignment.kl_penalty > 0 else 0.1
    return PreferenceObjectiveConfig(
        algorithm=config.alignment.alignment_algorithm,
        beta=beta,
        margin_target=config.alignment.preference_margin_target,
    )


def dpo_loss_value(policy_margin: float, reference_margin: float, beta: float) -> float:
    return -_log_sigmoid(beta * (policy_margin - reference_margin))


def orpo_loss_value(chosen_nll: float, policy_margin: float, beta: float) -> float:
    return chosen_nll - beta * _log_sigmoid(policy_margin)


def cpo_loss_value(policy_margin: float, beta: float, margin_target: float) -> float:
    return -_log_sigmoid(beta * (policy_margin - margin_target))


def _log_sigmoid(value: float) -> float:
    if value >= 0:
        return -math.log1p(math.exp(-value))
    return value - math.log1p(math.exp(value))
