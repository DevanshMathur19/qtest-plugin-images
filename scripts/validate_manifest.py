#!/usr/bin/env python3
"""Validate the complete qTest publisher multi-platform OCI index."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_manifest.py INDEX_JSON CHILD_LOCK")
    index = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    lock = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "catalog" / "versions.yaml").read_text(encoding="utf-8"))
    manifests = index.get("manifests", [])
    if len(manifests) != 5:
        raise SystemExit(f"expected five image descriptors, got {len(manifests)}")

    observed: dict[tuple[str, str, str], str] = {}
    for descriptor in manifests:
        platform = descriptor.get("platform", {})
        key = (
            platform.get("os", ""),
            platform.get("architecture", ""),
            platform.get("os.version", ""),
        )
        if key in observed:
            raise SystemExit(f"duplicate platform descriptor: {key}")
        observed[key] = descriptor.get("digest", "")

    expected: dict[tuple[str, str, str], str] = {}
    for name, item in catalog["platforms"].items():
        operating_system = "windows" if name.startswith("windows-") else "linux"
        architecture = "arm64" if name == "linux-arm64" else "amd64"
        os_version = item.get("os_version", "")
        expected[(operating_system, architecture, os_version)] = lock["children"][name][
            "digest"
        ]
    if observed != expected:
        raise SystemExit(f"manifest descriptors do not match lock: {observed} != {expected}")
    print("complete five-platform manifest matches the qualified digest lock")


if __name__ == "__main__":
    main()
