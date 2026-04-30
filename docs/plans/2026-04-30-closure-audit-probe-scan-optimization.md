# Closure Audit Probe Scan Optimization Plan

## Goal

Reduce redundant file reads in `services/mlx-worker-python/worker/productization/closure_audit.py`
when probe-source discovery already has enough evidence for every required metric probe.

## Scope

- Touch `services/mlx-worker-python/worker/productization/closure_audit.py`
- Touch `services/mlx-worker-python/tests/test_closure_audit.py`
- No Swift or macOS-only changes

## Linux-Only Constraint

This change must stay fully verifiable on Linux with focused Python tests, coverage,
and a synthetic performance probe.

## Proposed Change

Short-circuit `_collect_probe_sources(...)` once every required probe has reached its
maximum retained source count. Preserve the existing output schema and deterministic
source ordering for the files that are still read.

## Performance Probe

Create a synthetic repo tree where the first few scanned files already mention every
required probe name three times, followed by many large irrelevant files.

Measure:
- elapsed wall time for the old scan strategy versus the optimized scan strategy
- number of file reads performed by each strategy

Success criteria:
- identical collected probe-source payloads for the same early-match files
- materially fewer file reads after saturation
- measurable wall-time improvement on the synthetic probe

## Verification Commands

```text
PYTHONPATH=/tmp/melix-cron-python-opt-20260430-105157:/tmp/melix-cron-python-opt-20260430-105157/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_closure_audit.py
PYTHONPATH=/tmp/melix-cron-python-opt-20260430-105157:/tmp/melix-cron-python-opt-20260430-105157/services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_closure_audit.py
coverage report -m services/mlx-worker-python/worker/productization/closure_audit.py services/mlx-worker-python/tests/test_closure_audit.py
python3 /tmp/closure_audit_probe_scan_probe.py
git diff --check
```
