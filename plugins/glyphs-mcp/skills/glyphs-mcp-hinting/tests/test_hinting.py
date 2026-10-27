import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
from source_hints import inventory_objects, classify, file_map, instance_record
from binary_hints import audit
from compare_fonts import compare, render, validate_location
from native_hints import hint_record


def font_fixture(path, wide=0, include_alt=True):
    names=['.notdef', 'space', 'a']+(['a.alt']if include_alt else [])
    fb = FontBuilder(1000, isTTF=True); fb.setupGlyphOrder(names)
    fb.setupCharacterMap({32:'space',97:'a'}); glyphs = {}
    for n in names:
        p = TTGlyphPen(None)
        if n != 'space':
            p.moveTo((-40,0));p.lineTo((-40,500));p.lineTo((400+wide,500));p.lineTo((400+wide,0));p.closePath()
        glyphs[n] = p.glyph()
    fb.setupGlyf(glyphs);fb.setupHorizontalMetrics({n:(600,-40)for n in glyphs})
    fb.setupHorizontalHeader(ascent=800,descent=-200)
    fb.setupNameTable({'familyName':'Hint Test','styleName':'Regular','uniqueFontIdentifier':'Hint Test Regular','fullName':'Hint Test Regular','psName':'HintTest-Regular'})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    fb.setupPost();fb.setupMaxp();fb.save(path)


class SourceInventory(unittest.TestCase):
    def test_scopes_and_helpers_are_not_production_hints(self):
        info={'fontMaster':[{'id':'m1','name':'Regular'}]}
        hints=[{'type':'Stem','place':[0,80]},{'type':'Corner','name':'_corner'},{'type':'FutureKind','place':[1,2]}]
        glyphs=[{'glyphname':'a','layers':[{'layerId':'m1','hints':hints,'background':{'hints':[{'type':'Stem'}]}},{'layerId':'backup','hints':[{'type':'TTStem'}]}]}]
        original=copy.deepcopy(glyphs);r=inventory_objects(info,glyphs)
        self.assertEqual(r['hintCount'],5);self.assertEqual(r['countsByScope']['master/foreground'],3)
        self.assertEqual(r['countsByScope']['master/foreground/background'],1)
        self.assertEqual(r['countsByClass'],{'postscript':2,'outline-helper':1,'unknown':1,'truetype':1})
        self.assertEqual(glyphs,original);self.assertEqual(r['hints'][2]['raw'],hints[2])

    def test_unencoded_hidden_component_scope_is_retained(self):
        r=inventory_objects({'fontMaster':[{'id':'m'}]},[{'glyphname':'_provider','export':0,'layers':[{'layerId':'m','hints':[{'type':'Stem'}]}]},{'glyphname':'aacute','layers':[{'layerId':'m','shapes':[{'ref':'_provider'}]}]}])
        self.assertEqual(r['componentProviders']['aacute'],['_provider'])
        self.assertFalse(r['hints'][0]['export']);self.assertEqual(r['glyphCount'],2)

    def test_file_binding_detects_any_hint_edit_but_ignores_ui(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d);(p/'a.glyph').write_text('hint1');(p/'UIState.plist').write_text('ui1');a=file_map(p)
            (p/'UIState.plist').write_text('ui2');self.assertEqual(a,file_map(p))
            (p/'a.glyph').write_text('hint2');self.assertNotEqual(a,file_map(p))

    def test_format4_instance_identity_and_override(self):
        r=instance_record({'id':'saved-id','properties':[{'key':'styleNames','values':[{'language':'dflt','value':'Regular'}]}],'customParameters':[{'name':'Future Hint Mode','value':1}]})
        self.assertEqual(r['name'],'Regular');self.assertEqual(r['id'],'saved-id')
        self.assertEqual(r['hintParameters'][0]['value'],1)

    def test_helper_native_flag_takes_precedence(self):
        class Hint:
            isCorner=True;isPostScript=True;isTrueType=False;type=16
        r=hint_record(Hint());self.assertEqual(r['class'],'outline-helper');self.assertIn('position',r['unavailable'])


