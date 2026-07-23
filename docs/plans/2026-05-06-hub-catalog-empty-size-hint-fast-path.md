# Hub Catalog Size-Hint Multiplier Constants

## Goal

Avoid repeated power-expression evaluation while parsing Hub catalog model-size hints by reusing module-level byte multiplier constants for KB, MB, and GB units.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Linux-Only Constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance Probe

Use the existing registered probe:

- `hub-catalog-size-hint-regex-precompile`

The probe builds synthetic Hub catalog size-hint payloads and exercises both direct `cardData.model_size` parsing and labeled text parsing. The registered probe has focused `test_command`, `coverage_command`, and `probe_command` entries in `infra/perf/pr_scoped_probes.json`.

## 2026-07-09 exact MLX tag membership slice

This follow-up Python-only slice stays within `services/mlx-worker-python/worker/model_ops/hub_catalog.py` and the registered `hub-catalog-size-hint-regex-precompile` PR-scoped probe. It narrows `_tag_payload_contains_mlx(...)` by checking exact `"MLX"` / `"mlx"` list membership before falling back to per-item mixed-case atom checks. Behavior remains identical for exact tags, mixed-case tags, list subclasses, string payloads, and non-string tag payloads; the slice only avoids repeated Python-level tag iteration in the common exact-tag Hub compatibility path.

## 2026-07-16 common suffix direct size-hint slice

This follow-up Python-only slice keeps the same registered probe and narrows to
`_direct_size_hint_from_text(...)`. The common Hub model-size strings use a
single ASCII space followed by uppercase or lowercase `KB` / `MB` / `GB`, so the
direct parser now checks that three-character suffix first. Mixed-case units,
tab-separated units, trailing whitespace, and other uncommon valid formats still
fall through to the existing full scanner, preserving parser behavior while
reducing work for the repeated common-card/readme size-hint probe workload.

## Success Metrics

- Focused Hub catalog tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- The local base-vs-head registered probe reports behavior parity and lower mean elapsed time for the size-hint workload.

## Implementation Plan

1. Add module-level byte multiplier constants and reuse them in `_direct_size_hint_from_text(...)` and `_size_hint_from_text(...)`.
2. Extend the focused size-hint parser test to cover KB, fractional MB, and GB through both direct and regex-backed paths.
3. Run focused pytest, changed-scope coverage, `git diff --check`, and the registered local probe before opening the PR.

## 2026-07-16 explicit-line span parse slice

This follow-up Python-only slice keeps the same registered probe and narrows to
`_direct_size_hint_from_line(...)`, which is used by direct explicit Hub card and
README size-hint parsing. Common size-hint lines that end with a single ASCII
space plus `KB` / `MB` / `GB` or lowercase variants now parse directly from the
original text span instead of slicing a temporary line string before delegating to
`_direct_size_hint_from_text(...)`. Uncommon valid formats, including mixed-case
units, tab-separated units, and trailing whitespace, still fall back to the
existing full direct parser on the sliced span, preserving behavior while reducing
allocation and dispatch in the repeated registered size-hint workload.

## 2026-07-17 uppercase cursor decode slice

This follow-up Python-only slice keeps registered probe coverage through
`hub-catalog-next-cursor-fast-parse` and narrows to
`_unquote_plus_ascii_cursor(...)`, which decodes Hub pagination cursors extracted
from the `Link` header. The common Hugging Face cursor encoding observed by the
registered probe uses uppercase `%2F` and `%2B` escapes, so the decoder now tries
those replacements first and returns before the lowercase escape pass when the
cursor is fully decoded. Lowercase escapes, Unicode percent escapes, malformed
percent sequences, and plus-to-space decoding still fall through to the existing
lowercase or general decoding paths, preserving cursor behavior while reducing
string replacement work for the common uppercase cursor path.

## 2026-07-23 README table model-size prefix slice

This follow-up Python-only slice keeps the same registered
`hub-catalog-size-hint-regex-precompile` probe and narrows to
`_direct_explicit_size_hint_from_text(...)`. Hub README metadata commonly starts
with a short heading followed immediately by a `MODEL SIZE | ...` table-style
line. Checking the exact `README\nMODEL SIZE | ` prefix before the broader marker
search preserves all fallback marker parsing while avoiding redundant substring
searches for that common registered-probe shape.
