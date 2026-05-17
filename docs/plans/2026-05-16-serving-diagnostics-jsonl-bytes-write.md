# Serving diagnostics JSONL byte write optimization

## Scope

Optimize the Python serving diagnostics debug-event JSONL writer in
`services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The probe defines focused `test_command`,
`coverage_command`, and `probe_command` entries and reports queue elapsed time,
serialization elapsed time, retained/dropped counts, a serialization checksum,
and serialized byte count.

## Change

`_write_jsonl(...)` already accumulates exact UTF-8 JSONL text before writing the
file. This slice writes that payload through `Path.write_bytes(...)` after an
explicit UTF-8 encode instead of routing it through `Path.write_text(...)` and the
text I/O layer.

Behavior remains unchanged because the encoded bytes are the same UTF-8 payload
that `write_text(..., encoding="utf-8")` produced. The probe checksum and
serialized byte count are the parity guard for this narrow writer change.

## Validation plan

1. Run the focused serving diagnostics tests plus the PR-scoped probe registry
   tests for this probe.
2. Run changed-scope coverage for the changed source path and probe/test files.
3. Run the registered probe locally on Linux against `origin/main` and this branch
   before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local result

Local Linux probe, `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=50`:

- base (`origin/main`, e6a6f66f): `serialization_elapsed_ms_mean=0.988866`,
  `elapsed_ms_mean=5.396617`
- head: `serialization_elapsed_ms_mean=0.942207`, `elapsed_ms_mean=5.543796`
- serialization delta: `-0.046659 ms` (`-4.72%`)
- checksum and serialized byte count unchanged:
  `serialization_checksum=260064`, `serialized_bytes=10944`
- queue append elapsed is outside this writer slice and remained within the
  registered probe warning band in local sampling.
