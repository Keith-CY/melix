# LoRA Module 2 — Adapter-native evaluation compare (issue #13)

## Context

Issue [#13](https://github.com/Keith-CY/melix/issues/13) implements Module 2 from `docs/plans/2026-04-16-lora-capability-modules-and-commit-plan.md`: teach `eval compare` to accept adapter targets directly instead of forcing every target to be pre-materialized as a long-lived loaded model.

Today `resolve_compare_target_models` at `services/mlx-worker-python/worker/productization/evaluation_compare.py:36-54` hard-requires each compare target to exist as a pre-loaded registry entry. That defeats the "one base vs many adapters" workflow — operators have to manually activate each adapter into a long-lived derived model before compare will accept it. Module 1 (PRs #52 + #53) established runtime truth for adapter-backed models; Module 2 now teaches compare to leverage it.

**Gap to close**: accept adapter manifest paths directly, materialize each as an **ephemeral** registry entry for the compare run only, and record adapter lineage in committed compare artifacts so downstream exports preserve which adapter produced which target column.

## Scope

**In:**

- **Slice 2.1** — Adapter-target request contract + CLI surface. New `AdapterTargetSpec` dataclass + `parse_compare_target_adapter_manifest_paths` helper in `evaluation_compare.py`; new repeatable `--target-adapter PATH` flag on `eval compare`.
- **Slice 2.2** — On-demand materialization. New `resolve_compare_target_adapters(registry, specs, job_id)` that reads each adapter manifest, builds an ephemeral `ModelSpec` with `runtime_mode=RUNTIME_MODE_ADAPTER_BACKED`, and calls `registry.load_model`. `_run_compare_suite` wraps the evaluation loop in `try/finally` so ephemerals always unload.
- **Slice 2.3** — Persist lineage. New `EvaluationCompareTargetLineage` dataclass; `EvaluationCompareJob.target_lineage`; two new CSV columns on the compare samples export (`target_adapter_manifest_path`, `target_adapter_set_hash`).

**Out:**

- Env-gated real-model compare run — Module 1's integration test already proves adapter-backed inference end-to-end.
- Training / activation changes (Modules 3+).
- Proto schema changes — Module 2 rides on the `parameters` dict + Module 1's enum.
- Hub dataset changes — compare already supports HF datasets.

## Design

### Ephemeral derived model ids

`{source_model}-lora-{adapter_set_hash[:8]}-compare-{job_id_short}` — the `-compare-` segment makes the entry visually distinct from permanent adapter activations; the `job_id_short` disambiguates concurrent compares on the same adapter. `try/finally` cleanup guarantees the ephemeral entry is gone before the compare RPC returns.

### Module 1 reuse

The ephemeral `ModelSpec` sets `runtime_mode = RUNTIME_MODE_ADAPTER_BACKED`; Module 1's `_is_adapter_backed_spec` picks this up first and `AutoMLXBackend.load_model` forwards `adapter_path` to `mlx_lm.load()`. No custom load path — the full wiring PR #52 landed carries over.

### Memory budget

`registry.load_model` enforces `process_memory_budget_bytes` already. Loading N adapter targets simultaneously surfaces `MemoryBudgetExceeded` if it exceeds the budget — same user-facing contract as loading N fused derived models.

## Critical files

```
services/mlx-worker-python/worker/productization/evaluation_compare.py   (~80 lines)
services/mlx-worker-python/worker/productization/evaluation_schemas.py   (~50 lines)
services/mlx-worker-python/worker/productization/evaluation_store.py     (~30 lines)
services/mlx-worker-python/worker/engine/evaluation_core.py              (~40 lines)
services/mlx-worker-python/tests/test_evaluation_core.py                 (~250 lines)
services/mlx-worker-python/tests/test_evaluation_store.py                (~80 lines)
Sources/MelixCLICore/MelixCLI.swift                                      (~25 lines)
Tests/MelixCLITests/MelixCLIParserTests.swift                            (~60 lines)
Tests/MelixCLITests/MelixCLIRunnerTests.swift                            (~40 lines)
```

## Verification

1. `make py-test` — all existing tests stay green; new unit tests pass.
2. `make swift-test` — all existing tests stay green; new parser + runner tests pass.
3. `make proto-check` — clean (no proto changes).
4. `make phase8-real-e2e` — unchanged; Module 2 is additive.

## Risks

- **Registry leak on crash.** `finally` unloads ephemerals on normal + exception paths; SIGKILL loses them with the process (acceptable).
- **Concurrent compare collision.** `job_id_short` in the ephemeral id disambiguates; unit-tested.
- **Adapter manifest trust.** Operator-supplied manifest paths flow into `load_model` — same trust posture as `--target-model-id` referencing an operator-edited catalog entry; no new attack surface.
- **CSV column drift.** New columns land at the end of the header row, preserving existing column order for downstream parsers.
- **Memory budget.** Loading N adapters concurrently surfaces `MemoryBudgetExceeded` cleanly — documented operator-facing behavior.
