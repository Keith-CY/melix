# Remove hot-path micro-optimization scaffolding

## Motivation

A long run of `perf:` slices accumulated CPython micro-optimizations in pure-Python
helpers: module-level rebinding of builtins (`_STR = str`, `_JSON_LOADS = json.loads`),
`type(x) is str` pre-checks in front of `isinstance`, hand-unrolled tuple/dict copies,
per-arity "fast paths" that duplicate the general implementation, and caches layered
on top of `functools.lru_cache`.

Each slice was small. Together they made the affected modules several times larger
than the behavior they implement, and they were locked in place by white-box tests
that monkeypatch internals (`monkeypatch.setattr(module, "set", fail_set)`,
`str` subclasses whose `strip()` raises) so the branch could not be removed without
a test failing. That inverts the usual relationship between tests and code: the tests
asserted *how* the code ran rather than *what* it produced.

Six of the fast paths had drifted from the semantics they claimed to preserve. Three
were pre-existing:

- `worker.runtime.token_counting.whitespace_token_count` documented its ASCII branch
  as "the exact ASCII whitespace set recognized by `str.split()`", but the set omitted
  `\x1c`–`\x1f`, which `str.isspace()` treats as whitespace. ASCII text containing
  those separators was tokenized differently from the Unicode branch.
- `worker.runtime.stream_assembler._whitespace_token_count` had the same defect from a
  different direction: its 11-condition guard excluded `\t\n\r\v\f` before returning
  `text.count(" ") + 1`, but not `\x1c`–`\x1f`, which `str.split()` does split on. Any
  ASCII delta of 256+ characters containing one undercounted its tokens by one per
  occurrence.
- `worker.productization.report_evidence_gate._rule_matches_report` cached normalized
  rule values by writing `_melix_cached_*` keys into the caller's rule dict. The
  matrix dicts are caller-supplied and serializable, so the cache leaked into data the
  gate does not own — and it was redundant with the `lru_cache` already applied to the
  same normalization helpers.

A fourth was introduced by the first cut of this refactor and caught in review:
collapsing `scripts/changed_scope_coverage._measurable_non_comment_lines` to
`read_text().splitlines()` changed line numbering, because `str.splitlines()` also
breaks on `\v`, `\f`, `\x1c`–`\x1e`, `\x85`, ` ` and ` ` while the diff
parser counts only `\n`-delimited lines. It now reads lines through the file object,
which matches the numbering the other scan strategies already produced.

An earlier revision of this document said the pre-existing code "shared the defect but
only inside a narrow ASCII fast path". That was wrong, and the direction matters. The
ASCII fast path used `bytes.splitlines()`, which — unlike `str.splitlines()` — does not
break on `\v`, `\f` or `\x1c`–`\x1e`, so it agreed with file iteration. The defect was
in the *non-ASCII* fallback, `read_text(encoding="utf-8").splitlines()`, reached only
when the file was not pure ASCII and more than 8 lines had changed. That is the worse
of the two placements: `\x85`, ` ` and ` ` are themselves non-ASCII, so a file
containing one was routed to the single strategy that mis-numbered it.

One divergence is older than this change and survives it. Git counts lines by `\n`
alone, while every strategy here — file iteration, `bytes.splitlines()`, and the
`readlines()` this change settles on — also breaks on a bare `\r`. A source file
containing a lone CR is still numbered inconsistently with the diff parser. This change
does not fix that; it is recorded so the next person does not rediscover it as new.

A fifth and sixth were introduced by this refactor and found in a later review pass, on
the two largest collapsed files. Both are the same shape: a value that the old code
routed to a "not usable" branch now reaches a coercion that accepts it.

- `_trajectory_provenance_from_snapshot_manifest` derived the trace digest once and
  used it for both the gate check and the stored field. The old code coerced the two
  separately, and only the stored one applied `or ""`. Since `Mapping.get(key, default)`
  returns the default only for an *absent* key, a manifest carrying an explicit
  `"trajectory_trace_digest": null` reached `str(None).strip()` and was stored as the
  literal string `"None"`. Restored the `or ""`.
- `_probe_phase_duration_key` existed in the old file but was never called — the old
  `_slowest_probe_phases` inlined its own `type(x) is float/int/str` ladder. Routing the
  collapsed version through the helper made it live, and its `isinstance(duration,
  (float, int, str))` accepts `bool`, which subclasses `int`. A JSON
  `"duration_ms": true` scored 1.0 instead of 0.0, and because the result feeds
  `heapq.nlargest(5, ...)` it displaced a genuine phase from the top five rather than
  changing one reported number. `bool` is now excluded explicitly.

The second is the more instructive one: the collapse did not change the helper, it
changed *which* code was reachable. Deleting a duplicate implementation promotes
whatever it was duplicating, and the survivor may never have been exercised. `type(x) is
int` and `isinstance(x, int)` also differ for `int` subclasses; that difference is left
alone here because `json.loads` cannot produce one.

## Scope

Reverted to a single straightforward implementation, preserving observable behavior:

