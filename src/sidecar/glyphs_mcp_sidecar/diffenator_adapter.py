"""Pinned Diffenator CLI execution without Ninja's shell command strings.

Executed by the optional private Python runtime, never the sidecar interpreter.
"""
import json
from itertools import product
from pathlib import Path
import re
import sys


def select_pairs(old_fonts, new_fonts, options):
    from diffenator2.font import get_font_styles, Style
    method = options['styles']
    pattern = options.get('filterStyles')
    if method == 'instances':
        old = get_font_styles(old_fonts, method, pattern)
        new = get_font_styles(new_fonts, method, pattern)
        before = {style.name: style for style in old}
        after = {style.name: style for style in new}
        if len(before) != len(old) or len(after) != len(new):
            raise ValueError('Duplicate style names: compare one family at a time.')
        if set(before) != set(after):
            raise ValueError('Style sets differ: baseline-only=' + repr(sorted(set(before) - set(after)))
                             + ', candidate-only=' + repr(sorted(set(after) - set(before))))
        return [(before[name], after[name]) for name in sorted(before)]
    if len(old_fonts) != 1 or len(new_fonts) != 1 or not all(font.is_variable() for font in old_fonts + new_fonts):
        raise ValueError('Masters and cross_product require one variable TTF on each side.')
    old_font, new_font = old_fonts[0], new_fonts[0]
    old_axes = {axis.axisTag: axis for axis in old_font.ttFont['fvar'].axes}
    new_axes = new_font.ttFont['fvar'].axes
    if set(old_axes) != {axis.axisTag for axis in new_axes}:
        raise ValueError('Variable axis tags differ; compare named instances instead.')
    if method == 'cross_product':
        values = [tuple(dict.fromkeys((axis.minValue, axis.defaultValue, axis.maxValue))) for axis in new_axes]
        count = 1
        for axis_values in values:
            count *= len(axis_values)
        if count > 256:
            raise ValueError('Comparison exceeds 256 style locations; compare named instances or masters.')
        styles = [Style(new_font, dict(zip((axis.axisTag for axis in new_axes), location))) for location in product(*values)]
    else:
        styles = new_font.masters()
    pairs = []
    for style in styles:
        if pattern and not re.match(pattern, style.name):
            continue
        if any(tag not in old_axes or not old_axes[tag].minValue <= value <= old_axes[tag].maxValue
               for tag, value in style.coords.items()):
            raise ValueError('A candidate location is outside the baseline axis range; compare named instances instead.')
        pairs.append((Style(old_font, style.coords, style.name), style))
    return pairs


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    # Vendor Unicode data instead of using Youseedee's writable home cache or
    # automatic network refresh. Its files are covered by the runtime inventory.
    import youseedee
    unicode_data = Path(request["unicodeData"])
    if not (unicode_data / "UnicodeData.txt").is_file():
        raise ValueError("The optional runtime lacks its qualified Unicode data")
    youseedee.ucd_dir = lambda: unicode_data
    youseedee.ensure_files = lambda: None
    from diffenator2 import html, THRESHOLD
    from diffenator2._diffenator import DiffFonts
    from diffenator2.font import DFont
    from diffenator2.matcher import FontMatcher
    from diffenator2.utils import resource_filename
    from diffenator2.renderer import FONT_SIZE
    options = request['options']
    output = Path(request['output'])
    output.mkdir(mode=0o700)
    pairs = select_pairs([DFont(p, suffix='old') for p in request['baseline']],
                         [DFont(p, suffix='new') for p in request['candidate']], options)
    if not pairs:
        raise ValueError('No complete matching style set. Select compatible fonts or narrow the style filter.')
    if len(pairs) > 256:
        raise ValueError('Comparison exceeds 256 style locations; narrow the scope.')
    # Restrict font-derived filenames without changing the compared name table.
    package = html._package
    def contained_package(templates, dst, **kwargs):
        for key in ('font_styles_old', 'font_styles_new', 'font_styles'):
            for style in kwargs.get(key, []):
                style.stylename = re.sub(r'[^\w .-]', '_', style.stylename)
        return package(templates, dst, **kwargs)
    html._package = contained_package
    template = resource_filename('diffenator2', 'templates/diffenator.html')
    matched = []
    for index, (old, new) in enumerate(pairs):
        matcher = FontMatcher([old.font], [new.font])
        matcher.old_styles, matcher.new_styles = [old], [new]
        for style in (old, new):
            if style.font.is_variable():
                style.set_font_variations()
        matcher.upms()
        diff = DiffFonts(matcher, threshold=THRESHOLD, font_size=FONT_SIZE)
        diff.diff_all()
        if options.get('userWordlist'):
            diff.diff_strings(options['userWordlist'])
        diff.to_html(template, str(output / f'style-{index:03d}'))
        glyphs = diff.glyph_diff['glyphs']
        matched.append(dict(baselineStyle=old.name, candidateStyle=new.name,
                            baselineCoordinates=old.coords, candidateCoordinates=new.coords,
                            changedTables=sorted(diff.tables.diff),
                            addedGlyphs=len(glyphs.new), removedGlyphs=len(glyphs.missing),
                            modifiedGlyphs=len(glyphs.modified),
                            changedWords=sum(len(words) for words in diff.glyph_diff['words'].values())))
    (output / 'scope.json').write_text(json.dumps({'matchedStyles': matched}, indent=2))
    html.build_index_page(str(output))


if __name__ == '__main__':
    main()
