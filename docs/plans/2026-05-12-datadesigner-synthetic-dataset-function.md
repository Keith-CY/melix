# DataDesigner Synthetic Dataset Function

## Goal

Implement the first Melix integration function for NVIDIA NeMo DataDesigner:

```python
generate_synthetic_dataset_package(request, *, jobs_root, output_dir, progress=None) -> SyntheticDatasetPackageResult
```

The function converts a Melix-owned synthetic dataset request into a DataDesigner
configuration, runs preview or create mode, exports the generated rows, and
normalizes them into Melix dataset packages that can be consumed by training and
evaluation workflows.

## Non-Goals

- Do not add a public CLI, protobuf RPC, or native UI surface in the first slice.
- Do not make DataDesigner a required worker dependency for the base worker.
- Do not bypass Melix dataset package contracts by executing training or
  evaluation directly against DataDesigner artifacts.
- Do not upload generated datasets to Hugging Face Hub in the first slice.
- Do not enable arbitrary user-provided Python callables in Melix requests.

## Context

Relevant specs:

- `AGENTS.md`
- `docs/benchmark-evaluation-contract.md`
- `docs/plans/2026-05-05-dataset-management-and-selection.md`
- `docs/plans/2026-03-30-m7-4-offline-dataset-packaging-and-runners.md`

Relevant code paths:

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`

DataDesigner facts checked from `NVIDIA-NeMo/DataDesigner` on May 12, 2026:

- The install package is `data-designer`, Python `>=3.10`, Apache-2.0.
- The public interface is `data_designer.interface.DataDesigner`.
- `DataDesigner.create(config_builder, *, num_records, dataset_name, resume)`
  writes local artifacts under the configured `artifact_path`.
- `DataDesigner.preview(config_builder, *, num_records)` stores preview results
  in memory.
- `DatasetCreationResults.export(path, format="jsonl")` streams generated
  Parquet batches to JSONL without loading the full dataset.
- `DataDesignerConfigBuilder` supports `add_model_config`, `add_column`,
  `with_seed_dataset`, `write_config`, and `build`.
- Model configuration supports OpenAI-compatible providers through
  `ModelProvider(name, endpoint, provider_type="openai", api_key=...)` and
  `ModelConfig(alias, model, provider, inference_parameters=...)`.
- Core column configs include sampler, LLM text, LLM structured, LLM judge,
  expression, validation, seed dataset, embedding, image, and custom columns.

Current Melix contracts:

- Training data packages use `manifest.json`, `samples.jsonl`, and optional
  `valid.jsonl`.
- Evaluation executes materialized packages and not raw external schemas.
- Local training conversion already supports `chat_messages`,
  `prompt_completion`, `text_completion`, `preference_pair`,
  `prompt_candidate`, `reward_scored`, and `calibration`.
- Final-result evaluation packages use `system`, `input`, and `target` rows
  with a profile declared in `manifest.json`.

## Implementation Status

This slice implements the worker/productization adapter and dependency contract:

- `services/mlx-worker-python/worker/productization/synthetic_dataset_generation.py`
- `services/mlx-worker-python/tests/test_synthetic_dataset_generation.py`
- optional worker extra `synthetic-data = ["data-designer>=0.5.9,<0.6"]`

Public CLI, protobuf RPC, registry browse UI, and native studio surfaces remain
separate follow-up slices because they touch operator-facing workflows beyond
the function boundary.

## Function Boundary

The Python worker/productization module exposes:

```python
@dataclass(frozen=True)
class SyntheticDatasetRequest:
    dataset_id: str
    dataset_name: str
    mode: Literal["preview", "create"]
    num_records: int
    output_kind: Literal["training", "evaluation_final_result", "raw_jsonl"]
    output_format: str
    model_provider: SyntheticModelProvider
    models: tuple[SyntheticModelConfig, ...]
    columns: tuple[SyntheticColumnSpec, ...]
    job_id: str = ""
    seed_source: SyntheticSeedSource | None = None
    validation_ratio: float = 0.0
    preview_count: int = 3
    random_seed: int | None = None
    data_designer_resume_mode: Literal["never", "if_possible", "always"] = "never"
    disable_data_designer_telemetry: bool = True


@dataclass(frozen=True)
class SyntheticDatasetPackageResult:
    package_path: Path
    manifest_path: Path
    output_path: Path
    generated_jsonl_path: Path
    data_designer_artifact_path: Path
    config_path: Path
    manifest_payload: dict[str, Any]
    row_count: int
    validation_row_count: int
    output_kind: str
    preview_only: bool
```

The implementation function:

```python
def generate_synthetic_dataset_package(
    request: SyntheticDatasetRequest,
    *,
    jobs_root: Path,
    output_dir: Path,
    progress: Callable[[str, float], None] | None = None,
) -> SyntheticDatasetPackageResult:
    ...
