#!/usr/bin/env python3
"""Verify GitHub's release and uploaded asset digests before/after publication."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def verify(release, tag, files, *, published=False):
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-beta\.[1-9]\d*)?", tag):
        raise ValueError("A stable or beta version tag is required")
    prerelease = "-beta." in tag
    if prerelease and any("latest" in path.name.lower() for path in files):
        raise ValueError("Beta releases cannot contain Latest assets")
    if release.get("tag_name") != tag or release.get("draft") is not (not published) or release.get("prerelease") is not prerelease:
        raise ValueError("Release tag or publication state mismatch")
    expected_page = "https://github.com/thierryc/Glyphs-mcp/releases/tag/" + tag
    if published and release.get("html_url") != expected_page:
        raise ValueError("Unexpected published release URL")
    assets = release.get("assets", [])
    expected = {p.name: p for p in files}
    if len(expected) != len(files) or len(assets) != len(expected) or {a.get("name") for a in assets} != set(expected):
        raise ValueError("Release assets do not match the verified local set")
    for asset in assets:
        path = expected[asset["name"]]
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if asset.get("digest") != digest or asset.get("size") != path.stat().st_size or asset.get("state") != "uploaded":
            raise ValueError("Uploaded asset identity mismatch: " + path.name)
        url = f"https://github.com/thierryc/Glyphs-mcp/releases/download/{tag}/{path.name}"
        if asset.get("browser_download_url") != url:
            raise ValueError("Unexpected release download URL: " + path.name)
    return {"tag": tag, "published": published, "verifiedAssets": sorted(expected)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--published", action="store_true")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(json.load(sys.stdin), args.tag, args.files, published=args.published)))
