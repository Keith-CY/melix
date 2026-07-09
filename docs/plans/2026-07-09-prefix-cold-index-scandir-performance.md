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

## Success metrics

- Behavior parity: valid cold entries reload, orphaned sidecars are still pruned,
  and cold hits still promote back to the hot tier.
- Coverage: changed-scope coverage for the touched helper, tests, registry, and
  probe remains at or above 95%.
- Performance: registered probe `elapsed_ms_mean` is lower than the pre-change
  glob baseline, and `path_glob_calls_mean` drops to zero.
