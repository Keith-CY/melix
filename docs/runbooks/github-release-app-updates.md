# GitHub Release App Updates

## Purpose

Define the signed in-App update path for self-contained `Melix.app` archives
published from version tags. This path does not require an Apple Developer ID,
but it does require an independent Melix EdDSA signing key, a stable self-signed
macOS code-signing identity, and a complete Sparkle framework in every release
App.

## Trust Boundary

Sparkle `2.9.4` owns feed retrieval, archive download, EdDSA verification,
extraction, atomic App replacement, recovery, and relaunch. Melix owns the
operator-facing state and the release workflow that produces the signed feed.

Every update-enabled release is signed with the stable self-signed identity
`Melix GitHub Release Signing`. Its designated requirement is verified before
and after archiving so macOS sees one local code identity across releases.
Preview bundles remain ad-hoc signed and never contain update configuration.

The self-signed certificate does not establish Apple trust, notarization, or a
Developer ID identity. The independent Sparkle EdDSA signature authenticates
the archive and signed appcast as Melix releases. Neither mechanism removes
Gatekeeper or quarantine warnings that may apply to the first manual
installation.

Never reuse another product's Sparkle key or self-signed code identity. A Melix key compromise would allow
an attacker to produce updates accepted by existing Melix installations, so
the private key is release infrastructure, not a repository or developer-shell
convenience.

## Build Classes

The package workflow produces three classes of App bundle:

| Build class | Trigger | Update configuration |
| --- | --- | --- |
| Preview | branch, pull request, schedule, or manual dispatch | bundle ID `io.melix.menubar.preview`, target `macos_app_bundle_preview`, ad-hoc signature; Sparkle is bundled because the executable links it, but `SUFeedURL` and `SUPublicEDKey` are omitted and in-App updates are unavailable |
| Isolated release candidate | push of a validated stable `v<major>.<minor>.<patch>` tag | bundle ID `io.melix.menubar.release-candidate`, target `macos_app_bundle_github_release_candidate`, ad-hoc signature, independently named archive, and no feed, public update key, or certificate pins; it is a workflow artifact that can never be attached by the preview publishing path |
| Signed release | protected finalization of that tag candidate | bundle ID `io.melix.menubar`, target `macos_app_bundle_github_release`, stable self-signed code identity, stable GitHub Release feed and Melix public EdDSA key; generates and verifies a signed `appcast.xml` before publishing |

The stable feed is:

```text
https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml
```

The App checks at most once per day when automatic checks are enabled. It does
not silently download or install an update. Sparkle presents the release and
requires explicit user confirmation before installation.

## Release Credential Interface

The fixed `github-release` GitHub Actions environment must eventually provide
these protected values:

- Environment variable `SPARKLE_EDDSA_PUBLIC_KEY`: the base64-encoded 32-byte Melix
  public Ed25519 key embedded in tagged release bundles.
- Environment variable `MELIX_SIGNING_CERTIFICATE_SHA256`: the independently
  recorded 64-hex SHA-256 leaf-certificate pin.
- Environment variable `MELIX_SIGNING_CERTIFICATE_SHA1`: the independently
  recorded 40-hex SHA-1 leaf-certificate pin used by the macOS designated
  requirement. Neither expected pin is derived from the supplied PKCS#12.
- Environment secret `SPARKLE_EDDSA_PRIVATE_KEY`: the matching private seed used by
  the tag release job through standard input only.
- Environment secret `MELIX_SIGNING_CERTIFICATE_P12`: the base64-encoded PKCS#12
  export of the stable self-signed identity named exactly
  `Melix GitHub Release Signing`.
- Environment secret `MELIX_SIGNING_CERTIFICATE_PASSWORD`: the PKCS#12 export
  password.

All six values are required for protected version-tag finalization. The
workflow validates the tag and candidate receipts before the first expression
that references any protected variable or secret, then fails closed before
publishing if a value is absent, invalid, or inconsistent. Preview and
candidate jobs do not read these values and remain outside the update trust
chain.

Key and certificate creation, backup, and GitHub provisioning require explicit
operator authorization and are intentionally not performed by repository
bootstrap, tests, or packaging commands. After authorization, generate a new
EdDSA key with the `generate_keys` tool from the repository-pinned Sparkle
artifact and a Melix-specific account name. Separately create a long-lived
self-signed code-signing certificate whose common name is exactly
`Melix GitHub Release Signing`, then export its identity as password-protected
PKCS#12. Store encrypted offline recovery copies of both identities and record
both public certificate pins independently at that time. Put only the EdDSA
public key and two certificate pins in environment variables, and put the three
private values only in environment secrets. Do not print private material or place it in a
repository file, workflow artifact, issue, pull request, or log. The workflow
passes the masked PKCS#12 password only to `security import`, reads the EdDSA
private key only from standard input, and removes administrator trust plus the
temporary keychain, PKCS#12, PEM, and sentinel before publishing any artifact.

Production activation is blocked until GitHub itself is configured outside
this repository:

1. create the environment named exactly `github-release`;
2. require an authorized reviewer and restrict deployments to protected stable
   release tags;
3. configure the six protected values above in that environment;
4. protect `main` with the required reviews and status checks; and
5. protect release tags against deletion, rewriting, and unauthorized creation.

The workflow validates ancestry and version monotonicity, but repository code
cannot substitute for these environment, branch, and tag protections. Do not
publish an update-enabled release until all five controls are confirmed.

## Tag Release Flow

For a tag push, `.github/workflows/package-self-contained-app.yml`:

1. a non-secret Linux job checks an exact canonical stable SemVer tag, tag
   commit equality with `GITHUB_SHA`, ancestry from freshly fetched
   `origin/main`, and strict numeric monotonicity over all stable tags;
