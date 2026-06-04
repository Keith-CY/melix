# macOS App Self-Contained Python Runtime

## Goal

Fix the self-contained `Melix.app` package so the downloaded GitHub Actions
artifact launches on a macOS host that does not have the CI runner's Python
framework installed.

## Current Failure

The latest package artifact starts `Contents/MacOS/Melix.sh`, which invokes the
bundled `Contents/Resources/python-runtime/bin/python3`. That interpreter still
links to `/Library/Frameworks/Python.framework/Versions/3.13/Python`, so the
packaged app aborts on hosts without that external framework. The same artifact
also copies SwiftPM resource bundles into the `.app` root, which makes app-bundle
resource sealing fail.

## Scope

- Package the app with a uv-managed Python runtime instead of a framework Python
  from `actions/setup-python`.
- Reject packaging inputs whose Python runtime links to an external Python
  framework.
- Keep SwiftPM resource bundles under `Contents/Resources` only.
- Sign preview app archives ad-hoc before zipping so downloaded archives retain
  a valid sealed app bundle after extraction.
- Keep the shell launcher script under `Contents/Resources` and execute it from
  the native launcher through `/bin/bash`, so archive extraction does not depend
  on executable script code-signing extended attributes.
- Add focused regression tests for the workflow contract and bundle writer.

## Verification

- Focused pytest for macOS app bundle and package workflow tests.
- `git diff --check`.
- Build a local preview package and verify that the bundled
  `python-runtime/bin/python3` starts from inside the extracted app archive.
- Verify the signed archive survives zip extraction with
  `codesign --verify --deep --strict --verbose=4`.
- Smoke-launch the extracted app with an isolated short runtime directory and
  confirm both workers become ready without a dyld Python framework abort.

## Coverage and Metrics

- Coverage: focused Python tests for the touched packaging code and workflow
  contract; scoped `macos_app_bundle.py` coverage is expected to remain at or
  above 95 percent before commit.
- Metrics: `N/A`; this changes packaging correctness, not runtime serving
  performance.
