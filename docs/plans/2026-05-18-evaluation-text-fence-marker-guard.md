# Evaluation text fallback fence marker guard

## Scope

This Python-only performance slice narrows the text final-result fallback path in
`services/mlx-worker-python/worker/productization/evaluation_final_result.py`.
When a heuristic text response has no explicit answer prefix and no Markdown
fence marker, the previous path still ran the generic fence regular expression
before scanning the tail line. The optimized path first checks for the literal
fence marker and only runs the fence regex when a marker is present.

## Registered probe

The affected path is already covered by the PR-scoped
`evaluation-final-result-text-fallback-tail-scan` probe in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the product
code, regression tests, PR-scoped probe selection tests, and
`scripts/evaluation_text_fallback_probe.py`.

## Verification plan

1. Add a regression test proving marker-free text fallback does not invoke the
   generic fence scan while preserving the extracted final line.
2. Keep fenced-response behavior unchanged by retaining the existing fenced text
   tests.
3. Run the registered focused tests, changed-scope coverage command, and local
   registered probe on Linux.
4. Use the PR-scoped performance workflow as the merge gate for CI probe
   validation.

## Boundary

No Swift runtime behavior changes are included. Local validation is Linux-only
and covers the Python path directly.
