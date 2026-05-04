# Issue 365 Offline Preference Trainer Guard

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by preventing preference and RL
alignment modes from silently executing through the supervised MLX-LM LoRA
trainer.

Issue 365 is not complete after this slice. This slice is a release-readiness
guard: it makes the current production backend fail before long-running
execution when a real alignment trainer is not available. Later work must add
the real DPO, ORPO, CPO, GRPO, and RLHF trainer loops before these business
lines can be marked complete.

## Current Backend Finding

The installed local worker dependency is `mlx-lm 0.31.3`. Its public LoRA entry
point supports `fine_tune_type` values `lora`, `dora`, and `full`; it does not
provide DPO, ORPO, CPO, GRPO, or RLHF trainer entry points. Melix therefore must
not route those alignment modes through `mlx_lm.lora.train_model` and claim a
preference/RL run.

## Scope

### Included

- Add a backend capability gate to `MLXLMRunner.train`.
- Fail alignment training modes before native/subprocess MLX-LM execution when
  the runner has no alignment trainer implementation.
- Preserve deterministic/test runners as explicit contract runners so existing
  manifest and CLI contract tests can still exercise alignment payloads without
  claiming production trainer readiness.
- Fix DoRA native routing so supervised DoRA uses MLX-LM `fine_tune_type=dora`
  instead of `lora`.
- Fix serialized training request restoration for nested alignment configs.

### Excluded

- Full DPO, ORPO, or CPO optimizer loops.
- GRPO candidate generation, scoring, or policy updates.
- RLHF reward-model-backed policy optimization from issue 366.
- Real local runtime acceptance for alignment business lines.
- Closing issue 365.

## Performance And Metrics

This slice adds a constant-time mode check before MLX-LM model loading. The
desired performance effect is to avoid expensive model loading when the backend
cannot execute the requested alignment objective.

Success metrics:

- unsupported production alignment runs fail before MLX-LM native/subprocess
  execution
- supervised LoRA, QLoRA, and DoRA keep existing execution behavior
- changed-scope coverage remains at least 95 percent

## Verification

Targeted commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py
git diff --check
```

Coverage and metrics:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-preference-guard-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-preference-guard-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py services/mlx-worker-python/worker/model_ops/deterministic_lora_runner.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_lora_model_ops_unit.py
```

## Implementation Evidence

- Targeted Python regression:
  `119 passed in 3.07s`.
- Coverage run:
  `119 passed in 2.73s`.
- Python changed-line coverage:
  `100.00% (199/199)`.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Full DPO, ORPO, and CPO optimizer loops.
- GRPO candidate generation, scoring, and policy updates.
- RLHF integration with reward-model artifacts from issue 366.
- Real PTQ/QAT local inference release evidence.
- Complete CLI chain tests with real local runtime evidence for every business
  line.
- Window UI runnable/inspectable acceptance with real local runtime evidence
  for every business line.
