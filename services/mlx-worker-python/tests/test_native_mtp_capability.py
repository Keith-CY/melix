from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from worker.runtime.native_mtp import capability as native_mtp_capability
from worker.runtime.mlx_text_runtime import maybe_apply_native_mtp_text_preload_patches
from worker.runtime.mlx_vlm_runtime import maybe_apply_native_mtp_preload_patches
from worker.runtime.native_mtp.capability import (
    NativeMTPCapabilityDecision,
    resolve_native_mtp_capability,
)


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


def _native_mtp_receipt(metadata: dict[str, str]) -> dict[str, object]:
    receipt = json.loads(metadata["melix.native_mtp.receipt_json"])
    assert receipt["schema_version"] == metadata["melix.native_mtp.receipt.schema"]
    assert receipt["status"] == metadata["melix.native_mtp.receipt.status"]
    assert receipt["mode"] == metadata["melix.native_mtp.receipt.mode"]
    assert receipt["fallback_reason"] == metadata["melix.native_mtp.receipt.fallback_reason"]
    assert receipt["source"] == metadata["melix.native_mtp.receipt.source"]
    assert receipt["family"] == metadata["melix.native_mtp.receipt.family"]
    assert str(receipt["weight_count"]) == metadata["melix.native_mtp.receipt.weight_count"]
    assert str(receipt["effective_depth"]) == metadata["melix.native_mtp.receipt.effective_depth"]
    assert receipt["depth_source"] == metadata["melix.native_mtp.receipt.depth_source"]
    assert receipt["batch_shape"] == metadata["melix.native_mtp.receipt.batch_shape"]
    assert (
        receipt["batch_filter_policy"]
        == metadata["melix.native_mtp.receipt.batch_filter_policy"]
    )
    assert (
        receipt["batch_extend_policy"]
        == metadata["melix.native_mtp.receipt.batch_extend_policy"]
    )
    assert (
        receipt["batch_multi_row_policy"]
        == metadata["melix.native_mtp.receipt.batch_multi_row_policy"]
    )
    assert receipt["hardware_gate"] == metadata["melix.native_mtp.receipt.hardware_gate"]
    assert receipt["hardware_policy"] == metadata["melix.native_mtp.receipt.hardware_policy"]
    assert (
        receipt["hardware_policy_reason"]
        == metadata["melix.native_mtp.receipt.hardware_policy_reason"]
    )
    assert (
        receipt["hardware_policy_source"]
        == metadata["melix.native_mtp.receipt.hardware_policy_source"]
    )
    assert receipt["operator_override"] == metadata["melix.native_mtp.receipt.operator_override"]
    assert receipt["request_gate"] == metadata["melix.native_mtp.receipt.request_gate"]
    assert receipt["runtime_scope"] == metadata["melix.native_mtp.receipt.runtime_scope"]
    assert str(receipt["weights_present"]).lower() == metadata["melix.native_mtp.receipt.weights_present"]
    assert str(receipt["draft_supported"]).lower() == metadata["melix.native_mtp.receipt.draft_supported"]
    assert str(receipt["draft_loaded"]).lower() == metadata["melix.native_mtp.receipt.draft_loaded"]
    assert (
        str(receipt["target_decode_started"]).lower()
        == metadata["melix.native_mtp.receipt.target_decode_started"]
    )
    return receipt


