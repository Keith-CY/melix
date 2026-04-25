# Issue 63 Hugging Face Cache Scanning, MLX Filtering, and Token Download Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store Melix-managed Hugging Face downloads in the default Hugging Face cache, discover MLX-compatible models from configured roots plus that cache, hide non-MLX models, and allow CLI/Desktop users to provide a cached Hugging Face token for downloads.

**Architecture:** The Python worker remains the authority for download materialization and ordered model-root scanning. Hugging Face Hub downloads call `snapshot_download(cache_dir=~/.cache/huggingface/hub)` explicitly, ignoring `HUGGINGFACE_HUB_CACHE` and `HF_HOME` for Melix-managed downloads. Downloads return the real snapshot path and no longer create a Melix descriptor. Registry discovery scans user-configured model roots first and appends the default Hugging Face cache as an implicit root; it recognizes Hugging Face cache snapshots and plain local MLX directories, but only publishes models with explicit MLX compatibility signals. The Swift CLI and Desktop App cache an optional Hugging Face token in Melix's local secrets store and pass it as a transient request value without protocol changes.

**Tech Stack:** Python 3.12, `huggingface_hub`, pytest, Swift 6, Swift Testing, Melix worker/control-plane protobufs.

---

## Implementation Tasks

- [x] Update `DownloadPipeline` Hub download behavior so `snapshot_download` receives `cache_dir=~/.cache/huggingface/hub`, ignores `HUGGINGFACE_HUB_CACHE` and `HF_HOME`, forwards only a transient token argument, maps 401/403 errors to `hf_auth_failed`, and redacts token-like keys before writing operation state or manifests.
- [x] Return the real Hugging Face snapshot path from `melix model hub download`; do not create a managed Hugging Face descriptor for new downloads.
- [x] Update `WorkerModelCatalog` root discovery so configured `MELIX_MODEL_ROOTS` win first, legacy `MELIX_MANAGED_MODEL_ROOT` remains a compatibility source when configured, and the default Hugging Face cache is appended as an implicit root when present.
- [x] Add Hugging Face cache layout scanning for `models--<org>--<repo>/snapshots/<snapshot-id>`, restore `org/repo` model IDs, infer revisions from `refs/*` when available, skip `blobs`, and expose runtime metadata through `melix.model_path`, `melix.source_kind=hf_cache_snapshot`, `melix.hf_repo_id`, `melix.hf_revision`, `melix.registry_root_path`, and `melix.registry_relative_path`.
- [x] Add plain local MLX directory discovery for configured roots using stable root-relative model IDs and `melix.source_kind=local_mlx_directory`.
- [x] Filter registry output conservatively so only directories with explicit MLX signals from repo ID, README/card metadata, tags, `library_name`, file metadata, or path naming are shown.
- [x] Add CLI support for `melix model hub download --hf-token TOKEN`; cache provided tokens under `$MELIX_HOME/secrets/huggingface-token.json` with private permissions and automatically reuse cached tokens for later downloads.
- [x] Add Desktop App token input and cached-token reuse for the Hugging Face download flow without exposing the raw token in queue state, model rows, menus, details, metadata, logs, or command output.
- [x] Update official docs to describe direct Hugging Face cache storage, ordered root scanning, MLX-only discovery, and token caching.
- [x] Add focused Python, Swift CLI, and Desktop App tests for download cache placement, token forwarding/redaction, registry discovery/filtering, CLI parsing/output, and App token UI plumbing.

## Public Interfaces

- No protobuf schema changes.
- CLI `ManagedModelReceipt.managed_model_path` for Hub downloads is the real Hugging Face snapshot path.
- Registry and `/v1/models` metadata expose the runtime path through `melix.model_path`. Cache/root-discovered models do not expose `melix.registry_descriptor_path`.
- New cache-discovered models disappear from the registry after their snapshot directory is removed and the registry is rescanned. Descriptor-driven `melix.model_path_missing` handling remains only for legacy descriptors that are still present in configured roots.
- CLI and Desktop surfaces show only token presence and masked hints. The raw token is not written to operator state, download queue state, manifest data, registry metadata, `/v1/models`, logs, or PR evidence.
- Hugging Face authentication failures use stable code `hf_auth_failed` and message `Hugging Face authentication failed. Check your token and try again.`