2. an ordinary macOS package job builds the tagged source as the isolated
   candidate, without a feed, update key, certificate pin, or private input;
3. the candidate receipt binds tag, source SHA, bundle-tree digest, and archive
   digest, and the candidate is uploaded under an independent artifact and
   archive name that the old preview attachment path does not publish;
4. the fixed `github-release` environment job checks out the validated source,
   repeats tag validation against current `origin/main`, byte-compares the two
   tag receipts, extracts the candidate, and revalidates every candidate
   binding before any protected input is referenced;
5. it validates the three public variables, resolves the repository-pinned
   Sparkle tools, decodes the PKCS#12, and requires its leaf certificate to
   match the independently provisioned SHA-256 and SHA-1 pins, exact common
   name, self-signed subject/issuer, code-signing EKU, and private key;
6. only on a GitHub-hosted macOS runner, it saves the exact user keychain search
   list, creates an ephemeral keychain, adds code-signing-only administrator
   trust with passwordless `sudo`, and proves a real hardened-runtime sentinel
   signature;
7. it converts the candidate into the stable bundle, embeds feed, public key,
   certificate pins, candidate provenance, and `LSMinimumSystemVersion=15.0`;
8. it signs in Sparkle's documented order: `Installer.xpc`, `Downloader.xpc`
   with preserved entitlements, `Autoupdate` with preserved entitlements,
   `Updater.app`, `Sparkle.framework`, other Mach-O files, and the outer App;
   every target gets hardened runtime and explicit strict verification, and
   `codesign --deep` is never used;
9. it archives and extracts the result, then rechecks layout, runtime,
   entitlements, exact authority, both certificate hashes, and designated
   requirement for every required helper and outer code object;
10. it derives the EdDSA public key from the protected private seed in memory,
    requires a match, generates a one-version/no-delta appcast, requires its
    minimum system version to be exactly `15.0`, and verifies both appcast and
    archive signatures;
11. an unconditional cleanup removes administrator trust, restores the exact
    original search list, deletes the ephemeral keychain, PKCS#12, PEM, and
    sentinel, and writes a cleanup receipt; and
12. only `cleanup_confirmed=true` permits the stable archive and `appcast.xml`
    to be published and downstream distribution workflows to be triggered.

No candidate archive or stable archive is attached to a version-tag release
unless all signed-update and cleanup steps succeed.

## Bootstrap And Acceptance

The first signed release is a bootstrap release: existing manual or preview
installations do not contain the public key and cannot enter the update chain.
Install that bootstrap release manually, then validate the next signed release
from the installed App.

Acceptance requires all of the following evidence:

1. the installed bootstrap App reports its expected version and exposes
   **Check for Updates...** in the App menu and Settings;
2. the next release is discovered through the stable feed;
3. archive download, signature verification, extraction, replacement, and
   relaunch complete through Sparkle;
4. the relaunched App reports the new version, retains the existing `MELIX_HOME`
   operator state, and preserves the same designated requirement;
5. a tampered archive or signature is rejected without replacing the current
   App;
6. the previous App remains recoverable if replacement or relaunch fails.

Until this two-release acceptance is complete, describe the implementation as
update-capable but not production-accepted.

Cancellation is not a failed update. Sparkle error codes `4007` and `4008` and
`userDidCancelDownload` return the controller to an idle, retryable state and
clear any stale failure. A generic network error is `metadata` before an update
is discovered and `download` after discovery. Delegate and cycle-finish
callbacks must emit at most one terminal cancellation or failure.

## Recovery And Key Rotation

If metadata, download, authentication, extraction, replacement, or relaunch
fails, do not bypass Sparkle verification. Retry from the App after confirming
the GitHub Release assets, or download the trusted release manually and retain
the previous App until the new copy launches successfully. User state remains
outside the bundle under `MELIX_HOME` and must not be removed as part of App
recovery.

This implementation intentionally does not support in-band key rotation.
Changing, losing, or compromising either the EdDSA identity or self-signed code
identity requires an incident notice, revocation of the affected protected
values, creation of a new identity, and a new manually installed bootstrap App.
Existing installations must never accept a replacement key merely because a
new appcast advertises it. A code-identity change also changes the designated
requirement and may require users to approve privacy permissions again. Keep
multiple encrypted offline backups and rotate only through this manual
rebootstrap procedure.

## Verification

Run the focused package and update tests before a release workflow change:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_validate_macos_release_tag.py \
  services/mlx-worker-python/tests/test_macos_release_candidate.py \
  services/mlx-worker-python/tests/test_macos_self_signed_identity.py \
  services/mlx-worker-python/tests/test_finalize_macos_release_candidate.py \
  services/mlx-worker-python/tests/test_packaging_targets.py \
  services/mlx-worker-python/tests/test_macos_app_bundle.py \
  services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py

xcrun swift test --package-path apps/macos-menubar \
  --filter SoftwareUpdateControllerTests
```

The full repository verification and release gates remain required by
`AGENTS.md` and `docs/runbooks/phase-8-release-gates.md`.

The trust unit tests are pure/mocked and are safe locally. Never run
`macos_self_signed_identity.py prepare` on a developer Mac; the entrypoint also
rejects anything other than a GitHub-hosted macOS runner. The pull-request
`self-signed-trust-smoke` job is the sole real add-trust/sentinel/cleanup test.

On the 64 GiB Mac used for this implementation, the versioned pre-commit hook
must be invoked normally and is expected to print its policy skip because full
hook execution requires at least 128 GiB. Record that output honestly. The
focused suites, cached full menu-bar Swift suite, changed-scope coverage, and
GitHub CI are separate required evidence; do not describe the memory-policy
skip as a passed full repository gate.
