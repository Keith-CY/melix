# Agent UI Walkthrough

This runbook defines the lightweight browser walkthrough workflow agents should use before implementing substantial Melix UI or UX changes.

## When To Use

Use this workflow when a change affects screen layout, navigation, information architecture, form flow, or visible labels. It is especially useful for macOS App surfaces where a static SwiftUI patch would be hard for the operator to review before implementation.

Do not use this workflow for narrow copy fixes, non-visual backend changes, or emergency bug fixes where the desired UI is already unambiguous.

## Workflow

1. Create or update a disposable walkthrough artifact under `.runtime/walkthrough/`.
   - Use a focused HTML file such as `.runtime/walkthrough/server-page.html`.
   - Keep it self-contained enough to open with a `file://` URL.
   - Do not commit `.runtime` walkthrough files unless the user explicitly asks.

2. Open the walkthrough in the in-app browser when the user wants interactive review.
   - Use the current browser tab when available.
   - Keep the page close to the App surface being designed.
   - Prefer real labels, row density, controls, states, and example data over abstract wireframes.

3. Iterate on the walkthrough before touching production UI code.
   - Update the HTML immediately when the user gives visual or interaction feedback.
   - Treat the walkthrough as a shared review surface, not as a final artifact.
   - Keep accepted decisions visible in the mock so the next review starts from the latest state.

4. Record decisions and open questions in a paired runtime note.
   - Use a file such as `.runtime/walkthrough/server-page-issues.md`.
   - Separate accepted decisions from unresolved questions.
   - When implementation starts, copy durable decisions into a repository plan or spec.

5. Implement only after the user confirms the walkthrough direction.
   - Add or update the relevant plan under `docs/plans/`.
   - Add focused tests for the accepted behavior before production edits.
   - Apply the App changes in small, verifiable slices.

6. Verify and reopen the real App.
   - Run the relevant automated tests.
   - Rebuild the App when the change touches Swift UI.
   - Launch the local App so the operator can perform the final manual walkthrough.

## Review Checklist

- The walkthrough represents the first screen or actual workflow, not a marketing page.
- Rows, badges, controls, empty states, and disabled states use realistic content.
- The mock does not introduce terminology that differs from the intended App copy.
- User feedback is reflected in the walkthrough before production implementation.
- Durable decisions are represented in tests, docs, or a plan before handoff.
- `.runtime/walkthrough` files remain untracked unless explicitly requested.

## Output Expectations

At handoff, summarize:

- the walkthrough artifact used;
- the production files changed;
- the tests run;
- any unresolved product questions or unsupported backend paths.
