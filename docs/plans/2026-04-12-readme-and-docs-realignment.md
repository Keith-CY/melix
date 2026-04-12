# README And Docs Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Realign the public-facing documentation so the README introduces Melix as a product, while the docs tree cleanly separates onboarding, contribution guidance, current status, and engineering runbooks.

**Architecture:** Keep the existing canonical specs, runbooks, and plan archives in place, then add a small set of human-oriented entry documents that point to those deeper materials. Rewrite the root README around product narrative, LoRA plus benchmark positioning, audience fit, and contribution flow instead of repository-internal operations detail.

**Tech Stack:** Markdown, GitHub README rendering, Shields badges, existing repository docs and runbooks.

---

### Task 1: Rewrite The Root README

**Files:**
- Modify: `README.md`
- Reference: `apps/macos-menubar/Sources/AppMain/Resources/Branding/melix_logo.svg`

- [ ] **Step 1: Replace the current developer-heavy opening with a product-first hero**

Use a README structure with:

```markdown
<p align="center">
  <img ... />
</p>

# Melix

badges...

short product summary...
```

- [ ] **Step 2: Reframe the body around user-facing questions**

Cover these sections:

```markdown
## What Melix Is
## Why Melix Exists
## Who It Is For
## What You Can Do Today
## Quick Start
## Documentation
## Contributing
```

- [ ] **Step 3: Move operational detail out of the README**

Replace long install and acceptance detail with short links to:

```markdown
- docs/getting-started.md
- docs/current-status.md
- docs/runbooks/...
```

- [ ] **Step 4: Keep badge content truthful**

Use:

```markdown
- real GitHub Actions workflow badges
- static badges for Apple Silicon, Swift, Python, Apache-2.0, LoRA, Bench/Eval
```

### Task 2: Add Human-Oriented Docs Entry Pages

**Files:**
- Add: `docs/getting-started.md`
- Add: `docs/contributing.md`
- Add: `docs/current-status.md`

- [ ] **Step 1: Add a concise getting-started guide**

Include:

```markdown
- prerequisites
- make bootstrap
- make proto
- make swift-test / make py-test / make integration-test
- one shortest-path local stack flow
- one shortest-path LoRA / bench / eval example block
```

- [ ] **Step 2: Add a contribution guide**

Include:

```markdown
- branch/worktree expectations
- required verification commands
- docs update expectations
- coverage and metrics expectations before handoff
```

- [ ] **Step 3: Add a current-status page that matches shipped behavior**

Include:

```markdown
- shipped now
- current operator surfaces
- verified workflows
- honest boundaries and known gaps
- links to roadmap, progress log, and runbooks
```

### Task 3: Rebuild The Docs Navigation Around These Entry Pages

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/phase-roadmap.md`

- [ ] **Step 1: Turn `docs/README.md` into a real navigation page**

Group links under:

```markdown
- Product and status
- Getting started
- Operations and runbooks
- Architecture and protocols
- Decisions
- Historical plans
```

- [ ] **Step 2: Update `docs/phase-roadmap.md` so it reflects the current repository state**

Add or revise:

```markdown
- current completion summary
- current boundary / not-yet-shipped notes
- link to full execution index for milestone detail
```

- [ ] **Step 3: Keep canonical docs in place**

Do not move:

```markdown
- architecture-spec.md
- benchmark-evaluation-contract.md
- control-plane-protocol.md
- worker-rpc-schema.md
```

### Task 4: Verify Link Consistency And Markdown Hygiene

**Files:**
- Verify: `README.md`
- Verify: `docs/README.md`
- Verify: `docs/getting-started.md`
- Verify: `docs/contributing.md`
- Verify: `docs/current-status.md`
- Verify: `docs/phase-roadmap.md`

- [ ] **Step 1: Check markdown diff hygiene**

Run:

```bash
git diff --check
```

Expected: no whitespace or conflict-marker errors.

- [ ] **Step 2: Spot-check the rewritten entry points**

Run:

```bash
sed -n '1,240p' README.md
sed -n '1,260p' docs/README.md
sed -n '1,260p' docs/getting-started.md
sed -n '1,260p' docs/contributing.md
sed -n '1,260p' docs/current-status.md
sed -n '1,260p' docs/phase-roadmap.md
```

Expected: links and section order read cleanly, and the public-facing pages no longer lead with internal implementation detail.

- [ ] **Step 3: Record doc-scope metrics honestly**

Metrics note:

```markdown
N/A for executable coverage because this transaction is documentation-only.
Verification is markdown hygiene plus content alignment against repository sources.
```
