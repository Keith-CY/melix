# Issue 1471 Multimodal Speculative Comparison Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add claim-safe baseline-vs-accelerated comparison artifacts for multimodal speculative decode.

**Architecture:** Reuse the existing serving-diagnostics `baseline-vs-accelerated.json` contract instead of introducing a second artifact schema. Extend the VLM benchmark comparison path so speculative-decode comparisons run the same matched baseline and accelerated sample flow as the existing image batch-1 comparison, while keeping identity, greedy-sampler, route-stability, admission, and fallback checks centralized.

**Tech Stack:** Python worker maintenance benchmark code, existing serving-diagnostics artifact writer, pytest, changed-scope coverage, PR-scoped performance probes.

---

## Scope

This plan implements GitHub issue #1471 and is governed by
`docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`.

The implementation must satisfy these acceptance criteria:

- Comparison artifacts include baseline and accelerated phase rows for prefill and decode.
- The verifier fails when prompt protocol, prompt digest, prompt template digest, model id, task kind, or generation config differ.
- Artifacts record greedy sampler status and acceleration admission/fallback reason.

## File Map

- Modify `services/mlx-worker-python/worker/engine/maintenance_core.py`.
  - Add speculative comparison execution ext constants.
  - Refactor the existing VLM comparison writer/status metrics enough to support both image batch-1 and speculative comparison names without duplicating identity validation.
  - Add `_vlm_speculative_comparison_metrics()` and `_write_vlm_speculative_comparison_artifact()`.
- Modify `services/mlx-worker-python/tests/test_maintenance_service.py`.
  - Add RED tests for the speculative artifact writer and metrics path before implementation.
  - Keep existing image batch-1 comparison tests passing.
- Modify `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`.
  - Add a Unit 4.3.1 implementation note after the behavior is implemented.
- Modify `infra/perf/pr_scoped_probes.json` only if changed files are not already covered by an existing focused probe selection.
  - If the existing VLM comparison probe is already selected for `maintenance_core.py`, keep the registry unchanged so the PR does not force all probes.

## Performance Probes And Metrics

The changed path is benchmark/evidence generation, not request serving hot-path routing. The PR-scoped performance report must select the existing `vlm-batch1-comparison-artifact` or an updated VLM comparison probe for `maintenance_core.py`.

Success metrics:

- No in-scope performance regression in the PR-scoped performance report.
- Speculative comparison metrics emit:
  - `bench.<suite>.vlm_speculative_comparison_valid`
  - `bench.<suite>.vlm_speculative_comparison_claim_blocked`
  - `bench.<suite>.vlm_speculative_comparison_identity_match`
  - `bench.<suite>.vlm_speculative_route_stability`
  - `bench.<suite>.vlm_speculative_comparison_reason_code`
  - baseline and accelerated TTFT/decode throughput rows when samples exist
  - artifact-present metric when the artifact is written

## Task 1: Add RED tests for speculative artifact writing

**Files:**

- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [ ] **Step 1: Add a speculative sample helper**

Add a helper beside `_vlm_batch1_comparison_sample()`:

```python
def _vlm_speculative_comparison_sample(
    *,
    prompt_digest: str = "sha256:prompt-a",
    status: str = "admitted",
    fallback_reason: str = "",
    runtime_active: bool = True,
    acceleration_mode: str = "speculative_decode",
) -> maintenance_core_module.BenchSample:
    return maintenance_core_module.BenchSample(
        ttft_ms=11.0 if runtime_active else 20.0,
        total_latency_ms=32.0 if runtime_active else 60.0,
        completion_tokens=4,
        decode_tokens_per_second=190.0 if runtime_active else 100.0,
        prefill_ms=11.0 if runtime_active else 20.0,
        decode_ms=21.0 if runtime_active else 40.0,
        multimodal_decode_mode="single_stream",
        multimodal_fallback_reason=fallback_reason,
        model_id="melix-dev-vlm",
        task_kind="image-text-to-text",
        prompt_protocol_id="melix.vlm.benchmark.v1",
        prompt_digest=prompt_digest,
        prompt_template_digest="sha256:template-a",
        generation_config_digest="config-a",
        generation_config_json=json.dumps(
            {"temperature": 0.0, "top_p": 1.0, "top_k": 1, "max_output_tokens": 8},
            sort_keys=True,
        ),
        route_stability_status="stable",
        acceleration_mode=acceleration_mode,
        native_acceleration_status=status,
        native_acceleration_mode="speculative_decode",
        native_acceleration_runtime_active=runtime_active,
        native_acceleration_draft_supported=True,
        native_acceleration_effective_depth=4,
        native_acceleration_request_gate="media_draft_eligible",
        native_acceleration_runtime_scope="vlm_mtp",
        native_acceleration_fallback_reason=fallback_reason,
        native_acceleration_rounds=3 if runtime_active else 0,
        native_acceleration_accepted_tokens=9 if runtime_active else 0,
        native_acceleration_rejected_tokens=3 if runtime_active else 0,
        native_acceleration_acceptance_rate=0.75 if runtime_active else 0.0,
        native_acceleration_rollback_rate=0.25 if runtime_active else 0.0,
        native_acceleration_draft_propose_ms=12.5 if runtime_active else 0.0,
        native_acceleration_target_verify_ms=25.0 if runtime_active else 0.0,
        native_acceleration_autoregressive_fallback=not runtime_active,
        native_acceleration_sampling_matches_baseline=True,
    )
```

