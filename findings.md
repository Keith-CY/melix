# Findings

- Baseline audit showed `M6.1-M6.6`, `M6.10`, and `M6.11` largely implemented on `main`.
- The main missing closure points are:
  - `M6.7` requires benchmark evidence beyond unit tests.
  - `M6.8` requires benchmark or runbook evidence for sparse-prefill.
  - `M6.9` plan says "same model family" but current lock scope is mostly `source_model` or `artifact_path`.
- Quantization benchmark and release-gate scripts already exist and pass when run with explicit `PYTHONPATH`.
- Swift-targeted verification is presently unreliable because local cached build artifacts were produced by Swift `6.2.3` and the current compiler is `6.3`.
- `scripts/phase2_metrics_report.py` already contained active-KV decode evidence, but it did not emit sparse-prefill rows or sparse-prefill counters.
- Upload conflict locking did not previously block on linked quantized artifacts because upload scope was derived from `artifact_path`, not from quantization manifest identity.
- A fresh runtime boot with `MELIX_RUNTIME_DIR=.runtime/m6-phase2 ... bash scripts/dev_up.sh --prefer-built` produces executable live metrics without SwiftPM rebuild drift.

## Code Review Findings: M7.3-M7.5 Plan

Target file:
- `docs/superpowers/plans/2026-03-31-m7-3-m7-5-benchmark-eval-foundation.md`

Findings to address:

1. `[P1] Compare selected samples instead of checking only expected`
   - The planned evaluation runner uses `correct = sum(1 for sample in selected if sample["expected"])`, which treats any non-empty `expected` field as a correct answer.
   - This would report `1.0` accuracy for normal datasets even when the deterministic evaluator predicts the wrong answer.
   - Update the plan so accuracy is computed from predicted-vs-expected comparison, not expected-field presence.

2. `[P1] Return evaluationResults from handleRunEvaluation`
   - The planned Swift handler only populates `evaluationJob`, but the accompanying test in the same plan expects `response.ops.evaluationResults.count == 1`.
   - As written, the implementation steps and the verification steps do not agree.
   - Update the plan so the reply wiring includes `evaluationResults` and the PASS condition is internally consistent.

3. `[P2] Create jobs_root before writing evaluation artifacts`
   - The planned `EvaluationStore.persist_result()` writes files directly into `jobs_root` without creating the directory first.
   - A first run against a fresh path such as `tmp_path / "evaluation"` would fail with `FileNotFoundError`.
   - Add `jobs_root.mkdir(parents=True, exist_ok=True)` before writing artifacts.

4. `[P2] Measure coverage for the benchmark persistence files too`
   - Task 2 says the plan adds `benchmark_store.py` and modifies `maintenance_core.py`, but the touched-scope coverage command only checks evaluation-related Python files.
   - That means the plan could claim `>=95%` touched-scope coverage while leaving the benchmark persistence changes unmeasured.
   - Update the coverage step to include the benchmark persistence scope as well.

Suggested prompt for the original agent:
- `Read /Users/ChenYu/Documents/Github/melix/findings.md and update /Users/ChenYu/Documents/Github/melix/docs/superpowers/plans/2026-03-31-m7-3-m7-5-benchmark-eval-foundation.md to address the Code Review Findings: M7.3-M7.5 Plan section. Re-check that the implementation steps and Expected PASS/FAIL outcomes are self-consistent after the update.`
