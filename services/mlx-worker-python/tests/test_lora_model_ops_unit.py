from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.errors import ModelOperationError
from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
from worker.model_ops import training_config as training_config_module
from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline
from worker.model_ops.lora_training_pipeline import _int_ext
from worker.model_ops.mlx_lm_runner import MLXLMRunner
from worker.model_ops.training_dataset import HFDatasetReference, load_training_dataset_package, materialize_hf_training_dataset_package


def _write_dataset_package(
    root: Path,
    *,
    manifest_payload: dict[str, object] | None = None,
    sample_lines: list[str] | None = None,
    valid_lines: list[str] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = manifest_payload or {
        "schema_version": "melix.training_dataset_package.v1",
        "dataset_id": "melix-dev-dataset",
        "format": "chat_messages",
        "sample_count": 1,
        "version": "1",
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    lines = sample_lines or [
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                ]
            }
        )
    ]
    (root / "samples.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if valid_lines is not None:
        (root / "valid.jsonl").write_text("\n".join(valid_lines) + "\n", encoding="utf-8")
    return root


def _text_model(*, model_path: str = "models/plain-llama", quant_profile_id: str = "", family_id: str = "") -> common_pb2.ModelSpec:
    model = common_pb2.ModelSpec(
        model_id="melix-test-text",
        model_path=model_path,
        model_kind="text",
        revision="main",
        quant_profile_id=quant_profile_id,
        max_context=4096,
    )
    if family_id:
        model.ext["text_family_id"] = family_id
    model.ext["text_layer_count"] = "2"
    return model


class _UnexpectedActivationRunner(MLXLMRunner):
    def activate(self, request):  # noqa: ANN001
        raise AssertionError("adapter_backed_runtime should not invoke fused activation")



def test_adapter_activation_pipeline_emits_explicit_adapter_backed_runtime_load_contract(tmp_path: Path) -> None:
    weights_dir = tmp_path / "adapter-weights"
    weights_dir.mkdir(parents=True)
    manifest_path = tmp_path / "train_lora.adapter.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "weights_path": str(weights_dir / "adapters.safetensors"),
                "adapter_name": "unit-adapter",
                "adapter_set_hash": "adapter-hash-1234",
                "job_id": "model-ops-0001",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_model = _text_model(model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit", quant_profile_id="q4")
    source_model.parser_mode = "structured"
    source_model.reasoning_mode = "separate"
    source_model.tokenizer_hash = "tok-hash-a"
    source_model.ext["text_family_id"] = "qwen"

    result = AdapterActivationPipeline(runner=_UnexpectedActivationRunner()).run(
        job_id="model-ops-0002",
        request_ext={
            "artifact_path": str(manifest_path),
            "activation_mode": "adapter_backed_runtime",
            "derived_model_alias": "Runtime Alias",
        },
        source_model=source_model,
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["activation_mode"] == "adapter_backed_runtime"
    assert result.manifest["adapter_manifest_path"] == str(manifest_path)
    assert result.manifest["adapter_weights_path"] == str(weights_dir / "adapters.safetensors")
    assert result.manifest["source_model_kind"] == "text"
    assert result.manifest["source_model_parser_mode"] == "structured"
    assert result.manifest["source_model_reasoning_mode"] == "separate"
    assert result.manifest["source_model_quant_profile_id"] == "q4"
    assert result.manifest["source_model_tokenizer_hash"] == "tok-hash-a"
    assert result.manifest["source_model_ext"]["text_family_id"] == "qwen"



def test_normalize_training_config_rejects_non_text_models() -> None:
    model = common_pb2.ModelSpec(model_id="melix-embed", model_path="models/embed", model_kind="embedding")

    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=model,
            ext={},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )

    assert exc.value.code == "unsupported_model_family"


def test_normalize_training_config_rejects_unknown_modes_and_families() -> None:
    with pytest.raises(ModelOperationError) as mode_exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"training_mode": "mystery"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert mode_exc.value.code == "unsupported_training_mode"

    with pytest.raises(ModelOperationError) as family_exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(family_id="unknown-family"),
            ext={},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert family_exc.value.code == "unsupported_model_family"


def test_normalize_training_config_rejects_response_only_for_unsupported_shapes() -> None:
    with pytest.raises(ModelOperationError) as exc:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"response_only": "true"},
            dataset_format="text_completion",
            response_only_supported=False,
            sample_count=1,
        )

    assert exc.value.code == "invalid_dataset_package"