## Verification And Metrics

- Run targeted Python tests for `test_maintenance_service.py`, `test_model_registry_catalog.py`, and `tests/test_real_model_support.py`.
- Run targeted Swift tests for `MelixCLIParserTests`, `MelixCLIRunnerTests`, `ModelCatalogTests`, `ControlPlaneServiceTests`, and `OpenAIHandlerTests`.
- Run targeted Desktop App tests for `RuntimeViewModelTests`, `DesktopFoundationViewTests`, and `StatusMenuTests` covering token input, cached-token reuse, MLX-only display, and no raw-token leakage.
- Run `make py-test`, `make swift-test`, and a relevant integration smoke when feasible.
- Measure changed-line coverage for the touched Python scope and keep it at or above 95 percent.
- Capture a metrics report for the changed scope using existing probes: `registry.reload_latency_ms` and `registry.discovered_model_count`, and confirm scanning does not traverse Hugging Face `blobs` payloads. For non-live verification, record `N/A` with reason.

## Verification Record

- Targeted Python tests: `152 passed` for `test_maintenance_service.py`, `test_model_registry_catalog.py`, and `tests/test_real_model_support.py`.
- Targeted Swift CLI tests: `177 passed` for `MelixCLIParserTests` and `MelixCLIRunnerTests`.
- Targeted Desktop App tests: `404 passed` for the affected RuntimeViewModel, DesktopFoundationView, StatusMenu, CLI workflow, and bootstrap suites.
- Targeted control-plane tests: `338 passed` for `ModelCatalogTests`, `ControlPlaneServiceTests`, and `OpenAIHandlerTests`.
- Full Python suite: `make py-test` passed with `916 passed, 5 skipped`.
- Full Swift suite: `make swift-test` passed for protocol, text worker, control plane, and macOS menu bar packages.
- Integration smoke: `tests/integration/test_models_endpoint.py` passed with `2 passed`.
- Python coverage: `make py-coverage` passed. File-level coverage for touched worker files was `download_pipeline.py` 95% and `catalog.py` 96%; focused helper coverage showed `scripts/real_model_support.py` 96%.
- Live registry metrics and disk-usage evidence: `N/A` in this pass because no network-backed real model download or long-lived Melix stack was started. Deterministic tests cover fixed default HF cache placement, root discovery, MLX-only filtering, snapshot deletion behavior, token forwarding/redaction, and public metadata.

## Acceptance Evidence

- A Hub download of `mlx-community/Qwen3-0.6B-4bit` returns a snapshot path under `~/.cache/huggingface/hub`.
- The registry discovers MLX-compatible Hugging Face cache snapshots and plain local MLX directories, while hiding non-MLX or uncertain directories.
- `/v1/models` reports the actual runtime `melix.model_path` and cache/root identity metadata without descriptor metadata for cache-root-discovered models.
- Generation, benchmark, or eval can resolve a discovered MLX model by model ID without passing an explicit local path.
- A provided Hugging Face token is cached privately, reused for later downloads, and redacted from public outputs.

## Assumptions

- Token support is limited to Hugging Face model downloads; Hub search/show do not use it in this plan.
- CLI `--hf-token` caches by default; this plan does not add separate login/logout commands.
- Tokens are stored in Melix's local JSON secrets store, not macOS Keychain.
- The default Hugging Face cache participates in registry scanning after user-configured roots.
- Scope is limited to MLX-compatible model discovery; non-MLX models are hidden.
- Existing old copied managed layouts remain loadable as compatibility inputs when their roots are configured.
- No dependency or generated protobuf artifact changes are required.
