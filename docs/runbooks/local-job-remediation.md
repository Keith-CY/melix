# Local Job Remediation

This runbook defines the shared Melix contract for diagnosing local job failures
from bounded log excerpts, selecting safe remediation policies, and recording
operator-visible receipts. It applies to local model downloads, runtime launches,
training jobs, evaluation jobs, and future desktop projections that need to
explain a failure before retrying it.

The contract is intentionally side-effect-free. The classifier and policy layer
do not install dependencies, mutate host settings, or start replacement
processes. They return a diagnosis, a suggested remediation, and a bounded retry
decision that an owning job runner may choose to execute.

## Receipt Schema

Receipts use:

```text
melix.local_job_remediation_receipt.v1
```

Required fields:

| Field | Meaning |
|---|---|
| `schema_version` | Stable receipt schema identifier. |
| `command` | Original command vector with token-like values redacted. |
| `redacted_log_excerpt` | Tail-bounded log excerpt after secret redaction. |
| `diagnosis` | Typed failure diagnosis object. |
| `remediation` | Suggested remediation and operation type. |
| `decision` | Retry policy result for this attempt. |
| `outcome` | Caller-supplied result such as `planned`, `explained`, or `blocked`. |

`diagnosis` includes:

| Field | Meaning |
|---|---|
| `code` | Stable diagnosis code. |
| `summary` | Operator-facing failure summary. |
| `matched_pattern` | Lowercase pattern that triggered the classification. |

`remediation` includes:

| Field | Meaning |
|---|---|
| `operation_type` | One of the operation types below. |
| `summary` | Short operator-facing remediation summary. |
| `action` | Concrete action or policy change. |
| `retryable` | Whether automatic retry is eligible when policy allows it. |
| `changed_flags` | Suggested flag changes for retryable remediations. |

`decision` includes:

| Field | Meaning |
|---|---|
| `mode` | `auto`, `manual`, `dry_run`, or `disabled`. |
| `will_retry` | Whether the caller may perform an automatic retry now. |
| `reason` | Stable reason for the decision. |
| `attempt_index` | Zero-based attempt index that produced the failure. |
| `max_retries` | Retry budget from the active policy. |
| `dry_run` | Whether explain-only mode was requested. |
| `auto_remediation_enabled` | Whether automatic remediation was enabled. |

## Diagnosis Codes

| Code | Typical log evidence | Remediation operation |
|---|---|---|
| `memory_oom` | KV-cache pressure, CUDA/Metal out-of-memory, allocation failure | `retry_with_changed_flag` |
| `port_conflict` | Address already in use, `EADDRINUSE`, bind failure | `retry_with_changed_flag` |
| `missing_dependency` | `ModuleNotFoundError`, `No module named`, command not found | `dependency_install` |
| `gated_model_access` | Gated repository, 401/403, missing Hugging Face authentication | `manual_action` |
| `invalid_accelerator_selection` | Invalid device ordinal, unavailable GPU index, invalid accelerator override | `settings_change` |
| `unclassified` | No known pattern matched the bounded excerpt | `manual_action` |

## Operation Types

| Operation type | Automatic retry eligible | Meaning |
|---|---:|---|
| `retry_with_changed_flag` | Yes | The caller may retry with an explicit changed flag when budget remains. |
| `dependency_install` | No | The operator must install or restore dependencies before retrying. |
| `settings_change` | No | The operator must change runtime or accelerator settings before retrying. |
| `manual_action` | No | The operator must inspect or perform an external action before retrying. |

## Retry Policy

`LocalJobRemediationPolicy` controls decisions:

- `max_retries`: non-negative retry budget. Automatic retry is allowed only when
  `attempt_index < max_retries`.
- `dry_run`: when true, the receipt explains the remediation but always returns
  `will_retry=false` and `reason=dry_run_explain_only`.
- `auto_remediation_enabled`: when false, the receipt returns
  `will_retry=false` and `reason=auto_remediation_disabled`.
- `excerpt_bytes`: maximum UTF-8 bytes retained from the end of the log text.
  The default is 16 KiB.

Automatic retry is never allowed for non-retryable operation types, even when
retry budget remains.

## Redaction

Receipts must not expose operator secrets. The current redaction layer removes:

- `HF_TOKEN=...`
- `HUGGINGFACE_HUB_TOKEN=...`
- `MELIX_HF_TOKEN=...`
- `MELIX_HUGGINGFACE_TOKEN=...`
- command values after `--hf-token`, `--huggingface-token`, or `--token`
- inline token-like strings beginning with `hf_`

Log excerpts are tail-bounded before serialization so diagnostic receipts stay
bounded even when the original job log is large.

## Verification

Run focused tests after changing this contract:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_local_job_remediation.py
```

Run changed-scope coverage before commit:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run --data-file=.runtime/coverage/local_job_remediation.coverage -m pytest -q services/mlx-worker-python/tests/test_local_job_remediation.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json --data-file=.runtime/coverage/local_job_remediation.coverage -o .runtime/coverage/local_job_remediation.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python scripts/python_changed_line_coverage.py --diff-from origin/main --coverage-json .runtime/coverage/local_job_remediation.json services/mlx-worker-python/worker/model_ops/local_job_remediation.py services/mlx-worker-python/tests/test_local_job_remediation.py
```

Run the PR-scoped performance report and require `Status ok` with zero
direct/gated regressions:

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
