from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import types
from typing import Any

import pytest

from worker.model_ops.errors import ModelOperationError
from worker.productization import synthetic_dataset_generation as synthetic_module
from worker.productization.synthetic_dataset_generation import (
    SyntheticColumnSpec,
    SyntheticDatasetRequest,
    SyntheticModelConfig,
    SyntheticModelProvider,
    SyntheticSeedSource,
    generate_synthetic_dataset_package,
)


@dataclass
class _FakeDesignerState:
    rows: list[dict[str, Any]]
    instances: list["_FakeDataDesigner"] | None = None

    def __post_init__(self) -> None:
        if self.instances is None:
            self.instances = []


_fake_state = _FakeDesignerState(rows=[])


@dataclass(frozen=True)
class _FakeModelProvider:
    name: str
    endpoint: str
    provider_type: str
    api_key: str
    extra_headers: dict[str, str]


@dataclass(frozen=True)
class _FakeInferenceParams:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "kwargs", kwargs)


@dataclass(frozen=True)
class _FakeModelConfig:
    alias: str
    model: str
    provider: str
    inference_parameters: _FakeInferenceParams


@dataclass(frozen=True)
class _FakeColumnConfig:
    name: str
    column_type: str
    params: dict[str, Any]


class _FakeColumnType:
    SAMPLER = "sampler"
    LLM_TEXT = "llm_text"
    LLM_STRUCTURED = "llm_structured"
    LLM_JUDGE = "llm_judge"
    EXPRESSION = "expression"


class _FakeBuilder:
    def __init__(self, *, model_configs: list[_FakeModelConfig]) -> None:
        self.model_configs = model_configs
        self.columns: list[_FakeColumnConfig] = []
        self.seed_source: Any = None
        self.artifact_path = Path()

    def add_column(self, column_config: _FakeColumnConfig) -> None:
        self.columns.append(column_config)

    def with_seed_dataset(self, seed_source: Any) -> None:
        self.seed_source = seed_source

    def write_config(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "alias": model.alias,
                            "model": model.model,
                            "provider": model.provider,
                            "inference_parameters": model.inference_parameters.kwargs,
                        }
                        for model in self.model_configs
                    ],
                    "columns": [
                        {
                            "name": column.name,
                            "column_type": column.column_type,
                            **column.params,
                        }
                        for column in self.columns
                    ],
                    "column_names": [column.name for column in self.columns],
                    "seed_source": str(self.seed_source or ""),
                    "api_key": "should-not-persist",
                    "Authorization": "Bearer should-not-persist",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


class _FakeCreationResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def export(self, path: Path, *, format: str) -> None:
        assert format == "jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in self.rows),
            encoding="utf-8",
        )


class _FakeLocalFileSeedSource:
    def __init__(self, *, path: str) -> None:
        self.path = path

    @classmethod
    def from_path(cls, path: Path) -> _FakeLocalFileSeedSource:
        return cls(path=str(path))

    def __str__(self) -> str:
        return self.path


def _fake_get_column_config_from_kwargs(
    *,
    name: str,
    column_type: str,
    **params: Any,
) -> _FakeColumnConfig:
    return _FakeColumnConfig(name=name, column_type=column_type, params=params)


class _FakeDataDesigner:
    state = _fake_state

    def __init__(self, *, model_providers: list[_FakeModelProvider], artifact_path: str) -> None:
        self.model_providers = model_providers
        self.artifact_path = artifact_path
        self.rows = list(type(self).state.rows)
        self.preview_calls: list[tuple[_FakeBuilder, int]] = []
        self.create_calls: list[tuple[_FakeBuilder, int, str, bool]] = []
        type(self).state.instances.append(self)

    def preview(self, builder: _FakeBuilder, *, num_records: int) -> list[dict[str, Any]]:
        self.preview_calls.append((builder, num_records))
        return self.rows[:num_records]

    def create(
        self,
        builder: _FakeBuilder,
        *,
        num_records: int,
        dataset_name: str,
        resume: bool,
    ) -> _FakeCreationResult:
        self.create_calls.append((builder, num_records, dataset_name, resume))
        return _FakeCreationResult(self.rows[:num_records])


