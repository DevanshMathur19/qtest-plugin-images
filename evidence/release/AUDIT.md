# qTest Publisher Release Audit

Status: **promoted controlled-adoption release — customer UAT ready,
unsupported**

## Source

- Plugin source revision:
  `803c1f8de400c272a4a81395c8906bebaa6e1e84`
- Generated-image revision: `59d3ecaf70c8371cfaaa0a5065cb18327d354ccc`
- Version: `1.0.0`
- Candidate revision: `r2`
- Toolchain: Go `1.25.13`
- Platforms: Linux AMD64, Linux ARM64, Windows AMD64 LTSC 2019/2022/2025
- Source repository: `https://github.com/DevanshMathur19/qtest-publisher`
- Release-control repository:
  `https://github.com/DevanshMathur19/qtest-plugin-images`

## Completed local gates

- Unit tests
- Race detector
- `go vet`
- Linux AMD64/ARM64 and Windows AMD64 static cross-builds
- qTest HTTP contract tests
- Explicit proxy and private-CA tests
- Cancellation, throttling, ambiguous-POST, queue-state, batching, glob, JUnit,
  output, redaction, and empty-result tests
- `govulncheck` with Go 1.25.13: no reachable vulnerabilities
- Gitleaks 8.28.0: no leaks
- Deterministic Dockerfile and manifest generation
- Catalog, digest-lock, lifecycle, pipeline-contract, and manifest unit tests
- Local Linux AMD64 and ARM64 image build and empty-result smoke tests

## Superseded candidate execution

Candidate execution `SyUtWy6ZTh2qLGgzABhyDQ` was aborted after the Windows
publication topology was found to use an unverified LTSC 2022 VM pool. Its
`r1` outputs are abandoned and unsupported; immutable tags will not be
overwritten:

- Linux AMD64:
  `sha256:2792f6b2fde98ad151cf1d2ba54b04c4b348703431ca2c897dee27c5bc658a9b`
- Linux ARM64:
  `sha256:f8688d770685514ea5b91aeda1bbb9078abddc647614404330708cd45f5b54d4`

The corrected `r2` topology uses Harness Cloud for LTSC 2022 and matching
controlled VM pools for LTSC 2019 and LTSC 2025.

## Candidate publication evidence

The initial `r2` execution published four platforms. LTSC 2019 was completed
by a failed-stage retry after the live build-step timeout was corrected from
30 to 60 minutes:

- Initial execution:
  `https://app.harness.io/ng/account/gCoPSwHxS7ipOgx2iA9tOQ/all/orgs/default/projects/Drone_Plugins/pipelines/qtest_publisher_publish_candidates_dm/deployments/5eND5oqWRS6ZZn8eJxaUfw/pipeline`
- LTSC 2019 completion:
  `https://app.harness.io/ng/account/gCoPSwHxS7ipOgx2iA9tOQ/all/orgs/default/projects/Drone_Plugins/pipelines/qtest_publisher_publish_candidates_dm/deployments/pgmIoXVPTd2X1dHj9Lfn3g/pipeline`

Published immutable children:

- Linux AMD64:
  `sha256:f0e32d7691c4cc4d1e314a97328c7673f432ecd88c2c3df55b768352078d3bcf`
- Linux ARM64:
  `sha256:0f76a046f9309e00f69f1e833f742be01fd23a12ca8d9d661d92f977731c68d4`
- Windows LTSC 2019:
  `sha256:05899b3f8631e1677cdab2c69baee878c4f58f1daa7af88dacf9e5b1b92a2ec5`
- Windows LTSC 2022:
  `sha256:e11d90125587075c91e1749ad072bd6442b7743e690a3d47d9558f4560ce9cf3`
- Windows LTSC 2025:
  `sha256:062251cd72afa803f6be6b7745329b5e4199f1841d39e0df222fcb1bf501a0f8`

## KubernetesDirect qualification evidence

All five immutable children completed the empty-result contract, expected
operational-failure path, real qTest sandbox publication, and running-image
digest assertion:

- Qualification execution:
  `https://app.harness.io/ng/account/gCoPSwHxS7ipOgx2iA9tOQ/all/orgs/default/projects/Drone_Plugins/pipelines/qtest_publisher_qualify_kubernetes_dm/deployments/jDe0nOZ2T4mMQlPyrhBXqA/pipeline`
- qTest project: `31925`
- qTest cycle: `1053723`

Harness reports `IgnoreFailed` because each platform deliberately runs one
connection-failure test with an ignore failure strategy. No platform stage
failed, and all real sandbox publication and digest-assertion steps completed.

## qTest Manager UI verification

The qTest Manager UI was inspected after qualification and shows all five
platform suites under `qTest Publisher RC2 Qualification`:

- Linux AMD64, Windows LTSC 2019, and Windows LTSC 2025 use method identity.
  Each suite contains four executed runs: one passed, two failed, and one
  incomplete/skipped, matching the synthetic JUnit fixture.
- Linux ARM64 and Windows LTSC 2022 use class identity. Each suite contains one
  consolidated `io.harness.qtest.PublisherContract` run. Its failed status is
  expected because the grouped methods include assertion-failure and error
  cases.

This confirms the accepted queue jobs were rendered in the configured test
cycle with the expected suite hierarchy, identity modes, and status mapping.

## Security and license evidence

The Trivy `0.67.2` gate summary is recorded under
`evidence/release/security/summary.json` for all five immutable candidate
digests:

- No fixed HIGH or CRITICAL vulnerability gate findings
- No CRITICAL/forbidden license gate findings

Restricted, reciprocal, and unknown license counts remain recorded for review.
They do not fail the release automatically; the enforced license gate is
Trivy's CRITICAL/forbidden classification.

The promotion execution reran the gates with Trivy `0.75.0` and passed before
copying any production tags.

## Production promotion and qualification

The exact qualified child digests were copied without rebuilding to
`harness/qtest-publisher`:

- Multi-platform tag: `1.0.0`
- Manifest digest:
  `sha256:446928adf51b71dd99161b7217c3cc7e71d03eb2bd643588d9b56daf6ea4ef74`
- Immutable child tags:
  `1.0.0-linux-amd64-r2`, `1.0.0-linux-arm64-r2`,
  `1.0.0-windows-ltsc2019-amd64-r2`,
  `1.0.0-windows-ltsc2022-amd64-r2`, and
  `1.0.0-windows-ltsc2025-amd64-r2`
- Platform moving tags use the same names without `-r2`.
- Promotion execution:
  `https://app.harness.io/ng/account/gCoPSwHxS7ipOgx2iA9tOQ/all/orgs/default/projects/Drone_Plugins/pipelines/qtest_publisher_secure_promote_dm/deployments/PVKD2jhqQp66uDKFRH1Jdw/pipeline`

All five production digest references then repeated the KubernetesDirect
qualification journey. The assertions verified both the requested
`harness/qtest-publisher@sha256:...` Pod image and the running content digest:

- Production qualification execution:
  `https://app.harness.io/ng/account/gCoPSwHxS7ipOgx2iA9tOQ/all/orgs/default/projects/Drone_Plugins/pipelines/qtest_publisher_qualify_kubernetes_dm/deployments/TOjjgYlOQ5ivehxZ-2SdjQ/pipeline`

The execution status is `IgnoreFailed` only because each platform includes the
intentional ignored connection-failure contract.

## Customer handoff

- Customer guide:
  `https://harness.atlassian.net/wiki/spaces/CI1/pages/24347541549`
- Delivery-thread draft: `Dr0C7L2SANJ1` in `cs-elevance-health-devops`
- Customer-facing image: `harness/qtest-publisher:1.0.0`
- Handoff state: ready for customer UAT under controlled adoption

## Deferred support gates

- SPDX SBOMs, signatures, attestations, and SLSA provenance
- Customer environment UAT and final support approval

These gates are intentionally post-promotion, matching the controlled-adoption
process used for the previously delivered plugin images. Their deferral does
not block customer UAT, but `supported` remains `false` until final support
approval.

No customer credential or customer UAT input was required to implement or
qualify the plugin. The Harness-owned sandbox and production repository were
operational release prerequisites. Customer UAT starts after this promotion
and delivery handoff.
