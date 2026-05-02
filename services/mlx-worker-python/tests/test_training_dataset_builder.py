from __future__ import annotations

import json
from pathlib import Path

import pytest

from worker.model_ops import training_dataset as training_dataset_module
from worker.model_ops.errors import ModelOperationError
from worker.model_ops.training_dataset import (
    HFDatasetReference,
    ResolvedTrainingDatasetPackage,
    TrainingDatasetPackage,
    build_training_dataset_artifact,
    load_training_dataset_package,
    write_normalized_dataset_snapshot,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_write_jsonl_rows_streams_each_row_without_joining_the_full_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "rows.jsonl"
    writes: list[str] = []

    class RecordingFile:
        def __enter__(self) -> RecordingFile:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def write(self, chunk: str) -> int:
            writes.append(chunk)
            return len(chunk)

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> RecordingFile:
        assert self == output_path
        assert mode == "w"
        assert kwargs.get("encoding") == "utf-8"
        return RecordingFile()

    monkeypatch.setattr(Path, "open", fake_open)

    training_dataset_module._write_jsonl_rows(
        output_path,
        [
            {"text": "alpha"},
            {"text": "beta"},
        ],
    )

    assert writes == [
        json.dumps({"text": "alpha"}) + "\n",
        json.dumps({"text": "beta"}) + "\n",
    ]


def test_write_jsonl_rows_preserves_the_existing_blank_line_contract_for_empty_inputs(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "empty.jsonl"

    training_dataset_module._write_jsonl_rows(output_path, [])

    assert output_path.read_text(encoding="utf-8") == "\n"


def test_write_normalized_dataset_snapshot_writes_matching_train_and_samples_jsonl(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "dataset-package"
    package_path.mkdir(parents=True, exist_ok=True)
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"

    dataset = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=manifest_path,
        samples_path=samples_path,
        schema_version="melix.training_dataset_package.v1",
        dataset_id="melix-demo",
        format="prompt_completion",
        sample_count=2,
        version="1",
        normalized_samples=[
            {"prompt": "alpha", "completion": "beta"},
            {"prompt": "gamma", "completion": "delta"},
        ],
        normalized_validation_samples=[
            {"prompt": "holdout", "completion": "answer"},
        ],
        validation_sample_count=1,
        response_only_supported=False,
    )

    snapshot = write_normalized_dataset_snapshot(dataset, output_dir=tmp_path / "exports")

    assert snapshot.samples_path.read_text(encoding="utf-8") == (
        '{"prompt": "alpha", "completion": "beta"}\n'
        '{"prompt": "gamma", "completion": "delta"}\n'
    )
    assert snapshot.train_path.read_text(encoding="utf-8") == snapshot.samples_path.read_text(encoding="utf-8")
    assert snapshot.valid_path is not None
    assert snapshot.valid_path.read_text(encoding="utf-8") == (
        '{"prompt": "holdout", "completion": "answer"}\n'
    )


def test_write_normalized_dataset_snapshot_clears_stale_valid_jsonl_when_no_validation_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "dataset-package"
    package_path.mkdir(parents=True, exist_ok=True)
    stale_valid_path = tmp_path / "exports" / "normalized_dataset" / "valid.jsonl"
    stale_valid_path.parent.mkdir(parents=True, exist_ok=True)
    stale_valid_path.write_text("stale\n", encoding="utf-8")

    dataset = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=package_path / "manifest.json",
        samples_path=package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="melix-demo",
        format="prompt_completion",
        sample_count=2,
        version="1",
        normalized_samples=[
            {"prompt": "alpha", "completion": "beta"},
            {"prompt": "gamma", "completion": "delta"},
        ],
        normalized_validation_samples=[],
        validation_sample_count=0,
        response_only_supported=False,
    )

    snapshot = write_normalized_dataset_snapshot(dataset, output_dir=tmp_path / "exports")

    expected_payload = (
        '{"prompt": "alpha", "completion": "beta"}\n'
        '{"prompt": "gamma", "completion": "delta"}\n'
    )
    assert snapshot.samples_path.read_text(encoding="utf-8") == expected_payload
    assert snapshot.train_path.read_text(encoding="utf-8") == expected_payload
    assert snapshot.valid_path is None
    assert stale_valid_path.exists() is False



def test_load_training_dataset_package_respects_sample_limit_after_skipping_blank_lines(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "limited-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "limited-package",
                "format": "text_completion",
                "sample_count": 2,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        "\n"
        '{"text": "alpha"}\n'
        "\n"
        '{"text": "beta"}\n',
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path), sample_limit=1)

    assert package.sample_count == 1
    assert package.normalized_samples == [{"text": "alpha"}]



def test_load_training_dataset_package_stops_reading_after_sample_limit(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "limited-invalid-tail"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "limited-invalid-tail",
                "format": "text_completion",
                "sample_count": 2,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"text": "alpha"}\n'
        "{not-json\n",
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path), sample_limit=1)

    assert package.sample_count == 1
    assert package.normalized_samples == [{"text": "alpha"}]