@pytest.fixture(autouse=True)
def _fake_datadesigner_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_state.instances = []
    _fake_state.rows = [
        {"prompt": "p1", "completion": "c1"},
        {"prompt": "p2", "completion": "c2"},
        {"prompt": "p3", "completion": "c3"},
        {"prompt": "p4", "completion": "c4"},
    ]

    package = types.ModuleType("data_designer")
    interface = types.ModuleType("data_designer.interface")
    config = types.ModuleType("data_designer.config")
    builder = types.ModuleType("data_designer.config.config_builder")
    models = types.ModuleType("data_designer.config.models")
    column_types = types.ModuleType("data_designer.config.column_types")
    seed_source = types.ModuleType("data_designer.config.seed_source")

    interface.DataDesigner = _FakeDataDesigner
    builder.DataDesignerConfigBuilder = _FakeBuilder
    models.ModelProvider = _FakeModelProvider
    models.ModelConfig = _FakeModelConfig
    models.ChatCompletionInferenceParams = _FakeInferenceParams
    column_types.DataDesignerColumnType = _FakeColumnType
    column_types.get_column_config_from_kwargs = _fake_get_column_config_from_kwargs
    seed_source.LocalFileSeedSource = _FakeLocalFileSeedSource

    monkeypatch.setitem(sys.modules, "data_designer", package)
    monkeypatch.setitem(sys.modules, "data_designer.interface", interface)
    monkeypatch.setitem(sys.modules, "data_designer.config", config)
    monkeypatch.setitem(sys.modules, "data_designer.config.config_builder", builder)
    monkeypatch.setitem(sys.modules, "data_designer.config.models", models)
    monkeypatch.setitem(sys.modules, "data_designer.config.column_types", column_types)
    monkeypatch.setitem(sys.modules, "data_designer.config.seed_source", seed_source)


def _request(**overrides: Any) -> SyntheticDatasetRequest:
    defaults: dict[str, Any] = {
        "dataset_id": "support.sft.v1",
        "dataset_name": "support-sft",
        "mode": "create",
        "num_records": 4,
        "output_kind": "training",
        "output_format": "prompt_completion",
        "model_provider": SyntheticModelProvider(
            endpoint="http://127.0.0.1:12434/v1",
            api_key="secret-key",
            extra_headers={"Authorization": "Bearer secret-token", "X-Trace": "ok"},
        ),
        "models": (
            SyntheticModelConfig(
                alias="generator",
                model="melix-dev-text",
                temperature=0.2,
                max_tokens=128,
                extra_body={"api_key": "nested-secret", "safe": True},
            ),
        ),
        "columns": (
            SyntheticColumnSpec(
                name="prompt",
                column_type="llm_text",
                params={"prompt": "write prompt"},
            ),
            SyntheticColumnSpec(
                name="completion",
                column_type="llm_text",
                params={"prompt": "write completion"},
            ),
        ),
        "job_id": "job-1",
        "preview_count": 2,
    }
    defaults.update(overrides)
    return SyntheticDatasetRequest(**defaults)