```

### Placement

The implementation is placed under:

```text
services/mlx-worker-python/worker/productization/synthetic_dataset_generation.py
```

Keep it separate from `training_dataset.py` and
`evaluation_final_result.py` so DataDesigner remains an optional generation
adapter rather than a dependency of existing package readers.

### Dependency Shape

The worker declares DataDesigner as an optional extra:

```toml
[project.optional-dependencies]
synthetic-data = [
  "data-designer>=0.5.9,<0.6",
]
```

The function must lazy-import `data_designer` inside the call path and raise a
Melix `ModelOperationError(code="missing_optional_dependency", ...)` when the
extra is not installed.

Set `NEMO_TELEMETRY_ENABLED=false` by default for this Melix call path unless
the request explicitly opts in.

## Request Mapping

### Model Provider

Melix should map its local OpenAI-compatible gateway or remote-server target
into a DataDesigner model provider:

```python
dd.ModelProvider(
    name="melix",
    endpoint=request.model_provider.endpoint,
    provider_type="openai",
    api_key=request.model_provider.api_key,
    extra_headers=request.model_provider.extra_headers,
)
```

Each model alias maps to:

```python
dd.ModelConfig(
    alias=model.alias,
    model=model.model,
    provider="melix",
    inference_parameters=dd.ChatCompletionInferenceParams(
        temperature=model.temperature,
        top_p=model.top_p,
        max_tokens=model.max_tokens,
        timeout=model.timeout_seconds,
        max_parallel_requests=model.max_parallel_requests,
        extra_body=model.extra_body,
    ),
)
```

Do not store API keys in manifests, configs, or progress payloads. Persist only
the provider name, endpoint origin, model aliases, and model identifiers.

### Columns

The first supported Melix column subset should be conservative:

- `sampler`
- `llm_text`
- `llm_structured`
- `llm_judge`
- `expression`

Defer `validation`, `custom`, `image`, `embedding`, and MCP tool columns until
their security, asset, and dependency contracts are explicit. DataDesigner
validators can execute code, call local Python functions, or call remote
endpoints; Melix needs an explicit sandbox and allowlist contract before
exposing them.

Melix request fields should be declarative JSON-compatible data. The adapter
constructs DataDesigner config objects internally and rejects unknown column
types with `ModelOperationError(code="unsupported_synthetic_column", ...)`.

### Seed Data

The first seed sources should be:

- existing Melix training package
- existing Melix evaluation package
- local JSONL or CSV source
- managed HF dataset snapshot already readable through the dataset registry

The adapter should convert Melix packages to a staging JSONL/Parquet seed file
inside `jobs_root/synthetic-data/<job_id>/seed/`, then call
`DataDesignerConfigBuilder.with_seed_dataset(...)`. Avoid passing in-memory
dataframes across the function boundary because DataDesigner cannot serialize
DataFrame seed configs to reusable config files.

### Output Format

For `output_kind="training"`, `output_format` is the Melix training sample
format. Supported values are the formats listed in the training package section.

For `output_kind="evaluation_final_result"`, `output_format` is the
final-result `result_kind`; supported values are `json` and `text`.

For `output_kind="raw_jsonl"`, `output_format` must be `jsonl`.

## Output Mapping

DataDesigner should produce an intermediate JSONL:

```text
<output_dir>/data_designer/generated.jsonl
```

The Melix adapter then transforms that JSONL into one of these package shapes.

### Training Package

For `output_kind="training"`, normalize generated rows through the same sample
schemas used by `build_training_dataset_artifact`:

- `chat_messages`: requires `messages`
- `prompt_completion`: requires `prompt` and `completion`
- `text_completion`: requires `text`
- `preference_pair`: requires `prompt`, `chosen`, `rejected`
- `prompt_candidate`: requires `prompt`, `candidates`
- `reward_scored`: requires `prompt`, `response`, `reward_score`
- `calibration`: requires `text`

Write:

```text
<output_dir>/manifest.json
<output_dir>/samples.jsonl
<output_dir>/valid.jsonl      # only when validation rows exist
```

Manifest additions beyond the existing training package fields:

```json
{
  "schema_version": "melix.training_dataset_package.v1",
  "source_kind": "datadesigner",
  "operation": "generate_synthetic_dataset",
  "datadesigner": {
    "package": "data-designer",
    "config_path": ".../data_designer/config.json",
    "artifact_path": ".../data_designer/artifacts",
    "generated_jsonl_path": ".../data_designer/generated.jsonl",
    "num_records_requested": 100,
    "num_records_generated": 100,
    "mode": "create",
    "columns": ["topic", "prompt", "completion"],
    "model_aliases": ["generator"]
  }
}
```

### Evaluation Final-Result Package

For `output_kind="evaluation_final_result"`, map generated rows into:

- `system`
- `input`
- `target`
- optional `sample_id`

The function should reuse the final-result materialization semantics from
`evaluation_final_result.py` and write a package whose manifest declares:

```json
{
  "schema_version": "melix.evaluation_dataset_package.v2",
  "source_kind": "datadesigner",
  "profile_type": "final_result",
  "result_kind": "json",
  "extraction_mode": "strict_full_response",
  "scoring_mode": "normalized_exact_match",
  "threshold": 1.0
}
```

The generated `target` field must be valid for the requested `result_kind`
before the package is accepted.

### Raw JSONL

For `output_kind="raw_jsonl"`, only export the DataDesigner JSONL and write a
Melix inspection manifest. This is useful for preview and schema iteration, but
is not build-ready for training or evaluation.

## Execution Steps

1. Validate request fields and reject unsupported output or column types.
2. Resolve `job_id` from `request.job_id` or a deterministic dataset id plus
   timestamp fallback, then create an isolated staging root under
   `jobs_root/synthetic-data/<job_id>/`.
3. Lazy-import DataDesigner and verify the installed version if available.
4. Disable DataDesigner telemetry by default with a scoped environment override
   around the DataDesigner call and restore the prior environment afterward.
5. Build DataDesigner model providers, model configs, columns, and seed config.
6. Write the DataDesigner builder config to
   `<output_dir>/data_designer/config.json` for reproducibility.
7. In preview mode, call `DataDesigner.preview(...)`, convert the in-memory
   dataframe to JSONL, write an inspection manifest, and stop.
8. In create mode, call `DataDesigner.create(...)`, export JSONL with
   `DatasetCreationResults.export(..., format="jsonl")`, and capture profiling
   and task-trace summary metadata.
9. Convert generated rows to the selected Melix package shape.
10. Write manifest, samples, validation split, previews, token or field stats,
    quality counters, and DataDesigner provenance.

## Performance Probes And Metrics

First implementation slice should report these timings in the manifest and
progress events:

- `datadesigner_config_build_ms`
- `datadesigner_generate_ms`
- `datadesigner_export_ms`
- `melix_normalize_ms`
- `melix_package_write_ms`

Success metrics:

- `num_records_generated == num_records_requested` for create mode unless
  DataDesigner reports early shutdown or filtered rows.
- JSONL export uses DataDesigner streaming export, not `load_dataset()`, for
  create mode.
- Peak memory in a local synthetic probe is proportional to one DataDesigner
  output batch plus Melix normalization buffers, not the full generated dataset.
- Manifest contains no secrets.

## Verification

Focused implementation verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_synthetic_dataset_generation.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run \
  --data-file /tmp/synthetic_dataset_generation.coverage \
  --source=worker.productization.synthetic_dataset_generation \
  -m pytest -q \
  services/mlx-worker-python/tests/test_synthetic_dataset_generation.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report \
  --data-file /tmp/synthetic_dataset_generation.coverage \
  --include='*/worker/productization/synthetic_dataset_generation.py'
```

