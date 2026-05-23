# Event similarity bigram total cache

## Goal

Reduce repeated semantic event similarity scoring overhead by caching each normalized string's character-bigram total alongside the already cached bigram item tuple.

## Scope

This Python-only performance slice is limited to:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`

It preserves existing string similarity semantics and does not change event extraction prompts, scoring thresholds, protobuf schemas, or dependencies.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `event-extraction-alignment-accepted-edge-cache` in `infra/perf/pr_scoped_probes.json`. Its probe script includes `similarity_elapsed_ms_mean`, which exercises repeated `_string_similarity()` calls over deterministic text pairs.

## Proposed Change

1. Add a cached `_character_bigram_stats()` helper that returns both bigram items and their total count.
2. Make `_bigram_dice()` consume the cached total instead of summing cached item tuples on every comparison.
3. Keep `_character_bigram_items()` for compatibility by returning the item portion from the stats helper.
4. Extend the focused event extraction test to assert the new cached stats helper matches the existing bigram output.

## Verification

- Focused event extraction test covering string similarity cache behavior.
- Registered probe commands for `event-extraction-alignment-accepted-edge-cache`, including focused tests, changed-scope coverage, and local Linux probe metrics.
- `git diff --check`.

## Linux Boundary

This is a Python worker change and is locally verifiable on Linux. No Swift runtime effect is claimed.
