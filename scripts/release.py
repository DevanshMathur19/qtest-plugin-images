#!/usr/bin/env python3
"""Generate, validate, build, and gate qTest publisher platform releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as host_platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "versions.yaml"
CHILD_LOCK_PATH = ROOT / "locks" / "platform-child-digests.json"
DEFAULT_SOURCE_ROOT = ROOT.parent.parent / "qtest-publisher"
EXPECTED_PLATFORMS = {
    "linux-amd64",
    "linux-arm64",
    "windows-amd64-ltsc2019",
    "windows-amd64-ltsc2022",
    "windows-amd64-ltsc2025",
}
WINDOWS_BUILDS = {"2019": "17763", "2022": "20348", "2025": "26100"}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class GateError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot load {path}: {exc}") from exc


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def catalog() -> dict[str, Any]:
    value = load(CATALOG_PATH)
    if value.get("schema_version") != 1:
        raise GateError("unsupported catalog schema")
    if set(value.get("platforms", {})) != EXPECTED_PLATFORMS:
        raise GateError("catalog must contain exactly five supported platforms")
    if value.get("repository") != "devanshmathur19/qtest-publisher":
        raise GateError("unexpected candidate repository")
    if value.get("production_repository") != "harness/qtest-publisher":
        raise GateError("unexpected production repository")
    if value.get("supported") is not False:
        raise GateError("catalog support must remain false until promotion gates pass")
    plugin = value.get("plugin", {})
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(plugin.get("version", ""))):
        raise GateError("plugin version must be immutable semantic version")
    if not str(plugin.get("source_url", "")).startswith("https://"):
        raise GateError("source URL must use HTTPS")
    if not REVISION_RE.fullmatch(str(plugin.get("source_revision", ""))):
        raise GateError("source revision must be a full Git commit")
    if not isinstance(plugin.get("revision"), int) or plugin["revision"] < 1:
        raise GateError("plugin release revision must be a positive integer")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(plugin.get("go_version", ""))):
        raise GateError("Go version must be exact")
    go_sdk = value.get("build_tools", {}).get("go_windows_amd64", {})
    if go_sdk.get("version") != plugin.get("go_version"):
        raise GateError("Windows Go SDK must match the catalog Go version")
    if not str(go_sdk.get("url", "")).startswith("https://go.dev/dl/"):
        raise GateError("Windows Go SDK must use the official HTTPS download")
    if not HEX_RE.fullmatch(str(go_sdk.get("sha256", ""))):
        raise GateError("Windows Go SDK must have an exact SHA-256")

    seen: set[str] = set()
    for name, item in value["platforms"].items():
        parent = item.get("runtime_parent", {})
        if not DIGEST_RE.fullmatch(str(parent.get("digest", ""))):
            raise GateError(f"invalid runtime parent digest: {name}")
        if parent["digest"] in seen:
            raise GateError("each platform must pin its exact runtime child digest")
        seen.add(parent["digest"])
        if parent.get("tag") == "latest":
            raise GateError("mutable parent tags are forbidden")
        if name.startswith("windows-"):
            builder = item.get("builder_parent", {})
            if not DIGEST_RE.fullmatch(str(builder.get("digest", ""))):
                raise GateError(f"invalid builder parent digest: {name}")
            if builder.get("tag") == "latest":
                raise GateError("mutable builder tags are forbidden")
            ltsc = item.get("ltsc")
            if item.get("windows_build") != WINDOWS_BUILDS.get(ltsc):
                raise GateError(f"Windows build mismatch: {name}")
            if not str(item.get("os_version", "")).startswith(
                f"10.0.{item['windows_build']}."
            ):
                raise GateError(f"Windows os.version mismatch: {name}")
        elif any(field in item for field in ("ltsc", "windows_build", "os_version")):
            raise GateError(f"Linux platform contains Windows metadata: {name}")
    return value


def source_root(args: argparse.Namespace) -> Path:
    configured = getattr(args, "source_root", None) or os.environ.get(
        "QTEST_PUBLISHER_ROOT"
    )
    return (
        Path(configured).expanduser().resolve()
        if configured
        else DEFAULT_SOURCE_ROOT.resolve()
    )


def dockerfile_relative(cat: dict[str, Any], platform_name: str) -> Path:
    return Path("docker") / cat["platforms"][platform_name]["dockerfile"]


def child_tag(cat: dict[str, Any], platform_name: str) -> str:
    return (
        f"{cat['plugin']['version']}-{cat['platforms'][platform_name]['tag_suffix']}"
        f"-r{cat['plugin']['revision']}"
    )


def moving_tag(cat: dict[str, Any], platform_name: str) -> str:
    item = cat["platforms"][platform_name]
    if platform_name.startswith("windows-"):
        return f"{cat['plugin']['version']}-windows-ltsc{item['ltsc']}-amd64"
    return f"{cat['plugin']['version']}-{item['tag_suffix']}"


def render_linux(cat: dict[str, Any], platform_name: str) -> str:
    item = cat["platforms"][platform_name]
    parent = item["runtime_parent"]
    arch = platform_name.removeprefix("linux-")
    return "\n".join(
        [
            f"ARG RUNTIME_IMAGE={parent['image']}@{parent['digest']}",
            "FROM ${RUNTIME_IMAGE}",
            f"COPY --chown=65532:65532 release/linux/{arch}/qtest-publisher /qtest-publisher",
            'LABEL org.opencontainers.image.source="'
            + cat["plugin"]["source_url"]
            + '" \\',
            '      org.opencontainers.image.revision="'
            + cat["plugin"]["source_revision"]
            + '" \\',
            '      org.opencontainers.image.version="'
            + cat["plugin"]["version"]
            + '" \\',
            '      io.harness.release.status="candidate"',
            "USER 65532:65532",
            'ENTRYPOINT ["/qtest-publisher"]',
            "",
        ]
    )


def render_windows(cat: dict[str, Any], platform_name: str) -> str:
    item = cat["platforms"][platform_name]
    parent = item["runtime_parent"]
    return "\n".join(
        [
            "# escape=`",
            "",
            f"ARG RUNTIME_IMAGE={parent['image']}@{parent['digest']}",
            "FROM ${RUNTIME_IMAGE}",
            "USER ContainerUser",
            "WORKDIR C:/workspace",
            "COPY release/windows/amd64/qtest-publisher.exe C:/bin/qtest-publisher.exe",
            f'LABEL org.opencontainers.image.source="{cat["plugin"]["source_url"]}" `',
            f'      org.opencontainers.image.revision="{cat["plugin"]["source_revision"]}" `',
            f'      org.opencontainers.image.version="{cat["plugin"]["version"]}" `',
            f'      io.harness.windows.build="{item["windows_build"]}" `',
            '      io.harness.release.status="candidate"',
            'ENTRYPOINT ["C:\\\\bin\\\\qtest-publisher.exe"]',
            "",
        ]
    )


def render_all(cat: dict[str, Any]) -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for name in sorted(cat["platforms"]):
        content = (
            render_windows(cat, name)
            if name.startswith("windows-")
            else render_linux(cat, name)
        )
        rendered[dockerfile_relative(cat, name)] = content
    return rendered


def render_manifest(cat: dict[str, Any]) -> str:
    lines = [
        f'image: {cat["production_repository"]}:{{{{trimPrefix "v" build.tag}}}}',
        "manifests:",
    ]
    for name in sorted(cat["platforms"]):
        item = cat["platforms"][name]
        architecture = "arm64" if name == "linux-arm64" else "amd64"
        operating_system = "windows" if name.startswith("windows-") else "linux"
        lines += [
            "  -",
            f'    image: {cat["production_repository"]}:{{{{trimPrefix "v" build.tag}}}}-{item["tag_suffix"]}',
            "    platform:",
            f"      architecture: {architecture}",
            f"      os: {operating_system}",
        ]
        if operating_system == "windows":
            lines.append(f'      version: "{item["os_version"]}"')
    return "\n".join(lines) + "\n"


def validate_source(cat: dict[str, Any], checkout: Path) -> None:
    if not (checkout / "go.mod").is_file() or not (checkout / "plugin").is_dir():
        raise GateError("qtest-publisher checkout is missing")
    revision = cat["plugin"]["source_revision"]
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            cwd=checkout,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "diff", "--exit-code", revision, "--", "go.mod", "main.go", "plugin"],
            cwd=checkout,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise GateError("working source does not match the pinned source revision") from exc


def validate_child_lock(cat: dict[str, Any]) -> dict[str, Any]:
    lock = load(CHILD_LOCK_PATH)
    if set(lock.get("children", {})) != EXPECTED_PLATFORMS:
        raise GateError("child lock does not match catalog platforms")
    if lock.get("supported") is not False:
        raise GateError("release support must remain false")
    counts = {"published": 0, "qualified": 0, "promoted": 0}
    seen: set[str] = set()
    for name, item in lock["children"].items():
        if item.get("tag") != child_tag(cat, name):
            raise GateError(f"unexpected immutable tag: {name}")
        if item.get("supported") is not False:
            raise GateError(f"child support must remain false: {name}")
        digest = item.get("digest")
        if digest is None:
            if any(item.get(field) for field in counts):
                raise GateError(f"unpublished child has release state: {name}")
        else:
            if not DIGEST_RE.fullmatch(str(digest)) or digest in seen:
                raise GateError(f"invalid or duplicate child digest: {name}")
            seen.add(digest)
            if not isinstance(item.get("registry_compressed_size_bytes"), int) or item[
                "registry_compressed_size_bytes"
            ] <= 0:
                raise GateError(f"invalid registry size: {name}")
            if item.get("published") is not True:
                raise GateError(f"recorded child is not published: {name}")
            require_evidence(item, "publication")
        if item.get("qualified"):
            if not item.get("published"):
                raise GateError("qualified child must be published")
            require_evidence(item, "qualification")
        if item.get("promoted"):
            if not item.get("qualified"):
                raise GateError("promoted child must be qualified")
            require_evidence(item, "promotion")
        for field in counts:
            counts[field] += item.get(field) is True
    validate_summary_states(lock, counts)
    return lock


def require_evidence(item: dict[str, Any], kind: str) -> None:
    value = item.get("evidence", {}).get(kind)
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{kind} evidence is required")


def validate_summary_states(lock: dict[str, Any], counts: dict[str, int]) -> None:
    total = len(EXPECTED_PLATFORMS)
    for field, child, complete, empty in (
        ("publication_state", "published", "published", "unpublished"),
        ("qualification_state", "qualified", "qualified", "unqualified"),
        ("promotion_state", "promoted", "promoted", "unpromoted"),
    ):
        count = counts[child]
        expected = complete if count == total else empty if count == 0 else "partial"
        if lock.get(field) != expected:
            raise GateError(f"{field} must be {expected}")


def update_states(lock: dict[str, Any]) -> None:
    total = len(lock["children"])
    for field, child, complete, empty in (
        ("publication_state", "published", "published", "unpublished"),
        ("qualification_state", "qualified", "qualified", "unqualified"),
        ("promotion_state", "promoted", "promoted", "unpromoted"),
    ):
        count = sum(item.get(child) is True for item in lock["children"].values())
        lock[field] = complete if count == total else empty if count == 0 else "partial"
    lock["supported"] = False


def command_validate(args: argparse.Namespace) -> None:
    cat = catalog()
    validate_child_lock(cat)
    validate_source(cat, source_root(args))
    if len(render_all(cat)) != 5:
        raise GateError("generator must produce exactly five Dockerfiles")
    print("qTest catalog, source pin, generator, and child lock are valid")


def command_validate_lock(_: argparse.Namespace) -> None:
    cat = catalog()
    validate_child_lock(cat)
    if len(render_all(cat)) != 5:
        raise GateError("generator must produce exactly five Dockerfiles")
    print("qTest catalog, generator, and child lock are valid")


def command_generate(args: argparse.Namespace) -> None:
    cat = catalog()
    checkout = source_root(args)
    if not (checkout / "go.mod").is_file():
        raise GateError("--source-root must be a qtest-publisher checkout")
    for relative, content in render_all(cat).items():
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (checkout / "docker" / "manifest.tmpl").write_text(
        render_manifest(cat), encoding="utf-8"
    )
    print("generated five digest-pinned Dockerfiles and complete manifest")


def command_check(args: argparse.Namespace) -> None:
    cat = catalog()
    checkout = source_root(args)
    validate_source(cat, checkout)
    for relative, content in render_all(cat).items():
        path = checkout / relative
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise GateError(f"generated Dockerfile is stale: {relative}")
        if ":latest" in content or "http://" in content:
            raise GateError(f"mutable tag or insecure source: {relative}")
    manifest = checkout / "docker" / "manifest.tmpl"
    if not manifest.is_file() or manifest.read_text(encoding="utf-8") != render_manifest(cat):
        raise GateError("generated complete manifest is stale")
    print("all five Dockerfiles and complete manifest are current")


def command_build_binaries(args: argparse.Namespace) -> None:
    cat = catalog()
    checkout = source_root(args)
    validate_source(cat, checkout)
    revision = cat["plugin"]["source_revision"]
    version = cat["plugin"]["version"]
    for operating_system, architecture in (
        ("linux", "amd64"),
        ("linux", "arm64"),
        ("windows", "amd64"),
    ):
        output = (
            checkout
            / "release"
            / operating_system
            / architecture
            / ("qtest-publisher.exe" if operating_system == "windows" else "qtest-publisher")
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update(
            {"CGO_ENABLED": "0", "GOOS": operating_system, "GOARCH": architecture}
        )
        subprocess.run(
            [
                "go",
                "build",
                "-trimpath",
                "-ldflags",
                f"-s -w -X main.version={version}+{revision[:12]}",
                "-o",
                str(output),
                ".",
            ],
            cwd=checkout,
            env=environment,
            check=True,
        )
    print("built static Linux AMD64/ARM64 and Windows AMD64 binaries")


def command_inventory(_: argparse.Namespace) -> None:
    cat = catalog()
    lock = validate_child_lock(cat)
    print(
        json.dumps(
            [
                {
                    "platform": name,
                    "dockerfile": str(dockerfile_relative(cat, name)),
                    "runtime_parent": item["runtime_parent"],
                    "immutable_tag": child_tag(cat, name),
                    "moving_tag": moving_tag(cat, name),
                    "child_digest": lock["children"][name].get("digest"),
                    "supported": False,
                }
                for name, item in cat["platforms"].items()
            ],
            indent=2,
        )
    )


def command_record(args: argparse.Namespace) -> None:
    cat = catalog()
    if args.platform not in EXPECTED_PLATFORMS:
        raise GateError("unknown platform")
    lock = validate_child_lock(cat)
    item = lock["children"][args.platform]
    if args.command == "record-published":
        if not DIGEST_RE.fullmatch(args.digest) or args.size <= 0:
            raise GateError("published digest and positive size are required")
        if any(
            other.get("digest") == args.digest
            for name, other in lock["children"].items()
            if name != args.platform
        ):
            raise GateError("child digest cannot represent multiple platforms")
        if item.get("digest") and item["digest"] != args.digest:
            raise GateError("immutable digest is already recorded")
        item.update(
            {
                "digest": args.digest,
                "registry_compressed_size_bytes": args.size,
                "published": True,
                "qualified": False,
                "promoted": False,
                "config_digest": "sha256:"
                + hashlib.sha256(
                    render_all(cat)[dockerfile_relative(cat, args.platform)].encode()
                ).hexdigest(),
                "evidence": {"publication": args.evidence},
            }
        )
    elif args.command == "record-qualified":
        if not item.get("published"):
            raise GateError("only a published child can be qualified")
        item["qualified"] = True
        item.setdefault("evidence", {})["qualification"] = args.evidence
    else:
        if not item.get("qualified"):
            raise GateError("only a qualified child can be promoted")
        item["promoted"] = True
        item.setdefault("evidence", {})["promotion"] = args.evidence
    if not args.evidence.strip():
        raise GateError("evidence is required")
    update_states(lock)
    write(CHILD_LOCK_PATH, lock)


def validate_builder(cat: dict[str, Any], platform_name: str, family: str | None) -> None:
    if platform_name not in EXPECTED_PLATFORMS:
        raise GateError("unknown platform")
    if not platform_name.startswith("windows-"):
        return
    item = cat["platforms"][platform_name]
    expected = f"ltsc{item['ltsc']}"
    actual = family or os.environ.get("CI_WINDOWS_BUILDER_FAMILY")
    if not actual or actual.lower() != expected:
        raise GateError(f"builder mismatch: expected {expected}, got {actual}")
    if os.name == "nt":
        parts = host_platform.version().split(".")
        observed = parts[2] if len(parts) > 2 else ""
        if observed != item["windows_build"]:
            raise GateError(
                f"host build mismatch: expected {item['windows_build']}, got {observed}"
            )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command", required=True)
    for name, function in (
        ("validate", command_validate),
        ("generate", command_generate),
        ("check", command_check),
        ("build-binaries", command_build_binaries),
    ):
        command = commands.add_parser(name)
        command.add_argument("--source-root")
        command.set_defaults(func=function)
    commands.add_parser("validate-lock").set_defaults(func=command_validate_lock)
    commands.add_parser("inventory").set_defaults(func=command_inventory)
    for name in ("record-published", "record-qualified", "record-promoted"):
        command = commands.add_parser(name)
        command.add_argument("--platform", required=True)
        command.add_argument("--evidence", required=True)
        if name == "record-published":
            command.add_argument("--digest", required=True)
            command.add_argument("--size", required=True, type=int)
        command.set_defaults(func=command_record)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        args.func(args)
        return 0
    except (GateError, subprocess.CalledProcessError) as exc:
        print(f"release gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
