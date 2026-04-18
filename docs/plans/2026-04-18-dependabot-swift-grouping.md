# Dependabot Swift Grouping Plan

## Scope

This plan reduces duplicate Dependabot pull requests for Swift gRPC dependency updates across the
Melix monorepo. It changes only repository automation configuration and does not change runtime,
protocol, generated artifact, Python, or Swift source behavior.

## Root Cause

Melix has several Swift package manifests:

- `/Package.swift`
- `/packages/protocol/swift/Package.swift`
- `/services/mlx-text-worker-swift/Package.swift`
- `/services/control-plane-swift/Package.swift`
- `/apps/macos-menubar/Package.swift`

The previous Dependabot configuration declared a separate Swift updater for each directory. When the
same gRPC Swift dependency family released compatible updates, Dependabot opened one pull request per
manifest directory. Each pull request triggered the macOS Swift, Python, packaging, protocol drift,
and integration queues, creating repeated CI load for dependency changes that should be reviewed as
one family update.

## Planned Change

Use Dependabot's `directories` key to cover all Swift package manifests from one Swift ecosystem
entry. Add a single-ecosystem `swift-grpc` group with the pattern `github.com/grpc/*`.

This keeps non-gRPC Swift dependencies outside the group so unrelated Apple, Swift Server, or other
Swift package updates can still surface separately. It also avoids a broad all-Swift dependency
rollup, which would make failures harder to isolate.

## Success Metrics

- One scheduled gRPC Swift dependency family update should produce one Dependabot PR instead of one
  PR per Swift package directory.
- The resulting PR should still include all Swift lockfile changes needed for the affected manifests.
- Non-gRPC Swift dependencies should remain independently reviewable.
- Changed-scope coverage is `N/A` because this is configuration-only automation behavior.

## Verification

Local verification for this slice:

```bash
ruby -ryaml -e 'data = YAML.load_file(".github/dependabot.yml"); raise "bad version" unless data["version"] == 2; swift = data["updates"].select { |entry| entry["package-ecosystem"] == "swift" }; raise "expected one swift updater, got #{swift.length}" unless swift.length == 1; expected_dirs = ["/", "/packages/protocol/swift", "/services/mlx-text-worker-swift", "/services/control-plane-swift", "/apps/macos-menubar"]; raise "bad directories" unless swift[0]["directories"] == expected_dirs; raise "bad swift-grpc patterns" unless swift[0].dig("groups", "swift-grpc", "patterns") == ["github.com/grpc/*"]; puts "dependabot swift grouping config ok"'
git diff --check
```

GitHub-side verification happens on the next scheduled Dependabot run. The expected observable
outcome is a consolidated `swift-grpc` pull request when a dependency matching `github.com/grpc/*`
has updates in more than one Swift package directory.

## Known Gaps

- This change does not resolve the existing `pr-evidence` mismatch for Dependabot-generated pull
  request bodies.
- This change does not rerun or repair currently open Dependabot pull requests. Existing PRs can be
  closed and recreated, or allowed to age out after this configuration lands.
