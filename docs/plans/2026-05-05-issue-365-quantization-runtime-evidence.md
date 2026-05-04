# Issue 365 Quantization Runtime Evidence Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by replacing the quantized bundle
smoke-test boolean with typed local smoke evidence in
`melix.quantized_bundle.v1` manifests.

Issue 365 is still not complete after this slice. This work makes release-gate
evidence auditable and adds an opt-in local runtime generate probe, but it does
not implement real PTQ/QAT weight conversion or final local-runtime acceptance.

## Scope

### Included

- Add a `local_inference_smoke` manifest block for quantized bundles.
- Keep `release_gate.local_inference_smoke_result` derived from typed smoke
  evidence instead of a loose boolean.
- Preserve the current default structural bundle smoke mode for fast unit and
  deterministic release-gate checks.
- Add an opt-in `runtime_generate` smoke mode that loads the produced bundle
  through the worker runtime, renders a short prompt, requests one generated
  token, records latency and token-count evidence, and unloads the model.
- Record failure evidence for missing structural files and runtime smoke
  failures.
- Do not add or preserve screenshot artifacts as evidence for this slice.

### Excluded

- Real PTQ over merged model weights.
- Real QAT optimizer or fake-quant training execution.
- Final local-runtime quantization acceptance.
- Window UI screenshot evidence.
- Closing issue 365.

## Performance And Metrics

The default `structural` smoke mode keeps the existing cheap artifact check.
The opt-in `runtime_generate` mode intentionally adds one model load, one short
prompt render, one-token generation, and unload when operators request runtime
evidence.

Success metrics:

- Quantized bundle manifests include typed smoke evidence for requested and
  non-requested paths.
- Runtime-generate smoke evidence records status, evidence kind, latency, prompt
  hash, generated token count, runtime, and checked artifact files.
- Failure paths preserve structured evidence instead of only flipping a boolean.
- Changed-scope coverage remains at least 95 percent.

## Verification

Targeted commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_training_dataset_builder.py
git diff --check
```

Coverage and metrics:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_training_dataset_builder.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-quantization-runtime-evidence-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-quantization-runtime-evidence-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py docs/plans/2026-05-05-issue-365-quantization-runtime-evidence.md
```

Results on 2026-05-05:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 87 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_training_dataset_builder.py`: 87 passed.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-quantization-runtime-evidence-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py docs/plans/2026-05-05-issue-365-quantization-runtime-evidence.md`: 99.50% total changed-line coverage (198/199).
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python python -m compileall -q services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py`: passed.
- `git diff --check`: passed.
- Screenshot artifacts: none added or retained for this slice; only existing tracked product resources and evaluation fixtures were present.

## Remaining Issue 365 Gaps

- GRPO candidate generation, scoring, and policy updates.
- RLHF reward-model-backed policy optimization from issue 366.
- Real PTQ/QAT local inference release evidence.
- Full CLI chain tests for every business line.
- Window UI runnable and inspectable acceptance for every business line.
- Final release evidence separating deterministic/unit evidence from real local
  runtime evidence.
