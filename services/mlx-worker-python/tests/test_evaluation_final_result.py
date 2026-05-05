from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from worker.model_ops.errors import ModelOperationError
from worker.productization import evaluation_final_result as evaluation_final_result_module
from worker.productization.evaluation_final_result import (
    EvaluationFieldMapping,
    HFEvaluationDatasetSource,
    EvaluationMaterializationRequest,
    EvaluationProfileDefinition,
    _local_source_metadata,
    extract_final_result,
    materialize_hf_evaluation_dataset,
    materialize_local_evaluation_dataset,
    score_final_result,
)


def test_write_jsonl_rows_streams_each_row_without_joining_the_full_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "streamed.jsonl"
    writes: list[str] = []

    class _Writer:
        def write(self, chunk: str) -> int:
            writes.append(chunk)
            return len(chunk)

        def __enter__(self) -> _Writer:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_open(self: Path, mode: str = "r", *args: object, **kwargs: object) -> _Writer:
        assert self == output_path
        assert mode == "w"
        assert kwargs.get("encoding") == "utf-8"
        return _Writer()

    monkeypatch.setattr(Path, "open", fake_open)

    evaluation_final_result_module._write_jsonl_rows(
        output_path,
        [
            {"id": "sample-1", "target": "Paris"},
            {"id": "sample-2", "target": "Rome"},
        ],
    )

    assert writes == [
        '{"id": "sample-1", "target": "Paris"}',
        "\n",
        '{"id": "sample-2", "target": "Rome"}',
        "\n",
    ]


def test_write_jsonl_rows_preserves_blank_line_contract_for_empty_inputs(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.jsonl"

    evaluation_final_result_module._write_jsonl_rows(output_path, [])

    assert output_path.read_text(encoding="utf-8") == "\n"


def test_extract_final_result_prefers_last_fenced_json_block() -> None:
    outcome = extract_final_result(
        raw_response=(
            "Reasoning...\n"
            "```json\n"
            "{\"answer\":\"wrong\"}\n"
            "```\n"
            "Final payload follows.\n"
            "```json\n"
            "{\"answer\":\"Paris\"}\n"
            "```"
        ),
        result_kind="json",
        extraction_mode="heuristic_final",
    )

    assert outcome.extraction_status == "extracted"
    assert json.loads(outcome.extracted_result) == {"answer": "Paris"}
    assert outcome.failure_reason == ""


def test_extract_final_result_marks_ambiguous_text_answer_prefixes_as_failure() -> None:
    outcome = extract_final_result(
        raw_response="Answer: Paris\nAnswer: Lyon",
        result_kind="text",
        extraction_mode="heuristic_final",
    )

    assert outcome.extraction_status == "ambiguous_extraction"
    assert outcome.extracted_result == ""
    assert outcome.failure_reason == "multiple_answer_prefix_candidates"


def test_score_final_result_validates_json_schema_and_ignores_default_paths() -> None:
    score = score_final_result(
        extracted_result=json.dumps(
            {
                "verdict": "supported",
                "evidence": ["citation-a"],
                "confidence": 0.88,
            }
        ),
        target=json.dumps(
            {
                "verdict": "supported",
                "evidence": ["citation-b"],
            }
        ),
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="json",
            extraction_mode="heuristic_final",
            scoring_mode="json_field_match",
            threshold=1.0,
            output_schema={
                "type": "object",
                "required": ["verdict"],
                "properties": {
                    "verdict": {"type": "string"},
                    "evidence": {"type": "array"},
                    "confidence": {"type": "number"},
                },
            },
            ignored_paths=("confidence",),
        ),
    )

    assert score.validation_status == "validated"
    assert score.failure_reason == ""
    assert score.typed_score == 1.0


def test_score_final_result_rejects_invalid_json_shape_before_scoring() -> None:
    score = score_final_result(
        extracted_result=json.dumps([{"label": "A"}]),
        target=json.dumps({"label": "A"}),
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="json",
            extraction_mode="strict_full_response",
            scoring_mode="json_field_match",
            threshold=1.0,
            output_schema={
                "type": "object",
                "required": ["label"],
                "properties": {"label": {"type": "string"}},
            },
        ),
    )

    assert score.validation_status == "schema_failed"
    assert score.failure_reason == "root_type_mismatch"
    assert score.typed_score == 0.0


