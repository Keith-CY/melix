# Issue 2608: LoRA Held-Out Evaluation

## Issue

GitHub issue: https://github.com/Keith-CY/melix/issues/2608

## End-State Architecture

LoRA training should support a first-class held-out test split that is excluded
from train and validation rows by construction. When requested, the training
pipeline writes `test.jsonl` into the normalized dataset snapshot, trains only
on `train.jsonl`, keeps validation on `valid.jsonl`, then evaluates the trained
adapter on `test.jsonl` after adapter audit. The resulting loss and perplexity
become durable receipt, adapter manifest, provenance, and experiment-store
fields.

## This Slice

1. Add deterministic `test_ratio` handling to the normalized dataset snapshot.
   The split is digest-ranked, stable, and disjoint from train and validation.
2. Add a runner held-out evaluation interface.
   The deterministic runner returns fixture metrics for tests; the native MLX-LM
   runner uses `load_local_dataset(...).test` plus `mlx_lm.tuner.trainer.evaluate`
   against the trained adapter.
3. Add a held-out evaluation receipt.
   Runs without `test_ratio` write a skipped receipt with an explicit reason.
   Runs with a test split write completed metrics and paths.
4. Persist held-out fields in the adapter manifest, adapter provenance final
   metrics, and LoRA experiment run records.

## Metrics and Probes

- Changed scope is Python LoRA training and dataset paths.
- Focused coverage target:
  - `tests/test_training_dataset_builder.py`
  - `tests/test_lora_training_receipts.py`
  - `tests/test_lora_model_ops_unit.py`
  - `tests/test_lora_experiment_store.py`
  - `tests/test_lora_adapter_provenance.py`
- Performance probe expected from scoped pre-commit:
  - `lora-experiment-run-dir-name-scan` or other Python LoRA/data probes selected
    by `scripts/pr_scoped_performance.py`.
- Success metrics:
  - Held-out rows are absent from both train and validation JSONL.
  - Completed held-out receipt records finite loss/perplexity and sample count.
  - No-test runs record a skipped receipt reason.
  - Experiment store exposes held-out metrics for run comparison.

## Verification Plan

1. Add failing tests for deterministic three-way split and stale `test.jsonl`
   cleanup.
2. Add failing pipeline tests for completed and skipped held-out receipts.
3. Add failing provenance/store tests for persisted held-out metrics.
4. Implement the smallest production changes needed to pass those tests.
5. Run focused pytest with coverage for changed Python scope.
6. Before commit, rely on the repository pre-commit hook for the full local gate:
   `make swift-test`, `make py-test`, `make integration-test`, and scoped
   performance report.
