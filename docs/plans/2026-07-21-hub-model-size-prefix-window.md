# Hub catalog model-size prefix window

## Scope

This Python-only performance slice is limited to
`worker.model_ops.hub_catalog._direct_explicit_size_hint_from_text()`.

The Hub size-hint parser commonly receives README snippets where the canonical
`Model size: ...` marker appears near the beginning of the text. The existing
fallback searched for the uppercase pipe form before checking this common title
case marker. This slice checks for `Model size: ` in an initial bounded window
before the less common uppercase pipe marker, preserving the generic fallback for
later or differently cased markers.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

This slice targets the `elapsed_ms_mean` size-hint parser metric while keeping
`size_hint_calls_mean`, checksum, and match counts unchanged.

## 2026-07 marker order follow-up

This follow-up Python-only slice stays within
`worker.model_ops.hub_catalog._may_contain_model_marker()` and the same
registered `hub-catalog-size-hint-regex-precompile` probe. The marker guard now
checks the common `Model size` and uppercase `MODEL SIZE` adjacent-prefix forms
before the rarer lowercase/mixed-case alternatives. Behavior remains unchanged
for all four case combinations; the slice only reduces average failed membership
scans before the direct size-hint parser runs on common README metadata.

## 2026-08 exact card-label span follow-up

This follow-up Python-only slice stays within
`worker.model_ops.hub_catalog._direct_card_size_hint_from_text()` and the same
registered `hub-catalog-size-hint-regex-precompile` probe. Exact `MODEL SIZE:`
/ `MODEL SIZE|` / `Model size: ` card metadata labels now parse the numeric span
in the original string instead of slicing the tail and re-entering the generic
substring parser. Behavior remains unchanged for exact labels and the generic
fallback remains in place for less common label shapes.

## 2026-08 direct span integer accumulation follow-up

This follow-up Python-only slice stays within
`worker.model_ops.hub_catalog._direct_size_hint_from_span()` and the same
registered `hub-catalog-size-hint-regex-precompile` probe. Exact integer spans
with `KB`/`MB`/`GB` suffixes now parse the original character range directly,
avoiding the temporary three-character unit slice, numeric substring, and
`str.isdecimal()` scan. Decimal and malformed spans keep the existing fallback
semantics through the generic direct size-hint parser.

## Implementation plan

1. Keep the regex fallback and the direct uppercase pipe marker path intact.
2. Add a bounded early search for the common `Model size: ` README marker.
3. Reuse the existing size-hint tests that guard direct parsing and regex
   fallback behavior.
4. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.
6. For the 2026-08 follow-up, add a regression test proving exact card labels use
   span parsing without calling the substring parser.

## Success criteria

- Focused Hub catalog tests pass.
- Changed-scope coverage for touched Python paths remains at least 95%.
- The registered local probe reports unchanged `size_hint_calls_mean`, checksum,
  and match count with directionally lower `elapsed_ms_mean`.
- GitHub Actions and the registered PR-scoped performance report complete
  successfully before merge.
