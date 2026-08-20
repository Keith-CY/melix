# MCP source lease single-pass membership slice

This Python performance slice is limited to the MCP client manager source-lease
membership check used after owner release and lease expiry. The previous code used
`any(key[0] == source_id for key in self._leases)`, which creates a generator on
hot lifecycle cleanup paths.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`mcp-client-typed-lifecycle-dispatch` in `infra/perf/pr_scoped_probes.json`. The
probe watches `services/mlx-worker-python/worker/runtime/mcp_client.py`, the MCP
client/runtime tests, and `scripts/mcp_client_lifecycle_probe.py`; it includes
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Slice

- Add a small `_has_source_lease()` helper that scans lease keys directly and
  returns on the first matching source id.
- Use the helper in release and expiry cleanup decisions.
- Keep lease ownership semantics unchanged: actors are closed only when no lease
  remains for the source.

## Verification plan

Run the registered focused MCP test command, changed-scope coverage command, and
registered probe locally on Linux before opening the PR. GitHub Actions remains
the merge gate for the registered PR-scoped performance report.
