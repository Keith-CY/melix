# Observability Probe Policy And Production Isolation

## Goal

Separate Melix observability into explicit runtime modes so production serving
keeps near-zero probe overhead while benchmark, evaluation, release evidence,
debug diagnostics, and PR-scoped performance probes keep their required
evidence.

The canonical contract remains
`docs/evidence-telemetry-report-contract.md`. This plan refines that contract by
adding mode boundaries and production defaults; it does not remove required
benchmark or evaluation evidence.

## Mode Model

Melix observability has five modes:

| Mode | Default Use | Allowed Cost | Required Behavior |
|---|---|---:|---|
| `off` | Packaged production serving | Near zero | No telemetry threads, no power sampling, no debug JSONL, no per-row probe expansion |
| `minimal` | Production health surfaces | O(1) request counters | Reuse counters already produced by request execution |
| `sampled` | Operator-enabled production diagnostics | Bounded asynchronous work | Sampling rate and queue size must be bounded and non-blocking |
| `evidence` | Benchmark, evaluation, report gates | Full run-scoped evidence | Preserve valid `run-evidence.json`, `probe_timeline`, and `telemetry_summary` |
| `debug` | Explicit local diagnostics | Bounded detailed traces | Write detailed bundles only for the opted-in session |

`MELIX_PROBE_MODE` is the common environment override. Invalid values fall back
to a production-safe default.

## Probe Inventory And Retention Policy

### Swift Debug Probes

Swift debug probes are operator diagnostics, not production performance-claim
artifacts. They must stay opt-in except for bounded early-failure capture.

Current inventory:

- `Sources/MelixCLICore/MelixDiagnostics.swift` redacts sensitive strings,
  mappings, and environment values through `MelixDiagnosticsRedaction` before
  writing diagnostic artifacts.
- `MelixSystemDiagnostics.payload(...)` records platform state, Melix home
  layout, directory writability, and whether `MELIX_HOME`, `MELIX_RUNTIME_DIR`,
  `MELIX_LOGS_DIR`, `MELIX_WORKER_SOCKET_PATH`, and
  `MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH` are set.
- `MelixDiagnosticsStore.writeEarlyFailureBundle(...)` writes bounded early CLI
  failure bundles under `runs/<bundle_id>/debug/` with `command.txt`,
  `redacted-env.json`, `effective-config.json`, `system.json`,
  `capability-receipts.json`, `memory-estimate.json`, `logs.txt`,
  `metrics.json`, `error.json`, and `manifest.json`.
- `MelixDiagnosticsStore.writeDebugBundle(...)` writes explicit run debug
  bundles with the same redacted artifact shape and includes run-record
  artifacts, known gaps, probes, memory-related metrics, logs, metrics, and
  errors.
- `Tests/MelixCLITests/MelixCLIParserTests.swift` covers
  `melix debug bundle RUN_OR_JOB_ID`, `--output`, `--source-path`, and JSON
  output parsing.

Policy:

- Production hot paths must not emit Swift debug JSONL by default.
- Debug JSONL, DFlash-style tracing, serving diagnostics bundles, and detailed
  log snapshots must require `debug` mode, a CLI flag, or a dedicated debug
  environment variable.
- Debug artifacts may reference evidence artifacts, but benchmark/evaluation
  evidence must not depend on debug bundle presence.
- Debug bundles and `logs.txt` must not be used as public performance evidence
  unless a separate evidence-mode run generated the claim.

### CI PR-Scoped Probes

CI PR-scoped probes are regression evidence and developer tooling. They must not
enter packaged production runtime paths.

Current inventory:

- `infra/perf/pr_scoped_probes.json` currently registers 100 scoped probes. Each
  entry declares `id`, `name`, `runner`, `watch_globs`, `test_command`,
  `coverage_command`, `probe_command`, `probe_impl`, and `metrics`.
- `scripts/*probe*.py` contains synthetic and focused probes for dataset
  registry, hub catalog, multimodal preprocessing, runtime utilities, stream
  assembly, benchmark/evaluation reporting, event extraction, code evaluation,
  quantization, worker registry, startup signals, and Swift binary resolution.
- `scripts/pr_scoped_performance_scope.py` converts PR changed files into a
  selected-probe scope report.
