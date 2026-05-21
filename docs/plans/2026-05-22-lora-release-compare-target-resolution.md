# LoRA Release Compare Target Resolution

## Goal

Complete issue #729 by aligning the canonical evaluation contract and operator
runbook with the shipped `melix eval compare --target-adapter` surface. This
surface resolves LoRA adapter package manifest paths into compare targets so a
base model can be compared against adapter-backed targets without first
activating every adapter as a long-lived catalog model.

Parent direction: issue #724, "OpenSearch-VL alignment: gate LoRA release with
paired compare evidence". Milestone direction: issue #728, "automate
base-vs-adapter compare execution".

## Current Shipped Surface

- The Swift CLI accepts repeatable `--target-adapter PATH` values alongside
  repeatable `--target-model-id MODEL_ID` values.
- The CLI serializes adapter targets into
  `compare_target_adapter_manifest_paths`.
- The Python worker validates each `melix.lora_adapter_package.v1` manifest,
  builds an adapter-backed ephemeral compare target from its source model,
  weights path, and adapter set hash, and unloads that target when compare
  execution finishes.
- Compare evidence records target lineage so exported artifacts can identify
  adapter-backed targets.

## Scope

This slice is documentation and contract alignment only:

- update the benchmark/evaluation contract with the adapter-manifest compare
  request field and target-resolution semantics
- update the benchmark/matrix/evaluation/LoRA runbook with operator examples
  for registered model targets and adapter-manifest targets
- keep existing CLI, parser, runner, and worker behavior unchanged

Out of scope:

- adding new persisted artifact fields beyond the shipped target lineage
- adding statistical release-gate verdict enforcement
- changing LoRA training or adapter activation behavior
- changing protobuf schemas

## Performance And Metrics

This path updates documentation for an already shipped control surface and does
not change serving, training, evaluation, or compare execution code.

Measurement points:

- focused Swift CLI parser/runner tests that cover `--target-adapter`
- focused Python compare/worker tests that cover adapter manifest parsing,
  ephemeral target materialization, and cleanup
- `git diff --check`

Success metrics:

- the canonical contract names `compare_target_adapter_manifest_paths`
- the runbook no longer states that compare requires pre-activated target model
  IDs
- focused existing tests continue to pass
- changed-scope coverage is `N/A` because no executable code changes

## Implementation Plan

- [x] Add adapter-manifest target semantics to the canonical benchmark/evaluation contract.
- [x] Update the LoRA comparison runbook with `--target-adapter` examples and rules.
- [x] Run focused Swift and Python tests that already exercise the shipped target-resolution path.
- [x] Run `git diff --check`.

## Verification

- `HOME="$PWD/.swift-home/root-cli" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/root-cli" xcrun swift test --filter "parsesEvalCompareWithAdapterTargets|parsesEvalCompareMixedTargets|evalCompareForwardsAdapterTargetsToSubprocessArgv"`
  - Result: passed; 3 Swift Testing tests selected and passed. Existing test
    warnings were emitted from unrelated runner tests during compilation.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_compare.py services/mlx-worker-python/tests/test_evaluation_core.py -k "adapter_target or compare_target_adapter or load_adapter_target_spec or resolve_compare_target_adapters"`
  - Result: 16 passed, 101 deselected.
- `git diff --check`
  - Result: passed.
- Changed-scope coverage:
  - Result: `N/A`; this slice changes documentation only and does not touch
    executable code.
