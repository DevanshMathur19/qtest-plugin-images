#!/usr/bin/env python3
"""Assert that this KubernetesDirect pod ran the requested immutable image."""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import urllib.request
from pathlib import Path

TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")


def main() -> None:
    candidate = os.environ.get("CANDIDATE_IMAGE", "")
    match = re.search(r"@(sha256:[0-9a-f]{64})$", candidate)
    if not match:
        raise SystemExit("CANDIDATE_IMAGE must be pinned by digest")
    expected = match.group(1)
    namespace = os.environ["POD_NAMESPACE"]
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ["KUBERNETES_SERVICE_PORT_HTTPS"]
    pod = os.environ.get("POD_NAME") or socket.gethostname()
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    context = ssl.create_default_context(cafile=str(CA_PATH))
    url = f"https://{host}:{port}/api/v1/namespaces/{namespace}/pods/{pod}"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        pod_resource = json.load(response)
    requested_images = [
        item.get("image", "")
        for item in pod_resource.get("spec", {}).get("containers", [])
        + pod_resource.get("spec", {}).get("initContainers", [])
    ]
    normalized_candidate = candidate.removeprefix("docker.io/")
    if not any(
        image.removeprefix("docker.io/") == normalized_candidate
        for image in requested_images
    ):
        raise SystemExit(
            f"expected Pod image {candidate}; requested: {', '.join(requested_images)}"
        )
    status = pod_resource["status"]
    image_ids = [
        item.get("imageID", "")
        for item in status.get("containerStatuses", [])
        + status.get("initContainerStatuses", [])
    ]
    if not any(image_id.endswith("@" + expected) for image_id in image_ids):
        raise SystemExit(
            f"expected running imageID {expected}; observed: {', '.join(image_ids)}"
        )
    print(f"Requested image verified: {candidate}")
    print(f"Running digest verified: {expected}")


if __name__ == "__main__":
    main()
