# P13 implementation qualification

Target the current private lean v2 on Glyphs 4.1 (4107). Preserve the seven tools,
sidecar/bridge/core code, native Undo and autosaving, v1, all original reports and
user fonts. Implement only the focused curvature guidance and bounded companion
coverage feedback. No release publication or queue/Undo optimization.

Use the existing native P13 oracle and independent Bernstein formulas. Numerical
tolerance is 1e-9; stored data/object restoration requires exact equality. Exclude
derived bounds from the stored-data hash and record their hash separately.

**Realistic input:** the prior P09 frozen 423-glyph, nine-master Dactylotype copy.
Use fresh disposable copies and obtain each ID from public discovery. Inspect
`o s a n at eight A AE aacute space` in master indices 0, 3 and 6 (Thin Condensed,
Regular Condensed, Black Condensed). Preserve all nine masters and other glyphs.
Record the full input file manifest. Retain a local private source copy in the
candidate build folder; do not add that font source to the committed archive.

**Protocol:** first attempt, one warm-up and five timed complete replays for `o`
and `at`: enable, inspect, native +1 x node nudge, Undo, Redo, Undo, disable,
re-enable, disable. Stop a series on exact-restoration failure; do not fill missing
samples with a different task. Repeat any suspicious behavior on a fresh copy
with Curve Inspector disabled. Keep native test preparation and verification
separate from public tools/UI; no helper performs task edits or history.

**Coverage:** direct paths, mixed and component-only layers, empty/straight layers,
closed contour wraparound, exactly 128 and 129 cubics, three-master switching,
text/Font View, zoom, dirty reads, no stale notice, exact whole-font preservation.
The added node/path scan bounds receive deterministic test-double coverage.
Native timing uses the existing bounded ten-second probe, with restored callbacks
and at least two seconds after the last callback; heavy preservation snapshots
stay outside this interval. Record HTTP latency independently.

**Reproduction:** `fixture.py` accepts a new output path and uses the original
P13 `CurvatureTest.glyphs`. Run through the installed `glyphs run -a
"/Applications/Glyphs 4.app" --plugins ""` CLI. Its seeded timestamps reproduce the
tested added fixture byte for byte. For another native run, copy the harness to a
new report folder and set its OUT/FOLDER paths there; do not overwrite this report.
`ui-replay.js` uses case-encoded artifact filenames. `ui-replay-recorded.js` preserves
the original run, including its A/a naming mistake; unique native acknowledgements
retain all actual results. Never reuse a document ID across disposable copies or
relaunches. Do not publish a success if a required assertion fails.