def test_create_training_package_writes_melix_contract_and_redacts_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEMO_TELEMETRY_ENABLED", "true")
    progress_events: list[tuple[str, float]] = []

    result = generate_synthetic_dataset_package(
        _request(validation_ratio=0.25),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
        progress=lambda stage, fraction: progress_events.append((stage, fraction)),
    )

    assert result.row_count == 3
    assert result.validation_row_count == 1
    assert result.preview_only is False
    assert (tmp_path / "out" / "samples.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "p2", "completion": "c2"}\n'
        '{"prompt": "p3", "completion": "c3"}\n'
        '{"prompt": "p4", "completion": "c4"}\n'
    )
    assert (tmp_path / "out" / "valid.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "p1", "completion": "c1"}\n'
    )

    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.training_dataset_package.v1"
    assert manifest["source_kind"] == "datadesigner"
    assert manifest["operation"] == "generate_synthetic_dataset"
    assert manifest["format"] == "prompt_completion"
    assert manifest["sample_count"] == 3
    assert manifest["validation_sample_count"] == 1
    assert manifest["validation_strategy"] == "deterministic_hash_ratio"
    assert manifest["build_ready"] is True
    assert manifest["datadesigner"]["provider"]["api_key"] == "[REDACTED]"
    assert manifest["datadesigner"]["provider"]["extra_headers"]["Authorization"] == "[REDACTED]"
    assert manifest["datadesigner"]["models"][0]["extra_body"]["api_key"] == "[REDACTED]"
    assert "secret-key" not in json.dumps(manifest)
    assert "secret-token" not in json.dumps(manifest)
    assert "nested-secret" not in json.dumps(manifest)
    assert set(manifest["timing"]) >= {
        "datadesigner_config_build_ms",
        "datadesigner_generate_ms",
        "datadesigner_export_ms",
        "melix_normalize_ms",
        "melix_package_write_ms",
        "total_elapsed_ms",
    }

    config = json.loads((tmp_path / "out" / "data_designer" / "config.json").read_text(encoding="utf-8"))
    assert config["api_key"] == "[REDACTED]"
    assert config["Authorization"] == "[REDACTED]"
    assert _fake_state.instances[0].model_providers[0].api_key == "secret-key"
    assert _fake_state.instances[0].create_calls[0][3] is False
    assert progress_events[0][0] == "load_datadesigner"
    assert progress_events[-1] == ("complete", 1.0)
    assert synthetic_module.os.environ["NEMO_TELEMETRY_ENABLED"] == "true"


