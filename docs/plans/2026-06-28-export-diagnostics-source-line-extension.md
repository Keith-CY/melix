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

## 2026-06-29 follow-up: named secret marker helpers

This Python-only follow-up stays inside the same
`runtime-export-diagnostic-parser` registered probe and narrows to the remaining
marker gates in `_redact_text(...)`. After the broad secret-marker fast path,
named-secret and identity checks still used generator dispatch over tiny constant
tuples once a line entered secret redaction. This slice replaces those two
remaining generator checks with explicit helpers while preserving the same
case-normalized marker semantics and downstream regex redaction behavior.

Validation remains the registered focused pytest selection, changed-scope
coverage, and the registered local/CI probe for runtime export diagnostic
parsing.

## 2026-06-29 follow-up: excerpt byte accounting

This Python-only follow-up stays inside the same
`runtime-export-diagnostic-parser` registered probe and narrows to
`_build_redacted_excerpt(...)`. The excerpt builder already enforces the byte
bound incrementally before appending each rendered line. The previous tail check
encoded the complete excerpt a second time and recomputed the same byte count;
that was redundant once the bounded append loop had accepted or clipped the last
line. This slice records `excerpt_byte_count` from the existing incremental
counter while preserving the emitted excerpt text, line count, and truncation
semantics.

Validation remains the registered focused pytest selection, changed-scope
coverage, and the registered local/CI probe for runtime export diagnostic
parsing.

Local 2026-06-29 probe decision for this byte-accounting slice:

- Baseline `elapsed_ms_mean`: `5330.903970852627`, `5367.044953862205`, `5334.687961431752` ms; mean `5344.212295382195` ms.
- Post-change `elapsed_ms_mean`: `5313.273270290146`, `5320.671012284168`, `5329.956482721692` ms; mean `5321.3002550986685` ms (`-22.91204028352695` ms, `1.0043x` faster).
- Baseline `path_redaction_elapsed_ms_mean`: `41.330500289664734`, `41.05674671674414`, `38.63969701342285` ms; mean `40.34231467327724` ms.
- Post-change `path_redaction_elapsed_ms_mean`: `39.35490457973044`, `38.86108529487891`, `40.44690043000238` ms; mean `39.554296768203905` ms (`-0.7880179050733318` ms, `1.0199x` faster).
- Baseline `peak_bytes_mean`: `221628.14285714287`, `217392.7142857143`, `220683.42857142858` bytes; mean `219901.42857142855` bytes.
- Post-change `peak_bytes_mean`: `218961.0`, `218377.85714285713`, `225139.7142857143` bytes; mean `220826.1904761905` bytes (`+924.7619047619519` bytes, within the registered warning boundary).

Decision: accepted because the registered end-to-end elapsed metric and path-redaction submetric improved over three local Linux probe runs, the byte-count behavior is covered directly, and the small peak-memory movement remains within the registered warning boundary.

## 2026-06-29 follow-up: diagnosis marker dispatch

This Python-only follow-up stays inside the same
`runtime-export-diagnostic-parser` registered probe and narrows to
`_has_diagnosis_marker(...)`. The diagnosis matcher calls this gate for every
redacted excerpt line before trying the heavier regex-backed diagnosis patterns.
The previous implementation iterated over the `_DIAGNOSIS_MARKERS` tuple on each
line; this slice replaces that loop with an explicit boolean chain, preserving
the same lowercase marker semantics while avoiding per-line iterator dispatch in
the registered diagnosis-matching submetric.

Validation remains the registered focused pytest selection, changed-scope
coverage, and the registered local/CI probe for runtime export diagnostic
parsing.

Local 2026-06-29 probe decision for this diagnosis-marker dispatch slice:

- Baseline `elapsed_ms_mean`: `2637.5025729998015`, `2654.986914584879`, `2665.917513007298` ms; mean `2652.8023335306593` ms.
- Post-change `elapsed_ms_mean`: `2667.1227828017436`, `2697.7672479930334`, `2665.6808106112294` ms; mean `2676.8569471353353` ms (`+24.05461360467598` ms, within the registered 5% warning boundary).
- Baseline `diagnosis_matching_elapsed_ms_mean`: `0.6576695828698575`, `0.6117791985161602`, `0.6307542091235518` ms; mean `0.6334009968365232` ms.
- Post-change `diagnosis_matching_elapsed_ms_mean`: `0.6145246094092727`, `0.6511981831863523`, `0.593486987054348` ms; mean `0.6197365932166576` ms (`-0.01366440361986554` ms, `1.0220x` faster).
- Baseline `path_redaction_elapsed_ms_mean`: `21.92815599264577`, `18.738398794084787`, `19.31412999983877` ms; mean `19.993561595523108` ms.
- Post-change `path_redaction_elapsed_ms_mean`: `19.627736799884588`, `19.103819190058857`, `19.20032900525257` ms; mean `19.310628331732005` ms (`-0.682933263791103` ms, `1.0354x` faster).
- Baseline `peak_bytes_mean`: `201497.0`, `203466.4`, `203879.2` bytes; mean `202947.53333333333` bytes.
- Post-change `peak_bytes_mean`: `204847.0`, `203285.2`, `203169.0` bytes; mean `203767.06666666665` bytes (`+819.5333333333256` bytes, within the registered 5% warning boundary).

Decision: accepted because the targeted registered diagnosis-matching submetric improved over three local Linux probe runs, path redaction also improved, and the end-to-end elapsed/peak-memory movement stayed within the registered 5% warning boundary. `diagnostic_latency_ms` was noisy (`+0.5255787012477704` ms mean, `+5.96%`) and remains a CI-observed risk for this PR-scoped probe.

## 2026-07-03 follow-up: diagnosis local bindings

This Python-only follow-up stays inside the same
`runtime-export-diagnostic-parser` registered probe and narrows to
`_diagnoses_from_excerpt(...)`. The diagnosis matcher now binds the immutable
pattern tuple, marker helper, result append, and seen-code insertion once per
call, and reuses the matched `code` value when building the diagnosis payload.
This preserves the existing matching order, first-match-per-line behavior, and
all known-code early-stop semantics while reducing repeated global/method lookup
work in the diagnosis matching loop.

Validation remains the registered focused pytest selection, changed-scope
coverage, and the registered local/CI probe for runtime export diagnostic
parsing.

Local 2026-07-03 probe decision for this diagnosis local-bindings slice:

- Baseline `elapsed_ms_mean`: `2685.6642472324893`, `2612.476917402819`, `2616.904921992682` ms; mean `2638.3486955426635` ms.
- Post-change `elapsed_ms_mean`: `2621.045644627884`, `2658.575273421593`, `2688.9616494067013` ms; mean `2656.1941891520596` ms (`+17.84549360939618` ms, within the registered 5% warning boundary).
- Baseline `diagnosis_matching_elapsed_ms_mean`: `0.656659621745348`, `0.5976887652650476`, `0.6268176017329097` ms; mean `0.6270553295811018` ms.
- Post-change `diagnosis_matching_elapsed_ms_mean`: `0.614061183296144`, `0.6148329935967922`, `0.6404992192983627` ms; mean `0.6231311320637663` ms (`-0.003924197517335516` ms, `1.0063x` faster).
- Baseline `diagnostic_latency_ms`: `8.66139295976609`, `8.858373737893999`, `8.562006056308746` ms; mean `8.693924251322945` ms.
- Post-change `diagnostic_latency_ms`: `8.328807074576616`, `8.544051903299987`, `9.234769968315959` ms; mean `8.702542982064188` ms (`+0.008618730741243085` ms, within the registered 5% warning boundary).
- Baseline `peak_bytes_mean`: `203311.2`, `204043.2`, `202703.0` bytes; mean `203352.46666666667` bytes.
- Post-change `peak_bytes_mean`: `204749.8`, `204262.8`, `204080.4` bytes; mean `204364.33333333334` bytes (`+1011.8666666666686` bytes, within the registered 5% warning boundary).

Decision: accepted because the targeted diagnosis-matching submetric improved
across the local Linux probe triplet while parser coverage stayed at 1.0, and
the end-to-end elapsed, diagnostic latency, and peak-memory movement stayed
inside the registered warning boundary. CI remains the registered PR-scoped
probe gate for the final repository signal.
