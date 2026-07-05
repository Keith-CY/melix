# Issue 2188 Workspace Privacy Detector Environment Override

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit workspace-ingest operator environment override for privacy detector mode while preserving the existing default-off behavior and CLI flag precedence.

**Architecture:** `scripts/dataset_preparation_ingest.py` remains the CLI boundary for dataset ingest. It resolves the effective privacy detector mode from `--privacy-detector-mode` when supplied, otherwise from `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE`, otherwise `off`, and passes only the normalized mode into `DatasetIngestRequest`. The existing Python ingest receipt pipeline remains the source of detector receipts and sanitized audit counters.

**Tech Stack:** Python 3.12 CLI script, dataset ingest productization code, pytest, existing dataset ingest receipt JSON contracts, Melix pre-commit and PR-scoped dataset probes.

---

Follow-up: `2026-07-05-issue-2188-workspace-detect-mode.md` extends the
environment and CLI controls with explicit audit-only `detect` mode. Unsupported
environment-value examples should use a value such as `audit-only`; `detect` is
now a supported mode.

## Scope

- Add `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE` as an explicit workspace-ingest operator override.
- Keep workspace ingest default behavior unchanged when the environment variable and CLI flag are absent.
- Treat unsupported or empty environment values as `off`, matching the local proxy's safe unsupported-value behavior.
- Keep `--privacy-detector-mode off|detect|redact|block` as the highest-precedence explicit CLI override.
- Preserve the existing receipt shape: `privacy_detector_receipts`, `privacy_audit_counters`, and privacy detector metrics still come from `prepare_dataset_ingest(...)`.
- Keep raw secret values, raw source text, and raw matched spans out of CLI JSON and receipt metadata.

## Non-Goals

- No default-on privacy policy change.
- No local proxy or Swift route behavior change.
- No detector regex, receipt schema, or protobuf schema change.
- No diagnostics bundle content scanning.
- No model-backed or NER detector.

## Files

- Modify `scripts/dataset_preparation_ingest.py`
  - Add a named environment variable constant.
  - Add a small mode normalizer for environment values.
  - Make the CLI flag default to `None`, then resolve the effective mode after parsing.
- Modify `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
  - Add RED/GREEN CLI tests proving environment opt-in redacts sensitive source text.
  - Add CLI precedence coverage proving an explicit flag overrides the environment.
  - Add unsupported environment value coverage proving safe fallback to `off`.
- Modify `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md`
  - Document the workspace-ingest environment override and CLI precedence.
- Modify `infra/perf/pr_scoped_probes.json`
  - Add the new workspace privacy detector CLI tests to the relevant dataset
    preparation probe test and coverage commands.
- Modify `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
  - Assert the dataset preparation probes continue to replay every privacy
    detector ingest CLI test needed for changed-line coverage.
- Update this plan with verification evidence before PR handoff.

## Task 1: Add Failing CLI Environment Tests

**Files:**
- Test: `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`

- [x] **Step 1: Add environment opt-in RED test**

Add `test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment`.
The test should set `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE=redact`, omit
`--privacy-detector-mode`, write source text containing a secret assignment, run
`dataset_preparation_ingest.main(...)`, and assert:

- exit code is `0`;
- `privacy_detector_receipts[0].policy_mode` is `redact`;
- `privacy_detector_receipts[0].action` is `redacted`;
- the serialized receipt omits the raw secret fragments.

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment
```

Expected before implementation: fail because the CLI still defaults the mode to
`off`.

- [x] **Step 2: Add CLI precedence RED test**

Add `test_dataset_ingest_cli_privacy_detector_flag_overrides_environment`.
Set `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE=block`, pass
`--privacy-detector-mode off`, and assert:

- exit code is `0`;
- the receipt mode is `off`;
- no detector scan ran (`privacy_detector_latency_ms == 0.0`);
- the source segment still contains the raw secret text because detector mode is
  explicitly off and `pii_mask` is disabled.

Run the new nodeid and expect it to fail before implementation if the
environment is not read or if precedence is wrong.

- [x] **Step 3: Add unsupported environment RED test**

Add `test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment`.
Set `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE=audit-only`, omit the CLI flag, and
assert the effective receipt mode is `off`. This prevents a malformed operator
environment from blocking ingestion unexpectedly.

Run the nodeid before implementation and expect it to pass today only if the
environment is ignored; after implementation it must still pass for the stronger
reason that unsupported values normalize to `off`.

## Task 2: Resolve The Effective CLI Mode

**Files:**
- Modify: `scripts/dataset_preparation_ingest.py`

- [x] **Step 1: Add the environment constant and normalizer**

Add near the imports:

```python
WORKSPACE_PRIVACY_DETECTOR_MODE_ENV = "MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE"
```

Add helper:

```python
def _privacy_detector_mode_from_env() -> str:
    raw_value = os.environ.get(WORKSPACE_PRIVACY_DETECTOR_MODE_ENV, "")
    normalized = raw_value.strip().lower()
    return normalized if normalized in {"detect", "redact", "block"} else "off"
