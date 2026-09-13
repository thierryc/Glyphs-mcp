"""One release identity for beta labeling, artifact names and publication gates."""
import argparse
import json
from pathlib import Path
import re


def identity(version, channel="stable", beta_number=0):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid numeric release version")
    if channel not in {"stable", "beta"} or type(beta_number) is not int:
        raise ValueError("Invalid release channel")
    if (channel == "beta" and beta_number < 1) or (channel == "stable" and beta_number != 0):
        raise ValueError("Beta releases require a positive beta number; stable releases require zero")
    release_version = version + (f"-beta.{beta_number}" if channel == "beta" else "")
    branch = "lit/v2-beta" if channel == "beta" else "main"
    return {"version": version, "channel": channel, "betaNumber": beta_number,
            "releaseVersion": release_version, "tag": "v" + release_version, "branch": branch,
            "label": version + (f" Beta {beta_number}" if channel == "beta" else ""),
            "registryURL": f"https://raw.githubusercontent.com/thierryc/Glyphs-mcp/{branch}/templates/registry.json",
            "feedURL": f"https://raw.githubusercontent.com/thierryc/Glyphs-mcp/{branch}/appcast.xml"}


def load(root):
    root = Path(root)
    project = (root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj").read_text()
    versions = set(re.findall(r"MARKETING_VERSION\s*=\s*(\d+\.\d+\.\d+)\s*;", project))
    builds = set(re.findall(r"CURRENT_PROJECT_VERSION\s*=\s*(\d+)\s*;", project))
    if len(versions) != 1 or len(builds) != 1 or int(next(iter(builds))) < 1:
        raise ValueError("Release versions/build numbers must agree in Xcode")
    path = root / "release.json"
    config = json.loads(path.read_text()) if path.exists() else {}
    value = identity(next(iter(versions)), config.get("channel", "stable"), config.get("betaNumber", 0))
    value["installerBuild"] = int(next(iter(builds)))
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--field")
    args = parser.parse_args()
    value = load(args.repo_root)
    print(value[args.field] if args.field else json.dumps(value, indent=2))
