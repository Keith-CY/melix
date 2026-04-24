from __future__ import annotations

import json
from pathlib import Path
import urllib.request

from tests.integration.helpers import LiveMelixStack


def _write_registry_manifest(
    variant_dir: Path,
    *,
    model_id: str,
    manifest_fields: dict[str, object] | None = None,
) -> None:
    variant_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "melix.model_registry_manifest.v1",
        "model_id": model_id,
        "model_kind": "text",
        "quant_profile_id": "q4",
        "max_context": 8192,
        "ext": {},
    }
    if manifest_fields:
        payload.update(manifest_fields)
    (variant_dir / "manifest.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_models_endpoint_reports_the_discovered_dev_model_before_first_text_request() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
    )
    stack.start()

    try:
        with urllib.request.urlopen(stack.models_url(), timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["object"] == "list"
        model_rows = {item["id"]: item for item in payload["data"]}
        assert model_rows["melix-dev-text"]["melix_state"] == "discovered"
    finally:
        stack.stop()


def test_models_endpoint_exposes_structured_registry_identity_metadata(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry-root"
    runtime_snapshot = tmp_path / "hf-cache" / "models--mlx-community--Qwen2.5-7B-Instruct" / "snapshots" / "abc123"
    descriptor_dir = registry_root / "huggingface" / "mlx-community" / "Qwen2.5-7B-Instruct" / "4bit"
    runtime_snapshot.mkdir(parents=True)
    _write_registry_manifest(
        descriptor_dir,
        model_id="mlx-community/Qwen2.5-7B-Instruct/4bit",
        manifest_fields={
            "provider_id": "hf-mirror",
            "variant_id": "q4f16",
            "ext": {
                "melix.model_path": str(runtime_snapshot),
                "melix.registry_descriptor_path": str(descriptor_dir),
            },
        },
    )

    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        start_swift_text_worker=False,
        environment_overrides={"MELIX_MODEL_ROOTS": str(registry_root)},
    )
    stack.start()

    try:
        with urllib.request.urlopen(stack.models_url(), timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        model_rows = {item["id"]: item for item in payload["data"]}
        discovered = model_rows["mlx-community/Qwen2.5-7B-Instruct/4bit"]

        assert response.status == 200
        assert discovered["melix_state"] == "discovered"
        assert discovered["metadata"]["melix.registry_provider_id"] == "hf-mirror"
        assert discovered["metadata"]["melix.registry_organization_id"] == "mlx-community"
        assert discovered["metadata"]["melix.registry_model_name"] == "Qwen2.5-7B-Instruct"
        assert discovered["metadata"]["melix.registry_variant_id"] == "q4f16"
        assert discovered["metadata"]["melix.registry_relative_path"] == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit"
        assert discovered["metadata"]["melix.registry_descriptor_path"] == str(descriptor_dir)
        assert discovered["metadata"]["melix.model_path"] == str(runtime_snapshot)
    finally:
        stack.stop()
