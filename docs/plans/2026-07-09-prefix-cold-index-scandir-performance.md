# Prefix cold index scandir performance slice

## Context

The native MTP prompt-prefix cold tier reloads `.meta.json` sidecars when a
`ColdPrefixStore` is first consulted after worker startup. The previous reload
path used `Path.glob("*.meta.json")`, which allocates glob machinery and `Path`
objects before filtering entries. The reload only needs one non-recursive pass
over the cold tier root.

## Scope

This slice covers only `services/mlx-worker-python/worker/runtime/prefix_block_store.py`'s
cold prefix sidecar index load. It does not change hot prefix matching,
demotion/promotion semantics, snapshot serialization, or active KV quantization
matching.

## Probe registration

The slice registers `prefix-cold-index-scandir` in
`infra/perf/pr_scoped_probes.json` with focused test, coverage, and command-json
probe commands. The probe builds a synthetic cold tier, reloads the sidecar index
multiple times, and records elapsed time plus traversal call counts.

## Implementation plan

1. Add a regression test proving cold sidecar index load uses a single
   `os.scandir` pass without `Path.glob` while preserving reload behavior.
2. Replace the non-recursive `Path.glob("*.meta.json")` reload with an explicit
   `os.scandir` pass that keeps hot traversal state as strings, ignores entries
   with transient metadata errors, and preserves deterministic sorted processing.
3. Add and register the focused cold-index reload performance probe.
4. Validate with focused tests, changed-scope coverage, and the registered probe
   locally on Linux; rely on PR-scoped CI to replay the registered probe.

## 2026-07-09 JSON stream follow-up

This follow-up Python-only slice keeps the same `prefix-cold-index-scandir`
probe boundary and limits behavior changes to cold prefix sidecar reload. After
the scandir rewrite, the reload still constructed a `Path`, read the full JSON
text into a temporary string, and then parsed it with `json.loads(...)` for every
sidecar. This slice binds `builtins.open` once and streams each sidecar through
`json.load(...)` from the existing string path, preserving deterministic sorted
processing, orphan pruning, and corrupt-sidecar removal while avoiding the
per-sidecar JSON text allocation.

## Success metrics

- Behavior parity: valid cold entries reload, orphaned sidecars are still pruned,
  and cold hits still promote back to the hot tier.
- Coverage: changed-scope coverage for the touched helper, tests, registry, and
  probe remains at or above 95%.
- Performance: registered probe `elapsed_ms_mean` is lower than the pre-change
  cold-index reload path, and `path_glob_calls_mean` remains zero.

## 2026-07-25 JSON load handle follow-up

This follow-up keeps the same registered `prefix-cold-index-scandir` probe and
narrows the slice to sidecar JSON parsing inside `ColdPrefixStore._ensure_loaded_locked`.
The loader now passes the already-open binary file handle directly to
`json.load(...)` instead of materializing the full sidecar bytes object and then
calling `json.loads(...)`. Orphan prechecks, corrupt-sidecar cleanup, snapshot
name reuse, and token-id coercion remain unchanged.

Acceptance requires the focused cold-tier tests, changed-scope coverage, and the
registered Linux probe to pass locally, then the PR-scoped CI probe to complete
successfully before merge.
