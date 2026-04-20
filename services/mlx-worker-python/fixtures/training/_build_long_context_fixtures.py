"""Builds long-context JSONL fixtures with pre-measured Qwen token counts.

Run once from the repo root with a primed Qwen3.5-0.8B-OptiQ-4bit tokenizer:
    MELIX_TOKENIZER_PATH="$HOME/.cache/..../snapshot" \
        uv run --project services/mlx-worker-python python /tmp/build_long_context_fixtures.py

Produces the 4k + 8k samples.jsonl + manifest.json files in-place.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from transformers import AutoTokenizer

SEED_PARAGRAPH = (
    "Alice was beginning to get very tired of sitting by her sister on the "
    "bank, and of having nothing to do: once or twice she had peeped into the "
    "book her sister was reading, but it had no pictures or conversations in "
    "it, 'and what is the use of a book,' thought Alice 'without pictures or "
    "conversations?' So she was considering in her own mind (as well as she "
    "could, for the hot day made her feel very sleepy and stupid), whether "
    "the pleasure of making a daisy-chain would be worth the trouble of "
    "getting up and picking the daisies, when suddenly a White Rabbit with "
    "pink eyes ran close by her."
)

TOKENIZER_PATH = os.environ["MELIX_TOKENIZER_PATH"]
tok = AutoTokenizer.from_pretrained(TOKENIZER_PATH, use_fast=True)


def render_tokens(messages):
    return tok.apply_chat_template(messages, add_generation_prompt=False, return_dict=False)


def build_long_user_content(target_user_tokens: int) -> str:
    """Build a user-content string that, when token-counted alone, yields ~target tokens."""
    content = ""
    while True:
        content = (content + " " + SEED_PARAGRAPH).strip()
        ids = tok(content, add_special_tokens=False)["input_ids"]
        if len(ids) >= target_user_tokens:
            break
    return content


def build_samples(target_total: int, variants: list[dict]) -> list[dict]:
    """Produce samples whose full chat-template rendering yields ~target_total tokens."""
    samples = []
    for variant in variants:
        system = variant.get("system")
        turns = variant["turns"]  # list of (user_turn_target, assistant_short_text)
        # Estimate template overhead: render empty samples first to learn per-turn overhead
        # Simpler: iterate user content length until render token count reaches target.
        budget = target_total
        user_budget_per_turn = max(1, budget // max(1, len(turns) * 2))  # first pass
        # Build messages with placeholder lengths, then grow until template length >= target.
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        # Seed turns
        for user_target, asst_text in turns:
            messages.append({"role": "user", "content": build_long_user_content(user_target)})
            messages.append({"role": "assistant", "content": asst_text})
        # Grow last user turn until the full rendering hits target
        while True:
            total = len(render_tokens(messages))
            if total >= target_total:
                break
            # Grow the first user turn
            messages[1 if system else 0]["content"] = (
                messages[1 if system else 0]["content"] + " " + SEED_PARAGRAPH
            )
        total = len(render_tokens(messages))
        samples.append({
            "id": variant["id"],
            "rendered_tokens": total,
            "messages": messages,
        })
    return samples


# Variant schemas: (id, system-or-None, turns). turns = list of (user_token_seed, assistant_text).
FOUR_K_VARIANTS = [
    {"id": "4k-single-no-system", "turns": [(3800, "The White Rabbit hurried off into the field.")]},
    {"id": "4k-single-with-system",
     "system": "You are a concise literary assistant summarizing the passage.",
     "turns": [(3700, "Alice follows the rabbit curiously down the path.")]},
    {"id": "4k-two-turn",
     "turns": [(1800, "The paragraph describes Alice's afternoon."),
               (1800, "The White Rabbit appears and runs past her.")]},
    {"id": "4k-three-turn-system",
     "system": "Stay factual and terse.",
     "turns": [(1100, "A bored Alice."),
               (1100, "Then a rabbit."),
               (1200, "She pursues it.")]},
    {"id": "4k-long-user-short-asst",
     "turns": [(3900, "OK.")]},
    {"id": "4k-alt-system-variant",
     "system": "Reply in one short sentence.",
     "turns": [(3600, "A lazy afternoon upended by a hasty rabbit.")]},
    {"id": "4k-chat-mix",
     "turns": [(1300, "Mostly scene-setting."),
               (1300, "Transitions to the rabbit."),
               (1200, "Signals the inciting incident.")]},
    {"id": "4k-long-system",
     "system": ("You are a literary critic. Focus only on the opening "
                "paragraph of Alice's Adventures in Wonderland. Keep your "
                "response grounded in that paragraph and avoid introducing "
                "outside knowledge. Respond in one or two sentences."),
     "turns": [(3400, "It establishes boredom as the catalyst for adventure.")]},
    {"id": "4k-question-answer",
     "turns": [(3700, "The text is from Lewis Carroll's Alice in Wonderland.")]},
    {"id": "4k-reflective",
     "system": "You are reflective.",
     "turns": [(3500, "A fine opening to a children's classic.")]},
]

EIGHT_K_VARIANTS = [
    {"id": "8k-single-no-system", "turns": [(7700, "The passage sets a dreamy tone.")]},
    {"id": "8k-two-turn",
     "turns": [(3700, "Alice is bored."),
               (3700, "The rabbit arrives.")]},
    {"id": "8k-three-turn-system",
     "system": "Be concise.",
     "turns": [(2500, "Scene set."),
               (2500, "Rabbit appears."),
               (2500, "Alice follows.")]},
    {"id": "8k-long-system",
     "system": ("You are a reading assistant. Summarize only the quoted "
                "paragraph without adding modern context. Keep your answer "
                "to a single short sentence."),
     "turns": [(7500, "A bored girl is startled into adventure by a hasty rabbit.")]},
    {"id": "8k-variant-two",
     "system": "Stay succinct.",
     "turns": [(7500, "The opening moments before Alice's fall.")]},
]


def dump_fixture(out_dir: Path, fixture_id: str, target_total: int, variants: list[dict]):
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = build_samples(target_total, variants)
    samples_path = out_dir / "samples.jsonl"
    samples_path.write_text(
        "\n".join(json.dumps({"id": s["id"], "messages": s["messages"]}) for s in samples) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "melix.training_dataset_snapshot.v1",
        "dataset_id": fixture_id,
        "format": "chat_messages",
        "sample_count": len(samples),
        "validation_sample_count": 0,
        "version": "1",
        "response_only_supported": True,
        "target_tokens_per_sample": target_total,
        "tokenizer_reference": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "template_family": "qwen",
        "measured_tokens_per_sample": [
            {"id": s["id"], "rendered_tokens": s["rendered_tokens"]} for s in samples
        ],
        "notes": (
            "Generated by build_long_context_fixtures.py from a committed "
            "seed paragraph (Alice in Wonderland opening). Per-sample token "
            "counts recorded at generation time; the baseline harness asserts "
            "drift stays under 5%."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


ROOT = Path("services/mlx-worker-python/fixtures/training")
dump_fixture(ROOT / "long-context-4k.v1", "long-context-4k.v1", 4000, FOUR_K_VARIANTS)
dump_fixture(ROOT / "long-context-8k.v1", "long-context-8k.v1", 8000, EIGHT_K_VARIANTS)
print("fixtures built")
