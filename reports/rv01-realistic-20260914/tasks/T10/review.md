# OpenType review of the pinned Roboto Slab source

The 17 feature blocks are active. Sixteen are automatic; `lnum` is manual. Their names, source code and flags agree exactly between native Glyphs and glyphsLib. One stored `Uppercase` class and a `Languagesystems` prefix support generated contextual code. The bounded native compiler accepted the source with the isolated ss20 addition.

Seven exported behavior checks pass: liga off gives f+i, liga on gives fi; frac maps 1/4 to onequarter; ss01 maps g to g.ss01; smcp maps abc to small caps; lnum maps 012 to .lf figures; Romanian locl maps Scedilla to Scommaaccent. This verifies representative Latin behavior, not the complete multilingual repertoire, every lookup interaction or variable exports.

`ss20` duplicates the source’s existing `ss01` rule. It is appropriate only as an isolated feature-authoring control. Reuse ss01 in production. The g alternate has a different advance, which the exported proof retains; enabling it can legitimately change word spacing. The first malformed feature produces a useful native error naming ss20 and line 1. Treat `(False, error)` as failure: testing the tuple’s truthiness would be wrong.

The configured `$glyphs-mcp-opentype-features` skill calls retired tools and requests apiMajor=2. That route is blocked. The native control was explicitly authorized by this task; it is not proof that the seven-tool sidecar has feature editing or arbitrary Python tools. Do not import these retired instructions into the lean entry.