```

- [x] **Step 2: Resolve CLI flag precedence**

Change the parser argument default from `"off"` to `None`:

```python
parser.add_argument(
    "--privacy-detector-mode",
    choices=("off", "detect", "redact", "block"),
    default=None,
)
```

After parsing, set:

```python
privacy_detector_mode = args.privacy_detector_mode or _privacy_detector_mode_from_env()
```

Pass `privacy_detector_mode` into `build_receipt(...)`.

- [x] **Step 3: Keep explicit programmatic calls unchanged**

Do not change `build_receipt(...)` default. Direct callers that do not use the
CLI remain default-off unless they pass `privacy_detector_mode`.

## Task 3: Document The Operator Control

**Files:**
- Modify: `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md`
- Modify: this plan

- [x] **Step 1: Update the canonical dataset preparation plan**

Document that the dataset ingest CLI resolves privacy detector mode from:

1. `--privacy-detector-mode`;
2. `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE`;
3. `off`.

Document that unsupported environment values normalize to `off`.

- [x] **Step 2: Record verification evidence**

Append focused test results, coverage/probe metrics, and pre-commit report paths
to this plan before opening the pull request.

## Task 4: Verify And Ship

**Files:**
- All changed files.

- [x] **Step 1: Run focused tests**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_privacy_detector_flag_overrides_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment
```

- [x] **Step 2: Run adjacent ingest tests**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
```

- [x] **Step 3: Run syntax and diff checks**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python -m py_compile scripts/dataset_preparation_ingest.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
git diff --check
git diff --cached --check
```

- [x] **Step 4: Verify PR-scoped performance coverage mapping**

```bash
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_preparation_probes_cover_privacy_detector_ingest_tests services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_privacy_detector_flag_overrides_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment
```

Run the coverage commands for:

- `dataset-version-listing-scandir`;
- `dataset-quality-lengths-chain`;
- `dataset-source-records-scandir`.

- [x] **Step 5: Run the required pre-commit gate**

```bash
.githooks/pre-commit
```

Expected: `make swift-test`, `make py-test`, `make integration-test`, and
scoped performance all pass with no direct/gated regressions. Any context
regressions reported by registry-adjacent probes must be recorded separately.

## Verification Evidence

- RED:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_privacy_detector_flag_overrides_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment`
  failed before implementation as expected: environment opt-in receipt mode was
  still `off`; the other two tests passed under the old ignored-env behavior.
- GREEN focused:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_privacy_detector_flag_overrides_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment`
  passed: `3 passed in 0.04s`.
- Adjacent ingest tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
  passed: `26 passed in 0.14s`.
- Syntax:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python -m py_compile scripts/dataset_preparation_ingest.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
  passed.
- Diff hygiene:
  `git diff --check` passed.
- Initial pre-commit gate:
  `.githooks/pre-commit` passed `make swift-test` (`504.7s`),
  `make py-test` (`4681 passed, 14 skipped, 2 warnings in 173.77s`), and
  `make integration-test` (`123 passed, 1 skipped in 700.67s`), then failed
  scoped performance with `Status: verification_failed` because the three
  affected dataset probes did not yet replay the new CLI environment tests for
  changed-line coverage. Report:
  `.runtime/pre-commit-performance/20260705-082129-ffe5e1ff/report/report.md`.
- PR-scoped performance coverage mapping:
  `python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null` passed.
- PR-scoped coverage guard:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_preparation_probes_cover_privacy_detector_ingest_tests services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_privacy_detector_mode_from_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_privacy_detector_flag_overrides_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment`
  passed: `4 passed in 0.38s`.
- Dataset version listing coverage command:
  `dataset-version-listing-scandir` coverage command passed:
  `20 passed in 0.33s`; changed-line coverage `100.00%`.
- Dataset quality lengths coverage command:
  `dataset-quality-lengths-chain` coverage command passed:
  `21 passed in 0.32s`; changed-line coverage `100.00%`.
- Dataset source records coverage command:
  `dataset-source-records-scandir` coverage command passed:
  `35 passed in 0.37s`; changed-line coverage `100.00%`.
- Final pre-commit gate:
  `.githooks/pre-commit` passed. It completed `make swift-test` in `149.3s`,
  `make py-test` with `4681 passed, 14 skipped, 2 warnings in 159.13s`, and
  `make integration-test` with `123 passed, 1 skipped in 417.67s`.
- Final scoped performance:
  report `.runtime/pre-commit-performance/20260705-083904-ffe5e1ff/report/report.md`
  returned `Status: ok`, `Changed files: 6`, `Selected probes: 141`,
  `Direct/gated probes: 4`, `Regressions: 0`, `Context regressions: 7`, and
  `Verification failures: 0`.
- Direct dataset performance probes:
  `dataset-version-listing-scandir`, `dataset-quality-lengths-chain`, and
  `dataset-source-records-scandir` all returned `Status: ok`, targeted tests
  `pass`, coverage `pass (100.0%)`, and neutral or improvement metrics.
