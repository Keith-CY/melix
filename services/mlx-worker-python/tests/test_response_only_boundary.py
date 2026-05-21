"""Cross-family parity tests for the response-only boundary helper.

Milestone #43 Phase 2: prove that `compute_response_only_boundary` produces
identical offsets to MLX-LM's `ChatDataset.process()` across the four supported
chat-template families, plus the existing `melix-dev-dataset.v1` fixture.

The test depends on a locally cached tokenizer (the Qwen3.5-0.8B-OptiQ-4bit
tokenizer.json that PR #45 verification already pulled). When the cache is
missing — e.g., fresh CI without the model cache — the cross-family tests skip
rather than fail, matching the `MELIX_PHASE8_REAL_SMALL_MODEL_E2E` gating
pattern.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from worker.model_ops.response_only_boundary import (
    ResponseOnlyBoundary,
    aggregate_response_only_boundaries,
    compute_response_only_boundary,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_ROOT = (
    _REPO_ROOT
    / "services"
    / "mlx-worker-python"
    / "fixtures"
    / "training"
)
_TEMPLATE_MATRIX_DIR = _FIXTURE_ROOT / "chat-template-matrix.v1"
_DEV_DATASET_DIR = _FIXTURE_ROOT / "melix-dev-dataset.v1"
_TOKENIZER_CACHE_ENV = "MELIX_CHAT_TEMPLATE_TOKENIZER_PATH"
_DEFAULT_TOKENIZER_GLOB = (
    Path.home()
    / ".cache"
    / "huggingface"
    / "hub"
    / "models--mlx-community--Qwen3.5-0.8B-OptiQ-4bit"
    / "snapshots"
)


def _resolve_tokenizer_dir() -> Path | None:
    override = os.environ.get(_TOKENIZER_CACHE_ENV, "").strip()
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_dir() else None
    if not _DEFAULT_TOKENIZER_GLOB.exists():
        return None
    snapshots = sorted(_DEFAULT_TOKENIZER_GLOB.iterdir())
    for snapshot in snapshots:
        if (snapshot / "tokenizer.json").exists():
            return snapshot
    return None


def _load_tokenizer() -> Any:
    tokenizer_dir = _resolve_tokenizer_dir()
    if tokenizer_dir is None:
        pytest.skip(
            f"No cached chat-template tokenizer available. Set "
            f"{_TOKENIZER_CACHE_ENV} or prime the Qwen3.5-0.8B-OptiQ-4bit cache."
        )
    try:
        from transformers import AutoTokenizer
    except ModuleNotFoundError:  # pragma: no cover - dependency gate
        pytest.skip("transformers is not available in the current runtime.")
    return AutoTokenizer.from_pretrained(str(tokenizer_dir), use_fast=True)


def _load_template_matrix() -> dict[str, Any]:
    path = _TEMPLATE_MATRIX_DIR / "templates.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_matrix_samples() -> list[dict[str, Any]]:
    path = _TEMPLATE_MATRIX_DIR / "samples.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_dev_samples() -> list[dict[str, Any]]:
    path = _DEV_DATASET_DIR / "samples.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _mlx_chat_dataset_offset(tokenizer: Any, sample: dict[str, Any]) -> tuple[list[int], int]:
    """Reference computation — bit-exact to what MLX-LM uses at training time."""

    from mlx_lm.tuner.datasets import ChatDataset  # type: ignore[import-not-found]

    dataset = ChatDataset([sample], tokenizer=tokenizer, mask_prompt=True)
    return dataset.process(sample)


_FAMILIES = ("chatml", "llama3", "mistral_inst", "gemma_model")


@pytest.mark.parametrize("family", _FAMILIES)
def test_response_only_boundary_matches_mlx_lm_on_each_family(family: str) -> None:
    """Melix helper output must equal MLX-LM's ChatDataset.process offset.

    The mistral_inst template folds system prompts into the first user turn via
    a Jinja namespace var; the offset math still works because both
    ``compute_response_only_boundary`` and MLX-LM's ChatDataset drive the same
    template, so the parity assertion covers the merged case too.
    """

    tokenizer = _load_tokenizer()
    templates = _load_template_matrix()["templates"]
    assert family in templates, f"fixture templates missing {family}"
    tokenizer.chat_template = templates[family]["chat_template"]
    samples = _load_matrix_samples()

    for sample in samples:
        messages = sample["messages"]
        helper = compute_response_only_boundary(messages, tokenizer)
        tokens_ref, offset_ref = _mlx_chat_dataset_offset(tokenizer, sample)

        assert helper.total_tokens == len(tokens_ref), (
            f"[{family} / {sample['id']}] total tokens drift: helper={helper.total_tokens} ref={len(tokens_ref)}"
        )
        assert helper.assistant_offset == offset_ref, (
            f"[{family} / {sample['id']}] assistant offset drift: helper={helper.assistant_offset} ref={offset_ref}"
        )
        assert helper.response_tokens == helper.total_tokens - helper.assistant_offset


def test_response_only_boundary_forwards_tools_to_tokenizer() -> None:
    """Regression gate: tools must be forwarded on both apply_chat_template calls.

    Uses ChatML-style rendering with a minimal tool schema. If the helper drops
    ``tools`` it renders fewer tokens than MLX-LM and the parity assertion
    against ``ChatDataset.process`` (which DOES forward tools) will fail.
    """

    tokenizer = _load_tokenizer()
    templates = _load_template_matrix()["templates"]
    # Use a template that references tools in its Jinja so a missing tools arg
    # would surface as a divergence. ChatML renders tools inside the system
    # prefix when provided.
    tokenizer.chat_template = (
        "{% if tools %}<|im_start|>system\nYou have tools: "
        "{% for tool in tools %}{{ tool['name'] }}{% if not loop.last %}, {% endif %}{% endfor %}"
        "<|im_end|>\n{% endif %}"
        "{% for message in messages %}<|im_start|>{{ message['role'] }}\n"
        "{{ message['content'] }}<|im_end|>\n{% endfor %}"
        "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
    )
    tools = [{"name": "search_docs"}, {"name": "run_tests"}]
    sample = {
        "messages": [
            {"role": "user", "content": "Find the release notes."},
            {"role": "assistant", "content": "Sure, looking now."},
        ],
        "tools": tools,
    }

    helper = compute_response_only_boundary(sample["messages"], tokenizer, tools=tools)
    tokens_ref, offset_ref = _mlx_chat_dataset_offset(tokenizer, sample)
    assert helper.total_tokens == len(tokens_ref)
    assert helper.assistant_offset == offset_ref


def test_response_only_boundary_handles_non_assistant_last_message() -> None:
    """Mirror MLX-LM's add_generation_prompt=False branch for non-assistant-last.

    MLX-LM's ChatDataset sets ``add_generation_prompt = messages[-1].role == 'assistant'``.
    For an assistant-trailing sample both Melix and MLX-LM drop the last message and
    add the generation prompt; for a non-assistant-trailing sample both keep all
    messages and do not add the prompt. The helper must handle both branches.
    """

    tokenizer = _load_tokenizer()
    templates = _load_template_matrix()["templates"]
    tokenizer.chat_template = templates["chatml"]["chat_template"]

    # Sample ending with a user message — mlx-lm sets add_generation_prompt=False
    # and the offset equals the full token length (no response tokens).
    sample = {
        "messages": [
            {"role": "user", "content": "Hello."},
            {"role": "assistant", "content": "Hi."},
            {"role": "user", "content": "Again?"},
        ],
    }
    helper = compute_response_only_boundary(sample["messages"], tokenizer)
    tokens_ref, offset_ref = _mlx_chat_dataset_offset(tokenizer, sample)
    assert helper.total_tokens == len(tokens_ref)
    assert helper.assistant_offset == offset_ref


def test_response_only_boundary_matches_mlx_lm_on_dev_dataset() -> None:
    """No regression on the fixture used by phase8 acceptance."""

    tokenizer = _load_tokenizer()
    samples = _load_dev_samples()
    assert samples, "dev dataset must have at least one sample"

    for sample in samples:
        messages = sample["messages"]
        helper = compute_response_only_boundary(messages, tokenizer)
        tokens_ref, offset_ref = _mlx_chat_dataset_offset(tokenizer, sample)
        assert helper.total_tokens == len(tokens_ref)
        assert helper.assistant_offset == offset_ref


def test_response_only_boundary_rejects_empty_messages() -> None:
    tokenizer = _load_tokenizer()
    with pytest.raises(ValueError):
        compute_response_only_boundary([], tokenizer)


def test_probe_summarizes_train_set_without_rereading_disk() -> None:
    """_probe_response_only_boundary must iterate the loaded train_set.

    Guards the gemini-review refactor: the probe should call `train_set.process`
    (the exact path MLX-LM trains against) and skip jsonl re-reads.
    """

    from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module
    from worker.model_ops.training_config import LoRATrainingConfig

    class _FakeTrainSet:
        def __init__(self, samples: list[tuple[list[int], int]]) -> None:
            self._samples = samples
            self.process_calls = 0
            self.getitem_calls = 0

        def __len__(self) -> int:
            return len(self._samples)

        def __getitem__(self, index: int) -> tuple[list[int], int]:
            self.getitem_calls += 1
            return self._samples[index]

        def process(self, sample: tuple[list[int], int]) -> tuple[list[int], int]:
            self.process_calls += 1
            return sample

    class _DummyConfig:
        response_only = True
        max_seq_length = 5

    class _DummyRequest:
        config = _DummyConfig()
        dataset_format = "chat_messages"
        normalized_dataset_dir = Path("/non/existent/never/read")

    train_set = _FakeTrainSet(
        [
            ([0, 1, 2, 3, 4, 5], 3),
            ([0, 1, 2, 3], 2),
            ([0, 1, 2, 3, 4, 5, 6, 7], 4),
        ]
    )
    aggregate = mlx_lm_runner_module._probe_response_only_boundary(_DummyRequest(), train_set)

    assert aggregate.sample_count == 3
    assert aggregate.boundary_min == 2
    assert aggregate.boundary_max == 4
    assert aggregate.boundary_mean == pytest.approx((3 + 2 + 4) / 3)
    assert aggregate.response_tokens_min == 2
    assert aggregate.response_tokens_max == 4
    assert aggregate.response_tokens_mean == pytest.approx(3)
    assert aggregate.trainable_response_tokens_min == 1
    assert aggregate.trainable_response_tokens_max == 2
    assert aggregate.trainable_response_tokens_mean == pytest.approx(5 / 3)
    assert aggregate.trainable_response_token_count == 5
    assert aggregate.truncated_response_sample_count == 2
    assert aggregate.fully_truncated_response_sample_count == 0
    assert train_set.process_calls == 3, "probe must call train_set.process for each sample"
    # normalized_dataset_dir points to a non-existent path. If the probe re-read
    # disk, the test would fail — proving the disk re-read is gone.


def test_probe_returns_empty_when_response_only_is_disabled() -> None:
    from worker.model_ops import mlx_lm_runner as mlx_lm_runner_module

    class _DummyConfig:
        response_only = False

    class _DummyRequest:
        config = _DummyConfig()
        dataset_format = "chat_messages"
        normalized_dataset_dir = Path("/non/existent")

    class _FakeTrainSet:
        def __len__(self) -> int:
            return 5

        def __getitem__(self, index: int) -> Any:
            raise AssertionError("probe should short-circuit before touching the dataset")

        def process(self, sample: Any) -> Any:
            raise AssertionError("probe should short-circuit before touching the dataset")

    aggregate = mlx_lm_runner_module._probe_response_only_boundary(_DummyRequest(), _FakeTrainSet())
    assert aggregate.sample_count == 0


def test_aggregate_response_only_boundaries_handles_empty_and_full() -> None:
    empty = aggregate_response_only_boundaries([])
    assert empty.sample_count == 0
    assert empty.boundary_min == 0
    assert empty.boundary_max == 0
    assert empty.boundary_mean == 0.0
    assert empty.to_manifest_fields() == {
        "response_only_boundary_sample_count": 0,
        "response_only_boundary_min": 0,
        "response_only_boundary_max": 0,
        "response_only_boundary_mean": 0.0,
        "response_only_response_tokens_min": 0,
        "response_only_response_tokens_max": 0,
        "response_only_response_tokens_mean": 0.0,
        "response_only_trainable_response_tokens_min": 0,
        "response_only_trainable_response_tokens_max": 0,
        "response_only_trainable_response_tokens_mean": 0.0,
        "response_only_trainable_response_token_count": 0,
        "response_only_truncated_response_sample_count": 0,
        "response_only_fully_truncated_response_sample_count": 0,
    }

    tokenizer = _load_tokenizer()
    templates = _load_template_matrix()["templates"]
    tokenizer.chat_template = templates["chatml"]["chat_template"]
    samples = _load_matrix_samples()
    boundaries = [
        compute_response_only_boundary(sample["messages"], tokenizer)
        for sample in samples
    ]
    agg = aggregate_response_only_boundaries(boundaries)
    offsets = [b.assistant_offset for b in boundaries]
    assert agg.sample_count == len(samples)
    assert agg.boundary_min == min(offsets)
    assert agg.boundary_max == max(offsets)
    assert agg.boundary_mean == pytest.approx(sum(offsets) / len(offsets))
    assert agg.trainable_response_token_count == sum(b.response_tokens for b in boundaries)
    fields = agg.to_manifest_fields()
    assert set(fields.keys()) == {
        "response_only_boundary_sample_count",
        "response_only_boundary_min",
        "response_only_boundary_max",
        "response_only_boundary_mean",
        "response_only_response_tokens_min",
        "response_only_response_tokens_max",
        "response_only_response_tokens_mean",
        "response_only_trainable_response_tokens_min",
        "response_only_trainable_response_tokens_max",
        "response_only_trainable_response_tokens_mean",
        "response_only_trainable_response_token_count",
        "response_only_truncated_response_sample_count",
        "response_only_fully_truncated_response_sample_count",
    }


def test_response_only_boundary_records_are_slotted() -> None:
    boundary = ResponseOnlyBoundary(assistant_offset=8, total_tokens=10)
    aggregate = aggregate_response_only_boundaries([boundary])
    over_offset_aggregate = aggregate_response_only_boundaries(
        [ResponseOnlyBoundary(assistant_offset=12, total_tokens=10)]
    )

    assert not hasattr(boundary, "__dict__")
    assert not hasattr(aggregate, "__dict__")
    assert boundary.response_tokens == 2
    assert aggregate.trainable_response_token_count == 2
    assert over_offset_aggregate.response_tokens_max == 0
    assert over_offset_aggregate.trainable_response_token_count == 0


def test_aggregate_response_only_boundaries_marks_truncated_labels() -> None:
    boundaries = [
        ResponseOnlyBoundary(assistant_offset=8, total_tokens=10),
        ResponseOnlyBoundary(assistant_offset=12, total_tokens=16),
        ResponseOnlyBoundary(assistant_offset=20, total_tokens=18),
        ResponseOnlyBoundary(assistant_offset=2, total_tokens=7),
    ]

    agg = aggregate_response_only_boundaries(boundaries, max_seq_length=8)

    assert agg.sample_count == 4
    assert agg.boundary_min == 2
    assert agg.boundary_max == 20
    assert agg.response_tokens_min == 0
    assert agg.response_tokens_max == 5
    assert agg.response_tokens_mean == pytest.approx(2.75)
    assert agg.trainable_response_tokens_min == 0
    assert agg.trainable_response_tokens_max == 5
    assert agg.trainable_response_tokens_mean == pytest.approx(1.25)
    assert agg.trainable_response_token_count == 5
    assert agg.truncated_response_sample_count == 2
    assert agg.fully_truncated_response_sample_count == 2


def test_aggregate_response_only_boundaries_without_limit_updates_running_bounds() -> None:
    boundaries = [
        ResponseOnlyBoundary(assistant_offset=8, total_tokens=10),
        ResponseOnlyBoundary(assistant_offset=4, total_tokens=12),
        ResponseOnlyBoundary(assistant_offset=16, total_tokens=18),
        ResponseOnlyBoundary(assistant_offset=20, total_tokens=18),
    ]

    agg = aggregate_response_only_boundaries(boundaries, max_seq_length=None)

    assert agg.sample_count == 4
    assert agg.boundary_min == 4
    assert agg.boundary_max == 20
    assert agg.response_tokens_min == 0
    assert agg.response_tokens_max == 8
    assert agg.trainable_response_tokens_min == 0
    assert agg.trainable_response_tokens_max == 8
    assert agg.trainable_response_token_count == 12
    assert agg.truncated_response_sample_count == 0
    assert agg.fully_truncated_response_sample_count == 0
