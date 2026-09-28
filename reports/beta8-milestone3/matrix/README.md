# Native cleanup comparison

Five fresh native processes per case/route; 100 passing runs. These are native harness workflows,
not installed-client latency or actual editor Save measurements. Raw files retain stage timings
and native host identity; `summary.json` contains all metric medians/minima/maxima.

Seconds shown as median [minimum–maximum]. Cleanup scheduling includes application and
selective recovery for typed edits; script restoration reloads the saved font instead.

| Workload | Targets | Format | Total before → after | Longest scheduled cleanup before → after |
| --- | ---: | --- | --- | --- |
| width | 1000 | .glyphs | 0.658 [0.652–0.740] → 0.900 [0.893–1.204] | 0.215 [0.212–0.259] → 0.010 [0.010–0.022] |
| width | 1000 | .glyphspackage | 1.254 [1.186–1.429] → 1.630 [1.543–1.661] | 0.233 [0.224–0.257] → 0.010 [0.010–0.017] |
| width | 4096 | .glyphs | 2.596 [2.433–2.847] → 3.032 [2.978–3.050] | 0.933 [0.897–1.144] → 0.011 [0.010–0.013] |
| width | 4096 | .glyphspackage | 2.999 [2.927–3.257] → 3.623 [3.592–3.766] | 0.856 [0.849–0.970] → 0.011 [0.011–0.011] |
| script | 1000 | .glyphs | 0.570 [0.564–0.664] → 0.567 [0.561–0.579] | 0.000 [0.000–0.000] → 0.000 [0.000–0.001] |
| script | 1000 | .glyphspackage | 0.952 [0.894–0.975] → 0.964 [0.931–0.988] | 0.000 [0.000–0.001] → 0.000 [0.000–0.001] |
| script | 10000 | .glyphs | 3.940 [3.922–4.244] → 3.978 [3.932–4.228] | 0.002 [0.002–0.003] → 0.002 [0.001–0.004] |
| script | 10000 | .glyphspackage | 7.676 [7.346–8.139] → 7.535 [7.289–7.796] | 0.003 [0.003–0.003] → 0.001 [0.001–0.009] |
| script | 20000 | .glyphs | 7.851 [7.608–9.559] → 8.163 [8.029–8.447] | 0.005 [0.005–0.005] → 0.005 [0.004–0.021] |
| script | 20000 | .glyphspackage | 15.756 [15.284–16.407] → 15.238 [15.075–15.727] | 0.005 [0.004–0.007] → 0.007 [0.005–0.016] |

The cleanup maximum is not an overall UI-pause limit. Inspect the overall scheduled
maximum, main-thread call maximum and stage timings in the JSON before making a responsiveness
claim. Individual native calls, whole-font source checks and script invocations remain indivisible.
Peak RSS includes runtime, fixture and verification, not only incremental edit memory.
