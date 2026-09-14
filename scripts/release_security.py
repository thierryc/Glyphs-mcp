#!/usr/bin/env python3
"""Pure metadata and checksum gates for the local release workflow."""

from __future__ import annotations

import argparse
from desktop_release_identity import load as release_identity
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MARKETING_VERSION_RE = re.compile(r"\bMARKETING_VERSION\s*=\s*(\d+\.\d+\.\d+)\s*;")
BUILD_VERSION_RE = re.compile(r"\bCURRENT_PROJECT_VERSION\s*=\s*(\d+)\s*;")
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
CURRENT_V2_PUBLIC_TOOL_COUNT = 20
CURRENT_V2_CANONICAL_SCHEMA_VERSION = 8


class ReleaseSecurityError(ValueError):
    pass


def read_plist_version(path: Path, *, require_matching_build: bool = True) -> tuple[str, str]:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception as exc:
        raise ReleaseSecurityError(f"could not read plist {path}: {exc}") from exc
    short = str(data.get("CFBundleShortVersionString") or "")
    build = str(data.get("CFBundleVersion") or "")
    if not VERSION_RE.fullmatch(short):
        raise ReleaseSecurityError(f"invalid CFBundleShortVersionString in {path}: {short!r}")
    if require_matching_build and build != short:
        raise ReleaseSecurityError(f"CFBundleVersion differs from release version in {path}: {build!r} != {short!r}")
    if not require_matching_build and (not build.isdigit() or int(build) < 1):
        raise ReleaseSecurityError(f"installer CFBundleVersion must be a positive integer in {path}: {build!r}")
    return short, build


def read_xcode_versions(path: Path) -> tuple[set[str], set[int]]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ReleaseSecurityError(f"could not read Xcode project {path}: {exc}") from exc
    marketing = set(MARKETING_VERSION_RE.findall(text))
    builds = {int(value) for value in BUILD_VERSION_RE.findall(text)}
    if not marketing:
        raise ReleaseSecurityError(f"no MARKETING_VERSION values found in {path}")
    if not builds or min(builds) < 1:
        raise ReleaseSecurityError(f"CURRENT_PROJECT_VERSION must be a positive integer in {path}")
    return marketing, builds


def read_v2_source_version(versions_path: Path, pyproject_path: Path) -> str:
    try:
        tree = ast.parse(versions_path.read_text(encoding="utf-8"), filename=str(versions_path))
    except Exception as exc:
        raise ReleaseSecurityError(f"could not read v2 versions from {versions_path}: {exc}") from exc
    runtime_version = ""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "SERVER_VERSION" for target in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except Exception as exc:
                raise ReleaseSecurityError(f"invalid SERVER_VERSION in {versions_path}") from exc
            runtime_version = value if isinstance(value, str) else ""
            break
    try:
        pyproject_text = pyproject_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ReleaseSecurityError(f"could not read v2 project metadata {pyproject_path}: {exc}") from exc
    project_match = re.search(
        r"(?ms)^\[project\]\s*$.*?^version\s*=\s*\"([^\"]+)\"\s*$",
        pyproject_text,
    )
    project_version = project_match.group(1) if project_match else ""
    if not VERSION_RE.fullmatch(runtime_version):
        raise ReleaseSecurityError(f"v2 SERVER_VERSION is not release-ready: {runtime_version!r}")
    if project_version != runtime_version:
        raise ReleaseSecurityError(
            f"v2 pyproject version {project_version!r} does not match SERVER_VERSION {runtime_version!r}"
        )
    return runtime_version


def read_project_version(root: Path) -> str:
    source = root / "src/bridge/glyphs_mcp_bridge/__init__.py"
    if not source.is_file():
        return read_v2_source_version(root / "src/glyphs-mcp-v2/glyphs_mcp_v2/versions.py", root / "src/glyphs-mcp-v2/pyproject.toml")
    tree = ast.parse(source.read_text())
    version = next((node.value.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "PROJECT_VERSION" for t in node.targets)
                    and isinstance(node.value, ast.Constant)), None)
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ReleaseSecurityError("Invalid lean project version")
    return version


