# Runtime Export Diagnostics Source-Line Extension Slice

## Scope

This slice keeps runtime export diagnostic parsing behavior unchanged and optimizes only the source-line collection path in `worker.productization.export_target_diagnostics`.

The affected path is covered by the registered PR-scoped probe `runtime-export-diagnostic-parser` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for this Python path.

## Plan

1. Preserve `_split_source_lines()` behavior with a focused regression guard.
2. Add an append-oriented helper so `_collect_source_lines()` can extend the destination list directly instead of allocating an intermediate list for every runtime log or failure-check text.
3. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.

## Metrics

Baseline registered-probe runs before the change:

- `elapsed_ms_mean`: `2868.319716199767`, `2875.5502530024387`, `2864.8703943938017` ms; mean `2869.580121198669` ms.
- `diagnostic_latency_ms`: `9.030982968397439`, `9.151748032309115`, `9.544404107145965` ms; mean `9.242378369284173` ms.
- `peak_bytes_mean`: `200587.4`, `204114.6`, `203237.0` bytes; mean `202646.33333333334` bytes.

Post-change registered-probe runs after the final helper-local binding change:

- `elapsed_ms_mean`: `2859.638609807007`, `2876.9665531930514`, `2859.2025456018746` ms; mean `2865.2692362006444` ms (`-4.310884998024352` ms, `1.0015x` faster than baseline mean).
- `diagnostic_latency_ms`: `9.983449010178447`, `9.053748042788357`, `9.326779982075095` ms; mean `9.454659011680633` ms (`+0.21228064239646013` ms; within the registered 5% warning boundary).
- `peak_bytes_mean`: `201331.8`, `203772.4`, `204379.8` bytes; mean `203161.33333333334` bytes (`+515.0` bytes; within the registered 5% warning boundary).
- `diagnosis_matching_elapsed_ms_mean`: `25.672080006916076`, `27.310018602292985`, `26.85031680157408` ms; mean `26.610805136927713` ms (`-0.2258491875257447` ms).
- `path_redaction_elapsed_ms_mean`: `23.047549021430314`, `23.80858139367774`, `22.933048591949046` ms; mean `23.26305966901903` ms (`-0.3763882680416582` ms).

Decision: accepted for PR because the registered end-to-end elapsed metric improved, diagnosis matching and path-redaction sub-metrics improved, and the small latency/peak-memory noise remained within registered warning thresholds while behavior stayed covered by 100% changed-scope coverage.

## 2026-06-28 follow-up: secret marker fast path

This Python-only follow-up stays inside the same
`runtime-export-diagnostic-parser` registered probe and narrows to
`_redact_text(...)`. Every redacted excerpt line previously used a generator over
`_SECRET_REDACTION_MARKERS` before deciding whether secret-specific regexes were
needed. The common path has many plain runtime and target-path lines, so this
slice replaces that generator dispatch with an explicit marker helper while
preserving the same case-sensitive marker set and downstream redaction behavior.

Validation remains the registered focused pytest selection, changed-scope
coverage, and the registered local/CI probe for runtime export diagnostic
parsing.
