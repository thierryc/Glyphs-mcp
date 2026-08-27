#!/usr/bin/env python3
"""Build the deterministic, target-aware Glyphs MCP installer payload."""

from __future__ import annotations

import argparse
import importlib.util
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
V2_BUILDER_PATH = REPO_ROOT / "scripts" / "build_v2_runtime_payload.py"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
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


def _load_v2_builder() -> Any:
    spec = importlib.util.spec_from_file_location("glyphs_mcp_v2_payload_builder", V2_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the v2 runtime payload builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def validate_payload(
    payload_root: Path,
    *,
    release_version: str | None = None,
) -> dict[str, Any]:
    """Validate one built or signed schema-v2 payload without mutating it."""
    root = payload_root.resolve()
    manifest_path = root / "payload.json"
    if not manifest_path.is_file() or manifest_path.stat().st_size > 64 * 1024:
        raise RuntimeError("installer payload manifest is missing or too large")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("installer payload manifest is malformed") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schemaVersion") != 2
        or manifest.get("requirementsPath") != "requirements.txt"
        or manifest.get("skillsPath") != "skills"
        or not isinstance(manifest.get("targets"), dict)
        or set(manifest["targets"]) != {"3", "4"}
    ):
        raise RuntimeError("installer payload manifest schema is unsupported")
    if not (root / "requirements.txt").is_file() or not (root / "skills").is_dir():
        raise RuntimeError("installer payload shared resources are missing")

    expected = {
        "3": {
            "path": f"Plugins/Glyphs3/{PLUGIN_NAME}",
            "version": "1.11.0",
            "track": "1.x",
            "policy": "pinned",
            "tag": GLYPHS3_TAG,
            "commit": GLYPHS3_COMMIT_PREFIX,
        },
        "4": {
            "path": f"Plugins/Glyphs4/{PLUGIN_NAME}",
            "version": release_version,
            "track": "2.x",
            "policy": "release",
            "tag": None,
            "commit": None,
        },
    }
    resolved_plugins: list[Path] = []
    for major in ("3", "4"):
        target = manifest["targets"].get(major)
        contract = expected[major]
        if not isinstance(target, dict):
            raise RuntimeError(f"installer payload target {major} is malformed")
        plugin = _safe_payload_path(root, target.get("pluginPath"), str(contract["path"]))
        baseline = target.get("baseline")
        if (
            target.get("runtimeTrack") != contract["track"]
            or target.get("updatePolicy") != contract["policy"]
            or not isinstance(baseline, dict)
            or not str(baseline.get("tag") or "")
            or not str(baseline.get("commit") or "")
        ):
            raise RuntimeError(f"installer payload target {major} contract is invalid")
        if major == "3" and (
            target.get("pluginVersion") != contract["version"]
            or baseline.get("tag") != contract["tag"]
            or baseline.get("commit") != contract["commit"]
        ):
            raise RuntimeError("Glyphs 3 payload is not the pinned v1.11 baseline")
        if contract["version"] is not None and target.get("pluginVersion") != contract["version"]:
            raise RuntimeError(f"Glyphs {major} plug-in version does not match the release")
        info_path = plugin / "Contents" / "Info.plist"
        runtime_probe = plugin / "Contents" / "Resources" / "runtime_probe.py"
        runtime_policy = plugin / "Contents" / "Resources" / "runtime_path_policy.py"
        if not plugin.is_dir() or not info_path.is_file() or not runtime_probe.is_file() or not runtime_policy.is_file():
            raise RuntimeError(f"Glyphs {major} payload bundle is incomplete")
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
        if (
            str(info.get("CFBundleShortVersionString") or "") != target.get("pluginVersion")
            or str(info.get("CFBundleVersion") or "") != target.get("pluginVersion")
            or info.get("productPageURL") != PRODUCT_PAGE_URL
            or _contains_placeholder(info)
        ):
            raise RuntimeError(f"Glyphs {major} payload plist is not distributable")
        v2_runtime = plugin / "Contents" / "Resources" / "glyphs_mcp_v2" / "runtime.py"
        if (major == "4") != v2_runtime.is_file():
            raise RuntimeError(f"Glyphs {major} payload contains the wrong runtime track")
        resolved_plugins.append(plugin.resolve())
    if resolved_plugins[0] == resolved_plugins[1]:
        raise RuntimeError("installer payload targets reuse one plug-in bundle")
    return manifest


