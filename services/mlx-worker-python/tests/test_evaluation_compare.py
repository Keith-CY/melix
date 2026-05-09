from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker.productization.evaluation_compare import resolve_compare_target_models


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
