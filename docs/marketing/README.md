# Melix Marketing And Storytelling Kit

This folder contains product-facing writing for explaining, introducing, and
promoting Melix. It is written for website copy, README sections, release notes,
social posts, demos, and operator-facing walkthroughs.

Use these documents together:

| Document | Purpose |
|---|---|
| [Melix Overview](melix-overview.md) | Product introduction, audience, positioning, and honest boundaries |
| [LoRA Training Story](lora-training-story.md) | The primary narrative: dataset to training to activation to comparison |
| [Copy Kit](copy-kit.md) | Reusable short-form copy blocks for launches, websites, posts, and demos |
| [Evidence And Screenshots](evidence-and-screenshots.md) | Commands, smoke output, and App screenshot provenance |

The primary visual asset is:

![Melix Window UI showing an active LoRA-derived local server](assets/window-ui-lora-workflow.png)

This screenshot is generated from the current native macOS App renderer through
the repository-owned Window UI acceptance flow. It is not a design mockup.

## Messaging Rules

- Lead with local-first Apple Silicon model operations.
- Make LoRA training the main product story: prepare a dataset, train an
  adapter, activate a derived model, compare it, and keep the evidence.
- Keep claims tied to current repository truth:
  - [`docs/current-status.md`](../current-status.md)
  - [`docs/runbooks/phase-8-lora-adapter-workflow.md`](../runbooks/phase-8-lora-adapter-workflow.md)
  - [`docs/runbooks/benchmark-matrix-evaluation-and-lora.md`](../runbooks/benchmark-matrix-evaluation-and-lora.md)
- Do not claim cloud training, cross-platform support, unmeasured quality gains,
  or broad unsupported model-family coverage.
- When publishing externally, pair promotional copy with the evidence command or
  screenshot reference from [Evidence And Screenshots](evidence-and-screenshots.md).