def test_training_config_helpers_cover_family_and_validation_branches() -> None:
    mixtral = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="models/mixtral-8x7b", quant_profile_id="q4"),
        ext={"training_mode": "qlora", "hf_valid_split": "validation", "derived_model_alias": "alias-a"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
        validation_sample_count=1,
    )
    fallback = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="models/plain-generic"),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=1,
    )

    assert mixtral.family_id == "mixtral"
    assert mixtral.quantization_mode == "quantized_base"
    assert mixtral.validation_strategy == "hf_split"
    assert mixtral.desired_derived_model_alias == "alias-a"
    assert fallback.family_id == "llama"
    assert training_config_module._backend_target_modules(["custom.module"]) == ["custom.module"]


def test_training_config_applies_named_presets_and_allows_explicit_overrides() -> None:
    balanced = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit", quant_profile_id="q4"),
        ext={"preset_id": "balanced_adapter", "training_mode": "qlora", "rank": "24"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=4,
    )

    assert balanced.preset_id == "balanced_adapter"
    assert balanced.preset_title == "Balanced Adapter"
    assert balanced.rank == 24
    assert balanced.alpha == 32.0
    assert balanced.dropout == 0.05
    assert balanced.gradient_checkpointing is True
    assert balanced.batch_size == 2
    assert balanced.epochs == 2
    assert balanced.learning_rate == 1e-4

    with pytest.raises(ModelOperationError) as unknown_preset:
        training_config_module.normalize_training_config(
            source_model=_text_model(),
            ext={"preset_id": "mystery"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert unknown_preset.value.code == "invalid_training_preset"


def test_training_config_caps_computed_iters_with_max_steps() -> None:
    config = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="mlx-community/Qwen3.5-0.8B-OptiQ-4bit", quant_profile_id="q4"),
        ext={
            "training_mode": "qlora",
            "batch_size": "1",
            "epochs": "4",
            "max_steps": "2",
            "hf_valid_split": "validation",
        },
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=6,
        validation_sample_count=1,
    )

    assert config.iters == 2
    assert config.steps_per_report == 2
    assert config.steps_per_eval == 2
    assert config.steps_per_save == 2


def test_training_config_resolves_qwen_gemma_and_kimi_families() -> None:
    qwen = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path="mlx-community/Qwen3.5-0.8B-Instruct-4bit",
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    gemma = training_config_module.normalize_training_config(
        source_model=_text_model(model_path="unsloth/gemma-3-4b-it"),
        ext={},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )
    kimi = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path="mlx-community/kimi-k2-instruct-4bit",
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=2,
    )

    assert qwen.family_id == "qwen"
    assert gemma.family_id == "gemma"
    assert kimi.family_id == "kimi"
    assert qwen.quantization_mode == "quantized_base"
    assert kimi.quantization_mode == "quantized_base"
    assert any(module.endswith(".self_attn.q_proj") for module in qwen.expanded_target_modules)
    assert any(module.endswith(".mlp.gate_proj") for module in gemma.expanded_target_modules)
    assert any(module.endswith(".mlp.down_proj") for module in kimi.expanded_target_modules)


def test_training_config_scalar_helpers_reject_invalid_values() -> None:
    with pytest.raises(ModelOperationError):
        training_config_module._int_value("0", default=1, minimum=1, field_name="rank")
    with pytest.raises(ModelOperationError):
        training_config_module._float_value("-1", default=0.0, minimum=0.0, field_name="dropout")