def _copy_shared_payload(output: Path) -> None:
    if not REQUIREMENTS.is_file() or not SKILLS.is_dir():
        raise RuntimeError("installer requirements or skills are missing")
    shutil.copy2(REQUIREMENTS, output / "requirements.txt")
    shutil.copytree(SKILLS, output / "skills", ignore=_ignore_generated)


def build(output_root: Path, *, allow_outside_worktree: bool = False) -> dict[str, Any]:
    output = _assert_output(output_root, allow_outside_worktree)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    plugins = output / "Plugins"
    glyphs3 = plugins / "Glyphs3" / PLUGIN_NAME
    glyphs4 = plugins / "Glyphs4" / PLUGIN_NAME
    glyphs3.parent.mkdir(parents=True)
    glyphs4.parent.mkdir(parents=True)

    glyphs3_commit = _extract_pinned_glyphs3(glyphs3)
    glyphs3_resources = glyphs3 / "Contents/Resources"
    for name in SHARED_RUNTIME_FILES:
        source = CANONICAL_RUNTIME_RESOURCES / name
        if not source.is_file():
            raise RuntimeError(f"canonical installer runtime module is missing: {source}")
        shutil.copy2(source, glyphs3_resources / name)
    (REPO_ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="glyphs-mcp-v2-installer-", dir=REPO_ROOT / "build") as temporary:
        v2_output = Path(temporary) / "v2-runtime"
        v2_builder = _load_v2_builder()
        v2_result = v2_builder.build(v2_output)
        source_bundle = Path(str(v2_result["installableBundle"]))
        shutil.copytree(source_bundle, glyphs4, ignore=_ignore_generated)

    glyphs3_version = _sanitize_distribution_plist(glyphs3)
    glyphs4_version = _sanitize_distribution_plist(glyphs4)
    if glyphs3_version != "1.11.0":
        raise RuntimeError(f"pinned Glyphs 3 payload has unexpected version {glyphs3_version}")
    _copy_shared_payload(output)

    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "requirementsPath": "requirements.txt",
        "skillsPath": "skills",
        "targets": {
            "3": {
                "pluginPath": f"Plugins/Glyphs3/{PLUGIN_NAME}",
                "pluginVersion": glyphs3_version,
                "runtimeTrack": "1.x",
                "updatePolicy": "pinned",
                "baseline": {"tag": GLYPHS3_TAG, "commit": GLYPHS3_COMMIT_PREFIX},
            },
            "4": {
                "pluginPath": f"Plugins/Glyphs4/{PLUGIN_NAME}",
                "pluginVersion": glyphs4_version,
                "runtimeTrack": "2.x",
                "updatePolicy": "release",
                "baseline": {
                    "tag": "working-tree",
                    "commit": str(_run_git("rev-parse", "HEAD")).strip(),
                },
            },
        },
    }
    (output / "payload.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return validate_payload(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--output-root", type=Path)
    mode.add_argument("--verify-root", type=Path)
    parser.add_argument("--release-version")
    parser.add_argument(
        "--allow-outside-worktree",
        action="store_true",
        help="Allow an Xcode target build directory outside the checkout.",
    )
    arguments = parser.parse_args()
    if arguments.verify_root is not None:
        if arguments.allow_outside_worktree:
            parser.error("--allow-outside-worktree is only valid while building")
        manifest = validate_payload(
            arguments.verify_root,
            release_version=arguments.release_version,
        )
        versions = {major: target["pluginVersion"] for major, target in manifest["targets"].items()}
        print(f"Verified target-aware installer payload at {arguments.verify_root}: {versions}")
        return 0
    if arguments.release_version is not None:
        parser.error("--release-version requires --verify-root")
    output_root = arguments.output_root or DEFAULT_OUTPUT_ROOT
    manifest = build(
        output_root,
        allow_outside_worktree=arguments.allow_outside_worktree,
    )
    versions = {major: target["pluginVersion"] for major, target in manifest["targets"].items()}
    print(f"Built target-aware installer payload at {output_root}: {versions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
