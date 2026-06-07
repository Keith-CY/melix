# Native MTP weight shard load loop slice

This Python-only performance slice is limited to `worker.runtime.native_mtp.mlx_lm_loader`.
The native-MTP patched `load_model` path previously built one combined list from the
base `model*.safetensors` paths plus sidecar MTP shard paths before loading each
shard. Large models can have many base and sidecar shards, so this adds an
explicit streaming helper that loads base shards and sidecar shards in two loops
without materializing the combined path list.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
This slice extends that probe with weight-load-loop metrics while retaining the
existing index JSON, top-level safetensor listing, sidecar filtering, and key
predicate metrics. The probe has focused `test_command`, `coverage_command`, and
`probe_command` entries and runs on `ubuntu-latest`.

## Implementation plan

1. Add a small helper that loads base and native-MTP sidecar weight shards without
   building a combined path list.
2. Route the patched native-MTP `load_model` path through the helper.
3. Add a focused unit guard for load order and merged weight contents.
4. Extend the registered probe output and registry metrics for weight-load-loop
   timing and peak allocation.
5. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux before opening the PR.

## Verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
