# Prompt-Lookup Decoding

_Last updated: 2026-07-30_

Prompt-lookup decoding is a draft-model-free speculative decoding mode for the
Python text worker. It drafts continuation tokens by matching the current
generation suffix against n-grams already present in the request context, then
verifies the draft with one batched forward pass of the target model.

## When it helps

The win comes entirely from workloads whose output overlaps their input:

| Workload | Why it overlaps |
|---|---|
| RAG / document Q&A | The answer quotes retrieved passages verbatim |
| Code editing | The edited span echoes surrounding code |
| Summarization / extraction | Output reuses source phrasing and entity names |
| Agent turns | Repeated tool schemas and observation text |

On workloads with no overlap (open-ended creative generation) drafts stop
landing, and the hysteresis gate below returns the request to plain decoding.

## Why it is different from the other acceleration modes

| Mode | Extra assets | Model support |
|---|---|---|
| Draft-model speculative decode | A paired Draft Companion model | Any |
| Native MTP | MTP head weights in the checkpoint | Qwen3.5 family |
| **Prompt lookup** | **None** | **Any** |

That makes prompt lookup the only acceleration mode available for an arbitrary
locally imported model with no additional download.

## Correctness: greedy identity

Verification accepts the longest draft prefix matching the target model's own
greedy predictions, then emits one additional (bonus) token from the same
forward pass. Every emitted token is therefore a prediction the target model
made, so the token sequence is **identical to plain greedy decoding** — only the
number of forward passes differs.

Because of that, prompt lookup is **greedy-only**, and the bar for "greedy" is
provability from a documented contract rather than likely equivalence. A request
qualifies only when **both** hold:

- `temperature <= 0` — mlx-lm's `make_sampler` documents that `temp == 0`
  returns `mx.argmax` outright. A non-zero temperature with `top_k == 1` is also
  argmax under the current pin, but only by an argument about the sampler
  chain's internal ordering; that is upstream-owned, so it is excluded rather
  than relied on.
- `frequency_penalty` and `presence_penalty` are both zero — penalties do not
  reach the pinned mlx-lm's `make_sampler` (they live in
  `make_logits_processors`), but that forwarding is detected from the sampler
  factory at runtime. An mlx-lm bump that started accepting them would otherwise
  silently penalize the standard path while prompt lookup verified against a
  plain argmax.

Everything else — sampled requests, penalized requests, and structured-output
requests — stays on the standard decode path. Melix will not silently change a
request's output distribution to gain throughput.

Structured-output requests (`response_format`) also stay on the standard path,
since constraint enforcement lives in the sampler.

## Enabling it

Prompt lookup is opt-in through `AccelerationPolicy.ext` (no protocol change),
and the control plane forwards those keys to the worker. Request `ext` wins over
the session-level policy for the same key.

| Ext key | Meaning | Default |
|---|---|---|
| `melix.prompt_lookup.enabled` | Turns the mode on (`true`/`1`/`yes`/`on`) | off |
| `melix.prompt_lookup.max_ngram` | Longest suffix tried when matching | `8` |
| `melix.prompt_lookup.min_ngram` | Shortest suffix accepted as a match | `2` |
| `melix.prompt_lookup.max_draft_tokens` | Tokens proposed per verify cycle | `8` |
| `melix.prompt_lookup.min_accept_rate` | Accept-rate floor before pausing | `0.2` |
| `melix.prompt_lookup.warmup_cycles` | Drafted cycles observed before judging | `8` |
| `melix.prompt_lookup.cooldown_cycles` | Cycles paused after a trip | `16` |

Out-of-range or unparseable values fall back to the default rather than failing
the request — this is a performance path, and a bad knob must never turn into a
failed generation. `min_ngram` is clamped to `max_ngram`.

## Matching semantics

The n-gram index maps each n-gram to its **earliest** end position. Earliest
wins for two reasons: it biases drafts toward the grounded prompt/document
rather than the model's own recent output, and it makes "the only occurrence is
the suffix being matched right now" detectable, which is exactly the case where
no draft exists.

Suffixes are tried longest-first (`max_ngram` down to `min_ngram`); the first
match's continuation becomes the draft.

## Hysteresis fallback

Without a gate, an adversarial workload would pay a `1 + max_draft_tokens` wide
forward for every single emitted token. After `warmup_cycles` **drafted** cycles
the gate compares the observed accept rate against `min_accept_rate` and, if it
is below, pauses drafting for `cooldown_cycles` cycles before probing again.
Paused cycles are ordinary single-token forwards, so a paused request costs the
same as baseline decoding.

Cycles that proposed nothing are not observations: with no draft there is no
wasted verify width to protect against, so they do not accumulate toward a
pause.

## Receipts

Prompt-lookup metrics are projected onto the existing speculative receipt
vocabulary, so benchmark exports, diagnostics bundles, and the
acceleration-profile surfaces work unchanged:

| Field | Meaning under prompt lookup |
|---|---|
| `speculative_acceptance_rate` | Accepted ÷ proposed draft tokens |
| `speculative_rollback_rate` | Rejected ÷ proposed draft tokens |
| `speculative_accepted_tokens` | Draft tokens confirmed by verification |
| `speculative_rejected_tokens` | Draft tokens discarded |
| `speculative_fallback_count` | Times the hysteresis gate tripped |
| `speculative_num_draft_tokens` | Configured per-cycle draft width |
| `speculative_draft_model_configured` | Always `false` — no draft model exists |

## Boundaries

- Greedy only; sampled and structured-output requests use the standard path.
- Single-token EOS ids terminate generation inside the loop; multi-token stop
  sequences remain the downstream text stop contract's responsibility, matching
  the native-MTP path.
- A KV cache that cannot trim to an arbitrary boundary (rotating layouts, some
  quantized layouts) is rebuilt and re-prefilled rather than reused at a
  misaligned position — correct, but it costs the re-prefill.
- Composing prompt lookup with the session prefix cache is future work: the
  verify step owns its own cache today.