def test_create_training_package_removes_stale_valid_jsonl_without_validation(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "valid.jsonl").write_text("stale\n", encoding="utf-8")

    generate_synthetic_dataset_package(
        _request(num_records=1),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert not (tmp_path / "out" / "valid.jsonl").exists()


def test_training_validation_split_uses_stable_hash_instead_of_tail_rows(tmp_path: Path) -> None:
    generate_synthetic_dataset_package(
        _request(validation_ratio=0.5),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert (tmp_path / "out" / "samples.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "p3", "completion": "c3"}\n'
        '{"prompt": "p4", "completion": "c4"}\n'
    )
    assert (tmp_path / "out" / "valid.jsonl").read_text(encoding="utf-8") == (
        '{"prompt": "p1", "completion": "c1"}\n'
        '{"prompt": "p2", "completion": "c2"}\n'
    )


def test_preview_raw_jsonl_writes_inspection_manifest_without_build_ready_package(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "manifest.json").write_text("stale\n", encoding="utf-8")
    (tmp_path / "out" / "samples.jsonl").write_text("stale\n", encoding="utf-8")
    (tmp_path / "out" / "valid.jsonl").write_text("stale\n", encoding="utf-8")

    result = generate_synthetic_dataset_package(
        _request(mode="preview", output_kind="raw_jsonl", output_format="jsonl", num_records=2),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert result.preview_only is True
    assert result.output_path == tmp_path / "out" / "data_designer" / "generated.jsonl"
    assert not (tmp_path / "out" / "manifest.json").exists()
    assert not (tmp_path / "out" / "samples.jsonl").exists()
    assert not (tmp_path / "out" / "valid.jsonl").exists()
    manifest = json.loads((tmp_path / "out" / "synthetic_dataset.preview.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.synthetic_dataset_preview.v1"
    assert manifest["build_ready"] is False
    assert manifest["preview_only"] is True
    assert manifest["sample_count"] == 2
    assert "datadesigner_export_ms" not in manifest["timing"]
    assert _fake_state.instances[0].preview_calls[0][1] == 2


def test_create_evaluation_final_result_package_validates_json_targets(tmp_path: Path) -> None:
    source_rows = [
        {"sample_id": "one", "system": "sys", "input": "extract", "target": {"label": "a"}},
        {"sample_id": "two", "system": "", "input": "extract b", "target": '{"label":"b"}'},
    ]
    _fake_state.rows = source_rows

    result = generate_synthetic_dataset_package(
        _request(
            output_kind="evaluation_final_result",
            output_format="json",
            num_records=2,
        ),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "eval",
    )

    assert result.row_count == 2
    manifest = json.loads((tmp_path / "eval" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.evaluation_dataset_package.v2"
    assert manifest["profile_type"] == "final_result"
    assert manifest["result_kind"] == "json"
    assert manifest["field_mapping"]["input_text_path"] == "input"
    assert (tmp_path / "eval" / "samples.jsonl").read_text(encoding="utf-8") == (
        '{"id": "one", "system": "sys", "input": {"text": "extract"}, "target": {"label": "a"}}\n'
        '{"id": "two", "system": "", "input": {"text": "extract b"}, "target": {"label": "b"}}\n'
    )
    assert source_rows[1]["target"] == '{"label":"b"}'


def test_create_evaluation_text_package_and_resume_mode(tmp_path: Path) -> None:
    _fake_state.rows = [
        {"sample_id": "one", "system": "", "input": "classify", "target": "positive"},
    ]

    result = generate_synthetic_dataset_package(
        _request(
            output_kind="evaluation_final_result",
            output_format="text",
            num_records=1,
            data_designer_resume_mode="always",
            disable_data_designer_telemetry=False,
        ),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "eval",
    )

    assert result.row_count == 1
    manifest = json.loads((tmp_path / "eval" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["result_kind"] == "text"
    assert manifest["datadesigner"]["telemetry_disabled"] is False
    assert _fake_state.instances[0].create_calls[0][3] is True


def test_create_raw_jsonl_inspection_from_create_mode(tmp_path: Path) -> None:
    result = generate_synthetic_dataset_package(
        _request(output_kind="raw_jsonl", output_format="jsonl", num_records=2),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert result.preview_only is True
    manifest = json.loads((tmp_path / "out" / "synthetic_dataset.inspect.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.synthetic_dataset_inspection.v1"
    assert manifest["sample_count"] == 2
    assert manifest["build_ready"] is False


def test_invalid_evaluation_json_target_fails_before_package_write(tmp_path: Path) -> None:
    _fake_state.rows = [
        {"sample_id": "one", "system": "", "input": "extract", "target": "not json"},
    ]

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(
                output_kind="evaluation_final_result",
                output_format="json",
                num_records=1,
            ),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "eval",
        )

    assert error.value.code == "invalid_synthetic_output_row"
    assert not (tmp_path / "eval" / "manifest.json").exists()


def test_invalid_evaluation_json_target_type_fails_before_package_write(tmp_path: Path) -> None:
    _fake_state.rows = [
        {"sample_id": "one", "system": "", "input": "extract", "target": 42},
    ]

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(
                output_kind="evaluation_final_result",
                output_format="json",
                num_records=1,
            ),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "eval",
        )

    assert error.value.code == "invalid_synthetic_output_row"


def test_invalid_evaluation_text_target_is_rejected(tmp_path: Path) -> None:
    _fake_state.rows = [
        {"sample_id": "one", "system": "", "input": "classify", "target": ""},
    ]

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(
                output_kind="evaluation_final_result",
                output_format="text",
                num_records=1,
            ),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "eval",
        )

    assert error.value.code == "invalid_synthetic_output_row"


def test_invalid_training_row_is_reported_as_synthetic_output_error(tmp_path: Path) -> None:
    _fake_state.rows = [{"prompt": "", "completion": "answer"}]

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(num_records=1),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "invalid_synthetic_output_row"


def test_missing_datadesigner_dependency_reports_optional_extra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in list(sys.modules):
        if module_name == "data_designer" or module_name.startswith("data_designer."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "missing_optional_dependency"
    assert error.value.details["extra"] == "synthetic-data"


def test_unsupported_column_is_rejected_before_import(tmp_path: Path) -> None:
    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(
                columns=(
                    SyntheticColumnSpec(
                        name="unsafe",
                        column_type="validation",  # type: ignore[arg-type]
                    ),
                )
            ),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "unsupported_synthetic_column"
    assert error.value.details["column_type"] == "validation"


def test_stages_training_package_seed_rows(tmp_path: Path) -> None:
    seed_package = tmp_path / "seed-package"
    seed_package.mkdir()
    (seed_package / "samples.jsonl").write_text(
        '{"prompt": "seed-p", "completion": "seed-c"}\n',
        encoding="utf-8",
    )
    (seed_package / "valid.jsonl").write_text(
        '{"prompt": "seed-v", "completion": "seed-vc"}\n',
        encoding="utf-8",
    )

    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="training_package",
                source_path=seed_package,
            )
        ),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    staged = tmp_path / "jobs" / "synthetic-data" / "job-1" / "seed" / "training-package-seed.jsonl"
    assert staged.read_text(encoding="utf-8") == (
        '{"prompt": "seed-p", "completion": "seed-c"}\n'
        '{"prompt": "seed-v", "completion": "seed-vc"}\n'
    )
    assert str(_fake_state.instances[0].create_calls[0][0].seed_source) == str(staged)


def test_stages_evaluation_package_seed_rows(tmp_path: Path) -> None:
    seed_package = tmp_path / "eval-seed"
    seed_package.mkdir()
    (seed_package / "samples.jsonl").write_text(
        '{"id": "e1", "system": "sys", "input": {"text": "q"}, "target": {"a": 1}}\n',
        encoding="utf-8",
    )

    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="evaluation_package",
                source_path=seed_package,
            )
        ),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    staged = tmp_path / "jobs" / "synthetic-data" / "job-1" / "seed" / "evaluation-package-seed.jsonl"
    assert staged.read_text(encoding="utf-8") == (
        '{"system": "sys", "input": "q", "target": {"a": 1}, "sample_id": "e1"}\n'
    )


def test_stages_local_seed_file_and_directory(tmp_path: Path) -> None:
    local_jsonl = tmp_path / "source.jsonl"
    local_jsonl.write_text('{"topic": "a"}\n', encoding="utf-8")

    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="local_jsonl",
                source_path=local_jsonl,
            )
        ),
        jobs_root=tmp_path / "jobs-file",
        output_dir=tmp_path / "out-file",
    )
    assert (tmp_path / "jobs-file" / "synthetic-data" / "job-1" / "seed" / "source.jsonl").is_file()

    local_dir = tmp_path / "snapshot"
    local_dir.mkdir()
    (local_dir / "rows.jsonl").write_text('{"topic": "b"}\n', encoding="utf-8")
    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="managed_hf_snapshot",
                source_path=local_dir,
            )
        ),
        jobs_root=tmp_path / "jobs-dir",
        output_dir=tmp_path / "out-dir",
    )
    assert (tmp_path / "jobs-dir" / "synthetic-data" / "job-1" / "seed" / "snapshot" / "rows.jsonl").is_file()

    (local_dir / "extra.jsonl").write_text('{"topic": "c"}\n', encoding="utf-8")
    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="managed_hf_snapshot",
                source_path=local_dir,
            )
        ),
        jobs_root=tmp_path / "jobs-dir",
        output_dir=tmp_path / "out-dir-second",
    )
    assert (tmp_path / "jobs-dir" / "synthetic-data" / "job-1" / "seed" / "snapshot" / "extra.jsonl").is_file()


