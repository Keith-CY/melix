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

## Diagnostics Evidence

When smoke verification fails or blocks a target, the runner writes
`diagnostics/diagnostics-receipt.json` before updating `export-report.json`.
The receipt uses schema `melix.export_diagnostics_receipt.v1` and contains:

- parser status: `matched`, `unknown`, or `not_applicable`
- typed diagnosis rows for runtime load failures, unsupported architecture,
  duplicate tensor names, missing blobs, missing binaries, invalid runtime
  paths, timeouts, permission failures, insufficient memory, and unknown
  failures
- operator remedies with redacted evidence pointers for CLI, Desktop, and
  report surfaces
- redaction counts, bounded excerpt size, truncation state, and diagnostic
  parser latency metrics

Operator-facing diagnostics use `diagnostics/redacted-log-excerpt.txt`. The
parser redacts absolute host paths, credentials, bearer tokens, proxy secrets,
certificate-like contents, full prompts, full generations, dataset rows,
private prompt templates, and unnecessary user or operator identity values.
Paths under the target directory are rewritten as `<target>/...`; other
absolute paths are replaced with `<absolute-path>`.

`export-report.json` mirrors `diagnostic_status`, `diagnostic_codes`, and
`operator_remedies` from the diagnostics receipt. UI surfaces should render
those fields and should not parse raw runtime logs independently.

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

Run the diagnostic parser probe over the same fixture set:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python3 scripts/runtime_export_diagnostic_parser_probe.py
```

The diagnostic probe reports parser coverage, parsed failure count, unknown
failure count, redaction count, diagnostic latency, target count, and peak
bytes. The diagnostics parser bypasses the absolute-path redaction regex for
slashless diagnostic lines because that regex only matches `/...` path tokens.

## Waiver Policy

Runtime-unavailable load checks may be waived only when the export target
allows waivers and the waiver reason is
`EXPORT_WAIVER_REASON_RUNTIME_NOT_INSTALLED`. Waived smoke receipts preserve
the waiver id and skip generation checks. Missing files, digest mismatches,
unsafe paths, unsupported target types, missing source provenance, and missing
target manifests block verification instead of waiving.
