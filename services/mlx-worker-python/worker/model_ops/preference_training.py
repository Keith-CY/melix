from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any

from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_config import LoRATrainingConfig

if TYPE_CHECKING:
    from worker.model_ops.mlx_lm_runner import TrainingRequest, TrainingResult

_mlx_core: Any | None = None


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


@dataclass(frozen=True)
class PreferenceTokenSample:
    chosen_tokens: list[int]
    chosen_offset: int
    rejected_tokens: list[int]
    rejected_offset: int


@dataclass(frozen=True)
class PreferenceMetricSnapshot:
    preference_loss_final: float
    chosen_logprob_mean: float
    rejected_logprob_mean: float
    chosen_rejected_margin: float
    win_rate_proxy: float


class PreferenceTokenDataset:
    def __init__(self, pairs: list[PreferencePair], tokenizer: Any) -> None:
        self._samples = [_tokenize_preference_pair(pair, tokenizer) for pair in pairs]

    def __getitem__(self, idx: int) -> PreferenceTokenSample:
        return self._samples[idx]

    def __len__(self) -> int:
        return len(self._samples)

    def itemlen(self, idx: int) -> int:
        sample = self._samples[idx]
        return max(len(sample.chosen_tokens), len(sample.rejected_tokens))


class PreferenceMetricsCollector:
    def __init__(self) -> None:
        self.losses: list[float] = []
        self.learning_rates: list[float] = []
        self.tokens_seen = 0
        self.examples_seen: int | None = None
        self.tokens_per_second = 0.0

    def on_train_loss_report(self, train_info: dict) -> None:
        if "train_loss" in train_info:
            self.losses.append(float(train_info["train_loss"]))
        if "learning_rate" in train_info:
            self.learning_rates.append(float(train_info["learning_rate"]))
        if "trained_tokens" in train_info:
            self.tokens_seen = int(train_info["trained_tokens"])
        if "trained_examples" in train_info:
            self.examples_seen = int(train_info["trained_examples"])
        elif "examples_seen" in train_info:
            self.examples_seen = int(train_info["examples_seen"])
        if "tokens_per_second" in train_info:
            self.tokens_per_second = float(train_info["tokens_per_second"])

    def on_val_loss_report(self, val_info: dict) -> None:
        if "val_loss" in val_info:
            self.losses.append(float(val_info["val_loss"]))


def load_preference_pairs(dataset_dir: Path) -> list[PreferencePair]:
    path = dataset_dir / "train.jsonl"
    return _load_preference_pairs_file(path)


