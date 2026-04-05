# Task Plan

## Goal

Close the second executable `M13.4` slice by adding repo-owned smoke verification for the shipped
API onboarding examples so the quick-start material cannot drift away from live endpoint behavior.

## Scope

- add a repo-owned onboarding smoke script for the canonical `/health`, `/v1/responses`, and
  `/v1/messages` examples
- cover the same example semantics in deterministic integration tests so CI detects drift
- tighten desktop quick-start tests so example literals, auth expectations, and endpoint shapes
  stay aligned with the smoke script
- update milestone bookkeeping so `M13.4` can be called complete once example verification lands

## Measurement Points

- the onboarding smoke must pass against a live `LiveMelixStack`
- `/health` must return route readiness for the same local gateway base URL referenced in product
  onboarding
- `/v1/responses` and `/v1/messages` must accept the canonical example payloads and headers used by
  the quick-start material
- desktop quick-start helper tests must remain aligned with the example payload text and auth
  assumptions exercised by the smoke script
- changed-line coverage for the touched handwritten executable scope must remain at or above `95%`

## Phases

1. Planning and example-verification design
   - status: completed
   - evidence:
     - inspected existing integration coverage and confirmed the repository already proves endpoint
       streaming semantics, but does not yet own a smoke that explicitly validates the product
       quick-start example payloads and headers
     - selected a bounded second slice: add one repo-owned onboarding smoke plus aligned
       integration and desktop quick-start assertions before considering broader API-page changes
2. Onboarding smoke and quick-start alignment
   - status: completed
   - evidence:
     - added `scripts/m13_api_onboarding_smoke.py` so the repository now owns one live smoke for
       the canonical `/health`, `/v1/responses`, and `/v1/messages` examples under shared-access
       authentication
     - updated the desktop quick-start snippets to match shipped streaming behavior, including
       `stream=true`, SSE-friendly curl flags, and auth-aware `/health` examples for compatibility
       guidance
     - added deterministic Python and integration coverage for the smoke script and its failure
       branches so the product quick starts cannot silently drift from live endpoint expectations
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - focused quick-start verification passed in Swift and Python, the repo-owned smoke script ran
       successfully, and `make integration-test` covered the new live example path
     - touched-scope changed-line coverage reached `100.00%` (`282/282`) across the modified Swift
       and Python executable files
     - `M13.4` is now ready to be marked completed in the execution index

## Acceptance

- operators and CI both have a repo-owned smoke that verifies the canonical onboarding examples
- example snippets remain aligned with the live local gateway payloads, headers, and base URLs
- `M13.4` has both product-visible onboarding material and executable example verification

## Risks

- example verification could give a false sense of safety if it only tests endpoint availability
  but not the specific example payloads shown in product quick starts
- the smoke could drift from UI quick-start literals if shared example text and headers are not
  asserted in desktop tests
- shared-access authentication could make the smoke flaky if the script does not derive its headers
  from repository-owned stack state

## Outcome

- m13_4_api_onboarding_completed
