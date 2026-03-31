from __future__ import annotations

import json
from typing import Any

from worker.model_registry.catalog import WorkerModelCatalog

_ADAPTER_SET_HASH_KEY = "melix.adapter_set_hash"
_CAPABILITY_ROUTE_KIND_KEY = "melix.capability.route_kind"
_CAPABILITY_CLASS_KEY = "melix.capability.class"
_CAPABILITY_SUPPORTED_MODALITIES_KEY = "melix.capability.supported_modalities"
_CAPABILITY_SUPPORTED_TASKS_KEY = "melix.capability.supported_tasks"
_CAPABILITY_SUPPORTED_PARSERS_KEY = "melix.capability.supported_parsers"

_OPERATOR_RUNBOOK = "docs/runbooks/model-family-support-matrix.md"

_FAMILY_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "capability": "embedding",
        "family_id": "bert",
        "model_id": "melix-dev-embed",
        "environment": {},
        "integration_tests": [
            "tests/integration/test_non_text_endpoints.py::test_embeddings_endpoint_returns_vectors",
        ],
    },
    {
        "capability": "embedding",
        "family_id": "xlmr",
        "model_id": "melix-dev-embed",
        "environment": {"MELIX_DEV_EMBED_BACKEND_ID": "xlmr-v1"},
        "integration_tests": [
            "tests/integration/test_non_text_endpoints.py::test_embeddings_endpoint_supports_xlmr_backend_override",
        ],
    },
    {
        "capability": "embedding",
        "family_id": "bge-m3",
        "model_id": "melix-dev-embed",
        "environment": {"MELIX_DEV_EMBED_FAMILY_ID": "bge-m3"},
        "integration_tests": [
            "tests/integration/test_non_text_endpoints.py::test_embeddings_endpoint_supports_bge_and_mxbai_family_overrides",
        ],
    },
    {
        "capability": "embedding",
        "family_id": "mxbai-embed",
        "model_id": "melix-dev-embed",
        "environment": {"MELIX_DEV_EMBED_FAMILY_ID": "mxbai-embed"},
        "integration_tests": [
            "tests/integration/test_non_text_endpoints.py::test_embeddings_endpoint_supports_bge_and_mxbai_family_overrides",
        ],
    },
    {
        "capability": "rerank",
        "family_id": "basic",
        "model_id": "melix-dev-rerank",
        "environment": {"MELIX_DEV_RERANK_MODEL_PATH": "models/basic-reranker"},
        "integration_tests": [],
    },
    {
        "capability": "rerank",
        "family_id": "jina-v3",
        "model_id": "melix-dev-rerank",
        "environment": {},
        "integration_tests": [
            "tests/integration/test_non_text_endpoints.py::test_rerank_endpoint_prefers_exact_order_for_jina_v3_family",
        ],
    },
    {
        "capability": "rerank",
        "family_id": "causal-lm",
        "model_id": "melix-dev-rerank",
        "environment": {"MELIX_DEV_RERANK_FAMILY_ID": "causal-lm"},
        "integration_tests": [
            "tests/integration/test_non_text_endpoints.py::test_rerank_endpoint_supports_causal_lm_yes_no_scoring",
        ],
    },
)


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _contract_payload(variant: dict[str, Any]) -> dict[str, Any]:
    catalog = WorkerModelCatalog(environment=variant["environment"])
    model = catalog.get(variant["model_id"])
    if model is None:
        raise KeyError(f"Unknown model id for family matrix: {variant['model_id']}")

    ext = dict(model.ext)
    contract: dict[str, Any] = {
        "model_id": model.model_id,
        "model_kind": model.model_kind,
        "adapter_set_hash": ext.get(_ADAPTER_SET_HASH_KEY, ""),
        "route_kind": ext.get(_CAPABILITY_ROUTE_KIND_KEY, ""),
        "capability_class": ext.get(_CAPABILITY_CLASS_KEY, ""),
        "supported_modalities": _split_csv(ext.get(_CAPABILITY_SUPPORTED_MODALITIES_KEY, "")),
        "supported_tasks": _split_csv(ext.get(_CAPABILITY_SUPPORTED_TASKS_KEY, "")),
        "supported_parsers": _split_csv(ext.get(_CAPABILITY_SUPPORTED_PARSERS_KEY, "")),
        "architecture": ext.get("model_architecture", ""),
    }

    if variant["capability"] == "embedding":
        contract.update(
            {
                "backend_id": ext.get("embedding_backend_id", ""),
                "pooling_mode": ext.get("embedding_pooling_mode", ""),
                "dimensions": int(ext.get("embedding_dimensions", "0") or "0"),
            }
        )
    else:
        contract.update(
            {
                "backend_id": ext.get("rerank_backend_id", ""),
                "scoring_mode": ext.get("rerank_scoring_mode", ""),
            }
        )

    return contract


def build_family_support_matrix() -> dict[str, Any]:
    families: list[dict[str, Any]] = []
    for variant in _FAMILY_VARIANTS:
        integration_tests = list(variant["integration_tests"])
        families.append(
            {
                "capability": variant["capability"],
                "family_id": variant["family_id"],
                "contract": _contract_payload(variant),
                "live_path": {
                    "status": "verified" if integration_tests else "contract_only",
                    "integration_tests": integration_tests,
                    "operator_runbook": _OPERATOR_RUNBOOK,
                },
            }
        )

    live_verified_count = sum(1 for row in families if row["live_path"]["status"] == "verified")
    contract_only_count = len(families) - live_verified_count

    return {
        "summary": {
            "family_count": len(families),
            "embedding_family_count": sum(1 for row in families if row["capability"] == "embedding"),
            "rerank_family_count": sum(1 for row in families if row["capability"] == "rerank"),
            "live_verified_count": live_verified_count,
            "contract_only_count": contract_only_count,
        },
        "operator_runbooks": [_OPERATOR_RUNBOOK],
        "families": families,
    }


def main() -> None:
    print(json.dumps(build_family_support_matrix(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
