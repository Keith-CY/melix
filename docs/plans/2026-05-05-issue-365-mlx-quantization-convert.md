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
lineage. A follow-up extension in this branch adds a deterministic Melix
fake-quant optimizer execution path for QAT requests: it reads the
adapter-derived source artifact, computes fake-quant error proxies, writes a
QAT training trace and manifest, and links those artifacts from the quantized
bundle manifest.

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
- Run a deterministic Melix fake-quant optimizer for QAT requests and record the
  generated QAT training trace, training manifest, fake-quant artifact, source
  digest, optimizer metrics, and optional source training-manifest lineage.
- Record QAT fake-quant training metadata in both the quantized bundle manifest
  and the manifest-only weights payload.

### Excluded

- MLX-native QAT training over full model tensors.
- End-to-end release evidence for every issue 365 business line.
- Remote Hugging Face downloads during tests.
- Full CLI chain and Window UI acceptance.

## Performance And Metrics

The default `manifest_only` backend keeps the existing no-rescan hot path. The
new `mlx_lm_convert` backend necessarily walks the converted output directory
once to record artifact bytes because MLX-LM writes the shard set. The QAT
fake-quant optimizer walks the adapter-derived source artifact once, streams
source bytes to compute a digest and fake-quant error proxies, and writes a
small trace/manifest/artifact bundle.

Success metrics:

- Existing manifest-only quantization tests remain compatible.
- MLX-LM backend tests prove real-conversion routing with a fake converter.
- QAT tests prove fake-quant optimizer execution artifacts and metrics are
  written and linked from `melix.quantized_bundle.v1`.
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

Results on 2026-05-06 after QAT fake-quant optimizer extension:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py`: 53 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py`: 53 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="/Users/ChenYu/Documents/Github/melix/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-mlx-quantization-coverage.json`: wrote JSON report.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-mlx-quantization-coverage.json --diff-from origin/main services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py docs/plans/2026-05-05-issue-365-mlx-quantization-convert.md`: 97.35% total changed-line coverage (404/415).
- `python3 -m compileall -q services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py`: passed.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

- Real GRPO candidate generation and reward-guided policy update integration.
- RLHF reward-model-backed policy optimization from issue 366.
- MLX-native QAT training over full model tensors and real local-runtime release
  evidence for QAT artifacts.
- Full CLI chain tests with real local runtime evidence for every business
  line.
- Window UI runnable and inspectable acceptance for every business line.
- Final release evidence separating deterministic/unit evidence from real local
  runtime evidence.