def test_replaces_stale_seed_file_when_source_changes_to_directory(tmp_path: Path) -> None:
    source_file = tmp_path / "seed"
    source_file.write_text('{"topic": "file"}\n', encoding="utf-8")
    jobs_root = tmp_path / "jobs"

    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="local_jsonl",
                source_path=source_file,
            )
        ),
        jobs_root=jobs_root,
        output_dir=tmp_path / "out-file",
    )
    staged_path = jobs_root / "synthetic-data" / "job-1" / "seed" / "seed"
    assert staged_path.is_file()

    source_file.unlink()
    source_file.mkdir()
    (source_file / "rows.jsonl").write_text('{"topic": "dir"}\n', encoding="utf-8")
    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="managed_hf_snapshot",
                source_path=source_file,
            )
        ),
        jobs_root=jobs_root,
        output_dir=tmp_path / "out-dir",
    )

    assert (staged_path / "rows.jsonl").is_file()


def test_replaces_stale_seed_directory_when_source_changes_to_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "seed"
    source_dir.mkdir()
    (source_dir / "rows.jsonl").write_text('{"topic": "dir"}\n', encoding="utf-8")
    jobs_root = tmp_path / "jobs"

    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="managed_hf_snapshot",
                source_path=source_dir,
            )
        ),
        jobs_root=jobs_root,
        output_dir=tmp_path / "out-dir",
    )
    staged_path = jobs_root / "synthetic-data" / "job-1" / "seed" / "seed"
    assert (staged_path / "rows.jsonl").is_file()

    source_dir.rename(tmp_path / "old-seed")
    source_file = tmp_path / "seed"
    source_file.write_text('{"topic": "file"}\n', encoding="utf-8")
    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="local_jsonl",
                source_path=source_file,
            )
        ),
        jobs_root=jobs_root,
        output_dir=tmp_path / "out-file",
    )

    assert staged_path.is_file()
    assert staged_path.read_text(encoding="utf-8") == '{"topic": "file"}\n'


