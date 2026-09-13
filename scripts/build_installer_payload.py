#!/usr/bin/env python3
"""Build the deterministic, target-aware Glyphs MCP installer payload."""

from __future__ import annotations

import argparse
import json
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "installer-payload" / "Payload"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
RUNTIME_DEPENDENCY_PROVENANCE = (
    REPO_ROOT / "third_party" / "python-runtime-dependencies.json"
)
SKILLS = REPO_ROOT / "skills"
PLUGIN_NAME = "Glyphs MCP.glyphsPlugin"
GLYPHS3_TAG = "v1.11.0"
GLYPHS3_COMMIT_PREFIX = "13ca805"
GLYPHS3_REPOSITORY_PATH = Path("src/glyphs-mcp") / PLUGIN_NAME
CANONICAL_RUNTIME_RESOURCES = REPO_ROOT / "src/glyphs-mcp" / PLUGIN_NAME / "Contents/Resources"
SHARED_RUNTIME_FILES = ("runtime_path_policy.py", "runtime_probe.py")
PRODUCT_PAGE_URL = "https://github.com/thierryc/Glyphs-mcp"


def _assert_output(output_root: Path, allow_outside_worktree: bool) -> Path:
    resolved = output_root.resolve()
    if not allow_outside_worktree:
        try:
            resolved.relative_to(REPO_ROOT.resolve())
        except ValueError as exc:
            raise ValueError("installer payload output must remain inside the repository worktree") from exc
        if resolved == REPO_ROOT.resolve():
            raise ValueError("refusing to use the repository root as installer payload output")
    return resolved


def _run_git(*arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout


def _extract_pinned_glyphs3(destination: Path) -> str:
    commit = str(_run_git("rev-parse", f"{GLYPHS3_TAG}^{{commit}}")).strip()
    if not commit.startswith(GLYPHS3_COMMIT_PREFIX):
        raise RuntimeError(
            f"{GLYPHS3_TAG} resolved to unexpected commit {commit}; expected {GLYPHS3_COMMIT_PREFIX}"
        )
    archive = _run_git(
        "archive",
        "--format=tar",
        GLYPHS3_TAG,
        GLYPHS3_REPOSITORY_PATH.as_posix(),
        binary=True,
    )
    assert isinstance(archive, bytes)
    with tempfile.TemporaryDirectory(prefix="glyphs-mcp-v1-payload-") as temporary:
        extraction = Path(temporary)
        with tarfile.open(fileobj=BytesIO(archive), mode="r:") as stream:
            try:
                stream.extractall(extraction, filter="data")
            except TypeError:  # Python 3.9 supplied by older Xcode installations.
                stream.extractall(extraction)
        source = extraction / GLYPHS3_REPOSITORY_PATH
        if not source.is_dir():
            raise RuntimeError("pinned Glyphs 3 plug-in bundle is missing from the baseline tag")
        shutil.copytree(source, destination, ignore=_ignore_generated)
    return commit


def _ignore_generated(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == ".DS_Store"
        or name == "__pycache__"
        or name.endswith((".pyc", ".pyo"))
        or name == ".venv"
    }


def _sanitize_distribution_plist(bundle: Path) -> str:
    plist_path = bundle / "Contents" / "Info.plist"
    with plist_path.open("rb") as stream:
        info = plistlib.load(stream)
    for key in ("UpdateFeedURL", "productReleaseNotes"):
        value = info.get(key)
        if isinstance(value, str) and "____" in value:
            info.pop(key, None)
    info["productPageURL"] = PRODUCT_PAGE_URL
    for key, value in info.items():
        if isinstance(value, str) and "____" in value:
            raise RuntimeError(f"generated plug-in plist contains unresolved placeholder in {key}")
    version = str(info.get("CFBundleShortVersionString") or "")
    if not version or str(info.get("CFBundleVersion") or "") != version:
        raise RuntimeError(f"generated plug-in has invalid version metadata: {bundle}")
    with plist_path.open("wb") as stream:
        plistlib.dump(info, stream, sort_keys=True)
    return version


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "____" in value
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_placeholder(item) for item in value)
    return False


def _safe_payload_path(root: Path, relative: Any, expected: str) -> Path:
    if relative != expected:
        raise RuntimeError(f"installer payload path must be {expected!r}")
    candidate = root / expected
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError("installer payload path escapes its root") from exc
    return candidate


