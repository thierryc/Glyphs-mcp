# Glyphs 4 native-export parity fixture

`glyphs4-native-export-parity.json` contains the committed native observations
captured on August 30, 2026 with Glyphs 4.0.1 build 4004 and Python 3.14.6.
The capture is bound to repository commit
`355134afa0f0f16c1f0d470050caa007b1ee69a3`, the exact harness hash, the
complete artifact inventory, and unchanged disposable working-source hashes.

The four required probes are:

- RTL class orientation from native directional storage, exported UFO groups,
  explicit kerning-file presence or absence, and compiled `kern` GPOS;
- vertical sign and YAdvance behavior from compiled `vkrn` plus HarfBuzz
  `ttb` shaping with the feature on and off;
- both contextual-kerning boundaries with one positive sequence and at least
  three negative shaping controls; and
- positive and negative Number Value half ties from native UFO feature source
  and compiled GPOS adjustments.

Capture is host-only. Open the approved `Glyphs MCP V2 Disposable` source in
Glyphs 4 build 4004 or newer and ensure it is clean. Load
`scripts/capture_glyphs4_native_export_parity.py` in the Macro Panel and call
its `capture()` function with a new absolute directory below `/tmp`, the full
repository commit, and the harness path. The harness builds and exports a
detached in-memory font; it refuses a non-disposable or dirty working document,
records the working source tree hash before and after, and never calls a source
save operation.

Copy the generated JSON and artifact directory beside this file, then run:

```bash
python3 scripts/validate_glyphs4_native_parity.py
```

`--schema-only` exists solely to validate an uncaptured plan. It must never be
used by a release workflow. The default validator rejects pending evidence,
harness drift, unsupported hosts, missing provenance, links or special files,
artifact inventory drift, weak contextual controls, missing vertical shaping,
and incomplete half-tie coverage.

The build-4004 observation records that the native UFO contains the expected
directional group orientation but omits `kerning.plist` for the RTL/vertical-
only probe. Compiled GPOS retains the RTL and vertical adjustments. Number
Value half ties use ties-to-even rounding: `2.5` becomes `2`, `-2.5` becomes
`-2`, and both `0.5` and `-0.5` become `0`.

The capture is characterization evidence, not a recommendation about optical
kerning quality. No observation should be inferred from Glyphs documentation,
the v2 compiler, or synthetic offline test expectations.
