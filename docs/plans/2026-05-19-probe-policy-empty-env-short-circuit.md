# Probe Policy Empty Env Short Circuit

Date: 2026-05-19

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/productization/probe_policy.py` and the
focused tests in `services/mlx-worker-python/tests/test_probe_policy.py`.

## Registered Probe

The affected path is covered by the existing PR-scoped probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The probe
already declares focused `test_command`, `coverage_command`, and
`probe_command` entries and reports `env_parse_empty_call_ms_mean` as a
lower-is-better metric.

## Change

`ProbePolicy.from_env({})` is a hot no-op observability path in tests and
runtime callers that pass explicit scoped environment mappings. Before this
slice, the method always performed a mapping `.get()` lookup even when the
provided mapping was empty. This slice short-circuits explicit empty mappings to
the cached default policy singleton before probing the mapping.

Behavior remains unchanged: missing `MELIX_PROBE_MODE` still selects the default
mode, explicit empty values still select the default mode, invalid values still
fall back with `fallback_applied=True`, and `env=None` still reads `os.environ`.

## Verification Plan

- Run the registered focused probe-policy test command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run `scripts/probe_policy_noop_overhead_probe.py` locally and compare the
  `env_parse_empty_call_ms_mean` metric against the pre-change baseline.
- Use GitHub Actions PR-scoped performance as the merge gate after opening the
  PR.

## Linux Validation Boundary

This slice changes only Python code and is locally verifiable on Linux. No Swift
runtime performance claims are made.
