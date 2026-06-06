# Local Job Remediation Policies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable local-job log diagnosis and remediation contract with bounded retry decisions and operator-safe receipts.

**Architecture:** The Python worker owns local job execution truth, job manifests, and receipt payloads, so the first slice adds a small `worker.model_ops.local_job_remediation` module that can be reused by download, training, serving, and desktop projections. The module stays side-effect-free: it classifies logs, chooses a bounded remediation decision, and builds a redacted receipt; callers remain responsible for actually executing commands or mutating settings. Documentation records the operator contract and performance probes so later CLI/UI integrations share the same schema.

**Tech Stack:** Python 3.12, pytest, dataclasses, repository changed-scope coverage tooling, PR-scoped performance tooling.

---

## Files

- Create `services/mlx-worker-python/worker/model_ops/local_job_remediation.py`
  - Holds diagnosis codes, remediation operation types, retry policy input/output, redaction, log excerpt selection, and receipt serialization.
- Create `services/mlx-worker-python/tests/test_local_job_remediation.py`
  - Covers fixture logs for memory OOM, port conflict, missing dependency, gated model access, invalid accelerator selection, bounded retries, dry-run/explain, and auto-remediation disabled receipts.
- Create `docs/runbooks/local-job-remediation.md`
  - Defines the operator-facing local-job diagnosis, retry, dry-run, disabled-auto-remediation, and receipt contract.
- Modify `docs/README.md`
  - Adds the new runbook to the runbook index.

## Performance Probes and Success Metrics

- Classification must scan a bounded excerpt, not an unbounded full log. The implementation trims logs to the last 16 KiB by default.
- Receipt payloads must redact token-like values before serialization.
- Changed-scope Python coverage for the new module and tests must be at least 95%.
- PR-scoped performance report must show `Status ok` and zero direct/gated regressions.

## Task 1: Add Failing Tests for Diagnosis and Policy

**Files:**
- Create: `services/mlx-worker-python/tests/test_local_job_remediation.py`

- [ ] **Step 1: Write the failing tests**

Add pytest coverage that expects:

```python
from worker.model_ops.local_job_remediation import (
    LocalJobRemediationPolicy,
    classify_local_job_failure,
    local_job_remediation_receipt,
)


def test_classifier_maps_common_runtime_logs_to_typed_diagnoses() -> None:
    cases = [
        (
            "RuntimeError: KV cache needs 54.0 GiB but only 8.0 GiB is available",
            "memory_oom",
            "retry_with_changed_flag",
        ),
        (
            "OSError: [Errno 48] Address already in use while binding 127.0.0.1:12436",
            "port_conflict",
            "retry_with_changed_flag",
        ),
        (
            "ModuleNotFoundError: No module named 'sentencepiece'",
            "missing_dependency",
            "dependency_install",
        ),
        (
            "401 Client Error. Cannot access gated repo. You must be authenticated to access this model.",
            "gated_model_access",
            "manual_action",
        ),
        (
            "RuntimeError: invalid device ordinal: GPU index 8 is not available",
            "invalid_accelerator_selection",
            "settings_change",
        ),
    ]

    for log_text, expected_code, expected_operation in cases:
        diagnosis = classify_local_job_failure(log_text, command=["melix", "serve"])

        assert diagnosis is not None
        assert diagnosis.code == expected_code
        assert diagnosis.remediation.operation_type == expected_operation
        assert diagnosis.remediation.summary
```

```python
def test_remediation_receipt_records_bounded_retry_decision_and_redacts_logs() -> None:
    receipt = local_job_remediation_receipt(
        command=["melix", "serve", "--hf-token", "hf_secret_1234567890"],
        log_text="HF_TOKEN=hf_secret_1234567890\nOSError: [Errno 48] Address already in use",
        policy=LocalJobRemediationPolicy(max_retries=2),
        attempt_index=0,
        outcome="planned",
    )

    assert receipt["schema_version"] == "melix.local_job_remediation_receipt.v1"
    assert receipt["command"] == ["melix", "serve", "--hf-token", "[REDACTED]"]
    assert receipt["diagnosis"]["code"] == "port_conflict"
    assert receipt["remediation"]["operation_type"] == "retry_with_changed_flag"
    assert receipt["decision"] == {
        "mode": "auto",
        "will_retry": True,
        "reason": "retry_budget_available",
        "attempt_index": 0,
        "max_retries": 2,
        "dry_run": False,
        "auto_remediation_enabled": True,
    }
    assert "hf_secret" not in receipt["redacted_log_excerpt"]
```

```python
def test_retry_budget_dry_run_and_disabled_auto_remediation_stop_execution() -> None:
    log_text = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB"

    exhausted = local_job_remediation_receipt(
        command=["melix", "train"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(max_retries=1),
        attempt_index=1,
        outcome="blocked",
    )
    dry_run = local_job_remediation_receipt(
        command=["melix", "train"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(max_retries=1, dry_run=True),
        attempt_index=0,
        outcome="explained",
    )
    disabled = local_job_remediation_receipt(
        command=["melix", "train"],
        log_text=log_text,
        policy=LocalJobRemediationPolicy(max_retries=1, auto_remediation_enabled=False),
        attempt_index=0,
        outcome="blocked",
    )

    assert exhausted["decision"]["will_retry"] is False
    assert exhausted["decision"]["reason"] == "retry_budget_exhausted"
    assert dry_run["decision"]["will_retry"] is False
    assert dry_run["decision"]["mode"] == "dry_run"
    assert dry_run["decision"]["reason"] == "dry_run_explain_only"
    assert disabled["decision"]["will_retry"] is False
    assert disabled["decision"]["mode"] == "disabled"
    assert disabled["decision"]["reason"] == "auto_remediation_disabled"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_local_job_remediation.py
```