def train_preference_native(request: TrainingRequest) -> TrainingResult:
    try:
        import mlx.core as mx
        import mlx.optimizers as optim
        from mlx_lm.tuner.trainer import TrainingArgs, train
        from mlx_lm.tuner.utils import (
            build_schedule,
            linear_to_lora_layers,
            print_trainable_parameters,
        )
        from mlx_lm.utils import load, save_config
    except ModuleNotFoundError as exc:
        from worker.model_ops.mlx_lm_runner import NativeExecutionUnavailable

        raise NativeExecutionUnavailable("MLX-LM is not available in the current runtime.") from exc

    from worker.model_ops.mlx_lm_runner import (
        TrainingMetrics,
        TrainingResult,
        _checkpoint_summary,
        _mlx_lora_namespace,
        _mlx_peak_memory_gb,
        _reset_mlx_peak_memory_probe,
    )

    objective = resolve_preference_objective(request.config)
    pairs = load_preference_pairs(request.normalized_dataset_dir)
    args = _mlx_lora_namespace(request)
    args.fine_tune_type = "lora"

    started_at = time.perf_counter()
    request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
    _reset_mlx_peak_memory_probe()
    try:
        mx.random.seed(args.seed)
        model, tokenizer = load(str(request.model_path), lazy=False)
        model.freeze()
        if args.num_layers > len(model.layers):
            raise ValueError(
                f"Requested to train {args.num_layers} layers "
                f"but the model only has {len(model.layers)} layers."
            )
        linear_to_lora_layers(
            model,
            args.num_layers,
            args.lora_parameters,
            use_dora=False,
        )
        if args.resume_adapter_file is not None:
            model.load_weights(args.resume_adapter_file, strict=False)
        print_trainable_parameters(model)

        reference_model = None
        if objective.algorithm == "dpo":
            reference_model_path = (
                request.config.alignment.reference_model_path
                if request.config.alignment is not None
                and request.config.alignment.reference_model_path
                else str(request.model_path)
            )
            reference_model, _ = load(str(reference_model_path), lazy=False)
            reference_model.freeze()
            reference_model.eval()

        adapter_file = request.adapter_output_dir / "adapters.safetensors"
        save_config(vars(args), request.adapter_output_dir / "adapter_config.json")
        dataset = PreferenceTokenDataset(pairs, tokenizer)
        training_args = TrainingArgs(
            batch_size=args.batch_size,
            iters=args.iters,
            val_batches=0,
            steps_per_report=args.steps_per_report,
            steps_per_eval=0,
            steps_per_save=args.save_every,
            adapter_file=adapter_file,
            max_seq_length=args.max_seq_length,
            grad_checkpoint=args.grad_checkpoint,
            grad_accumulation_steps=args.grad_accumulation_steps,
        )
        learning_rate = (
            build_schedule(args.lr_schedule)
            if args.lr_schedule
            else args.learning_rate
        )
        optimizer = optim.Adam(learning_rate=learning_rate)
        collector = PreferenceMetricsCollector()
        preference_loss = make_preference_loss(objective, reference_model=reference_model)
        train(
            model=model,
            args=training_args,
            optimizer=optimizer,
            train_dataset=dataset,
            val_dataset=None,
            loss=preference_loss,
            iterate_batches=iterate_preference_batches,
            training_callback=collector,
        )
        metrics_snapshot = evaluate_preference_metrics(
            model=model,
            dataset=dataset,
            objective=objective,
            batch_size=args.batch_size,
            max_seq_length=args.max_seq_length,
            reference_model=reference_model,
        )
    except ModelOperationError:
        raise
    except Exception as exc:
        raise ModelOperationError(
            code="backend_training_failure",
            message=f"MLX-LM preference training failed: {exc}",
        ) from exc

    duration_ms = (time.perf_counter() - started_at) * 1000.0
    losses = collector.losses or [metrics_snapshot.preference_loss_final]
    learning_rates = collector.learning_rates or [request.config.learning_rate]
    checkpoint_count, latest_checkpoint_path = _checkpoint_summary(request.adapter_output_dir)
    return TrainingResult(
        weights_path=adapter_file,
        adapter_config_path=request.adapter_output_dir / "adapter_config.json",
        metrics=TrainingMetrics(
            job_duration_ms=duration_ms,
            tokens_seen=collector.tokens_seen,
            examples_seen=_preference_examples_seen(
                collector=collector,
                config=request.config,
            ),
            loss_final=losses[-1],
            loss_best=min(losses),
            learning_rate_final=learning_rates[-1],
            checkpoint_count=checkpoint_count,
            resume_ready=latest_checkpoint_path != "",
            latest_checkpoint_path=latest_checkpoint_path,
            resume_source_path=(
                str(request.resume_source_path)
                if request.resume_source_path is not None
                else ""
            ),
            tokens_per_second=collector.tokens_per_second,
            peak_memory_gb=_mlx_peak_memory_gb(),
            preference_loss_final=metrics_snapshot.preference_loss_final,
            chosen_logprob_mean=metrics_snapshot.chosen_logprob_mean,
            rejected_logprob_mean=metrics_snapshot.rejected_logprob_mean,
            chosen_rejected_margin=metrics_snapshot.chosen_rejected_margin,
            win_rate_proxy=metrics_snapshot.win_rate_proxy,
        ),
        execution_backend="native",
    )


def make_preference_loss(
    objective: PreferenceObjectiveConfig,
    *,
    reference_model: Any = None,
) -> Any:
    def preference_loss(
        model: Any,
        chosen_batch: Any,
        chosen_lengths: Any,
        rejected_batch: Any,
        rejected_lengths: Any,
    ) -> tuple[Any, Any]:
        loss_values, token_count, _, _ = preference_loss_components(
            model=model,
            chosen_batch=chosen_batch,
            chosen_lengths=chosen_lengths,
            rejected_batch=rejected_batch,
            rejected_lengths=rejected_lengths,
            objective=objective,
            reference_model=reference_model,
        )
        return loss_values.astype(_mx().float32).mean(), token_count

    return preference_loss


def preference_loss_components(
    *,
    model: Any,
    chosen_batch: Any,
    chosen_lengths: Any,
    rejected_batch: Any,
    rejected_lengths: Any,
    objective: PreferenceObjectiveConfig,
    reference_model: Any = None,
) -> tuple[Any, Any, Any, Any]:
    mx = _mx()
    chosen_logprob, chosen_token_count, chosen_nll = sequence_logprobs(
        model,
        chosen_batch,
        chosen_lengths,
    )
    rejected_logprob, rejected_token_count, _ = sequence_logprobs(
        model,
        rejected_batch,
        rejected_lengths,
    )
    policy_margin = chosen_logprob - rejected_logprob
    token_count = chosen_token_count.sum() + rejected_token_count.sum()
    if objective.algorithm == "dpo":
        if reference_model is None:
            raise ModelOperationError(
                code="invalid_alignment_config",
                message="DPO preference training requires a reference model.",
            )
        reference_chosen_logprob, _, _ = sequence_logprobs(
            reference_model,
            chosen_batch,
            chosen_lengths,
        )
        reference_rejected_logprob, _, _ = sequence_logprobs(
            reference_model,
            rejected_batch,
            rejected_lengths,
        )
        reference_margin = reference_chosen_logprob - reference_rejected_logprob
        loss_values = -_mlx_log_sigmoid(
            objective.beta * (policy_margin - reference_margin)
        )
    elif objective.algorithm == "orpo":
        loss_values = chosen_nll - objective.beta * _mlx_log_sigmoid(policy_margin)
    elif objective.algorithm == "cpo":
        loss_values = -_mlx_log_sigmoid(
            objective.beta * (policy_margin - objective.margin_target)
        )
    else:
        raise ModelOperationError(
            code="unsupported_alignment_trainer",
            message=f"Unsupported offline preference algorithm: {objective.algorithm}",
            details={"alignment_algorithm": objective.algorithm},
        )
    return loss_values, token_count.astype(mx.float32), chosen_logprob, rejected_logprob


