from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worker.runtime.mlx_text_runtime import maybe_apply_native_mtp_text_preload_patches
from worker.runtime.mlx_vlm_runtime import maybe_apply_native_mtp_preload_patches
from worker.runtime.native_mtp.capability import NativeMTPCapabilityDecision, resolve_native_mtp_capability


def _write_model(
    model_dir: Path,
    *,
    config: dict[str, object],
    weight_map: dict[str, str] | None = None,
) -> None:
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    if weight_map is not None:
        (model_dir / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": weight_map}),
            encoding="utf-8",
        )


def _install_fake_native_mtp(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[tuple[str, bool]],
    *,
    patch_result: bool = True,
) -> None:
    class FakeNativeMTP:
        @staticmethod
        def set_mtp_active(active: bool) -> None:
            calls.append(("active", active))

        @staticmethod
        def set_mtp_weight_attachment(active: bool) -> None:
            calls.append(("attach", active))

        @staticmethod
        def apply_native_mtp_patches() -> bool:
            calls.append(("patch", True))
            return patch_result

    import worker.runtime as worker_runtime_pkg

    monkeypatch.setitem(sys.modules, "worker.runtime.native_mtp", FakeNativeMTP)
    monkeypatch.setattr(worker_runtime_pkg, "native_mtp", FakeNativeMTP, raising=False)