@pytest.mark.parametrize(
    ("manifest_payload", "sample_lines", "expected_code"),
    [
        (None, ["{not-json"], "invalid_dataset_package"),
        ({"schema_version": "melix.training_dataset_package.v1"}, [json.dumps({"text": "hello"})], "invalid_dataset_package"),
        (
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "bad-format",
                "format": "unknown",
                "sample_count": 1,
                "version": "1",
            },
            [json.dumps({"text": "hello"})],
            "invalid_dataset_package",
        ),
        (
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "mismatch",
                "format": "text_completion",
                "sample_count": 2,
                "version": "1",
            },
            [json.dumps({"text": "hello"})],
            "invalid_dataset_package",
        ),
    ],
)
def test_load_training_dataset_package_rejects_manifest_and_sample_errors(
    tmp_path: Path,
    manifest_payload: dict[str, object] | None,
    sample_lines: list[str],
    expected_code: str,
) -> None:
    package_dir = tmp_path / "dataset"
    package_dir.mkdir(parents=True, exist_ok=True)
    if manifest_payload is None:
        (package_dir / "manifest.json").write_text("{not-json", encoding="utf-8")
    else:
        (package_dir / "manifest.json").write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")
    (package_dir / "samples.jsonl").write_text("\n".join(sample_lines) + "\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_dir))

    assert exc.value.code == expected_code


def test_load_training_dataset_package_rejects_empty_and_invalid_validation_data(tmp_path: Path) -> None:
    empty_package = _write_dataset_package(
        tmp_path / "empty",
        manifest_payload={
            "schema_version": "melix.training_dataset_package.v1",
            "dataset_id": "empty",
            "format": "text_completion",
            "sample_count": 1,
            "version": "1",
        },
        sample_lines=[""],
    )
    with pytest.raises(ModelOperationError) as empty_exc:
        load_training_dataset_package(str(empty_package))
    assert empty_exc.value.code == "invalid_dataset_package"

    invalid_valid = _write_dataset_package(
        tmp_path / "invalid-valid",
        valid_lines=["{not-json"],
    )
    with pytest.raises(ModelOperationError) as valid_exc:
        load_training_dataset_package(str(invalid_valid))
    assert valid_exc.value.code == "invalid_dataset_package"


@pytest.mark.parametrize(
    "sample",
    [
        "not-a-dict",
        {"messages": []},
        {"messages": ["bad"]},
        {"messages": [{"role": "invalid", "content": "bad"}]},
        {
            "messages": [
                {"role": "user", "content": "a"},
                {"role": "user", "content": "b"},
                {"role": "assistant", "content": "c"},
            ]
        },
        {"messages": [{"role": "user", "content": "a"}]},
    ],
)
def test_normalize_sample_rejects_invalid_chat_shapes(sample: object) -> None:
    with pytest.raises(ModelOperationError):
        training_dataset_module._normalize_sample(
            sample,
            format_name="chat_messages",
            max_characters_per_sample=0,
        )


def test_normalize_sample_covers_prompt_text_and_tool_paths() -> None:
    prompt_completion = training_dataset_module._normalize_sample(
        {"prompt": "abcdef", "completion": "uvwxyz"},
        format_name="prompt_completion",
        max_characters_per_sample=3,
    )
    with_tools = training_dataset_module._normalize_sample(
        {
            "messages": [
                {"role": "user", "content": "abcdef"},
                {"role": "assistant", "content": "uvwxyz"},
            ],
            "tools": [{"name": "search"}],
        },
        format_name="chat_messages",
        max_characters_per_sample=3,
    )
    with pytest.raises(ModelOperationError):
        training_dataset_module._normalize_sample(
            {"prompt": "", "completion": "x"},
            format_name="prompt_completion",
            max_characters_per_sample=0,
        )
    with pytest.raises(ModelOperationError):
        training_dataset_module._normalize_sample(
            {"text": ""},
            format_name="text_completion",
            max_characters_per_sample=0,
        )

    assert prompt_completion == {"prompt": "abc", "completion": "uvw"}
    assert with_tools["tools"] == [{"name": "search"}]
    assert with_tools["messages"][0]["content"] == "abc"
    assert training_dataset_module._truncate_text("abcdef", 2) == "ab"


def test_materialize_hf_training_dataset_rejects_empty_validation_split(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
        valid_split="validation",
    )

    def fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint == "rows" and params["split"] == "validation":
            return {"rows": []}
        if endpoint == "rows":
            return {"rows": [{"row": {"text": "hello"}}]}
        return {"splits": [{"split": "train", "config": "default"}]}

    with pytest.raises(ModelOperationError) as exc:
        materialize_hf_training_dataset_package(
            reference,
            cache_root=tmp_path / "datasets",
            fetch_json=fetcher,
        )

    assert exc.value.code == "hf_dataset_fetch_failed"


def test_hf_dataset_helpers_cover_paging_and_direct_chat_paths(tmp_path: Path) -> None:
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="messages",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )

    config = training_dataset_module._resolve_hf_dataset_name(
        reference,
        lambda endpoint, params: {"splits": ["bad", {"split": "train", "config": "default"}]},
    )
    assert config == "default"

    calls: list[int] = []

    def paged_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(int(params["offset"]))
        if params["offset"] == "0":
            return {"rows": [{"row": {"text": f"value-{index}"}} for index in range(100)]}
        return {"rows": []}

    rows = training_dataset_module._fetch_hf_dataset_rows(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            chat_feature="",
            prompt_feature="",
            completion_feature="",
            text_feature="text",
        ),
        paged_fetcher,
    )
    assert len(rows) == 100
    assert calls == [0, 100]

    assert training_dataset_module._infer_hf_dataset_format(reference, [{"messages": []}]) == "chat_messages"
    assert training_dataset_module._infer_hf_dataset_format(
        HFDatasetReference(
            dataset_path="melix/demo-hf",
            dataset_name="default",
            dataset_revision="main",
            train_split="train",
            chat_feature="",
            prompt_feature="p",
            completion_feature="c",
            text_feature="",
        ),
        [{"p": "hi", "c": "there"}],
    ) == "prompt_completion"
    assert training_dataset_module._map_hf_row_to_training_sample(
        {"messages": [{"role": "user", "content": "hello"}]},
        "chat_messages",
        reference,
    ) == {"messages": [{"role": "user", "content": "hello"}]}


