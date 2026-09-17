import copy
import hashlib
import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
discovery = importlib.import_module("release_discovery")


def fixture(tmp_path):
    asset = tmp_path / "Glyphs-MCP-latest.dmg"
    asset.write_bytes(b"signed and notarized fixture")
    release = {"tag_name": "v2.0.0", "draft": True, "prerelease": False,
               "html_url": "https://github.com/thierryc/Glyphs-mcp/releases/tag/untagged-a1b2c3",
               "assets": [{"name": asset.name, "size": asset.stat().st_size, "state": "uploaded",
                           "digest": "sha256:" + hashlib.sha256(asset.read_bytes()).hexdigest(),
                           "browser_download_url": "https://github.com/thierryc/Glyphs-mcp/releases/download/untagged-a1b2c3/" + asset.name}]}
    return release, [asset]


def test_discovery_requires_exact_uploaded_bytes_then_published_stable_latest(tmp_path):
    release, files = fixture(tmp_path)
    discovery.verify(release, "v2.0.0", files)
    with pytest.raises(ValueError, match="state"):
        discovery.verify(release, "v2.0.0", files, published=True)
    release["draft"] = False
    release["html_url"] = "https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0"
    release["assets"][0]["browser_download_url"] = (
        "https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0/" + files[0].name
    )
    assert discovery.verify(release, "v2.0.0", files, published=True)["published"]


def test_draft_discovery_accepts_gh_release_view_shape(tmp_path):
    release, files = fixture(tmp_path)
    gh_release = {
        "tagName": release["tag_name"],
        "isDraft": release["draft"],
        "isPrerelease": release["prerelease"],
        "url": release["html_url"],
        "assets": [{
            "name": asset["name"],
            "size": asset["size"],
            "state": asset["state"],
            "digest": asset["digest"],
            "url": asset["browser_download_url"],
        } for asset in release["assets"]],
    }
    assert discovery.verify(gh_release, "v2.0.0", files)["published"] is False


@pytest.mark.parametrize("mutation", ["digest", "size", "state", "url", "extra", "duplicate", "prerelease", "tag", "missing"])
def test_bad_upload_never_becomes_discoverable(tmp_path, mutation):
    release, files = fixture(tmp_path)
    asset = release["assets"][0]
    if mutation in ("digest", "size", "state"): asset[mutation] = "wrong"
    elif mutation == "url": asset["browser_download_url"] = "https://example.org/file.dmg"
    elif mutation == "extra": release["assets"].append({"name": "unexpected"})
    elif mutation == "duplicate": release["assets"].append(copy.deepcopy(asset))
    elif mutation == "prerelease": release["prerelease"] = True
    elif mutation == "tag": release["tag_name"] = "v1.11.0"
    else: release["assets"] = []
    with pytest.raises(ValueError): discovery.verify(release, "v2.0.0", files)
