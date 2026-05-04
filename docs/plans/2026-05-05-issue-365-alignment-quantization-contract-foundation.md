# Issue 365 Alignment And Quantization Contract Foundation

## Goal

Start the implementation path for
https://github.com/Keith-CY/melix/issues/365 by landing the contract foundation
for local alignment runs and quantization release evidence.

Issue 365 is broader than a single implementation slice. This plan covers the
first verifiable slice only: typed dataset contracts, alignment mode validation,
alignment-run manifest linkage, the public `melix alignment train` CLI surface,
and quantization manifest fields needed by later release gates.

## Completion Audit

Issue 365 requires these deliverables:

- alignment modes: DPO, ORPO, CPO, GRPO, and RLHF
- dataset contracts: `preference_pair`, `prompt_candidate`, `reward_scored`,
  and `calibration`
- alignment manifests: `melix.alignment_run.v1` plus adapter manifest backlinking
- quantization manifest fields: `quantization_mode`, `source_artifact_kind`,
  and `release_gate` evidence
- CLI surface: `melix alignment train`
- real trainer paths for DPO, ORPO, CPO, GRPO, and RLHF
- PTQ and QAT-aware quantized export paths
- full CLI chain acceptance with real local runtime evidence
- matching Window UI coverage and release evidence

The current implementation does not yet complete the full issue. This slice
only claims the contract and manifest foundation. Later slices must not mark the
business lines release-ready until they have real trainer and local inference
evidence.

## Scope

### Included

- Add `cpo`, `grpo`, and `rlhf` as typed alignment mode contracts.
- Keep SFT LoRA, QLoRA, and DoRA in `LoRATrainingConfig`.
- Add alignment-specific configuration/state for preference and RL modes.
- Add dataset validation for `prompt_candidate`, `reward_scored`, and
  `calibration` packages.
- Emit `melix.alignment_run.v1` for preference and RL training modes that run
  through the worker training path.
- Backlink adapter manifests to the alignment manifest with
  `alignment_run_manifest_path`.
- Record candidate-group reward margin and variance metrics in alignment
  manifests when prompt-candidate samples include scored candidate groups.
- Return explicit validation errors for malformed scalar alignment arguments and
  null prompt-candidate entries.
- Validate GRPO candidate-count consistency against prompt-candidate samples and
  validate that RLHF reward-model references point to readable JSON manifests.
- Add `melix alignment train` as a distinct CLI command group that forwards
  alignment parameters to the worker operation.
- Extend quantization manifests with `quantization_mode`,
  `source_artifact_kind`, and release-gate evidence fields.
- Add negative validation for unsupported QAT source artifacts.

### Excluded

- Full DPO, ORPO, CPO, GRPO, or RLHF optimizer implementation.
- Reward-model training details owned by issue 366.
- Window UI controls for every business line.
- Real local runtime acceptance for each business line.
- Closing issue 365.

## Implementation Plan

- [x] Add tests for `cpo`, `grpo`, and `rlhf` contract validation.
- [x] Add tests for `prompt_candidate`, `reward_scored`, and `calibration`
  dataset validation.
- [x] Add tests for `melix.alignment_run.v1` manifest creation and adapter
  manifest backlinking.
- [x] Add tests for quantization manifest release-gate fields and unsupported
  QAT source validation.
- [x] Add tests for `melix alignment train` parsing and runner forwarding.
- [x] Implement the worker-side contract, manifest, and quantization changes.
- [x] Implement the CLI parser/runner surface.
- [x] Run targeted Python and Swift tests plus changed-scope metrics.

## Performance And Metrics

This slice adds contract checks and manifest writes before long-running model
work. It should not introduce an additional model execution pass.

Success metrics:

- unsupported alignment/dataset/source-artifact combinations fail before
  runner execution
- alignment manifest writes are bounded to one small JSON file per alignment run
- quantization manifest evidence is populated from request/runtime metadata
  without rescanning bundle artifacts
- targeted changed-scope coverage is at least 95 percent before commit

## Verification

Targeted commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_quantization_pipeline.py
swift test --filter MelixCLIParserTests
swift test --filter MelixCLIRunnerTests
git diff --check
```

Coverage and metrics:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_quantization_pipeline.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python coverage json -o /tmp/issue365-contract-coverage.json
python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/issue365-contract-coverage.json services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/model_ops/training_dataset.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/worker/engine/maintenance_core.py
```

## Implementation Evidence

- Targeted Python regression:
  `126 passed in 2.93s`.
- Coverage run:
  `126 passed in 2.83s`.
- Python changed-line coverage:
  `100.00% (188/188)`.
- CLI parser tests:
  `63 tests` passed.
- CLI runner tests:
  `147 tests` passed.
- `git diff --check`: passed.

## Remaining Issue 365 Gaps

This slice does not close issue 365. The following acceptance items remain:

- full DPO, ORPO, and CPO optimizer loops
- GRPO candidate generation, scoring, and policy updates
- RLHF integration with reward-model artifacts from issue 366
- real PTQ/QAT local inference release evidence
- full CLI chain tests for every business line
- Window UI controls and acceptance coverage for every business line
- real local runtime evidence proving release readiness
