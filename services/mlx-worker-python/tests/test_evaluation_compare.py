from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from packages.protocol.python.worker.v1 import common_pb2
from worker.productization.evaluation_compare import (
    load_adapter_target_spec,
    resolve_compare_target_adapters,
    resolve_compare_target_models,
)


class _FakeRegistry:
    def __init__(self, model_ids: list[str]) -> None:
        self._handles = [f"handle-{index}" for index in range(len(model_ids))]
        self._loaded_by_handle = {
            handle: SimpleNamespace(spec=SimpleNamespace(model_id=model_id))
            for handle, model_id in zip(self._handles, model_ids, strict=True)
        }
        self.get_loaded_model_calls: list[str] = []

    def list_loaded_models(self) -> list[str]:
        return list(self._handles)

    def get_loaded_model(self, handle: str) -> object | None:
        self.get_loaded_model_calls.append(handle)
        return self._loaded_by_handle.get(handle)


class _AdapterLoadRegistry:
    def __init__(self) -> None:
        self.loaded_model_specs: list[common_pb2.ModelSpec] = []
        self.load_model_calls: list[str] = []
        self.unload_model_calls: list[str] = []

    def load_model(self, model_spec: common_pb2.ModelSpec):
        model_spec_snapshot = common_pb2.ModelSpec()
        model_spec_snapshot.CopyFrom(model_spec)
        self.loaded_model_specs.append(model_spec_snapshot)
        self.load_model_calls.append(str(model_spec.model_id))
        handle = f"handle-{len(self.load_model_calls)}"
        return SimpleNamespace(handle=handle, spec=model_spec)

    def unload_model(self, handle: str) -> bool:
        self.unload_model_calls.append(handle)
        return True


def _write_adapter_manifest(
    *,
    tmp_path: Path,
    adapter_name: str,
    source_model_id: str = "melix-dev-text",
    adapter_set_hash: str = "adapterhash12345678",
) -> Path:
    weights_dir = tmp_path / f"weights-{adapter_name}"
    weights_dir.mkdir(parents=True, exist_ok=True)
    weights_path = weights_dir / "adapters.safetensors"
    weights_path.write_text("", encoding="utf-8")
    manifest_path = tmp_path / f"{adapter_name}.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "job_id": f"job-{adapter_name}",
                "adapter_name": adapter_name,
                "adapter_set_hash": adapter_set_hash,
                "weights_path": str(weights_path),
                "source_model": source_model_id,
                "source_model_path": f"/tmp/{source_model_id}/model",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_resolve_compare_target_models_short_circuits_after_all_targets_found() -> None:
    registry = _FakeRegistry(["target-a", "target-b", *[f"unused-{index}" for index in range(1000)]])

    resolved = resolve_compare_target_models(
        registry=registry,
        target_model_ids=("target-a", "target-b"),
    )

    assert tuple(resolved) == ("target-a", "target-b")
    assert [loaded.spec.model_id for loaded in resolved.values()] == ["target-a", "target-b"]
    assert registry.get_loaded_model_calls == ["handle-0", "handle-1"]


def test_resolve_compare_target_models_preserves_requested_order_after_short_circuit() -> None:
    registry = _FakeRegistry(["target-a", "target-b", "target-c", "unused"])

    resolved = resolve_compare_target_models(
        registry=registry,
        target_model_ids=("target-c", "target-a"),
    )

    assert tuple(resolved) == ("target-c", "target-a")
    assert [loaded.spec.model_id for loaded in resolved.values()] == ["target-c", "target-a"]
    assert registry.get_loaded_model_calls == ["handle-0", "handle-1", "handle-2"]


def test_resolve_compare_target_models_scans_all_handles_when_target_missing() -> None:
    registry = _FakeRegistry(["target-a", "target-b", "target-c"])

    with pytest.raises(ValueError, match="Unknown comparison target model IDs: missing-target"):
        resolve_compare_target_models(
            registry=registry,
            target_model_ids=("target-a", "missing-target"),
        )

    assert registry.get_loaded_model_calls == ["handle-0", "handle-1", "handle-2"]