def test_registry_accepts_qwen_native_head_shape(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-native-head"
    _write_model(
        model_dir,
        config={
            "model_type": "qwen3_5",
            "text_config": {
                "model_type": "qwen3_5",
                "mtp_num_hidden_layers": 1,
            },
        },
        weight_map={
            "language_model.mtp.fc.weight": "mtp.safetensors",
            "language_model.model.embed_tokens.weight": "model.safetensors",
        },
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=True, active=True)

    assert decision.patchable is True
    assert decision.compatible is True
    assert decision.resolution == "accepted"
    assert decision.refusal_reason == ""
    assert metadata["melix.native_mtp.enabled"] == "true"
    assert metadata["melix.native_mtp.compatible"] == "true"
    assert metadata["melix.native_mtp.weights_present"] == "true"
    assert metadata["melix.native_mtp.weight_count"] == "1"
    assert metadata["melix.native_mtp.reason"] == ""
    assert metadata["melix.native_mtp.family"] == "qwen3_5"
    assert metadata["melix.native_mtp.source"] == "native_head"
    assert metadata["melix.native_mtp.head_count"] == "1"
    assert metadata["melix.native_mtp.batch_shape"] == "singleton_only"
    assert metadata["melix.native_mtp.hardware_gate"] == "not_evaluated"
    assert metadata["melix.native_mtp.resolution"] == "accepted"
    assert metadata["melix.native_mtp.refusal_reason"] == ""
    assert metadata["melix.native_mtp.receipt.schema"] == "melix.native_mtp.capability.v1"
    assert metadata["melix.native_mtp.receipt.status"] == "admitted"
    assert metadata["melix.native_mtp.receipt.mode"] == "speculative_decode"
    assert metadata["melix.native_mtp.receipt.draft_supported"] == "true"
    assert metadata["melix.native_mtp.receipt.effective_depth"] == "1"
    assert metadata["melix.native_mtp.receipt.depth_source"] == "native_head"
    assert metadata["melix.native_mtp.receipt.runtime_scope"] == "text_only_singleton"


def test_registry_refuses_assistant_sidecar_shape(tmp_path: Path) -> None:
    model_dir = tmp_path / "assistant-sidecar"
    _write_model(
        model_dir,
        config={
            "model_type": "gemma4_assistant",
            "mtp_num_hidden_layers": 1,
        },
        weight_map={"mtp.fc.weight": "assistant-mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.speculative.role": "assistant",
            "melix.speculative.kind": "mtp",
        },
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)

    assert decision.patchable is False
    assert decision.compatible is False
    assert decision.resolution == "refused"
    assert decision.refusal_reason == "assistant_sidecar"
    assert metadata["melix.native_mtp.compatible"] == "false"
    assert metadata["melix.native_mtp.source"] == "assistant_sidecar"
    assert metadata["melix.native_mtp.resolution"] == "refused"
    assert metadata["melix.native_mtp.reason"] == "assistant_sidecar"
    assert metadata["melix.native_mtp.receipt.status"] == "refused"
    assert metadata["melix.native_mtp.receipt.fallback_reason"] == "assistant_sidecar"
    assert metadata["melix.native_mtp.receipt.draft_supported"] == "false"


def test_registry_preserves_disabled_legacy_flag_path(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-disabled"
    _write_model(
        model_dir,
        config={
            "model_type": "qwen3_5_text",
            "mtp_num_hidden_layers": 2,
        },
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "false"},
    )
    metadata = decision.to_metadata(patch_applied=True, active=False)

    assert decision.patchable is True
    assert decision.compatible is True
    assert decision.resolution == "legacy_only"
    assert decision.refusal_reason == "disabled"
    assert metadata["melix.native_mtp.enabled"] == "false"
    assert metadata["melix.native_mtp.reason"] == "disabled"
    assert metadata["melix.native_mtp.resolution"] == "legacy_only"
    assert metadata["melix.native_mtp.receipt.status"] == "not_requested"
    assert metadata["melix.native_mtp.receipt.mode"] == "disabled"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "operator_disabled"


def test_registry_reports_missing_native_head_weights(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-missing-head"
    _write_model(
        model_dir,
        config={
            "model_type": "qwen3_5_text",
            "mtp_num_hidden_layers": "bad",
            "text_config": {
                "model_type": "qwen3_5_text",
                "mtp_num_hidden_layers": 1,
            },
        },
        weight_map={"model.embed_tokens.weight": "model.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=True, active=False)

    assert decision.patchable is True
    assert decision.resolution == "refused"
    assert decision.refusal_reason == "missing_mtp_weights"
    assert metadata["melix.native_mtp.reason"] == "missing_mtp_weights"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "missing_native_head_weights"


def test_registry_reports_unsupported_enabled_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "unsupported"
    _write_model(
        model_dir,
        config={"model_type": "llama", "mtp_num_hidden_layers": 0},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)

    assert decision.patchable is False
    assert decision.resolution == "refused"
    assert decision.refusal_reason == "unsupported_model"
    assert metadata["melix.native_mtp.reason"] == "unsupported_model"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "unsupported_model"


def test_registry_treats_invalid_utf8_json_payloads_as_empty(tmp_path: Path) -> None:
    model_dir = tmp_path / "invalid-json-payloads"
    model_dir.mkdir()
    (model_dir / "config.json").write_bytes(b"\xff")
    (model_dir / "model.safetensors.index.json").write_bytes(b"\xff")

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert decision.source == "none"
    assert decision.weights_present is False
    assert decision.refusal_reason == "unsupported_model"


def test_registry_reports_patch_failure_for_native_head(tmp_path: Path) -> None:
    model_dir = tmp_path / "qwen-patch-failed"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)

    assert metadata["melix.native_mtp.reason"] == "patch_failed"
    assert metadata["melix.native_mtp.resolution"] == "refused"
    assert metadata["melix.native_mtp.receipt.status"] == "refused"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "patch_failed"


def test_registry_detects_assistant_sidecar_from_role_or_model_type(tmp_path: Path) -> None:
    role_model_dir = tmp_path / "role-sidecar"
    _write_model(
        role_model_dir,
        config={"model_type": "unknown", "mtp_num_hidden_layers": 1},
    )
    model_type_dir = tmp_path / "model-type-sidecar"
    _write_model(
        model_type_dir,
        config={"model_type": "gemma4_assistant", "architectures": ["GemmaMTPForCausalLM"]},
    )

    by_role = resolve_native_mtp_capability(
        role_model_dir,
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.speculative.role": "assistant",
            "melix.speculative.target_family": "gemma4-v1",
        },
    )
    by_model_type = resolve_native_mtp_capability(
        model_type_dir,
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.speculative.kind": "mtp",
        },
    )

    assert by_role.source == "assistant_sidecar"
    assert by_role.family == "gemma4-v1"
    assert by_model_type.source == "assistant_sidecar"


def test_registry_detects_architecture_only_assistant_sidecar(tmp_path: Path) -> None:
    model_dir = tmp_path / "architecture-sidecar"
    _write_model(
        model_dir,
        config={
            "model_type": "gemma4_assistant",
            "architectures": ["GemmaMTPForCausalLM"],
            "mtp_num_hidden_layers": "not-a-number",
        },
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert decision.source == "assistant_sidecar"
    assert decision.refusal_reason == "assistant_sidecar"
    assert decision.head_count == 0


def test_registry_ignores_non_mtp_assistant_architecture(tmp_path: Path) -> None:
    model_dir = tmp_path / "non-mtp-assistant"
    _write_model(
        model_dir,
        config={
            "model_type": "gemma4_assistant",
            "architectures": ["GemmaForCausalLM"],
            "text_config": {"mtp_num_hidden_layers": "bad"},
            "mtp_num_hidden_layers": "also-bad",
        },
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert decision.source == "none"
    assert decision.refusal_reason == "unsupported_model"
    assert decision.head_count == 0


def test_registry_receipt_supports_empty_fallback_reason() -> None:
    decision = NativeMTPCapabilityDecision(
        enabled=True,
        compatible=False,
        patchable=False,
        weights_present=False,
        weight_count=0,
        family="unknown",
        source="none",
        head_count=0,
        batch_shape="unsupported",
        hardware_gate="not_evaluated",
        resolution="fallback",
        refusal_reason="",
    )

    metadata = decision.to_metadata(patch_applied=False, active=False, reason="")

    assert metadata["melix.native_mtp.reason"] == ""
    assert metadata["melix.native_mtp.resolution"] == "fallback"
    assert metadata["melix.native_mtp.receipt.status"] == "fallback"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "not_admitted"


def test_text_preload_routes_through_registry_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "text-qwen-native-head"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )
    calls: list[tuple[str, bool]] = []
    _install_fake_native_mtp(monkeypatch, calls)

    metadata = maybe_apply_native_mtp_text_preload_patches(
        str(model_dir),
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert metadata["melix.native_mtp.active"] == "true"
    assert metadata["melix.native_mtp.receipt.status"] == "admitted"
    assert ("patch", True) in calls
    assert calls[-1] == ("active", True)


def test_text_preload_routes_through_registry_and_refuses_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "text-sidecar"
    _write_model(
        model_dir,
        config={"model_type": "gemma4_assistant", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "assistant-mtp.safetensors"},
    )
    calls: list[tuple[str, bool]] = []
    _install_fake_native_mtp(monkeypatch, calls)

    metadata = maybe_apply_native_mtp_text_preload_patches(
        str(model_dir),
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.speculative.role": "assistant",
            "melix.speculative.kind": "mtp",
        },
    )

    assert metadata["melix.native_mtp.resolution"] == "refused"
    assert metadata["melix.native_mtp.reason"] == "assistant_sidecar"
    assert ("patch", True) not in calls
    assert calls[-1] == ("active", False)


def test_vlm_preload_routes_through_registry_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "vlm-qwen-native-head"
    _write_model(
        model_dir,
        config={
            "model_type": "qwen3_5",
            "text_config": {
                "model_type": "qwen3_5",
                "mtp_num_hidden_layers": 1,
            },
        },
        weight_map={
            "language_model.mtp.fc.weight": "mtp.safetensors",
            "language_model.model.embed_tokens.weight": "model.safetensors",
        },
    )
    calls: list[tuple[str, bool]] = []
    _install_fake_native_mtp(monkeypatch, calls)

    metadata = maybe_apply_native_mtp_preload_patches(
        str(model_dir),
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert metadata["melix.native_mtp.active"] == "true"
    assert metadata["melix.native_mtp.family"] == "qwen3_5"
    assert metadata["melix.native_mtp.receipt.status"] == "admitted"
    assert metadata["melix.native_mtp.receipt.mode"] == "speculative_decode"
    assert ("patch", True) in calls
    assert calls[-1] == ("active", True)