def test_materialize_local_evaluation_dataset_requires_explicit_mapping_for_jsonl(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(json.dumps({"prompt": "Question", "answer": "Paris"}) + "\n", encoding="utf-8")

    with pytest.raises(ModelOperationError) as excinfo:
        materialize_local_evaluation_dataset(
            request=EvaluationMaterializationRequest(
                source_kind="jsonl",
                source_path=source_path,
                profile=EvaluationProfileDefinition(
                    profile_type="final_result",
                    result_kind="text",
                    extraction_mode="heuristic_final",
                    scoring_mode="normalized_exact_match",
                    threshold=1.0,
                ),
                field_mapping=EvaluationFieldMapping(),
            ),
            cache_root=tmp_path / "cache",
        )

    assert excinfo.value.code == "invalid_evaluation_source"


def test_materialize_local_evaluation_dataset_builds_final_result_package_from_jsonl_with_blank_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(
        "\n".join(
            [
                json.dumps({"meta": {"sys": "Return the final answer only."}, "payload": {"question": "Capital of France?", "target": "Paris"}, "sample": {"id": "capital-1"}}),
                "",
                "  ",
                json.dumps({"meta": {"sys": "Return the final answer only."}, "payload": {"question": "Capital of Italy?", "target": "Rome"}, "sample": {"id": "capital-2"}}),
                "",
            ]
        ),
        encoding="utf-8",
    )

    def _forbid_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == source_path.resolve():
            raise AssertionError("streaming JSONL loader should not call Path.read_text")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", _forbid_read_text)

    materialized = materialize_local_evaluation_dataset(
        request=EvaluationMaterializationRequest(
            source_kind="jsonl",
            source_path=source_path,
            profile=EvaluationProfileDefinition(
                profile_type="final_result",
                result_kind="text",
                extraction_mode="heuristic_final",
                scoring_mode="normalized_exact_match",
                threshold=1.0,
            ),
            field_mapping=EvaluationFieldMapping(
                system_path="meta.sys",
                input_text_path="payload.question",
                target_path="payload.target",
                sample_id_path="sample.id",
            ),
            dataset_id="capital.dev.v1",
            suite_id="capital",
        ),
        cache_root=tmp_path / "cache",
    )

    manifest = json.loads((materialized.package_path / "manifest.json").read_text(encoding="utf-8"))
    samples = [
        json.loads(line)
        for line in (materialized.package_path / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert manifest["source_kind"] == "jsonl"
    assert [sample["id"] for sample in samples] == ["capital-1", "capital-2"]
    assert samples[1]["input"]["text"] == "Capital of Italy?"
    assert samples[1]["target"] == "Rome"


def test_materialize_local_evaluation_dataset_streams_serialized_samples_into_jsonl_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(
        "\n".join(
            [
                json.dumps({"meta": {"sys": "Return the final answer only."}, "payload": {"question": "Capital of France?", "target": "Paris"}, "sample": {"id": "capital-1"}}),
                json.dumps({"meta": {"sys": "Return the final answer only."}, "payload": {"question": "Capital of Italy?", "target": "Rome"}, "sample": {"id": "capital-2"}}),
                "",
            ]
        ),
        encoding="utf-8",
    )
    original_write_jsonl_rows = evaluation_final_result_module._write_jsonl_rows
    captured_rows: list[dict[str, object]] = []

    def _assert_streaming_rows(path: Path, rows: object) -> None:
        assert "samples.jsonl" in path.name
        assert not isinstance(rows, list)
        assert iter(rows) is rows
        captured_rows.extend(list(rows))
        assert list(rows) == []
        original_write_jsonl_rows(path, captured_rows)

    monkeypatch.setattr(evaluation_final_result_module, "_write_jsonl_rows", _assert_streaming_rows)

    materialized = materialize_local_evaluation_dataset(
        request=EvaluationMaterializationRequest(
            source_kind="jsonl",
            source_path=source_path,
            profile=EvaluationProfileDefinition(
                profile_type="final_result",
                result_kind="text",
                extraction_mode="heuristic_final",
                scoring_mode="normalized_exact_match",
                threshold=1.0,
            ),
            field_mapping=EvaluationFieldMapping(
                system_path="meta.sys",
                input_text_path="payload.question",
                target_path="payload.target",
                sample_id_path="sample.id",
            ),
            dataset_id="capital.dev.v1",
            suite_id="capital",
        ),
        cache_root=tmp_path / "cache",
    )

    manifest = json.loads((materialized.package_path / "manifest.json").read_text(encoding="utf-8"))
    samples = [
        json.loads(line)
        for line in (materialized.package_path / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert [row["id"] for row in captured_rows] == ["capital-1", "capital-2"]
    assert manifest["sample_count"] == 2
    assert [sample["id"] for sample in samples] == ["capital-1", "capital-2"]


def test_materialize_local_evaluation_dataset_does_not_leave_partial_cache_after_streaming_failure(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(
        "\n".join(
            [
                json.dumps({"meta": {"sys": "Return the final answer only."}, "payload": {"question": "Capital of France?", "target": "Paris"}, "sample": {"id": "capital-1"}}),
                json.dumps({"meta": {"sys": "Return the final answer only."}, "payload": {"question": "Capital of Italy?"}, "sample": {"id": "capital-2"}}),
                "",
            ]
        ),
        encoding="utf-8",
    )

    request = EvaluationMaterializationRequest(
        source_kind="jsonl",
        source_path=source_path,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="meta.sys",
            input_text_path="payload.question",
            target_path="payload.target",
            sample_id_path="sample.id",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
    )
    cache_root = tmp_path / "cache"

    with pytest.raises(ModelOperationError) as excinfo:
        materialize_local_evaluation_dataset(request=request, cache_root=cache_root)

    assert excinfo.value.code == "invalid_evaluation_source"
    assert cache_root.exists() is False or list(cache_root.iterdir()) == []


def test_write_materialized_package_preserves_existing_published_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    package_path = cache_root / "demo-cache-key"
    package_path.mkdir()
    manifest_path = package_path / "manifest.json"
    samples_path = package_path / "samples.jsonl"
    manifest_path.write_text(json.dumps({"sample_count": 1}, indent=2) + "\n", encoding="utf-8")
    samples_path.write_text(json.dumps({"id": "existing-sample"}) + "\n", encoding="utf-8")

    evaluation_final_result_module._write_materialized_package(
        cache_root=cache_root,
        package_path=package_path,
        manifest_payload={"sample_count": 2},
        serialized_samples=iter([{"id": "new-sample"}]),
    )

    assert json.loads(manifest_path.read_text(encoding="utf-8"))["sample_count"] == 1
    assert samples_path.read_text(encoding="utf-8").strip() == json.dumps({"id": "existing-sample"})
    assert list(cache_root.glob(".demo-cache-key.tmp-*")) == []



def test_write_materialized_package_replaces_incomplete_existing_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    package_path = cache_root / "demo-cache-key"
    package_path.mkdir()
    (package_path / "samples.jsonl").write_text(json.dumps({"id": "stale-sample"}) + "\n", encoding="utf-8")

    evaluation_final_result_module._write_materialized_package(
        cache_root=cache_root,
        package_path=package_path,
        manifest_payload={"sample_count": 1},
        serialized_samples=iter([{"id": "fresh-sample"}]),
    )

    assert json.loads((package_path / "manifest.json").read_text(encoding="utf-8"))["sample_count"] == 1
    assert (package_path / "samples.jsonl").read_text(encoding="utf-8").strip() == json.dumps({"id": "fresh-sample"})
    assert list(cache_root.glob(".demo-cache-key.tmp-*")) == []



def test_local_source_metadata_reports_same_sha256_and_size_as_path_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.jsonl"
    payload = (
        json.dumps({"prompt": "Capital of France?", "answer": "Paris"})
        + "\n"
        + json.dumps({"prompt": "Capital of Italy?", "answer": "Rome"})
        + "\n"
    )
    source_path.write_text(payload, encoding="utf-8")

    def _forbid_read_bytes(self: Path) -> bytes:
        if self.resolve() == source_path.resolve():
            raise AssertionError("streaming metadata hashing should not call Path.read_bytes")
        return original_read_bytes(self)

    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", _forbid_read_bytes)

    metadata = _local_source_metadata(source_kind="jsonl", source_path=source_path)
    expected_bytes = original_read_bytes(source_path)

    assert metadata == {
        "source_kind": "jsonl",
        "source_path": str(source_path.resolve()),
        "source_sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "source_size_bytes": len(expected_bytes),
    }


def test_materialize_local_evaluation_dataset_rejects_non_object_jsonl_rows_without_read_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.jsonl"
    source_path.write_text(json.dumps(["not", "an", "object"]) + "\n", encoding="utf-8")

    def _forbid_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == source_path.resolve():
            raise AssertionError("streaming JSONL loader should not call Path.read_text")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", _forbid_read_text)

    with pytest.raises(ModelOperationError) as excinfo:
        materialize_local_evaluation_dataset(
            request=EvaluationMaterializationRequest(
                source_kind="jsonl",
                source_path=source_path,
                profile=EvaluationProfileDefinition(
                    profile_type="final_result",
                    result_kind="text",
                    extraction_mode="heuristic_final",
                    scoring_mode="normalized_exact_match",
                    threshold=1.0,
                ),
                field_mapping=EvaluationFieldMapping(
                    input_text_path="prompt",
                    target_path="answer",
                ),
            ),
            cache_root=tmp_path / "cache",
        )

    assert excinfo.value.code == "invalid_evaluation_source"
    assert excinfo.value.message == "JSONL evaluation rows must be JSON objects."


def test_materialize_local_evaluation_dataset_builds_final_result_package_from_csv(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.csv"
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sys", "question", "gold"])
        writer.writeheader()
        writer.writerow(
            {
                "sys": "Return the final answer only.",
                "question": "Capital of France?",
                "gold": "Paris",
            }
        )

    materialized = materialize_local_evaluation_dataset(
        request=EvaluationMaterializationRequest(
            source_kind="csv",
            source_path=source_path,
            profile=EvaluationProfileDefinition(
                profile_type="final_result",
                result_kind="text",
                extraction_mode="heuristic_final",
                scoring_mode="normalized_exact_match",
                threshold=1.0,
            ),
            field_mapping=EvaluationFieldMapping(
                system_path="sys",
                input_text_path="question",
                target_path="gold",
            ),
            dataset_id="capital.dev.v1",
            suite_id="capital",
        ),
        cache_root=tmp_path / "cache",
    )

    manifest = json.loads((materialized.package_path / "manifest.json").read_text(encoding="utf-8"))
    sample = json.loads((materialized.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert manifest["profile_type"] == "final_result"
    assert manifest["result_kind"] == "text"
    assert manifest["source_kind"] == "csv"
    assert sample["system"] == "Return the final answer only."
    assert sample["input"]["text"] == "Capital of France?"
    assert sample["target"] == "Paris"


def test_materialize_local_evaluation_dataset_invalidates_cache_when_local_source_changes(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.csv"
    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sys", "question", "gold"])
        writer.writeheader()
        writer.writerow(
            {
                "sys": "Return the final answer only.",
                "question": "Capital of France?",
                "gold": "Paris",
            }
        )

    request = EvaluationMaterializationRequest(
        source_kind="csv",
        source_path=source_path,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="sys",
            input_text_path="question",
            target_path="gold",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
    )

    first = materialize_local_evaluation_dataset(
        request=request,
        cache_root=tmp_path / "cache",
    )

    with source_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sys", "question", "gold"])
        writer.writeheader()
        writer.writerow(
            {
                "sys": "Return the final answer only.",
                "question": "Capital of Italy?",
                "gold": "Rome",
            }
        )

    second = materialize_local_evaluation_dataset(
        request=request,
        cache_root=tmp_path / "cache",
    )

    sample = json.loads((second.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert second.cache_key != first.cache_key
    assert second.package_path != first.package_path
    assert sample["input"]["text"] == "Capital of Italy?"
    assert sample["target"] == "Rome"


def test_materialize_hf_evaluation_dataset_invalidates_cache_when_rows_change(
    tmp_path: Path,
) -> None:
    class ChangingFetcher:
        def __init__(self) -> None:
            self._rows_calls = 0

        def __call__(self, endpoint: str, params: dict[str, str]) -> dict[str, object]:
            if endpoint != "rows":
                raise AssertionError(f"Unexpected endpoint: {endpoint}")
            self._rows_calls += 1
            if self._rows_calls == 1:
                row = {
                    "system_prompt": "Return only the final answer.",
                    "question": "Capital of France?",
                    "gold_answer": "Paris",
                    "sample_key": "capital-1",
                }
            else:
                row = {
                    "system_prompt": "Return only the final answer.",
                    "question": "Capital of Italy?",
                    "gold_answer": "Rome",
                    "sample_key": "capital-1",
                }
            return {"rows": [{"row": row}]}

    fetcher = ChangingFetcher()
    source = HFEvaluationDatasetSource(
        dataset_path="melix/demo-hf",
        dataset_name="default",
        dataset_revision="main",
        split="train",
    )

    first = materialize_hf_evaluation_dataset(
        source=source,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="system_prompt",
            input_text_path="question",
            target_path="gold_answer",
            sample_id_path="sample_key",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
        cache_root=tmp_path / "cache",
        fetch_json=fetcher,
    )

    second = materialize_hf_evaluation_dataset(
        source=source,
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            system_path="system_prompt",
            input_text_path="question",
            target_path="gold_answer",
            sample_id_path="sample_key",
        ),
        dataset_id="capital.dev.v1",
        suite_id="capital",
        cache_root=tmp_path / "cache",
        fetch_json=fetcher,
    )

    sample = json.loads((second.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert second.cache_key != first.cache_key
    assert second.package_path != first.package_path
    assert sample["input"]["text"] == "Capital of Italy?"
    assert sample["target"] == "Rome"


def test_hf_evaluation_materialization_prefers_local_cache_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    cache_repo = home / ".cache" / "huggingface" / "hub" / "datasets--org--cached"
    snapshot = cache_repo / "snapshots" / "abc123"
    data_dir = snapshot / "data"
    data_dir.mkdir(parents=True)
    (cache_repo / "refs").mkdir()
    (cache_repo / "refs" / "main").write_text("abc123", encoding="utf-8")
    (data_dir / "train-00000-of-00001.jsonl").write_text(
        json.dumps(
            {
                "question": "Capital of France?",
                "gold": "Paris",
                "id": "sample-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))

    def fail_fetcher(endpoint: str, params: dict[str, str]) -> dict[str, object]:
        raise AssertionError(f"unexpected remote fetch {endpoint} {params}")

    materialized = materialize_hf_evaluation_dataset(
        source=HFEvaluationDatasetSource(
            dataset_path="org/cached",
            dataset_revision="main",
            split="train",
        ),
        profile=EvaluationProfileDefinition(
            profile_type="final_result",
            result_kind="text",
            extraction_mode="heuristic_final",
            scoring_mode="normalized_exact_match",
            threshold=1.0,
        ),
        field_mapping=EvaluationFieldMapping(
            input_text_path="question",
            target_path="gold",
            sample_id_path="id",
        ),
        dataset_id="cached.dev.v1",
        suite_id="cached",
        cache_root=tmp_path / "cache",
        fetch_json=fail_fetcher,
    )

    manifest = json.loads((materialized.package_path / "manifest.json").read_text(encoding="utf-8"))
    sample = json.loads((materialized.package_path / "samples.jsonl").read_text(encoding="utf-8").strip())

    assert manifest["source_kind"] == "hf_cache_snapshot"
    assert manifest["hf_snapshot_id"] == "abc123"
    assert manifest["hf_snapshot_path"] == str(snapshot.resolve())
    assert sample["id"] == "sample-1"
    assert sample["input"]["text"] == "Capital of France?"
    assert sample["target"] == "Paris"
