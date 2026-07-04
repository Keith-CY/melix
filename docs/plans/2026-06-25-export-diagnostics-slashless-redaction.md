# Export diagnostics slashless redaction fast path

## Scope

This slice keeps the runtime export diagnostics parser behavior unchanged while
skipping the absolute-path redaction regex for diagnostic lines that contain no
slash character. The absolute-path redactor only matches `/...` path tokens, so
slashless lines cannot produce path redactions.

## Probe

The registered PR-scoped probe is `runtime-export-diagnostic-parser` in
`infra/perf/pr_scoped_probes.json`. It includes focused test, coverage, and
`scripts/runtime_export_diagnostic_parser_probe.py` commands. The probe reports
parser coverage, parsed and unknown failure counts, redaction counts, diagnostic
latency, path-redaction latency, elapsed time, and peak bytes.

## Success criteria

- Parser coverage remains `1.0` with no unknown-count regression.
- Changed-scope coverage for the diagnostics parser remains at least 95%.
- Registered probe elapsed time improves or remains neutral without reducing
  redaction coverage.