Optional live smoke after the dependency extra is locked:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra synthetic-data \
  python scripts/synthetic_dataset_generation_smoke.py \
  --endpoint http://127.0.0.1:12434/v1 \
  --model melix-dev-text \
  --output-dir .runtime/synthetic-data-smoke
```

## Acceptance Criteria

- A focused adapter function can generate a Melix training package from a
  DataDesigner config without changing existing training package readers.
- The same function can generate a final-result evaluation package from
  DataDesigner rows without changing evaluation execution semantics.
- Preview mode produces inspection artifacts but does not claim build-ready
  package status.
- DataDesigner artifacts, generated JSONL, and Melix manifests are linked by
  stable paths and provenance fields.
- Secrets are redacted from all persisted artifacts.
- DataDesigner remains an optional dependency.

## Risks And Open Questions

- DataDesigner stays behind the `synthetic-data` extra so pandas, pyarrow, MCP,
  and related generation dependencies stay out of the base worker install path.
- Preview results are in memory; large generation must use create mode plus
  streaming export.
- Local Melix gateway compatibility with DataDesigner OpenAI provider should be
  validated against `/v1/chat/completions` before enabling a public command.
- DataDesigner custom columns and validators can execute user logic or call
  remote endpoints; the first Melix surface should expose only declarative,
  allowlisted column specs.
- Final-result evaluation scoring requires target validity. The adapter should
  fail package creation early when generated targets do not match the requested
  `result_kind`.

## Rollback Or Safe Exit

Remove `synthetic_dataset_generation.py`, its focused tests, and the
`synthetic-data` optional extra if the integration direction changes. Generated
runtime artifacts belong under `.runtime/` or the operator-specified output
directory, never under tracked repository paths.
