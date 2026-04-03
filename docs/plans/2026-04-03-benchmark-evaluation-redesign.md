# 2026-04-03 Benchmark And Evaluation Redesign

## Summary

Melix now has productized LoRA and benchmark operator workflows, including direct Hugging Face benchmark imports and VLM compatibility for `unsloth/gemma-4-E4B-it-MLX-8bit`. The next transaction splits the current overloaded benchmark surface into two explicit product lines:

- `bench`: performance benchmarking
- `eval`: intelligence evaluation

The redesign keeps shared model loading, run persistence, and export infrastructure, but it stops mixing latency and scoring semantics inside one operator surface.

## Goals

- expose `melix eval ...` as a first-class CLI product alongside `melix bench ...`
- preserve `melix bench ...` for performance-only measurement and expand its input surface for context and batching probes
- add typed evaluation job, result, and sample export structures so accuracy-style runs can persist sample-level evidence
- make Window UI reflect the split between performance and intelligence workflows rather than overloading the benchmark cards
- keep control-plane truth in Swift and execution truth in Python

## Scope

- protocol and shared type updates for evaluation job and sample export
- CLI parser and runner support for `eval run`, `eval list`, and sample-aware export commands
- control-plane request and reply wiring for evaluation job history and export
- Python worker persistence for evaluation jobs, results, and sample-level records
- Window UI follow-up for evaluation runs and sample inspection

## Non-Goals

- vision-language intelligence suites in the first evaluation redesign slice
- merging benchmark and evaluation into one combined command
- agentic or tool-use evaluation suites in the first slice

## Product Contracts

### Performance Benchmarking

`bench` remains responsible for serving and runtime performance only.

Required inputs:

- benchmark target: `--model-id` or `--repo-id`
- suite selection
- context-length sweep inputs
- batch-size sweep inputs
- max-output token budget

Required outputs:

- summary performance metrics
- per-context measurements
- per-batch measurements
- persisted runs
- CSV export

### Intelligence Evaluation

`eval` becomes the public entry point for correctness and reasoning quality.

Required inputs:

- evaluation target: `--model-id` or `--repo-id`
- suite selection
- sample size
- batch factor
- seed
- few-shot count

Required outputs:

- summary suite scores
- persisted evaluation jobs and results
- sample-level exports as CSV and JSONL

## Initial Suite Set

The first evaluation slice targets text-only suites:

- `mmlu`
- `arc_challenge`
- `hellaswag`
- `winogrande`
- `truthfulqa_mc`
- `gsm8k`
- `humaneval`
- `mbpp`

## Execution Slices

1. Plan and status reset for the new benchmark/evaluation transaction.
2. Protocol updates for evaluation exports and CLI-facing request shapes.
3. `melix eval` CLI parser and runner implementation.
4. Control-plane evaluation export and history plumbing.
5. Python worker evaluation persistence and sample export.
6. Window UI evaluation workspace.
7. Verification, coverage, metrics, and commit closure.

## Verification

Each executable slice must satisfy:

- targeted tests for the touched scope
- changed-line coverage `>=95%` for the touched executable scope
- `progress.md` metrics and verification updates

Final transaction verification:

- `make proto`
- `make py-test`
- `make swift-test`
- `make integration-test`