def test_batch_generator_declares_batch_state_policy() -> None:
    from worker.runtime.native_mtp import batch_generator

    assert batch_generator.batch_state_policy_receipt() == {
        "batch_shape": "singleton_only",
        "batch_state_policy": "singleton_timeline_safe",
        "batch_filter_policy": "preserve_when_singleton_uid_matches",
        "batch_extend_policy": "reconcile_then_drop",
        "batch_multi_row_policy": "multi_row_decode_unsupported",
    }


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
        hardware_profile=SimpleNamespace(),
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
    assert metadata["melix.native_mtp.hardware_gate"] == "admitted"
    assert metadata["melix.native_mtp.resolution"] == "accepted"
    assert metadata["melix.native_mtp.refusal_reason"] == ""
    assert metadata["melix.native_mtp.receipt.schema"] == "melix.native_mtp.capability.v1"
    assert metadata["melix.native_mtp.receipt.status"] == "admitted"
    assert metadata["melix.native_mtp.receipt.mode"] == "speculative_decode"
    assert metadata["melix.native_mtp.receipt.draft_supported"] == "true"
    assert metadata["melix.native_mtp.receipt.effective_depth"] == "1"
    assert metadata["melix.native_mtp.receipt.depth_source"] == "native_head"
    assert metadata["melix.native_mtp.receipt.runtime_scope"] == "text_only_singleton"
    assert _native_mtp_receipt(metadata) == {
        "schema_version": "melix.native_mtp.capability.v1",
        "status": "admitted",
        "requested_method": "native_mtp",
        "resolved_method": "native_mtp",
        "mode": "speculative_decode",
        "source": "native_head",
        "family": "qwen3_5",
        "compatible": True,
        "weights_present": True,
        "weight_count": 1,
        "draft_supported": True,
        "effective_depth": 1,
        "depth_source": "native_head",
        "cache_shape": "qwen3_5_native_mtp",
        "batch_shape": "singleton_only",
        "batch_state_policy": "singleton_timeline_safe",
        "batch_filter_policy": "preserve_when_singleton_uid_matches",
        "batch_extend_policy": "reconcile_then_drop",
        "batch_multi_row_policy": "multi_row_decode_unsupported",
        "hardware_gate": "admitted",
        "hardware_policy": "auto",
        "hardware_policy_reason": "unclassified_device",
        "hardware_policy_source": "auto",
        "operator_override": "",
        "request_gate": "native_mtp_enabled",
        "runtime_scope": "text_only_singleton",
        "patch_applied": True,
        "draft_loaded": True,
        "target_decode_started": False,
        "fallback_reason": "",
    }


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
        hardware_profile=SimpleNamespace(),
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
    assert _native_mtp_receipt(metadata) == {
        "schema_version": "melix.native_mtp.capability.v1",
        "status": "refused",
        "requested_method": "native_mtp",
        "resolved_method": "disabled",
        "mode": "disabled",
        "source": "assistant_sidecar",
        "family": "gemma4_assistant",
        "compatible": False,
        "weights_present": True,
        "weight_count": 1,
        "draft_supported": False,
        "effective_depth": 0,
        "depth_source": "none",
        "cache_shape": "none",
        "batch_shape": "unsupported",
        "batch_state_policy": "none",
        "batch_filter_policy": "none",
        "batch_extend_policy": "none",
        "batch_multi_row_policy": "none",
        "hardware_gate": "admitted",
        "hardware_policy": "auto",
        "hardware_policy_reason": "unclassified_device",
        "hardware_policy_source": "auto",
        "operator_override": "",
        "request_gate": "assistant_sidecar_refused",
        "runtime_scope": "none",
        "patch_applied": False,
        "draft_loaded": False,
        "target_decode_started": False,
        "fallback_reason": "assistant_sidecar",
    }


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
        hardware_profile=SimpleNamespace(),
    )
    metadata = decision.to_metadata(patch_applied=True, active=False)

    assert decision.patchable is True
    assert decision.resolution == "refused"
    assert decision.refusal_reason == "missing_mtp_weights"
    assert metadata["melix.native_mtp.reason"] == "missing_mtp_weights"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "missing_native_head_weights"


