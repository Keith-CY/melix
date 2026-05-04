from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_ops.quantization_pipeline import OQQuantizationPipeline
from worker.model_ops.quantization_profiles import (
    normalize_quantization_profile,
    protected_scope_for_request,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def build_service(tmp_path: Path) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")


def _write_dataset_package(
    root: Path,
    *,
    format: str,
    samples: list[dict[str, object]],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "melix-calibration-dev",
                "format": format,
                "sample_count": len(samples),
                "version": "1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with (root / "samples.jsonl").open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample) + "\n")
    return root


def test_quantize_job_writes_bundle_directory_and_versioned_manifest(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )

    progress_stages = [event.progress.stage for event in events if event.HasField("progress")]
    assert progress_stages == [
        "resolve_source",
        "normalize_profile",
        "quantize_weights",
        "write_bundle",
        "write_manifest",
    ]

    manifest_event = next(event.manifest for event in events if event.HasField("manifest"))
    manifest_payload = json.loads(manifest_event.manifest_json)
    completed_event = events[-1].completed

    bundle_path = Path(events[-1].completed.output_path)
    assert bundle_path.name == "quantize.artifact"
    assert bundle_path.is_dir() is True
    assert (bundle_path / "config.json").exists() is True
    assert (bundle_path / "tokenizer.json").exists() is True
    assert (bundle_path / "weights.safetensors").exists() is True

    manifest_path = bundle_path / "manifest.json"
    assert manifest_path.exists() is True
    assert json.loads(manifest_path.read_text()) == manifest_payload
    assert manifest_payload["schema_version"] == "melix.quantized_bundle.v1"
    assert manifest_payload["artifact_kind"] == "quantized_model_bundle"
    assert manifest_payload["quantization_mode"] == "ptq"
    assert manifest_payload["source_artifact_kind"] == "base_model"
    assert manifest_payload["source_artifact_path"]
    assert manifest_payload["calibration_dataset_uri"] == ""
    assert manifest_payload["quantized_artifact_bytes"] == manifest_payload["artifact_bytes"]
    assert manifest_payload["release_gate"] == {
        "quality_delta": 0.0,
        "latency_delta": 0.0,
        "local_inference_smoke_result": "not_requested",
    }
    assert manifest_payload["quant_profile"] == {
        "algorithm": "oq",
        "schema_version": "melix.quant_profile.v1",
        "quant_profile_id": "q4",
        "weight_quant": "q4",
        "kv_quant": "q8",
    }
    assert manifest_event.quant_profile.algorithm == "oq"
    assert manifest_event.quant_profile.schema_version == "melix.quant_profile.v1"
    assert manifest_event.quant_profile.quant_profile_id == "q4"
    assert manifest_event.quant_profile.weight_quant == "q4"
    assert manifest_event.quant_profile.kv_quant == "q8"
    assert manifest_event.artifact.schema_version == "melix.quantized_bundle.v1"
    assert manifest_event.artifact.artifact_kind == "quantized_model_bundle"
    assert manifest_event.artifact.manifest_path == str(manifest_path)
    assert manifest_event.artifact.bundle_path == str(bundle_path)
    assert completed_event.quant_profile.quant_profile_id == "q4"
    assert completed_event.artifact.bundle_path == str(bundle_path)
    assert completed_event.artifact.manifest_path == str(manifest_path)
    assert manifest_payload["compatibility"] == {
        "runtime": "mlx_text",
        "serving_compatible": True,
        "smoke_test_requested": False,
        "smoke_test_passed": False,
    }


def test_quantize_job_records_successful_smoke_validation(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                run_smoke_test=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )

    manifest_event = next(event.manifest for event in events if event.HasField("manifest"))
    manifest_payload = json.loads(manifest_event.manifest_json)
    completed_event = events[-1].completed

    assert manifest_payload["compatibility"]["smoke_test_requested"] is True
    assert manifest_payload["compatibility"]["smoke_test_passed"] is True
    assert manifest_payload["release_gate"]["local_inference_smoke_result"] == "passed"
    assert manifest_payload["artifact_bytes"] > 0
    assert manifest_payload["manifest_bytes"] > 0
    assert manifest_event.artifact.smoke_test_requested is True
    assert manifest_event.artifact.smoke_test_passed is True
    assert completed_event.artifact.smoke_test_requested is True
    assert completed_event.artifact.smoke_test_passed is True


def test_quantize_job_writes_manifest_once_after_in_memory_byte_convergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service(tmp_path)
    write_calls = 0
    encode_manifest_bytes: list[int] = []
    original_write_manifest = OQQuantizationPipeline._write_manifest
    original_encode_manifest = OQQuantizationPipeline._encode_manifest

    def counting_write_manifest(path: Path, payload: dict[str, object], encoded: bytes | None = None) -> int:
        nonlocal write_calls
        write_calls += 1
        return original_write_manifest(path, payload, encoded)

    def tracking_encode_manifest(payload: dict[str, object]) -> bytes:
        encode_manifest_bytes.append(int(payload["manifest_bytes"]))
        return original_encode_manifest(payload)

    monkeypatch.setattr(OQQuantizationPipeline, "_write_manifest", staticmethod(counting_write_manifest))
    monkeypatch.setattr(OQQuantizationPipeline, "_encode_manifest", staticmethod(tracking_encode_manifest))

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )

    manifest_event = next(event.manifest for event in events if event.HasField("manifest"))
    manifest_path = Path(events[-1].completed.output_path) / "manifest.json"
    manifest_payload = json.loads(manifest_event.manifest_json)
    final_manifest_bytes = manifest_payload["manifest_bytes"]

    assert write_calls == 1
    assert encode_manifest_bytes.count(final_manifest_bytes) == 1
    assert manifest_payload["manifest_bytes"] == manifest_path.stat().st_size
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest_payload

    rewrite_path = manifest_path.with_name("manifest.rewrite.json")
    assert original_write_manifest(rewrite_path, manifest_payload) == final_manifest_bytes
    assert rewrite_path.read_bytes() == manifest_path.read_bytes()


def test_quantize_pipeline_counts_artifact_bytes_without_rescanning_bundle_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service(tmp_path)
    original_scandir = os.scandir
    bundle_scandir_calls = 0

    def tracked_scandir(path: str | os.PathLike[str]) -> os.ScandirIterator[os.DirEntry[str]]:
        nonlocal bundle_scandir_calls
        if Path(path).name == "quantize.artifact":
            bundle_scandir_calls += 1
            raise AssertionError("quantize pipeline should not rescan the bundle directory for artifact_bytes")
        return original_scandir(path)

    with pytest.raises(AssertionError, match="should not rescan"):
        tracked_scandir(bundle_path := tmp_path / "quantize.artifact")
    assert bundle_scandir_calls == 1
    bundle_scandir_calls = 0

    monkeypatch.setattr(os, "scandir", tracked_scandir)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )

    bundle_path = Path(events[-1].completed.output_path)
    manifest_payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    expected_artifact_bytes = sum(
        (bundle_path / file_name).stat().st_size
        for file_name in ("config.json", "tokenizer.json", "weights.safetensors")
    )

    assert bundle_scandir_calls == 0
    assert manifest_payload["artifact_bytes"] == expected_artifact_bytes