| Module | Before | After |
| --- | --- | --- |
| `worker/trajectory_provenance.py` | 956 lines | 236 lines |
| `worker/productization/report_evidence_gate.py` | 720 lines | 478 lines |
| `scripts/changed_scope_coverage.py` `_measurable_non_comment_lines` | 5 duplicated scan strategies (6 by the time this landed) | 1 |
| `worker/runtime/token_counting.py` | 2 hand-rolled scan loops | `len(text.split())` |
| `worker/runtime/stream_assembler.py` `_whitespace_token_count` | 11-condition guard | `len(text.split())` |
| `worker/model_ops/hub_catalog.py` `_string` / `_int` | exact-type pre-checks | `isinstance` |
| `worker/runtime/runtime_utils.py` shard scan | clean-string strip elision | `str(...).strip()` |
| `worker/runtime/text_family_adapters.py` expert count | 2 duplicated coercion ladders | 1 shared coercion |

Deleted alongside the code they measured:

- probes `trajectory-provenance-copy-elision`, `trajectory-manifest-json-load`,
  `changed-scope-coverage-singleton-range-fastpath` and their scripts
- the `split_calls_mean` metric from `deterministic-vlm-completion-token-scan` and
  `vision-family-prompt-token-count-scan`, and the `*source_read_calls_mean` metrics
  from `changed-scope-coverage-measured-set-filter`
- the plan documents that specified the removed fast paths

Behavior tests were kept; tests that asserted an internal call pattern were either
rewritten to assert the observable result or removed. `_probe_phases` now returns
`{}` for a `str`-subclass phase whose `strip()` is overridden the same way any other
value is normalized, and `_dict_list` no longer returns the caller's list object.

## Reconciling with `main`

While this change was in review, `main` took 30 commits, 24 of them `perf:` slices of
the same shape this document describes. Six touched files rewritten here, and the
branch stopped being mergeable. The rebase resolved seven conflicting files:

| File | Resolution |
| --- | --- |
| `worker/trajectory_provenance.py` | Collapse kept. The landed change (#3206) swapped `type(x)` for a module-level `_TYPE` alias inside the block this change deletes — no behavior to carry forward. |
| `scripts/changed_scope_coverage.py` | Collapse kept for `_measurable_non_comment_lines` (#3202, #3205, #3224 added two more scan strategies and a third ASCII branch). The `covered_singleton` short-circuit (#3202) lands in `_measurable_changed_lines`, which this change does not touch, and is preserved. |
| `changed_scope_coverage_measured_probe.py` | Landed sparse fixture kept and generalized (`expected_sparse_*`); the read-call counters dropped. Taking one side wholesale would have paired a five-line fixture with a two-line assertion and failed the probe at runtime. |
| `tests/test_changed_scope_coverage.py` | Seven landed tests rewritten to assert results rather than call patterns. In five of them the fixture file is never created, so asserting the empty result already proves the source was not read — the `Path.read_text` monkeypatch was redundant. |
| `tests/test_trajectory_provenance.py` | The `_TYPE`-binding test dropped; the payload test kept, minus its three fail-if-called patches, because its copy-isolation assertions are real. |
| `tests/test_vision_runtime.py` | Two `str` subclasses counting `split()` calls replaced by the assertions on token counts they were wrapping. |
| `infra/perf/pr_scoped_probes.json` | Deletions kept; node ids renamed to match the rewritten tests. |

Whether the landed `perf:` commits should themselves be reverted is a separate
decision, deliberately not taken here: they are other authors' merged work, reverting
two dozen of them would make this change unreviewable, and the question is about the
policy above rather than about this diff. The conflict is worth recording as evidence
either way — the scaffolding was being re-added to two of these exact functions while
the change removing it was in review.

## Rule going forward

Keep properties that change complexity class; drop constant-factor tricks and caches
that mutate caller data. The first cut of this refactor removed both kinds together
and the PR-scoped report caught it: deriving run-kind values per rule instead of once
per matrix turned matching from O(roles + rows) into O(roles x rows), and dropping the
metric-prefix bucketing and the bounded top-k cost real time on real inputs. Those were
restored. The rule-dict mutation was not.

When collapsing duplicated implementations, check what the survivor actually is. Two of
the six drifts above came from a shared helper the removed code had bypassed — in one
case a helper that had never been called at all, so nothing had ever exercised it. A
collapse is not only a deletion; it promotes whatever the deleted branch stood in front
of, and that code may be reachable for the first time.

Beyond that line, micro-optimize a pure-Python helper only when a profile of a real
workload attributes measurable time to it. A registered probe that measures a synthetic
loop over the helper is not that evidence. When a fast path is justified, it needs a
test that pins the *result*, not the branch — a test that fails when a branch is
deleted but the output is unchanged is a maintenance liability, not coverage.

## Probes run against both revisions

The PR-scoped harness executes the **head** probe script against the **base** checkout
as well (`base/../head/scripts/...`). Renaming or re-typing a private helper's parameter
therefore breaks the base-side measurement with a `TypeError`, reported as
`probe_failed` rather than as a regression. A probe script that reaches into a private
helper must feature-detect the signature it is calling — see
`scripts/report_evidence_gate_run_kind_probe.py`, which inspects the signature once at
import and adapts.

## Verification

`make py-test` plus `pytest tests` on Linux: no regressions against the pre-change
baseline. The set of failing tests is byte-identical before and after. (128 tests fail
on Linux in both cases; they require Apple Silicon MLX or a built Swift binary.)

CI on macOS covers what Linux cannot: `python-tests` and `integration-tests` both pass
on the final revision of this branch.
