# Issue 1472 Apple Silicon Speculative Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repository-owned speculative VLM smoke probe that reports throughput, TTFT, acceptance rate, fallback stability, repeated-media correctness, and gated speed-target status for Issue #1472.

**Architecture:** Keep the smoke probe as an explicit script under `scripts/` so it can run in PR-scoped performance and as an operator-facing artifact command. The CI path uses deterministic synthetic VLM samples and the existing baseline-vs-accelerated evidence writer; live Apple Silicon execution can later populate the same fields without changing the PR gate contract.

**Tech Stack:** Python 3.12, `uv`, `pytest`, Melix worker `MaintenanceCore` benchmark evidence helpers, PR-scoped performance registry JSON.

---

### Task 1: Add the Smoke Probe Script Contract

**Files:**
- Create: `scripts/vlm_speculative_smoke_probe.py`
- Modify: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

- [x] **Step 1: Write the failing test**

Add `test_vlm_speculative_smoke_probe_script_emits_metrics` near the existing VLM probe tests:

```python
def test_vlm_speculative_smoke_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["vlm_speculative_smoke_probe.py"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(REPO_ROOT / "scripts/vlm_speculative_smoke_probe.py"), run_name="__main__")

    assert exc_info.value.code == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["sample_count"] == 5.0
    assert metrics["smoke_pass_count"] == 5.0
    assert metrics["speed_target_met_count"] == 5.0
    assert metrics["fallback_stability_count"] == 5.0
    assert metrics["repeated_media_correctness_count"] == 5.0
    assert metrics["comparison_artifact_present_count"] == 5.0
    assert metrics["baseline_ttft_ms"] == 20.0
    assert metrics["accelerated_ttft_ms"] == 12.0
    assert metrics["accelerated_decode_tokens_per_second"] == 166.7
    assert metrics["acceptance_rate"] == 0.75
    assert metrics["fallback_count"] == 0.0
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
UV_PYTHON=3.12 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vlm_speculative_smoke_probe_script_emits_metrics
```

Expected: FAIL because `scripts/vlm_speculative_smoke_probe.py` does not exist.

- [x] **Step 3: Implement the script**

Create `scripts/vlm_speculative_smoke_probe.py` with deterministic baseline and accelerated `BenchSample` rows. The script must:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.engine.maintenance_core import BenchSample, MaintenanceCore  # noqa: E402
```

Use `MaintenanceCore._write_vlm_speculative_comparison_artifact` to prove artifact generation and emit numeric metrics for sample count, smoke pass count, speed-target count, fallback stability, repeated-media correctness, TTFT, throughput, acceptance rate, fallback count, payload bytes, and artifact write elapsed time.

- [x] **Step 4: Run the test to verify it passes**

Run the same pytest command. Expected: PASS.

### Task 2: Register the PR-Scoped Probe

**Files:**
- Modify: `infra/perf/pr_scoped_probes.json`
- Modify: `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

- [x] **Step 1: Write registry selection and command tests**

Add tests:

```python
def test_scope_report_selects_vlm_speculative_smoke_probe() -> None:
    scope = build_scope_report(
        registry_path=REGISTRY_PATH,
        changed_files=[
            "scripts/vlm_speculative_smoke_probe.py",
            "services/mlx-worker-python/worker/engine/maintenance_core.py",
        ],
    )

    assert "vlm-speculative-smoke-probe" in {
        probe["id"] for probe in scope["selected_probes"]
    }


def test_vlm_speculative_smoke_probe_command_has_base_fallback() -> None:
    probe = next(
        probe
        for probe in load_probe_registry(REGISTRY_PATH)
        if probe.probe_id == "vlm-speculative-smoke-probe"
    )

    assert "if [ -f scripts/vlm_speculative_smoke_probe.py ]" in probe.probe_command
    assert "smoke_pass_count" in probe.probe_command
    assert "speed_target_met_count" in probe.probe_command
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
UV_PYTHON=3.12 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_vlm_speculative_smoke_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vlm_speculative_smoke_probe_command_has_base_fallback
```

