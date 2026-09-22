"""Read stable GitHub release metadata; never download or execute binaries."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.request import Request, urlopen

REPOSITORY = "https://github.com/rqkeqq-ui/ck3translate"
API_URL = "https://api.github.com/repos/rqkeqq-ui/ck3translate/releases/latest"


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError("Invalid stable version")
    return tuple(int(part) for part in match.groups())


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    notes: str


def parse_release(data: dict, current: str) -> Release | None:
    if not isinstance(data, dict):
        raise ValueError("Invalid release response")
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name", "")
    if not isinstance(tag, str):
        raise ValueError("Invalid release version")
    if version_tuple(tag) <= version_tuple(current):
        return None
    body = data.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise ValueError("Invalid release notes")
    return Release(tag.removeprefix("v"), f"{REPOSITORY}/releases/tag/{tag}", body[:12000])


def check_release(current: str) -> Release | None:
    request = Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "CK3LocalizationManager"})
    with urlopen(request, timeout=8) as response:
        body = response.read(1_000_001)
    if len(body) > 1_000_000:
        raise ValueError("Release response is too large")
    return parse_release(json.loads(body), current)


def should_notify(release: Release | None, skipped: str, manual: bool = False) -> bool:
    return release is not None and (manual or release.version != skipped)
