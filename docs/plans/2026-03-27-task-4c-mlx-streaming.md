# Melix Task 4C Execution Plan: Real MLX Token Streaming

## Scope

This plan extends Task 4B by turning the worker `auto` backend mode into a real MLX text-generation path.

The slice remains narrow:

- keep the explicit `deterministic` and `auto` backend modes
- implement real `mlx-lm` model loading and token streaming for `auto`
- keep deterministic mode as the default integration-test path
- support tokenizer chat-template rendering when the loaded tokenizer exposes it
- map Melix `SamplingConfig` into `mlx-lm` sampling controls
- keep the control-plane HTTP and bridge transport contracts unchanged

This slice does not add:

- worker-side cache reuse or prompt-cache materialization
- speculative decoding
- embeddings, rerank, or multimodal runtime support
- a promise that the default dev model placeholder is a valid MLX model source without explicit environment configuration

## Architecture Boundaries

- The Swift control plane continues to own HTTP translation, SSE formatting, request identity, and cancellation.
- The Python worker continues to own model loading, prompt rendering, and token generation.
- `auto` backend mode means real MLX runtime behavior.
- `deterministic` backend mode remains the stable fallback for local integration and CI coverage.
- The worker model catalog may resolve the development model source from environment so the control plane does not need MLX-specific logic.

## Planned Changes

### Worker runtime

- Implement `AutoMLXBackend.load_model()` by calling `mlx_lm.load(...)`.
- Return a runtime payload that includes the loaded model, tokenizer, and resolved model source.
- Implement `AutoMLXBackend.generate_tokens()` with `mlx_lm.stream_generate(...)`.
- Preserve cancellation by checking the request cancel event between yielded segments.
- Treat empty text segments as non-user-visible and skip them unless they are the terminal segment.

### Prompt rendering

- Extend `MLXTextRuntime.render_prompt(...)` to use `tokenizer.apply_chat_template(..., tokenize=False, add_generation_prompt=True)` when the loaded tokenizer exposes a chat template.
- Keep the current plain-text fallback for fake backends, deterministic mode, and tokenizers without templates.

### Sampling mapping

- Add a small runtime helper that converts Melix `SamplingConfig` into `mlx_lm.sample_utils.make_sampler(...)` arguments.
- Map `temperature`, `top_p`, `top_k`, and `max_output_tokens`.
- Ignore unsupported Melix fields for now rather than inventing behavior.

### Model source resolution

- Allow the development text model source to be overridden with environment configuration for MLX runs.
- Keep the existing `melix-dev-text` model identity unchanged.
- If no valid MLX model source is configured, `auto` mode should fail cleanly with a structured runtime error instead of silently falling back to deterministic mode.

## Performance Probes and Success Metrics

Required probes for this slice:

- MLX model-load latency
- prompt-render latency before generation
- MLX time-to-first-token
- token throughput reported by `mlx-lm`
- worker terminal finish reason

Initial success targets:

- deterministic integration remains green without MLX dependencies enabled in the test command
- touched Python worker scope remains at or above 95 percent automated coverage before commit
- MLX smoke verification is available behind explicit environment configuration
- if no MLX model source is configured, the failure mode is immediate and explicit

If no local MLX model source is available during verification, the metrics report must mark live MLX latency and throughput as `N/A`.

## Verification Plan

Fail-first targeted tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_runtime_edges.py -q
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_generate_stream.py -q
```

Broader verification:

```bash
make py-test
make integration-test
make coverage
```

Optional MLX smoke verification:

```bash
MELIX_DEV_TEXT_MODEL_PATH="<local path or hf repo>" \
uv run --project services/mlx-worker-python --extra mlx python -m worker.bootstrap --socket-path /tmp/melix-worker.sock --backend-mode auto
```

## Exit Conditions

Task 4C is complete when:

- `auto` backend mode no longer raises the placeholder `NotImplementedError`
- the worker can stream real text segments from `mlx-lm.stream_generate(...)`
- prompt rendering uses the tokenizer chat template when available
- deterministic integration remains unchanged and passing
- the worker emits clean runtime errors when MLX is unavailable or the configured model source is invalid
