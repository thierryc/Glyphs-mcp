# Local releases of Glyphs MCP

Build, test, sign, notarize and upload on the maintainer’s Mac. No GitHub
Actions or GitHub-hosted signing credentials are used for releases.

The current candidate is Glyphs MCP Desktop 2.0.0 Beta 4 / build 46,
with coordinated sidecar/bridge product version `2.0.0`, interface revision `1`
and bridge protocol `1`. Follow [the beta release plan](../BETA-LAUNCH.md)
for its prerelease tag, beta update feed and download names.
The Glyphs 4-only payload has seven tools, eleven managed skills, two optional
companions, the Cursor plugin and private Python runtimes for Apple Silicon and
Intel. Glyphs 3 remains available through its separate pinned v1.11.0 release
at v1.11.0 / 13ca805; it is not packaged in Beta 4.

## Prerequisites

Use Xcode, Git, authenticated GitHub CLI, a Python 3.14 development environment,
the locked private runtime caches, and a Developer ID Application certificate.
The default signing identity is Thierry Charbonnel (N9U29A4T8J).
Set `PYTHON_BIN` to the absolute path of the development Python executable.

Notarization reads the existing Keychain profile `gmcp-notary`; override it
with `NOTARY_PROFILE`. Create a profile using `xcrun notarytool
store-credentials` when necessary. Keep credentials in Keychain, never in the
repository or release assets.

## Versioning and verification

Read `scripts/desktop_release_identity.py` and `release.json` first. The helper
is the source of the release label, beta number, build, tag and channel URLs.
Use `scripts/bump_version.py --dry-run --beta N --installer-build BUILD X.Y.Z`
before applying a beta bump; omitting `--beta` selects a stable release. For a
final release use a new higher build and its separate qualification.
Align the bridge’s project version, installer marketing version and four
host plugin manifests. Increment the installer build for a new candidate.
The bridge protocol `1`, lean interface revision `1`, negotiated MCP transport
version and pinned Glyphs 3 version are separate. See
[version and identity](../content/reference/version-identity.mdx).
The installer’s displayed project version and build come from its bundle.

```sh
PYTHON_BIN=/absolute/path/to/python scripts/run_local_release_tests.sh
```

The local gate checks the complete Python and installer suites, skills, docs,
module budgets, deterministic unsigned payload builds, offline startup for
both private runtimes, source metadata and whitespace. Preserve the reviewed
disposable-font acceptance evidence and original-source hash separately.

## Build and sign

```sh
scripts/build_installer_app.sh
scripts/notarize_installer_app.sh
scripts/make_installer_dmg.sh
scripts/verify_release_artifacts.sh --tag v2.0.0-beta.4 --write-checksums
```

The Release installer is universal. `release_payload.py` discovers every
Mach-O file, including Python extensions, shared libraries, both glyphs-cli
executables and all plug-in loaders. It rejects paths escaping the payload,
removes old signatures, signs native files with secure timestamps and hardened
runtime, then seals code bundles from the inside out. Only glyphs-cli receives
`disable-library-validation`, because it loads the user’s separately signed
Glyphs framework. This entitlement is not applied to the installer or Python.

After signing, the release tool regenerates bridge, companion and runtime
identities in the lean manifest, then the outer payload identity. Installer
verification remains exact; signing is never performed during installation.

Notarization submits an expanded payload ZIP so Apple can inspect all nested
code. The accepted tickets are stapled to the Glyphs 4 bridge and both
companions. Identities are refreshed again after stapling. The payload is
compressed into the app’s sealed `Payload.gmcparchive`; the app is re-signed,
notarized and stapled, then the DMG is signed, notarized and stapled.

The final verifier checks Developer ID, team, hardened runtime, timestamps,
Gatekeeper acceptance, all nested signatures, component identities and
signature-preserving installation copies. It also checks the extracted app
ZIP. For stable releases it checks that the versioned/latest DMGs are
byte-identical. Beta artifacts use their prerelease suffix and must not include
`Glyphs-MCP-latest.dmg`. Run the private
runtime startup and native regression checks against the signed payload too.

`CONFIGURATION=Debug` is refused by the distribution builder.
`SKIP_NOTARIZATION=1` creates deliberately named non-release artifacts and
is refused by the publisher.

## Desktop update discovery

Sparkle 2.9.6 is checksum-pinned in `third_party/sparkle.json`. Its separate Ed25519 private key remains in Keychain under account `cx.ap.glyphsMcp`; the public key is in Info.plist. Never export private keys into the repository or release assets.

Run `scripts/build_desktop_release.sh` for the signed/notarized app, DMG and local update candidate. The product is `dist/installer-app/Glyphs MCP.app`. `dist/desktop-update/` contains the signed versioned ZIP, signed appcast, SHA256SUMS and an unpublished candidate record. The Xcode scheme remains GlyphsMCPInstaller. Sparkle nested apps, XPC services and frameworks are signed inside out with their entitlements preserved.

The Beta 4 feed candidate is `https://raw.githubusercontent.com/thierryc/Glyphs-mcp/lit/v2-beta/appcast.xml`; archives use the exact prerelease tag and versioned GitHub Releases URLs. Stable releases use `main/appcast.xml` after their separate release decision. Resolve these values from `desktop_release_identity.py`; do not hand-copy the stable feed into a beta build. Automatic checking is opt-in and installation is user initiated. Both the feed and archive must verify before extraction. Follow [Sparkle distribution guidance](https://sparkle-project.org/documentation/).

Publication is a separate approved step. Publish verified archives first, then the exact signed appcast. Never edit signed feed bytes. There are no GitHub Actions. Keep v1 documentation and download guidance intact; the legacy installer updater is not the desktop updater.

Application replacement and component migration are separate recoverable stages. A new manager must remain usable with previous components if migration fails. Test an actual signed older-to-newer update, invalid signatures, interrupted downloads, cancelled Glyphs closure and failed component migration before release.

The shared process control lock covers replacement startup as well as Stop and port changes. Recovery stops replacement code before restoring files. If safe stopping fails, retain the recovery journal instead of replacing files under a running process. The same sidecar service label is associated with `cx.ap.glyphsMcp`; no second supervisor is installed.


## Recovery

If Apple rejects a submission, retrieve its log with `xcrun notarytool log
<SUBMISSION_ID> --keychain-profile gmcp-notary`. Repair the cause and rebuild;
do not bypass verification. A partially uploaded draft stays private. Inspect
its exact state before removing a failed draft or starting a new release.
Never replace a distributed artifact to bypass the empty-draft gate. For a beta,
use a new beta number and higher installer build; for stable, use a new release
version and higher build. Requalify the resulting artifacts.
