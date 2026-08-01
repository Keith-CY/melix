# GitHub Release App Updates Plan

## Goal

Give the self-contained macOS `Melix.app` a user-controlled, observable, and
cryptographically authenticated update path from GitHub Releases without
requiring an Apple Developer ID, notarization, or silent installation.

## Governing Contracts

- `docs/runbooks/platform-packaging-targets.md` owns the delivery and update
  strategy for the self-contained App bundle.
- `docs/window-ui-product-spec.md` keeps software updates inside the existing
  Settings domain instead of adding a new routable desktop domain.
- `docs/runbooks/phase-8-release-gates.md` requires release evidence to fail
  closed when required security artifacts are missing or invalid.
- `docs/engineering-standards.md` requires dependency lockfiles, tests,
  changed-scope coverage, and metrics for executable changes.

This is a focused Settings card and application-menu command with established
interaction semantics, not a navigation or information-architecture change.
The interactive UI walkthrough is therefore not required for this slice.

## Current Gap

- The package workflow produces ad-hoc-signed preview archives and attaches tag
  archives to GitHub Releases, but it does not publish authenticated update
  metadata.
- The packaged `Info.plist` has no update feed or independent update public key.
- The desktop App has no update controller, no scheduled check, no manual check,
  and no operator-visible update state.
- Replacing a downloaded App manually is the only upgrade path. Preview
  artifacts expire and are not a stable or authenticated update channel.

## End-State Architecture

1. Use Sparkle 2 as the update transaction engine. Sparkle owns feed loading,
   version selection, user confirmation, archive download, EdDSA verification,
   extraction, atomic replacement, recovery after failed replacement, and
   application relaunch.
2. Give every update-enabled release the stable self-signed macOS code-signing
   identity `Melix GitHub Release Signing`. Store its exported PKCS#12 identity
   and password only in encrypted offline backups and the two release secrets.
   This preserves one designated requirement across releases without claiming
   Apple trust, Developer ID, or notarization.
3. Treat a Melix-specific Ed25519 key as the update authenticity identity. The public key is
   embedded in release bundles; the private key exists only in the maintainer's
   secure backup and the `SPARKLE_EDDSA_PRIVATE_KEY` GitHub Actions secret.
   Melix must not reuse another product's update key.
4. Keep ad-hoc macOS code signing only for preview bundles. An ad-hoc archive
   must never contain the release feed or public update key and must never be
   labeled as an update-enabled release.
5. Publish a signed `appcast.xml` and its EdDSA-signed App archive from version
   tags. The stable feed is
   `https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml`.
6. Split a tag run into three trust classes. A non-secret job first validates
   an exact stable canonical tag, tag-to-source SHA equality, ancestry from the
   current `origin/main`, and a strictly increasing numeric SemVer. An
   untrusted package job then emits an independently named candidate with
   bundle ID `io.melix.menubar.release-candidate`, target
   `macos_app_bundle_github_release_candidate`, no feed, no update key, no
   certificate pins, and a receipt binding tag, source SHA, bundle tree, and
   archive digest. Only the fixed `github-release` protected environment may
   turn that candidate into a release after revalidating both receipts. That
   protected publication is globally serialized across tags, re-fetches every
   stable tag immediately before upload, and fails a queued older release once
   a newer stable version exists.
7. Fail the protected release job closed unless its independently provisioned
   EdDSA public variable, certificate SHA-256 variable, certificate SHA-1
   variable, EdDSA private secret, self-signed PKCS#12 secret, and PKCS#12
   password secret are present and mutually consistent. Pull-request, branch,
   scheduled, and manually dispatched preview archives remain outside the
   supported update chain.
8. Package the complete Sparkle framework, including `Installer.xpc`,
   `Downloader.xpc`, `Autoupdate`, and `Updater.app`, under
   `Contents/Frameworks`. Sign in Sparkle's documented inside-out order:
   `Installer.xpc`; `Downloader.xpc` while preserving its legal empty
   entitlement plist; `Autoupdate`; `Updater.app`;
   `Sparkle.framework`; remaining Mach-O files; outer App. Every signature uses
   hardened runtime and is verified explicitly; `codesign --deep` is forbidden.
