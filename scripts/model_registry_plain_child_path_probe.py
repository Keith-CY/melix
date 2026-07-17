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

from worker.model_registry.catalog import WorkerModelCatalog


def main() -> int:
    model_count = int(os.environ.get("MELIX_MODEL_REGISTRY_PLAIN_CHILD_PROBE_MODELS", "400"))
    sample_count = int(os.environ.get("MELIX_MODEL_REGISTRY_PLAIN_CHILD_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    root_plain_child_join_samples: list[float] = []
    plain_scan_count_samples: list[float] = []
    manifest_count_samples: list[float] = []

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
        original_truediv = Path.__truediv__

        for _ in range(sample_count):
            root_plain_child_joins = 0

            def tracking_truediv(self: Path, key: object) -> Path:
                nonlocal root_plain_child_joins
                counts_root_plain_child = (
                    self == resolved_root
                    and isinstance(key, str)
                    and (key.startswith("model-") or key.startswith("ignored-"))
                )
                result = original_truediv(self, key)  # type: ignore[arg-type]
                if counts_root_plain_child:
                    root_plain_child_joins += 1
                return result

            Path.__truediv__ = tracking_truediv  # type: ignore[method-assign]
            try:
                started = time.perf_counter()
                manifests, plain_scans, hf_repos = WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(root)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
            finally:
                Path.__truediv__ = original_truediv

            if hf_repos:
                raise SystemExit(f"unexpected hf repos: {hf_repos!r}")
            if len(plain_scans) != model_count:
                raise SystemExit(f"unexpected plain scan count: {len(plain_scans)} != {model_count}")
            if len(manifests) != model_count:
                raise SystemExit(f"unexpected manifest count: {len(manifests)} != {model_count}")
            elapsed_samples.append(elapsed_ms)
            root_plain_child_join_samples.append(float(root_plain_child_joins))
            plain_scan_count_samples.append(float(len(plain_scans)))
            manifest_count_samples.append(float(len(manifests)))

    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "root_plain_child_path_joins_mean": round(statistics.fmean(root_plain_child_join_samples), 6),
                "plain_scan_count_mean": round(statistics.fmean(plain_scan_count_samples), 6),
                "manifest_count_mean": round(statistics.fmean(manifest_count_samples), 6),
                "model_count": float(model_count),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