def test_load_training_dataset_package_supports_preference_pair_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "preference-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "preference-package",
                "format": "preference_pair",
                "sample_count": 2,
                "version": "1",
                "validation_sample_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"prompt": "Choose a greeting.", "chosen": "Hello.", "rejected": "Goodbye."}\n'
        '{"prompt": "Pick the safer answer.", "chosen": "Use the guide.", "rejected": "Guess."}\n',
        encoding="utf-8",
    )
    (package_path / "valid.jsonl").write_text(
        '{"prompt": "Holdout?", "chosen": "Yes.", "rejected": "No."}\n',
        encoding="utf-8",
    )

    package = load_training_dataset_package(str(package_path))

    assert package.format == "preference_pair"
    assert package.response_only_supported is False
    assert package.normalized_samples == [
        {"prompt": "Choose a greeting.", "chosen": "Hello.", "rejected": "Goodbye."},
        {"prompt": "Pick the safer answer.", "chosen": "Use the guide.", "rejected": "Guess."},
    ]
    assert package.normalized_validation_samples == [
        {"prompt": "Holdout?", "chosen": "Yes.", "rejected": "No."}
    ]


def test_load_training_dataset_package_rejects_incomplete_preference_pair_samples(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "invalid-preference-package"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "invalid-preference-package",
                "format": "preference_pair",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text(
        '{"prompt": "Choose.", "chosen": "A"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"



def test_iter_dataset_package_jsonl_rows_enforces_sample_limit_before_invalid_tail(
    tmp_path: Path,
) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(
        '{"text": "alpha"}\n'
        "\n"
        '{"text": "beta"}\n'
        "{not-json\n",
        encoding="utf-8",
    )

    rows = list(
        training_dataset_module._iter_dataset_package_jsonl_rows(
            rows_path,
            invalid_json_message="Training dataset sample is not valid JSON.",
            sample_limit=2,
        )
    )

    assert rows == [{"text": "alpha"}, {"text": "beta"}]



def test_load_training_dataset_package_rejects_invalid_manifest_json(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "invalid-manifest"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text("{not-json", encoding="utf-8")
    (package_path / "samples.jsonl").write_text('{"text": "alpha"}\n', encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"



def test_load_training_dataset_package_rejects_invalid_sample_json(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "invalid-sample"
    package_path.mkdir(parents=True, exist_ok=True)
    (package_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "invalid-sample",
                "format": "text_completion",
                "sample_count": 1,
                "version": "1",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (package_path / "samples.jsonl").write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as exc:
        load_training_dataset_package(str(package_path))

    assert exc.value.code == "invalid_dataset_package"



def test_build_training_dataset_artifact_converts_alpaca_rows_and_records_quality_signals(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "alpaca.jsonl",
        [
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Repeat the token.",
                "input": "",
                "output": "token\u0000token",
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "alpaca",
            "dataset_id": "melix-alpaca-demo",
            "validation_ratio": "0.34",
            "preview_count": "2",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "built-dataset",
        source_model_id="melix-dev-text",
    )

    payload = result.manifest_payload
    package = load_training_dataset_package(str(result.package_path))

    assert result.output_path == result.package_path
    assert payload["schema_version"] == "melix.training_dataset_package.v1"
    assert payload["dataset_id"] == "melix-alpaca-demo"
    assert payload["format"] == "prompt_completion"
    assert payload["sample_count"] == 2
    assert payload["validation_sample_count"] == 1
    assert payload["validation_strategy"] == "deterministic_ratio"
    assert payload["conversion_template"] == "alpaca"
    assert payload["source_kind"] == "local_path"
    assert len(payload["preview_samples"]) == 2
    assert payload["quality"]["duplicate_count"] == 1
    assert payload["quality"]["dirty_count"] == 1
    assert payload["token_stats"]["estimator"] == "whitespace_v1"
    assert payload["token_stats"]["prompt_tokens_p95"] >= 3
    assert package.dataset_id == "melix-alpaca-demo"
    assert package.format == "prompt_completion"
    assert package.validation_sample_count == 1


def test_build_training_dataset_artifact_converts_preference_pair_rows(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "preferences.jsonl",
        [
            {
                "prompt": "Choose the concise answer.",
                "chosen": "Use the short answer.",
                "rejected": "Add unrelated details.",
            },
            {
                "prompt": "Choose the concise answer.",
                "chosen": "Use the short answer.",
                "rejected": "Add unrelated details.",
            },
            {
                "prompt": "Pick the better answer.",
                "chosen": "same",
                "rejected": "same",
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "dataset_id": "melix-preference-demo",
            "validation_ratio": "0.34",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "built-preference-dataset",
        source_model_id="melix-dev-text",
    )

    payload = result.manifest_payload
    package = load_training_dataset_package(str(result.package_path))

    assert payload["schema_version"] == "melix.training_dataset_package.v1"
    assert payload["format"] == "preference_pair"
    assert payload["conversion_template"] == "preference_pair"
    assert payload["response_only_supported"] is False
    assert payload["quality"]["duplicate_count"] == 1
    assert payload["quality"]["dirty_count"] == 1
    assert payload["quality"]["dirty_samples"] == [
        {"index": 2, "reasons": ["duplicate_preference_pair"]}
    ]
    assert payload["token_stats"]["prompt_tokens_max"] >= 4
    assert payload["token_stats"]["completion_tokens_max"] >= 6
    assert package.format == "preference_pair"
    assert package.validation_sample_count == 1


def test_build_training_dataset_artifact_inspects_sharegpt_rows_without_writing_a_package(
    tmp_path: Path,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "sharegpt.jsonl",
        [
            {
                "conversations": [
                    {"from": "system", "value": "You are helpful."},
                    {"from": "human", "value": "Say hi."},
                    {"from": "gpt", "value": "Hi there."},
                ]
            },
            {
                "conversations": [
                    {"from": "human", "value": "Say bye."},
                    {"from": "gpt", "value": "Bye."},
                ]
            },
        ],
    )

    result = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "preview_count": "1",
            "inspect_only": "true",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "dataset-inspect",
        source_model_id="melix-dev-text",
    )

    payload = result.manifest_payload

    assert result.output_path == result.manifest_path
    assert payload["schema_version"] == "melix.training_dataset_inspection.v1"
    assert payload["format"] == "chat_messages"
    assert payload["conversion_template"] == "sharegpt"
    assert payload["sample_count"] == 2
    assert payload["validation_sample_count"] == 0
    assert payload["preview_samples"][0]["messages"][0]["role"] == "system"
    assert payload["preview_samples"][0]["messages"][-1]["role"] == "assistant"
    assert payload["build_ready"] is True
    assert (result.package_path / "samples.jsonl").exists() is False


def test_build_training_dataset_artifact_materializes_hf_source_and_clears_stale_validation_file(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "hf-dataset"
    stale_valid = output_dir / "valid.jsonl"
    stale_valid.parent.mkdir(parents=True, exist_ok=True)
    stale_valid.write_text("stale\n", encoding="utf-8")

    def fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        if endpoint == "splits":
            return {
                "splits": [
                    {
                        "dataset": "HuggingFaceH4/ultrachat_200k",
                        "config": "default",
                        "split": "train_sft",
                    }
                ]
            }
        if endpoint == "rows":
            offset = params.get("offset", "0")
            if offset != "0":
                return {"rows": []}
            return {
                "rows": [
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say hi."},
                                {"role": "assistant", "content": "Hi."},
                            ]
                        }
                    },
                    {
                        "row": {
                            "messages": [
                                {"role": "user", "content": "Say bye."},
                                {"role": "assistant", "content": "Bye."},
                            ]
                        }
                    },
                ]
            }
        raise AssertionError(f"unexpected hf fetch: {endpoint} {params}")

    result = build_training_dataset_artifact(
        {
            "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
            "template": "source_schema",
            "dataset_id": "melix-hf-demo",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=output_dir,
        source_model_id="melix-dev-text",
        hf_dataset_fetcher=fetcher,
    )

    payload = result.manifest_payload
    assert payload["source_kind"] == "hf_dataset"
    assert payload["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k"
    assert payload["hf_dataset_name"] == "default"
    assert payload["hf_train_split"] == "train"
    assert payload["source_manifest_path"].endswith("manifest.json")
    assert payload["source_samples_path"].endswith("samples.jsonl")
    assert payload["sample_count"] == 2
    assert stale_valid.exists() is False


def test_hf_preference_pair_schema_inference_and_mapping() -> None:
    default_reference = HFDatasetReference(
        dataset_path="melix/preferences",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )
    default_rows = [
        {
            "prompt": "Choose.",
            "chosen": "A.",
            "rejected": "B.",
        }
    ]
    assert training_dataset_module._infer_hf_dataset_format(
        default_reference,
        default_rows,
    ) == "preference_pair"
    assert training_dataset_module._map_hf_row_to_training_sample(
        default_rows[0],
        "preference_pair",
        default_reference,
    ) == {"prompt": "Choose.", "chosen": "A.", "rejected": "B."}

    configured_reference = HFDatasetReference(
        dataset_path="melix/preferences",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        chat_feature="",
        prompt_feature="question",
        completion_feature="",
        text_feature="",
        chosen_feature="accepted",
        rejected_feature="rejected_answer",
    )
    configured_row = {
        "question": "Pick.",
        "accepted": "Use this.",
        "rejected_answer": "Avoid this.",
    }
    assert training_dataset_module._infer_hf_dataset_format(
        configured_reference,
        [configured_row],
    ) == "preference_pair"
    assert training_dataset_module._map_hf_row_to_training_sample(
        configured_row,
        "preference_pair",
        configured_reference,
    ) == {"prompt": "Pick.", "chosen": "Use this.", "rejected": "Avoid this."}

    with pytest.raises(ModelOperationError) as missing_column:
        training_dataset_module._map_hf_row_to_training_sample(
            {"question": "Pick.", "accepted": "Use this."},
            "preference_pair",
            configured_reference,
        )
    assert missing_column.value.code == "hf_dataset_fetch_failed"


def test_build_training_dataset_artifact_loads_existing_package_and_helper_branches(
    tmp_path: Path,
) -> None:
    source_package = tmp_path / "existing-package"
    _write_jsonl(
        source_package / "samples.jsonl",
        [
            {"text": "alpha beta"},
            {"text": "gamma delta"},
        ],
    )
    (source_package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "melix.training_dataset_package.v1",
                "dataset_id": "existing-package",
                "format": "text_completion",
                "sample_count": 2,
                "version": "3",
                "validation_sample_count": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    built = build_training_dataset_artifact(
        {
            "dataset_uri": str(source_package),
            "template": "existing_package",
            "preview_count": "1",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "rebuilt-package",
        source_model_id="melix-dev-text",
    )

    assert built.manifest_payload["source_kind"] == "local_package"
    assert built.manifest_payload["conversion_template"] == "existing_package"
    assert built.manifest_payload["preview_samples"] == [{"text": "alpha beta"}]


    with pytest.raises(ModelOperationError) as missing_uri:
        training_dataset_module._resolve_dataset_build_source(
            {},
            jobs_root=tmp_path / "jobs",
            hf_dataset_fetcher=None,
            sample_limit=0,
        )
    assert missing_uri.value.code == "invalid_dataset_source"

    missing_path = tmp_path / "does-not-exist.jsonl"
    with pytest.raises(ModelOperationError) as missing_path_exc:
        training_dataset_module._resolve_dataset_build_source(
            {"dataset_uri": str(missing_path)},
            jobs_root=tmp_path / "jobs",
            hf_dataset_fetcher=None,
            sample_limit=0,
        )
    assert missing_path_exc.value.code == "invalid_dataset_source"

    invalid_jsonl = tmp_path / "invalid.jsonl"
    invalid_jsonl.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as invalid_json_exc:
        training_dataset_module._read_local_jsonl_rows(invalid_jsonl, sample_limit=0)
    assert invalid_json_exc.value.code == "invalid_dataset_source"

    scalar_jsonl = tmp_path / "scalar.jsonl"
    scalar_jsonl.write_text('"hello"\n', encoding="utf-8")
    with pytest.raises(ModelOperationError) as non_object_exc:
        training_dataset_module._read_local_jsonl_rows(scalar_jsonl, sample_limit=0)
    assert non_object_exc.value.code == "invalid_dataset_source"

    empty_jsonl = tmp_path / "empty.jsonl"
    empty_jsonl.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as empty_exc:
        training_dataset_module._read_local_jsonl_rows(empty_jsonl, sample_limit=0)
    assert empty_exc.value.code == "invalid_dataset_source"

    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {"instruction": "Do it", "output": "Done"},
    ) == "alpaca"
    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {"prompt": "Choose", "chosen": "A", "rejected": "B"},
    ) == "preference_pair"
    assert training_dataset_module._resolve_local_conversion_template(
        "auto",
        {"conversation": []},
    ) == "sharegpt"
    with pytest.raises(ModelOperationError) as invalid_template:
        training_dataset_module._resolve_local_conversion_template("mystery", {"text": "hello"})
    assert invalid_template.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as no_template:
        training_dataset_module._resolve_local_conversion_template("auto", {"image": "unsupported"})
    assert no_template.value.code == "invalid_dataset_source"

    assert training_dataset_module._convert_local_rows(
        [{"text": "hello world"}],
        "text_completion",
    ) == ("text_completion", [{"text": "hello world"}])
    assert training_dataset_module._convert_local_rows(
        [{"prompt": "Choose", "chosen": "A", "rejected": "B"}],
        "preference_pair",
    ) == ("preference_pair", [{"prompt": "Choose", "chosen": "A", "rejected": "B"}])
    with pytest.raises(ModelOperationError) as bad_sharegpt_shape:
        training_dataset_module._convert_local_rows(
            [{"conversations": "bad"}],
            "sharegpt",
        )
    assert bad_sharegpt_shape.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as bad_sharegpt_turn:
        training_dataset_module._convert_local_rows(
            [{"conversations": ["bad-turn"]}],
            "sharegpt",
        )
    assert bad_sharegpt_turn.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as bad_sharegpt_role:
        training_dataset_module._convert_local_rows(
            [{"conversations": [{"from": "robot", "value": "??"}]}],
            "sharegpt",
        )
    assert bad_sharegpt_role.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as unsupported_template:
        training_dataset_module._convert_local_rows([{"text": "hello"}], "mystery")
    assert unsupported_template.value.code == "invalid_dataset_source"

    with pytest.raises(ModelOperationError) as split_exc:
        training_dataset_module._deterministic_validation_split([{"text": "solo"}], 0.5)
    assert split_exc.value.code == "invalid_dataset_source"

    assert training_dataset_module._sample_token_counts({}, "chat_messages") == (0, 0)
    assert training_dataset_module._sample_token_counts(
        {"text": "hello world"},
        "text_completion",
    ) == (0, 2)
    sample_rows = [
        {"prompt": "hello world", "completion": "hello world"},
        {"prompt": "hello world", "completion": "hello world"},
    ]
    assert training_dataset_module._build_quality_report(sample_rows) == {
        "duplicate_count": 1,
        "duplicate_sample_indices": [1],
        "dirty_count": 2,
        "dirty_samples": [
            {"index": 0, "reasons": ["duplicate_prompt_completion"]},
            {"index": 1, "reasons": ["duplicate_prompt_completion"]},
        ],
    }
    assert training_dataset_module._build_token_stats(sample_rows, "prompt_completion") == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 2.0,
        "prompt_tokens_p50": 2,
        "prompt_tokens_p95": 2,
        "prompt_tokens_max": 2,
        "completion_tokens_mean": 2.0,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 2,
        "completion_tokens_max": 2,
        "total_tokens_mean": 4.0,
        "total_tokens_p50": 4,
        "total_tokens_p95": 4,
        "total_tokens_max": 4,
    }
    assert training_dataset_module._mean_value([]) == 0.0
    assert training_dataset_module._percentile_value([], 0.95) == 0


def test_build_token_stats_reuses_single_sorted_pass_per_token_series(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_percentile_value(values: list[int], pct: float) -> int:
        raise AssertionError(f"legacy percentile helper should not run for optimized token stats ({pct=}, {values=})")

    def fail_generic_token_counter(sample: dict[str, object], format_name: str) -> tuple[int, int]:
        raise AssertionError(f"prompt_completion token stats should use the direct fast path ({format_name=})")

    def fail_mean_value(values: list[int]) -> float:
        raise AssertionError(f"prompt_completion token stats should reuse collected totals ({values=})")

    class SinglePassPromptCompletionSamples:
        def __init__(self) -> None:
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("prompt_completion token stats should consume the iterable only once")
            return iter(
                [
                    {"prompt": "a b c", "completion": "d e"},
                    {"prompt": "f", "completion": "g h i j"},
                    {"prompt": "k l", "completion": "m"},
                    {"prompt": "n o p q", "completion": "r s t"},
                ]
            )

    monkeypatch.setattr(training_dataset_module, "_percentile_value", fail_percentile_value)
    monkeypatch.setattr(training_dataset_module, "_sample_token_counts", fail_generic_token_counter)
    monkeypatch.setattr(training_dataset_module, "_mean_value", fail_mean_value)

    prompt_completion_samples = SinglePassPromptCompletionSamples()

    assert training_dataset_module._build_token_stats(
        prompt_completion_samples,
        "prompt_completion",
    ) == {
        "estimator": "whitespace_v1",
        "sample_count": 4,
        "prompt_tokens_mean": 2.5,
        "prompt_tokens_p50": 2,
        "prompt_tokens_p95": 3,
        "prompt_tokens_max": 4,
        "completion_tokens_mean": 2.5,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 3,
        "completion_tokens_max": 4,
        "total_tokens_mean": 5.0,
        "total_tokens_p50": 5,
        "total_tokens_p95": 5,
        "total_tokens_max": 7,
    }
    assert prompt_completion_samples.iterations == 1
    with pytest.raises(AssertionError, match="reuse collected totals"):
        fail_mean_value([])
    assert training_dataset_module._mean_value_from_total(0, 0) == 0.0

    monkeypatch.undo()
    assert training_dataset_module._build_token_stats(
        [
            {"text": "alpha beta gamma"},
            {"text": "delta"},
        ],
        "text_completion",
    ) == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 0.0,
        "prompt_tokens_p50": 0,
        "prompt_tokens_p95": 0,
        "prompt_tokens_max": 0,
        "completion_tokens_mean": 2.0,
        "completion_tokens_p50": 1,
        "completion_tokens_p95": 1,
        "completion_tokens_max": 3,
        "total_tokens_mean": 2.0,
        "total_tokens_p50": 1,
        "total_tokens_p95": 1,
        "total_tokens_max": 3,
    }

    with pytest.raises(ModelOperationError) as int_parse_exc:
        training_dataset_module._int_ext_value(
            "bad",
            default=0,
            minimum=0,
            field_name="sample_limit",
        )
    assert int_parse_exc.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as int_range_exc:
        training_dataset_module._int_ext_value(
            "-1",
            default=0,
            minimum=0,
            field_name="sample_limit",
        )
    assert int_range_exc.value.code == "invalid_dataset_source"

    with pytest.raises(ModelOperationError) as float_parse_exc:
        training_dataset_module._float_ext_value(
            "bad",
            default=0.0,
            minimum=0.0,
            maximum=1.0,
            field_name="validation_ratio",
        )
    assert float_parse_exc.value.code == "invalid_dataset_source"
    with pytest.raises(ModelOperationError) as float_range_exc:
        training_dataset_module._float_ext_value(
            "1.5",
            default=0.0,
            minimum=0.0,
            maximum=1.0,
            field_name="validation_ratio",
        )
    assert float_range_exc.value.code == "invalid_dataset_source"


def test_build_token_stats_skips_quality_only_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_canonical_sample_digest(sample: dict[str, object]) -> bytes:
        raise AssertionError(f"token stats should not compute canonical digests ({sample=})")

    def fail_dirty_sample_reasons(sample: dict[str, object]) -> list[str]:
        raise AssertionError(f"token stats should not inspect dirty-sample reasons ({sample=})")

    monkeypatch.setattr(training_dataset_module, "_canonical_sample_digest", fail_canonical_sample_digest)
    monkeypatch.setattr(training_dataset_module, "_dirty_sample_reasons", fail_dirty_sample_reasons)

    assert training_dataset_module._build_token_stats(
        [
            {"prompt": "alpha beta", "completion": "gamma delta"},
            {"prompt": "epsilon", "completion": "zeta eta theta"},
        ],
        "prompt_completion",
    ) == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 1.5,
        "prompt_tokens_p50": 1,
        "prompt_tokens_p95": 1,
        "prompt_tokens_max": 2,
        "completion_tokens_mean": 2.5,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 2,
        "completion_tokens_max": 3,
        "total_tokens_mean": 4.0,
        "total_tokens_p50": 4,
        "total_tokens_p95": 4,
        "total_tokens_max": 4,
    }


def test_build_quality_and_token_stats_caps_retained_examples_but_preserves_total_counts() -> None:
    repeated_sample = {"prompt": "same text", "completion": "same text"}

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [dict(repeated_sample) for _ in range(12)],
        "prompt_completion",
    )

    assert quality == {
        "duplicate_count": 11,
        "duplicate_sample_indices": list(range(1, 11)),
        "dirty_count": 12,
        "dirty_samples": [
            {"index": index, "reasons": ["duplicate_prompt_completion"]}
            for index in range(10)
        ],
    }
    assert token_stats["sample_count"] == 12
    assert token_stats["prompt_tokens_mean"] == 2.0
    assert token_stats["prompt_tokens_p95"] == 2
    assert token_stats["total_tokens_max"] == 4


def test_prompt_completion_dirty_sample_reasons_match_generic_quality_rules() -> None:
    samples = [
        {"prompt": "hello", "completion": "world"},
        {"prompt": "same text", "completion": " same text "},
        {"prompt": "bad\x00prompt", "completion": "clean"},
        {"prompt": "bad\x00same", "completion": "bad\x00same"},
    ]

    for sample in samples:
        assert training_dataset_module._prompt_completion_dirty_sample_reasons(
            sample
        ) == training_dataset_module._dirty_sample_reasons(sample)


def test_build_quality_and_token_stats_uses_prompt_completion_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generic_token_counter(sample: dict[str, object], format_name: str) -> tuple[int, int]:
        raise AssertionError(f"prompt_completion quality stats should use the direct fast path ({format_name=}, {sample=})")

    monkeypatch.setattr(training_dataset_module, "_sample_token_counts", fail_generic_token_counter)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "a b c", "completion": "d e"},
            {"prompt": "f", "completion": "g h i j"},
            {"prompt": "k l", "completion": "m"},
            {"prompt": "n o p q", "completion": "r s t"},
        ],
        "prompt_completion",
    )

    assert quality == {
        "duplicate_count": 0,
        "duplicate_sample_indices": [],
        "dirty_count": 0,
        "dirty_samples": [],
    }
    assert token_stats == {
        "estimator": "whitespace_v1",
        "sample_count": 4,
        "prompt_tokens_mean": 2.5,
        "prompt_tokens_p50": 2,
        "prompt_tokens_p95": 3,
        "prompt_tokens_max": 4,
        "completion_tokens_mean": 2.5,
        "completion_tokens_p50": 2,
        "completion_tokens_p95": 3,
        "completion_tokens_max": 4,
        "total_tokens_mean": 5.0,
        "total_tokens_p50": 5,
        "total_tokens_p95": 5,
        "total_tokens_max": 7,
    }

    monkeypatch.undo()
    assert training_dataset_module._build_quality_and_token_stats(
        [{"text": "alpha beta gamma"}, {"text": "delta"}],
        "text_completion",
    )[1] == {
        "estimator": "whitespace_v1",
        "sample_count": 2,
        "prompt_tokens_mean": 0.0,
        "prompt_tokens_p50": 0,
        "prompt_tokens_p95": 0,
        "prompt_tokens_max": 0,
        "completion_tokens_mean": 2.0,
        "completion_tokens_p50": 1,
        "completion_tokens_p95": 1,
        "completion_tokens_max": 3,
        "total_tokens_mean": 2.0,
        "total_tokens_p50": 1,
        "total_tokens_p95": 1,
        "total_tokens_max": 3,
    }


def test_build_quality_and_token_stats_uses_prompt_completion_duplicate_key_fast_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generic_digest(sample: dict[str, object]) -> bytes:
        raise AssertionError(f"normalized prompt_completion samples should not hash JSON digests ({sample=})")

    monkeypatch.setattr(training_dataset_module, "_canonical_sample_digest", fail_generic_digest)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "same text", "completion": "answer"},
            {"prompt": "same text", "completion": "answer"},
            {"prompt": "different", "completion": "answer"},
        ],
        "prompt_completion",
    )

    assert quality == {
        "duplicate_count": 1,
        "duplicate_sample_indices": [1],
        "dirty_count": 0,
        "dirty_samples": [],
    }
    assert token_stats["sample_count"] == 3


