# Runtime Utils Kwarg Accepts Inline Membership

## Scope

This Python-only performance slice is limited to the cached callable keyword
signature hot path in `services/mlx-worker-python/worker/runtime/runtime_utils.py`.
It preserves the public `CallableKwargSignature.declares()` and `accepts()` APIs,
cache behavior, package-version helpers, and model-weight scanning behavior.

## Registered probe

The affected path is covered by the registered PR-scoped performance probes in
`infra/perf/pr_scoped_probes.json` for `runtime_utils.py`. The primary probe for
this slice is `runtime-utils-kwarg-signature-cache`, which includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports
`elapsed_ms_mean` plus `inspect_signature_calls_mean`. This slice also keeps the
probe command on `python3` for the checked-in probe script path so local and CI
validation follow the repository interpreter policy.

## Optimization hypothesis

`callable_accepts_kwarg()` is the hot cached-path caller in generation and
runtime adapter setup. Once a callable signature is cached, `accepts()` only needs
a membership check in the cached keyword set plus the var-keyword flag. Inlining
that membership check avoids the extra Python method call through `declares()` on
every cached `accepts()` query while preserving the exact result for declared
keywords and `**kwargs` callables.

## Validation plan

1. Run the registered focused runtime-utils test command locally on Linux.
2. Run the registered changed-scope coverage command locally and require at least
   95% coverage for touched scope.
3. Run `scripts/runtime_utils_kwarg_cache_probe.py` before and after the change
   and compare `elapsed_ms_mean`; `inspect_signature_calls_mean` must remain 1.0.
4. Use the GitHub PR-scoped performance workflow as the final registered probe
   gate before merge.