def test_quantize_job_uses_typed_quant_profile_when_provided(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        output_dir=str(tmp_path / "quantize"),
        generate_manifest=True,
        ext={"operation": "quantize"},
    )
    request.quant_profile.algorithm = "oq"
    request.quant_profile.schema_version = "melix.quant_profile.v1"
    request.quant_profile.quant_profile_id = "q6"
    request.quant_profile.weight_quant = "q6"
    request.quant_profile.kv_quant = "q4"
    request.quant_profile.ext["quant_group_size"] = "128"

    events = list(service.ConvertModel(request, context=None))
    manifest_event = next(event.manifest for event in events if event.HasField("manifest"))
    manifest_payload = json.loads(manifest_event.manifest_json)

    assert manifest_event.quant_profile.quant_profile_id == "q6"
    assert manifest_event.quant_profile.weight_quant == "q6"
    assert manifest_event.quant_profile.kv_quant == "q4"
    assert manifest_event.quant_profile.ext["quant_group_size"] == "128"
    assert manifest_payload["quant_profile"]["quant_profile_id"] == "q6"
    assert manifest_payload["quant_profile"]["ext"] == {"quant_group_size": "128"}


def test_quantize_job_records_qat_mode_source_kind_and_release_gate_evidence(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    source_artifact_path = tmp_path / "merged-adapter"
    source_artifact_path.mkdir()

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                run_smoke_test=True,
                ext={
                    "operation": "quantize",
                    "quantization_mode": "qat",
                    "source_artifact_kind": "merged_adapter",
                    "source_artifact_path": str(source_artifact_path),
                    "quality_delta": "-0.0125",
                    "latency_delta": "-0.2",
                    "qat_fake_quant": "enabled",
                },
            ),
            context=None,
        )
    )

    manifest_payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert manifest_payload["quantization_mode"] == "qat"
    assert manifest_payload["source_artifact_kind"] == "merged_adapter"
    assert manifest_payload["source_artifact_path"] == str(source_artifact_path)
    assert manifest_payload["release_gate"] == {
        "quality_delta": -0.0125,
        "latency_delta": -0.2,
        "local_inference_smoke_result": "passed",
    }
    assert manifest_payload["qat"] == {"fake_quant": "enabled"}


