# Hub Catalog KV Cache Fit Evidence

## Scope

This Python-only slice improves Hub catalog local-fit evidence for MLX text models. It applies the guide principle that local fit is not just model weights: the live resident estimate must include the KV cache implied by the advertised context window when Hub config metadata provides enough architecture fields.

Affected implementation path:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`

Affected tests:

- `services/mlx-worker-python/tests/test_hub_catalog.py`

## Behavior

When Hub payload `config` metadata includes text-model architecture values, Melix should estimate FP16/BF16 KV-cache bytes with:

```text
context_tokens * layers * kv_heads * head_dim * bytes_per_element * 2
```

The estimate should use the model's key/value head count when available, otherwise attention heads, and should derive `head_dim` from `hidden_size / num_attention_heads` when an explicit head dimension is absent. The estimate is added to the existing resident-byte estimate before local-fit status is chosen. Local-fit reasons should mention the KV-cache estimate so operators can see that long-context memory is included.

If the required config metadata is missing, existing behavior remains unchanged.

## Metrics And Verification

- Focused behavior: `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py`
- Changed-scope coverage: run the registered Hub catalog coverage command from `infra/perf/pr_scoped_probes.json`.
- Performance: the existing Hub catalog PR-scoped probes still cover the changed file and should run in CI.

## Acceptance

- A small 4-bit model with a large advertised context can be marked `heavy` when estimated KV-cache bytes push resident memory beyond the comfort budget.
- Existing local-fit behavior for payloads without usable config metadata stays unchanged.