def sequence_logprobs(model: Any, batch: Any, lengths: Any) -> tuple[Any, Any, Any]:
    mx = _mx()
    inputs = batch[:, :-1]
    targets = batch[:, 1:]
    logits = model(inputs)
    if isinstance(logits, tuple):
        logits = logits[0]
    logits = logits.astype(mx.float32)
    log_probs = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
    token_logprobs = mx.take_along_axis(
        log_probs,
        targets[..., None],
        axis=-1,
    ).squeeze(-1)
    steps = mx.arange(1, targets.shape[1] + 1)
    mask = mx.logical_and(steps >= lengths[:, 0:1], steps <= lengths[:, 1:])
    mask = mask.astype(mx.float32)
    token_count = mask.sum(axis=1)
    safe_token_count = mx.maximum(token_count, mx.ones_like(token_count))
    sequence_logprob = (token_logprobs * mask).sum(axis=1)
    chosen_nll = -sequence_logprob / safe_token_count
    return sequence_logprob, safe_token_count, chosen_nll


def evaluate_preference_metrics(
    *,
    model: Any,
    dataset: PreferenceTokenDataset,
    objective: PreferenceObjectiveConfig,
    batch_size: int,
    max_seq_length: int,
    reference_model: Any = None,
) -> PreferenceMetricSnapshot:
    losses: list[float] = []
    chosen_logprobs: list[float] = []
    rejected_logprobs: list[float] = []
    for batch in iterate_preference_batches(
        dataset=dataset,
        batch_size=batch_size,
        max_seq_length=max_seq_length,
        loop=False,
    ):
        loss_values, _, chosen_logprob, rejected_logprob = preference_loss_components(
            model=model,
            chosen_batch=batch[0],
            chosen_lengths=batch[1],
            rejected_batch=batch[2],
            rejected_lengths=batch[3],
            objective=objective,
            reference_model=reference_model,
        )
        losses.extend(_array_to_float_list(loss_values))
        chosen_logprobs.extend(_array_to_float_list(chosen_logprob))
        rejected_logprobs.extend(_array_to_float_list(rejected_logprob))
    if not losses:
        raise ModelOperationError(
            code="invalid_dataset_package",
            message="preference_pair training requires at least one full batch.",
            details={
                "batch_size": str(batch_size),
                "sample_count": str(len(dataset)),
            },
        )
    margins = [
        chosen - rejected
        for chosen, rejected in zip(chosen_logprobs, rejected_logprobs)
    ]
    wins = [1.0 if margin > 0.0 else 0.0 for margin in margins]
    return PreferenceMetricSnapshot(
        preference_loss_final=sum(losses) / len(losses),
        chosen_logprob_mean=sum(chosen_logprobs) / len(chosen_logprobs),
        rejected_logprob_mean=sum(rejected_logprobs) / len(rejected_logprobs),
        chosen_rejected_margin=sum(margins) / len(margins),
        win_rate_proxy=sum(wins) / len(wins),
    )