def test_quantize_job_rejects_qat_for_base_model_sources(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "quantization_mode": "qat",
                    "source_artifact_kind": "base_model",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_quantization_mode"
    assert events[-1].failed.error.details["quantization_mode"] == "qat"
    assert events[-1].failed.error.details["source_artifact_kind"] == "base_model"


def test_quantize_job_rejects_unknown_quantization_mode(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "quantization_mode": "mystery",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_quantization_mode"
    assert events[-1].failed.error.details["quantization_mode"] == "mystery"


def test_quantize_job_rejects_unknown_source_artifact_kind(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "source_artifact_kind": "checkpoint",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_source_artifact_kind"
    assert events[-1].failed.error.details["source_artifact_kind"] == "checkpoint"


def test_quantize_job_rejects_adapter_artifact_source_without_path(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "source_artifact_kind": "adapter_export",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "missing_source_artifact_path"
    assert events[-1].failed.error.details["source_artifact_kind"] == "adapter_export"


def test_quantize_job_rejects_non_numeric_release_gate_values(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "quality_delta": "bad",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_quantization_release_gate"
    assert events[-1].failed.error.details["field"] == "quality_delta"
    assert events[-1].failed.error.details["value"] == "bad"


def test_quantize_job_records_calibration_dataset_lineage(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    calibration_dataset = _write_dataset_package(
        tmp_path / "calibration-dataset",
        format="calibration",
        samples=[{"text": "calibration prompt one"}, {"text": "calibration prompt two"}],
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "calibration_dataset_uri": str(calibration_dataset),
                },
            ),
            context=None,
        )
    )

    manifest_payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert manifest_payload["calibration_dataset_uri"] == str(calibration_dataset)
    assert manifest_payload["calibration_dataset"] == {
        "dataset_uri": str(calibration_dataset),
        "dataset_id": "melix-calibration-dev",
        "dataset_version": "1",
        "dataset_format": "calibration",
        "sample_count": 2,
        "manifest_path": str(calibration_dataset / "manifest.json"),
        "package_path": str(calibration_dataset),
    }


def test_quantize_job_rejects_non_calibration_dataset_lineage(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    sft_dataset = _write_dataset_package(
        tmp_path / "sft-dataset",
        format="prompt_completion",
        samples=[{"prompt": "hello", "completion": "world"}],
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "quantize"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "calibration_dataset_uri": str(sft_dataset),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_calibration_dataset"
    assert events[-1].failed.error.details["required_format"] == "calibration"
    assert events[-1].failed.error.details["actual_format"] == "prompt_completion"


def test_quantize_job_supports_oq2_to_oq8_profiles_with_calibration_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    expected_samples = {
        "q2": 96,
        "q3": 80,
        "q4": 64,
        "q5": 48,
        "q6": 32,
        "q7": 24,
        "q8": 16,
    }

    for profile_id, sample_count in expected_samples.items():
        events = list(
            service.ConvertModel(
                maintenance_pb2.ConvertModelRequest(
                    source_model="melix-dev-text",
                    output_dir=str(tmp_path / profile_id),
                    weight_quant=profile_id,
                    kv_quant="q8",
                    generate_manifest=True,
                    run_smoke_test=True,
                    ext={"operation": "quantize", "quant_profile_id": profile_id},
                ),
                context=None,
            )
        )

        manifest_event = next(event.manifest for event in events if event.HasField("manifest"))
        manifest_payload = json.loads(manifest_event.manifest_json)

        assert manifest_event.quant_profile.quant_profile_id == profile_id
        assert manifest_payload["quant_profile"]["quant_profile_id"] == profile_id
        assert manifest_payload["calibration"]["method"] == "deterministic_mixed_precision_scan"
        assert manifest_payload["calibration"]["sample_count"] == sample_count
        assert manifest_payload["calibration"]["dataset_digest"].startswith("melix-dev-text:")
        assert manifest_payload["calibration"]["mixed_precision"] is True
        allocations = manifest_payload["calibration"]["bit_allocation"]
        assert [entry["group"] for entry in allocations] == ["attention", "mlp", "output"]
        assert sum(entry["layer_count"] for entry in allocations) == 24
        assert allocations[-1]["bit_width"] == "q8"


def test_quantize_job_supports_oq35_vlm_fp8_and_hybrid_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-vlm",
                output_dir=str(tmp_path / "q35"),
                weight_quant="q3",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "quant_profile_id": "q3.5",
                    "source_precision": "fp8",
                    "hybrid_mode": "vlm-hybrid",
                    "retain_visual_precision": "q8",
                },
            ),
            context=None,
        )
    )

    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert payload["quant_profile"]["quant_profile_id"] == "q3.5"
    assert payload["source_format"]["precision"] == "fp8"
    assert payload["source_format"]["model_kind"] == "vlm"
    assert payload["hybrid_layout"]["mode"] == "vlm-hybrid"
    assert payload["hybrid_layout"]["retain_visual_precision"] == "q8"
    assert payload["strategy"]["family"] == "dense"


def test_quantize_job_records_awq_sensitivity_and_compensation_metadata(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "enhanced"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "awq_equalization": "enabled",
                    "sensitivity_planning": "enabled",
                    "compensation_mode": "gptq_hessian",
                    "quant_algorithm": "oqe",
                },
            ),
            context=None,
        )
    )

    manifest = next(event.manifest for event in events if event.HasField("manifest"))
    payload = json.loads(manifest.manifest_json)

    assert payload["planning"]["equalization"]["mode"] == "awq"
    assert payload["planning"]["sensitivity"]["enabled"] is True
    assert payload["planning"]["sensitivity"]["planner"] == "deterministic_hessian_budget"
    assert payload["compensation"]["mode"] == "gptq_hessian"
    assert payload["compensation"]["quant_algorithm"] == "oqe"
    assert payload["compensation"]["hessian_aware"] is True


