# PR-Scoped Performance CI Plan

## Summary

Add a dedicated GitHub Actions workflow that runs only the performance probes affected by the pull request, runs only the targeted verification commands for those probes, compares base-vs-head metrics, and publishes a sticky PR comment with the scoped report.

## Goals

1. Avoid full-repository performance sweeps on every PR.
2. Tie each performance probe to explicit code paths and focused verification commands.
3. Compare each selected probe against the PR base commit and the PR head commit.
4. Publish a stable sticky PR comment that updates in place on each PR sync.
5. Make future scope expansion data-driven so adding a new probe definition automatically expands CI coverage.

## Non-Goals

- Replacing the existing benchmark/evaluation report workflow.
- Inventing cross-repository performance baselines outside the PR base/head diff.
- Claiming full performance coverage for code paths that do not yet have registered probes.

## Proposed Design

### Probe Registry

Create a JSON registry under `infra/perf/` where each entry declares:

- `id` and human-readable `name`
- `watch_globs` that decide whether a PR affects the probe
- `test_command` for focused verification
- `coverage_command` and `coverage_targets` for changed-scope evidence when practical
- `probe_command` that prints machine-readable JSON metrics
- metric metadata (`key`, `unit`, `direction`)

The workflow scope step selects probes whose `watch_globs` match the PR diff. If registry or workflow infrastructure files change, select all probes so CI revalidates the framework.

### Scope Resolution

Add a Python script that:

1. Reads the registry.
2. Computes changed files between the PR base and head SHAs.
3. Emits the selected probe list as workflow-job JSON outputs.
4. Produces a small markdown summary for the final PR comment.

### Probe Execution

Add a Python runner script that:

1. Receives a repository checkout path plus a probe id.
2. Runs the probe's focused test and coverage commands in that checkout.
3. Runs the probe command and captures JSON metrics.
4. Persists a normalized artifact JSON payload.

The workflow will run the selected probe matrix for both `base` and `head` checkouts and upload the artifacts.

### Report Rendering

Add a report builder that:

1. Loads the selected-probe scope metadata.
2. Loads base/head probe artifacts.
3. Computes per-metric deltas.
4. Renders terminal + markdown output.
5. Emits a sticky-comment body with a stable marker.

When no probes match, the workflow should still update the sticky comment with an explicit “no registered performance probes were affected” result.

## Initial Seed Probes

Seed the registry with Linux-verifiable Python probes for existing hot paths so the workflow is immediately useful without requiring a full Melix stack boot.

Planned initial entries:

1. `benchmark-evaluation-report-running-aggregates`
   - Watches `worker/productization/benchmark_evaluation_report.py` and its tests.
   - Focused verification: `test_benchmark_evaluation_report.py`.
   - Probe: synthetic large-bundle aggregation comparison.

2. `closure-audit-probe-source-short-circuit`
   - Watches `worker/productization/closure_audit.py` and its tests.
   - Focused verification: `test_closure_audit.py`.
   - Probe: synthetic many-file scan comparison.

## Success Metrics

- The workflow runs only selected probes, not the full performance suite.
- Each selected probe reports base/head metrics and deltas in a sticky PR comment.
- Adding a new registry entry is sufficient to extend CI scope.
- Focused coverage for the changed executable scope remains measurable at >=95% for seeded probes.

## Verification Plan

- Unit tests for scope selection logic.
- Unit tests for report rendering and delta computation.
- Unit tests for probe runner command parsing / artifact normalization.
- Local dry-run of the scope script against synthetic changed-file inputs.
- Local execution of seeded probe runners on the current checkout.
- Local YAML validation for the new workflow.

## Iterative Optimization Slices

### Benchmark evaluation metric-direction constants

- Scope: `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`.
- Probe: `benchmark-evaluation-report-running-aggregates` remains the registered CI and local probe for this path.
- Slice boundary: use a precomputed exact-key direction map for the registered report probe's common metric suffixes before falling back to the fragment scans, so the large synthetic report path avoids repeated substring scans for known keys while preserving fallback semantics.
- Verification target: focused benchmark-evaluation report tests, changed-scope coverage, and the registered PR-scoped performance probe.

## Known Constraints

- Only code paths with registered probes participate in this CI.
- PRs that touch unregistered paths will receive an explicit no-probe comment rather than a speculative result.
- Seed probes should avoid requiring a live Apple Silicon runtime so the CI remains reliable and reasonably fast.
