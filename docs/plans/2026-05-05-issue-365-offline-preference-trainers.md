# Issue 365 Offline Preference Trainers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first real local DPO, ORPO, and CPO trainer execution
paths for Issue 365 instead of manifest-only alignment placeholders.

**Architecture:** Keep supervised LoRA/QLoRA/DoRA execution in
`MLXLMRunner.train_native` through `mlx_lm.lora.train_model`, and add a
separate worker-side preference trainer module for `preference_pair` datasets.
The preference trainer uses MLX-LM's lower-level tuner primitives with
algorithm-specific loss functions, writes normal adapter weights/config, and
returns objective-specific metrics that the alignment manifest records.

**Tech Stack:** Python worker, MLX/MLX-LM 0.31.x tuner primitives,
`pytest`, `coverage`, `scripts/python_changed_line_coverage.py`.

---

## Completion Boundary

This plan does not complete all #365 acceptance criteria. It covers only Slice
2: offline DPO, ORPO, and CPO trainer execution. GRPO, RLHF/#366, PTQ/QAT real
local inference evidence, full CLI chain acceptance, and Window real-runtime
acceptance remain separate Issue 365 slices.

## Files

- Create: `services/mlx-worker-python/worker/model_ops/preference_training.py`
  - Owns preference-pair tokenization, batching, losses, MLX-LM trainer wiring,
    adapter config writing, and preference metrics.
- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
  - Routes `training_objective=preference` to the new preference trainer and
    keeps `alignment_rl` guarded until GRPO/RLHF are implemented.
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
  - Copies preference trainer metrics into `melix.alignment_run.v1`.
- Modify: `services/mlx-worker-python/worker/model_ops/deterministic_lora_runner.py`
  - Keeps deterministic contract behavior explicit for tests.
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
  - Adds pure unit coverage for preference dataset parsing, serialization, and
    runner routing.
- Modify: `services/mlx-worker-python/tests/test_lora_model_ops.py`
  - Adds worker pipeline assertions for real preference metrics in manifests.
- Modify: `docs/plans/2026-05-05-issue-365-offline-preference-trainers.md`
  - Records implementation evidence and remaining gaps.

## Algorithm Contracts

- DPO loss:
  `-log_sigmoid(beta * ((logp_chosen - logp_rejected) - (logp_ref_chosen - logp_ref_rejected)))`
- ORPO loss:
  `chosen_nll + beta * -log_sigmoid(logp_chosen - logp_rejected)`
- CPO loss:
  `-log_sigmoid(beta * ((logp_chosen - logp_rejected) - margin_target))`

Use `alignment.kl_penalty` as `beta` when it is greater than zero; otherwise use
`0.1`. Use `preference_margin_target` from request ext when present; otherwise
use `0.0` for CPO. DPO loads `reference_model_path` when provided, otherwise it
uses a frozen base-model reference loaded from the same source model path.

## Task 1: Preference Metrics Shape

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`

- [x] **Step 1: Write the failing metrics serialization test**

Add this test near the existing training request serialization tests:

```python
def test_training_metrics_serializes_preference_fields(tmp_path: Path) -> None:
    metrics = mlx_lm_runner_module.TrainingMetrics(
        job_duration_ms=10.0,
        tokens_seen=4,
        examples_seen=2,
        loss_final=0.4,
        loss_best=0.3,
        learning_rate_final=1e-4,
        preference_loss_final=0.2,
        chosen_logprob_mean=-1.5,
        rejected_logprob_mean=-2.0,
        chosen_rejected_margin=0.5,
        win_rate_proxy=1.0,
    )
    result = mlx_lm_runner_module.TrainingResult(
        weights_path=tmp_path / "adapters.safetensors",
        adapter_config_path=tmp_path / "adapter_config.json",
        metrics=metrics,
        execution_backend="native",
    )

    restored = mlx_lm_runner_module._deserialize_training_result(
        mlx_lm_runner_module._serialize_training_result(result)
    )

    assert restored.metrics.preference_loss_final == pytest.approx(0.2)
    assert restored.metrics.chosen_logprob_mean == pytest.approx(-1.5)
    assert restored.metrics.rejected_logprob_mean == pytest.approx(-2.0)
    assert restored.metrics.chosen_rejected_margin == pytest.approx(0.5)
    assert restored.metrics.win_rate_proxy == pytest.approx(1.0)
```

- [x] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_training_metrics_serializes_preference_fields
```

Expected: fails with `TypeError` for unknown `TrainingMetrics` keyword.

- [x] **Step 3: Add metrics fields**