def validate_release_metadata(repo_root: Path, tag: str, app_plist: Path | None = None) -> str:
    root = repo_root.resolve()
    versions_path = root / "src/glyphs-mcp-v2/glyphs_mcp_v2/versions.py"
    pyproject_path = root / "src/glyphs-mcp-v2/pyproject.toml"
    project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"

    version = read_project_version(root)
    marketing_versions, _build_versions = read_xcode_versions(project)
    if marketing_versions != {version}:
        values = ", ".join(sorted(marketing_versions))
        raise ReleaseSecurityError(f"Xcode MARKETING_VERSION values ({values}) do not all match {version}")

    release = release_identity(root)
    if tag != release["tag"]:
        raise ReleaseSecurityError(f"release tag {tag!r} must exactly match {release['tag']}")

    if app_plist is not None:
        app_version, app_build = read_plist_version(app_plist.resolve(), require_matching_build=False)
        if int(app_build) != release["installerBuild"]:
            raise ReleaseSecurityError("Built app build number does not match source")
        info = plistlib.loads(app_plist.read_bytes())
        if (info.get("GMCPReleaseChannel", "stable") != release["channel"]
                or info.get("GMCPBetaNumber", 0) != release["betaNumber"]):
            raise ReleaseSecurityError("Built app release channel does not match source")
        if release["channel"] == "beta" and (info.get("SUFeedURL") != release["feedURL"]
                or info.get("GMCPTemplateRegistryURL") != release["registryURL"]):
            raise ReleaseSecurityError("Beta app must use beta feed and registry URLs")
        if app_version != version:
            raise ReleaseSecurityError(f"built installer version {app_version} does not match source {version}")
    return version


PINNED_GLYPHS3_VERSION = "1.11.0"
AGENT_PLUGIN_MANIFESTS = (
    "plugins/glyphs-mcp/.codex-plugin/plugin.json",
    "plugins/glyphs-mcp/.claude-plugin/plugin.json",
    "plugins/glyphs-mcp/.cursor-plugin/plugin.json",
    "plugins/glyphs-mcp/.github/plugin/plugin.json",
)


