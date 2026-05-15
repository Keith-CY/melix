from __future__ import annotations

from dataclasses import dataclass, field


UNSUPPORTED_REASON_MISSING_ADAPTER_PROVIDER = "missing_adapter_provider"
UNSUPPORTED_REASON_UNSUPPORTED_BACKEND = "unsupported_backend"
UNSUPPORTED_REASON_UNSUPPORTED_QUANTIZED_BASE = "unsupported_quantized_base"
UNSUPPORTED_REASON_MISSING_QUANTIZATION_PROVIDER = "missing_quantization_provider"
UNSUPPORTED_REASON_NON_MERGEABLE_ADAPTER = "non_mergeable_adapter"


@dataclass(frozen=True)
class AdapterCapabilities:
    lora_like: bool
    mergeable: bool
    relora_compatible: bool
    quantized_base_supported: bool

    def as_manifest(self) -> dict[str, bool]:
        return {
            "lora_like": self.lora_like,
            "mergeable": self.mergeable,
            "relora_compatible": self.relora_compatible,
            "quantized_base_supported": self.quantized_base_supported,
        }


@dataclass(frozen=True)
class AdapterCapabilityRecord:
    adapter_family: str
    adapter_algorithm: str
    capabilities: AdapterCapabilities
    backend: str = "mlx_lm"
    backend_supported: bool = True
    unsupported_reason: str = ""
    loader_kwargs: dict[str, str] = field(default_factory=dict)

    def as_manifest(self) -> dict[str, object]:
        return {
            "adapter_family": self.adapter_family,
            "adapter_algorithm": self.adapter_algorithm,
            "adapter_capabilities": self.capabilities.as_manifest(),
            "backend": self.backend,
            "backend_supported": self.backend_supported,
            "unsupported_reason": self.unsupported_reason,
            "loader_kwargs": dict(self.loader_kwargs),
        }


class AdapterCapabilityRegistry:
    def __init__(self, records: list[AdapterCapabilityRecord] | None = None) -> None:
        self._records: dict[str, AdapterCapabilityRecord] = {}
        for record in records or []:
            self.register(record)

    def register(self, record: AdapterCapabilityRecord) -> None:
        adapter_family = normalize_adapter_family(record.adapter_family)
        if not adapter_family:
            raise ValueError("adapter_family must not be empty")
        if not record.adapter_algorithm.strip():
            raise ValueError("adapter_algorithm must not be empty")
        normalized_record = AdapterCapabilityRecord(
            adapter_family=adapter_family,
            adapter_algorithm=record.adapter_algorithm.strip().lower(),
            capabilities=record.capabilities,
            backend=record.backend.strip() or "mlx_lm",
            backend_supported=record.backend_supported,
            unsupported_reason=record.unsupported_reason.strip(),
            loader_kwargs=dict(record.loader_kwargs),
        )
        self._records[adapter_family] = normalized_record

    def resolve(self, adapter_family: str) -> AdapterCapabilityRecord | None:
        return self._records.get(normalize_adapter_family(adapter_family))

    def records(self) -> dict[str, AdapterCapabilityRecord]:
        return dict(self._records)


def normalize_adapter_family(value: str) -> str:
    return value.strip().lower()


DEFAULT_ADAPTER_CAPABILITY_REGISTRY = AdapterCapabilityRegistry(
    [
        AdapterCapabilityRecord(
            adapter_family="lora",
            adapter_algorithm="lora",
            capabilities=AdapterCapabilities(
                lora_like=True,
                mergeable=True,
                relora_compatible=True,
                quantized_base_supported=True,
            ),
        ),
        AdapterCapabilityRecord(
            adapter_family="qlora",
            adapter_algorithm="lora",
            capabilities=AdapterCapabilities(
                lora_like=True,
                mergeable=True,
                relora_compatible=True,
                quantized_base_supported=True,
            ),
        ),
        AdapterCapabilityRecord(
            adapter_family="dora",
            adapter_algorithm="dora",
            capabilities=AdapterCapabilities(
                lora_like=True,
                mergeable=True,
                relora_compatible=False,
                quantized_base_supported=True,
            ),
        ),
    ]
)
