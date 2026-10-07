# qTest Publisher Images

Release controls for the generic `harness/qtest-publisher` plugin on:

- Linux AMD64
- Linux ARM64
- Windows AMD64 LTSC 2019
- Windows AMD64 LTSC 2022
- Windows AMD64 LTSC 2025

Plugin source and generated Dockerfiles live in the standalone
`qtest-publisher` repository. This directory owns the exact source revision,
runtime parent child digests, deterministic Dockerfile and manifest generation,
immutable child digest state, qualification definitions, and promotion policy.

## Source validation

```bash
python3 scripts/release.py validate \
  --source-root /path/to/qtest-publisher
python3 scripts/release.py generate \
  --source-root /path/to/qtest-publisher
python3 scripts/release.py check \
  --source-root /path/to/qtest-publisher
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Build binaries

```bash
python3 scripts/release.py build-binaries \
  --source-root /path/to/qtest-publisher
```

This produces static binaries for Linux AMD64/ARM64 and Windows AMD64. Windows
container images must still be packaged and tested on matching controlled
Windows workers.

All release state begins unpublished and unsupported. Source validation,
cross-compilation, or a candidate build is not a support claim.

## Release sequence

1. `.harness/publish-candidates.yaml` validates the source and publishes five
   immutable platform children. Windows binaries are compiled with a
   checksum-verified Go SDK and packaged on matching Windows VM pools.
2. Record each registry digest and publication execution with
   `scripts/release.py record-published`.
3. `.harness/qualify-kubernetes.yaml` runs empty-result and real sandbox
   publication contracts on KubernetesDirect Linux AMD64/ARM64 and Windows
   LTSC 2019/2022/2025. Every stage asserts the running image ID.
4. Record each successful stage with `scripts/release.py record-qualified`.
5. `.harness/secure-promote.yaml` blocks on the complete qualified lock, runs
   vulnerability and license gates, copies children by digest without
   rebuilding, and validates the five-platform index.

Promotion is a controlled-adoption milestone and does not set `supported:
true`. SBOM, signature, provenance, and final support approval remain explicit
post-promotion gates, matching the process used by the other delivered image
families.

The qualification pipeline requires a Harness-owned qTest sandbox URL, bearer
token, disposable project ID, and test-cycle ID as runtime inputs. No qTest
credential or tenant URL is stored in source or an image. Customer UAT occurs
after delivery and is not a release gate.
