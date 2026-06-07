# Engine plain parser metrics fast path slice

This Python-only performance slice is limited to `worker.engine.engine_core`.
Plain text generation requests with an empty execution extension map currently
still run through the generic allowed-tools receipt helper and allocate/update a
parser metrics dict from an intermediate literal during terminal completion.
The common no-tools/no-reasoning path can use already-known defaults directly.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and runs on `ubuntu-latest`.

## Implementation plan

1. Keep the optimization restricted to plain text requests with an empty
   execution extension map.
2. Reuse the default omitted allowed-tools receipt constant instead of calling
   the generic receipt builder for that path.
3. Assign plain-path parser metrics directly to avoid the intermediate update
   literal while preserving emitted metric keys and values.
4. Add a focused regression guard that proves the empty-extension plain path does
   not call `_allowed_tools_receipt_json()` and still emits the default receipt.
5. Run the registered focused tests, changed-scope coverage, and the registered
   probe locally on Linux before opening the PR.

## Verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
