from __future__ import annotations

import json
from pathlib import Path

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def build_service(tmp_path: Path) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    return WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")


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
    assert manifest_payload["artifact_bytes"] > 0
    assert manifest_payload["manifest_bytes"] > 0
    assert manifest_event.artifact.smoke_test_requested is True
    assert manifest_event.artifact.smoke_test_passed is True
    assert completed_event.artifact.smoke_test_requested is True
    assert completed_event.artifact.smoke_test_passed is True


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