def test_build_quality_and_token_stats_falls_back_to_generic_digest_for_non_normalized_prompt_completion_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digested_samples: list[dict[str, object]] = []
    original_digest = training_dataset_module._canonical_sample_digest

    def tracking_digest(sample: dict[str, object]) -> bytes:
        digested_samples.append(sample)
        return original_digest(sample)

    monkeypatch.setattr(training_dataset_module, "_canonical_sample_digest", tracking_digest)

    quality, token_stats = training_dataset_module._build_quality_and_token_stats(
        [
            {"prompt": "same text", "completion": "answer", "metadata": "a"},
            {"prompt": "same text", "completion": "answer", "metadata": "b"},
        ],
        "prompt_completion",
    )

    assert digested_samples == [
        {"prompt": "same text", "completion": "answer", "metadata": "a"},
        {"prompt": "same text", "completion": "answer", "metadata": "b"},
    ]
    assert quality == {
        "duplicate_count": 0,
        "duplicate_sample_indices": [],
        "dirty_count": 0,
        "dirty_samples": [],
    }
    assert token_stats["sample_count"] == 2


def test_resolve_dataset_build_source_reuses_existing_package_sample_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized_samples = [{"text": "alpha beta"}]
    normalized_validation_samples = [{"text": "gamma delta"}]
    package_path = tmp_path / "existing-package"
    package_path.mkdir(parents=True, exist_ok=True)
    package = TrainingDatasetPackage(
        package_path=package_path,
        manifest_path=package_path / "manifest.json",
        samples_path=package_path / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="existing-package",
        format="text_completion",
        sample_count=1,
        version="1",
        normalized_samples=normalized_samples,
        normalized_validation_samples=normalized_validation_samples,
        validation_sample_count=1,
        response_only_supported=False,
    )

    monkeypatch.setattr(
        training_dataset_module,
        "load_training_dataset_package",
        lambda dataset_uri, sample_limit=0: package,
    )

    resolved = training_dataset_module._resolve_dataset_build_source(
        {"dataset_uri": str(tmp_path / "existing-package"), "template": "existing_package"},
        jobs_root=tmp_path / "jobs",
        hf_dataset_fetcher=None,
        sample_limit=0,
    )

    assert resolved["samples"] is normalized_samples
    assert resolved["validation_samples"] is normalized_validation_samples


