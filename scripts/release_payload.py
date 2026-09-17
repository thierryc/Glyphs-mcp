#!/usr/bin/env python3
"""Sign and verify all native code in a lean installer payload, locally."""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile

from build_installer_payload import validate_payload
from build_simple_v2 import _identity, _fingerprint_helper

IDENTITY = "Developer ID Application: Thierry Charbonnel (N9U29A4T8J)"
TEAM = "N9U29A4T8J"
BRIDGE = "Glyphs MCP Bridge.glyphsPlugin"
COMPANIONS = {"curve-inspector": "Glyphs Curve Inspector.glyphsReporter",
              "reference-inspector": "Glyphs Reference Inspector.glyphsReporter"}
SUFFIXES = {".glyphsPlugin", ".glyphsReporter", ".glyphsPalette", ".glyphsTool",
            ".glyphsFilter", ".glyphsFileFormat", ".framework", ".app"}
MAGIC = {bytes.fromhex(value) for value in (
    "feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca", "cafebabf", "bfbafeca")}


def inventory(root):
    root = Path(root).resolve()
    native, bundles = [], []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            if not path.resolve().is_relative_to(root):
                raise ValueError("Payload symlink escapes root: " + str(path))
            continue
        if path.is_dir() and path.suffix in SUFFIXES:
            bundles.append(path)
        elif path.is_file():
            with path.open("rb") as stream:
                if stream.read(4) in MAGIC:
                    native.append(path)
    applications = [path for path in bundles if path.suffix == ".app"]
    native = [path for path in native if not any(app in path.parents for app in applications)]
    return native, sorted(bundles, key=lambda p: (-len(p.parts), str(p)))


def managed_bundles(root):
    return [root / "Lean" / BRIDGE, *(root / "Lean" / n for n in COMPANIONS.values())]


def component_records(root, manifest):
    lean = root / "Lean"
    if manifest["bridge"]["bundle"] != BRIDGE:
        raise ValueError("Unexpected bridge bundle")
    records = [(lean / BRIDGE, manifest["bridge"]), (lean / "sidecar", manifest["sidecar"])]
    if {c["id"] for c in manifest["companions"]} != set(COMPANIONS) or len(manifest["companions"]) != 2:
        raise ValueError("Unexpected companions")
    for item in manifest["companions"]:
        if item["bundle"] != COMPANIONS[item["id"]]:
            raise ValueError("Unexpected companion bundle")
        records.append((lean / item["bundle"], item))
    if set(manifest["runtimes"]) != {"arm64", "x86_64"}:
        raise ValueError("Both private runtime architectures are required")
    for arch, item in manifest["runtimes"].items():
        if item["path"] != "runtimes/" + arch:
            raise ValueError("Unexpected private runtime path")
        records.append((lean / item["path"], item))
    for path, _ in records:
        if not path.is_dir() or path.is_symlink():
            raise ValueError("Missing regular component directory: " + str(path))
    return records


def refresh_identities(root):
    """Release-only: call after verified signing or accepted stapling, before sealing the app."""
    root = Path(root).resolve()
    inventory(root)  # Reject escaping paths before following files for hashing.
    lean_path = root / "Lean/manifest.json"
    manifest = json.loads(lean_path.read_text())
    for path, record in component_records(root, manifest):
        record["identity"] = _identity(path)
        if "codeHash" in record:
            record["codeHash"] = _fingerprint_helper().payload_hash(path)
    lean_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    outer_path = root / "payload.json"
    outer = json.loads(outer_path.read_text())
    outer["leanIdentity"] = _identity(root / "Lean")
    outer_path.write_text(json.dumps(outer, indent=2, sort_keys=True) + "\n")


def verify_identities(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "Lean/manifest.json").read_text())
    for path, record in component_records(root, manifest):
        if "codeHash" in record and record["codeHash"] != _fingerprint_helper().payload_hash(path):
            raise ValueError("Component code fingerprint mismatch: " + str(path))
        if record["identity"] != _identity(path):
            raise ValueError("Component identity mismatch: " + str(path))
    outer = json.loads((root / "payload.json").read_text())
    if outer["leanIdentity"] != _identity(root / "Lean"):
        raise ValueError("Lean payload identity mismatch")


def run(*args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed for {args[-1]}: {result.stdout}{result.stderr}")
    return result.stdout + result.stderr


def verify_code(path, identity=IDENTITY):
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", path)
    details = run("/usr/bin/codesign", "-d", "--verbose=4", path)
    for expected in ("Authority=" + identity, "TeamIdentifier=" + TEAM, "(runtime)", "Timestamp="):
        if expected not in details:
            raise ValueError(f"Missing {expected} in signature: {path}")


def sign_payload(root, identity=IDENTITY):
    validate_payload(root)
    verify_identities(root)
    natives, bundles = inventory(root)
    if not natives or len(bundles) < 3:
        raise ValueError("Missing native payload code")
    with tempfile.TemporaryDirectory(prefix="glyphs-sign-entitlements-") as temporary:
        cli_entitlements = Path(temporary) / "glyphs-cli.plist"
        # The CLI intentionally loads the user's Glyphs framework (a different Team ID).
        cli_entitlements.write_bytes(plistlib.dumps({"com.apple.security.cs.disable-library-validation": True}))

        def sign(path):
            subprocess.run(["/usr/bin/codesign", "--remove-signature", str(path)], capture_output=True)
            args = ["/usr/bin/codesign", "--sign", identity, "--timestamp", "--options", "runtime"]
            if path in [root / "Lean/runtimes" / a / "bin/glyphs" for a in ("arm64", "x86_64")]:
                args += ["--entitlements", str(cli_entitlements)]
            if path.suffix == ".app":
                args += ["--force", "--deep"]
            run(*args, path)
            verify_code(path, identity)

        for native in natives:
            sign(native)
        for bundle in bundles:
            sign(bundle)
    refresh_identities(root)
    print(json.dumps({"signedMachO": len(natives), "signedBundles": len(bundles)}))


def verify_payload(root, identity=IDENTITY, *, installed=False):
    validate_payload(root)
    verify_identities(root)
    natives, bundles = inventory(root)
    if not natives or len(bundles) < 3:
        raise ValueError("Missing native payload code")
    for path in natives + bundles:
        verify_code(path, identity)
    if installed:
        # Copy every managed component, including runtimes. No signing or mutation at install time.
        with tempfile.TemporaryDirectory(prefix="glyphs-signed-install-") as temporary:
            for index, source in enumerate(managed_bundles(root) + [root / "Lean/runtimes"]):
                destination = Path(temporary) / str(index) / source.name
                destination.parent.mkdir()
                run("/usr/bin/ditto", source, destination)
                if _identity(source) != _identity(destination):
                    raise ValueError("Installed component identity changed: " + source.name)
                if source.suffix in SUFFIXES:
                    verify_code(destination, identity)
                    run("/usr/bin/xcrun", "stapler", "validate", destination)
                    if not (destination / "Contents/CodeResources").is_file():
                        raise ValueError("Installed notarization ticket is missing")
    print(json.dumps({"verifiedMachO": len(natives), "verifiedBundles": len(bundles), "installedCopy": installed}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sign", "verify", "refresh", "bundles"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--identity", default=IDENTITY)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "sign": sign_payload(root, args.identity)
    elif args.action == "verify": verify_payload(root, args.identity, installed=args.installed)
    elif args.action == "refresh": refresh_identities(root)
    else:
        validate_payload(root)
        for path in managed_bundles(root):
            if not path.is_dir(): raise ValueError("Missing managed bundle: " + str(path))
            print(path)


if __name__ == "__main__": main()
