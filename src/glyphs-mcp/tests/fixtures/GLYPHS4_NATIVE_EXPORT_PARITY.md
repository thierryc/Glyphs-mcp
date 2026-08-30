# Glyphs 4 native-export parity fixture

`glyphs4-native-export-parity.json` is deliberately committed in
`capture_required` state. It contains no claimed native observations. The v2
release gate must fail until an authentic capture and its complete artifact
tree are committed.

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

`--schema-only` exists solely to validate this pending plan. It must never be
used by a release workflow. The default validator rejects pending evidence,
harness drift, unsupported hosts, missing provenance, links or special files,
artifact inventory drift, weak contextual controls, missing vertical shaping,
and incomplete half-tie coverage.

The capture is characterization evidence, not a recommendation about optical
kerning quality. No observation should be inferred from Glyphs documentation,
the v2 compiler, or synthetic offline test expectations.