def _read_agent_plugin_version(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReleaseSecurityError(f"could not read agent plug-in manifest {path}: {exc}") from exc
    version = data.get("version") if isinstance(data, Mapping) else None
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ReleaseSecurityError(f"invalid agent plug-in version in {path}: {version!r}")
    return version


def _validate_target_payload(
    payload_root: Path, release_version: str, repo_root: Path
) -> Mapping[str, Any]:
    builder_path = repo_root / "scripts/build_installer_payload.py"
    if not builder_path.is_file():
        raise ReleaseSecurityError(f"installer payload builder is missing: {builder_path}")
    spec = importlib.util.spec_from_file_location("glyphs_mcp_candidate_payload", builder_path)
    if spec is None or spec.loader is None:
        raise ReleaseSecurityError("could not load the installer payload validator")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        manifest = module.validate_payload(payload_root, release_version=release_version)
    except Exception as exc:
        raise ReleaseSecurityError(f"target-aware installer payload is invalid: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise ReleaseSecurityError("target-aware installer payload returned no manifest")
    return manifest


def validate_unsigned_candidate(
    repo_root: Path,
    *,
    expected_version: str,
    installer_build: int,
    payload_root: Path | None = None,
    app_plist: Path | None = None,
) -> dict[str, Any]:
    """Validate a local unsigned v2 candidate without requiring a tag or signature."""
    root = repo_root.resolve()
    lean = (root / "src/bridge").is_dir()
    knowledge = None if lean else validate_knowledge_dependencies(root)
    if not VERSION_RE.fullmatch(expected_version):
        raise ReleaseSecurityError(f"invalid expected release version: {expected_version!r}")
    if isinstance(installer_build, bool) or installer_build < 1:
        raise ReleaseSecurityError("installer build must be a positive integer")

    version = read_project_version(root)
    if version != expected_version:
        raise ReleaseSecurityError(
            f"v2 source version {version!r} does not match expected {expected_version!r}"
        )
    project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
    marketing_versions, build_versions = read_xcode_versions(project)
    if marketing_versions != {version}:
        values = ", ".join(sorted(marketing_versions))
        raise ReleaseSecurityError(f"Xcode MARKETING_VERSION values ({values}) do not all match {version}")
    if build_versions != {installer_build}:
        values = ", ".join(str(value) for value in sorted(build_versions))
        raise ReleaseSecurityError(
            f"installer build values ({values}) do not exactly match {installer_build}"
        )

    pinned_paths = (
        root / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
        root / "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
    )
    for path in pinned_paths:
        short, build = read_plist_version(path)
        if short != PINNED_GLYPHS3_VERSION or build != PINNED_GLYPHS3_VERSION:
            raise ReleaseSecurityError(
                f"pinned Glyphs 3 surface must remain {PINNED_GLYPHS3_VERSION}: {path}"
            )

    for relative in AGENT_PLUGIN_MANIFESTS:
        manifest_version = _read_agent_plugin_version(root / relative)
        if manifest_version != version:
            raise ReleaseSecurityError(
                f"agent plug-in manifest {relative} is {manifest_version}, expected {version}"
            )

    if app_plist is not None:
        app_version, app_build = read_plist_version(app_plist.resolve(), require_matching_build=False)
        if app_version != version or int(app_build) != installer_build:
            raise ReleaseSecurityError(
                f"built installer metadata {app_version} ({app_build}) does not match "
                f"{version} ({installer_build})"
            )
    payload_manifest = None
    if payload_root is not None:
        payload_manifest = _validate_target_payload(payload_root.resolve(), version, root)
    runtime_identity = None
    if payload_manifest is not None:
        runtime_identity = {"lean": payload_manifest["leanIdentity"]} if lean else dict(payload_manifest["targets"]["4"]["runtimeIdentity"])

    return {
        "releaseVersion": version,
        "installerBuild": installer_build,
        "targets": {"3": PINNED_GLYPHS3_VERSION, "4": version},
        "canonicalSchemaVersion": None if lean else CURRENT_V2_CANONICAL_SCHEMA_VERSION,
        "publicToolCount": 7 if lean else CURRENT_V2_PUBLIC_TOOL_COUNT,
        "managedSkillCount": len(json.loads((root / "skills/manifest.json").read_text())["managedSkills"]) if lean else 18,
        "runtimeIdentity": runtime_identity,
        "payloadValidated": payload_root is not None,
        "builtAppValidated": app_plist is not None,
        "signed": False,
        "notarized": False,
        "publishable": False,
        "knowledgeDependencies": knowledge,
    }


def validate_candidate_repository_state(repo_root: Path) -> None:
    root = repo_root.resolve()
    for base in ("main", "origin/main"):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, "HEAD"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "not an ancestor of HEAD"
            raise ReleaseSecurityError(f"unsigned candidate is not based on {base}: {detail}")


def validate_signing_preflight(repo_root: Path) -> None:
    root = repo_root.resolve()
    required = (
        root / "scripts/build_installer_app.sh",
        root / "scripts/notarize_installer_app.sh",
        root / "scripts/verify_release_artifacts.sh",
        root / "scripts/publish_release_assets.sh",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ReleaseSecurityError("release signing scripts are missing: " + ", ".join(missing))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in required)
    for marker in ("Developer ID Application", "notarytool", "stapler", "codesign", "git verify-tag"):
        if marker not in combined:
            raise ReleaseSecurityError(f"release signing preflight is missing {marker!r}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_knowledge_dependencies(
    repo_root: Path,
    *,
    check_upstream: bool = False,
) -> dict[str, Any]:
    """Verify vendored authority offline and optionally fail on upstream drift."""

    root = repo_root.resolve()
    knowledge_root = root / "third_party/glyphs-file-format-v4"
    manifest_path = knowledge_root / "knowledge-dependencies.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReleaseSecurityError(
            f"could not read knowledge provenance manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(manifest, Mapping) or manifest.get("schemaVersion") != 1:
        raise ReleaseSecurityError("knowledge provenance manifest schema is unsupported")
    if not str(manifest.get("auditedAt") or ""):
        raise ReleaseSecurityError("knowledge provenance manifest lacks an audit date")
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ReleaseSecurityError("knowledge provenance manifest has no dependencies")
    if not (knowledge_root / "LICENSE").is_file():
        raise ReleaseSecurityError("vendored Glyphs format reference lacks its license")

    verified = []
    drift_checked = []
    for raw in dependencies:
        if not isinstance(raw, Mapping):
            raise ReleaseSecurityError("knowledge dependency entry is malformed")
        identity = str(raw.get("id") or "")
        source = str(raw.get("source") or "")
        role = str(raw.get("role") or "")
        if not identity or not source or not role:
            raise ReleaseSecurityError("knowledge dependency lacks id, source, or role")
        audited_at = str(raw.get("auditedAt") or manifest.get("auditedAt") or "")
        local_path = raw.get("localPath")
        expected_hash = str(raw.get("sha256") or "")
        commit = str(raw.get("commit") or "")
        branch = str(raw.get("branch") or "")
        authoritative = role != "explanatory_online"
        if not audited_at:
            raise ReleaseSecurityError(f"knowledge dependency lacks an audit date: {identity}")
        if authoritative:
            missing = [
                key
                for key in ("branch", "commit", "path", "localPath", "sha256", "license")
                if not raw.get(key)
            ]
            if missing:
                raise ReleaseSecurityError(
                    f"pinned knowledge dependency lacks {', '.join(missing)}: {identity}"
                )
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ReleaseSecurityError(
                    f"pinned knowledge dependency has an invalid commit: {identity}"
                )
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                raise ReleaseSecurityError(
                    f"pinned knowledge dependency has an invalid SHA-256: {identity}"
                )
        if expected_hash:
            if not isinstance(local_path, str) or not local_path:
                raise ReleaseSecurityError(f"hashed knowledge dependency lacks localPath: {identity}")
            path = (knowledge_root / local_path).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ReleaseSecurityError(
                    f"knowledge dependency escapes the repository: {identity}"
                ) from exc
            if not path.is_file() or _sha256(path) != expected_hash:
                raise ReleaseSecurityError(
                    f"knowledge dependency hash differs from its pin: {identity}"
                )
            verified.append(identity)
        if check_upstream and commit:
            if not branch:
                raise ReleaseSecurityError(
                    f"pinned knowledge dependency lacks its upstream branch: {identity}"
                )
            try:
                result = subprocess.run(
                    ["git", "ls-remote", source, f"refs/heads/{branch}"],
                    cwd=root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=60,
                )
            except Exception as exc:
                raise ReleaseSecurityError(
                    f"could not resolve upstream knowledge head for {identity}: {exc}"
                ) from exc
            if result.returncode != 0:
                detail = result.stderr.strip() or "git ls-remote failed"
                raise ReleaseSecurityError(
                    f"could not resolve upstream knowledge head for {identity}: {detail}"
                )
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            head = lines[0].split()[0] if lines else ""
            if head != commit:
                raise ReleaseSecurityError(
                    f"upstream knowledge drift requires review for {identity}: {commit} -> {head or 'missing'}"
                )
            drift_checked.append(identity)
    required = {
        "glyphs-file-format-v4-schema",
        "glyphs-file-format-v4-specification",
        "glyphs-object-wrapper",
        "glyphs-python-reporter-template",
        "glyphs-python-palette-template",
    }
    if not required.issubset(verified):
        raise ReleaseSecurityError("official Glyphs v4 schema and specification pins are required")
    return {
        "auditedAt": manifest["auditedAt"],
        "verified": sorted(verified),
        "upstreamChecked": sorted(drift_checked),
        "upstreamDrift": False,
    }


def _safe_relative(path: Path, base_dir: Path) -> Path:
    if path.is_symlink():
        raise ReleaseSecurityError(f"artifact must be a regular non-symlink file: {path}")
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ReleaseSecurityError(f"artifact is outside checksum root: {path}") from exc
    if not resolved.is_file():
        raise ReleaseSecurityError(f"artifact must be a regular non-symlink file: {path}")
    return relative


def write_checksums(paths: Iterable[Path], output: Path, base_dir: Path) -> None:
    entries = []
    seen = set()
    for path in paths:
        relative = _safe_relative(path, base_dir)
        key = relative.as_posix()
        if key in seen:
            raise ReleaseSecurityError(f"duplicate checksum artifact: {key}")
        seen.add(key)
        entries.append((key, _sha256(path.resolve())))
    if not entries:
        raise ReleaseSecurityError("no artifacts were supplied for checksums")
    if output.is_symlink():
        raise ReleaseSecurityError("checksum output must not be a symlink")
    output_resolved = output.resolve()
    try:
        output_relative = output_resolved.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ReleaseSecurityError("checksum output must be inside its artifact root") from exc
    if output_relative.as_posix() in seen:
        raise ReleaseSecurityError("checksum output must not overwrite a release artifact")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(entries)), encoding="utf-8")


