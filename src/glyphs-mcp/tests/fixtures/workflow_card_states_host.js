'use strict';
const assert = require('assert/strict');
const {host, action, state, deliver, tick} = require('./mock_edit_workflow_host');
const reads = h => h.calls.filter(m => m.params?.name === 'get_edit_workflow');
const writes = h => h.calls.filter(m => m.params?.name === 'respond_edit_workflow');
const payload = (revision=1, status='ready') => {
  const s = state(revision, status, [action('apply', 'Apply changes'), action('discard', 'Cancel preview')]);
  s.data.actions[0].presentation='primary';s.data.actions[1].presentation='secondary';
  s.data.mode='preview';s.data.poll=false;s.data.uiRefreshIntervalMs=5000;
  return s;
};
const failed = code => ({structuredContent:{ok:false,error:{code,message:'Choice rejected'}}});
const cases = {
  async stale() {
    const h=host({deferWrites:true,deferReads:true});await tick();deliver(h,payload());
    h.dispatch({id:reads(h)[0].id,result:{structuredContent:payload()}});await tick();
    h.click('apply');const write=writes(h)[0];
    h.dispatch({id:write.id,result:failed('stale_workflow_action')});await tick();
    assert(h.get('actions').hidden);assert(h.get('save-form').hidden);
    const done=payload(2,'cancelled');done.data.actions=[];done.data.uiRefreshIntervalMs=0;done.data.message='Request cancelled.';
    h.dispatch({id:reads(h).at(-1).id,result:{structuredContent:done}});await tick();
    assert.equal(h.get('status').textContent,'Request cancelled.');assert.equal(h.get('error').textContent,'');
    assert(h.get('actions').hidden);assert(h.get('check-status').hidden);assert.equal(writes(h).length,1);
    assert(![...h.timers.values()].some(t=>t.delay===5000));
  },
  async refresh_failure() {
    const h=host({deferWrites:true,deferReads:true});await tick();deliver(h,state());
    h.dispatch({id:reads(h)[0].id,result:{structuredContent:state()}});await tick();
    h.click('save_as_continue');assert(!h.get('save-form').hidden);
    h.get('save-form').listeners.submit({preventDefault(){}});
    h.dispatch({id:writes(h)[0].id,result:failed('stale_workflow_action')});await tick();
    h.dispatch({id:reads(h).at(-1).id,error:{message:'Connection lost'}});await tick();
    assert(h.get('actions').hidden);assert(h.get('more-options').hidden);assert(h.get('save-form').hidden);
    assert(!h.get('check-status').hidden);assert(!h.get('check-status').disabled);
    h.get('check-status').listeners.click();assert.equal(writes(h).length,1);
    h.dispatch({id:reads(h).at(-1).id,result:{structuredContent:payload(8)}});await tick();
    assert(!h.get('actions').hidden);assert(h.get('check-status').hidden);assert.equal(h.get('error').textContent,'');
  },
  async validation() {
    const h=host({deferWrites:true});await tick();deliver(h,state());await tick();
    h.click('save_continue');h.dispatch({id:writes(h)[0].id,result:failed('destination_exists')});await tick();
    assert(h.get('error').textContent.includes('Choice rejected'));assert(!h.get('actions').hidden);
    h.advance(5000);await tick();assert(h.get('error').textContent.includes('Choice rejected'));
    const fresh=state(3,'saved',[]);fresh.data.message='Font saved.';h.setState(fresh);h.advance(5000);await tick();
    assert.equal(h.get('error').textContent,'');assert(h.get('actions').hidden);
  },
  async external_completion() {
    const h=host();await tick();deliver(h,payload());await tick();
    assert([...h.timers.values()].some(t=>t.delay===5000));
    const done=payload(3,'saved');done.data.actions=[];done.data.uiRefreshIntervalMs=0;done.data.message='Font saved.';
    h.setState(done);h.advance(5000);await tick();assert(h.get('actions').hidden);
    assert.equal(h.get('status').textContent,'Font saved.');assert.equal(writes(h).length,0);
    assert(![...h.timers.values()].some(t=>t.delay===5000));
  },
  async menu() {
    const h=host({deferWrites:true});await tick();const s=state(1,'applied',[
      {...action('finish_edit','Keep without saving'),presentation:'primary'},
      {...action('discard','Undo these changes'),presentation:'secondary'},
      {...action('save_result','Save font'),presentation:'menu'},
      {...action('save_result_as','Save As…',true),presentation:'menu'},
      {...action('wait_for_answer','Wait for my answer'),presentation:'auto_keep'},
    ]);deliver(h,s);await tick();
    assert.deepEqual(h.get('actions').children.map(b=>b.dataset.action),['finish_edit','discard']);
    assert.equal(h.get('more-actions').children.length,2);assert(!h.get('more-options').hidden);
    assert.equal(h.get('auto-keep-actions').children[0].textContent,'Turn off automatic Keep');
    h.click('save_result_as');assert(!h.get('save-form').hidden);
    h.get('save-form').listeners.submit({preventDefault(){}});assert.equal(writes(h)[0].params.arguments.destination,'/fonts/version A-copy.glyphs');
    assert(h.get('fallback').hidden);
    const textOnly=host({tools:false});await tick();deliver(textOnly,s);
    assert(!textOnly.get('fallback').hidden);assert(textOnly.get('fallback').textContent.includes('Save As'));
  },
  async countdown_refresh() {
    const h=host({deferWrites:true});await tick();const s=state(1,'applied',[
      {...action('finish_script','Keep without saving'),presentation:'primary'},
      {...action('wait_for_answer','Wait for my answer'),presentation:'auto_keep'},
    ]);
    Object.assign(s.data,{jobId:'job_a',requestFingerprint:'request_a',scope:{kind:'python_script'},
      autoKeep:{enabled:true,action:'finish_script',delaySeconds:30},uiRefreshIntervalMs:5000});
    deliver(h,s);await tick();assert.equal(h.get('auto-keep-actions').children[0].textContent,'Pause countdown');
    for(let seconds=5;seconds<30;seconds+=5) {h.advance(5000);await tick();assert.equal(writes(h).length,0);assert.equal(h.get('auto-keep-progress').value,seconds);}
    h.advance(5000);await tick();assert.equal(writes(h).length,1);assert(writes(h)[0].params.arguments.automatic);
  },
  async wrong_response() {
    const h=host({deferReads:true});await tick();deliver(h,payload());
    const other=payload();other.data.id='edit_other';
    h.dispatch({id:reads(h)[0].id,result:{structuredContent:other}});await tick();
    assert(h.get('actions').hidden);assert(!h.get('check-status').hidden);
    assert(h.get('error').textContent.includes('did not match'));assert.equal(writes(h).length,0);
    h.get('check-status').listeners.click();assert.equal(reads(h).at(-1).params.arguments.workflow_id,'edit_example');
  },
  async inspection_during_refresh() {
    const h=host({deferReads:true});await tick();const s=state(1,'applied',[
      {...action('finish_edit','Keep without saving'),presentation:'primary'},
      {...action('wait_for_answer','Wait for my answer'),presentation:'auto_keep'},
    ]);
    Object.assign(s.data,{jobId:'job_a',requestFingerprint:'request_a',
      autoKeep:{enabled:true,action:'finish_edit',delaySeconds:30},uiRefreshIntervalMs:5000});
    deliver(h,s);h.dispatch({id:reads(h)[0].id,result:{structuredContent:s}});await tick();
    h.advance(20000);await tick();
    const background=reads(h).at(-1);
    assert(!h.get('actions').hidden,'a routine pending read preserves the card layout');
    assert(h.get('actions').children.every(b=>b.disabled));
    h.get('result-details').open=true;h.get('result-details').listeners.toggle();
    h.get('result-details').open=false;h.get('result-details').listeners.toggle();
    h.dispatch({id:background.id,result:{structuredContent:s}});await tick();
    assert.equal(h.get('auto-keep-progress').value,0,'inspection during an in-flight read resets elapsed time');
    h.advance(10000);await tick();assert.equal(writes(h).length,0);
  },
  async compact() {
    const h=host();await tick();const s=payload();s.data.summary='Unicode 🖋 description '.repeat(20);
    s.data.scope={kind:'python_script'};s.data.job={report:{targetCount:11,skippedCount:0}};
    deliver(h,s);await tick();assert.equal(Array.from(h.get('scope').textContent).length,140);
    assert.equal(h.get('full-summary').textContent,s.data.summary);assert.equal(h.get('targets').textContent,'11 targets');
    assert.equal(h.get('path').textContent,'version A.glyphs');assert.equal(h.get('full-path').textContent,'/fonts/version A.glyphs');
    assert(h.get('result-details').listeners.toggle);assert(!h.get('script-review').listeners.toggle);
  },
  async focus() {
    const h=host();await tick();deliver(h,payload());await tick();h.get('actions').children[0].focus();
    const done=payload(4,'cancelled');done.data.actions=[];done.data.uiRefreshIntervalMs=0;
    h.setState(done);h.advance(5000);await tick();assert.equal(h.document.activeElement,h.get('status'));
  },
};
(async()=>{const name=process.argv[3];assert(cases[name],name);await cases[name]();console.log(`Workflow card: ${name} passed`);})().catch(error=>{console.error(error);process.exitCode=1;});
