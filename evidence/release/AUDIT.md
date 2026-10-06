# qTest Publisher Release Audit

Status: **development candidate — unsupported**

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

## Outstanding release evidence

- Harness-owned qTest sandbox URL, secret, disposable project, and test cycle
- Five immutable `r2` candidate registry digests
- Matching-worker Windows image builds
- Five-platform KubernetesDirect qualification execution
- Registry vulnerability/license reports
- SPDX SBOMs, signatures, attestations, and SLSA provenance
- Complete production manifest digest and promotion execution

No customer credential or customer UAT input is required to implement the
plugin. The Harness-owned sandbox and remote repositories are operational
release prerequisites. Customer UAT starts only after promotion and delivery.