- `worker.productization.pr_scoped_performance.build_scope_report(...)` selects
  probes by `watch_globs` and forces all probes when the workflow, registry,
  PR-scoped scripts, PR-scoped tests, or PR-scoped implementation changes.
- `.github/workflows/pr-scoped-performance.yml` checks out isolated base and
  head worktrees, runs the selected probe matrix, uploads
  `artifacts/probes/<probe-id>.json`, and posts the scoped report.
- `scripts/pr_scoped_performance_run.py` runs head tests and coverage before
  base/head probe commands and writes
  `melix.pr_scoped_performance_probe_result.v1` JSON.

Policy:

- Keep PR-scoped probes as evidence mode for PR review and merge gates.
- Do not import CI probe scripts from production serving, benchmark, or
  evaluation hot paths.
- Synthetic workloads, repeated loops, `tracemalloc`, monkey-patching, and call
  counters are allowed only in CI/tooling probes.
- Keep `test_command`, `coverage_command`, and `probe_command` explicit so each
  future performance issue has focused tests, coverage, and metrics evidence.

### Benchmark And Evaluation Evidence Probes

Benchmark/evaluation probes are durable operator and release evidence. They
must remain available when debug probes and CI probes are disabled.

Current inventory:

- `docs/evidence-telemetry-report-contract.md` requires every benchmark,
  evaluation, event-extraction, and adapter/runtime check to write an evidence
  envelope with `probe_timeline`, `telemetry_summary`, `model_memory_summary`,
  linked artifacts, failure state, and fallback state.
- The evidence contract defines required probe fields: run/span identity,
  component, phase, monotonic start, duration, status, error attribution, and
  small structured attributes.
- Fan-out stages must write aggregate summary probes and may write only bounded
  representative sample probes for slow, failed, skipped, or fallback samples.
- `docs/benchmark-evaluation-contract.md` requires `manifest.jsonl`,
  `effective-config.json`, and optional `preflight-report.json` in both the
  temporary run directory and operator output directory.
- Batch-run configuration records isolation and execution variables including
  `MELIX_HOME`, `MELIX_RUNTIME_DIR`, `MELIX_SERVICE_INSTANCE_NAME`,
  `MELIX_HTTP_PORT`, `MELIX_CLI`, `MELIX_BATCH_MODEL_LIST`,
  `MELIX_DOWNLOAD_ROOT`, `MELIX_RUN_TMP_ROOT`,
  `MELIX_RESTART_STACK_PER_MODEL`, and the benchmark/evaluation `MELIX_*`
  knobs.
- `services/mlx-worker-python/worker/productization/benchmark_export.py`
  collects benchmark jobs, benchmark summaries, matrix rows, evaluation jobs,
  evaluation summaries, evaluation samples, compare artifacts, and deduplicated
  `run_evidence`.
- `Tests/test_phase8_acceptance_bundle.py` preserves
  `evaluation-samples.jsonl` and an `events.jsonl` diagnostic path in generated
  acceptance artifacts.

Policy:

- Keep run evidence envelopes, aggregate probe timelines, telemetry summaries,
  model memory summaries, manifests, and exported JSON/CSV/JSONL artifacts as
  required `evidence` mode outputs.
- Do not replace machine-readable evidence with Markdown, terminal summaries,
  logs, or CSV-only exports.
- Do not remove evidence probes to optimize production defaults. Instead, bound
  fan-out probes, keep telemetry off the hot path, and record explicit
  instrumentation gaps when telemetry is unavailable.
- Treat `loaded_model_estimated_resident_bytes` and
  `runtime_stats_model_resident_bytes` as evidence-critical model-residency
  fields distinct from worker RSS and host memory.

### Production Hot Path Exclusions

The following must not be enabled by default in `off`, `minimal`, or packaged
production serving paths:

- Per-token, per-row, or full-payload JSONL debug tracing.
- Full prompt, response, dataset row, credential, or secret capture in probe
  attributes.
- Synthetic microbenchmarks, repeated-loop probes, `tracemalloc`, monkey-patched
  call counters, or CI base/head comparison commands.
- Request-critical `powermetrics` or heavyweight sampler startup.
- Blocking debug queues or unbounded in-memory event buffers.

## Milestones

### Milestone 1: Policy Foundation And Production Defaults