Add these defaulted fields to `TrainingMetrics`:

```python
    preference_loss_final: float | None = None
    chosen_logprob_mean: float | None = None
    rejected_logprob_mean: float | None = None
    chosen_rejected_margin: float | None = None
    win_rate_proxy: float | None = None
```

- [x] **Step 4: Verify the test passes**

Run the same pytest command. Expected: `1 passed`.

## Task 2: Preference Trainer Module

**Files:**

- Create: `services/mlx-worker-python/worker/model_ops/preference_training.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`

- [x] **Step 1: Write failing unit tests for dataset loading and objective config**

Add tests that create `train.jsonl` with `prompt/chosen/rejected`, call
`load_preference_pairs(...)`, and assert:

```python
assert pairs[0].prompt == "Choose."
assert pairs[0].chosen == "Helpful."
assert pairs[0].rejected == "Unsafe."
assert resolve_preference_beta(config) == pytest.approx(0.1)
```

Also add a CPO request with `preference_margin_target="0.25"` and assert the
resolved margin is `0.25`.

- [x] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'preference_pairs or preference_beta'
```

Expected: import failure because `preference_training.py` does not exist.

- [x] **Step 3: Implement the module skeleton**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
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
                    details={"line_number": str(line_number), "missing_field": str(exc.args[0])},
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
        margin_target=0.0,
    )
```

- [x] **Step 4: Verify skeleton tests pass**

Run the same pytest command. Expected: targeted tests pass.

## Task 3: Native Preference Trainer Routing

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- Modify: `services/mlx-worker-python/worker/model_ops/preference_training.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`

- [x] **Step 1: Write failing routing test**

Add a test that monkeypatches `preference_training.train_preference_native` to
write adapter files and return metrics. Assert `MLXLMRunner().train(...)` for
`training_mode=dpo` returns `execution_backend="native"` and does not raise
`unsupported_alignment_trainer`.

- [x] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py::test_mlx_lm_runner_routes_preference_training_to_preference_backend
```

Expected: fails with `unsupported_alignment_trainer`.

- [x] **Step 3: Implement routing**

In `MLXLMRunner.supports_alignment_training`, return true only for
`training_objective == "preference"`. Keep `alignment_rl` guarded.

In `MLXLMRunner.train_native`, before supervised MLX-LM dataset loading:

```python
if request.config.training_objective == "preference":
    from worker.model_ops.preference_training import train_preference_native

    return train_preference_native(request)
```

- [x] **Step 4: Verify routing test passes**

Run the same pytest command. Expected: `1 passed`.

## Task 4: MLX Preference Loss Implementation

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/preference_training.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`

- [x] **Step 1: Add pure loss tests with fake arrays**

Add tests for `dpo_loss_values`, `orpo_loss_values`, and `cpo_loss_values`
using small numeric margins. Assert chosen margins lower the loss and rejected
margins raise it.

- [x] **Step 2: Run failing loss tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py -k 'dpo_loss_values or orpo_loss_values or cpo_loss_values'
```

Expected: fails because loss helpers do not exist.

- [x] **Step 3: Implement stable scalar helpers**

Implement scalar helpers first so behavior is testable without MLX:

```python
import math


def _log_sigmoid(value: float) -> float:
    if value >= 0:
        return -math.log1p(math.exp(-value))
    return value - math.log1p(math.exp(value))


def dpo_loss_value(policy_margin: float, reference_margin: float, beta: float) -> float:
    return -_log_sigmoid(beta * (policy_margin - reference_margin))


def orpo_loss_value(chosen_nll: float, policy_margin: float, beta: float) -> float:
    return chosen_nll - beta * _log_sigmoid(policy_margin)


def cpo_loss_value(policy_margin: float, beta: float, margin_target: float) -> float:
    return -_log_sigmoid(beta * (policy_margin - margin_target))
```

- [x] **Step 4: Implement MLX loss closure**

Add MLX equivalents that compute chosen/rejected sequence logprobs from model
logits and select DPO/ORPO/CPO based on `PreferenceObjectiveConfig.algorithm`.
The loss closure must return `(loss, token_count)` in the shape expected by
`mlx_lm.tuner.trainer.train`.

- [x] **Step 5: Verify tests pass**

Run the same pytest command. Expected: loss tests pass.

## Task 5: Adapter Output And Metrics

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/preference_training.py`
- Modify: `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- Test: `services/mlx-worker-python/tests/test_lora_model_ops.py`

- [x] **Step 1: Write failing manifest metrics test**

Extend the existing DPO/ORPO/CPO parametrized pipeline test to assert:

```python
assert alignment_payload["metrics"]["preference_loss_final"] == pytest.approx(0.2)
assert alignment_payload["metrics"]["chosen_logprob_mean"] == pytest.approx(-1.5)
assert alignment_payload["metrics"]["rejected_logprob_mean"] == pytest.approx(-2.0)
assert alignment_payload["metrics"]["chosen_rejected_margin"] == pytest.approx(0.5)
assert alignment_payload["metrics"]["win_rate_proxy"] == pytest.approx(1.0)
```

- [x] **Step 2: Run failing pipeline test**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py::test_train_lora_supports_preference_mode_contracts
```

