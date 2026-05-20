# Model Registry Plain Scan Slots

## Goal

Reduce transient allocation overhead in the plain-local model registry scan path by removing the per-instance `__dict__` from `_PlainLocalModelScan` records.

## Scope

This slice is intentionally limited to the Python model registry scan bookkeeping path:

- add `slots=True` to the private `_PlainLocalModelScan` dataclass;
- pin the allocation contract in the existing plain-local scan regression test;
- reuse the existing registered PR-scoped performance probe for `model-registry-plain-local-manifest-stat-elision`.

It does not change model discovery order, descriptor parsing, Hugging Face cache pruning, manifest parsing, JSON cache behavior, or protobuf outputs.

## Performance Probe

Registered probe: `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`.

The probe builds a synthetic plain-local registry, runs `WorkerModelCatalog.snapshot()`, and reports scan elapsed time plus manifest/generation-config stat and config-load counts. This slice keeps the semantic counters unchanged while reducing per-scan record allocation overhead.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR. CI remains the source of truth for the PR-scoped base-vs-head performance report.
