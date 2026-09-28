# Language-aware kerning proofing

Require `kerning.proof.v1` and use the existing read tool. No Save, job or script
is needed; dirty and never-saved fonts are supported.

```json
{"document_id":"doc_…","entities":[{"kind":"kerning_proof","master":"exact-master-id","direction":"LTR","languages":["en","fr"],"limit":100}],"fields":["pairs"]}
```

Use exactly one selector and `fields:["pairs"]`. Explicit master and direction
(`LTR`, `RTL`, `vertical`) remain mandatory. `languages` contains unique supported
tags; unsupported tags fail rather than silently broadening coverage. Limit is
1–100. Follow `nextCursor` unchanged until `complete:true`, including empty pages.
Changing scope or observed document state requires restarting without a cursor.

The first reads build a small volatile mapping for the dataset alphabet,
visiting at most 256 glyphs per call. It keeps at most 512 codepoint records,
not a font-wide glyph or kerning table. Only each glyph’s primary Unicode is
used. Missing or multiply assigned codepoints are skipped; secondary Unicode,
unencoded alternates, ligatures and shaping substitutions are not guessed.
The mapping is reused while document ID, generation, dirty state, count and
boundary evidence match. Another document or a bridge restart expires it.
These are guarded live reads, not an atomic font snapshot: silent changes not
reflected in native change signals may escape detection.

Candidate pages inspect at most 256 dataset pairs and return at most 100.
`scannedGlyphs`, `scannedCandidates`, `phase`, `returned`, `totalCandidates`,
per-page missing/ambiguous counts and at most ten skipped examples explain
progress. Deduplication spans requested languages. Ordering uses the earliest
upstream rank in any requested language, then the character pair.

Each item contains characters, exact mapped glyph names, matching language
tags and a two-character `proof` string. This is unshaped proof text, not a
language-aware layout engine. Coverage reports exact glyph/glyph,
glyph/group, group/glyph and group/group stored entries. Null is absence;
zero remains an explicit stored exception. Effective resolution delegates to
native Glyphs when available, with `native`, `none` or `unknown` status. Unknown
is not zero. Covered pairs remain candidates: coverage says nothing about
whether the spacing looks good.

Present these as **pairs to inspect**, without mandatory corrections or proposed
values. Discovery neither edits nor launches collision analysis. Exact assignments
use [typed kerning edits](kerning-edits.md); collision repair remains separate.

The bundled pair facts come from André Fuchs’ MIT-licensed
[kerning-pairs](https://github.com/andre-fuchs/kerning-pairs/tree/b7a0e29ed81a8edee7b4b6cb1935ebf7d29ca611)
at the pinned revision shown in each response. Language tags come from its
per-language aggregate files and documented table: `cs da de en es et fi fr hr
hu it lt lv nl no pl pt ro se sk sl sq sv tr`. Upstream labels `se` as Sami;
this is not a claim of exhaustive Sami or other language coverage. The source
focuses on Basic Latin through Latin Extended A and quotation marks. Numeric
scores are removed; no words, article text or font kerning values are bundled.
The package includes the complete MIT notice, input checksums and normalization
provenance. The repository’s `scripts/vendor_kerning_pairs.py --check` reproduces
the normalized payload. Historical v1 data remains unchanged.
