from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys
import types
from urllib.error import HTTPError, URLError

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.grpc_server import WorkerMaintenanceService
from worker.engine.maintenance_core import MaintenanceCore
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline
from worker.model_ops.mlx_lm_runner import (
    ActivationMetrics,
    ActivationRequest,
    ActivationResult,
    MLXLMRunner,
    NativeExecutionUnavailable,
    TrainingMetrics,
    TrainingRequest,
    TrainingResult,
)
from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.training_dataset import (
    HFDatasetReference,
    materialize_hf_training_dataset_package,
    resolve_training_dataset_package,
)
from worker.model_registry.catalog import WorkerModelCatalog
from worker.registry import WorkerRegistry


def _write_dataset_package(
    root: Path,
    *,
    dataset_id: str = "melix-dev-dataset",
    format: str = "chat_messages",
    samples: list[dict],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": dataset_id,
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


class SuccessfulRunner(MLXLMRunner):
    def __init__(self) -> None:
        super().__init__()
        self.native_train_calls = 0
        self.subprocess_train_calls = 0
        self.native_activation_calls = 0
        self.subprocess_activation_calls = 0
        self.last_train_request: TrainingRequest | None = None

    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        self.last_train_request = request
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-test-adapter")
        adapter_config_path.write_text(
            json.dumps(
                {
                    "fine_tune_type": "lora",
                    "num_layers": request.config.num_layers,
                    "lora_parameters": {
                        "rank": request.config.rank,
                        "dropout": request.config.dropout,
                        "scale": request.config.alpha,
                        "keys": request.config.expanded_target_modules,
                    },
                    "mask_prompt": request.config.mask_prompt,
                    "grad_checkpoint": request.config.gradient_checkpointing,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1234.0,
                tokens_seen=2048,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
            ),
            execution_backend="native",
        )

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        self.subprocess_train_calls += 1
        return self.train_native(request)

    def activate_native(self, request: ActivationRequest) -> ActivationResult:
        self.native_activation_calls += 1
        request.derived_model_dir.mkdir(parents=True, exist_ok=True)
        (request.derived_model_dir / "config.json").write_text(
            json.dumps({"model_type": "llama"}) + "\n",
            encoding="utf-8",
        )
        (request.derived_model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
        activation_manifest = request.derived_model_dir / "manifest.json"
        activation_manifest.write_text(
            json.dumps({"schema_version": "melix.derived_text_model.v1"}) + "\n",
            encoding="utf-8",
        )
        return ActivationResult(
            derived_model_dir=request.derived_model_dir,
            manifest_path=activation_manifest,
            metrics=ActivationMetrics(job_duration_ms=321.0),
            execution_backend="native",
        )

    def activate_subprocess(self, request: ActivationRequest, reason: Exception) -> ActivationResult:
        self.subprocess_activation_calls += 1
        return self.activate_native(request)


class NativeUnavailableRunner(SuccessfulRunner):
    def train_native(self, request: TrainingRequest) -> TrainingResult:
        self.native_train_calls += 1
        self.last_train_request = request
        raise NativeExecutionUnavailable("mlx native path unavailable")

    def train_subprocess(self, request: TrainingRequest, reason: Exception) -> TrainingResult:
        self.subprocess_train_calls += 1
        self.last_train_request = request
        request.adapter_output_dir.mkdir(parents=True, exist_ok=True)
        weights_path = request.adapter_output_dir / "adapters.safetensors"
        adapter_config_path = request.adapter_output_dir / "adapter_config.json"
        weights_path.write_bytes(b"melix-test-adapter")
        adapter_config_path.write_text(
            json.dumps(
                {
                    "fine_tune_type": "lora",
                    "num_layers": request.config.num_layers,
                    "lora_parameters": {
                        "rank": request.config.rank,
                        "dropout": request.config.dropout,
                        "scale": request.config.alpha,
                        "keys": request.config.expanded_target_modules,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return TrainingResult(
            weights_path=weights_path,
            adapter_config_path=adapter_config_path,
            metrics=TrainingMetrics(
                job_duration_ms=1234.0,
                tokens_seen=2048,
                examples_seen=2,
                loss_final=0.42,
                loss_best=0.33,
                learning_rate_final=1e-4,
            ),
            execution_backend="subprocess",
        )


def _build_service(tmp_path: Path, runner: MLXLMRunner) -> WorkerMaintenanceService:
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(runner=runner),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )
    return service


class FakeHFDatasetFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((endpoint, dict(params)))
        if endpoint == "splits":
            return {
                "splits": [
                    {
                        "dataset": "melix/demo-hf",
                        "config": "default",
                        "split": "train",
                    },
                    {
                        "dataset": "melix/demo-hf",
                        "config": "default",
                        "split": "validation",
                    }
                ]
            }
        if endpoint == "rows":
            if params.get("split") == "validation":
                return {
                    "rows": [
                        {"row": {"text": "validation sample"}},
                    ]
                }
            return {
                "rows": [
                    {"row": {"text": "hello from hf"}},
                    {"row": {"text": "goodbye from hf"}},
                ]
            }
        raise AssertionError(f"Unexpected endpoint: {endpoint}")


def test_train_lora_produces_adapter_package_and_expanded_modules(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            },
            {
                "messages": [
                    {"role": "user", "content": "Say bye."},
                    {"role": "assistant", "content": "Bye."},
                ]
            },
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "q_proj,gate_proj",
                    "num_layers": "2",
                    "rank": "16",
                    "alpha": "32",
                    "dropout": "0.1",
                    "response_only": "true",
                    "gradient_checkpointing": "true",
                    "target_repo": "melix/adapters/melix-dev-adapter",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    stages = [event.progress.stage for event in events if event.HasField("progress")]

    assert stages == [
        "resolve_source",
        "validate_dataset",
        "normalize_config",
        "prepare_training_data",
        "apply_lora",
        "train",
        "write_adapter",
        "write_manifest",
    ]
    assert payload["schema_version"] == "melix.lora_adapter_package.v1"
    assert payload["training_mode"] == "lora"
    assert payload["adapter_name"] == "melix-dev-adapter"
    assert payload["source_model"] == "melix-dev-text"
    assert payload["dataset_uri"] == str(dataset_dir)
    assert payload["response_only"] is True
    assert payload["gradient_checkpointing"] is True
    assert payload["training_duration_ms"] == 1234.0
    assert payload["loss_final"] == 0.42
    assert payload["adapter_artifact_bytes"] > 0
    assert payload["adapter_set_hash"]
    assert payload["weights_path"].endswith("adapters.safetensors")
    assert payload["adapter_config_path"].endswith("adapter_config.json")
    assert payload["normalized_dataset_manifest_path"].endswith("normalized_dataset/manifest.json")
    assert Path(payload["weights_path"]).is_file()
    assert Path(payload["adapter_config_path"]).is_file()
    assert Path(payload["normalized_dataset_manifest_path"]).is_file()
    assert payload["target_modules"] == [
        "model.layers.0.self_attn.q_proj",
        "model.layers.1.self_attn.q_proj",
        "model.layers.0.mlp.gate_proj",
        "model.layers.1.mlp.gate_proj",
    ]


def test_resolve_training_dataset_rejects_invalid_source_kind_and_missing_hf_path(tmp_path: Path) -> None:
    with pytest.raises(Exception) as invalid_source:
        resolve_training_dataset_package(
            {"dataset_source_kind": "remote_zip"},
            jobs_root=tmp_path / "jobs",
        )
    assert invalid_source.value.code == "invalid_dataset_source"

    with pytest.raises(Exception) as missing_path:
        resolve_training_dataset_package(
            {"dataset_source_kind": "hf_dataset"},
            jobs_root=tmp_path / "jobs",
        )
    assert missing_path.value.code == "invalid_dataset_source"


def test_train_lora_materializes_hf_dataset_and_reuses_cached_package(tmp_path: Path) -> None:
    fetcher = FakeHFDatasetFetcher()
    registry = WorkerRegistry(model_catalog=WorkerModelCatalog())
    service = WorkerMaintenanceService(registry, jobs_root=tmp_path / "model-ops")
    service._core = MaintenanceCore(
        registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(
            runner=SuccessfulRunner(),
            hf_dataset_fetcher=fetcher,
        ),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=SuccessfulRunner()),
    )

    request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        output_dir=str(tmp_path / "ignored-train-output"),
        generate_manifest=True,
        ext={
            "operation": "train_lora",
            "adapter_name": "melix-hf-adapter",
            "dataset_source_kind": "hf_dataset",
            "hf_dataset_path": "melix/demo-hf",
            "hf_train_split": "train",
            "text_feature": "text",
        },
    )

    first_events = list(service.ConvertModel(request, context=None))
    second_events = list(service.ConvertModel(request, context=None))

    first_payload = json.loads(
        next(event.manifest for event in first_events if event.HasField("manifest")).manifest_json
    )
    second_payload = json.loads(
        next(event.manifest for event in second_events if event.HasField("manifest")).manifest_json
    )

    assert first_payload["dataset_source_kind"] == "hf_dataset"
    assert first_payload["hf_dataset_path"] == "melix/demo-hf"
    assert first_payload["hf_dataset_name"] == "default"
    assert first_payload["hf_train_split"] == "train"
    assert first_payload["dataset_uri"] == "hf://melix/demo-hf?config=default&split=train&revision=main"
    assert first_payload["dataset_cache_hit"] is False
    assert first_payload["dataset_materialized_package_path"].startswith(str(tmp_path / "model-ops" / "datasets"))
    assert Path(first_payload["dataset_materialized_package_path"]).is_dir()
    assert second_payload["dataset_cache_hit"] is True
    assert [endpoint for endpoint, _ in fetcher.calls] == ["splits", "rows"]


def test_train_lora_supports_qlora_with_hf_valid_split_and_persists_desired_alias(
    tmp_path: Path,
) -> None:
    fetcher = FakeHFDatasetFetcher()
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.model_path = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    source_model.quant_profile_id = "q4"

    service._core = MaintenanceCore(
        service._core._registry,
        jobs_root=tmp_path / "model-ops",
        lora_training_pipeline=LoRATrainingPipeline(
            runner=runner,
            hf_dataset_fetcher=fetcher,
        ),
        adapter_activation_pipeline=AdapterActivationPipeline(runner=runner),
    )

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "ignored-train-output"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-qwen35-acceptance-adapter",
                    "dataset_source_kind": "hf_dataset",
                    "hf_dataset_path": "melix/demo-hf",
                    "hf_train_split": "train",
                    "hf_valid_split": "validation",
                    "text_feature": "text",
                    "derived_model_alias": "melix-qwen35-acceptance",
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)
    normalized_dataset_path = Path(payload["normalized_dataset_manifest_path"])
    normalized_dataset_payload = json.loads(normalized_dataset_path.read_text(encoding="utf-8"))

    assert payload["training_mode"] == "qlora"
    assert payload["quantization_mode"] == "quantized_base"
    assert payload["hf_valid_split"] == "validation"
    assert payload["validation_strategy"] == "hf_split"
    assert payload["validation_sample_count"] == 1
    assert payload["desired_derived_model_alias"] == "melix-qwen35-acceptance"
    assert normalized_dataset_payload["validation_sample_count"] == 1
    assert normalized_dataset_payload["validation_strategy"] == "hf_split"
    assert normalized_dataset_payload["hf_valid_split"] == "validation"
    assert runner.last_train_request is not None
    assert runner.last_train_request.config.training_mode == "qlora"
    assert runner.last_train_request.config.validation_strategy == "hf_split"
    assert runner.last_train_request.config.validation_sample_count == 1
    assert (normalized_dataset_path.parent / "valid.jsonl").is_file()
    assert [params["split"] for endpoint, params in fetcher.calls if endpoint == "rows"] == [
        "train",
        "validation",
    ]


def test_train_lora_rejects_qlora_for_non_quantized_base_model(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())
    source_model = service._core._registry.model_catalog.get("melix-dev-text")
    assert source_model is not None
    source_model.model_path = "models/plain-llama"
    source_model.quant_profile_id = ""

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "training_mode": "qlora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_training_mode"


def test_resolve_training_dataset_rejects_hf_valid_split_for_local_package(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "text": "hello",
            }
        ],
        format="text_completion",
    )

    with pytest.raises(Exception) as exc:
        resolve_training_dataset_package(
            {
                "dataset_source_kind": "local_package",
                "dataset_uri": str(dataset_dir),
                "hf_valid_split": "validation",
            },
            jobs_root=tmp_path / "jobs",
        )

    assert exc.value.code == "invalid_dataset_source"


def test_materialize_hf_training_dataset_rejects_empty_row_payload(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )

    def empty_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint == "rows":
            return {"rows": []}
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    with pytest.raises(Exception) as exc:
        materialize_hf_training_dataset_package(
            reference,
            cache_root=tmp_path / "datasets",
            fetch_json=empty_fetcher,
        )
    assert exc.value.code == "hf_dataset_fetch_failed"


def test_hf_dataset_fetcher_reports_http_url_json_and_shape_errors(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return self._payload

    def raise_http(request, timeout: int):
        raise HTTPError(request.full_url, 429, "rate limited", hdrs=None, fp=None)

    monkeypatch.setattr(training_dataset_module, "urlopen", raise_http)
    with pytest.raises(Exception) as http_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert http_exc.value.code == "hf_dataset_fetch_failed"

    def raise_url(request, timeout: int):
        raise URLError("offline")

    monkeypatch.setattr(training_dataset_module, "urlopen", raise_url)
    with pytest.raises(Exception) as url_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert url_exc.value.code == "hf_dataset_fetch_failed"

    monkeypatch.setattr(
        training_dataset_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"{not-json"),
    )
    with pytest.raises(Exception) as json_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert json_exc.value.code == "hf_dataset_fetch_failed"

    monkeypatch.setattr(
        training_dataset_module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"[]"),
    )
    with pytest.raises(Exception) as shape_exc:
        training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"})
    assert shape_exc.value.code == "hf_dataset_fetch_failed"

    captured_headers: dict[str, str] = {}

    def success_urlopen(request, timeout: int):
        for key, value in request.header_items():
            captured_headers[key.lower()] = value
        return FakeResponse(b"{}")

    monkeypatch.setenv("HF_TOKEN", "secret-token")
    monkeypatch.setattr(training_dataset_module, "urlopen", success_urlopen)
    assert training_dataset_module._fetch_hf_dataset_server_json("rows", {"dataset": "melix/demo-hf"}) == {}
    assert captured_headers["authorization"] == "Bearer secret-token"


