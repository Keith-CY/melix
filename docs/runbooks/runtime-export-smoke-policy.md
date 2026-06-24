# Runtime Export Smoke Policy

This runbook covers the bounded post-export smoke policy for materialized
runtime export targets. Use it after a target directory contains
`export-target-manifest.json` and generated target artifacts.

## Smoke Evidence

The smoke runner verifies required artifact metadata and target-local digest
rows before runtime checks. When a target requires runtime loading, it also
checks the runtime binary policy and generated file paths. Generation-capable
targets write a bounded synthetic preview.

The target directory receives:

- `smoke/smoke-receipt.json`: metadata, load, generation, timeout, waiver, and
  policy outcomes.
- `smoke/generation-preview.txt`: bounded diagnostic preview text for targets
  that require generation smoke.

`export-report.json` is updated with the smoke receipt path, terminal
verification state, blocker code, waiver id, and report-level `ok` status.

## Probe Command

Run the smoke policy probe over the checked-in fixtures:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python3 scripts/runtime_export_smoke_policy_probe.py
```

The probe reports metadata check latency, load smoke latency, generation smoke
latency, output preview byte count, timeout count, waiver count, target count,
and peak bytes.

## Waiver Policy

Runtime-unavailable load checks may be waived only when the export target
allows waivers and the waiver reason is
`EXPORT_WAIVER_REASON_RUNTIME_NOT_INSTALLED`. Waived smoke receipts preserve
the waiver id and skip generation checks. Missing files, digest mismatches,
unsafe paths, unsupported target types, missing source provenance, and missing
target manifests block verification instead of waiving.
