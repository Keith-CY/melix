from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

from packages.protocol.python.worker.v1 import common_pb2, maintenance_pb2

_SUPPORTED_OQ_PROFILE_IDS = ("q2", "q3", "q3.5", "q4", "q5", "q6", "q7", "q8")
_CALIBRATION_SAMPLE_COUNTS = {
    "q2": 96,
    "q3": 80,
    "q3.5": 72,
    "q4": 64,
    "q5": 48,
    "q6": 32,
    "q7": 24,
    "q8": 16,
}
_BIT_ALLOCATIONS = {
    "q2": [("attention", "q2", 8), ("mlp", "q3", 12), ("output", "q8", 4)],
    "q3": [("attention", "q3", 8), ("mlp", "q4", 12), ("output", "q8", 4)],
    "q3.5": [("attention", "q3", 8), ("mlp", "q4", 12), ("output", "q8", 4)],
    "q4": [("attention", "q4", 8), ("mlp", "q5", 12), ("output", "q8", 4)],
    "q5": [("attention", "q5", 8), ("mlp", "q6", 12), ("output", "q8", 4)],
    "q6": [("attention", "q6", 8), ("mlp", "q7", 12), ("output", "q8", 4)],
    "q7": [("attention", "q7", 8), ("mlp", "q8", 12), ("output", "q8", 4)],
    "q8": [("attention", "q8", 8), ("mlp", "q8", 12), ("output", "q8", 4)],
}


@dataclass(frozen=True)
class QuantizationProfile:
    algorithm: str
    schema_version: str
    quant_profile_id: str
    weight_quant: str
    kv_quant: str
    ext: dict[str, str] = field(default_factory=dict)

    def to_manifest_dict(self) -> dict[str, str]:
        payload = {
            "algorithm": self.algorithm,
            "schema_version": self.schema_version,
            "quant_profile_id": self.quant_profile_id,
            "weight_quant": self.weight_quant,
            "kv_quant": self.kv_quant,
        }
        if self.ext:
            payload["ext"] = dict(self.ext)
        return payload

    @property
    def source_precision(self) -> str:
        return self.ext.get("source_precision", "fp16")


@dataclass(frozen=True)
class CalibrationAllocation:
    group: str
    bit_width: str
    layer_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "group": self.group,
            "bit_width": self.bit_width,
            "layer_count": self.layer_count,
        }


@dataclass(frozen=True)
class CalibrationPlan:
    method: str
    sample_count: int
    dataset_digest: str
    mixed_precision: bool
    bit_allocation: tuple[CalibrationAllocation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "sample_count": self.sample_count,
            "dataset_digest": self.dataset_digest,
            "mixed_precision": self.mixed_precision,
            "bit_allocation": [entry.to_dict() for entry in self.bit_allocation],
        }


def normalize_quantization_profile(
    request: maintenance_pb2.ConvertModelRequest,
) -> QuantizationProfile:
    if request.HasField("quant_profile"):
        profile = request.quant_profile
        return QuantizationProfile(
            algorithm=profile.algorithm or "oq",
            schema_version=profile.schema_version or "melix.quant_profile.v1",
            quant_profile_id=profile.quant_profile_id or profile.weight_quant or request.weight_quant or "q4",
            weight_quant=profile.weight_quant or request.weight_quant or profile.quant_profile_id or "q4",
            kv_quant=profile.kv_quant or request.kv_quant,
            ext=dict(profile.ext),
        )

    ext = dict(request.ext)
    algorithm = ext.get("quant_algorithm", "oq") or "oq"
    quant_profile_id = ext.get("quant_profile_id", request.weight_quant or "q4") or "q4"
    if quant_profile_id not in _SUPPORTED_OQ_PROFILE_IDS:
        quant_profile_id = request.weight_quant or "q4"
    if quant_profile_id not in _SUPPORTED_OQ_PROFILE_IDS:
        quant_profile_id = "q4"
    kv_quant = request.kv_quant or ext.get("kv_quant", "")
    return QuantizationProfile(
        algorithm=algorithm,
        schema_version="melix.quant_profile.v1",
        quant_profile_id=quant_profile_id,
        weight_quant=request.weight_quant or quant_profile_id,
        kv_quant=kv_quant,
        ext={
            key: value
            for key, value in ext.items()
            if key.startswith("quant_")
        },
    )