Introduce shared policy parsing and default no-op production behavior in the
Python productization path.

Acceptance:

- Production-safe modes do not start Apple Silicon telemetry sessions.
- Production-safe modes do not call `powermetrics`, `tracemalloc`, or any heavy
  sampler by default.
- Benchmark and evaluation stores can still be constructed with an explicit
  evidence collector for compatibility.
- Existing evidence-mode fixtures continue to produce collected telemetry.

### Milestone 2: Evidence Plane Boundary

Make benchmark, evaluation, comparison reports, and release gates explicitly use
`evidence` mode.

Acceptance:

- `bench` and `eval` produce valid `run-evidence.json` artifacts in evidence
  mode.
- Missing evidence remains a verifier failure for evidence-mode runs.
- Production serving code does not import evidence-only collectors on the hot
  path.
- Report and gate tests prove probe timelines remain available for evidence
  claims.

### Milestone 3: Debug And Diagnostics Plane

Unify detailed diagnostics under explicit `debug` mode.

Acceptance:

- Swift debug probes such as DFlash JSONL tracing remain opt-in.
- Serving diagnostics bundles are written only when requested.
- Debug event queues are bounded; queue overflow drops debug events instead of
  blocking serving.
- Debug artifacts do not qualify as public performance claims unless generated
  through evidence mode.

### Milestone 4: CI Performance Probe Isolation

Keep PR-scoped performance probes out of production packages and runtime import
paths.

Acceptance:

- `scripts/*_probe.py` and `infra/perf/pr_scoped_probes.json` remain CI/tooling
  entrypoints.
- Production packaging excludes synthetic probe commands and fixtures unless a
  developer tooling bundle explicitly requests them.
- PR-scoped probes can still be selected from changed files and report metrics.
- Documentation tells contributors when to add CI probes versus runtime metrics.

### Milestone 5: Measurement, Rollout, And Guardrails

Add regression tests, metrics, and release checks that prevent observability
cost from leaking back into production.

Acceptance:

- No-op policy overhead is measured with a focused microprobe.
- Evidence artifact validity is covered by focused tests and report gate checks.
- Production mode has tests that fail if telemetry threads or heavyweight
  samplers start.
- The PR template evidence section records mode, probe overhead, and known
  deferred observability work.

## Plans And Executable Units

### Plan 1.1: Python ProbePolicy Foundation

Executable units:

- Unit 1.1.1: Add `ProbePolicy` and `ProbeMode` parsing for
  `MELIX_PROBE_MODE`.
- Unit 1.1.2: Add a no-op telemetry collector/session/collection.
- Unit 1.1.3: Wire `BenchmarkStore` and `EvaluationStore` through the policy.
- Unit 1.1.4: Add focused tests for mode parsing and no-op collector behavior.

### Plan 1.2: Production Default Tests

Executable units:

- Unit 1.2.1: Assert production-safe store defaults do not call the sampler.
- Unit 1.2.2: Assert evidence fixture collectors still produce collected
  telemetry.
- Unit 1.2.3: Add a microprobe for no-op policy overhead.

### Plan 2.1: Benchmark And Evaluation Evidence Entry Points

Executable units:

- Unit 2.1.1: Mark CLI and control-plane benchmark entrypoints as `evidence`.
- Unit 2.1.2: Mark evaluation and event-extraction entrypoints as `evidence`.
- Unit 2.1.3: Preserve report verifier failures for missing evidence.

### Plan 2.2: Evidence Report Compatibility

Executable units:

- Unit 2.2.1: Prove `probe_timeline` and `telemetry_summary` stay valid in
  report generation.
- Unit 2.2.2: Update docs to distinguish model residency, host telemetry, and
  production counters.
- Unit 2.2.3: Keep benchmark/evaluation artifacts readable by desktop evidence
  views.

### Plan 3.1: Swift Debug Probe Policy

Executable units:

- Unit 3.1.1: Inventory Swift debug probe environment variables and callsites.
- Unit 3.1.2: Route Swift debug probes through the common mode vocabulary.
- Unit 3.1.3: Add tests that debug JSONL is opt-in and bounded.

### Plan 3.2: Serving Diagnostics Trace Plane

Executable units:

