# PR-scoped force-all wildcard inline loop slice

## Scope

This slice keeps the PR-scoped performance scope matcher behavior unchanged and
only tightens the force-all wildcard check used by
`worker.productization.pr_scoped_performance.build_scope_report`.

## Optimization

`build_scope_report` should normalize the changed-file list through a small LRU
cache keyed by the incoming changed-file tuple. Repeated scope builds in local
pre-commit and PR-scoped probe runs often reuse the same changed-file payload,
so the cache avoids rebuilding the de-duplicated sorted path tuple each time.

`_changed_paths_match_force_all_wildcards` should also iterate cached compiled
force-all wildcard matchers directly instead of calling the generic
`_matches_any_compiled_glob` helper for every changed path. When the caller
already has the sorted changed-path tuple produced by `build_scope_report`, the
function uses the literal prefix with `bisect_left` to skip unrelated path ranges
before checking the regex. The generic helper remains the canonical matcher for
external callers; this hot path can reuse the same prefix and regex checks
without per-path helper-call overhead.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`.
That entry defines focused `test_command`, `coverage_command`, and
`probe_command` coverage for `pr_scoped_performance.py` and the matching tests.

## Verification plan

- Run the registered focused test command for
  `pr-scoped-performance-scope-matcher`.
- Run the registered coverage command and require at least 95 percent changed
  scope coverage.
- Run the registered probe locally on Linux and compare repeated samples against
  the pre-change baseline.
- Use GitHub Actions PR-scoped performance output as the merge gate.