def test_resolve_dataset_build_source_reuses_hf_package_sample_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized_samples = [
        {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}
    ]
    normalized_validation_samples = [
        {"messages": [{"role": "user", "content": "Bye"}, {"role": "assistant", "content": "Goodbye"}]}
    ]
    package = TrainingDatasetPackage(
        package_path=tmp_path / "hf-package",
        manifest_path=tmp_path / "hf-package" / "manifest.json",
        samples_path=tmp_path / "hf-package" / "samples.jsonl",
        schema_version="melix.training_dataset_package.v1",
        dataset_id="hf-package",
        format="chat_messages",
        sample_count=1,
        version="1",
        normalized_samples=normalized_samples,
        normalized_validation_samples=normalized_validation_samples,
        validation_sample_count=1,
        response_only_supported=True,
    )
    reference = HFDatasetReference(
        dataset_path="HuggingFaceH4/ultrachat_200k",
        dataset_name="default",
        dataset_revision="main",
        train_split="train",
        valid_split="validation",
        chat_feature="messages",
        prompt_feature="",
        completion_feature="",
        text_feature="",
    )
    resolved_package = ResolvedTrainingDatasetPackage(
        package=package,
        source_kind="hf_dataset",
        dataset_uri="hf://HuggingFaceH4/ultrachat_200k",
        materialized_package_path=package.package_path,
        cache_key="demo-key",
        cache_hit=True,
        hf_reference=reference,
    )

    monkeypatch.setattr(
        training_dataset_module,
        "resolve_training_dataset_package",
        lambda request_ext, jobs_root, hf_dataset_fetcher, sample_limit=0: resolved_package,
    )

    resolved = training_dataset_module._resolve_dataset_build_source(
        {"hf_dataset_path": "HuggingFaceH4/ultrachat_200k", "template": "source_schema"},
        jobs_root=tmp_path / "jobs",
        hf_dataset_fetcher=None,
        sample_limit=0,
    )

    assert resolved["samples"] is normalized_samples
    assert resolved["validation_samples"] is normalized_validation_samples
    assert resolved["hf_metadata"]["hf_valid_split"] == "validation"


