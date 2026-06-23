# Managed Hugging Face Cache Root Fidelity

## Goal

Honor operator-selected Hugging Face cache roots for Melix-managed Hub downloads and record the
effective cache root in the managed artifact receipt before activation.

## Governing Issue

- GitHub issue: #1258

## Context

Managed artifact integrity receipts now cover operation identity, strict preflight, transport,
digest verification, diagnostics export, companion staging, release policy, and executable model
file trust. The remaining durable-operation watch finding requires cache-root fidelity: a managed
download should not duplicate or ignore a custom Hugging Face cache root, and the receipt should make
the effective root auditable.

## Scope

In scope:

- Respect `melix.hf_cache_root` and `hf_cache_root` request metadata for managed Hub imports.
- Respect process-level `HUGGINGFACE_HUB_CACHE` and `HF_HOME` roots when no request-level cache root
  is supplied, including roots that do not exist yet.
- Pass the resolved cache root to `snapshot_download(cache_dir=...)`.
- Record `melix.effective_hf_cache_root` in the download receipt `ext`.
- Use the same effective cache root as the implicit Hugging Face registry root so detection and
  load metadata point at the operator-selected cache.
- Preserve the default cache root when no explicit cache root or environment override exists.

Out of scope:

- Reworking registry root ordering.
- Adding UI controls for cache roots.
- Changing artifact digest, release policy, companion staging, or executable model file trust.

## Performance Probes

The changed path is managed Hub import setup and receipt materialization. It does not affect model
inference. Verification uses focused download-pipeline and registry catalog tests plus the PR-scoped
performance report for the changed Python scope.

## Verification

Focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_download_pipeline_unit.py::test_managed_hub_import_honors_explicit_hf_cache_root \
  services/mlx-worker-python/tests/test_download_pipeline_unit.py::test_managed_hub_import_honors_hf_home_environment \
  services/mlx-worker-python/tests/test_download_pipeline_unit.py::test_managed_hub_cache_root_honors_request_hf_home \
  services/mlx-worker-python/tests/test_download_pipeline_unit.py::test_managed_hub_cache_root_honors_huggingface_hub_cache_environment \
  services/mlx-worker-python/tests/test_download_pipeline_unit.py::test_managed_hub_cache_root_ignores_missing_huggingface_environment \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload
```

## Acceptance

- Managed Hub imports with `melix.hf_cache_root` call `snapshot_download` with that resolved root.
- Managed Hub imports with `HF_HOME` and no request override call `snapshot_download` with
  `<HF_HOME>/hub`.
- The terminal receipt records `melix.effective_hf_cache_root`.
- Registry discovery uses `HUGGINGFACE_HUB_CACHE` or `<HF_HOME>/hub` as the implicit Hugging Face
  cache root and reports missing configured roots as inaccessible.
- Default behavior remains `~/.cache/huggingface/hub` when no cache root is configured.