def test_quantize_job_selects_moe_or_dense_strategy(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    dense_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "dense"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={"operation": "quantize"},
            ),
            context=None,
        )
    )
    moe_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="models/melix-dev-moe-8x7b",
                output_dir=str(tmp_path / "moe"),
                weight_quant="q4",
                kv_quant="q8",
                generate_manifest=True,
                ext={
                    "operation": "quantize",
                    "architecture_class": "moe",
                },
            ),
            context=None,
        )
    )

    dense_payload = json.loads(next(event.manifest for event in dense_events if event.HasField("manifest")).manifest_json)
    moe_payload = json.loads(next(event.manifest for event in moe_events if event.HasField("manifest")).manifest_json)

    assert dense_payload["strategy"]["family"] == "dense"
    assert dense_payload["strategy"]["planner"] == "dense-layerwise"
    assert moe_payload["strategy"]["family"] == "moe"
    assert moe_payload["strategy"]["planner"] == "expert-aware"


def test_protected_scope_prefers_explicit_scope_and_can_be_empty() -> None:
    explicit_request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        ext={"protected_scope": "model-family:custom-explicit"},
    )
    assert protected_scope_for_request(explicit_request) == "model-family:custom-explicit"

    empty_request = maintenance_pb2.ConvertModelRequest()
    assert protected_scope_for_request(empty_request) == ""


