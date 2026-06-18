# Runtime utils package-version dict cache performance slice

## Scope

Optimize the Python worker runtime utility hot path for repeated installed package
version checks. The current implementation already caches successful and missing
`importlib.metadata.version()` lookups; this slice keeps that behavior but replaces
the bounded `functools.lru_cache` wrapper with a module-local dictionary lookup to
reduce per-call overhead in tight runtime metadata loops.

Behavior must remain unchanged:

- successful version lookups are cached by package name;
- missing packages cache as the empty string;
- `clear_installed_package_version_cache()` invalidates all cached package names;
- callers still receive only a string version or `""`.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`runtime-utils-package-version-cache` in `infra/perf/pr_scoped_probes.json`.
The probe watches `services/mlx-worker-python/worker/runtime/runtime_utils.py`,
includes focused `test_command`, `coverage_command`, and `probe_command` entries,
and measures `elapsed_ms_mean` plus `metadata_version_calls_mean`.

## Implementation plan

1. Reuse the existing focused cache behavior tests for success, missing-package,
   and explicit cache-clear semantics.
2. Replace `@lru_cache(maxsize=128)` on `installed_package_version()` with a
   module-local dictionary keyed by package name.
3. Keep the public cache-clear helper name stable and implement it by clearing
   the dictionary.
4. Run the registered focused tests, changed-scope coverage, and registered probe
   locally on Linux. Use the PR-scoped performance workflow as the CI validation
   source after push.

## Baseline and local probe evidence

Local Linux registered probe before the change:

```json
{"elapsed_ms_mean": 8.063814137130976, "iterations_per_sample": 60000.0, "metadata_version_calls_mean": 3.0, "package_count": 3.0, "sample_count": 5.0}
```

A five-run local comparison on the same Linux host after the virtual environment
was warm showed:

- baseline mean: `7.9760694690048695 ms`
- dict-cache mean: `7.93121799826622 ms`
- mean delta: `-0.0448514707386495 ms` (`0.5623254776421254%` faster)
- baseline median: `7.983871269971132 ms`
- dict-cache median: `7.7527957037091255 ms` (`2.8942797102844855%` faster)
- `metadata_version_calls_mean`: unchanged at `3.0`

## Success criteria

- Focused runtime-utils package-version tests pass.
- Changed-scope coverage for the touched runtime utility, tests, and probe paths
  is at least 95%.
- The registered probe keeps `metadata_version_calls_mean` at 3.0 and reduces or
  does not regress `elapsed_ms_mean`.
