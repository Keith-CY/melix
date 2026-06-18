# Engine sampling stop-list match performance slice

This Python-only performance slice is limited to `EngineCore._sampling_with_resolved_stop` in `services/mlx-worker-python/worker/engine/engine_core.py`.

## Scope

- Preserve stop-sequence resolution semantics for empty, matching, and changed stop lists.
- Avoid tuple materialization when the protobuf repeated `sampling.stop` list already matches the resolved stop tuple.
- Keep the existing `engine-generate-usage-token-elision` PR-scoped probe as the registered probe for the touched `EngineCore` path and extend its focused commands with the non-empty stop-list reuse regression test.

## Verification plan

- Focused pytest for `_sampling_with_resolved_stop` reuse/change behavior and the registered probe tests.
- Changed-scope coverage through the registered probe `coverage_command`.
- Registered PR-scoped performance probe command for `engine-generate-usage-token-elision`.
- Local micro-benchmark comparing the old tuple materialization check against the indexed match loop on the protobuf repeated stop container.

## Metrics

The expected local effect is lower CPU time for non-empty matching stop lists. The registered probe remains the CI validation gate for the touched `EngineCore` path; local Linux metrics are reported in the PR evidence.
