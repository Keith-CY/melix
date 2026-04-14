# Executable Code Eval: HumanEval / MBPP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Melix executable-code evaluation for `humaneval` and `mbpp` as a first-class product
slice spanning checked-in dataset fixtures, worker-side sandboxed code execution, compare evidence
preservation, public CLI compare exports, and operator-facing documentation.

**Architecture:** Keep the Swift control plane as the public orchestration surface, keep Python
worker execution as the scoring truth, require explicit `code_exec_policy=sandboxed` for
executable-code suites, and preserve compile/runtime/test evidence through both standard evaluation
and base-versus-target compare exports.

**Tech Stack:** Swift, Python, Melix evaluation dataset packages, Swift Testing, pytest, coverage.

---

## Scope

- [x] Add checked-in Melix development fixtures for `humaneval.dev.v1` and `mbpp.dev.v1`.
- [x] Gate executable-code suites behind `code_exec_policy=sandboxed`.
- [x] Execute Python candidate code with compile/runtime/timeout/test evidence persisted per sample.
- [x] Preserve executable-code evidence through `eval compare` sample generation and export bundles.
- [x] Add dedicated CLI compare export commands:
  - `melix eval compare export-summary-csv`
  - `melix eval compare export-samples-csv`
  - `melix eval compare export-samples-jsonl`
- [x] Update the canonical contract and runbook for executable-code suites and compare exports.

## Product Decisions

- [x] Treat executable-code evaluation as an end-to-end product slice rather than a worker-only
  implementation detail.
- [x] Keep checked-in Melix dataset packages as the development-time source of truth for both
  executable-code suites.
- [x] Preserve executable-code evidence in compare exports instead of flattening compare results
  into the standard evaluation sample export path.
- [x] Use dedicated compare export commands instead of overloading the existing `eval export-*`
  commands.

## Probes And Success Metrics

- [x] Standard executable-code suite metrics persist:
  - `eval.<suite>.pass_at_1`
  - `eval.<suite>.correct_count`
  - `eval.<suite>.incorrect_count`
  - `eval.<suite>.code_exec_pass_count`
  - `eval.<suite>.code_exec_fail_count`
- [x] Standard sample evidence persists:
  - `code_language`
  - `code_entry_point`
  - `code_compile_status`
  - `code_runtime_status`
  - `code_timeout_status`
  - `code_test_status`
  - `code_tests_passed`
  - `code_tests_total`
  - `code_failure_detail`
- [x] Compare sample evidence persists:
  - `base_code_*`
  - `target_code_*`
  - `code_language`
  - `code_entry_point`

## Metrics Report

- Python changed-line coverage for the executable-code evaluation slice:
  - `99.10%` (`220/222`)
- Swift CLI changed-line coverage for compare export command and parser updates:
  - `97.77%` (`263/269`)
- Swift control-plane changed-line coverage for benchmark export bundle compare/code-evidence
  decoding and rendering:
  - `100.00%` (`266/266`)
- Aggregate measurable changed-line coverage across the touched Python and Swift executable-code
  slice:
  - `98.94%` (`749/757`)

## Verification

- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --data-file /tmp/executable_code_eval_py.coverage --source=services/mlx-worker-python/worker,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter BenchmarkExportBundleTests`
- [x] `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/executable_code_eval_py_coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/worker/productization/evaluation_compare.py services/mlx-worker-python/worker/productization/evaluation_schemas.py services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_maintenance_service.py`
- [x] `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift`
- [x] `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`
- [x] `git diff --check`
