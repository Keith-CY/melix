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

Three of the fast paths had drifted from the semantics they claimed to preserve:

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
parser counts only `\n`-delimited lines. The old code shared the defect but only
inside a narrow ASCII fast path; the collapse made it unconditional in the script that
gates changed-line coverage for every PR. It now reads lines through the file object,
which matches the diff parser exactly.

## Scope

Reverted to a single straightforward implementation, preserving observable behavior:

| Module | Before | After |
| --- | --- | --- |
| `worker/trajectory_provenance.py` | 956 lines | 236 lines |
| `worker/productization/report_evidence_gate.py` | 720 lines | 478 lines |
| `scripts/changed_scope_coverage.py` `_measurable_non_comment_lines` | 5 duplicated scan strategies | 1 |
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

## Rule going forward

Keep properties that change complexity class; drop constant-factor tricks and caches
that mutate caller data. The first cut of this refactor removed both kinds together
and the PR-scoped report caught it: deriving run-kind values per rule instead of once
per matrix turned matching from O(roles + rows) into O(roles x rows), and dropping the
metric-prefix bucketing and the bounded top-k cost real time on real inputs. Those were
restored. The rule-dict mutation was not.

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
