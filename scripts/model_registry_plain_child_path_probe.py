#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

import worker.model_registry.catalog as model_catalog
from worker.model_registry.catalog import WorkerModelCatalog


def main() -> int:
    model_count = int(os.environ.get("MELIX_MODEL_REGISTRY_PLAIN_CHILD_PROBE_MODELS", "400"))
    sample_count = int(os.environ.get("MELIX_MODEL_REGISTRY_PLAIN_CHILD_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    root_plain_child_join_samples: list[float] = []
    root_identity_comparison_samples: list[float] = []
    plain_scan_count_samples: list[float] = []
    manifest_count_samples: list[float] = []
    module_glob_call_samples: list[float] = []
    module_scandir_call_samples: list[float] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "registry"
        root.mkdir()
        for index in range(model_count):
            model_dir = root / f"model-{index:04d}"
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "config.json").write_text(
                json.dumps(
                    {
                        "model_type": "qwen3",
                        "architectures": ["Qwen3ForCausalLM"],
                        "library_name": "mlx",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (model_dir / "weights.safetensors").write_bytes(b"0")

            manifest_dir = root / f"ignored-{index:04d}"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            (manifest_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "melix.model_registry_manifest.v1",
                        "model_id": f"ignored-{index:04d}",
                        "model_kind": "text",
                        "quant_profile_id": "q4",
                        "max_context": 8192,
                        "ext": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

        resolved_root = root.resolve()
        embedding_model_dir = Path(tmpdir) / "artifact-embedding-probe"
        embedding_model_dir.mkdir(parents=True, exist_ok=True)
        pooling_config_path = embedding_model_dir / "1_Pooling" / "config.json"
        pooling_config_path.parent.mkdir()
        pooling_config_path.write_text(
            json.dumps(
                {
                    "pooling_mode_mean_tokens": True,
                    "word_embedding_dimension": 4,
                }
            ),
            encoding="utf-8",
        )
        normalize_config_path = embedding_model_dir / "2_Normalize" / "config.json"
        normalize_config_path.parent.mkdir()
        normalize_config_path.write_text("{}", encoding="utf-8")
        original_truediv = Path.__truediv__
        original_eq = Path.__eq__
        original_glob = Path.glob
        original_scandir = model_catalog.os.scandir

        for _ in range(sample_count):
            root_plain_child_joins = 0
            root_identity_comparisons = 0
            module_glob_calls = 0
            module_scandir_calls = 0

            def tracking_truediv(self: Path, key: object) -> Path:
                nonlocal root_plain_child_joins
                counts_root_plain_child = (
                    self is resolved_root
                    and isinstance(key, str)
                    and (key.startswith("model-") or key.startswith("ignored-"))
                )
                result = original_truediv(self, key)  # type: ignore[arg-type]
                if counts_root_plain_child:
                    root_plain_child_joins += 1
                return result

            def tracking_eq(self: Path, other: object) -> bool:  # pragma: no cover - optimized path should not call this
                nonlocal root_identity_comparisons
                if self is resolved_root or other is resolved_root:
                    root_identity_comparisons += 1
                return original_eq(self, other)

            def tracking_glob(self: Path, pattern: str):
                nonlocal module_glob_calls
                if self == embedding_model_dir:  # pragma: no cover - optimized head should not call Path.glob
                    module_glob_calls += 1
                return original_glob(self, pattern)  # pragma: no cover - optimized head should not call Path.glob

            def tracking_scandir(path: str):
                nonlocal module_scandir_calls
                if path == os.fspath(embedding_model_dir):
                    module_scandir_calls += 1
                return original_scandir(path)

            Path.__truediv__ = tracking_truediv  # type: ignore[method-assign]
            Path.__eq__ = tracking_eq  # type: ignore[method-assign]
            Path.glob = tracking_glob  # type: ignore[method-assign]
            model_catalog.os.scandir = tracking_scandir
            try:
                started = time.perf_counter()
                manifests, plain_scans, hf_repos = WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(root)
                module_paths = model_catalog._artifact_embedding_module_paths(embedding_model_dir)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
            finally:
                Path.__truediv__ = original_truediv
                Path.__eq__ = original_eq
                Path.glob = original_glob  # type: ignore[method-assign]
                model_catalog.os.scandir = original_scandir

            if module_paths != (pooling_config_path, normalize_config_path):
                raise SystemExit(f"unexpected embedding module paths: {module_paths!r}")  # pragma: no cover

            if hf_repos:
                raise SystemExit(f"unexpected hf repos: {hf_repos!r}")
            if len(plain_scans) != model_count:
                raise SystemExit(f"unexpected plain scan count: {len(plain_scans)} != {model_count}")
            if len(manifests) != model_count:
                raise SystemExit(f"unexpected manifest count: {len(manifests)} != {model_count}")
            elapsed_samples.append(elapsed_ms)
            root_plain_child_join_samples.append(float(root_plain_child_joins))
            root_identity_comparison_samples.append(float(root_identity_comparisons))
            plain_scan_count_samples.append(float(len(plain_scans)))
            manifest_count_samples.append(float(len(manifests)))
            module_glob_call_samples.append(float(module_glob_calls))
            module_scandir_call_samples.append(float(module_scandir_calls))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "root_plain_child_path_joins_mean": round(statistics.fmean(root_plain_child_join_samples), 6),
                "root_identity_comparisons_mean": round(statistics.fmean(root_identity_comparison_samples), 6),
                "plain_scan_count_mean": round(statistics.fmean(plain_scan_count_samples), 6),
                "manifest_count_mean": round(statistics.fmean(manifest_count_samples), 6),
                "module_path_glob_calls_mean": round(statistics.fmean(module_glob_call_samples), 6),
                "module_path_scandir_calls_mean": round(statistics.fmean(module_scandir_call_samples), 6),
                "model_count": float(model_count),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