def test_normalize_profile_falls_back_to_weight_quant_when_ext_profile_id_is_unsupported() -> None:
    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        weight_quant="q6",
        kv_quant="q8",
        ext={"quant_profile_id": "q-bogus"},
    )
    profile = normalize_quantization_profile(request)
    # q-bogus is not in _SUPPORTED_OQ_PROFILE_IDS, so it falls back to weight_quant "q6"
    assert profile.quant_profile_id == "q6"
    assert profile.weight_quant == "q6"


def test_normalize_profile_falls_back_to_q4_when_both_ext_and_weight_quant_are_unsupported() -> None:
    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        weight_quant="q-invalid",
        ext={"quant_profile_id": "q-also-invalid"},
    )
    profile = normalize_quantization_profile(request)
    # both unsupported: double-fallback ends at q4
    assert profile.quant_profile_id == "q4"
    assert profile.weight_quant == "q-invalid"  # weight_quant field is not normalized, only profile_id


def test_normalize_profile_strips_non_quant_ext_keys() -> None:
    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        weight_quant="q4",
        ext={
            "operation": "quantize",
            "quant_group_size": "128",
            "quant_algorithm": "oqe",
        },
    )
    profile = normalize_quantization_profile(request)
    # only keys starting with "quant_" are kept in ext
    assert "operation" not in profile.ext
    assert profile.ext.get("quant_group_size") == "128"
    assert profile.ext.get("quant_algorithm") == "oqe"


def test_protected_scope_uses_source_model_spec_ext_over_request_source_model() -> None:
    spec = common_pb2.ModelSpec(model_id="llama-family-3-8b")
    spec.ext["embedding_family_id"] = "llama-embed"

    request = maintenance_pb2.ConvertModelRequest(source_model="melix-dev-text")
    # spec ext fields come before request.source_model in candidate priority
    assert protected_scope_for_request(request, source_model_spec=spec) == "model-family:llama-embed"


def test_protected_scope_falls_back_to_source_model_spec_model_id() -> None:
    spec = common_pb2.ModelSpec(model_id="gemma-2b")
    request = maintenance_pb2.ConvertModelRequest(source_model="melix-dev-text")
    # spec has no ext families, so model_id is the first non-empty candidate
    result = protected_scope_for_request(request, source_model_spec=spec)
    assert result == "model-family:gemma-2b"


def test_protected_scope_falls_back_to_request_source_model_when_spec_absent() -> None:
    request = maintenance_pb2.ConvertModelRequest(source_model="melix-fallback-model")
    assert protected_scope_for_request(request) == "model-family:melix-fallback-model"
