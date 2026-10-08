import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(release)
MANIFEST_SPEC = importlib.util.spec_from_file_location(
    "validate_manifest", ROOT / "scripts" / "validate_manifest.py"
)
validate_manifest = importlib.util.module_from_spec(MANIFEST_SPEC)
assert MANIFEST_SPEC.loader
MANIFEST_SPEC.loader.exec_module(validate_manifest)


class ReleaseTests(unittest.TestCase):
    @staticmethod
    def fresh_lock():
        value = json.loads(
            (ROOT / "locks" / "platform-child-digests.json").read_text()
        )
        for child in value["children"].values():
            child.update(
                {
                    "digest": None,
                    "registry_compressed_size_bytes": 0,
                    "published": False,
                    "qualified": False,
                    "promoted": False,
                    "supported": False,
                    "config_digest": "",
                    "evidence": {},
                }
            )
        value.update(
            {
                "publication_state": "unpublished",
                "qualification_state": "unqualified",
                "promotion_state": "unpromoted",
                "supported": False,
            }
        )
        return value

    def test_catalog_pins_all_five_platform_children(self):
        catalog = release.catalog()
        self.assertEqual(release.EXPECTED_PLATFORMS, set(catalog["platforms"]))
        self.assertFalse(catalog["supported"])
        digests = {
            platform["runtime_parent"]["digest"]
            for platform in catalog["platforms"].values()
        }
        self.assertEqual(5, len(digests))
        self.assertTrue(all(release.DIGEST_RE.fullmatch(item) for item in digests))
        self.assertEqual(
            catalog["plugin"]["go_version"],
            catalog["build_tools"]["go_windows_amd64"]["version"],
        )
        self.assertTrue(
            release.HEX_RE.fullmatch(
                catalog["build_tools"]["go_windows_amd64"]["sha256"]
            )
        )
        for name, item in catalog["platforms"].items():
            if name.startswith("windows-"):
                self.assertTrue(
                    release.DIGEST_RE.fullmatch(item["builder_parent"]["digest"])
                )

    def test_generator_uses_minimal_pinned_runtimes(self):
        catalog = release.catalog()
        rendered = release.render_all(catalog)
        self.assertEqual(5, len(rendered))
        linux = rendered[Path("docker/Dockerfile.linux.amd64")]
        self.assertIn("gcr.io/distroless/static-debian12@sha256:", linux)
        self.assertIn("USER 65532:65532", linux)
        self.assertIn('ENTRYPOINT ["/qtest-publisher"]', linux)
        for name in ("ltsc2019", "ltsc2022", "ltsc2025"):
            windows = rendered[Path(f"docker/Dockerfile.windows.amd64.{name}")]
            self.assertIn("mcr.microsoft.com/windows/nanoserver@sha256:", windows)
            self.assertIn("qtest-publisher.exe", windows)
            self.assertIn("USER ContainerUser", windows)
            self.assertNotIn("ContainerAdministrator", windows)
            self.assertNotIn("servercore", windows.lower())
        self.assertTrue(all(":latest" not in content for content in rendered.values()))

    def test_manifest_has_linux_and_exact_windows_descriptors(self):
        manifest = release.render_manifest(release.catalog())
        self.assertEqual(5, manifest.count("    platform:"))
        self.assertIn("architecture: arm64", manifest)
        self.assertIn("os: linux", manifest)
        self.assertIn('version: "10.0.17763.9245"', manifest)
        self.assertIn('version: "10.0.20348.5622"', manifest)
        self.assertIn('version: "10.0.26100.33438"', manifest)

    def test_tags_are_immutable_and_platform_specific(self):
        catalog = release.catalog()
        immutable = {
            release.child_tag(catalog, platform)
            for platform in release.EXPECTED_PLATFORMS
        }
        moving = {
            release.moving_tag(catalog, platform)
            for platform in release.EXPECTED_PLATFORMS
        }
        self.assertEqual(5, len(immutable))
        self.assertEqual(5, len(moving))
        self.assertTrue(all("latest" not in tag for tag in immutable | moving))

    def test_generate_and_check_are_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module test\n")
            (root / "plugin").mkdir()
            release.command_generate(SimpleNamespace(source_root=str(root)))
            with mock.patch.object(release, "validate_source"):
                release.command_check(SimpleNamespace(source_root=str(root)))

    def test_current_lock_is_fail_closed(self):
        lock = release.validate_child_lock(release.catalog())
        self.assertIn(
            lock["publication_state"], {"unpublished", "partial", "published"}
        )
        self.assertIn(
            lock["qualification_state"], {"unqualified", "partial", "qualified"}
        )
        self.assertIn(
            lock["promotion_state"], {"unpromoted", "partial", "promoted"}
        )
        self.assertFalse(lock["supported"])

    def test_lock_validation_does_not_require_source_checkout(self):
        release.command_validate_lock(SimpleNamespace())

    def test_lifecycle_requires_publish_then_qualify(self):
        source = self.fresh_lock()
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "lock.json"
            lock_path.write_text(json.dumps(source))
            with mock.patch.object(release, "CHILD_LOCK_PATH", lock_path):
                published = SimpleNamespace(
                    command="record-published",
                    platform="linux-amd64",
                    digest="sha256:" + "a" * 64,
                    size=123,
                    evidence="harness://execution/publish",
                )
                release.command_record(published)
                release.command_record(
                    SimpleNamespace(
                        command="record-qualified",
                        platform="linux-amd64",
                        evidence="harness://execution/qualify",
                    )
                )
                release.command_record(
                    SimpleNamespace(
                        command="record-promoted",
                        platform="linux-amd64",
                        evidence="harness://execution/promote",
                    )
                )
                lock = release.validate_child_lock(release.catalog())
        self.assertTrue(lock["children"]["linux-amd64"]["promoted"])
        self.assertEqual("partial", lock["promotion_state"])
        self.assertFalse(lock["supported"])

    def test_duplicate_child_digest_is_rejected(self):
        source = self.fresh_lock()
        digest = "sha256:" + "b" * 64
        for platform in ("linux-amd64", "linux-arm64"):
            source["children"][platform].update(
                {
                    "digest": digest,
                    "registry_compressed_size_bytes": 1,
                    "published": True,
                    "evidence": {"publication": "harness://execution/publish"},
                }
            )
        source["publication_state"] = "partial"
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "lock.json"
            lock_path.write_text(json.dumps(source))
            with mock.patch.object(release, "CHILD_LOCK_PATH", lock_path):
                with self.assertRaisesRegex(release.GateError, "duplicate"):
                    release.validate_child_lock(release.catalog())

    def test_wrong_windows_builder_is_rejected(self):
        with self.assertRaisesRegex(release.GateError, "builder mismatch"):
            release.validate_builder(
                release.catalog(), "windows-amd64-ltsc2019", "ltsc2022"
            )
        release.validate_builder(release.catalog(), "linux-arm64", None)

    def test_release_pipelines_cover_all_platforms_and_gates(self):
        pipeline_root = ROOT / ".harness"
        publish = (pipeline_root / "publish-candidates.yaml").read_text()
        qualify = (pipeline_root / "qualify-kubernetes.yaml").read_text()
        promote = (pipeline_root / "secure-promote.yaml").read_text()

        self.assertEqual(5, publish.count("type: BuildAndPushDockerRegistry"))
        self.assertEqual(2, publish.count("type: VM"))
        self.assertEqual(4, publish.count("runtime: {type: Cloud, spec: {}}"))
        self.assertEqual(2, publish.count("delegateSelectors: [windows-vm]"))
        self.assertNotIn("windows2022BuilderPool", publish)
        self.assertIn("name: Publish Windows LTSC 2022", publish)
        self.assertEqual(3, publish.count("Get-ItemPropertyValue"))
        self.assertIn("Expected Windows build 20348", publish)
        self.assertIn("refusing to overwrite immutable tag", publish)
        self.assertEqual(5, publish.count("caching: false"))
        self.assertEqual(6, publish.count("timeout: 60m"))
        self.assertEqual(5, publish.count("slsa_provenance: {enabled: true}"))
        self.assertGreaterEqual(
            publish.count(release.catalog()["plugin"]["source_revision"]), 2
        )
        expected_assets = release.render_all(release.catalog())
        expected_assets[Path("docker/manifest.tmpl")] = release.render_manifest(
            release.catalog()
        )
        for path, content in expected_assets.items():
            digest = hashlib.sha256(content.encode()).hexdigest()
            self.assertIn(f"{digest}  {path}", publish)
        for platform in release.EXPECTED_PLATFORMS:
            self.assertEqual(2, publish.count(release.child_tag(release.catalog(), platform)))
        self.assertIn("go test -race ./...", publish)
        self.assertIn("govulncheck@v1.1.4", publish)
        self.assertIn("staticcheck@v0.6.1", publish)
        self.assertIn("gitleaks:v8.28.0", publish)
        self.assertNotIn(":latest", publish)

        self.assertIn("connectorRef: dmgitcon", qualify)
        self.assertIn(
            "name: linuxAmd64KubernetesConnector, type: String, value: gcopdmlinuxamd64",
            qualify,
        )
        self.assertIn(
            "name: linuxArm64KubernetesConnector, type: String, value: gcopdmarm64",
            qualify,
        )
        self.assertIn("name: Require five digest-pinned candidates", qualify)
        self.assertIn("published/promoted", qualify)
        self.assertIn("child[\"promoted\"]", qualify)
        self.assertIn("python3 scripts/release.py validate-lock", qualify)
        self.assertEqual(5, qualify.count("suite_name: qtest-qualification-"))
        self.assertEqual(5, qualify.count('reuse_suite: "true"'))
        self.assertEqual(5, qualify.count("name: Empty result contract"))
        self.assertEqual(5, qualify.count("name: Expected operational failure"))
        self.assertEqual(5, qualify.count("EXPECTED_FAILURE_STATUS:"))
        self.assertEqual(5, qualify.count("name: Publish sandbox JUnit"))
        self.assertEqual(
            5,
            qualify.count("Assert running image digest")
            + qualify.count("Assert runtime and image digest"),
        )
        self.assertEqual(5, qualify.count("type: KubernetesDirect"))
        self.assertIn("node.kubernetes.io/windows-build: \"10.0.26100\"", qualify)

        self.assertIn("connectorRef: dmgitcon", promote)
        self.assertIn('crane index append "$@" -t "$production_index"', promote)
        self.assertNotIn("candidate_index", promote)
        self.assertLess(
            promote.index("name: Vulnerability and license gates"),
            promote.index("name: Promote verified artifacts by digest"),
        )
        self.assertLess(
            promote.index("crane auth login index.docker.io"),
            promote.index("crane copy \"$source\" \"$immutable_ref\""),
        )
        self.assertIn("DOCKER_USERNAME: harnesscie", promote)
        self.assertIn(
            'DOCKER_PASSWORD: <+secrets.getValue("Harness_Dockerhub_PAT")>',
            promote,
        )
        for required in (
            "trivy image",
            "crane copy",
            "validate_manifest.py",
            "unqualified child",
        ):
            self.assertIn(required, promote)
        self.assertIn(
            "--exit-code 1 --severity CRITICAL --scanners license", promote
        )
        self.assertIn("version=v0.75.0", promote)
        self.assertNotIn("cosign", promote)
        self.assertNotIn("syft", promote)
        self.assertNotIn(":latest", promote)

    def test_qualification_assets_are_present(self):
        linux_assertion = (
            ROOT / "scripts" / "assert_kubernetes_image.py"
        ).read_text()
        windows_assertion = (
            ROOT / "scripts" / "assert-kubernetes-image.ps1"
        ).read_text()
        for assertion in (linux_assertion, windows_assertion):
            self.assertIn("Requested image verified:", assertion)
            self.assertIn("Running digest verified:", assertion)
        self.assertIn('pod_resource.get("spec", {})', linux_assertion)
        self.assertIn("$podResource.spec.containers", windows_assertion)
        fixture = ROOT / "tests" / "fixtures" / "junit" / "TEST-qtest-publisher.xml"
        self.assertIn("<failure", fixture.read_text())
        self.assertIn("<error", fixture.read_text())
        self.assertIn("<skipped", fixture.read_text())

    def test_complete_manifest_validator_matches_all_five_locked_children(self):
        catalog = release.catalog()
        lock = self.fresh_lock()
        manifests = []
        for index, (name, item) in enumerate(catalog["platforms"].items(), start=1):
            digest = "sha256:" + format(index, "064x")
            lock["children"][name]["digest"] = digest
            platform = {
                "os": "windows" if name.startswith("windows-") else "linux",
                "architecture": "arm64" if name == "linux-arm64" else "amd64",
            }
            if name.startswith("windows-"):
                platform["os.version"] = item["os_version"]
            manifests.append({"digest": digest, "platform": platform})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index_path = root / "index.json"
            lock_path = root / "lock.json"
            index_path.write_text(json.dumps({"manifests": manifests}))
            lock_path.write_text(json.dumps(lock))
            with mock.patch("sys.argv", ["validate_manifest.py", str(index_path), str(lock_path)]):
                validate_manifest.main()


if __name__ == "__main__":
    unittest.main()