def test_missing_seed_source_fails(tmp_path: Path) -> None:
    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(
                seed_source=SyntheticSeedSource(
                    source_kind="local_jsonl",
                    source_path=tmp_path / "missing.jsonl",
                )
            ),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "invalid_synthetic_seed_source"


def test_missing_seed_package_samples_are_rejected(tmp_path: Path) -> None:
    training_seed = tmp_path / "training-seed"
    training_seed.mkdir()
    with pytest.raises(ModelOperationError) as training_error:
        generate_synthetic_dataset_package(
            _request(
                seed_source=SyntheticSeedSource(
                    source_kind="training_package",
                    source_path=training_seed,
                )
            ),
            jobs_root=tmp_path / "jobs-training",
            output_dir=tmp_path / "out-training",
        )

    assert training_error.value.code == "invalid_synthetic_seed_source"

    evaluation_seed = tmp_path / "evaluation-seed"
    evaluation_seed.mkdir()
    with pytest.raises(ModelOperationError) as evaluation_error:
        generate_synthetic_dataset_package(
            _request(
                seed_source=SyntheticSeedSource(
                    source_kind="evaluation_package",
                    source_path=evaluation_seed,
                )
            ),
            jobs_root=tmp_path / "jobs-evaluation",
            output_dir=tmp_path / "out-evaluation",
        )

    assert evaluation_error.value.code == "invalid_synthetic_seed_source"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("dataset_id", "", "invalid_synthetic_dataset_request"),
        ("dataset_name", "", "invalid_synthetic_dataset_request"),
        ("mode", "bad", "invalid_synthetic_dataset_request"),
        ("num_records", 0, "invalid_synthetic_dataset_request"),
        ("output_kind", "bad", "unsupported_synthetic_output"),
        ("output_format", "bad", "unsupported_synthetic_output"),
        ("model_provider", SyntheticModelProvider(endpoint=""), "invalid_synthetic_dataset_request"),
        ("models", (), "invalid_synthetic_dataset_request"),
        (
            "models",
            (
                SyntheticModelConfig(alias="", model="a"),
            ),
            "invalid_synthetic_dataset_request",
        ),
        (
            "models",
            (
                SyntheticModelConfig(alias="same", model="a"),
                SyntheticModelConfig(alias="same", model="b"),
            ),
            "invalid_synthetic_dataset_request",
        ),
        ("columns", (), "invalid_synthetic_dataset_request"),
        (
            "columns",
            (SyntheticColumnSpec(name="", column_type="llm_text"),),
            "invalid_synthetic_dataset_request",
        ),
        (
            "columns",
            (
                SyntheticColumnSpec(name="prompt", column_type="llm_text"),
                SyntheticColumnSpec(name=" prompt ", column_type="expression"),
            ),
            "invalid_synthetic_dataset_request",
        ),
        ("validation_ratio", 1.0, "invalid_synthetic_dataset_request"),
        ("preview_count", 0, "invalid_synthetic_dataset_request"),
    ],
)
def test_request_validation_errors(
    tmp_path: Path,
    field: str,
    value: Any,
    expected_code: str,
) -> None:
    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(**{field: value}),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == expected_code


