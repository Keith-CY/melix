# Engine Generate Cancel Event Local Binding

## Scope

This Python slice targets the generate streaming loop in
`services/mlx-worker-python/worker/engine/engine_core.py`. Behavior stays
unchanged: cancellation checks, runtime invocation, usage accounting, and final
completion events keep the same semantics.

## Registered probe

Existing registered PR-scoped probe: `engine-generate-usage-token-elision` in
`infra/perf/pr_scoped_probes.json`.

The probe covers `engine_core.py`, focused generate-stream tests, and
`scripts/engine_generate_usage_token_probe.py`, with focused `test_command`,
`coverage_command`, and `probe_command` entries. No registry change is needed
for this narrow hot-loop optimization.

## Optimization

Bind `state.cancel_event` once to a local variable and reuse that local in the
runtime call, per-event cancellation check, and final usage/finish checks. The
streaming loop runs for every generation request, so avoiding repeated nested
attribute lookups keeps the hot path smaller without changing control flow.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux. CI's PR-scoped performance workflow remains the merge
gate for the registered probe report.