Expected: fails because metrics are not copied into alignment manifest.

- [x] **Step 3: Copy metrics into alignment manifest**

In `_alignment_manifest_payload`, when `dataset_contract == "preference_pair"`,
populate preference metrics from `training_result.metrics` instead of static
zero defaults. Keep the config-time loss selector under
`preference_loss_config` so manifest consumers can distinguish the requested
objective from the observed `preference_loss_final` scalar.

- [x] **Step 4: Verify pipeline test passes**

Run the same pytest command. Expected: `3 passed`.

## Task 6: Verification And Evidence

**Files:**

- Modify: `docs/plans/2026-05-05-issue-365-offline-preference-trainers.md`

- [x] **Step 1: Run focused regression**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_lora_model_ops.py
```

Expected: all tests pass.

- [x] **Step 2: Run coverage**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops_unit.py services/mlx-worker-python/tests/test_lora_model_ops.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-offline-preference-trainers-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-offline-preference-trainers-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/preference_training.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py
```

Expected: changed-line coverage is at least `95.00%`.

- [x] **Step 3: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [x] **Step 4: Update implementation evidence**

Append the exact command outcomes under a new `## Implementation Evidence`
section in this plan.

## Implementation Evidence

- Baseline in isolated worktree before this slice:
  `119 passed in 4.01s`.
- Failing metrics serialization test:
  failed with `TrainingMetrics.__init__() got an unexpected keyword argument
  'preference_loss_final'`.
- Targeted metrics serialization test after implementation:
  `1 passed in 0.05s`.
- Failing manifest metrics test:
  failed with missing `preference_loss_final` in alignment manifest metrics.
- Targeted metrics and manifest tests after implementation:
  `4 passed in 0.38s`.
- Failing preference module tests:
  failed with `ModuleNotFoundError: No module named
  'worker.model_ops.preference_training'`.
- Targeted preference module tests after implementation:
  `6 passed, 55 deselected in 0.11s`.
- CPO margin-target config test:
  `2 passed in 0.10s`.
- Focused Python regression:
  `128 passed in 2.49s`.
- Coverage run:
  `128 passed in 2.39s`.
- Python changed-line coverage:
  `100.00% (464/464)`.
- `git diff --check`: passed.
- Failing preference routing test:
  failed because `worker.model_ops.preference_training` had no
  `train_preference_native` entry point.
- Targeted preference routing and alignment-RL guard tests after implementation:
  `2 passed in 0.05s`.
- Targeted MLX preference loss and objective metrics tests:
  `4 passed, 64 deselected in 1.60s`.
- Native preference trainer wiring test with patched MLX-LM trainer:
  `1 passed, 2 warnings in 0.86s`.
- Focused Python regression after native preference trainer routing:
  `139 passed, 2 warnings in 3.13s`.
- Coverage run after native preference trainer routing:
  `139 passed, 2 warnings in 3.44s`.
- Python changed-line coverage after native preference trainer routing:
  `97.21% (557/573)` after refreshing `origin/main` to include merged
  PR #368.
- `git diff --check` after native preference trainer routing: passed.
- PR #369 review follow-up targeted tests:
  `8 passed, 2 warnings in 1.18s`.
- Focused Python regression after PR #369 review follow-up:
  `142 passed, 2 warnings in 3.49s`.
- Coverage run after PR #369 review follow-up:
  `142 passed, 2 warnings in 4.03s`.
- Python changed-line coverage after PR #369 review follow-up:
  `97.88% (600/613)`.
- `git diff --check` after PR #369 review follow-up: passed.

## Remaining Issue 365 Gaps After This Plan

- GRPO candidate generation, scoring, and policy updates.
- RLHF reward-model-backed policy optimization from #366.
- PTQ/QAT real local inference and quality/latency/size gate evidence.
- Complete CLI chain tests with real local runtime evidence for every business
  line.
- Window UI runnable/inspectable acceptance with real local runtime evidence
  for every business line.