def test_misc_lora_helpers_cover_int_ext_and_cached_valid_split(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "hf_dataset_name": "default",
                "hf_dataset_revision": "main",
                "hf_train_split": "train",
                "hf_valid_split": "validation",
            }
        ),
        encoding="utf-8",
    )
    reference = HFDatasetReference(
        dataset_path="melix/demo-hf",
        dataset_name="",
        dataset_revision="old",
        train_split="old-train",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="text",
    )

    restored = training_dataset_module._reference_from_cached_manifest(reference, manifest_path)

    assert restored.valid_split == "validation"
    assert _int_ext({"sample_limit": "7"}, "sample_limit") == 7
    assert _int_ext({}, "sample_limit") == 0


def test_mlx_lm_runner_train_native_collects_checkpoint_throughput_and_peak_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mlx_pkg = types.ModuleType("mlx")
    fake_mlx_pkg.__path__ = []
    fake_mlx_core = types.ModuleType("mlx.core")
    reset_calls: list[str] = []

    class FakeMetal:
        @staticmethod
        def reset_peak_memory() -> None:
            reset_calls.append("reset")

        @staticmethod
        def get_peak_memory() -> float:
            return float(3 * 1024**3)

    fake_mlx_core.metal = FakeMetal()
    fake_mlx_pkg.core = fake_mlx_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx_pkg)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mlx_core)

    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.__path__ = []
    fake_lora = types.ModuleType("mlx_lm.lora")
    fake_callbacks = types.ModuleType("mlx_lm.tuner.callbacks")
    fake_datasets = types.ModuleType("mlx_lm.tuner.datasets")
    fake_utils = types.ModuleType("mlx_lm.utils")

    class FakeTrainingCallback:
        pass

    def fake_load(model_source: str, *, lazy: bool = False):
        assert model_source == str(tmp_path / "base-model")
        assert lazy is False
        return object(), object()

    def fake_load_local_dataset(dataset_dir: Path, tokenizer, args):
        _ = tokenizer
        assert dataset_dir == tmp_path / "normalized"
        assert args.adapter_path == str(tmp_path / "adapter-output")
        return ["train"], ["valid"], None

    def fake_train_model(args, model, train_set, valid_set, training_callback) -> None:
        _ = model
        assert train_set == ["train"]
        assert valid_set == ["valid"]
        training_callback.on_train_loss_report(
            {
                "train_loss": 0.8,
                "learning_rate": 1e-4,
                "trained_tokens": 120,
            }
        )
        training_callback.on_val_loss_report({"val_loss": 0.2})
        checkpoint_root = Path(args.adapter_path)
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        (checkpoint_root / "checkpoint-1").mkdir(parents=True, exist_ok=True)
        (checkpoint_root / "checkpoint-1" / "weights.safetensors").write_text("a", encoding="utf-8")
        (checkpoint_root / "checkpoint-2.safetensors").write_text("b", encoding="utf-8")

    fake_lora.train_model = fake_train_model
    fake_callbacks.TrainingCallback = FakeTrainingCallback
    fake_datasets.load_local_dataset = fake_load_local_dataset
    fake_utils.load = fake_load
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(sys.modules, "mlx_lm.lora", fake_lora)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.callbacks", fake_callbacks)
    monkeypatch.setitem(sys.modules, "mlx_lm.tuner.datasets", fake_datasets)
    monkeypatch.setitem(sys.modules, "mlx_lm.utils", fake_utils)

    perf_counter_values = iter([10.0, 12.0])
    monkeypatch.setattr(
        mlx_lm_runner_module.time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    config = training_config_module.normalize_training_config(
        source_model=_text_model(
            model_path=str(tmp_path / "base-model"),
            quant_profile_id="q4",
        ),
        ext={"training_mode": "qlora"},
        dataset_format="chat_messages",
        response_only_supported=True,
        sample_count=4,
    )
    request = mlx_lm_runner_module.TrainingRequest(
        job_id="train-real",
        base_model_id="melix-dev-text",
        model_path=tmp_path / "base-model",
        model_revision="main",
        adapter_output_dir=tmp_path / "adapter-output",
        normalized_dataset_dir=tmp_path / "normalized",
        config=config,
        dataset_format="chat_messages",
    )

    result = mlx_lm_runner_module.MLXLMRunner().train_native(request)

    assert reset_calls == ["reset"]
    assert result.metrics.loss_final == pytest.approx(0.2)
    assert result.metrics.loss_best == pytest.approx(0.2)
    assert result.metrics.learning_rate_final == pytest.approx(1e-4)
    assert result.metrics.checkpoint_count == 2
    assert result.metrics.resume_ready is True
    assert result.metrics.tokens_per_second == pytest.approx(60.0)
    assert result.metrics.peak_memory_gb == pytest.approx(3.0)


def test_adapter_backed_runtime_manifest_requires_adapter_weights_path(tmp_path: Path) -> None:
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "adapter_set_hash": "adapter-alpha",
                "adapter_name": "demo-adapter",
            }
        ) + "\n",
        encoding="utf-8",
    )

    pipeline = AdapterActivationPipeline()

    with pytest.raises(ModelOperationError) as exc:
        pipeline.run(
            job_id="activate-1",
            request_ext={
                "artifact_path": str(adapter_manifest_path),
                "activation_mode": "adapter_backed_runtime",
            },
            source_model=_text_model(model_path=str(tmp_path / "base-model")),
            output_dir=tmp_path / "activate",
        )

    assert exc.value.code == "activation_failure"
    assert "weights_path" in exc.value.message


