# Research and tool assessment

Reviewed 2026-11-04. These sources guide a first pass; old UI examples and forum
opinions are not current native API qualification.

- [Glyphs: Making small caps](https://glyphsapp.com/learn/making-small-caps): starting
  workflow for naming, scaling, weight, spacing, metrics, accents and feature checks.
  It explicitly retains manual fine tuning after automatic construction.
- [TypeDrawers: Small Capitals](https://typedrawers.com/discussion/4703/small-capitals):
  practitioners discuss height and lowercase weight relationships, then identify
  heavy diagonals, excessive width and awkward terminals. Treat judgments as design
  evidence rather than fixed numerical laws.
- [TypeDrawers: usefulness of tools](https://typedrawers.com/discussion/2713/usefulness-of-plugins-extensions-other-tools):
  practical reports of RMX reducing construction work; no measured speed claim.
- [Glyphs Forum: single-master RMX](https://forum.glyphsapp.com/t/rmx-scaler-without-multiple-masters/16094):
  distinguishes mathematical scaling/offset starting points from multi-weight
  derivation. [Irregular lettering](https://forum.glyphsapp.com/t/small-caps-w-hand-drawn-font/9322)
  may need redrawing from scratch.
- [Glyphs Handbook](https://handbook.glyphsapp.com/en/single-page/): Offset Curve's
  independent offsets and Keep Compatible trade accuracy for unchanged structure;
  current small/petite naming and automatic-feature conventions.
- [RMX handbook](https://remix-tools.com/glyphsapp/manual) and
  [changelog](https://remix-tools.com/glyphsapp/changelog): optional multi-weight
  scaling. The changelog records Glyphs 4 support and later fixes, as well as
  changed handling of anchors, groups, keys and components. Verify the actual
  installed version. Do not infer scripting support from menu availability.
- [Microsoft OpenType features](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt):
  small/petite substitutions and language-sensitive case mapping.
- [Glyphs Turkish I](https://glyphsapp.com/learn/localize-your-font-turkish),
  [Spanish punctuation](https://glyphsapp.com/learn/localize-your-font-spanish-inverted-question-and-exclamation-marks),
  [Catalan middle dot](https://glyphsapp.com/learn/localize-your-font-catalan-punt-volat):
  concrete language/feature checks.

## Optional tools and learned models

Native transforms, qualified layer-local offset, existing inspectors and explicit
outline edits are the v1 baseline. No new palette, trained model or paid dependency
is required. A palette could later expose measured candidates and a review queue
if native proof tabs plus conversation prove insufficient.

Beztrace matching can fit approved imagery to an existing contour structure within
its actual supported scope and point policy. It does not choose small-cap design
or guarantee correct semantic correspondence across a whole family.

[DeepVecFont-v2](https://arxiv.org/abs/2303.14585), with
[official code/checkpoints](https://github.com/yizhiwang96/DeepVecFont-v2), and
[VecGlypher](https://xk-huang.github.io/VecGlypher/), with a
[published checkpoint](https://huggingface.co/VecGlypher/VecGlypher-27b-it), demonstrate
vector glyph synthesis. Their cited evaluations do not establish uppercase-to-
small/petite derivation with preserved Glyphs components, anchors, spacing and
multi-master topology. That is an evidence gap, not proof the methods cannot help.

A later experiment should compare constrained corrections to existing outlines
against full glyph generation and the native baseline. Use paired, permitted
uppercase/small-cap/petite-cap examples and split held-out evaluation by family.
Measure designer correction time, acceptance, semantic node correspondence,
structural failures, geometry, reading proofs and sampled interpolation. Image
similarity alone does not determine typographic quality. Review actual model,
checkpoint and dataset terms separately; code licensing does not license all
training fonts. No model downloads, paid inference, training or proprietary-font
sharing is authorized just by invoking this skill.
