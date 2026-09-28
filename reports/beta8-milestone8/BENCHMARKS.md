# Native benchmark evidence

Five fresh Glyphs CLI processes per route/count/format. Script uses recorded pre-change sources; typed uses the frozen candidate. Counts 100 and the explicit batch boundary are the same case.

Total edit time includes preparation, dispatch/application, polling and independent verification. Saving is a second equivalent result. Typed recovery restores selected entries; script recovery reloads the whole font. These are different recovery guarantees.

Peak RSS includes the Glyphs runtime and fixture, sampled before recovery. Longest chunk measures scheduled preparation/application work, not UI frame rate or all synchronous save/load work. CLI startup, HTTP, Codex latency and actual editor NSDocument saving are excluded and qualified separately.

| Route | Format | Pairs | Edit median ms [range] | Prepare ms | Apply/poll ms | Verify ms | Save ms | Recovery ms | Peak MiB | Longest scheduled chunk ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| script | glyphs | 1 | 305.47 [299.22–314.58] | 70.07 | 238.44 | 0.87 | 259.33 | 5.94 | 174.1 | 2.08 |
| script | glyphs | 10 | 304.87 [302.99–313.07] | 67.29 | 237.04 | 0.99 | 253.09 | 6.16 | 174.8 | 2.54 |
| script | glyphs | 100 | 312.81 [309.39–317.46] | 74.73 | 234.00 | 2.50 | 262.22 | 13.87 | 176.5 | 13.15 |
| script | glyphspackage | 1 | 312.10 [306.37–333.17] | 67.00 | 241.53 | 0.40 | 262.61 | 7.00 | 174.5 | 2.48 |
| script | glyphspackage | 10 | 302.78 [301.09–309.08] | 66.37 | 236.12 | 0.46 | 257.59 | 8.23 | 174.2 | 3.40 |
| script | glyphspackage | 100 | 320.85 [311.10–327.35] | 86.09 | 227.12 | 3.33 | 259.01 | 26.10 | 176.1 | 17.14 |
| typed | glyphs | 1 | 310.53 [307.08–317.75] | 70.96 | 239.95 | 0.59 | 254.14 | 254.32 | 174.9 | 1.32 |
| typed | glyphs | 10 | 304.93 [297.16–317.23] | 72.06 | 236.03 | 0.76 | 261.00 | 258.11 | 173.9 | 5.16 |
| typed | glyphs | 100 | 313.41 [310.98–322.32] | 91.03 | 217.44 | 2.46 | 261.94 | 257.39 | 177.9 | 10.54 |
| typed | glyphspackage | 1 | 310.87 [305.47–313.12] | 70.96 | 239.88 | 0.62 | 253.33 | 248.19 | 174.6 | 1.33 |
| typed | glyphspackage | 10 | 308.40 [301.72–378.36] | 70.94 | 235.48 | 0.73 | 257.95 | 257.15 | 174.7 | 5.06 |
| typed | glyphspackage | 100 | 312.55 [310.33–317.64] | 107.14 | 204.96 | 2.31 | 267.59 | 263.90 | 178.3 | 10.39 |

All metric ranges, including each stage and RSS, are in `benchmark-summary.json`; individual records retain host and source identities.

| Format | Glyph coverage | Languages | Returned pairs | Pages | All-page median ms [range] | Longest read median ms | Largest response bytes |
|---|---|---|---:|---:|---:|---:|---:|
| glyphs | sparse (30) | en | 339 | 19 | 128.70 [127.82–214.07] | 14.03 | 29556 |
| glyphs | sparse (30) | fr,de | 354 | 24 | 200.70 [194.46–287.60] | 15.68 | 29899 |
| glyphs | sparse (30) | all 24 | 357 | 34 | 767.36 [751.87–785.39] | 32.48 | 43383 |
| glyphs | dense (286) | en | 4341 | 46 | 636.56 [592.26–639.50] | 20.76 | 29590 |
| glyphs | dense (286) | fr,de | 5767 | 60 | 979.48 [926.38–1003.17] | 25.17 | 30080 |
| glyphs | dense (286) | all 24 | 8306 | 86 | 2944.73 [2609.11–3083.63] | 51.30 | 43283 |
| glyphspackage | sparse (30) | en | 339 | 19 | 132.94 [127.26–147.32] | 14.95 | 29556 |
| glyphspackage | sparse (30) | fr,de | 354 | 24 | 216.49 [202.07–228.34] | 15.62 | 29899 |
| glyphspackage | sparse (30) | all 24 | 357 | 34 | 872.08 [812.12–894.64] | 37.46 | 43383 |
| glyphspackage | dense (286) | en | 4341 | 46 | 608.24 [601.13–652.74] | 21.74 | 29590 |
| glyphspackage | dense (286) | fr,de | 5767 | 60 | 956.02 [927.46–974.28] | 24.10 | 30080 |
| glyphspackage | dense (286) | all 24 | 8306 | 86 | 2732.44 [2626.76–2848.31] | 46.18 | 43283 |

Proof timings include a cold bounded primary-Unicode map for each language filter. Every page visits at most 256 glyphs or dataset candidates and returns at most 100 pairs. No font-wide kerning table is copied. A page is live evidence, not an atomic font snapshot.
