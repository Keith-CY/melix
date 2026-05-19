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
            {"role": "tool", "content": "Tool observation: plain observation"},
            {"role": "assistant", "content": "Final answer: Done"},
        ],
    }
    assert rows[1] == {
        "messages": [{"role": "assistant", "content": "Final answer: Only answer"}]
    }
    assert rows[2] == {
        "messages": [{"role": "assistant", "content": "Final answer: Matched answer"}]
    }
    assert rows[3] == {
        "messages": [
            {"role": "assistant", "content": "Final answer: Already formatted"}
        ]
    }
    assert metrics == {
        "sample_count": 4,
        "tool_call_count": 1,
        "tool_observation_count": 1,
        "media_ref_count": 2,
        "final_answer_count": 4,
    }
    assert agentic_sft_formatter.merge_projection_metrics(
        {"sample_count": "bad", "tool_call_count": "2"},
        {"sample_count": 1},
    )["sample_count"] == 1