def verify_checksums(
    checksum_file: Path,
    base_dir: Path,
    expected_paths: Iterable[Path] | None = None,
) -> None:
    _safe_relative(checksum_file, base_dir)
    try:
        lines = checksum_file.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        raise ReleaseSecurityError(f"could not read checksum file: {exc}") from exc
    if not lines:
        raise ReleaseSecurityError("checksum file is empty")
    seen = set()
    for line in lines:
        match = CHECKSUM_RE.fullmatch(line)
        if not match:
            raise ReleaseSecurityError(f"malformed checksum line: {line!r}")
        expected, name = match.groups()
        relative = Path(name)
        normalized_name = relative.as_posix()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or normalized_name != name
            or normalized_name in seen
        ):
            raise ReleaseSecurityError(f"unsafe or duplicate checksum path: {name!r}")
        seen.add(normalized_name)
        candidate = base_dir / relative
        if candidate.is_symlink():
            raise ReleaseSecurityError(f"checksum artifact is missing or unsafe: {name!r}")
        path = candidate.resolve()
        try:
            path.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ReleaseSecurityError(f"checksum path escapes artifact root: {name!r}") from exc
        if not path.is_file():
            raise ReleaseSecurityError(f"checksum artifact is missing or unsafe: {name!r}")
        actual = _sha256(path)
        if actual != expected:
            raise ReleaseSecurityError(f"checksum mismatch for {name!r}")
    if expected_paths is not None:
        expected_names = {_safe_relative(path, base_dir).as_posix() for path in expected_paths}
        if seen != expected_names:
            missing = sorted(expected_names - seen)
            unexpected = sorted(seen - expected_names)
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected: {', '.join(unexpected)}")
            raise ReleaseSecurityError(f"checksum manifest artifact set differs ({'; '.join(details)})")


