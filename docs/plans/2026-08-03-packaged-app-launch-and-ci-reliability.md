# Packaged App Launch And CI Reliability

## Goal

Restore the self-contained macOS App launch contract and remove the recurring
scheduled-CI failures observed on `main` without weakening production request
semantics.

## Confirmed Failures

1. A hardened-runtime preview bundle passes strict static code-signing checks
   but dyld rejects bundled Sparkle, Python extensions, and Swift MLX code when
   their ad-hoc signatures have no common Team ID.
2. The package workflow expands an empty Bash array under `set -u`. GitHub's
   macOS Bash 3.2 reports `candidate_arguments[@]: unbound variable` for normal
   preview and scheduled builds.
3. Two scheduled Swift failures are test synchronization defects: the
   `startChat` test inspects asynchronous generation before consuming the
   stream, and the HTTP resume test uses a fixed 500 ms wait despite the
   repository's existing CI wait-budget policy.

## End-State Design

- Keep hardened runtime and explicit inside-out signing for every packaged
  target.
- Grant `com.apple.security.cs.disable-library-validation` only to the three
  packaged executables that intentionally load bundled non-platform code:
  `melix-menubar`, `melix-text-worker-swift`, and the versioned bundled Python
  interpreter. Preserve and verify Sparkle helper entitlements independently.
- Make workflow preview and release-candidate identity arguments explicit,
  avoiding optional Bash arrays entirely.
- Make async tests observe their true completion boundary. Reuse the shared CI
  wait multiplier for bounded polling rather than changing production timing.
- Run the assembled App in the package workflow, poll its public health
  endpoint, always terminate it, and prove every descriptor-recorded process
  has exited so static signing success cannot substitute for runtime acceptance.

## Verification And Metrics

- Unit tests cover the exact library-validation exception targets, generated
  codesign commands, entitlement verification, and workflow argument branches.
- The affected Python packaging scope reaches at least 95 percent changed-line
  coverage.
- Both previously failing Swift tests pass repeatedly and in their repository
  test groups with `CI=true`.
- A freshly assembled App reaches `GET /health` on an isolated explicit port,
  publishes its active-runtime descriptor, and leaves no descriptor-recorded
  processes after shutdown.
- Packaging-signing plan construction remains O(number of packaged Mach-O
  files). The exception classification adds constant work per target and no
  additional filesystem traversal.
- Observability mode is `minimal`: the workflow retains bounded launcher logs
  only on failure and reports health acceptance without credentials or request
  bodies.

## Delivery Slices

- [x] Add failing regression coverage for the three confirmed defects.
- [x] Apply the signing, workflow, and test-synchronization fixes.
- [x] Add packaged runtime launch acceptance to the package workflow.
- [x] Run focused coverage, full repository gates, and the scoped performance
      report.
- [ ] Open an evidence-complete pull request and monitor its required checks.
