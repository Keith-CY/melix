# Probe policy factory static dispatch slice

## Scope

This Python-only performance slice targets the no-op probe policy helper path in
`services/mlx-worker-python/worker/productization/probe_policy.py`. The affected
path is covered by the registered PR-scoped probe `probe-policy-noop-overhead` in
`infra/perf/pr_scoped_probes.json`, which has focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Change

Keep `ProbePolicy.evidence()` and `ProbePolicy.debug()` behavior unchanged while
using static dispatch for the cached singleton helpers. These helpers do not use a
class object, so avoiding classmethod binding removes unnecessary descriptor work
from the hot no-op policy overhead probe.

## Verification plan

- Run focused probe policy tests and PR-scoped probe registry tests.
- Run changed-scope coverage through the registered `coverage_command`.
- Run the registered probe policy no-op overhead probe locally on Linux and
  compare `evidence_policy_call_ms_mean` and `debug_policy_call_ms_mean` against
  `origin/main` with the same iteration and sample counts.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claims are made.
