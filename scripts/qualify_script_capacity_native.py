"""Native-only capacity regressions on disposable fonts; never installs anything."""
import argparse
import json
from pathlib import Path
import sys
import time
from native_script_harness import Harness
from glyphs_mcp_protocol import script_targets
from glyphs_mcp_protocol.preparation import stored_layers

parser = argparse.ArgumentParser()
parser.add_argument('--format', choices=['glyphs', 'glyphspackage'], required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args([a for a in sys.argv[1:] if a != '--'])
assert not args.output.exists()


def exercise(h):
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    def incomplete():
        from GlyphsApp import GSFont, GSGlyph, GSFontMaster
        font = GSFont(); font.masters.append(GSFontMaster())
        glyph = GSGlyph('missing'); font.glyphs.append(glyph)
        missing = str(font.masters[0].id)
        glyph.removeLayerForId_(missing)
        before = tuple((str(l.layerId), bool(script_targets.value(l, 'hasBackground'))) for l in stored_layers(glyph))
        try: script_targets.resolve(font, [dict(glyph='missing', layer=missing)])
        except ValueError as exc: assert 'layer is unavailable' in str(exc)
        else: raise AssertionError('missing stored layer was manufactured')
        after = tuple((str(l.layerId), bool(script_targets.value(l, 'hasBackground'))) for l in stored_layers(glyph))
        assert before == after
        # Create just this foreground deliberately, then check inspection creates no background.
        owner = glyph.layers[missing]
        assert not script_targets.value(owner, 'hasBackground')
        rows, skipped = script_targets.resolve(font, [dict(glyph='missing', layer=missing, surface='background')])
        assert not rows and skipped['count'] == 1 and not script_targets.value(owner, 'hasBackground')
        return True
    check('missing native master layer/background never created by resolution', h.main(incomplete))
    targets = dict(master=h.mid, glyphs='all', surface='background')
    original_y = h.main(lambda: h.doc.font.glyphs[0].layers[h.mid].background.paths[0].nodes[0].position.y)
    source = 'def run(layer, params, context):\n    node = layer.paths[0].nodes[0]\n    node.position = (node.position.x, node.position.y + .25)\n    if context["index"] == 17: raise RuntimeError("intentional partial failure")'
    value = h.wait(h.start(dict(source=source, targets=targets), 'partial'), 'waiting_run')
    check('4097 callbacks prepared without execution', h.main(lambda: h.doc.font.glyphs[0].layers[h.mid].background.paths[0].nodes[0].position.y) == original_y)
    value = h.wait(h.choose(value, 'run_script'), 'failed')
    evidence = value['job']['bridgeOperation']['scriptResult']
    check('failure stops subsequent callbacks', evidence['executedTargets'] == 17 and evidence['executed'])
    check('partial edits remain visible', h.main(lambda: h.doc.font.glyphs[17].layers[h.mid].background.paths[0].nodes[0].position.y) == original_y+.25)
    check('untouched later callback', h.main(lambda: h.doc.font.glyphs[18].layers[h.mid].background.paths[0].nodes[0].position.y) == original_y)
    check('failed script cannot auto Keep', value['autoKeep']['action'] is None)
    old_id = value['document']['id']
    value = h.choose(value, 'restore_saved_script')
    check('partial failure restored with fresh binding', value['state'] == 'discarded' and value['document']['id'] != old_id)
    check('all partial coordinates restored', h.main(lambda: all(g.layers[h.mid].background.paths[0].nodes[0].position.y == original_y for g in h.doc.font.glyphs)))
    source = 'import time\ndef run(layer, params, context):\n    node = layer.paths[0].nodes[0]\n    node.position = (node.position.x, node.position.y + .25)\n    time.sleep(.0005)'
    value = h.wait(h.start(dict(source=source, targets=targets), 'cancel'), 'waiting_run')
    value = h.choose(value, 'run_script')
    deadline = time.monotonic()+60
    while time.monotonic() < deadline:
        value = h.service.edit_workflows.get(value['id'])
        evidence = (value.get('job') or {}).get('bridgeOperation') or {}
        if (evidence.get('scriptResult') or {}).get('executedTargets', 0): break
        time.sleep(.005)
    else: raise AssertionError('no callback progress')
    value = h.wait(h.choose(value, 'cancel'), 'cancelled')
    evidence = value['job']['bridgeOperation']['scriptResult']
    check('cancellation stops remaining native callbacks', 0 < evidence['executedTargets'] < 4097)
    check('cancelled script cannot auto Keep', value['autoKeep']['action'] is None)
    value = h.choose(value, 'restore_saved_script')
    check('cancelled edits restore without replay', value['state'] == 'discarded' and
          h.main(lambda: all(g.layers[h.mid].background.paths[0].nodes[0].position.y == original_y for g in h.doc.font.glyphs)))
    return checks


out = Harness(count=4097, suffix=args.format, batch_fixture=True).run(exercise)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out), flush=True)
if not out.get('passed'): raise RuntimeError(out.get('error'))