def test_reference_from_cached_manifest_handles_invalid_payloads(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )
    manifest_path = tmp_path / "manifest.json"

    manifest_path.write_text("{not-json", encoding="utf-8")
    assert training_dataset_module._reference_from_cached_manifest(reference, manifest_path) == reference

    manifest_path.write_text("[]", encoding="utf-8")
    assert training_dataset_module._reference_from_cached_manifest(reference, manifest_path) == reference


def test_hf_dataset_helper_resolution_and_mapping_paths() -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="",
        dataset_revision="main",
        train_split="train",
        valid_split="",
        chat_feature="messages",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )

    assert (
        training_dataset_module._resolve_hf_dataset_name(
            reference,
            lambda endpoint, params: {"splits": [{"split": "validation", "config": "fallback"}]},
        )
        == "fallback"
    )

    with pytest.raises(Exception) as missing_splits:
        training_dataset_module._resolve_hf_dataset_name(
            reference,
            lambda endpoint, params: {"splits": []},
        )
    assert missing_splits.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(Exception) as missing_config:
        training_dataset_module._resolve_hf_dataset_name(
            reference,
            lambda endpoint, params: {"splits": [{"split": "train"}]},
        )
    assert missing_config.value.code == "hf_dataset_fetch_failed"

    fetch_calls: list[tuple[str, dict[str, str]]] = []

    def paged_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        fetch_calls.append((endpoint, dict(params)))
        return {
            "rows": [
                {"row": {"text": "alpha"}},
                "skip-me",
                {"row": {"text": "beta"}},
            ]
        }

    rows = training_dataset_module._fetch_hf_dataset_rows(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
        paged_fetcher,
    )
    assert rows == [{"text": "alpha"}, {"text": "beta"}]
    assert fetch_calls[0][0] == "rows"

    with pytest.raises(Exception) as malformed_rows:
        training_dataset_module._fetch_hf_dataset_rows(
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="",
                completion_feature="",
                text_feature="text",
            ),
            lambda endpoint, params: {"rows": "bad"},
        )
    assert malformed_rows.value.code == "hf_dataset_fetch_failed"

    assert training_dataset_module._infer_hf_dataset_format(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="prompt",
            completion_feature="completion",
            text_feature="",
        ),
        [{"prompt": "p", "completion": "c"}],
    ) == "prompt_completion"
    assert training_dataset_module._infer_hf_dataset_format(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
        [{"text": "hello"}],
    ) == "text_completion"

    with pytest.raises(Exception) as format_error:
        training_dataset_module._infer_hf_dataset_format(
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="",
                completion_feature="",
                text_feature="",
            ),
            [{"unknown": "field"}],
        )
    assert format_error.value.code == "hf_dataset_fetch_failed"

    assert training_dataset_module._map_hf_row_to_training_sample(
        {"prompt": "p", "completion": "c"},
        "prompt_completion",
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="prompt",
            completion_feature="completion",
            text_feature="",
        ),
    ) == {"prompt": "p", "completion": "c"}
    assert training_dataset_module._map_hf_row_to_training_sample(
        {"text": "hello"},
        "text_completion",
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            valid_split="",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
    ) == {"text": "hello"}

    with pytest.raises(Exception) as chat_error:
        training_dataset_module._map_hf_row_to_training_sample(
            {"messages": "bad"},
            "chat_messages",
            reference,
        )
    assert chat_error.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(Exception) as prompt_error:
        training_dataset_module._map_hf_row_to_training_sample(
            {"prompt": "p"},
            "prompt_completion",
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="prompt",
                completion_feature="completion",
                text_feature="",
            ),
        )
    assert prompt_error.value.code == "hf_dataset_fetch_failed"

    with pytest.raises(Exception) as text_error:
        training_dataset_module._map_hf_row_to_training_sample(
            {"body": "p"},
            "text_completion",
            HFDatasetReference(
                dataset_path="melix/demo-hf",
                dataset_name="default",
                dataset_revision="main",
                train_split="train",
                valid_split="",
                chat_feature="",
                prompt_feature="",
                completion_feature="",
                text_feature="text",
            ),
        )
    assert text_error.value.code == "hf_dataset_fetch_failed"


