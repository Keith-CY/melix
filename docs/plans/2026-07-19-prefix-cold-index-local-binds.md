# Prefix cold index local-bind reload slice

## Scope

This Python-only performance slice is limited to `ColdPrefixStore._ensure_loaded_locked()` cold-index reloads in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`.

The previous implementation already used one `os.scandir()` pass, filename-sidecar orphan prechecks, and JSON byte loading. This slice keeps that behavior intact while reducing repeated global and attribute lookups inside the per-metadata loop. It also delays `Path` construction until after a metadata payload has passed the snapshot-name check, so malformed or post-decode orphan sidecars can be removed by string path without allocating a `Path` object.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports cold-index reload elapsed time plus JSON-load, `Path.glob`, and `os.scandir` call counts.

## Optimization plan

1. Keep the existing `os.scandir()` index rebuild and filename orphan precheck.
2. Bind the hot-loop helpers (`_OPEN`, `json.loads`, `_session_digest`, `_normalize_kv_quant_profile`, `_remove_path_string_quietly`, `ColdEntryMeta`, `self._root`, and `self._index`) once before iterating metadata sidecars.
3. Use `payload.get` locally when building `ColdEntryMeta`.
4. Remove malformed or orphaned metadata sidecars with `_remove_path_string_quietly()` when a `Path` object is not otherwise needed.
5. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the registered probe merge gate.

## Validation notes

This slice is locally verifiable on Linux. No Swift runtime effect is claimed.
