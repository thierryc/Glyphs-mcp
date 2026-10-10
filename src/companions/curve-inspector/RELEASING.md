# Curve Inspector releases

Curve Inspector has its own version, bundle build and tag. A companion-only
change does not require a new Glyphs MCP desktop product version. The full
desktop pipeline in `macos-installer/RELEASING.md` is appropriate when the
application, server, installer or deliberately embedded distribution changes.
A later desktop build must include the current companion source and rerun its
own signed-container checks; the standalone plugin does not update Sparkle.

## Preparation and proportional verification

1. Review the scoped diff and preserve unrelated work. Increment the companion
   plist version/build and Reporter registration together. Keep the engine
   version when its implementation is unchanged. Freeze the source fingerprints.
2. Use `scripts/build_curve_inspector.py --output <new-versioned-candidate>`.
   It bundles identical canonical engine bytes into plugin and skill, excludes
   caches and retains Apache, GlyphsSDK and pinned SuperTool notices.
3. Validate the unsigned SDK loader and bundle before signing. For packaging
   changes, run the focused build/Reporter checks once and carry forward the
   explicitly identified engine/UI qualification when implementation hashes
   match. Native behavior changes need their affected tests. Do not run the
   complete MCP/desktop/VM matrix for a standalone metadata patch.
4. Preserve the installed working bundle. Stage distribution bytes in a new
   versioned directory; never sign source or the current installation in place.

## Signing and notarization gates

Use the existing Developer ID Application certificate and `gmcp-notary`
Keychain profile. Signing and trust verification need macOS trust-service
access; an unavailable authority in a sandbox is not valid release evidence.
Never export private keys or credentials. Apple notarization is a validation
submission, separate from GitHub publication.

- Inventory Mach-O files. This bundle has one universal SDK loader. If nested
  code is added, sign it inside out. Sign the final bundle with secure timestamp
  and hardened runtime; do not add broad entitlements or use deep signing.
- Verify `codesign --verify --deep --strict` and explicitly check Developer ID,
  team `N9U29A4T8J`, hardened runtime, timestamp, bundle ID and architectures.
  Signing changes the loader hash; its original upstream SDK hash remains
  provenance, while the signed hash belongs in the distribution receipt.
- Create a private submission ZIP with `ditto -c -k --keepParent`. Submit with
  `notarytool`, retain its ID, require `Accepted`, and inspect the report. After
  uncertain output, query that submission; do not upload a duplicate blindly.
- Staple the accepted ticket to the plugin, validate it, and verify the signature
  again. For this Glyphs plugin, Gatekeeper uses `spctl --assess --type install`;
  require `Notarized Developer ID`. Never disable Gatekeeper to pass a check.
- Package the stapled bundle into the final plugin ZIP. Extract those exact bytes
  with `ditto`, then repeat signature, ticket and Gatekeeper checks. Verify
  copy identity, engine/skill consistency and absence of caches or private QA data.
  One deliberate tampered-resource copy must be refused by signature validation.

These gates follow [Apple Developer ID guidance](https://developer.apple.com/developer-id/)
and [Apple's custom notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow).
A ZIP itself cannot receive the plugin's ticket; archive the already-stapled
bundle. The plain-Python skill ZIP does not need a fabricated code signature.

## Sealing and local installation

Seal the plugin ZIP, bundled skill ZIP, release manifest, release notes and
SHA256SUMS. Record version/build, engine digest, controller digest, signed bundle
file inventory, source commit/tag, Apple submission ID and exact acceptance.
Keep credentials, raw private-font records and notarization upload ZIPs out of
public assets. Final checksums are calculated after all signing/stapling.

Install the final signed/stapled plugin through Glyphs' native installer; check
that the installed file inventory and trust evidence match the sealed artifact.
Never re-sign installed files. Request a safe Glyphs relaunch with unsaved work
accounted for, then verify the registered companion version and open its panel.
For an unchanged implementation this is a focused load/trust smoke check, not
another font-mutation qualification cycle.

Commit only release-owned public source and evidence. Leave checkout routing,
private/local QA and unrelated diagnostics unstaged. Create a local signed
`curve-inspector-v<VERSION>` tag. Preserve the previous verified bundle.

## Publication boundary

Local preparation never invokes `publish_release_assets.sh`, pushes a branch or
tag, creates/uploads a GitHub draft, updates an appcast or deploys the website.
The desktop publisher verifies desktop identities and must not be reused with
a companion tag. Future publication uploads the sealed standalone inventory
without rebuilding or re-signing. Keep the companion release out of the desktop
Latest/update feed (`make_latest=false`), even though the plugin release is
stable. Public asset digest checks happen after separately authorized upload;
record them as unperformed during local preparation.