def test_build_training_dataset_artifact_inspects_samples_once_for_quality_and_token_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingSequence:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self._rows = rows
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return iter(self._rows)

        def __len__(self) -> int:
            return len(self._rows)

        def __getitem__(self, index: int | slice) -> object:
            return self._rows[index]

        def __bool__(self) -> bool:
            return bool(self._rows)

    train_samples = CountingSequence(
        [
            {"prompt": "alpha beta", "completion": "gamma"},
            {"prompt": "delta", "completion": "delta"},
        ]
    )
    validation_samples = CountingSequence(
        [
            {"prompt": "alpha beta", "completion": "gamma"},
        ]
    )

    monkeypatch.setattr(
        training_dataset_module,
        "_resolve_dataset_build_source",
        lambda *args, **kwargs: {
            "dataset_id": "counted-source",
            "format": "prompt_completion",
            "version": "1",
            "source_kind": "local_path",
            "source_uri": "/tmp/counted-source.jsonl",
            "source_manifest_path": "",
            "source_samples_path": "/tmp/counted-source.jsonl",
            "samples": train_samples,
            "validation_samples": validation_samples,
            "response_only_supported": True,
            "conversion_template": "prompt_completion",
            "hf_metadata": {},
        },
    )

    built = build_training_dataset_artifact(
        {
            "inspect_only": "true",
            "preview_count": "2",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "inspect-once",
        source_model_id="melix-dev-text",
    )

    assert train_samples.iterations == 1
    assert validation_samples.iterations == 1
    assert built.manifest_payload["quality"] == {
        "duplicate_count": 1,
        "duplicate_sample_indices": [2],
        "dirty_count": 1,
        "dirty_samples": [
            {"index": 1, "reasons": ["duplicate_prompt_completion"]},
        ],
    }
    assert built.manifest_payload["token_stats"]["estimator"] == "whitespace_v1"
    assert built.manifest_payload["token_stats"]["sample_count"] == 3
    assert built.manifest_payload["token_stats"]["prompt_tokens_max"] == 2
    assert built.manifest_payload["token_stats"]["completion_tokens_max"] == 1
    assert built.manifest_payload["token_stats"]["total_tokens_max"] == 3



def test_build_training_dataset_artifact_streams_local_jsonl_without_bulk_row_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "alpaca-streamed.jsonl",
        [
            {
                "instruction": "Translate to French.",
                "input": "Hello world",
                "output": "Bonjour le monde",
            },
            {
                "instruction": "Summarize.",
                "input": "A short article",
                "output": "A concise summary",
            },
        ],
    )

    def fail_read_rows(path: Path, *, sample_limit: int) -> list[dict[str, object]]:
        raise AssertionError(f"bulk row reader should not be used for {path} ({sample_limit=})")

    def fail_convert_rows(rows: list[dict[str, object]], template: str) -> tuple[str, list[dict[str, object]]]:
        raise AssertionError(f"bulk row converter should not be used for {template}")

    monkeypatch.setattr(training_dataset_module, "_read_local_jsonl_rows", fail_read_rows)
    monkeypatch.setattr(training_dataset_module, "_convert_local_rows", fail_convert_rows)

    built = build_training_dataset_artifact(
        {
            "dataset_uri": str(dataset_path),
            "template": "auto",
            "preview_count": "1",
        },
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "streamed-package",
        source_model_id="melix-dev-text",
    )

    assert built.manifest_payload["source_kind"] == "local_path"
    assert built.manifest_payload["conversion_template"] == "alpaca"
    assert built.manifest_payload["sample_count"] == 2
    assert built.manifest_payload["preview_samples"] == [
        {
            "prompt": "Translate to French.\n\nInput:\nHello world",
            "completion": "Bonjour le monde",
        }
    ]
    assert (built.package_path / "samples.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "Translate to French.\\n\\nInput:\\nHello world", "completion": "Bonjour le monde"}\n'
        '{"prompt": "Summarize.\\n\\nInput:\\nA short article", "completion": "A concise summary"}\n'
    )


def test_local_jsonl_helpers_cover_streaming_and_single_row_conversions(tmp_path: Path) -> None:
    dataset_path = _write_jsonl(
        tmp_path / "helpers.jsonl",
        [
            {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]},
            {"prompt": "Question", "completion": "Answer"},
        ],
    )

    assert training_dataset_module._read_local_jsonl_rows(dataset_path, sample_limit=0) == [
        {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]},
        {"prompt": "Question", "completion": "Answer"},
    ]
    assert training_dataset_module._convert_local_row(
        {"messages": [{"role": "user", "content": "Hi"}]},
        "chat_messages",
    ) == {"messages": [{"role": "user", "content": "Hi"}]}
    assert training_dataset_module._convert_local_row(
        {"prompt": "Question", "completion": "Answer"},
        "prompt_completion",
    ) == {"prompt": "Question", "completion": "Answer"}

    empty_jsonl = tmp_path / "empty-stream.jsonl"
    empty_jsonl.write_text("\n", encoding="utf-8")
    with pytest.raises(ModelOperationError) as empty_exc:
        training_dataset_module._resolve_local_training_samples(
            empty_jsonl,
            template="auto",
            sample_limit=0,
        )
    assert empty_exc.value.code == "invalid_dataset_source"