- [ ] **Step 2: Add the RED writer test**

Add:

```python
def test_vlm_speculative_comparison_artifact_records_native_acceleration(tmp_path: Path) -> None:
    baseline = _vlm_speculative_comparison_sample(
        status="fallback",
        fallback_reason="operator_disabled",
        runtime_active=False,
        acceleration_mode="baseline",
    )
    accelerated = _vlm_speculative_comparison_sample()

    paths = MaintenanceCore._write_vlm_speculative_comparison_artifact(
        output_dir=tmp_path,
        comparison_id="cmp-speculative",
        baseline=baseline,
        accelerated=accelerated,
    )

    payload = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    assert payload["comparison_validity"] == "valid"
    assert payload["methodology"]["sampler_is_greedy"] is True
    assert payload["runs"]["baseline"]["acceleration_mode"] == "baseline"
    assert payload["runs"]["baseline"]["fallback_reason"] == "operator_disabled"
    assert payload["runs"]["accelerated"]["acceleration_mode"] == "speculative_decode"
    assert payload["runs"]["accelerated"]["acceleration_admitted"] is True
    assert payload["runs"]["accelerated"]["native_acceleration"]["runtime_active"] is True
    assert payload["runs"]["accelerated"]["native_acceleration"]["forward_counts"] == {
        "accepted_tokens": 9,
        "rejected_tokens": 3,
        "rounds": 3,
    }
    assert {row["phase"] for row in payload["phase_rows"]} == {"prefill", "decode"}
```

- [ ] **Step 3: Verify RED**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_artifact_records_native_acceleration
```

Expected: fail with `AttributeError` because `_write_vlm_speculative_comparison_artifact` does not exist.

## Task 2: Implement speculative artifact writer

**Files:**

- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`

- [ ] **Step 1: Add the writer**

Add a static method near `_write_vlm_batch1_comparison_artifact()`:

```python
@staticmethod
def _write_vlm_speculative_comparison_artifact(
    *,
    output_dir: Path,
    comparison_id: str,
    baseline: BenchSample,
    accelerated: BenchSample,
) -> dict[str, Path]:
    return write_baseline_accelerated_evidence(
        output_root=output_dir,
        comparison_id=comparison_id,
        baseline=MaintenanceCore._vlm_sample_evidence_run(
            sample=baseline,
            acceleration_mode="baseline",
        ),
        accelerated=MaintenanceCore._vlm_sample_evidence_run(
            sample=accelerated,
            acceleration_mode=accelerated.acceleration_mode or "speculative_decode",
        ),
    )
```

- [ ] **Step 2: Verify GREEN**

Run the RED test again.

Expected: pass.

## Task 3: Add RED tests for speculative comparison metrics

**Files:**

- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [ ] **Step 1: Add metrics success test**

Add:

```python
def test_vlm_speculative_comparison_metrics_writes_matched_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    core = MaintenanceCore.__new__(MaintenanceCore)
    suite = SimpleNamespace(
        suite_id="smoke",
        cases=(SimpleNamespace(prompt="what is this?", image_uris=("image.png",)),),
    )
    baseline = _vlm_speculative_comparison_sample(
        status="fallback",
        fallback_reason="operator_disabled",
        runtime_active=False,
        acceleration_mode="baseline",
    )
    accelerated = _vlm_speculative_comparison_sample()
    samples = iter((baseline, accelerated))
    seen_ext: list[dict[str, str] | None] = []

    def fake_measure(**kwargs):
        seen_ext.append(kwargs.get("execution_ext"))
        return next(samples)

    monkeypatch.setattr(core, "_measure_vlm_bench_sample", fake_measure)

    metrics = core._vlm_speculative_comparison_metrics(
        loaded_model=SimpleNamespace(),
        suite=suite,
        parameters={},
        job_id="job-1",
        source_repo="repo",
        task_kind="image-text-to-text",
        output_dir=tmp_path,
    )

    metric_by_name = {metric.name: metric for metric in metrics}
    assert metric_by_name["bench.smoke.vlm_speculative_comparison_valid"].value == 1.0
    assert metric_by_name["bench.smoke.vlm_speculative_comparison_claim_blocked"].value == 0.0
    assert metric_by_name["bench.smoke.vlm_speculative_comparison_artifact_present"].value == 1.0
    assert seen_ext == [
        {"melix.vlm.speculative_probe.enabled": "false"},
        {"melix.vlm.speculative_probe.enabled": "true"},
    ]
```

- [ ] **Step 2: Add blocked-route test**

Add:

```python
def test_vlm_speculative_comparison_metrics_blocks_when_speculative_not_runtime_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    core = MaintenanceCore.__new__(MaintenanceCore)
    suite = SimpleNamespace(
        suite_id="smoke",
        cases=(SimpleNamespace(prompt="what is this?", image_uris=("image.png",)),),
    )
    baseline = _vlm_speculative_comparison_sample(
        status="fallback",
        fallback_reason="operator_disabled",
        runtime_active=False,
        acceleration_mode="baseline",
    )
    accelerated = _vlm_speculative_comparison_sample(
        status="fallback",
        fallback_reason="unsupported_route",
        runtime_active=False,
    )
    samples = iter((baseline, accelerated))

    monkeypatch.setattr(core, "_measure_vlm_bench_sample", lambda **_kwargs: next(samples))

    metrics = core._vlm_speculative_comparison_metrics(
        loaded_model=SimpleNamespace(),
        suite=suite,
        parameters={},
        job_id="job-1",
        source_repo="repo",
        task_kind="image-text-to-text",
        output_dir=tmp_path,
    )

    metric_by_name = {metric.name: metric for metric in metrics}
    assert metric_by_name["bench.smoke.vlm_speculative_comparison_valid"].value == 0.0
    assert metric_by_name["bench.smoke.vlm_speculative_comparison_claim_blocked"].value == 1.0
    assert metric_by_name["bench.smoke.vlm_speculative_comparison_reason_code"].value == 9.0
```

- [ ] **Step 3: Verify RED**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_writes_matched_artifact services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_blocks_when_speculative_not_runtime_active
```

Expected: fail with `AttributeError` because `_vlm_speculative_comparison_metrics` does not exist.

## Task 4: Implement speculative comparison metrics

**Files:**

- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`

- [ ] **Step 1: Add constants**

Add near the existing VLM comparison constants:

```python
_VLM_SPECULATIVE_BASELINE_EXT = {"melix.vlm.speculative_probe.enabled": "false"}
_VLM_SPECULATIVE_ACCELERATED_EXT = {"melix.vlm.speculative_probe.enabled": "true"}
```

- [ ] **Step 2: Add metrics method**

Add `_vlm_speculative_comparison_metrics()` near `_vlm_batch1_comparison_metrics()`. It should:

- return `[]` when `vlm_speculative_compare` is explicitly falsey
- return blocked status metrics when `output_dir`, `job_id`, or `suite.cases` is missing
- measure the first case twice with baseline and accelerated speculative ext
- block if the accelerated sample is not `native_acceleration_runtime_active`
- write the speculative comparison artifact through `_write_vlm_speculative_comparison_artifact()`
- convert `ServingDiagnosticsComparisonError` into blocked status metrics

- [ ] **Step 3: Add status metrics helper**

Add `_vlm_speculative_comparison_status_metrics()` mirroring the existing batch-1 helper but using `vlm_speculative_*` metric names.

- [ ] **Step 4: Add reason-code helper**

Add `_vlm_speculative_comparison_reason_code()` with the same identity and sampler codes as batch-1, plus:

- `speculative_route_not_runtime_active` -> `9.0`
- `comparison_artifact_context_missing` -> `99.0`

- [ ] **Step 5: Verify GREEN**

Run the two RED metrics tests again.

Expected: pass.

## Task 5: Wire speculative metrics into VLM benchmark mode

**Files:**

- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [ ] **Step 1: Add RED integration assertion**

Extend `test_bench_events_vlm_mode_produces_vlm_metrics()` to assert that VLM benchmark events include:

```python
assert "bench.smoke.vlm_speculative_comparison_valid" in metric_names
assert "bench.smoke.vlm_speculative_comparison_claim_blocked" in metric_names
```

and default blocked values:

```python
assert metrics_by_name["bench.smoke.vlm_speculative_comparison_valid"] == 0.0
assert metrics_by_name["bench.smoke.vlm_speculative_comparison_claim_blocked"] == 1.0
```

- [ ] **Step 2: Verify RED**

Run the single integration test.

Expected: fail because the new metric names are absent.

- [ ] **Step 3: Wire metrics into `_measure_vlm_bench_metrics()`**

Append `_vlm_speculative_comparison_metrics()` to the existing comparison metrics list.

- [ ] **Step 4: Verify GREEN**

Run the single integration test again.

Expected: pass.

## Task 6: Update docs and performance probe coverage

**Files:**

- Modify: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`
- Modify if needed: `infra/perf/pr_scoped_probes.json`
- Modify if needed: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

- [ ] **Step 1: Add Unit 4.3.1 implementation note**

Record that the unit reuses the serving-diagnostics comparison artifact, records speculative native acceleration receipts, and blocks claims when identity, greedy sampling, route stability, or speculative runtime-active admission fail.

- [ ] **Step 2: Check PR-scoped probe selection**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_vlm_batch1_comparison_probe
```

The existing probe is selected by `maintenance_core.py`. Do not edit the probe
registry solely to add the new test names because registry changes intentionally
select all probes. Instead, run the explicit focused and coverage commands below
and let the existing VLM comparison probe provide scoped performance coverage.

## Task 7: Verification, coverage, commit, and PR

**Files:**

- All changed files.

- [ ] **Step 1: Run focused tests**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_artifact_records_native_acceleration \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_artifact_requires_matched_identity \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_writes_matched_artifact \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_blocks_when_speculative_not_runtime_active \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_blocks_disabled_missing_context_and_identity_errors \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_policy_and_runtime_signature_edges \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_bench_sample_passes_acceleration_policy_when_runtime_supports_it \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_reason_code_covers_blockers \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_bench_events_vlm_mode_produces_vlm_metrics
```

- [ ] **Step 2: Run changed-scope coverage**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_artifact_requires_matched_identity \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_artifact_records_route_metrics \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_metrics_blocks_missing_context_and_identity_errors \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_metrics_writes_matched_artifact \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_artifact_records_native_acceleration \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_artifact_requires_matched_identity \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_writes_matched_artifact \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_blocks_when_speculative_not_runtime_active \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_metrics_blocks_disabled_missing_context_and_identity_errors \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_policy_and_runtime_signature_edges \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_bench_sample_passes_acceleration_policy_when_runtime_supports_it \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_speculative_comparison_reason_code_covers_blockers \
  services/mlx-worker-python/tests/test_maintenance_service.py::test_bench_events_vlm_mode_produces_vlm_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py
```

Expected: changed-scope coverage at or above 95 percent.

- [ ] **Step 3: Run diff and full local gate through commit**

```bash
git diff --check
git add docs/plans/2026-07-04-issue-1471-multimodal-speculative-comparison.md \
  docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md \
  services/mlx-worker-python/worker/engine/maintenance_core.py \
  services/mlx-worker-python/tests/test_maintenance_service.py
git commit -m "Add multimodal speculative comparison artifacts"
```

Expected: pre-commit full local gate passes and scoped performance report reports `Status: ok` with no regressions.

- [ ] **Step 4: Create PR**

Use the repository PR template with `Closes #1471`, local command evidence, changed-scope coverage, and scoped performance report.

- [ ] **Step 5: Merge lifecycle**

Wait for CI, PR evidence, review threads, and performance report. Fetch `origin/main` before merge, merge `origin/main` into the branch if it advanced, re-verify if needed, then squash merge only after CI/performance report are green and there are no regressions.
