# qTest Publisher Release Audit

Status: **development candidate — unsupported**

## Source

- Plugin source revision:
  `816464df142eec022158fe7685772d8eabd65b82`
- Generated-image revision: `e985020e590003292d1d0204293e8b14c75d9e51`
- Version: `1.0.0`
- Toolchain: Go `1.25.13`
- Platforms: Linux AMD64, Linux ARM64, Windows AMD64 LTSC 2019/2022/2025

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

## Outstanding release evidence

- A standalone remote source repository and remote release-controls repository
- Harness-owned qTest sandbox URL, secret, disposable project, and test cycle
- Five immutable candidate registry digests
- Matching-worker Windows image builds
- Five-platform KubernetesDirect qualification execution
- Registry vulnerability/license reports
- SPDX SBOMs, signatures, attestations, and SLSA provenance
- Complete production manifest digest and promotion execution

No customer credential or customer UAT input is required to implement the
plugin. The Harness-owned sandbox and remote repositories are operational
release prerequisites. Customer UAT starts only after promotion and delivery.
