# Issue 365 MLX Quantization Convert Slice

## Goal

Continue https://github.com/Keith-CY/melix/issues/365 by adding an opt-in real
MLX-LM weight conversion backend for PTQ quantization jobs.

Issue 365 is still not complete after this slice. Existing quantization slices
recorded lineage, release-gate, QAT-mode, and runtime-smoke evidence, but the
default fast path still writes deterministic structural bundle files. This
slice adds a separate backend that can invoke `mlx_lm.convert(..., quantize=True)`
for local source artifacts while preserving the existing deterministic backend
for fast tests and unsupported environments. It also tightens the QAT-aware
export evidence block so QAT requests preserve adapter-derived source lineage,
fake-quant settings, optional QAT training-manifest lineage, and calibration
lineage.

## Scope

### Included

- Add `quantization_backend=mlx_lm_convert` as an explicit opt-in backend.
- Keep the current deterministic bundle writer as `manifest_only`.
- Validate MLX conversion inputs before long-running conversion starts.
- Reject unsupported QAT requests for the MLX-LM conversion backend because
  `mlx_lm.convert` is a PTQ conversion path, not QAT training.
- Derive MLX-LM quantization parameters from the Melix quantization profile and
  optional explicit ext fields.
- Record `execution_backend` and `real_weight_conversion` in
  `melix.quantized_bundle.v1`.
- Run structural and runtime-generate smoke preflight against the file layout
  emitted by the selected backend.
- Require QAT source artifacts to exist before writing an output bundle.
- Record QAT-aware export metadata in both the quantized bundle manifest and
  the manifest-only weights payload.

### Excluded

- Real QAT training.
- End-to-end release evidence for every issue 365 business line.
- Remote Hugging Face downloads during tests.
- Full CLI chain and Window UI acceptance.

## Performance And Metrics

The default `manifest_only` backend keeps the existing no-rescan hot path. The
new `mlx_lm_convert` backend necessarily walks the converted output directory
once to record artifact bytes because MLX-LM writes the shard set.

Success metrics:

- Existing manifest-only quantization tests remain compatible.
- MLX-LM backend tests prove real-conversion routing with a fake converter.
- Changed-line coverage remains at least 95 percent.

## Verification

Targeted commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-mlx-quantization-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-mlx-quantization-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py docs/plans/2026-05-05-issue-365-mlx-quantization-convert.md
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python python -m compileall -q services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py
git diff --check
```

Results on 2026-05-05:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py`: 52 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py`: 52 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-mlx-quantization-coverage.json`: wrote JSON report.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-mlx-quantization-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py docs/plans/2026-05-05-issue-365-mlx-quantization-convert.md`: 98.55% total changed-line coverage (271/275).
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python python -m compileall -q services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py`: passed.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Real GRPO candidate generation and reward-guided policy update integration.
- RLHF reward-model-backed policy optimization from issue 366.
- Real QAT training.
- Full CLI chain tests with real local runtime evidence for every business
  line.
- Window UI runnable and inspectable acceptance for every business line.
- Final release evidence separating deterministic/unit evidence from real local
  runtime evidence.