def iterate_preference_batches(
    dataset: PreferenceTokenDataset,
    batch_size: int,
    max_seq_length: int,
    loop: bool = False,
    seed: int | None = None,
    comm_group: Any = None,
) -> Iterator[tuple[Any, Any, Any, Any]]:
    import numpy as np

    mx = _mx()
    if len(dataset) < batch_size:
        raise ValueError(
            f"Dataset must have at least batch_size={batch_size} examples "
            f"but only has {len(dataset)}."
        )
    if comm_group is not None:
        raise NotImplementedError(
            "Distributed preference batch sharding is deferred until GRPO support lands."
        )
    idx = sorted(range(len(dataset)), key=dataset.itemlen)
    batch_idx = [
        idx[i: i + batch_size]
        for i in range(0, len(idx) - batch_size + 1, batch_size)
    ]
    if seed is not None:
        np.random.seed(seed)
    while True:
        indices = np.random.permutation(len(batch_idx))
        for batch_index in indices:
            samples = [dataset[j] for j in batch_idx[batch_index]]
            max_length = max(
                max(len(sample.chosen_tokens), len(sample.rejected_tokens))
                for sample in samples
            )
            pad_to = 32
            max_length_in_batch = 1 + pad_to * ((max_length + pad_to - 1) // pad_to)
            max_length_in_batch = min(max_length_in_batch, max_seq_length)
            chosen_batch, chosen_lengths = _pad_preference_side(
                samples,
                side="chosen",
                max_length=max_length_in_batch,
            )
            rejected_batch, rejected_lengths = _pad_preference_side(
                samples,
                side="rejected",
                max_length=max_length_in_batch,
            )
            yield (
                mx.array(chosen_batch),
                mx.array(chosen_lengths),
                mx.array(rejected_batch),
                mx.array(rejected_lengths),
            )
        if not loop:
            break


def _load_preference_pairs_file(path: Path) -> list[PreferencePair]:
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


def _tokenize_preference_pair(pair: PreferencePair, tokenizer: Any) -> PreferenceTokenSample:
    chosen_tokens, chosen_offset = _tokenize_prompt_response(
        tokenizer,
        prompt=pair.prompt,
        response=pair.chosen,
    )
    rejected_tokens, rejected_offset = _tokenize_prompt_response(
        tokenizer,
        prompt=pair.prompt,
        response=pair.rejected,
    )
    return PreferenceTokenSample(
        chosen_tokens=chosen_tokens,
        chosen_offset=chosen_offset,
        rejected_tokens=rejected_tokens,
        rejected_offset=rejected_offset,
    )


def _tokenize_prompt_response(
    tokenizer: Any,
    *,
    prompt: str,
    response: str,
) -> tuple[list[int], int]:
    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_chat_template):
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ]
        try:
            tokens = list(apply_chat_template(messages, return_dict=False))
            prefix_tokens = list(
                apply_chat_template(
                    messages[:-1],
                    add_generation_prompt=True,
                    return_dict=False,
                )
            )
            tokens = _append_eos_if_needed(tokens, tokenizer)
            return tokens, min(len(prefix_tokens), max(len(tokens) - 1, 0))
        except (TypeError, ValueError, AttributeError):
            pass

    prompt_tokens = _encode_text(tokenizer, prompt)
    response_tokens = _encode_text(tokenizer, response)
    tokens = _append_eos_if_needed([*prompt_tokens, *response_tokens], tokenizer)
    return tokens, min(len(prompt_tokens), max(len(tokens) - 1, 0))


def _encode_text(tokenizer: Any, text: str) -> list[int]:
    try:
        return list(tokenizer.encode(text, add_special_tokens=False))
    except TypeError:
        return list(tokenizer.encode(text))


def _append_eos_if_needed(tokens: list[int], tokenizer: Any) -> list[int]:
    eos_token_id = getattr(tokenizer, "eos_token_id", None)
    if eos_token_id is None or (tokens and tokens[-1] == eos_token_id):
        return tokens
    return [*tokens, int(eos_token_id)]


def _pad_preference_side(
    samples: list[PreferenceTokenSample],
    *,
    side: str,
    max_length: int,
) -> tuple[Any, list[tuple[int, int]]]:
    import numpy as np

    batch = np.zeros((len(samples), max_length), np.int32)
    lengths: list[tuple[int, int]] = []
    for row, sample in enumerate(samples):
        tokens = sample.chosen_tokens if side == "chosen" else sample.rejected_tokens
        offset = sample.chosen_offset if side == "chosen" else sample.rejected_offset
        truncated_length = min(len(tokens), max_length)
        batch[row, :truncated_length] = tokens[:truncated_length]
        safe_offset = min(offset, max(truncated_length - 1, 0))
        lengths.append((safe_offset, truncated_length))
    return batch, lengths


def _mlx_log_sigmoid(value: Any) -> Any:
    mx = _mx()
    return -mx.logaddexp(mx.zeros_like(value), -value)


def _array_to_float_list(value: Any) -> list[float]:
    import numpy as np

    return [float(item) for item in np.array(value).reshape(-1).tolist()]


def _mx() -> Any:
    global _mlx_core
    if _mlx_core is None:
        import mlx.core as mx

        _mlx_core = mx
    return _mlx_core


def _preference_examples_seen(
    *,
    collector: PreferenceMetricsCollector,
    config: LoRATrainingConfig,
) -> int:
    if collector.examples_seen is not None:
        return collector.examples_seen
    # MLX-LM preference callbacks reliably expose trained_tokens, but not row
    # counts. Keep examples_seen as configured sample-visits until that callback
    # adds an actual examples counter.
    return config.batch_size * config.iters