def test_adapter_backed_runtime_activation_writes_explicit_runtime_contract(tmp_path: Path) -> None:
    adapter_weights_path = tmp_path / "weights" / "adapters.safetensors"
    adapter_weights_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_weights_path.write_text("adapter", encoding="utf-8")
    adapter_manifest_path = tmp_path / "train_lora.adapter.json"
    adapter_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "melix.lora_adapter_package.v1",
                "source_model": "melix-test-text",
                "adapter_set_hash": "adapter-beta",
                "adapter_name": "demo-adapter",
                "weights_path": str(adapter_weights_path),
                "desired_derived_model_alias": "Demo Alias",
            }
        ) + "\n",
        encoding="utf-8",
    )

    class GuardRunner:
        def activate(self, request) -> None:  # pragma: no cover - should never be called
            raise AssertionError(f"unexpected fused activation request: {request}")

    pipeline = AdapterActivationPipeline(runner=GuardRunner())
    result = pipeline.run(
        job_id="activate-2",
        request_ext={
            "artifact_path": str(adapter_manifest_path),
            "activation_mode": "adapter_backed_runtime",
        },
        source_model=_text_model(model_path=str(tmp_path / "base-model")),
        output_dir=tmp_path / "activate",
    )

    assert result.manifest["schema_version"] == "melix.derived_text_model.v1"
    assert result.manifest["activation_mode"] == "adapter_backed_runtime"
    assert result.manifest["activation_backend"] == "internal"
    assert result.manifest["adapter_manifest_path"] == str(adapter_manifest_path)
    assert result.manifest["adapter_weights_path"] == str(adapter_weights_path)
    assert result.manifest["derived_model_path"] == str(tmp_path / "base-model")
    assert result.manifest["derived_model_alias"] == "Demo Alias"
    assert result.manifest_path.exists()