def test_resolve_compare_target_models_ignores_empty_and_none_loaded_models() -> None:
    registry = _FakeRegistry(["", "target-a", "unused"])
    registry._loaded_by_handle["handle-0"] = SimpleNamespace(spec=SimpleNamespace(model_id=""))
    registry._loaded_by_handle["handle-1"] = None
    registry._loaded_by_handle["handle-2"] = SimpleNamespace(spec=SimpleNamespace(model_id="target-a"))

    resolved = resolve_compare_target_models(
        registry=registry,
        target_model_ids=("target-a",),
    )

    assert tuple(resolved) == ("target-a",)
    assert registry.get_loaded_model_calls == ["handle-0", "handle-1", "handle-2"]


def test_load_adapter_target_spec_populates_runtime_fields_and_ephemeral_id(
    tmp_path: Path,
) -> None:
    manifest_path = _write_adapter_manifest(
        tmp_path=tmp_path,
        adapter_name="adapter",
        adapter_set_hash="deadbeefcafebabe",
    )

    spec = load_adapter_target_spec(manifest_path=manifest_path, job_id="model-ops-0042")

    expected_suffix = hashlib.sha256(b"model-ops-0042").hexdigest()[:8]
    assert spec.ephemeral_derived_model_id == (
        f"melix-dev-text-lora-deadbeef-compare-{expected_suffix}"
    )
    assert spec.adapter_set_hash == "deadbeefcafebabe"
    assert spec.adapter_weights_path.endswith("adapters.safetensors")
    assert spec.derived_from_model_id == "melix-dev-text"
    assert spec.derived_from_model_path == "/tmp/melix-dev-text/model"
    assert spec.runtime_manifest_fields["adapter_runtime.switch_mode"] == "base_reuse_adapter_swap"
    assert spec.runtime_manifest_fields["adapter_runtime.sharing_policy"] == "shared_base_isolated_adapter"
    assert spec.runtime_manifest_fields["adapter_runtime.compatibility_status"] == "compatible"
    assert len(spec.runtime_manifest_fields["adapter_runtime.base_reuse_key"]) == 64
    assert len(spec.runtime_manifest_fields["adapter_runtime.adapter_isolation_key"]) == 64


def test_load_adapter_target_spec_shares_base_key_and_isolates_adapters(
    tmp_path: Path,
) -> None:
    manifest_a = _write_adapter_manifest(
        tmp_path=tmp_path,
        adapter_name="alpha",
        adapter_set_hash="adapteralpha1234",
    )
    manifest_b = _write_adapter_manifest(
        tmp_path=tmp_path,
        adapter_name="beta",
        adapter_set_hash="adapterbeta5678",
    )

    spec_a = load_adapter_target_spec(manifest_path=manifest_a, job_id="compare-shared")
    spec_b = load_adapter_target_spec(manifest_path=manifest_b, job_id="compare-shared")

    assert (
        spec_a.runtime_manifest_fields["adapter_runtime.base_reuse_key"]
        == spec_b.runtime_manifest_fields["adapter_runtime.base_reuse_key"]
    )
    assert (
        spec_a.runtime_manifest_fields["adapter_runtime.adapter_isolation_key"]
        != spec_b.runtime_manifest_fields["adapter_runtime.adapter_isolation_key"]
    )
    assert spec_a.ephemeral_derived_model_id != spec_b.ephemeral_derived_model_id


def test_resolve_compare_target_adapters_loads_runtime_ext_fields(tmp_path: Path) -> None:
    manifest_path = _write_adapter_manifest(tmp_path=tmp_path, adapter_name="runtime")
    spec = load_adapter_target_spec(manifest_path=manifest_path, job_id="compare-runtime")
    registry = _AdapterLoadRegistry()

    loaded, unload_handles = resolve_compare_target_adapters(
        registry=registry,
        adapter_target_specs=(spec,),
    )

    assert tuple(loaded) == (spec.ephemeral_derived_model_id,)
    assert unload_handles == ["handle-1"]
    loaded_spec = registry.loaded_model_specs[0]
    assert loaded_spec.ext["melix.adapter_runtime.switch_mode"] == "base_reuse_adapter_swap"
    assert loaded_spec.ext["melix.adapter_runtime.sharing_policy"] == "shared_base_isolated_adapter"
    assert loaded_spec.ext["melix.adapter_runtime.compatibility_status"] == "compatible"
    assert len(loaded_spec.ext["melix.adapter_runtime.base_reuse_key"]) == 64
    assert len(loaded_spec.ext["melix.adapter_runtime.adapter_isolation_key"]) == 64
