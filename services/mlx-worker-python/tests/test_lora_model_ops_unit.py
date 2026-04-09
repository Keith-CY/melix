from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_ops import training_config as training_config_module
from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.lora_training_pipeline import _int_ext
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