def calibration_plan_for_profile(
    profile: QuantizationProfile,
    *,
    source_model: str,
) -> CalibrationPlan:
    allocations = tuple(
        CalibrationAllocation(group=group, bit_width=bit_width, layer_count=layer_count)
        for group, bit_width, layer_count in _BIT_ALLOCATIONS[profile.quant_profile_id]
    )
    digest = sha256(f"{source_model}:{profile.quant_profile_id}".encode("utf-8")).hexdigest()[:12]
    return CalibrationPlan(
        method="deterministic_mixed_precision_scan",
        sample_count=_CALIBRATION_SAMPLE_COUNTS[profile.quant_profile_id],
        dataset_digest=f"{source_model}:{digest}",
        mixed_precision=True,
        bit_allocation=allocations,
    )


def strategy_metadata_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    *,
    source_model: str,
) -> dict[str, str]:
    ext = dict(request.ext)
    architecture_class = ext.get("architecture_class", "").lower()
    lowered_source = source_model.lower()
    family = architecture_class or ("moe" if "moe" in lowered_source else "dense")
    return {
        "family": family,
        "planner": "expert-aware" if family == "moe" else "dense-layerwise",
    }


def source_format_metadata_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    *,
    model_kind: str,
) -> dict[str, str]:
    ext = dict(request.ext)
    return {
        "precision": ext.get("source_precision", "fp16"),
        "model_kind": model_kind,
    }


def hybrid_layout_metadata_for_request(
    request: maintenance_pb2.ConvertModelRequest,
) -> dict[str, str] | None:
    ext = dict(request.ext)
    hybrid_mode = ext.get("hybrid_mode", "")
    if not hybrid_mode:
        return None
    return {
        "mode": hybrid_mode,
        "retain_visual_precision": ext.get("retain_visual_precision", ""),
    }


def planning_metadata_for_request(
    request: maintenance_pb2.ConvertModelRequest,
) -> dict[str, object] | None:
    ext = dict(request.ext)
    if ext.get("awq_equalization") != "enabled" and ext.get("sensitivity_planning") != "enabled":
        return None
    return {
        "equalization": {
            "mode": "awq" if ext.get("awq_equalization") == "enabled" else "disabled",
        },
        "sensitivity": {
            "enabled": ext.get("sensitivity_planning") == "enabled",
            "planner": "deterministic_hessian_budget",
        },
    }


def compensation_metadata_for_request(
    request: maintenance_pb2.ConvertModelRequest,
) -> dict[str, object] | None:
    ext = dict(request.ext)
    mode = ext.get("compensation_mode", "")
    if not mode and ext.get("quant_algorithm") != "oqe":
        return None
    return {
        "mode": mode or "none",
        "quant_algorithm": ext.get("quant_algorithm", "oq"),
        "hessian_aware": "hessian" in mode,
    }


def protected_scope_for_request(
    request: maintenance_pb2.ConvertModelRequest,
    *,
    source_model_spec: common_pb2.ModelSpec | None = None,
) -> str:
    ext = dict(request.ext)
    explicit_scope = ext.get("protected_scope", "").strip()
    if explicit_scope:
        return explicit_scope

    candidate_values: list[str] = []
    if source_model_spec is not None:
        spec_ext = dict(source_model_spec.ext)
        candidate_values.extend(
            [
                spec_ext.get("embedding_family_id", ""),
                spec_ext.get("rerank_family_id", ""),
                spec_ext.get("vision_family_id", ""),
                spec_ext.get("detected_family_id", ""),
                spec_ext.get("model_architecture", ""),
                source_model_spec.model_id,
            ]
        )

    candidate_values.extend(
        [
            ext.get("family_id", ""),
            ext.get("embedding_family_id", ""),
            ext.get("rerank_family_id", ""),
            ext.get("vision_family_id", ""),
            ext.get("detected_family_id", ""),
            ext.get("model_architecture", ""),
            ext.get("architecture_class", ""),
            request.source_model,
        ]
    )

    for value in candidate_values:
        normalized = (value or "").strip()
        if normalized:
            return f"model-family:{normalized}"
    return ""