Expected: FAIL because `worker.model_ops.local_job_remediation` does not exist.

## Task 2: Implement Local Job Remediation Core

**Files:**
- Create: `services/mlx-worker-python/worker/model_ops/local_job_remediation.py`

- [ ] **Step 1: Implement the public model and classifier**

Implement frozen dataclasses:

```python
@dataclass(frozen=True, slots=True)
class LocalJobRemediation:
    operation_type: str
    summary: str
    action: str
    retryable: bool
    changed_flags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LocalJobFailureDiagnosis:
    code: str
    summary: str
    remediation: LocalJobRemediation
    matched_pattern: str


@dataclass(frozen=True, slots=True)
class LocalJobRemediationPolicy:
    max_retries: int = 1
    dry_run: bool = False
    auto_remediation_enabled: bool = True
    excerpt_bytes: int = 16 * 1024
```

Add `classify_local_job_failure(log_text: str, *, command: Sequence[str] = ()) -> LocalJobFailureDiagnosis | None` with ordered pattern families:

- `memory_oom`: `kv cache`, `out of memory`, `cuda out of memory`, `metal`, `allocation failed`; remediation `retry_with_changed_flag`, retryable, suggested flags such as lower context or batch size.
- `port_conflict`: `address already in use`, `eaddrinuse`, `port is already in use`; remediation `retry_with_changed_flag`, retryable, suggested `--port=<available-port>`.
- `missing_dependency`: `modulenotfounderror`, `no module named`, `command not found`; remediation `dependency_install`, not retryable without operator action.
- `gated_model_access`: `gated repo`, `401 client error`, `403 client error`, `hf token`, `authentication`; remediation `manual_action`, not auto-retryable.
- `invalid_accelerator_selection`: `invalid device ordinal`, `gpu index`, `no such device`, `accelerator`; remediation `settings_change`, not auto-retryable.

- [ ] **Step 2: Implement bounded decisions and receipts**

Add `local_job_remediation_receipt(...) -> dict[str, Any]` that returns:

- schema version `melix.local_job_remediation_receipt.v1`
- redacted command list
- redacted bounded log excerpt
- diagnosis object
- remediation object
- decision object with `mode`, `will_retry`, `reason`, `attempt_index`, `max_retries`, `dry_run`, and `auto_remediation_enabled`
- `outcome`

Redact `HF_TOKEN=...`, `HUGGINGFACE_HUB_TOKEN=...`, `--hf-token VALUE`, and strings starting with `hf_`.

- [ ] **Step 3: Run focused tests**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_local_job_remediation.py
```

Expected: PASS.

## Task 3: Document Operator Contract

**Files:**
- Create: `docs/runbooks/local-job-remediation.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Add runbook**

Document:

- the schema name and field-level receipt shape
- diagnosis codes and operation types
- bounded retry behavior
- dry-run/explain behavior
- disabled auto-remediation behavior
- redaction and log excerpt bounds
- verification commands

- [ ] **Step 2: Add README entry**

Add `Local Job Remediation` to the runbook table in `docs/README.md`.

## Task 4: Verify, Commit, PR, and Merge

- [ ] **Step 1: Run focused tests**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_local_job_remediation.py
```

- [ ] **Step 2: Run changed-scope coverage**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run --data-file=.runtime/coverage/local_job_remediation.coverage -m pytest -q services/mlx-worker-python/tests/test_local_job_remediation.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json --data-file=.runtime/coverage/local_job_remediation.coverage -o .runtime/coverage/local_job_remediation.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python scripts/python_changed_line_coverage.py --diff-from origin/main --coverage-json .runtime/coverage/local_job_remediation.json services/mlx-worker-python/worker/model_ops/local_job_remediation.py services/mlx-worker-python/tests/test_local_job_remediation.py
```

Expected: changed-line coverage at least 95%.

- [ ] **Step 3: Run scoped performance report**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python - <<'PY'
from pathlib import Path
from scripts import pre_commit_gate

root = Path.cwd()
changed = pre_commit_gate.staged_changed_files(root, base_ref="origin/main")
outcome = pre_commit_gate.run_performance_report(root, changed, base_ref="origin/main")
print(f"PERF_STATUS={outcome.status}")
print(f"PERF_REPORT_DIR={outcome.report_dir}")
raise SystemExit(0 if outcome.status == "ok" else 1)
PY
```

Expected: `Status ok`, zero direct/gated regressions.

- [ ] **Step 4: Run pre-commit gate**

```bash
.githooks/pre-commit
```

Expected: full local gate passes or a documented non-code N/A where a gate is not measurable.

- [ ] **Step 5: Commit and open PR**

Commit one focused change and open a PR closing #1763. The PR body must preserve the template headings `## Plan or Spec`, `## Commands Run`, `## Coverage and Metrics`, and `## Known Gaps`.

- [ ] **Step 6: Monitor PR to terminal outcome**

Wait for review, mergeability, CI, and performance report. Fix in-scope failures or regressions, push updates, rerun relevant local verification, and squash merge only when the PR is current with `origin/main`, CI is green, review threads are resolved, and the performance report has no direct/gated regressions.
