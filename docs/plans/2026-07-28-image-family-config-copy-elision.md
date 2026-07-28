# Image family config copy elision performance slice

## Scope

Optimize one Python hot path in `worker/runtime/image_family_adapters.py`: image
family config resolution should read caller-provided metadata as a mapping view
instead of materializing a defensive `dict` copy for every call.

## Registered probe

This slice adds the PR-scoped registered probe
`image-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe watches:

- `services/mlx-worker-python/worker/runtime/image_family_adapters.py`
- `services/mlx-worker-python/tests/test_image_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/image_family_config_probe.py`
- `docs/plans/2026-07-28-image-family-config-copy-elision.md`

The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries. The probe command keeps an inline fallback so CI can
run the same measurement against the base checkout before
`scripts/image_family_config_probe.py` exists there. The probe reports resolver
elapsed time, peak bytes, and metadata iteration calls so the no-copy behavior
is directly measurable.

## Behavior

No behavior changes are intended. Image family ID, task kind, backend ID,
workflow role, and generation/edit support resolution continue to use the same
fallbacks and validation rules.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. The CI PR-scoped
performance workflow remains the merge gate.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
