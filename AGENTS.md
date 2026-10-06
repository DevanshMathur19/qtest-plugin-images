# qTest Plugin Images

- This release-control repository owns platform Dockerfile generation, catalog
  validation, digest locks, qualification, promotion policy, and evidence for
  `qtest-publisher`.
- Plugin source remains in the standalone `qtest-publisher` repository.
- Support Linux AMD64/ARM64 and Windows AMD64 LTSC 2019/2022/2025.
- Windows containers run only on matching 17763/20348/26100 workers.
- Generate Dockerfiles from `catalog/versions.yaml`; do not hand-edit them.
- Pin each runtime parent by platform-child digest.
- Never bake tokens, tenant URLs, customer certificates, proxies, or
  destination identifiers into images.
- Publish immutable platform tags and promote qualified digests without
  rebuilding.
- Keep `supported` false until every release gate passes.
