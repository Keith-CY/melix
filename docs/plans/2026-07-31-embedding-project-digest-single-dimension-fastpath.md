# Embedding project digest single-dimension fast path

## Scope

This Python-only performance slice is limited to
`worker.runtime.embedding_backends.DeterministicEmbeddingBackend._project_digest(...)`.
Behavior stays equivalent to the legacy digest projection for all dimensions while
adding a direct branch for one-dimensional projections.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The registry entry already has focused
`test_command`, `coverage_command`, and `probe_command` entries. This slice
extends the probe payload and registered metrics with:

- `single_dimension_elapsed_ms_mean`
- `single_dimension_peak_bytes_mean`

The existing large expanded-vector, default eight-dimension, and zero-dimension
metrics remain in the same registered probe. The zero-dimension elapsed metric
uses a wider warning threshold because it is a sub-30ms empty-return guard that
showed CI noise while the single-dimension direct metric remained the gated slice
signal.

## Implementation plan

1. Add a one-dimensional projection fast path after digest unpacking and before
   the expanded projection helper.
2. Preserve exact legacy normalization semantics: the single component normalizes
   to `1.0`, `-1.0`, or `0.0` when the raw component is zero.
3. Add a regression test proving the one-dimensional path does not call the
   expanded projection helper.
4. Extend the registered probe script and registry metric list to measure the
   single-dimension workload locally and in PR-scoped CI.

## Verification

Local Linux validation must include the focused registered tests, changed-scope
coverage, and the registered probe. GitHub Actions PR-scoped performance remains
the merge gate after the PR is opened.