class CompiledFonts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.base=self.root/'base.ttf';self.hinted=self.root/'hinted.ttf';font_fixture(self.base)
        f=TTFont(self.base);p=Program();p.fromAssembly(['SVTCA[0]']);f['glyf']['a'].program=p;f.save(self.hinted)
    def tearDown(self):self.tmp.cleanup()

    def test_tt_program_detected_without_geometry_drift(self):
        a=audit(self.base);b=audit(self.hinted)
        self.assertEqual(a['glyphsWithInstructions'],0);self.assertEqual(b['glyphsWithInstructions'],1)
        self.assertTrue(b['inputUnchanged']);self.assertTrue(compare(self.base,self.hinted)['hintOnlyChecksPass'])

    def test_real_outline_drift_rejected(self):
        p=self.root/'changed.ttf';font_fixture(p,wide=1);r=compare(self.base,p)
        self.assertFalse(r['hintOnlyChecksPass']);self.assertIn('a',r['locations'][0]['changedOutlines'])

    def test_units_per_em_drift_rejected(self):
        f=TTFont(self.hinted);f['head'].unitsPerEm=2000;p=self.root/'upm.ttf';f.save(p)
        r=compare(self.base,p);self.assertFalse(r['hintOnlyChecksPass']);self.assertIn('unitsPerEm',r['changedHeadFields'])

    def test_glyph_set_failure_still_writes_report(self):
        p=self.root/'order.ttf';font_fixture(p,include_alt=False)
        plan={'glyphs':['a'],'modes':[{'name':'base','file':str(self.base)},{'name':'changed','file':str(p)}]}
        out=self.root/'order-report'
        with self.assertRaises(ValueError):render(plan,out,Path('/unused'))
        r=json.loads((out/'comparison.json').read_text());self.assertFalse(r['preservation'][0]['hintOnlyChecksPass'])
        self.assertIn('error',r['preservation'][0])

    def test_cff_fontmatrix_drift_rejected(self):
        from fontTools.pens.t2CharStringPen import T2CharStringPen
        fb=FontBuilder(1000,isTTF=False);fb.setupGlyphOrder(['.notdef','a']);fb.setupCharacterMap({97:'a'})
        strings={}
        for name in ['.notdef','a']:
            pen=T2CharStringPen(600,None);pen.moveTo((0,0));pen.lineTo((0,500));pen.lineTo((400,500));pen.lineTo((400,0));pen.closePath();strings[name]=pen.getCharString()
        fb.setupHorizontalMetrics({n:(600,0)for n in strings});fb.setupHorizontalHeader(ascent=800,descent=-200)
        fb.setupNameTable({'familyName':'Matrix Test','styleName':'Regular','psName':'MatrixTest-Regular'})
        fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200);fb.setupPost()
        fb.setupCFF('MatrixTest-Regular',{'FullName':'Matrix Test Regular','FamilyName':'Matrix Test','Weight':'Regular'},strings,{})
        fb.setupMaxp();base=self.root/'matrix-base.otf';fb.save(base)
        f=TTFont(base);top=f['CFF '].cff.topDictIndex[0];top.FontMatrix=[v*2 for v in top.FontMatrix];other=self.root/'matrix-changed.otf';f.save(other)
        r=compare(base,other);self.assertTrue(r['outlineScaleChanged']);self.assertFalse(r['hintOnlyChecksPass'])

    def test_unknown_axis_and_out_of_range_not_silently_ignored(self):
        from types import SimpleNamespace
        f={'fvar':SimpleNamespace(axes=[SimpleNamespace(axisTag='wght',minValue=300,defaultValue=400,maxValue=700)])}
        validate_location(f,{'wght':400})
        with self.assertRaises(ValueError):validate_location(f,{'weight':400})
        with self.assertRaises(ValueError):validate_location(f,{'wght':900})

    def test_metric_drift_rejected(self):
        f=TTFont(self.hinted);f['hmtx']['a']=(601,-40);p=self.root/'metric.ttf';f.save(p)
        self.assertEqual(compare(self.base,p)['changedMetrics'],['a'])

    def test_cmap_drift_rejected(self):
        f=TTFont(self.hinted)
        for t in f['cmap'].tables:
            if t.isUnicode():t.cmap[98]='a'
        p=self.root/'cmap.ttf';f.save(p);self.assertIn('cmap',compare(self.base,p)['changedTables'])

    def test_failed_proof_records_drift_and_does_not_render(self):
        p=self.root/'changed.ttf';font_fixture(p,wide=1);out=self.root/'failure'
        plan={'glyphs':['a'],'modes':[{'name':'base','file':str(self.base)},{'name':'drift','file':str(p)}]}
        with self.assertRaises(ValueError):render(plan,out,Path('/does/not/need/a/label/font'))
        self.assertTrue((out/'comparison.json').is_file());self.assertFalse(list(out.glob('*.png')))

    def test_proof_unencoded_alias_and_negative_sidebearing(self):
        label=Path('/System/Library/Fonts/Supplemental/Arial.ttf')
        if not label.exists():self.skipTest('System label font unavailable')
        plan={'glyphs':['a.alt','a'],'sizes':[12,16],'modes':[{'name':'base','file':str(self.base)},{'name':'hinted','file':str(self.hinted)}]}
        a=self.base.read_bytes();b=self.hinted.read_bytes();r=render(plan,self.root/'proof',label)
        self.assertEqual(len(r['pixels']),4);self.assertTrue(r['inputFilesUnchanged'])
        self.assertEqual(a,self.base.read_bytes());self.assertEqual(b,self.hinted.read_bytes())
        self.assertTrue((self.root/'proof'/r['pages'][0]['file']).is_file())

    def test_missing_glyph_never_silently_skipped(self):
        plan={'glyphs':['missing'],'modes':[{'name':'base','file':str(self.base)},{'name':'hinted','file':str(self.hinted)}]}
        with self.assertRaisesRegex(ValueError,'Missing glyphs'):render(plan,self.root/'missing',Path('/unused'))

    def test_existing_directory_not_overwritten(self):
        out=self.root/'out';out.mkdir();(out/'keep').write_text('owner work')
        plan={'glyphs':['a'],'modes':[{'name':'base','file':str(self.base)},{'name':'hinted','file':str(self.hinted)}]}
        with self.assertRaises(FileExistsError):render(plan,out,Path('/unused'))
        self.assertEqual((out/'keep').read_text(),'owner work')

if __name__=='__main__':unittest.main()
