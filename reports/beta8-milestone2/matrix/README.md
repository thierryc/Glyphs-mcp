# Milestone 2 native-route benchmark

Five fresh processes per route, case and format. Times below are median [minimum–maximum] seconds. Both routes use identical prebuilt fixtures. Baseline is the frozen milestone 1 runtime; this is not a v1 or external-worker comparison.

Colors select 1/10/100 glyphs from 501, with two masters and four triangular contours on each foreground plus a four-contour Regular background. Widths select 1/100/1,000/4,096 named glyphs from 5,000, each with one master and four contours in foreground and background. Requests name dispersed glyphs in reverse order. All unselected persisted contents, backgrounds, native Undo/Redo and selective recovery are checked.

| Task | Format | Targets | Before prep | After prep | Before prepare + apply | After prepare + apply |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| color | glyphs | 1 | 0.168 [0.164–0.176] | 0.077 [0.074–0.079] | 0.404 [0.401–0.409] | 0.527 [0.520–0.539] |
| color | glyphs | 10 | 0.997 [0.987–1.008] | 0.104 [0.093–0.109] | 3.051 [2.923–3.057] | 2.038 [2.015–2.309] |
| color | glyphs | 100 | 9.424 [9.338–9.718] | 0.446 [0.429–0.465] | 27.618 [27.333–28.015] | 19.189 [18.833–19.285] |
| color | glyphspackage | 1 | 0.196 [0.187–0.203] | 0.113 [0.103–0.123] | 0.683 [0.671–0.684] | 0.599 [0.590–0.618] |
| color | glyphspackage | 10 | 1.035 [1.026–1.077] | 0.132 [0.118–0.136] | 2.982 [2.938–3.022] | 2.062 [2.019–2.236] |
| color | glyphspackage | 100 | 9.515 [9.457–9.608] | 0.460 [0.455–0.481] | 27.708 [27.569–28.147] | 18.810 [18.465–18.895] |
| width | glyphs | 1 | 0.607 [0.593–0.623] | 0.069 [0.062–0.072] | 0.692 [0.673–0.730] | 0.144 [0.128–0.290] |
| width | glyphs | 100 | 0.622 [0.600–0.648] | 0.079 [0.066–0.086] | 0.720 [0.691–0.730] | 0.138 [0.137–0.391] |
| width | glyphs | 1,000 | 0.588 [0.582–0.608] | 0.199 [0.190–0.202] | 1.035 [1.012–1.091] | 0.657 [0.651–0.665] |
| width | glyphs | 4,096 | 0.666 [0.657–0.673] | 0.640 [0.632–0.642] | 2.449 [2.394–2.472] | 2.399 [2.393–2.420] |
| width | glyphspackage | 1 | 0.845 [0.838–0.854] | 0.349 [0.346–0.397] | 1.133 [1.125–1.175] | 0.637 [0.619–0.680] |
| width | glyphspackage | 100 | 0.897 [0.854–0.947] | 0.363 [0.302–0.398] | 1.512 [1.423–1.587] | 0.948 [0.851–0.974] |
| width | glyphspackage | 1,000 | 0.921 [0.894–0.952] | 0.438 [0.420–0.440] | 1.687 [1.640–1.757] | 1.092 [1.073–1.131] |
| width | glyphspackage | 4,096 | 1.017 [1.013–1.072] | 0.854 [0.835–0.883] | 3.310 [3.209–3.557] | 2.760 [2.708–2.822] |

All stage timings, longest measured calls/chunks and per-process peak RSS are in [summary.json](summary.json). Peak RSS includes native runtime, fixture loading and verification. It is not an incremental allocation measurement. These are local workflow timings, excluding process startup and fixture generation, with polling included in application. Clean baselines need no Save; Save time is zero. Actual editor saving and installed-client latency are separate checks.

Main-thread measurements cover instrumented bridge calls and scheduled callbacks; they do not cover all native event-loop work and are not a UI-stall guarantee. Verification uses persisted native property lists as well as scalar widths/colors and runs outside edit timings. Recovery timing includes guarded selective restoration; Undo/Redo verification is separate. The benchmark remains a small synthetic contour workload, not a capacity promise for arbitrary complex fonts.