def validate_release_state(
    release_data: Mapping[str, Any],
    tag: str,
    expected_asset_names: Iterable[str],
) -> None:
    if release_data.get("tagName") != tag:
        raise ReleaseSecurityError(
            f"release tag mismatch: {release_data.get('tagName')!r} != {tag!r}"
        )
    if release_data.get("isDraft") is not True:
        raise ReleaseSecurityError("release must remain a draft while verified assets are uploaded")
    if "-beta." in tag and release_data.get("isPrerelease") is not True:
        raise ReleaseSecurityError("beta release draft must be marked as a prerelease before upload")
    raw_assets = release_data.get("assets")
    if not isinstance(raw_assets, list):
        raise ReleaseSecurityError("release asset metadata is malformed")
    existing = set()
    for item in raw_assets:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ReleaseSecurityError("release asset metadata is malformed")
        existing.add(item["name"])
    expected = set(expected_asset_names)
    if "" in expected:
        raise ReleaseSecurityError("expected release asset names must not be empty")
    if existing:
        raise ReleaseSecurityError(
            "release draft must be empty before upload; found: " + ", ".join(sorted(existing))
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    metadata = subparsers.add_parser("metadata", help="verify source, installer, and tag version alignment")
    metadata.add_argument("--repo-root", type=Path, required=True)
    metadata.add_argument("--tag", required=True)
    metadata.add_argument("--app-plist", type=Path)

    candidate = subparsers.add_parser(
        "candidate",
        help="verify an unsigned local v2 candidate without requiring a tag or signature",
    )
    candidate.add_argument("--repo-root", type=Path, required=True)
    candidate.add_argument("--version", required=True)
    candidate.add_argument("--installer-build", type=int, required=True)
    candidate.add_argument("--payload-root", type=Path)
    candidate.add_argument("--app-plist", type=Path)

    knowledge = subparsers.add_parser(
        "knowledge",
        help="verify pinned Glyphs format knowledge and optionally compare upstream heads",
    )
    knowledge.add_argument("--repo-root", type=Path, required=True)
    knowledge.add_argument("--check-upstream", action="store_true")

    checksums = subparsers.add_parser("checksums", help="write deterministic SHA-256 checksums")
    checksums.add_argument("--base-dir", type=Path, required=True)
    checksums.add_argument("--output", type=Path, required=True)
    checksums.add_argument("paths", type=Path, nargs="+")

    verify = subparsers.add_parser("verify-checksums", help="verify a generated checksum manifest")
    verify.add_argument("--base-dir", type=Path, required=True)
    verify.add_argument(
        "--expect",
        action="append",
        default=[],
        type=Path,
        help="require this exact artifact in the manifest (repeatable)",
    )
    verify.add_argument("checksum_file", type=Path)

    release_state = subparsers.add_parser(
        "release-state",
        help="verify that the remote release is an empty compatible draft",
    )
    release_state.add_argument("--tag", required=True)
    release_state.add_argument("--release-json", required=True)
    release_state.add_argument("--expect-name", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "metadata":
            print(validate_release_metadata(args.repo_root, args.tag, args.app_plist))
        elif args.command == "candidate":
            validate_candidate_repository_state(args.repo_root)
            validate_signing_preflight(args.repo_root)
            result = validate_unsigned_candidate(
                args.repo_root,
                expected_version=args.version,
                installer_build=args.installer_build,
                payload_root=args.payload_root,
                app_plist=args.app_plist,
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "knowledge":
            print(
                json.dumps(
                    validate_knowledge_dependencies(
                        args.repo_root,
                        check_upstream=args.check_upstream,
                    ),
                    sort_keys=True,
                )
            )
        elif args.command == "checksums":
            write_checksums(args.paths, args.output, args.base_dir)
            print(args.output)
        elif args.command == "verify-checksums":
            verify_checksums(args.checksum_file, args.base_dir, args.expect or None)
            print("checksums verified")
        else:
            try:
                release_data = json.loads(args.release_json)
            except json.JSONDecodeError as exc:
                raise ReleaseSecurityError(f"release metadata is not valid JSON: {exc}") from exc
            if not isinstance(release_data, Mapping):
                raise ReleaseSecurityError("release metadata must be a JSON object")
            validate_release_state(release_data, args.tag, args.expect_name)
            print("release draft verified")
    except ReleaseSecurityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
