"""Read-only path diagnostics and qualified repair using existing outline helpers."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter

from ..outline import path_hash
from ..path_doctor import validate_options, seam_pattern, qualify
from . import stored_layers
from . import path_attributes


def path_state(path):
    from .outline import _value, _node
    nodes = list(path.nodes)
    if len(nodes) > 4096: raise ValueError('path exceeds the 4,096-node limit')
    return {'closed': bool(_value(path, 'closed', False)), 'locked': bool(_value(path, 'locked', False)) or bool(path_attributes.attributes(path).get('locked', False)),
            'attributeState': path_attributes.state(path),
            'nodes': [{**_node(n), 'attributeState': path_attributes.state(n)} for n in nodes]}


def referenced(layer, path):
    from .outline import _hinted
    # Conservative: moving any segment/node addresses on a hinted path is held.
    return _hinted(layer, list(path.nodes))


def validate_segments(state):
    from .outline import _segment
    nodes = state['nodes']
    if any(not math.isfinite(n[k]) for n in nodes for k in ('x', 'y')):
        raise ValueError('non-finite authored coordinates')
    on = [i for i,n in enumerate(nodes) if n['type'] != 'offcurve']
    if len(on) < 2: raise ValueError('path needs at least two on-curve nodes')
    if not state['closed'] and (not on or on[0] != 0 or on[-1] != len(nodes)-1):
        raise ValueError('open path must start and end on-curve')
    for end in on if state['closed'] else on[1:]: _segment(state, end)


def profile_problems(state):
    problems = []
    def number(value):
        if isinstance(value, dict) and set(value) == {'float'}:
            return float.fromhex(value['float'])
        return float(value)
    for index, node in enumerate(state['nodes']):
        points = node.get('attributeState', {}).get('attributes', {}).get('penPoints', [])
        previous = -1.0
        for point in points:
            try:
                fields = point['penPoint']
                t = number(fields['t'])
                if not math.isfinite(t) or not 0 <= t <= 1 or t < previous:
                    problems.append({'node': index, 'reason': 'profile t outside [0,1] or unordered'})
                previous = t
                for key in ('width', 'height'):
                    value = number(fields[key])
                    if not math.isfinite(value) or value <= 0:
                        problems.append({'node': index, 'reason': 'non-positive/non-finite profile '+key})
                if node['type'] == 'offcurve':
                    problems.append({'node': index, 'reason': 'profile stored on unsupported off-curve address'})
            except (KeyError, TypeError, ValueError):
                problems.append({'node': index, 'reason': 'unsupported profile representation'})
    return problems


def normalize(layer, path, expected):
    """Retain seam XY/start index; transplant incoming segment, never refit curves."""
    from .outline import _set_nodes, _validate
    before = path_state(path)
    if path_hash(before) != expected: raise ValueError('seam state guard is stale (geometry, attributes or profiles changed)')
    reasons = qualify(before, referenced=referenced(layer, path))
    from .outline import _value
    if bool(_value(layer, 'locked', False)): reasons.append('layer is locked')
    parent = _value(layer, 'parent', None)
    if parent is not None and bool(_value(parent, 'locked', False)): reasons.append('glyph is locked')
    reasons.extend(p['reason'] for p in profile_problems(before))
    if reasons: raise ValueError('seam repair held: ' + '; '.join(sorted(set(reasons))))
    validate_segments(before)  # Known zero line is valid; no general validator weakened.
    nodes = list(path.nodes); first, last = nodes[0], nodes[-1]
    path_attributes.transfer_profiles(first, last)
    first.type = last.type
    _set_nodes(path, nodes[:-1])
    _validate(path)
    after = path_state(path)
    wanted = {**before, 'nodes': [dict(n) for n in before['nodes'][:-1]]}
    wanted['nodes'][0] = {**wanted['nodes'][0], 'type': before['nodes'][-1]['type'],
        'attributeState': {**before['nodes'][0]['attributeState'], 'attributes':
            {**before['nodes'][0]['attributeState']['attributes'], **before['nodes'][-1]['attributeState']['attributes']}}}
    # Empty incoming profile storage must remain absent, not an invented default.
    if 'penPoints' not in before['nodes'][-1]['attributeState']['attributes']:
        wanted['nodes'][0]['attributeState']['attributes'].pop('penPoints', None)
    if after != wanted:
        raise ValueError('seam repair changed an unapproved invariant')
    return {'nodeMap': {str(i): (0 if i == len(nodes)-1 else i) for i in range(len(nodes))},
            'incomingSegment': {'beforeEndNode': len(nodes)-1, 'afterEndNode': 0},
            'removedSegment': {'startNode': len(nodes)-1, 'endNode': 0, 'type': 'line', 'length': 0},
            'preserved': ['authored coordinates', 'real segments and handles', 'direction', 'seam XY',
                          'path order', 'smoothness', 'fill explicitness', 'profiles and inherited defaults']}


def inspect_path(state, *, document_id=None, glyph, layer, path, references=False):
    target = {'document': document_id, 'glyph': glyph, 'layer': layer, 'surface': 'foreground', 'path': path}
    issues = []
    def issue(code, classification, severity, evidence, confidence='definite', nodes=None, repair=None, held=None):
        address = {**target, 'nodes': nodes or []}
        stable = json.dumps([glyph, layer, path, code, nodes or []], separators=(',', ':'))
        issues.append({'issueId': 'pd1:' + hashlib.sha256(stable.encode()).hexdigest()[:24],
            'code': code, 'target': address, 'classification': classification, 'severity': severity,
            'confidence': confidence, 'evidence': evidence, 'stateHash': path_hash(state),
            'repair': repair, 'heldReasons': held or []})
    try: validate_segments(state)
    except (ValueError, RuntimeError) as exc:
        issue('malformed_segments', 'structural', 'error', str(exc))
        return issues
    nodes=state['nodes']; attrs=state.get('attributeState', {}).get('attributes', {})
    problems=profile_problems(state)
    if problems:
        issue('invalid_profiles', 'structural', 'error', problems, nodes=sorted({p['node'] for p in problems}))
    if seam_pattern(state):
        reasons=qualify(state, referenced=references) + sorted({p['reason'] for p in problems})
        issue('redundant_closed_seam', 'structural', 'warning',
            {'automaticClosingLineLength': 0, 'incomingType': nodes[-1]['type'],
             'seam': [nodes[0]['x'], nodes[0]['y']], 'causeOfEditingFailure': 'unproven',
             'seamProfiles':{'redundant':nodes[0].get('attributeState',{}).get('attributes',{}).get('penPoints',[]),
                             'incoming':nodes[-1].get('attributeState',{}).get('attributes',{}).get('penPoints',[])},
             'nodeMap':{str(i):(0 if i==len(nodes)-1 else i) for i in range(len(nodes))},
             'proposedChange':'transplant incoming segment type and profiles to node 0; remove only automatic zero line',
             'preservedInvariants':['real segment coordinates/types/handles','direction','seam XY','stroke order',
                                    'profile fields and defaults','fill','smoothness','unrelated data']},
            nodes=[len(nodes)-1, 0], held=reasons,
            repair=None if reasons else {'op': 'normalize_closed_seam', 'path': path, 'stateHash': path_hash(state)})
    if state['closed'] and not seam_pattern(state) and nodes[0]['type'] != 'offcurve' and nodes[-1]['type'] != 'offcurve':
        distance=math.hypot(nodes[0]['x']-nodes[-1]['x'], nodes[0]['y']-nodes[-1]['y'])
        if 0 < distance <= .001:
            issue('near_closed_seam', 'suspicious', 'info',
                  {'endpointDistance':distance,'action':'inspect drawing intent; no automatic repair'},
                  confidence='suspicious', nodes=[len(nodes)-1,0])
    stroke = any(k in attrs for k in ('strokeWidth','strokeHeight')) or any(
        n.get('attributeState', {}).get('attributes', {}).get('penPoints') for n in nodes)
    if state['closed'] and stroke and 'fill' not in attrs:
        issue('closed_stroke_fill_unset', 'appearance', 'warning',
              {'fill': 'inherited/unset', 'action': 'inspect native appearance; set fill only under separate authorization'})
    if state['closed'] and all(not n.get('smooth') for n in nodes if n['type']!='offcurve'):
        issue('corner_connections', 'drawing_convention', 'info',
              'Corner flags allow independent handles. This is valid and does not authorize smoothing.')
    if not state['closed']:
        start=(nodes[0]['x'],nodes[0]['y'])
        repeats=[i for i,n in enumerate(nodes[1:],1) if n['type']!='offcurve' and (n['x'],n['y'])==start]
        if repeats:
            issue('open_return', 'drawing_convention', 'info', 'Intentional returns/retracing are valid; no repair proposed.', nodes=[0]+repeats)
        if nodes[0].get('attributeState',{}).get('attributes',{}).get('penPoints'):
            issue('inactive_open_start_profiles', 'drawing_convention', 'info',
                  'Stored controls have no incoming segment; preserve authored data.', nodes=[0])
    return issues


def prepare_iter(font, request, *, document_id=None):
    options=validate_options(request['options']); names=options['glyphs']; layers=options['layers']
    totals=Counter({'glyphs':0,'layers':0,'paths':0,'directStrokePaths':0,'closedStrokePaths':0,'componentReferences':0,'unsupportedPaths':0}); issues=[]; digests=[]
    if names=='all': selected=font.glyphs
    else:
        selected=[]
        for name in names:
            g=font.glyphs[name]
            if g is None: raise ValueError('diagnostic glyph unavailable: '+name)
            selected.append(g)
            yield
    master_ids={str(m.id) for m in font.masters}
    for glyph in selected:
        totals['glyphs']+=1
        found=set()
        for layer in stored_layers(glyph):
            identity=str(layer.layerId)
            if (layers=='all_masters' and identity not in master_ids) or (layers!='all_masters' and identity not in layers):
                yield; continue
            found.add(identity); totals['layers']+=1
            totals['componentReferences']+=len(list(layer.components or []))
            for index,path in enumerate(layer.paths):
                totals['paths']+=1
                try:
                    state=path_state(path)
                    digests.append([str(glyph.name),identity,index,path_hash(state)])
                    attrs=state['attributeState']['attributes']
                    stroke=any(k in attrs for k in ('strokeWidth','strokeHeight'))
                    totals['directStrokePaths']+=int(stroke)
                    totals['closedStrokePaths']+=int(stroke and state['closed'])
                    findings = inspect_path(state, document_id=document_id, glyph=str(glyph.name),
                        layer=identity,path=index,references=referenced(layer,path))
                    from .outline import _value
                    held = []
                    if identity not in master_ids:
                        held.append('repair is qualified only for foreground ordinary-master layers')
                    if bool(_value(glyph, 'locked', False)) or bool(_value(layer, 'locked', False)):
                        held.append('owning glyph or layer is locked')
                    for finding in findings:
                        if finding.get('repair') and held:
                            finding['proposedRepair'] = finding.pop('repair')
                            finding['repair'] = None
                            finding['heldReasons'].extend(held)
                    issues.extend(findings)
                except (ValueError, TypeError, RuntimeError) as exc:
                    totals['unsupportedPaths']+=1
                    issues.append({'code':'unsupported_path','target':{'document':document_id,'glyph':str(glyph.name),
                        'layer':identity,'surface':'foreground','path':index},'severity':'warning','confidence':'definite',
                        'classification':'unsupported','repair':None,'heldReasons':[str(exc)],'evidence':str(exc),
                        'issueId':'pd1:'+hashlib.sha256(json.dumps([str(glyph.name),identity,index,'unsupported_path']).encode()).hexdigest()[:24]})
                yield
            yield
        if (master_ids if layers=='all_masters' else set(layers))-found:
            raise ValueError('requested stored layers are missing for '+str(glyph.name))
        yield
    counts=Counter(i['code'] for i in issues)
    return [], {'claim':'Read-only live Path Doctor structural evidence; no repair, cleanup or save.',
        'scope':{'surface':'foreground','layers':layers,'glyphs':names,'backgrounds':False,
                 'historicalLayers':False,'componentsExpanded':False},
        'coverage':{**dict(totals),'complete':not totals['unsupportedPaths'],
                    'consistency':'sliced live scan; caller must guard generation; not an atomic native snapshot'},
        'issueCounts':dict(sorted(counts.items())), 'issues':issues,
        'scanHash':'sha256:'+hashlib.sha256(json.dumps(digests,separators=(',',':')).encode()).hexdigest(),
        'limitations':['No native editing-failure causality claim.','No expanded component or historical/background audit.']}
