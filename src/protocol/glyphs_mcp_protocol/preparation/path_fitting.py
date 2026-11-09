"""Coordinated polygon reconstruction on detached interpolation families."""
from ..path_fitting import validate_options
from ..polygon_fitting import fit_family_iter
from ..outline import path_hash, outline_state_hash, validate_operation
from .outline import _glyph, _copy, _compare, _shape_state, _apply, _value
from .path_doctor import path_state, referenced
from .path_cleanup import groups, protected, stroked, layer_context, validate_bounded
from .path_cleanup_samples import make_validator


def prepare_iter(font, request, *, sample_validator=None):
    options = validate_options(request['options'])
    if sample_validator is None: sample_validator = make_validator()
    changes, rows, held = [], [], []
    examined = 0
    for target in options['targets']:
        glyph = _glyph(font,target['glyph']); name = str(glyph.name)
        try:
            if _value(glyph,'locked',False): raise ValueError('glyph is locked')
            branches = groups(font,glyph)
        except (ValueError,RuntimeError,TypeError) as exc:
            held.append({'glyph':name,'reason':str(exc)});yield;continue
        for branch,layers in branches.items():
            examined += len(layers)
            try:
                originals = [_copy(l) for l in layers]; trials = [_copy(l) for l in layers]
                operations = [[] for l in layers]; details = [[] for l in layers]
                for selected in target['paths']:
                    index = selected['path']; states = []
                    for live,trial in zip(layers,trials):
                        if index >= len(trial.paths): raise ValueError('selected path is unavailable')
                        state = path_state(trial.paths[index])
                        if (_value(live,'locked',False) or protected(state) or stroked(state)
                                or referenced(live,live.paths[index])):
                            raise ValueError('selected polygon is locked, hinted, stroked or carries authored references')
                        states.append(state)
                    plans = yield from fit_family_iter(states,keep_nodes=selected['keepNodes'],
                        corner_nodes=selected['cornerNodes'],corner_angle=options['cornerAngle'],
                        max_deviation=options['maxDeviation'])
                    for i,(trial,state,plan) in enumerate(zip(trials,states,plans)):
                        op = validate_operation({'op':'fit_polygon','path':index,'stateHash':path_hash(state),
                            'segments':plan['segments'],'cornerNodes':plan['cornerNodes'],
                            'maxDeviation':options['maxDeviation']})
                        context = layer_context(trial); others = [path_state(p) for p in trial.paths]
                        _apply(trial,op)
                        if (layer_context(trial) != context or len(trial.paths) != len(others)
                                or any(path_state(p) != old for j,(p,old) in enumerate(zip(trial.paths,others)) if j != index)):
                            raise ValueError('fitting changed unrelated layer data')
                        operations[i].append(op)
                        details[i].append({'path':index,**{k:v for k,v in plan.items() if k != 'segments'}})
                        yield
                if len({_compare(l) for l in trials}) != 1:
                    raise ValueError('fitting changed interpolation correspondence')
                measurements = [validate_bounded([path_state(p) for p in original.paths],
                    [path_state(p) for p in trial.paths],options['maxDeviation'])
                    for original,trial in zip(originals,trials)]
                samples = sample_validator(font,glyph,layers,trials,options)
                branch_changes,branch_rows=[],[]
                for live,original,trial,ops,detail,evidence in zip(layers,originals,trials,operations,details,measurements):
                    before = sum(len(p.nodes) for p in original.paths)
                    after = sum(len(p.nodes) for p in trial.paths)
                    branch_changes.append({'kind':'outline','glyph':name,'layer':str(live.layerId),
                        'beforeHash':outline_state_hash(_shape_state(original)),
                        'afterHash':outline_state_hash(_shape_state(trial)),'operations':ops})
                    branch_rows.append({'glyph':name,'layer':str(live.layerId),'status':'changed',
                        'beforeNodes':before,'afterNodes':after,'removedNodes':before-after,
                        'paths':detail,'measurements':{**evidence,'intermediateSamples':samples}})
                changes.extend(branch_changes);rows.extend(branch_rows)
            except (ValueError,RuntimeError,TypeError) as exc:
                held.append({'glyph':name,'branch':branch,'reason':str(exc)})
            yield
        yield
    return changes, {'claim':'Explicit polygon reconstruction prepared on detached layers; no live edits or save.',
        'kind':'path_fitting','settings':options,'layers':rows,'held':held,'heldCount':len(held),
        'changedLayers':len(changes),'unchangedLayers':examined-len(changes),
        'removedNodes':sum(r['removedNodes'] for r in rows),
        'beforeNodes':sum(r['beforeNodes'] for r in rows),'afterNodes':sum(r['afterNodes'] for r in rows),
        'maximumBoundaryError':max((bound for row in rows for bound in
            [row['measurements']['boundaryErrorUpperBound']]+[s.get('boundaryErrorUpperBound',0.)
                for s in row['measurements']['intermediateSamples']]),default=0.),
        'warnings':[f'{len(held)} polygon families held'] if held else [],
        'validation':'Continuous source-span bounds; cumulative native layer boundary/topology checks; native interpolation samples. Sampled coverage is not a continuous designspace guarantee.',
        'comparison':'View → Changes Against Reference; Edit → Comparison Reference → Last Saved. Saving advances the reference.'}
