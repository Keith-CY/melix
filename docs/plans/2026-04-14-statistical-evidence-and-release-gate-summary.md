# Statistical Evidence And Release-Gate Summary

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Use superpowers:using-git-worktrees before editing code. Use
> superpowers:test-driven-development for every behavior change.

**Goal:** Close the Statistical Evidence and release-summary gaps in Melix evaluation comparison so
paired compare runs can emit category-aware evidence, paired confidence intervals, and
release-friendly verdicts that the Phase 8 release gate can consume directly.

**Architecture:** Keep Python worker productization as scoring and statistical truth, then extend
shared export and presentation seams so the same persisted compare bundle feeds the release gate,
control-plane export bundle, CLI output, and Window UI state. Preserve existing comparison fields
such as `delta_accuracy`, `win_count`, and `regression_count`; add statistical evidence as a
backward-compatible extension instead of replacing the current compare schema.

**Tech Stack:** Python, Swift, SwiftUI, pytest, Swift Testing, repository-owned JSON/CSV/Markdown
artifacts, existing Phase 8 release-gate policy JSON.

**Statistical Defaults**

- Paired bootstrap interval: `95%` confidence, deterministic seed, fixed bootstrap iteration count
  owned by policy and persisted in compare output.
- Analytical interval: paired-difference normal approximation over correctness deltas with the same
  confidence level, emitted alongside bootstrap evidence.
- Release verdict: `improvement`, `regression`, or `inconclusive`.
- Verdict rule: only emit `improvement` or `regression` when observed delta clears the configured
  minimum effect threshold and both interval families land on the same side of zero. Otherwise emit
  `inconclusive`.
- Category or subject breakdown: emit only when dataset samples carry stable category metadata.

## File Scope

### Worker and productization

- Add: `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_compare.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_reports.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_schemas.py`
- Modify: `services/mlx-worker-python/worker/productization/evaluation_store.py`
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Modify: `services/mlx-worker-python/worker/productization/release_gates.py`

### Worker tests

- Modify: `services/mlx-worker-python/tests/test_evaluation_schemas.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_store.py`
- Modify: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Modify: `services/mlx-worker-python/tests/test_benchmark_export.py`
- Modify: `services/mlx-worker-python/tests/test_release_gates.py`
- Add: `services/mlx-worker-python/tests/test_statistical_evidence.py`

### Swift and operator surfaces

- Modify: `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`
- Modify: `Sources/MelixCLICore/MelixCLI.swift`
- Modify: `Tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Modify: `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`
- Modify: `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`

### Docs and policy

- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/runbooks/benchmark-matrix-evaluation-and-lora.md`
- Modify: `docs/runbooks/phase-8-release-gates.md`
- Modify: `infra/release/phase8-release-gate-policy.json`

## Task 1: Extend Comparison Schema And Statistical Core

- [ ] Add a worker-owned statistical helper module for paired correctness deltas, bootstrap
  intervals, analytical intervals, category aggregation, and release verdict derivation.
- [ ] Extend compare summary schema with:
  - `category_breakdown`
  - `statistical_evidence`
  - `release_gate_summary`
  - `effect_threshold`
  - `verdict`
- [ ] Keep `delta_accuracy`, `base_accuracy`, `target_accuracy`, and win/loss counters unchanged.
- [ ] Persist bootstrap and analytical metadata, including method name, confidence level, lower and
  upper bounds, and whether the interval crosses zero.

**TDD order**

1. Schema tests fail on missing statistical fields.
2. Statistical helper tests fail on interval and verdict behavior.
3. Compare builder tests fail on missing evidence projection.
4. Implement minimal code to satisfy each slice.

## Task 2: Expand Stored Artifacts, Reports, And Exports

- [ ] Extend compare summary JSON and CSV with the new evidence and verdict fields.
- [ ] Extend compare Markdown reports with:
  - observed delta
  - bootstrap interval
  - analytical interval
  - effect threshold
  - release verdict
  - category breakdown table when present
- [ ] Extend export-bundle normalization so statistical compare rows survive into shared export
  bundles rather than being flattened down to one `score_name` only.
- [ ] Keep existing summary CSV headers readable and deterministic; add new release-friendly columns
  rather than changing old field names.

## Task 3: Feed Statistical Evidence Into Phase 8 Release Gates

- [ ] Add policy-backed comparison thresholds to
  `infra/release/phase8-release-gate-policy.json`, including confidence level, bootstrap iteration
  count, and minimum effect threshold for the supported comparison suites.
- [ ] Extend release-gate report building to collect or synthesize compare statistical evidence from
  persisted evaluation comparison artifacts.
- [ ] Add a dedicated comparison section in the release-gate JSON output with verdict-oriented
  summary fields.
- [ ] Fail closed when required comparison evidence is missing or when the verdict is policy-failing.

## Task 4: Surface Statistical Summary Through Swift, CLI, And Window UI

- [ ] Extend the shared export bundle decoding to retain statistical compare summary fields.
- [ ] Update `melix eval compare` rendering so human-readable output includes verdict, delta,
  bootstrap CI, analytical CI, and threshold.
- [ ] Update Window UI runtime state to expose the same summary for compare history rows or compare
  detail views without inventing a separate source of truth.
- [ ] Keep JSON and text render paths consistent with the persisted compare bundle.

## Task 5: Update Contract, Runbooks, Verification, And Metrics

- [ ] Update the canonical benchmark and evaluation contract with the shipped statistical and
  category-breakdown fields.
- [ ] Update the operator runbooks for compare evidence review and Phase 8 release-gate
  interpretation.
- [ ] Record the touched-scope metrics and changed-line coverage evidence for Python and Swift.
- [ ] Do not claim completion until fresh verification output exists for the touched scope and full
  repository gate.

## Verification

### Targeted Python verification

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_statistical_evidence.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_release_gates.py -q
```

### Targeted Swift verification

```bash
swift test --filter 'MelixCLIRunnerTests'

swift test --package-path services/control-plane-swift \
  --filter 'BenchmarkExportBundleTests'

swift test --package-path apps/macos-menubar \
  --filter 'RuntimeViewModelTests'
```

### Coverage and final verification

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run \
  --source=services/mlx-worker-python/worker \
  -m pytest \
  services/mlx-worker-python/tests/test_statistical_evidence.py \
  services/mlx-worker-python/tests/test_evaluation_schemas.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_evaluation_core.py \
  services/mlx-worker-python/tests/test_benchmark_export.py \
  services/mlx-worker-python/tests/test_release_gates.py -q

make py-test
make swift-test
make integration-test
```

## Acceptance

- Compare summaries classify outcomes as `improvement`, `regression`, or `inconclusive`.
- Bootstrap and analytical confidence intervals are both persisted and exported.
- Category breakdown appears only for supported suites and remains absent otherwise.
- Phase 8 release-gate JSON includes a policy-backed comparison summary instead of forcing operators
  to infer the verdict from raw delta alone.
- CLI, control-plane export, and Window UI all decode the same statistical summary shape.
