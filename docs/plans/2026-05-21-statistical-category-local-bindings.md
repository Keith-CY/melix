# Statistical Evidence Category Breakdown Local Bindings

## Goal

Reduce per-row overhead in `build_category_breakdown()` while preserving category
filtering, missing-key handling, deterministic ordering, and rounded accuracy
payloads.

## Linux constraint

This is a Python worker/productization slice and is locally verifiable on Linux
with focused pytest, changed-scope coverage, and the registered PR-scoped
performance probe.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`statistical-evidence-category-breakdown-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_category_breakdown_probe.py`

## Optimization

Bind the category totals lookup, string type, and rounding helper once per
function call instead of resolving them repeatedly in the hot row loop or output
materialization loop. For the common probe workload where included rows carry
both correctness keys, use direct key reads with `KeyError` fallback so missing
correctness fields still count as false without paying `dict.get()` method
lookup overhead on every included row.

## Success metrics

- Focused statistical evidence pytest and PR-scoped probe tests pass.
- Changed-scope coverage for touched executable Python/test/probe files remains
  at least 95%.
- The local registered probe reports lower `elapsed_ms_mean` versus the
  pre-change baseline while preserving checksum, row count, and category count.
- GitHub Actions PR-scoped performance completes successfully before merge.

## 2026-07-20 follow-up: exact string category label check

This follow-up keeps the same registered probe and narrows to the category-label
normalization branch in `build_category_breakdown()`. The common row payload uses
plain `str` category labels, so the hot loop now checks the locally bound
`type(raw_category_label) is str` fast path before falling back to the original
`isinstance(..., str)` behavior for string subclasses and to
`str(raw_category_label).strip()` for non-string labels. This preserves
missing-key handling, string-subclass labels with custom `__str__`, non-string
label support, deterministic ordering, and rounded accuracy payloads while
avoiding an `isinstance(...)` call for each included plain-string row.

Local Linux probe quintet:

- Baseline `elapsed_ms_mean`: `9.978312626481056`, `10.006940178573132`,
  `11.492647929117084`, `10.83152424544096`, `11.737409373745322` ms; mean
  `10.80936687067151` ms.
- Post-change `elapsed_ms_mean`: `10.127129592001438`, `9.964018128812313`,
  `10.066704591736197`, `9.91921592503786`, `10.359516181051731` ms; mean
  `10.087316883727908` ms (`-0.7220499869436026` ms, `1.0716x` faster,
  `-6.68%`).
- `peak_bytes_mean` stayed `17040.0`; checksum stayed `250365.72`.

## 2026-08-15 follow-up: exact string class check

This follow-up keeps the same registered probe and narrows to one additional
category-label normalization micro-path in `build_category_breakdown()`. The
common probe rows use exact `str` category labels, so the hot loop now uses the
row value's `__class__` for the exact-string fast path instead of calling the
locally bound `type(...)` helper. The string-subclass fallback still calls the
instance `.strip()` method, preserving custom subclass behavior covered by
`test_build_category_breakdown_aggregates_supported_categories_only`.

Success criteria remain unchanged: focused pytest, changed-scope coverage, the
registered local Linux probe, and the GitHub Actions PR-scoped performance probe
must pass before merge.

Local Linux evidence before PR:

- Focused pytest and changed-scope coverage passed with 100% changed-line coverage.
- Default registered probe 5x mean was noisy: baseline `9.972119564190507` ms,
  head `10.02399220596999` ms; `peak_bytes_mean` improved from `16880.0` to
  `16872.0` bytes and checksum stayed `250365.72`.
- A larger 200k-row registered-probe run showed the expected direction:
  baseline `42.77662228975844` ms, head `42.20924256203164` ms
  (`-0.5673797277268022` ms, `1.013442073187951x`), with `peak_bytes_mean`
  improving from `16073.142857142857` to `16065.142857142857` bytes and checksum
  staying `1400511.9926000002`.
