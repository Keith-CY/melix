# Changed-scope coverage singleton range branch elision

This Python-only performance slice is limited to `scripts/changed_scope_coverage.py` and the registered `changed-scope-coverage-singleton-range-fastpath` PR-scoped probe.

## Scope

- Keep changed-line coverage semantics unchanged.
- Avoid the sorted-list fallback branch for the common singleton changed-line path when coverage line lists are already ascending.
- Do not change probe selection, registry behavior, or coverage thresholds.

## Registered probe

The affected path is covered by `infra/perf/pr_scoped_probes.json` entry `changed-scope-coverage-singleton-range-fastpath`, which includes focused `test_command`, `coverage_command`, and `probe_command` values for Linux validation.

## Verification plan

1. Run focused changed-scope coverage tests plus PR-scoped registry tests.
2. Run the registered changed-scope coverage command for the touched files.
3. Run `python3 scripts/changed_scope_coverage_singleton_probe.py` locally on Linux and compare with the pre-change baseline.
4. Use GitHub Actions PR-scoped performance as the merge gate after the PR is opened.

## Local baseline and candidate result

Before the change on `origin/main` (`8a34100ad73c34f7fbc9cb6d7c4d091eb906f74f`), three local probe runs returned singleton elapsed means of approximately `0.541042 ms`, `0.508871 ms`, and `0.527198 ms` with `source_read_calls_mean=0.0` (`old_mean=0.525704 ms`).

After the change, seven stable local probe runs returned `new_mean=0.507185 ms`, `delta_ms=-0.018519`, `speedup=1.036513x`, and `source_read_calls_mean=0.0`.
