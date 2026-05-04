# Issue 365 Quantization Lineage Evidence Slice

## Goal

Continue the implementation path for
https://github.com/Keith-CY/melix/issues/365 by tightening the quantization
linkage between CLI requests, calibration datasets, source artifacts, and
`melix.quantized_bundle.v1` release evidence.

Issue 365 is still not complete after this slice. This work only expands the
quantization evidence surface that must exist before full PTQ/QAT acceptance can
claim release readiness.

## Scope

### Included

- Add public `melix quantize` options for:
  - `--quantization-mode`
  - `--source-artifact-kind`
  - `--source-artifact-path`
  - `--calibration-dataset-uri`
  - `--quality-delta`
  - `--latency-delta`
- Forward those options through the Swift CLI runner and command codec.
- Record `source_artifact_path`, `calibration_dataset_uri`, and
  `quantized_artifact_bytes` in quantized bundle manifests.
- Validate optional calibration dataset packages with the existing
  `calibration` dataset contract before writing quantization artifacts.
- Add structured failures for missing adapter-derived QAT source artifacts and
  non-calibration datasets.

### Excluded

- Real PTQ over merged model weights.
- Real QAT optimizer/fake-quant training execution.
- Final local-runtime quantization acceptance.
- Closing issue 365.

## Performance And Metrics

This slice adds one optional dataset manifest read and sample validation when
`--calibration-dataset-uri` is provided. Without that option, quantization keeps
the current deterministic calibration-plan path.

Success metrics:

- CLI parser and runner tests cover the new quantization options.
- Worker tests cover calibration dataset manifest linkage and negative
  validation.
- Changed-scope coverage remains at least 95 percent.

## Verification

Targeted commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_quantization_pipeline.py
swift test --filter MelixCLIParserTests
swift test --filter MelixCLIRunnerTests
git diff --check
```

Coverage and metrics:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_quantization_pipeline.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-quantization-lineage-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-quantization-lineage-coverage.json services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/engine/maintenance_core.py
```

Results on 2026-05-05:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_quantization_pipeline.py`: 72 passed.
- `swift test --filter MelixCLIParserTests`: 63 tests passed.
- `swift test --filter MelixCLIRunnerTests`: 147 tests passed.
- `git diff --check`: passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_quantization_pipeline.py`: 72 passed.
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-quantization-lineage-coverage.json services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/engine/maintenance_core.py`: 100.00% total changed-line coverage (22/22).

## Remaining Issue 365 Gaps

- Full DPO, ORPO, and CPO optimizer loops.
- GRPO candidate generation, scoring, and policy updates.
- RLHF integration with reward-model artifacts from issue 366.
- Real PTQ/QAT local inference release evidence.
- Full CLI chain tests for every business line.
- Window UI controls and acceptance coverage for every business line.
