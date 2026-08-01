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

The package workflow produces two classes of App bundle:

| Build class | Trigger | Update configuration |
| --- | --- | --- |
| Preview | branch, pull request, schedule, or manual dispatch | bundle ID `io.melix.menubar.preview`, target `macos_app_bundle_preview`, ad-hoc signature; Sparkle is bundled because the executable links it, but `SUFeedURL` and `SUPublicEDKey` are omitted and in-App updates are unavailable |
| Signed release | push of a `v*` tag | bundle ID `io.melix.menubar`, target `macos_app_bundle_github_release`, stable self-signed code identity, stable GitHub Release feed and Melix public EdDSA key; generates and verifies a signed `appcast.xml` before publishing |

The stable feed is:

```text
https://github.com/Keith-CY/melix/releases/latest/download/appcast.xml
```

The App checks at most once per day when automatic checks are enabled. It does
not silently download or install an update. Sparkle presents the release and
requires explicit user confirmation before installation.

## Release Credential Interface

The repository must eventually provide these GitHub Actions values:

- Actions variable `SPARKLE_EDDSA_PUBLIC_KEY`: the base64-encoded 32-byte Melix
  public Ed25519 key embedded in tagged release bundles.
- Actions secret `SPARKLE_EDDSA_PRIVATE_KEY`: the matching private seed used by
  the tag release job through standard input only.
- Actions secret `MELIX_SIGNING_CERTIFICATE_P12`: the base64-encoded PKCS#12
  export of the stable self-signed identity named exactly
  `Melix GitHub Release Signing`.
- Actions secret `MELIX_SIGNING_CERTIFICATE_PASSWORD`: the PKCS#12 export
  password.

All four values are required for a version-tag release. The workflow fails
closed before publishing release artifacts if any value is absent or invalid,
or if the configured EdDSA public key does not match the private seed.
Preview artifacts do not read these values and remain intentionally outside the
update trust chain.

Key and certificate creation, backup, and GitHub provisioning require explicit
operator authorization and are intentionally not performed by repository
bootstrap, tests, or packaging commands. After authorization, generate a new
EdDSA key with the `generate_keys` tool from the repository-pinned Sparkle
artifact and a Melix-specific account name. Separately create a long-lived
self-signed code-signing certificate whose common name is exactly
`Melix GitHub Release Signing`, then export its identity as password-protected
PKCS#12. Store encrypted offline recovery copies of both identities. Put only
the EdDSA public key in the Actions variable and put the three private values
only in their Actions secrets. Do not print private material or place it in a
repository file, workflow artifact, issue, pull request, or log. The workflow
passes the masked PKCS#12 password only to `security import`, reads the EdDSA
private key only from standard input, and removes the temporary PKCS#12 file
and keychain before publishing any artifact.

## Tag Release Flow

For a push of a `v*` tag, `.github/workflows/package-self-contained-app.yml`:

1. builds the App and all bundled runtimes from the tagged commit;
2. imports the stable self-signed PKCS#12 identity into an ephemeral keychain,
   verifies its exact name and self-signed subject/issuer, and resolves its
   public certificate SHA-1;
3. validates the EdDSA public key and embeds the release bundle ID, packaging
   target, feed URL, and public key in
   `Contents/Info.plist`;
4. copies the complete Sparkle framework, including `Updater.app` and both XPC
   services, into `Contents/Frameworks`;
5. adds and verifies the executable rpath for `Contents/Frameworks`;
6. signs nested code and the complete App with the stable identity, archives
   it, extracts it, and verifies the archive layout, deep signature, exact
   authority, certificate SHA-1, and designated requirement;
7. deletes the ephemeral keychain and PKCS#12 file before artifact upload;
8. derives the EdDSA public key from the new-format private seed in memory,
   requires it to match the configured public key, and then passes the private
   key to the pinned Sparkle tools through standard input;
9. generates a one-version, no-delta `appcast.xml`, verifies the appcast
   signature, extracts the enclosure signature, and verifies the archive;
10. publishes both the archive and `appcast.xml` on the matching GitHub Release.

No archive is attached to a version-tag release unless all signed-update steps
succeed.

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

## Recovery And Key Rotation

If metadata, download, authentication, extraction, replacement, or relaunch
fails, do not bypass Sparkle verification. Retry from the App after confirming
the GitHub Release assets, or download the trusted release manually and retain
the previous App until the new copy launches successfully. User state remains
outside the bundle under `MELIX_HOME` and must not be removed as part of App
recovery.

Rotate the EdDSA signing key through a transition release signed by the current key
and embedding the next public key. Only later releases may be signed solely by
the next key. If the current private key is lost or compromised before a
transition release, existing installations cannot securely trust a replacement
key through the update channel; require a new manual bootstrap installation and
publish an incident notice. Replacing or losing the self-signed code identity
also changes the App's designated requirement and can require users to approve
privacy permissions again. Keep multiple encrypted offline backups of both
identities and never rotate either casually.

## Verification

Run the focused package and update tests before a release workflow change:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_macos_app_bundle.py \
  services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py

xcrun swift test --package-path apps/macos-menubar \
  --filter SoftwareUpdateControllerTests
```

The full repository verification and release gates remain required by
`AGENTS.md` and `docs/runbooks/phase-8-release-gates.md`.
