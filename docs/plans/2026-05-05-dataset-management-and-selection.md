# Dataset Management And Selection

## Context

Melix model management already treats the default Hugging Face hub cache as an
implicit local root. Operators can download a model through `melix model hub
download`, rescan the registry, and then use the cached snapshot as a managed
local artifact. Datasets need the same local-first treatment so benchmark,
evaluation, and training workflows can reuse datasets that were downloaded with
Melix or with the Hugging Face CLI.

## Goals

- Discover Hugging Face dataset snapshots under the default hub cache
  (`~/.cache/huggingface/hub/datasets--*`) without requiring a separate import.
- Add CLI dataset management commands for listing, downloading, and removing
  managed dataset snapshots.
- Download datasets through the same model-operation job channel used by model
  hub downloads, while passing `repo_type="dataset"` to Hugging Face Hub.
- Remove only snapshot working trees from the HF cache. Blob and lock cleanup is
  intentionally out of scope because those files may be shared by other
  revisions.
- Let `bench run` and `eval run` accept an explicit managed dataset reference.
- Make evaluation HF dataset materialization prefer a local cached snapshot
  before falling back to the Hugging Face Dataset Viewer API.

## Non-Goals

- No new protobuf RPCs in this slice. Dataset management reuses
  `ConvertModelRequest.ext.operation`, matching the current model operations
  path and avoiding generated artifact churn.
- No dataset root CRUD in the first slice. The implicit HF cache root is the
  required local-first source of truth; extra roots can follow after the data
  model settles.
- No blob reference counting or cache vacuuming.
- No broad desktop UI redesign. The CLI and worker semantics are the stable
  backend contract for a later UI surface.

## Design

### Dataset Snapshot Catalog

The worker owns a small dataset catalog that scans the default HF hub cache for
directories named `datasets--*`. Each repo directory is interpreted as:

- `datasets--org--repo` -> `org/repo`
- `datasets--repo` -> `repo`

For each `snapshots/<sha>` directory the catalog records:

- `dataset_id`: `repo_id@revision`
- `repo_id`
- `revision`, resolved from `refs/*` when present, otherwise the snapshot hash
- `snapshot_id`
- `snapshot_path`
- `source_kind`: `hf_cache_snapshot`
- file inventory for JSONL, JSON, CSV, Parquet, Arrow, and README files
- total snapshot bytes
- inferred split names from dataset file names
- a restore command using `melix dataset hub download`

### Operations

Dataset operations use the existing `ConvertModel` stream:

- `dataset_snapshot`: emits a manifest containing `dataset_registry.datasets`
- `dataset_download`: calls `snapshot_download(..., repo_type="dataset")`,
  then emits a completed manifest for the cached snapshot
- `dataset_remove`: resolves a repo plus revision or snapshot id and removes
  only `snapshots/<sha>`

HF tokens use the same CLI token store as model hub downloads. Worker manifests
must not echo tokens.

### Selection

`melix eval run --dataset-ref REPO[@REV]` is equivalent to passing
`--hf-dataset-path REPO --hf-dataset-revision REV`, with the additional intent
that the worker should prefer a locally cached snapshot. `--hf-dataset-name`,
`--hf-dataset-split`, and the existing field mapping options keep their current
meaning.

`melix bench run --dataset-ref REPO[@REV]` overrides the suite dataset source.
The existing suite prompt/image feature defaults remain in force unless the
operator passes explicit dataset feature options. The selected dataset reference
is persisted in benchmark parameters and suite metadata.

### Local Materialization

When a requested HF dataset snapshot is present locally, materialization reads
rows directly from supported snapshot files:

- `.jsonl`
- `.json`
- `.csv`
- `.parquet` when `pyarrow` is available

If no local snapshot can satisfy the request, the existing Dataset Viewer API
fallback remains in place.

## Verification Plan

- Python unit tests for synthetic HF dataset cache scanning, row loading,
  download manifest behavior, safe snapshot removal, and local evaluation
  materialization.
- Swift parser and runner tests for new `dataset` commands, `--dataset-ref`
  parsing, token redaction/reuse, and benchmark/evaluation parameter plumbing.
- Targeted commands:
  - `uv run pytest services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_benchmark_suites.py`
  - `swift test --filter MelixCLIParserTests`
  - `swift test --filter MelixCLIRunnerTests`

## Metrics Report

Changed-scope coverage is measurable for the Python and Swift test scopes above.
The success criterion before handoff is targeted test pass plus an explicit
coverage or N/A note if the local coverage tooling does not support the touched
mixed Python/Swift slice in one command.
