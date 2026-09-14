# P13 lean coverage improvement and realistic-font qualification

Implemented and installed the focused curvature guidance and bounded companion
coverage notice on Glyphs 4.1 (4107). The sidecar, bridge, seven-tool catalog,
comb geometry, jobs, Undo and autosave implementations are unchanged.

The final candidate passes 30/30 realistic display/coverage controls and 577 lean
regressions. Exact native Undo restoration fails for fractional nodes in `at`
and `s`; the `at` failure reproduces with Curve Inspector disabled. Do not read
this checkpoint as unconditional native history or stability approval.

`evidence.tar.gz` contains the full follow-up folder, all intermediate-revision
results, timestamped public/native/UI logs, screenshots, independent analysis,
fixture generator and its required oracle/client files. Every member was read
back and verified against `evidence-manifest.json`. Archive paths are relative
to the parent workspace. Extract into a fresh directory to follow evidence links:

```sh
mkdir p13-followup-evidence
tar -xzf evidence.tar.gz -C p13-followup-evidence
```

Open `p13-followup-evidence/reports/v1-v2/13-curvature-display/improvements-20260913/report.md`.
The original paired benchmark remains in the prior
`reports/p13-curvature-display-20260913` checkpoint; its full raw evidence is in
that checkpoint's separate archive, not duplicated here. All 1,445 original P13
artifact hashes remain unchanged.

The private Dactylotype source is **not** committed. The exact 451-file baseline
is retained locally under `build/p13-curvature-candidate/fixtures/` and its full
source manifest is in the evidence. Native scripts contain historical local
paths; adapt only in a fresh report folder and read the test specification before
running. Extraction or analysis does not run Glyphs, authorize a new autosave
change, or silently reperform failed history tests.

The installed curve bundle fingerprint is
`49263f6ab0d19d391251adca825cf2cba73c65531fb45f16a74cab3467bd85dc`.
Configured focused skills match the tested payload. Original fonts/settings,
v1 and unrelated work are preserved. No release publication occurred.