def test_registry_recognizes_deepseek_v3_nextn_and_fails_closed_until_patch_exists(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "deepseek-v3-nextn"
    _write_model(
        model_dir,
        config={
            "model_type": "deepseek_v3",
            "num_nextn_predict_layers": 2,
        },
        weight_map={
            "model.layers.0.shared_head.head.weight": "nextn.safetensors",
            "model.layers.0.eh_proj.weight": "nextn.safetensors",
            "model.embed_tokens.weight": "model.safetensors",
        },
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)
    receipt = _native_mtp_receipt(metadata)

    assert decision.compatible is True
    assert decision.patchable is False
    assert decision.family == "deepseek_v3_nextn"
    assert decision.source == "native_head"
    assert decision.head_count == 2
    assert decision.weights_present is True
    assert decision.weight_count == 2
    assert decision.resolution == "refused"
    assert decision.refusal_reason == "patch_unsupported"
    assert metadata["melix.native_mtp.reason"] == "patch_unsupported"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "patch_unsupported"
    assert receipt["family"] == "deepseek_v3_nextn"
    assert receipt["cache_shape"] == "deepseek_v3_nextn_native_mtp"
    assert receipt["effective_depth"] == 0
    assert receipt["draft_supported"] is False


def test_registry_reports_missing_deepseek_nextn_weights(tmp_path: Path) -> None:
    model_dir = tmp_path / "deepseek-v3-missing-nextn"
    _write_model(
        model_dir,
        config={
            "model_type": "deepseek_v3",
            "num_nextn_predict_layers": 2,
        },
        weight_map={"model.embed_tokens.weight": "model.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)

    assert decision.compatible is True
    assert decision.patchable is False
    assert decision.weights_present is False
    assert decision.refusal_reason == "missing_mtp_weights"
    assert metadata["melix.native_mtp.reason"] == "missing_mtp_weights"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "missing_native_head_weights"


def test_registry_device_policy_auto_disables_lower_end_m2(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-m2"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
        hardware_profile=SimpleNamespace(
            system="Darwin",
            machine="arm64",
            chip_family="Apple M2 Pro",
            model_identifier="Mac14,7",
        ),
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)
    receipt = _native_mtp_receipt(metadata)

    assert decision.compatible is True
    assert decision.patchable is True
    assert decision.refusal_reason == "device_policy_disabled"
    assert metadata["melix.native_mtp.hardware_gate"] == "disabled"
    assert metadata["melix.native_mtp.reason"] == "device_policy_disabled"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "device_policy_disabled"
    assert receipt["hardware_policy"] == "auto"
    assert receipt["hardware_policy_reason"] == "m1_m2_compute_bound"
    assert receipt["hardware_policy_source"] == "auto"


def test_registry_device_policy_force_on_overrides_lower_end_m2(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-force-on"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.device_policy": "force_on",
        },
        hardware_profile=SimpleNamespace(
            system="Darwin",
            machine="arm64",
            chip_family="Apple M2 Pro",
            model_identifier="Mac14,7",
        ),
    )
    metadata = decision.to_metadata(patch_applied=True, active=True)
    receipt = _native_mtp_receipt(metadata)

    assert metadata["melix.native_mtp.hardware_gate"] == "admitted"
    assert metadata["melix.native_mtp.reason"] == ""
    assert receipt["hardware_policy"] == "force_on"
    assert receipt["hardware_policy_reason"] == "operator_force_on"
    assert receipt["hardware_policy_source"] == "operator"
    assert receipt["operator_override"] == "force_on"


def test_registry_device_policy_force_off_refuses_even_capable_qwen(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-force-off"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.device_policy": "force_off",
        },
        hardware_profile=SimpleNamespace(
            system="Darwin",
            machine="arm64",
            chip_family="Apple M4 Max",
            model_identifier="Mac16,5",
        ),
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)
    receipt = _native_mtp_receipt(metadata)

    assert decision.refusal_reason == "device_policy_disabled"
    assert metadata["melix.native_mtp.hardware_gate"] == "disabled"
    assert metadata["melix.native_mtp.reason"] == "device_policy_disabled"
    assert receipt["hardware_policy"] == "force_off"
    assert receipt["hardware_policy_reason"] == "operator_force_off"
    assert receipt["hardware_policy_source"] == "operator"
    assert receipt["operator_override"] == "force_off"


def test_registry_device_policy_auto_admits_supported_apple_silicon(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-m4"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
        hardware_profile=SimpleNamespace(
            system="Darwin",
            machine="arm64",
            chip_family="Apple M4 Max",
            model_identifier="Mac16,5",
        ),
    )
    metadata = decision.to_metadata(patch_applied=True, active=True)
    receipt = _native_mtp_receipt(metadata)

    assert decision.refusal_reason == ""
    assert metadata["melix.native_mtp.hardware_gate"] == "admitted"
    assert metadata["melix.native_mtp.reason"] == ""
    assert receipt["hardware_policy"] == "auto"
    assert receipt["hardware_policy_reason"] == "supported_apple_silicon"
    assert receipt["hardware_policy_source"] == "auto"


def test_registry_detects_darwin_arm64_hardware_once_and_caches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-detected-m4"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )
    calls: list[str] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> SimpleNamespace:
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 5
        calls.append(command[-1])
        stdout = (
            "Apple M4 Max\n"
            if command[-1] == "machdep.cpu.brand_string"
            else "Mac16,5\n"
        )
        return SimpleNamespace(returncode=0, stdout=stdout)

    monkeypatch.setattr(native_mtp_capability, "_CACHED_HARDWARE_PROFILE", None)
    monkeypatch.setattr(native_mtp_capability.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(native_mtp_capability.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(native_mtp_capability.subprocess, "run", fake_run)

    first = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    second = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert first.hardware_gate == "admitted"
    assert first.hardware_policy_reason == "supported_apple_silicon"
    assert second.hardware_gate == "admitted"
    assert calls == ["machdep.cpu.brand_string", "hw.model"]


def test_registry_detects_non_darwin_hardware_once_and_caches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-linux"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )
    calls = 0

    def fake_run(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(native_mtp_capability, "_CACHED_HARDWARE_PROFILE", None)
    monkeypatch.setattr(native_mtp_capability.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native_mtp_capability.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(native_mtp_capability.subprocess, "run", fake_run)

    first = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    second = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert first.hardware_gate == "admitted"
    assert first.hardware_policy_reason == "unclassified_device"
    assert second.hardware_gate == "admitted"
    assert calls == 0


def test_registry_fails_closed_when_darwin_arm64_hardware_probe_times_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "qwen-native-head-timeout"
    _write_model(
        model_dir,
        config={"model_type": "qwen3_5_text", "mtp_num_hidden_layers": 1},
        weight_map={"mtp.fc.weight": "mtp.safetensors"},
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(native_mtp_capability, "_CACHED_HARDWARE_PROFILE", None)
    monkeypatch.setattr(native_mtp_capability.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(native_mtp_capability.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(native_mtp_capability.subprocess, "run", fake_run)

    decision = resolve_native_mtp_capability(
        model_dir,
        metadata={"melix.native_mtp.enabled": "true"},
    )
    metadata = decision.to_metadata(patch_applied=False, active=False)
    receipt = _native_mtp_receipt(metadata)

    assert decision.refusal_reason == "device_policy_disabled"
    assert metadata["melix.native_mtp.hardware_gate"] == "disabled"
    assert metadata["melix.native_mtp.reason"] == "device_policy_disabled"
    assert receipt["hardware_policy_reason"] == "unclassified_apple_silicon"
    assert receipt["hardware_policy_source"] == "auto"


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
        hardware_profile=SimpleNamespace(),
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
    fallback_metadata = decision.to_metadata(patch_applied=False, active=False)

    assert metadata["melix.native_mtp.reason"] == ""
    assert metadata["melix.native_mtp.resolution"] == "fallback"
    assert metadata["melix.native_mtp.receipt.status"] == "fallback"
    assert metadata["melix.native_mtp.receipt.request_gate"] == "not_admitted"
    assert fallback_metadata["melix.native_mtp.reason"] == ""
    assert fallback_metadata["melix.native_mtp.receipt.status"] == "fallback"


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
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.device_policy": "force_on",
        },
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


def test_text_preload_refuses_deepseek_nextn_without_runtime_patch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "text-deepseek-nextn"
    _write_model(
        model_dir,
        config={"model_type": "deepseek_v3", "num_nextn_predict_layers": 2},
        weight_map={
            "model.layers.0.shared_head.head.weight": "nextn.safetensors",
            "model.layers.0.eh_proj.weight": "nextn.safetensors",
        },
    )
    calls: list[tuple[str, bool]] = []
    _install_fake_native_mtp(monkeypatch, calls)

    metadata = maybe_apply_native_mtp_text_preload_patches(
        str(model_dir),
        metadata={"melix.native_mtp.enabled": "true"},
    )

    assert metadata["melix.native_mtp.compatible"] == "true"
    assert metadata["melix.native_mtp.family"] == "deepseek_v3_nextn"
    assert metadata["melix.native_mtp.resolution"] == "refused"
    assert metadata["melix.native_mtp.reason"] == "patch_unsupported"
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
        metadata={
            "melix.native_mtp.enabled": "true",
            "melix.native_mtp.device_policy": "force_on",
        },
    )

    assert metadata["melix.native_mtp.active"] == "true"
    assert metadata["melix.native_mtp.family"] == "qwen3_5"
    assert metadata["melix.native_mtp.receipt.status"] == "admitted"
    assert metadata["melix.native_mtp.receipt.mode"] == "speculative_decode"
    assert ("patch", True) in calls
    assert calls[-1] == ("active", True)
