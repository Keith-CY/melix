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

Two of the fast paths had drifted from the semantics they claimed to preserve:

- `worker.runtime.token_counting.whitespace_token_count` documented its ASCII branch
  as "the exact ASCII whitespace set recognized by `str.split()`", but the set omitted
  `\x1c`–`\x1f`, which `str.isspace()` treats as whitespace. ASCII text containing
  those separators was tokenized differently from the Unicode branch.
- `worker.productization.report_evidence_gate._rule_matches_report` cached normalized
  rule values by writing `_melix_cached_*` keys into the caller's rule dict. The
  matrix dicts are caller-supplied and serializable, so the cache leaked into data the
  gate does not own — and it was redundant with the `lru_cache` already applied to the
  same normalization helpers.

## Scope

Reverted to a single straightforward implementation, preserving observable behavior:

| Module | Before | After |
| --- | --- | --- |
| `worker/trajectory_provenance.py` | 956 lines | 236 lines |
| `worker/productization/report_evidence_gate.py` | 720 lines | 439 lines |
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

Micro-optimize a pure-Python helper only when a profile of a real workload attributes
measurable time to it. A registered probe that measures a synthetic loop over the
helper is not that evidence. When a fast path is justified, it needs a test that
pins the *result*, not the branch — a test that fails when a branch is deleted but
the output is unchanged is a maintenance liability, not coverage.

## Verification

`make py-test` plus `pytest tests` on Linux: no regressions against the pre-change
baseline. (128 tests fail on Linux both before and after this change; they require
Apple Silicon MLX or a built Swift binary.)
