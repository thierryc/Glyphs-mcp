'use strict';
const assert=require('assert/strict');
const {host,state,deliver,tick}=require('./mock_edit_workflow_host.js');
(async()=>{
 const h=host();await tick();const v=state(1,'ready',[]);
 v.data.scope={kind:'kerning_edit',glyphs:[]};
 v.data.job={changeCount:2,sample:[
  {kind:'kerning',master:'M1',direction:'LTR',left:'A<b>',right:'@MMK_R_V',before:null,after:0},
  {kind:'kerning',master:'M2',direction:'vertical',left:'A',right:'V',before:-72.5,after:null}
 ]};
 deliver(h,v);await tick();
 const text=h.get('proposal').children.map(n=>n.textContent).join('\n');
 assert(text.includes('A<b> / @MMK_R_V · M1 · LTR: absent → 0'));
 assert(text.includes('A / V · M2 · vertical: -72.5 → remove'));
 assert(!h.get('proposal').children.some(n=>n.tag==='b'));
})().catch(error=>{console.error(error);process.exitCode=1;});
