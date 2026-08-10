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

## 2026-07-28 exact bool literal follow-up

This follow-up keeps the same registered probe and narrows the behavior-preserving
change to `_bool_value()`: exact normalized bool metadata literals now return
before `strip().lower()`, while padded or mixed-case literals still flow through
the existing normalization fallback. The registered probe uses exact
`melix.image.supports_generation` and `melix.image.supports_edit` literals, so it
measures the avoided string normalization work directly.

Local Linux registered probe samples for this follow-up on this host:

- baseline `origin/main`: `1098.599725`, `1102.834226`, `1100.484947` ms; mean `1100.639633` ms.
- exact bool literal fast path: `1007.095734`, `1001.498386`, `1021.254512` ms; mean `1009.949544` ms.
- delta: `-90.690089` ms, `8.239762%` faster (`1.089797x`).
- `metadata_iteration_calls_mean`: unchanged at `0.0`; `peak_bytes_mean`: unchanged at `1160.4`.

## 2026-08-09 slotted config follow-up

This follow-up keeps the same registered probe and narrows the
behavior-preserving change to the immutable image-family dataclasses:
`ImageFamilyDescriptor`, `ImageFamilyDetection`, and
`ResolvedImageFamilyConfig` now use `slots=True`. Repeated image-family config
resolution creates `ImageFamilyDetection` and `ResolvedImageFamilyConfig` objects
on every call, so removing per-instance `__dict__` storage reduces allocation
pressure without changing fallback or validation semantics.

The focused regression test asserts these config objects no longer expose
`__dict__`, matching the text-family config pattern already used in
`worker/runtime/text_family_adapters.py`. The registered probe remains
`image-family-config-copy-elision`; its `peak_bytes_mean` and elapsed-time metrics
cover the repeated resolver allocation path.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before opening the PR. The CI PR-scoped
performance workflow remains the merge gate.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
