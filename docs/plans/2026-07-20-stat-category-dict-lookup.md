# Statistical evidence category dict lookup slice

## Context

`worker.productization.statistical_evidence.build_category_breakdown()` is used by evaluation report evidence assembly to aggregate many per-sample category rows into sorted category summaries. The hot loop receives repeated category labels, so most row visits update an existing totals bucket.

## Slice

This Python-only performance slice is limited to the category totals lookup in `build_category_breakdown()`. It keeps row parsing and output semantics unchanged while replacing the existing `dict.get()` plus `None` branch with a direct dictionary lookup and `KeyError` miss path. In the registered probe shape, category buckets are created once and then reused for tens of thousands of rows, so the direct lookup avoids the per-row sentinel comparison on the hot hit path.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `statistical-evidence-category-breakdown-single-pass` in `infra/perf/pr_scoped_probes.json`. The same file also selects `statistical-evidence-bootstrap-single-sort`, so both registered statistical-evidence probes remain part of the local and CI evidence for this slice.

Expected direction for `statistical-evidence-category-breakdown-single-pass`: lower `elapsed_ms_mean`; `peak_bytes_mean` should stay within the existing threshold.

## Verification

Run the registered focused test command, changed-scope coverage command, and registered probe command locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the final merge gate.
