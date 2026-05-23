# Closed Issue Post-Closure Follow-up Audit

## Goal

Audit closed GitHub issues for comments that arrived after closure, decide
whether those comments require Melix follow-up work, and make the required
follow-up work durable without reopening completed milestone issues.

## Source

- Repository: `Keith-CY/melix`
- Audit timestamp: 2026-05-23
- Closed issues scanned: 398
- Issues with comments strictly after `closedAt`: #41, #43, #365, and #676
- Runtime audit artifacts:
  `.runtime/closed-issue-followup-audit/summary.json` and
  `.runtime/closed-issue-followup-audit/post-close-comments.md`

The audit uses the strict rule that a comment must have `createdAt > closedAt`
to count as a post-closure follow-up. Closure evidence posted before or at the
same second as closure is not treated as follow-up work.

## Findings

| Issue | Post-closure comments | Decision | Follow-up owner |
| --- | ---: | --- | --- |
| #41 | 25 | Update needed | #1518 |
| #43 | 18 | Update needed | #1519 |
| #365 | 2 | No repository update needed | N/A |
| #676 | 1 | No repository update needed | N/A |

## Issue #41 Decision

#41 was closed before a later stream of structured-streaming and reasoning
continuity watch notes arrived. The early post-close notes from 2026-05-06
through 2026-05-08 were already moved into #615 and implemented by PR #630.
The later notes from 2026-05-11 through 2026-05-23 still contain actionable
advice that should not live only in a closed milestone comment thread.

Tracker #1518 now owns the remaining #41 post-closure follow-up audit. It must
avoid duplicating work already covered by #615, #867, #868, #1384, #1385, and
#1392.

The remaining buckets are:

- request-local compatibility policy receipts
- prompt-budget admission and typed error details
- declared parser-format audit and parser selector parity
- stream/non-stream finalizer parity
- token-routed reasoning/tool assembly
- generation bounds normalization

Each bucket must either become a concrete child issue or be mapped to an
existing open issue with evidence.

## Issue #43 Decision

#43 was closed before a later stream of long-context and advanced fine-tuning
watch notes arrived. The first post-close comment was explicitly moved to #70,
and parts of the later material are already covered by #70, #365, #935, #1258,
and their merged PRs. The remaining advice is still actionable enough to need a
durable owner.

Tracker #1519 now owns the remaining #43 post-closure follow-up audit. It must
avoid duplicating covered work and split the still-open advice into small,
verifiable implementation issues.

The remaining buckets are:

- training admission and receipt hardening
- training artifact and export correctness
- runtime and dependency safety guards
- advanced training planner and evidence

Each bucket must either become a concrete child issue or be mapped to an
existing open issue with evidence.

## Issue #365 Decision

#365 received two comments after closure. Both are completion and mapping
comments from the repository owner. They confirm that the Issue 365 stack landed
through #442, #446, #451, #457, and the final #439 merged-tree audit. They do
not introduce new work.

No code, documentation, PR, or issue-status update is required for #365.

## Issue #676 Decision

#676 received one comment after closure. The comment corrects the closeout
evidence with shell-safe formatting and points back to merged PR #857 plus
current-state verification. It does not introduce new work.

No code, documentation, PR, or issue-status update is required for #676.

## Performance Probes And Metrics

This audit changes repository planning state and GitHub tracking only. It does
not change runtime, control-plane, worker, CLI, or UI behavior, so no runtime
performance probe is applicable for this slice.

Metrics for the audit process:

- closed issues scanned: 398
- post-closure candidate issues: 4
- candidates requiring new tracking: 2
- candidates requiring no update: 2
- comment pagination overflow during audit: 0

Implementation child issues created from #1518 and #1519 must define their own
performance probes, measurement points, and success metrics before changing
behavior.

## Acceptance Criteria

- All closed issues in the repository are scanned with pagination.
- Only comments with `createdAt > closedAt` are counted as post-closure
  follow-ups.
- Every issue with post-closure comments receives an explicit decision:
  update needed, no update needed, or human decision needed.
- Update-needed decisions have durable GitHub tracking issues.
- No-update-needed decisions record why no repository update is required.
- Closed source issues #41 and #43 receive comments linking the new trackers.
- This plan is committed through a pull request so the audit outcome remains
  discoverable from the repository.

## Verification

```bash
git fetch origin main --prune
gh issue list --state closed --limit 1000 --json number,title,closedAt,updatedAt,comments,url --jq 'length'
gh api graphql ... # paginated closed issue query with comments(first:100)
gh issue view 41 --repo Keith-CY/melix --comments
gh issue view 43 --repo Keith-CY/melix --comments
gh issue view 365 --repo Keith-CY/melix --comments
gh issue view 676 --repo Keith-CY/melix --comments
git diff --check
```

No automated code coverage command is applicable because this is a
documentation and issue-tracking audit with no executable behavior changes.