def test_duplicate_column_validation_reports_column_name(tmp_path: Path) -> None:
    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(
                columns=(
                    SyntheticColumnSpec(name="prompt", column_type="llm_text"),
                    SyntheticColumnSpec(name="prompt", column_type="expression"),
                )
            ),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "invalid_synthetic_dataset_request"
    assert error.value.details["column_name"] == "prompt"


def test_raw_jsonl_requires_jsonl_output_format(tmp_path: Path) -> None:
    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(output_kind="raw_jsonl", output_format="text"),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "unsupported_synthetic_output"


def test_uses_fallback_column_api_when_config_factory_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    column_types = sys.modules["data_designer.config.column_types"]
    monkeypatch.delattr(column_types, "get_column_config_from_kwargs", raising=False)

    class FallbackBuilder(_FakeBuilder):
        def add_column(
            self,
            column_config: _FakeColumnConfig | None = None,
            *,
            name: str | None = None,
            column_type: str | None = None,
            **params: Any,
        ) -> None:
            assert column_config is None
            assert name is not None
            assert column_type is not None
            self.columns.append(_FakeColumnConfig(name=name, column_type=column_type, params=params))

    sys.modules["data_designer.config.config_builder"].DataDesignerConfigBuilder = FallbackBuilder

    generate_synthetic_dataset_package(
        _request(),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    builder = _fake_state.instances[0].create_calls[0][0]
    assert builder.columns[0].name == "prompt"


def test_preview_result_accepts_tuple_dataframe_like_and_wrappers(tmp_path: Path) -> None:
    class TuplePreviewDesigner(_FakeDataDesigner):
        def preview(self, builder: _FakeBuilder, *, num_records: int) -> tuple[dict[str, str], ...]:
            return ({"prompt": "tuple", "completion": "row"},)

    sys.modules["data_designer.interface"].DataDesigner = TuplePreviewDesigner
    result = generate_synthetic_dataset_package(
        _request(mode="preview", num_records=1),
        jobs_root=tmp_path / "jobs-tuple",
        output_dir=tmp_path / "out-tuple",
    )
    assert result.row_count == 1
    assert not (tmp_path / "out-tuple" / "samples.jsonl").exists()

    class FrameLike:
        def to_dict(self, *, orient: str) -> list[dict[str, str]]:
            assert orient == "records"
            return [{"prompt": "frame", "completion": "row"}]

    class DataWrapper:
        data = FrameLike()

    class FramePreviewDesigner(_FakeDataDesigner):
        def preview(self, builder: _FakeBuilder, *, num_records: int) -> DataWrapper:
            return DataWrapper()

    sys.modules["data_designer.interface"].DataDesigner = FramePreviewDesigner
    result = generate_synthetic_dataset_package(
        _request(mode="preview", num_records=1),
        jobs_root=tmp_path / "jobs-frame",
        output_dir=tmp_path / "out-frame",
    )
    assert result.row_count == 1

    class ResultsWrapper:
        preview_results = [{"prompt": "wrapped", "completion": "row"}]

    class ResultsPreviewDesigner(_FakeDataDesigner):
        def preview(self, builder: _FakeBuilder, *, num_records: int) -> ResultsWrapper:
            return ResultsWrapper()

    sys.modules["data_designer.interface"].DataDesigner = ResultsPreviewDesigner
    result = generate_synthetic_dataset_package(
        _request(mode="preview", num_records=1),
        jobs_root=tmp_path / "jobs-results",
        output_dir=tmp_path / "out-results",
    )
    assert result.row_count == 1


def test_invalid_preview_shape_is_reported(tmp_path: Path) -> None:
    class BadPreviewDesigner(_FakeDataDesigner):
        def preview(self, builder: _FakeBuilder, *, num_records: int) -> object:
            return object()

    sys.modules["data_designer.interface"].DataDesigner = BadPreviewDesigner

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(mode="preview", num_records=1),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "invalid_datadesigner_preview"
    assert error.value.details["preview_result_type"] == "object"


def test_empty_jsonl_writer_creates_empty_file(tmp_path: Path) -> None:
    output = tmp_path / "empty.jsonl"

    synthetic_module._write_jsonl_rows(output, [])

    assert output.is_file()
    assert output.read_text(encoding="utf-8") == ""


def test_config_write_failure_is_reported(tmp_path: Path) -> None:
    class BadBuilder(_FakeBuilder):
        def write_config(self, path: Path) -> None:
            raise RuntimeError("boom")

    sys.modules["data_designer.config.config_builder"].DataDesignerConfigBuilder = BadBuilder

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "synthetic_config_write_failed"


def test_create_rejects_invalid_export_jsonl(tmp_path: Path) -> None:
    class BadCreationResult:
        def export(self, path: Path, *, format: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ok": true}\n[]\n', encoding="utf-8")

    class BadExportDesigner(_FakeDataDesigner):
        def create(
            self,
            builder: _FakeBuilder,
            *,
            num_records: int,
            dataset_name: str,
            resume: bool,
        ) -> BadCreationResult:
            return BadCreationResult()

    sys.modules["data_designer.interface"].DataDesigner = BadExportDesigner

    with pytest.raises(ModelOperationError) as error:
        generate_synthetic_dataset_package(
            _request(),
            jobs_root=tmp_path / "jobs",
            output_dir=tmp_path / "out",
        )

    assert error.value.code == "invalid_datadesigner_export"


def test_default_job_id_is_sanitized_and_invalid_config_redaction_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(synthetic_module.time, "time", lambda: 10.0)

    class InvalidJSONBuilder(_FakeBuilder):
        def write_config(self, path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not-json\n", encoding="utf-8")

    sys.modules["data_designer.config.config_builder"].DataDesignerConfigBuilder = InvalidJSONBuilder
    result = generate_synthetic_dataset_package(
        _request(dataset_id="bad id/../x", job_id=""),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert result.row_count == 4
    assert (tmp_path / "jobs" / "synthetic-data" / "bad-id-..-x-10000").is_dir()
    assert (tmp_path / "out" / "data_designer" / "config.json").read_text(encoding="utf-8") == "{not-json\n"


def test_redaction_handles_lists_and_scalar_values(tmp_path: Path) -> None:
    result = generate_synthetic_dataset_package(
        _request(
            models=(
                SyntheticModelConfig(
                    alias="generator",
                    model="melix-dev-text",
                    extra_body={
                        "items": [
                            {"token": "list-secret"},
                            "literal",
                        ],
                    },
                ),
            )
        ),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert result.manifest_payload["datadesigner"]["models"][0]["extra_body"]["items"] == [
        {"token": "[REDACTED]"},
        "literal",
    ]


def test_column_type_falls_back_to_string_when_enum_name_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyColumnType:
        pass

    sys.modules["data_designer.config.column_types"].DataDesignerColumnType = EmptyColumnType

    generate_synthetic_dataset_package(
        _request(),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    builder = _fake_state.instances[0].create_calls[0][0]
    assert builder.columns[0].column_type == "llm_text"


def test_local_seed_source_can_fallback_to_plain_path_when_local_seed_class_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "data_designer.config.seed_source", raising=False)
    local_jsonl = tmp_path / "source.jsonl"
    local_jsonl.write_text('{"topic": "a"}\n', encoding="utf-8")

    generate_synthetic_dataset_package(
        _request(
            seed_source=SyntheticSeedSource(
                source_kind="local_jsonl",
                source_path=local_jsonl,
            )
        ),
        jobs_root=tmp_path / "jobs",
        output_dir=tmp_path / "out",
    )

    assert isinstance(_fake_state.instances[0].create_calls[0][0].seed_source, str)