9. Pin the release certificate twice from protected configuration, using both
   SHA-256 and SHA-1 rather than deriving either expectation from the PKCS#12.
   Verify exact authority, both leaf-certificate hashes, designated
   requirement, helper entitlements, hardened runtime, complete layout, and
   the extracted archive before publishing.
10. Bind `CFBundleShortVersionString`, `CFBundleVersion`, the packaging
    manifest `product_version`, and both Sparkle appcast version attributes to
    the validated tag receipt. Derive `LSMinimumSystemVersion` from the
    menu-bar package's `.macOS(.v15)` declaration and require the signed
    appcast to publish exactly `15.0`. Publish explicitly as latest, then read
    GitHub's latest release and its downloaded appcast back before dispatching
    downstream distribution.
11. Initialize updates only when the running bundle contains a valid HTTPS feed,
   a non-empty public key, and the packaged Sparkle framework. A checkout build
   or preview bundle reports updates as unavailable instead of starting a
   partially configured updater.
12. Add a Software Updates card to Settings and a **Check for Updates...** item
   to the application menu. The card exposes the current version, automatic
   check preference, last check time, current stage, last failure, manual check,
   and GitHub Releases fallback.
13. Check at most once per day by default. Installing always requires an
   explicit user decision; automatic download and silent installation remain
   disabled.
14. Treat Sparkle cancellation codes `4007` and `4008`, including
    `userDidCancelDownload`, as one non-failure terminal event that returns the
    controller to an idle, retryable state. Track whether an update was already
    discovered so generic network errors and Sparkle codes `2000`/`2001` map
    to metadata before discovery and download afterward, and suppress duplicate
    terminal failures from paired delegate callbacks.
15. Redact implementation details from operator errors while retaining a typed
    state that distinguishes configuration, metadata, download, authenticity,
    extraction, replacement/recovery, and relaunch failures for tests and
    diagnostics.

## Security And Recovery Contract

- HTTPS protects transport; the independent EdDSA signature is the release
  authenticity boundary.
- The stable self-signed code identity preserves one macOS designated
  requirement across release builds. It is not an Apple trust anchor and does
  not replace EdDSA archive or feed verification.
- Both the archive signature and the signed appcast must verify before
  installation. A digest-only or TLS-only update is insufficient.
- Missing or mismatched key material, an unsigned feed, an invalid signature,
  a changed archive length, a downgrade, or an invalid bundle layout must fail
  closed.
- The user must see and approve every install. Melix never executes an
  unverified archive and never silently replaces itself.
- Sparkle's installer preserves the current App until the replacement is ready
  and restores it when replacement fails. The existing App remains usable when
  the feed or download is unavailable.
- **View Releases** remains the recovery route. The first Sparkle-enabled Melix
  version must be installed manually; subsequent signed releases can update it.
- Private key, PKCS#12, and password values must never appear in repository
  files, pull-request text, logs, workflow summaries, or test fixtures. Only
  the EdDSA public key and code-signing certificate fingerprint may be stored or
  displayed.
- Administrator code-signing trust exists only on a GitHub-hosted macOS runner.
  Preparation saves the exact user keychain search list, validates independent
  certificate pins, adds code-signing-only trust with passwordless `sudo`, and
  proves a real hardened-runtime sentinel signature. Cleanup removes trust,
  restores the exact search list, deletes keychain, PKCS#12, PEM, and sentinel,
  and must be confirmed before release assets can be published.
- Repository code cannot create the `github-release` environment, its required
  reviewers, deployment tag policy, protected variables/secrets, protected
  `main`, or immutable release-tag rules. Those external GitHub controls are
  production activation blockers, not follow-up niceties.
- EdDSA and stable code-signing identities do not rotate in-band. Any change or
  loss requires incident handling and a new manually installed bootstrap App;
  existing installations must never silently trust a replacement identity.

## Performance Probes And Success Metrics

- App launch performs no foreground network request. Update-configuration
  resolution is local, remains O(1), and must complete 100 deterministic
  resolutions in under 10 ms in the focused Swift probe.
- Preview/release package configuration validation and package-time Sparkle
  resolution remain O(1) in the number of repository files.
- Automatic checks run no more than once per 86,400 seconds and execute outside
  Chat, generation, and control-plane request paths.
