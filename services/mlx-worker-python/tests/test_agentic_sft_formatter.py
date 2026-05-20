from __future__ import annotations

from worker.model_ops import agentic_sft_formatter


def test_agentic_tool_trace_sft_formatter_covers_defensive_branches() -> None:
    rows, metrics = agentic_sft_formatter.format_trace_rows(
        [
            {
                "trace_id": "trace-defensive",
                "question": "What happened?",
                "media_refs": ["fixture://loose", {}],
                "turns": [
                    "ignored",
                    {"role": "system", "content": "Use tools."},
                    {
                        "role": "assistant",
                        "content": "I will inspect.",
                        "tool_call": {
                            "id": "call-1",
                            "name": "visit",
                            "arguments": "ignored",
                        },
                    },
                    {"role": "tool", "observation": "plain observation"},
                    {"role": "tool", "observation": ""},
                ],
                "final_answer": "Done",
            },
            {
                "trace_id": "trace-answer-only",
                "question": "Answer only.",
                "turns": [],
                "final_answer": "Only answer",
            },
            {
                "trace_id": "trace-final-equals-assistant",
                "turns": [{"role": "assistant", "content": "Matched answer"}],
                "final_answer": "Matched answer",
            },
            {
                "trace_id": "trace-final-already-formatted",
                "turns": [
                    {
                        "role": "assistant",
                        "content": "Final answer: Already formatted",
                    }
                ],
                "final_answer": "Already formatted",
            },
        ]
    )

    assert rows[0] == {
        "messages": [
            {
                "role": "system",
                "content": "Media references:\n- fixture://loose\n- {}\n\nUse tools.",
            },
            {
                "role": "assistant",
                "content": (
                    'I will inspect.\nTool call: {"arguments":{},"id":"call-1",'
                    '"name":"visit"}'
                ),
            },
        ],
        "response_only_boundary": {
            "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
            "mask_prompt": True,
            "trainable_role": "assistant",
            "trainable_kind": "tool_call",
            "trainable_message_index": 1,
            "trace_id": "trace-defensive",
        },
    }
    assert rows[1] == {
        "messages": [
            {
                "role": "system",
                "content": "Media references:\n- fixture://loose\n- {}\n\nUse tools.",
            },
            {
                "role": "assistant",
                "content": (
                    'I will inspect.\nTool call: {"arguments":{},"id":"call-1",'
                    '"name":"visit"}'
                ),
            },
            {"role": "tool", "content": "Tool observation: plain observation"},
            {"role": "assistant", "content": "Final answer: Done"},
        ],
        "response_only_boundary": {
            "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
            "mask_prompt": True,
            "trainable_role": "assistant",
            "trainable_kind": "final_answer",
            "trainable_message_index": 3,
            "trace_id": "trace-defensive",
        },
    }
    assert rows[2] == {
        "messages": [{"role": "assistant", "content": "Final answer: Only answer"}],
        "response_only_boundary": {
            "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
            "mask_prompt": True,
            "trainable_role": "assistant",
            "trainable_kind": "final_answer",
            "trainable_message_index": 0,
            "trace_id": "trace-answer-only",
        },
    }
    assert rows[3] == {
        "messages": [{"role": "assistant", "content": "Final answer: Matched answer"}],
        "response_only_boundary": {
            "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
            "mask_prompt": True,
            "trainable_role": "assistant",
            "trainable_kind": "final_answer",
            "trainable_message_index": 0,
            "trace_id": "trace-final-equals-assistant",
        },
    }
    assert rows[4] == {
        "messages": [
            {"role": "assistant", "content": "Final answer: Already formatted"}
        ],
        "response_only_boundary": {
            "policy_id": "melix.agentic_tool_trace.response_only_boundaries.v1",
            "mask_prompt": True,
            "trainable_role": "assistant",
            "trainable_kind": "final_answer",
            "trainable_message_index": 0,
            "trace_id": "trace-final-already-formatted",
        },
    }
    assert metrics == {
        "sample_count": 4,
        "trainer_row_count": 5,
        "tool_call_count": 1,
        "tool_observation_count": 1,
        "media_ref_count": 2,
        "final_answer_count": 4,
        "response_only_boundary_count": 5,
        "mask_prompt_boundary_count": 5,
    }
    assert agentic_sft_formatter.count_trace_trainer_rows(
        [
            {
                "turns": [
                    {"role": "assistant", "tool_call": {"id": "a"}},
                    {"role": "assistant", "content": "done"},
                ],
                "final_answer": "done",
            }
        ]
    ) == 2
    assert agentic_sft_formatter.merge_projection_metrics(
        {"sample_count": "bad", "tool_call_count": "2"},
        {"sample_count": 1},
    )["sample_count"] == 1


def test_agentic_tool_trace_token_metrics_split_agentic_sft_spans() -> None:
    metrics = agentic_sft_formatter.collect_token_metrics(
        [
            {
                "trace_id": "trace-tokens",
                "question": "What happened?",
                "turns": [
                    {"role": "system", "content": "system prompt"},
                    {"role": "user", "content": "find answer"},
                    {
                        "role": "assistant",
                        "tool_call": {
                            "id": "call-1",
                            "name": "visit",
                            "arguments": {"url": "fixture doc"},
                        },
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call-1",
                        "observation": "tool result here",
                    },
                    {"role": "assistant", "content": "done now"},
                ],
                "final_answer": "done now",
            }
        ]
    )

    assert metrics == {
        "estimator": "whitespace_v1",
        "source_trace_count": 1,
        "trace_tokens": 19,
        "tool_call_tokens": 4,
        "observation_tokens": 7,
        "final_answer_tokens": 4,
    }
    assert agentic_sft_formatter.merge_token_metrics(
        {"trace_tokens": "bad", "tool_call_tokens": "2"},
        {"source_trace_count": 1, "trace_tokens": 3},
    ) == {
        "estimator": "whitespace_v1",
        "source_trace_count": 1,
        "trace_tokens": 3,
        "tool_call_tokens": 2,
        "observation_tokens": 0,
        "final_answer_tokens": 0,
    }


def test_agentic_tool_trace_token_metrics_ignore_unusable_turns() -> None:
    metrics = agentic_sft_formatter.collect_token_metrics(
        [
            {
                "trace_id": "trace-defensive",
                "turns": [
                    "ignored",
                    {"role": "assistant", "content": ""},
                    {"role": "assistant", "content": "Final answer: Already formatted"},
                    {"role": "tool", "tool_call_id": "call-empty", "observation": ""},
                ],
                "final_answer": "Already formatted",
            }
        ]
    )

    assert metrics == {
        "estimator": "whitespace_v1",
        "source_trace_count": 1,
        "trace_tokens": 4,
        "tool_call_tokens": 0,
        "observation_tokens": 0,
        "final_answer_tokens": 4,
    }
