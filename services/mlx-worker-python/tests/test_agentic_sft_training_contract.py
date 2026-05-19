from __future__ import annotations

from dataclasses import replace

import pytest

from packages.protocol.python.worker.v1 import common_pb2

from worker.model_ops import lora_training_pipeline as lora_training_pipeline_module
from worker.model_ops import training_config as training_config_module
from worker.model_ops.errors import ModelOperationError


def test_agentic_sft_training_contract_is_explicit_and_trace_bound() -> None:
    text_model = common_pb2.ModelSpec(
        model_id="plain-text",
        model_path="models/plain-llama",
        model_kind="text",
        revision="dev",
        max_context=2048,
        ext={"text_family_id": "llama"},
    )
    agentic_config = training_config_module.normalize_training_config(
        source_model=text_model,
        ext={"training_mode": "lora", "training_objective": "agentic_sft"},
        dataset_format="agentic_tool_trace",
        response_only_supported=True,
        sample_count=2,
    )
    assert agentic_config.training_objective == "agentic_sft"
    assert agentic_config.dataset_contract == "agentic_tool_trace"
    assert agentic_config.response_only is True
    assert agentic_config.mask_prompt is True

    lora_training_pipeline_module._validate_alignment_inputs(
        config=agentic_config,
        samples=[{"trace_id": "trace-1", "turns": [], "final_answer": "done"}],
    )
    with pytest.raises(ModelOperationError) as contract_error:
        lora_training_pipeline_module._validate_alignment_inputs(
            config=replace(agentic_config, dataset_contract="sft"),
            samples=[{"trace_id": "trace-1", "turns": [], "final_answer": "done"}],
        )
    assert contract_error.value.code == "invalid_agentic_sft_dataset"
    assert contract_error.value.details["required_dataset_contract"] == "agentic_tool_trace"

    with pytest.raises(ModelOperationError) as sample_error:
        lora_training_pipeline_module._validate_alignment_inputs(
            config=agentic_config,
            samples=[{"trace_id": "trace-1"}],
        )
    assert sample_error.value.code == "invalid_agentic_sft_dataset"
    assert sample_error.value.details["sample_index"] == "0"
    assert sample_error.value.details["missing_fields"] == "turns,final_answer"

    with pytest.raises(Exception) as objective_error:
        training_config_module.normalize_training_config(
            source_model=text_model,
            ext={"training_mode": "lora", "training_objective": "agentic_sft"},
            dataset_format="chat_messages",
            response_only_supported=True,
            sample_count=1,
        )
    assert objective_error.value.code == "invalid_training_objective"
    assert objective_error.value.details["required_training_objective"] == (
        "supervised_finetuning"
    )


def test_non_sft_training_mode_contracts_remain_unchanged() -> None:
    preference_contract = training_config_module._resolve_training_mode_contract(
        "dpo",
        "preference_pair",
    )
    assert preference_contract["training_objective"] == "preference"
    assert preference_contract["dataset_contract"] == "preference_pair"
    assert training_config_module._resolve_training_mode_contract(
        "grpo",
        "prompt_candidate",
    )["training_objective"] == "alignment_rl"
    assert training_config_module._resolve_training_mode_contract(
        "rlhf",
        "reward_scored",
    )["dataset_contract"] == "reward_scored"
    assert training_config_module._resolve_training_mode_contract(
        "cpt",
        "text_completion",
    )["training_objective"] == "continual_pretraining"