def test_train_lora_invalid_dataset_package_fails_with_typed_error(tmp_path: Path) -> None:
    invalid_dataset_dir = tmp_path / "dataset-invalid"
    invalid_dataset_dir.mkdir(parents=True, exist_ok=True)
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(invalid_dataset_dir),
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "invalid_dataset_package"


def test_train_lora_rejects_unknown_target_module(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    service = _build_service(tmp_path, SuccessfulRunner())

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                    "target_modules": "q_proj,unknown_proj",
                },
            ),
            context=None,
        )
    )

    assert events[-1].failed.error.code == "unsupported_lora_target_module"


def test_train_lora_uses_fallback_runner_when_native_path_is_unavailable(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    runner = NativeUnavailableRunner()
    service = _build_service(tmp_path, runner)

    events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )

    payload = json.loads(next(event.manifest for event in events if event.HasField("manifest")).manifest_json)

    assert runner.native_train_calls == 1
    assert runner.subprocess_train_calls == 1
    assert payload["training_backend"] == "subprocess"


def test_activate_adapter_produces_derived_model_and_registry_activation_state(tmp_path: Path) -> None:
    dataset_dir = _write_dataset_package(
        tmp_path / "dataset",
        samples=[
            {
                "messages": [
                    {"role": "user", "content": "Say hi."},
                    {"role": "assistant", "content": "Hi there."},
                ]
            }
        ],
    )
    runner = SuccessfulRunner()
    service = _build_service(tmp_path, runner)

    train_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "train"),
                generate_manifest=True,
                ext={
                    "operation": "train_lora",
                    "adapter_name": "melix-dev-adapter",
                    "dataset_uri": str(dataset_dir),
                },
            ),
            context=None,
        )
    )
    adapter_manifest_path = train_events[-1].completed.output_path

    activate_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "activate"),
                generate_manifest=True,
                ext={
                    "operation": "activate_adapter",
                    "artifact_path": adapter_manifest_path,
                    "derived_model_alias": "Activated Alias",
                },
            ),
            context=None,
        )
    )
    activation_payload = json.loads(
        next(event.manifest for event in activate_events if event.HasField("manifest")).manifest_json
    )

    snapshot_events = list(
        service.ConvertModel(
            maintenance_pb2.ConvertModelRequest(
                source_model="melix-dev-text",
                output_dir=str(tmp_path / "snapshot"),
                generate_manifest=True,
                ext={"operation": "registry_snapshot"},
            ),
            context=None,
        )
    )
    snapshot_payload = json.loads(
        next(event.manifest for event in snapshot_events if event.HasField("manifest")).manifest_json
    )

    assert runner.native_activation_calls == 1
    assert activation_payload["schema_version"] == "melix.derived_text_model.v1"
    assert activation_payload["activation_mode"] == "fused_derived_model"
    assert activation_payload["derived_model_id"].startswith("melix-dev-text-lora-")
    assert activation_payload["derived_model_alias"] == "Activated Alias"
    assert activation_payload["source_adapter_job_id"] == "model-ops-0001"
    assert train_events[-1].completed.output_path == str(
        tmp_path / "model-ops" / "train_lora" / "model-ops-0001" / "train_lora.adapter.json"
    )
    assert activate_events[-1].completed.output_path == str(
        tmp_path
        / "model-ops"
        / "activate_adapter"
        / "model-ops-0002"
        / activation_payload["derived_model_id"]
        / "manifest.json"
    )
    assert activation_payload["adapter_set_hash"]
    assert Path(activation_payload["derived_model_path"]).is_dir()
    assert snapshot_payload["adapters"][0]["activation_status"] == "activated"
    assert snapshot_payload["adapters"][0]["derived_model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["model_id"] == activation_payload["derived_model_id"]
    assert snapshot_payload["derived_models"][0]["adapter_manifest_path"] == train_events[-1].completed.output_path


def test_activate_native_passes_repo_id_strings_to_save(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_load(model_path: str, *, adapter_path: str, return_config: bool):
        recorded["load_model_path"] = model_path
        recorded["load_adapter_path"] = adapter_path
        recorded["return_config"] = return_config

        class FakeModel:
            def named_modules(self):
                return []

            def update_modules(self, modules):
                recorded["updated_modules"] = modules

        return FakeModel(), object(), {"model_type": "llama"}

    def fake_save(output_dir, repo_id_or_path, model, tokenizer, config, donate_model=False):
        recorded["save_output_dir"] = output_dir
        recorded["save_base_model"] = repo_id_or_path
        recorded["save_donate_model"] = donate_model

    monkeypatch.setitem(
        sys.modules,
        "mlx.utils",
        types.SimpleNamespace(tree_unflatten=lambda items: items),
    )
    monkeypatch.setitem(
        sys.modules,
        "mlx_lm.utils",
        types.SimpleNamespace(load=fake_load, save=fake_save),
    )

    runner = MLXLMRunner()
    request = ActivationRequest(
        job_id="model-ops-activate-1",
        base_model_id="melix-dev-text",
        model_path=Path("mlx-community/Qwen3.5-0.8B-OptiQ-4bit"),
        adapter_dir=tmp_path / "adapter",
        adapter_manifest_path=tmp_path / "adapter" / "train_lora.adapter.json",
        derived_model_dir=tmp_path / "derived",
        activation_mode="fused_derived_model",
    )
    request.adapter_dir.mkdir(parents=True, exist_ok=True)
    request.adapter_manifest_path.write_text("{}", encoding="utf-8")

    result = runner.activate_native(request)

    assert recorded["load_model_path"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert recorded["save_base_model"] == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
    assert isinstance(recorded["save_base_model"], str)
    assert result.manifest_path == request.derived_model_dir / "manifest.json"
