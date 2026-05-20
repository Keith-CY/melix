# Agentic Benchmark Fixture Suite Plan

## Goal

Add repository-owned fixture-backed agentic benchmark suites for image,
search, and visit tool-use paths.

## Scope

- Covers issue #709 under the OpenSearch-VL agentic benchmark metrics
  direction.
- Adds small default `text-generation` benchmark suite catalog entries that
  materialize from checked-in fixture packages instead of Hugging Face.
- Reuses the existing benchmark row contract: each fixture row supplies a
  prompt, `tool_calls`, and `tool_fixture_context`.
- Keeps request-level persistence for every tool turn and final-answer phase
  out of scope; that is the next milestone unit.

## Architecture

The benchmark suite catalog already turns text-generation rows into
`BenchmarkCase` values that preserve `tool_calls` and `tool_fixture_context`.
This slice makes that row shape runnable without network access by adding
Melix fixture packages under `services/mlx-worker-python/fixtures/benchmark/`
and a local fixture source path on `BenchmarkSuiteDefinition`.

The default catalog adds three suite ids for `text-generation`:

- `agentic_image`: image-inspection fixture using `image_crop` and
  `image_search`
- `agentic_search`: retrieval fixture using `text_search`
- `agentic_visit`: browser fixture using `visit`

Fixture materialization writes the same `manifest.json` and `rows.jsonl`
package shape as remote datasets, but reports `source_kind:
melix_benchmark_fixture` and `dataset_uri:
melix-fixture://benchmark/<fixture-package-id>`. The materialized manifest
also records `fixture_package_id` so exports and debugging can identify the
checked-in source package.

## Performance Probes And Metrics

- Measurement points:
  - dataset materialization cache hit/miss on the benchmark fixture package
  - request prompt rendering from fixture rows
  - agentic tool runtime metrics emitted later from the preserved tool calls:
    `agentic_tool.call_count`, `agentic_tool.latency_ms`,
    `agentic_tool.observation_emitted_bytes`, timeout count, and failed count
- Success metrics:
  - resolving the three default agentic suites performs no Hugging Face fetch
  - materialized package metadata identifies the fixture source
  - generated cases preserve tool calls and deterministic fixture context
  - existing Hugging Face-backed suites remain unchanged

## Implementation Plan

1. Update `docs/benchmark-evaluation-contract.md` with the local benchmark
   fixture source contract and the three suite ids.
2. Add failing tests in
   `services/mlx-worker-python/tests/test_benchmark_suites.py` for default
   catalog discovery, local materialization metadata, no remote fetch, and
   case preservation.
3. Add fixture package directories under
   `services/mlx-worker-python/fixtures/benchmark/`.
4. Extend `BenchmarkSuiteDefinition` and the materializer to support local
   fixture packages while keeping existing Hugging Face behavior unchanged.
5. Bundle the small benchmark fixtures in the macOS app repo subset so packaged
   workers can resolve the default agentic suites.
6. Run focused benchmark suite and packaging tests, changed-scope coverage, and `git diff
   --check`.

## Verification

- `git diff --check`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_suites.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_macos_app_bundle.py::test_write_unsigned_macos_app_bundle_writes_self_contained_layout`
- Changed-scope coverage for
  `services/mlx-worker-python/worker/productization/benchmark_suites.py` and
  `services/mlx-worker-python/worker/productization/macos_app_bundle.py`

## Known Gaps

- This slice does not persist request-level rows for every tool turn and
  final-answer phase. That remains the second unit under issue #708.
- The fixture suites are deterministic and local-only; network-backed search
  and visit providers remain outside the local benchmark contract.
