#!/usr/bin/env python3
"""Pure metadata and checksum gates for the local release workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import sys
from typing import Any, Iterable, Mapping


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MARKETING_VERSION_RE = re.compile(r"\bMARKETING_VERSION\s*=\s*(\d+\.\d+\.\d+)\s*;")
BUILD_VERSION_RE = re.compile(r"\bCURRENT_PROJECT_VERSION\s*=\s*(\d+)\s*;")
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")


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


def validate_release_metadata(repo_root: Path, tag: str, app_plist: Path | None = None) -> str:
    root = repo_root.resolve()
    source_plist = root / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist"
    manager_plist = root / "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist"
    project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"

    version, _ = read_plist_version(source_plist)
    manager_version, _ = read_plist_version(manager_plist)
    if manager_version != version:
        raise ReleaseSecurityError(f"Plugin Manager version {manager_version} does not match source {version}")
    if tag != f"v{version}":
        raise ReleaseSecurityError(f"release tag {tag!r} must exactly match v{version}")

    marketing_versions, _build_versions = read_xcode_versions(project)
    if marketing_versions != {version}:
        values = ", ".join(sorted(marketing_versions))
        raise ReleaseSecurityError(f"Xcode MARKETING_VERSION values ({values}) do not all match {version}")

    if app_plist is not None:
        app_version, _ = read_plist_version(app_plist.resolve(), require_matching_build=False)
        if app_version != version:
            raise ReleaseSecurityError(f"built installer version {app_version} does not match source {version}")
    return version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    conflicts = sorted(expected & existing)
    if conflicts:
        raise ReleaseSecurityError(
            "draft already contains release asset(s): " + ", ".join(conflicts)
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    metadata = subparsers.add_parser("metadata", help="verify source, installer, and tag version alignment")
    metadata.add_argument("--repo-root", type=Path, required=True)
    metadata.add_argument("--tag", required=True)
    metadata.add_argument("--app-plist", type=Path)

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
