# Eval Schema and Hints Reproducibility

## Issue

Refs #639.

## Goal

Make `melix eval run` and `melix eval compare` accept reproducibility inputs that are stable enough for later run reports:

- `--schema <path>` loads a JSON schema file and feeds the existing structured result validation path.
- `--hints <path>` loads task guidance from `.json`, `.md`, or `.txt` and appends it to live evaluation prompts.
- Evaluation run metadata records schema and hints path, SHA-256, size, and format without persisting full hints text.
- JSON schema validation covers nested objects, arrays, nullable fields, and invalid output.
- Benchmark/evaluation comparison reports warn when baseline and candidate runs use different schema or hints hashes.

## Design

Use the current `EvaluationProfile.output_schema_json` path for schema content instead of adding a new protocol surface. The CLI reads `--schema`, validates that it is JSON, canonicalizes it with sorted keys, and passes it as `output_schema_json`. `--schema` and `--output-schema-json` are mutually exclusive so the receipt metadata is unambiguous.

Use evaluation request parameters for reproducibility metadata:

- `schema_path`
- `hints_path`

The Python worker resolves those paths, computes `schema_sha256`, `schema_size_bytes`, `hints_sha256`, `hints_size_bytes`, and `hints_format`, and keeps those in the persisted evaluation job parameters. The worker passes hints text only in memory to prompt construction.

Benchmark/evaluation report generation compares the persisted schema and hints hashes from evaluation jobs and compare jobs. Hash mismatches make the report status `warning`, set comparison validity to `partial`, and render a reproducibility warning in Markdown output.

## Probes and Metrics

Reuse existing per-sample probes:

- `eval.<suite>.sample_render_ms_mean`
- `eval.<suite>.validation_ms_mean`
- `eval.<suite>.scoring_ms_mean`
- `eval.<suite>.raw_response_chars_mean`
- `eval.<suite>.extracted_result_chars_mean`

Add run-level metadata fields that make later report comparison deterministic:

- `schema_sha256`
- `schema_size_bytes`
- `hints_sha256`
- `hints_size_bytes`
- `hints_format`
- `hints_prompt_chars`

Add report-level comparison warnings:

- `evaluation_schema_sha256_mismatch`
- `evaluation_hints_sha256_mismatch`

Success criteria: schema/hints metadata is stable across reruns with unchanged files, validation failures remain machine-readable, and hints do not leak full text into persisted job parameters.

## Implementation Steps

1. Add CLI parsing and command-codec support for `--schema` and `--hints` on `eval run` and `eval compare`.
2. Add worker metadata resolution for schema/hints paths and in-memory hints prompt injection.
3. Expand JSON schema validation for nested objects, arrays, nullable fields, and additional property checks.
4. Add report mismatch detection for schema/hints hashes.
5. Add Swift parser/runner coverage and Python evaluation/report coverage.
6. Run focused tests, changed-line coverage, diff checks, and PR evidence validation before publishing.

## Verification Plan

- `swift test --filter MelixCLIParserTests --filter MelixCLIRunnerTests/eval`
- `swift test --enable-code-coverage --filter MelixCLIParserTests --filter MelixCLIRunnerTests/eval`
- `uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py`
- changed-line coverage for touched Swift and Python files
- `git diff --check`