- Unit 3.2.1: Add bounded trace queue semantics for debug diagnostics.
- Unit 3.2.2: Keep serving diagnostics bundles separate from evidence claims.
- Unit 3.2.3: Document operational use of debug versus evidence mode.

### Plan 4.1: CI Probe Registry Governance

Executable units:

- Unit 4.1.1: Document PR-scoped probe ownership and naming rules.
- Unit 4.1.2: Add a registry validation test for probe commands and watch
  globs.
- Unit 4.1.3: Ensure production package manifests exclude synthetic probe
  scripts.

### Plan 4.2: Contributor Workflow

Executable units:

- Unit 4.2.1: Update contributor guidance for runtime metrics versus CI probes.
- Unit 4.2.2: Add a checklist item for observability mode and overhead.
- Unit 4.2.3: Add examples for adding a new PR-scoped performance probe.

### Plan 5.1: Overhead Measurement

Executable units:

- Unit 5.1.1: Add no-op recorder overhead microprobe and thresholds.
- Unit 5.1.2: Add sampled-mode queue saturation microprobe.
- Unit 5.1.3: Add evidence-mode artifact validity metrics.

### Plan 5.2: Release Guardrails

Executable units:

- Unit 5.2.1: Add release gate checks for production-safe observability mode.
- Unit 5.2.2: Add changed-scope coverage requirements for probe policy modules.
- Unit 5.2.3: Add rollback guidance for disabling optional debug probes.

## Performance Probes And Metrics

- Production no-op overhead: mean wall time for a no-op recorder call across a
  large synthetic loop; target is within 5 percent of a direct empty function
  call in the same process.
- Production sampler isolation: count calls to heavy sampler methods while
  persisting benchmark/evaluation records in `off` and `minimal`; target is `0`.
- Evidence validity: `assert_valid_run_evidence_payload` passes for benchmark
  and evaluation evidence mode.
- Debug opt-in: detailed JSONL event count is `0` unless `debug` mode or the
  specific debug environment variable is enabled.
- CI isolation: PR-scoped probe commands run from `infra/perf/pr_scoped_probes.json`
  and are not imported by serving hot path modules.

## Acceptance Metrics For Follow-Up Issues

Use these metrics when splitting the policy into Milestone, Plan, or Unit
issues.

| Metric | Required acceptance |
|---|---|
| Production no-op overhead | Default execution with debug and CI probes disabled stays at or below 1 percent elapsed-time regression for the touched path, emits no per-token/per-row debug stream, starts no heavyweight sampler, and allocates no unbounded debug buffer. |
| Evidence artifact validity | Evidence-mode benchmark/evaluation runs emit parseable JSON/JSONL/CSV artifacts with valid schema versions, linked artifact paths, telemetry or explicit telemetry-failure records, model-memory evidence where applicable, and verifier failures for missing required evidence. |
| Debug JSONL opt-in | Default execution writes no debug JSONL; explicit `debug` mode or a dedicated opt-in writes only valid newline-delimited JSON objects with schema metadata, bounded attributes, redaction metadata, and no full prompts, responses, credentials, or secrets. |
| PR-scoped probe isolation | Changed-file selection matches registry `watch_globs`, force-all infrastructure changes select all registered probes, base/head worktrees stay separate, each selected probe uploads one scoped JSON result, and production packages do not import synthetic probe scripts. |

## Initial PR Scope

The first PR for this plan implements Milestone 1 foundation:

- `ProbePolicy` and mode parsing.
- No-op Apple Silicon telemetry collection for production-safe modes.
- Store-level wiring for benchmark and evaluation persistence.
- Focused tests proving no heavy telemetry is started by default and evidence
  fixtures still work.

Later milestones remain tracked as issues so they can land in smaller,
reviewable slices without weakening the target architecture.

## Issue Tracking Map

Milestone issues:

| Milestone | Issue |
|---|---|
| Milestone 1: Policy Foundation And Production Defaults | #882 |
| Milestone 2: Evidence Plane Boundary | #883 |
| Milestone 3: Debug And Diagnostics Plane | #884 |
| Milestone 4: CI Performance Probe Isolation | #885 |
| Milestone 5: Measurement, Rollout, And Guardrails | #886 |

Plan issues:

| Plan | Parent Milestone | Issue |
|---|---:|---:|
| Plan 1.1: Python ProbePolicy Foundation | #882 | #887 |
| Plan 1.2: Production Default Tests | #882 | #889 |
| Plan 2.1: Benchmark And Evaluation Evidence Entry Points | #883 | #888 |
| Plan 2.2: Evidence Report Compatibility | #883 | #891 |
| Plan 3.1: Swift Debug Probe Policy | #884 | #890 |
| Plan 3.2: Serving Diagnostics Trace Plane | #884 | #892 |
| Plan 4.1: CI Probe Registry Governance | #885 | #893 |
| Plan 4.2: Contributor Workflow | #885 | #894 |
| Plan 5.1: Overhead Measurement | #886 | #896 |
| Plan 5.2: Release Guardrails | #886 | #895 |

Executable unit issues:

| Unit | Parent Plan | Issue |
|---|---:|---:|
| Unit 1.1.1: Add `ProbePolicy` and `ProbeMode` parsing | #887 | #898 |
| Unit 1.1.2: Add no-op telemetry collector/session/collection | #887 | #901 |
| Unit 1.1.3: Wire stores through policy | #887 | #899 |
| Unit 1.1.4: Add focused ProbePolicy tests | #887 | #900 |
| Unit 1.2.1: Assert production-safe store defaults do not call sampler | #889 | #897 |
| Unit 1.2.2: Assert evidence fixture collectors still produce collected telemetry | #889 | #903 |
| Unit 1.2.3: Add no-op policy overhead microprobe | #889 | #904 |
| Unit 2.1.1: Mark benchmark entrypoints as evidence mode | #888 | #905 |
| Unit 2.1.2: Mark evaluation and event-extraction entrypoints as evidence mode | #888 | #902 |
| Unit 2.1.3: Preserve report verifier failures for missing evidence | #888 | #906 |
| Unit 2.2.1: Prove report generation compatibility | #891 | #908 |
| Unit 2.2.2: Update docs for telemetry distinctions | #891 | #909 |
| Unit 2.2.3: Keep desktop evidence view compatibility | #891 | #907 |
| Unit 3.1.1: Inventory Swift debug probes | #890 | #910 |
| Unit 3.1.2: Route Swift debug probes through common mode vocabulary | #890 | #911 |
| Unit 3.1.3: Add debug JSONL opt-in tests | #890 | #912 |
| Unit 3.2.1: Add bounded trace queue semantics | #892 | #915 |
| Unit 3.2.2: Separate serving diagnostics bundles from evidence claims | #892 | #914 |
| Unit 3.2.3: Document debug versus evidence mode | #892 | #913 |
| Unit 4.1.1: Document PR-scoped probe ownership | #893 | #916 |
| Unit 4.1.2: Add registry validation test | #893 | #917 |
| Unit 4.1.3: Exclude synthetic probe scripts from production packages | #893 | #918 |
| Unit 4.2.1: Update contributor guidance | #894 | #919 |
| Unit 4.2.2: Add checklist item for mode and overhead | #894 | #921 |
| Unit 4.2.3: Add PR-scoped performance probe examples | #894 | #920 |
| Unit 5.1.1: Add no-op recorder overhead microprobe | #896 | #924 |
| Unit 5.1.2: Add sampled-mode queue saturation microprobe | #896 | #922 |
| Unit 5.1.3: Add evidence-mode artifact validity metrics | #896 | #923 |
| Unit 5.2.1: Add release gate checks | #895 | #926 |
| Unit 5.2.2: Add changed-scope coverage requirements | #895 | #925 |
| Unit 5.2.3: Add rollback guidance | #895 | #927 |

## Verification

Focused initial PR commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_probe_policy.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_apple_silicon_telemetry.py
```

Changed-scope coverage command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_probe_policy.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_apple_silicon_telemetry.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/probe_policy.py \
  services/mlx-worker-python/worker/productization/apple_silicon_telemetry.py \
  services/mlx-worker-python/worker/productization/benchmark_store.py \
  services/mlx-worker-python/worker/productization/evaluation_store.py \
  services/mlx-worker-python/tests/test_probe_policy.py \
  services/mlx-worker-python/tests/test_benchmark_store.py \
  services/mlx-worker-python/tests/test_evaluation_store.py \
  services/mlx-worker-python/tests/test_apple_silicon_telemetry.py
```