- The packaged archive grows only by the complete Sparkle framework; the
  package manifest records its version and packaged byte count.
- Changed executable lines in the Swift update scope and Python packaging scope
  must each reach at least 95 percent automated coverage.
- Focused unit tests must cover disabled preview configuration, manual and
  scheduled-check policy, no update, update available, redacted failure
  mapping, install/relaunch stages, and visible state mapping. Post-provisioning
  two-release acceptance must cover real metadata/network and download
  failures, invalid archive/feed signatures, extraction or replacement failure
  and recovery, install approval, and relaunch.
- Packaging tests must prove the release `Info.plist`, framework layout, stable
  nested code identity, designated requirement, signed feed inputs, and
  fail-closed workflow contract.
- The versioned pre-commit hook remains authoritative. On this task's 64 GiB
  macOS host it is expected to record its policy skip because the full hook gate
  requires at least 128 GiB; focused Python/Swift suites, an explicit cached
  full menu-bar Swift suite, changed-scope coverage, and CI remain required
  evidence. The memory-policy skip is not evidence that the full gate passed.
- Observability mode is `minimal`: only current stage, last check time, and a
  redacted error summary are retained. No URLs with query data, HTTP bodies,
  system profile, key material, or downloaded paths are logged.
- Fixed-base local performance reports for the final review-hardening tree
  selected all seven packaging probes with no verification failures; every
  targeted test and changed-scope coverage gate passed. Concurrent host load
  produced unstable timing-only regressions in both retained reports. The
  measured functions, their repository-owned transitive helpers and constants,
  and every probe definition match `origin/main` by AST or content SHA-256;
  the only probe-file difference is an untimed Python 3.12 module-registration
  compatibility fix. The timing findings are therefore outside this change's
  hot paths and non-blocking rather than an accepted product regression.

## Delivery Slices

- [x] Inspect the current Melix packaging/release path and the existing
      GitHub-release updater implementation in the related macOS project.
- [x] Define the independent trust boundary, preview-vs-release behavior,
      performance targets, and acceptance matrix before implementation.
- [x] Add Sparkle to the macOS App dependency graph and lockfile.
- [x] Add a testable update controller, typed state, application-menu command,
      and Settings card.
- [x] Extend App packaging to embed updater configuration and the complete
      Sparkle framework only under fail-closed release inputs.
- [x] Extend tag packaging with a stable self-signed code identity and verify
      the exact authority and designated requirement before release.
- [x] Extend the tag workflow to generate, verify, and publish the signed
      archive plus signed appcast.
- [x] Isolate the tag candidate from all release inputs and require non-secret
      tag validation plus protected revalidation before any protected input is
      referenced.
- [x] Add GitHub-hosted-only self-signed trust lifecycle and real sentinel
      smoke coverage with cleanup-confirmed publication ordering.
- [x] Add the update runbook and update the packaging target contract.
- [x] Regenerate focused tests, changed-scope coverage, all seven selected
      packaging performance probes, packaging smoke, and the cached full
      menu-bar Swift suite for the final review-hardening tree.
- [ ] Complete the remaining full repository gates in GitHub CI. The local
      64 GiB host invokes the normal versioned hook, which records its
      memory-policy skip instead of running the 128 GiB full gate.
- [ ] Create and protect the external `github-release` environment, configure
      required reviewers and tag deployment policy, protect `main` and release
      tags, then provision a new Melix update key, stable self-signed code
      identity, two protected public pins, and three protected secrets only
      after explicit operator authorization. Never create or expose private
      material as part of this pull request.
- [ ] Install the first signed bootstrap release manually and validate a real
      update to the next signed release before calling the production chain
      end-to-end accepted.

## Known Bootstrap Boundary

This pull request can implement and verify every deterministic code, packaging,
and workflow boundary without handling private signing material. Production
activation remains intentionally blocked until an operator creates the
`github-release` environment with required review and tag deployment policy,
protects `main` and release tags, authorizes a new Melix-specific EdDSA identity
and stable self-signed macOS identity, stores encrypted offline backups, and
configures the three protected variables and three protected secrets. The
first release must still be installed manually and a second release must pass
real update acceptance. These external and security-sensitive steps are not
inferred from permission to edit source code.