Expected: FAIL because the registry entry is missing.

- [x] **Step 3: Add the registry entry**

Add `vlm-speculative-smoke-probe` next to the existing VLM comparison probe. Watch `scripts/vlm_speculative_smoke_probe.py`, `scripts/vlm_batch1_comparison_probe.py`, `services/mlx-worker-python/worker/engine/maintenance_core.py`, `services/mlx-worker-python/tests/test_maintenance_service.py`, `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`, and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`. Gate metrics should include:

```json
[
  {"key": "artifact_elapsed_ms_mean", "unit": "ms", "direction": "informational"},
  {"key": "smoke_pass_count", "unit": "count", "direction": "higher_is_better", "warn_pct": 0.0},
  {"key": "speed_target_met_count", "unit": "count", "direction": "higher_is_better", "warn_pct": 0.0},
  {"key": "fallback_stability_count", "unit": "count", "direction": "higher_is_better", "warn_pct": 0.0},
  {"key": "repeated_media_correctness_count", "unit": "count", "direction": "higher_is_better", "warn_pct": 0.0}
]
```

- [x] **Step 4: Run the tests to verify they pass**

Run the same pytest command. Expected: PASS.

### Task 3: Document the Unit 4.3.2 Contract

**Files:**
- Modify: `docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md`

- [x] **Step 1: Update implementation notes**

Add a Unit 4.3.2 paragraph after the Unit 4.3.1 note. State that the smoke probe requires baseline and accelerated TTFT/throughput, native acceleration acceptance/rollback fields, fallback stability, repeated-media correctness, and a speed-target pass flag before promotion.

- [x] **Step 2: Verify docs mention the issue**

Run:

```bash
rg -n "Unit 4.3.2|vlm_speculative_smoke_probe|speed target|fallback stability" docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md
```

Expected: The Unit 4.3.2 note and existing issue map are present.

### Task 4: Final Verification and Commit

**Files:**
- All files changed above.

- [x] **Step 1: Run focused tests**

Run:

```bash
UV_PYTHON=3.12 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vlm_speculative_smoke_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_vlm_speculative_smoke_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_vlm_speculative_smoke_probe_command_has_base_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
```

- [x] **Step 2: Run the smoke script**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/vlm_speculative_smoke_probe.py
```

Expected: JSON metrics with `smoke_pass_count`, `speed_target_met_count`, `fallback_stability_count`, and `repeated_media_correctness_count` all equal to `5.0`.

- [x] **Step 3: Run diff and scoped performance**

Run:

```bash
git diff --check origin/main...HEAD
UV_PYTHON=3.12 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx python - <<'PY'
from pathlib import Path
import subprocess
from scripts.pre_commit_gate import run_performance_report
root = Path.cwd()
changed = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", "origin/main...HEAD", "--"], cwd=root, text=True).splitlines()
changed = [line.strip() for line in changed if line.strip()]
outcome = run_performance_report(root, changed, base_ref="origin/main")
print("outcome_status:", outcome.status)
print("selected_probe_count:", outcome.selected_probe_count)
print("report_dir:", outcome.report_dir)
raise SystemExit(0 if outcome.status == "ok" else 1)
PY
```

- [x] **Step 4: Commit**

```bash
git add docs/plans/2026-04-26-issue-42-multimodal-fast-paths.md docs/plans/2026-07-04-issue-1472-apple-silicon-speculative-smoke.md infra/perf/pr_scoped_probes.json scripts/vlm_speculative_smoke_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
git commit -m "Add VLM speculative smoke probe"
```

## Self-Review

- Spec coverage: The probe reports throughput, TTFT, acceptance rate, fallback stability, repeated-media correctness, and speed-target status. The plan updates the governing Plan 4.3 doc.
- Placeholder scan: No TBD/TODO/fill-in placeholders remain.
- Type consistency: Test names, script name, registry id, and metric keys are consistent across tasks.
