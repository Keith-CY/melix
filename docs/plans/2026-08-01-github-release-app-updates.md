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
6. Fail tag packaging closed unless the public-key build variable, EdDSA
   private-key secret, self-signed PKCS#12 secret, and PKCS#12 password secret
   are present and the EdDSA public/private values form the same key pair.
   Pull-request, branch, scheduled, and
   manually dispatched preview archives remain explicitly outside the supported
   update chain and do not embed an updater public key.
7. Package the complete Sparkle framework, including its updater and XPC helper
   components, under `Contents/Frameworks`. Deep-sign the finished App bundle
   only after all nested components are present, then verify the archive after
   extraction.
8. Sign the completed release bundle and every nested component with the stable
   self-signed identity, then verify its exact authority, certificate SHA-1,
   designated requirement, complete archive layout, and deep signature after
   archive extraction.
9. Initialize updates only when the running bundle contains a valid HTTPS feed,
   a non-empty public key, and the packaged Sparkle framework. A checkout build
   or preview bundle reports updates as unavailable instead of starting a
   partially configured updater.
10. Add a Software Updates card to Settings and a **Check for Updates...** item
   to the application menu. The card exposes the current version, automatic
   check preference, last check time, current stage, last failure, manual check,
   and GitHub Releases fallback.
11. Check at most once per day by default. Installing always requires an
   explicit user decision; automatic download and silent installation remain
   disabled.
12. Redact implementation details from operator errors while retaining a typed
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
- Observability mode is `minimal`: only current stage, last check time, and a
  redacted error summary are retained. No URLs with query data, HTTP bodies,
  system profile, key material, or downloaded paths are logged.

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
- [x] Add the update runbook and update the packaging target contract.
- [x] Run focused tests, changed-scope coverage, performance probes, packaging
      smoke, and the full repository gates.
- [ ] Provision a new Melix update key, stable self-signed code identity, and
      repository values only after explicit operator authorization; never
      create or expose private material as part of this pull request.
- [ ] Install the first signed bootstrap release manually and validate a real
      update to the next signed release before calling the production chain
      end-to-end accepted.

## Known Bootstrap Boundary

This pull request can implement and verify every deterministic code, packaging,
and workflow boundary without handling private signing material. Production
activation remains intentionally blocked until an operator authorizes creation
of a new Melix-specific EdDSA identity and stable self-signed macOS code
identity, stores encrypted offline backups, and configures the required Actions
variable and three secrets. That operational step is security-sensitive and is
not inferred from permission to edit source code.
