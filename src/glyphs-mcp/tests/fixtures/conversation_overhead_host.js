'use strict';
const assert = require('assert/strict');
const {host, action, state, deliver, tick} = require('./mock_edit_workflow_host');
const reads = h => h.calls.filter(m => m.params?.name === 'get_edit_workflow');
const writes = h => h.calls.filter(m => m.params?.name === 'respond_edit_workflow');
function script(revision=1) {
  const s = state(revision, 'waiting_run', [action('run_script', 'Run script')]);
  Object.assign(s.data, {jobId:'job_A', requestFingerprint:'request_A', scope:{kind:'python_script'},
    message:'Script ready.', poll:false});
  return s;
}
function full(s) {
  const f = structuredClone(s);
  f.data.scriptReview = {source:'# <script>text, not markup</script>\n'.repeat(700), params:{dx:0.25}, targets:[], entrypoint:'script'};
  f.data.job = {bridgeOperation:{scriptResult:{output:'<b>literal output</b>'}}};
  return f;
}
function toggle(h, open) {h.get('result-details').open=open;h.get('result-details').listeners.toggle();}
const cases = {
  async duplicate() {
    const h=host();await tick();const s=script();deliver(h,s);await tick();
    for(let i=0;i<10;i++){deliver(h,structuredClone(s));await tick();}
    const report={reads:reads(h).length,writes:writes(h).length};
    if(process.argv[4] !== '--measure') assert.equal(report.reads,1,'matching verified host notifications need no new read');
    assert.equal(report.writes,0);
    return report;
  },
  async reopen() {
    const h=host();await tick();const s=script();deliver(h,s);await tick();
    const expanded=full(s);h.setState(expanded);
    for(let i=0;i<5;i++){toggle(h,true);await tick();toggle(h,false);await tick();}
    const fullReads=reads(h).filter(m=>m.params.arguments.include_review).length;
    const report={reads:reads(h).length,fullReads,writes:writes(h).length,
      responseDataBytes:Buffer.byteLength(JSON.stringify(s)) + fullReads*Buffer.byteLength(JSON.stringify(expanded))};
    assert.equal(h.get('script-source').textContent,expanded.data.scriptReview.source);
    if(process.argv[4] !== '--measure') assert.equal(fullReads,1,'reuse details for the same verified request');
    assert.equal(report.writes,0);
    return report;
  },
  async document() {
    const h=host();await tick();const s=full(script());deliver(h,s);await tick();
    const next=script(2);next.data.document.id='doc_B';next.data.document.path='/fonts/B.glyphs';
    deliver(h,next);await tick();
    assert.equal(h.get('script-source').textContent,'','a new document binding clears old source and output');
    assert.equal(h.get('script-output').textContent,'');
    return {passed:true};
  },
  async late_read() {
    const h=host({deferReads:true});await tick();const first=script();deliver(h,first);
    const old=reads(h)[0];const second=script(2);
    second.data.id='edit_B';second.data.jobId='job_B';second.data.requestFingerprint='request_B';
    second.data.document={id:'doc_B',path:'/fonts/B.glyphs'};
    deliver(h,second);
    h.dispatch({id:old.id,result:{structuredContent:full(first)}});await tick();
    assert.equal(reads(h).at(-1).params.arguments.workflow_id,'edit_B','late A response must not redirect reconciliation to A');
    assert.equal(h.get('path').textContent,'B.glyphs');
    assert.equal(h.get('script-source').textContent,'');
    const latest=reads(h).at(-1);h.dispatch({id:latest.id,result:{structuredContent:second}});await tick();
    assert.equal(writes(h).length,0);
    return {passed:true};
  },
  async visibility() {
    const h=host();await tick();const s=full(script());deliver(h,s);await tick();
    const before=reads(h).length;
    h.document.hidden=true;h.listeners.visibilitychange();
    h.document.hidden=false;h.listeners.visibilitychange();await tick();
    assert.equal(reads(h).length,before+1,'returning to a card still reconciles fresh server state');
    assert.equal(writes(h).length,0);
    return {passed:true};
  },
  async late_write() {
    const h=host({deferWrites:true});await tick();const first=script();deliver(h,first);await tick();
    h.click('run_script');const old=writes(h)[0];
    const second=script(2);second.data.id='edit_B';second.data.jobId='job_B';
    second.data.requestFingerprint='request_B';second.data.document={id:'doc_B',path:'/fonts/B.glyphs'};
    deliver(h,second);
    h.dispatch({id:old.id,result:{structuredContent:full(first)}});await tick();
    assert.equal(h.get('path').textContent,'B.glyphs');
    assert.equal(h.get('script-source').textContent,'');
    assert.equal(reads(h).at(-1).params.arguments.workflow_id,'edit_B');
    assert.equal(writes(h).length,1,'a late mutation response must not replay any action');
    return {passed:true};
  },
  async typed_summary() {
    const h=host();await tick();const s=state(1,'applied',[]);
    s.data.summary='Move the requested node by +0.25, -0.5';s.data.job={changeCount:1};
    deliver(h,s);await tick();
    assert(h.get('scope').textContent.includes(s.data.summary));
    assert(!h.get('scope').textContent.includes('pending'),'typed summaries must not invent unresolved script surfaces');
    return {passed:true};
  },
};
(async()=>{const name=process.argv[3];assert(cases[name],name);console.log(JSON.stringify({case:name,...await cases[name]()}));})().catch(e=>{console.error(e);process.exit(1);});