def validate_payload(payload_root: Path, *, release_version: str | None = None) -> dict:
    from build_simple_v2 import _identity
    root = Path(payload_root).resolve()
    manifest = json.loads((root / "payload.json").read_text())
    if manifest.get("schemaVersion") != 3 or set(manifest.get("targets", {})) != {"3", "4"}:
        raise ValueError("Unsupported installer payload")
    if release_version and manifest["version"] != release_version:
        raise ValueError("Installer release version mismatch")
    for name in ("Lean", "Installer"):
        if _identity(root / name) != manifest[name.lower() + "Identity"]:
            raise ValueError("Payload identity mismatch: " + name)
    for major, expected in (("3", "1.11.0"), ("4", manifest["version"])):
        target = manifest["targets"][major]
        path = _safe_payload_path(root, target["pluginPath"],
            "Plugins/Glyphs3/Glyphs MCP.glyphsPlugin" if major == "3" else "Lean/Glyphs MCP Bridge.glyphsPlugin")
        info = plistlib.loads((path / "Contents/Info.plist").read_bytes())
        if info["CFBundleShortVersionString"] != expected or target["pluginVersion"] != expected:
            raise ValueError("Plugin version mismatch")
    if manifest["targets"]["3"]["baseline"] != {"tag": "v1.11.0", "commit": "13ca805"}:
        raise ValueError("Glyphs 3 pin changed")
    return manifest


def build_payload(output_root=DEFAULT_OUTPUT_ROOT, *, allow_outside_worktree=False, runtime_root=None):
    from build_simple_v2 import build, _identity
    output = _assert_output(Path(output_root), allow_outside_worktree)
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    legacy = output / "Plugins/Glyphs3" / PLUGIN_NAME
    legacy.parent.mkdir(parents=True)
    _extract_pinned_glyphs3(legacy)
    _sanitize_distribution_plist(legacy)
    for name in SHARED_RUNTIME_FILES:
        shutil.copy2(CANONICAL_RUNTIME_RESOURCES / name, legacy / "Contents/Resources" / name)
    shutil.copy2(REQUIREMENTS, output / "requirements.txt")
    shutil.copytree(SKILLS, output / "skills", ignore=_ignore_generated)
    shutil.copytree(REPO_ROOT / "legacy/glyphs3/skills", output / "skills-v1", ignore=_ignore_generated)
    runtime_root = Path(runtime_root or REPO_ROOT / "build/private-runtime")
    lean = build(output / "Lean", runtime_root=runtime_root)
    helper = output / "Installer"; helper.mkdir()
    for name in ("install_simple_v2.py", "installation_transaction.py", "build_simple_v2.py"):
        shutil.copy2(REPO_ROOT / "scripts" / name, helper / name)
    provenance = output / "ThirdParty"; provenance.mkdir()
    for name in ("lean-runtime.json", "lean-runtime-arm64.lock", "lean-runtime-x86_64.lock", "lean-runtime-wheels-arm64.json", "lean-runtime-wheels-x86_64.json"):
        shutil.copy2(REPO_ROOT / "third_party" / name, provenance / name)
    manifest = {"schemaVersion": 3, "version": lean["projectVersion"], "installerBuild": lean["installerBuild"],
        "requirementsPath": "requirements.txt", "skillsPath": "skills",
        "leanIdentity": _identity(output / "Lean"), "installerIdentity": _identity(helper),
        "targets": {
            "3": {"pluginPath": "Plugins/Glyphs3/Glyphs MCP.glyphsPlugin", "pluginVersion": "1.11.0",
                  "runtimeTrack": "1.x", "updatePolicy": "pinned", "baseline": {"tag": "v1.11.0", "commit": "13ca805"}},
            "4": {"pluginPath": "Lean/Glyphs MCP Bridge.glyphsPlugin", "pluginVersion": lean["projectVersion"],
                  "runtimeTrack": "2.x", "updatePolicy": "release", "baseline": {"tag": "v1.11.0", "commit": "13ca805"}}}}
    (output / "payload.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return validate_payload(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--allow-outside-worktree", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--verify-root", type=Path)
    parser.add_argument("--release-version")
    args = parser.parse_args()
    result = validate_payload(args.verify_root or args.output_root, release_version=args.release_version) if args.validate_only or args.verify_root else build_payload(
        args.output_root, allow_outside_worktree=args.allow_outside_worktree)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()
