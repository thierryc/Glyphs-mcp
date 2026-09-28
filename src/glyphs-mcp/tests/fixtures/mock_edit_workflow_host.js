'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
function host({initialize=true, tools=true, reject=false, deferWrites=false, deferReads=false}={}) {
  let serverState = null;
  let document;
  class Element {
    constructor(tag='div') {this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.style={setProperty(k,v){this[k]=v;}};this.hidden=false;this.textContent='';this.value='';}
    append(...items){this.children.push(...items);}
    replaceChildren(...items){this.children=items;}
    addEventListener(k,f){this.listeners[k]=f;}
    setAttribute(k,v){this[k]=v;}
    getBoundingClientRect(){return {height:350};}
    querySelectorAll(selector){return this.children.flatMap(e => [e,...(e.querySelectorAll?.('*')||[])]).filter(e => selector==='*'||selector==='button'&&e.tag==='button'||selector==='input:checked'&&e.tag==='input'&&e.checked);}
    querySelector(){return this.submit ||= new Element('button');}
    focus(){document.activeElement=this;}
  }
  const elements=new Map(), calls=[], timers=new Map(), listeners={};let sequence=0, now=0;
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  document={documentElement:new Element(),hidden:false,getElementById:get,createElement:t=>new Element(t),createTextNode:t=>({textContent:t}),querySelector:()=>get('main'),querySelectorAll:s=>[...elements.values()].flatMap(e=>e.querySelectorAll(s)),addEventListener:(k,f)=>listeners[k]=f};
  const parent={postMessage(message){calls.push(message);if(message.method==='ui/initialize'&&initialize)queueMicrotask(()=>dispatch({id:message.id,result:{hostCapabilities:tools?{serverTools:{}}:{},hostContext:{theme:'dark'}}}));if(message.method==='tools/call') { const read=message.params.name==='get_edit_workflow'; if (read ? deferReads : deferWrites) return; queueMicrotask(()=>dispatch(reject?{id:message.id,error:{message:'Host tool permission unavailable'}}:{id:message.id,result:{structuredContent:read?serverState:(serverState=state(4,'applied',[]))}})); }}};
  const dispatch=data=>listeners.message({source:parent,origin:'https://host.test',data:{jsonrpc:'2.0',...data}});
  vm.runInNewContext(code,{window:{parent,addEventListener:(k,f)=>listeners[k]=f},document,Map,Promise,console,performance:{now:()=>now},setTimeout:(callback,delay)=>{timers.set(++sequence,{callback,delay,at:now+delay});return sequence;},clearTimeout:id=>timers.delete(id)});
  const advance=ms=>{now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.callback();}};
  return {get,document,calls,timers,dispatch,listeners,advance,setState:s=>serverState=s,click:name=>get('actions').children.find(b=>b.dataset.action===name).listeners.click()};
}
const action=(name,label,destination=false)=>({action:name,label,token:'token-'+name,requiresDestination:destination});
const state=(revision=1,value='waiting_save',actions=[action('save_continue','Save and continue'),action('save_as_continue','Save As…',true)])=>({ok:true,data:{id:'edit_example',revision,state:value,document:{id:'doc_A',familyName:'Two fonts with this name',path:'/fonts/version A.glyphs'},scope:{kind:'width_delta',glyphs:['A'],masters:['M1']},actions,message:value==='applied'?'Changes applied. Save your font to keep them.\nSaving includes the whole font.':'Preparing changes…',text:'Conversation alternative',modelContext:JSON.stringify({workflow_id:'edit_example',expected_revision:revision,state:value,actions:actions.map(a=>({action:a.action,label:a.label,action_token:a.token,requiresDestination:a.requiresDestination}))}),poll:value==='preparing'}});
const deliver=(h,s,{server=s}={})=>{h.setState(server);h.dispatch({method:'ui/notifications/tool-result',params:{structuredContent:s}});};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
module.exports = {host, action, state, deliver, tick};
if (require.main === module) (async()=>{
 const h=host();await tick();deliver(h,state());await tick();
 assert(h.calls.some(m=>m.method==='ui/notifications/initialized'));
 assert.equal(h.document.documentElement.style.colorScheme,'dark');
 assert.equal(h.get('path').textContent,'/fonts/version A.glyphs');
 h.click('save_as_continue');assert.equal(h.get('save-form').hidden,false);assert.equal(h.get('destination').textContent,'/fonts/version A-copy.glyphs');
 h.get('folder').value='/new';h.get('filename').value='Family.glyphs';h.get('save-form').listeners.submit({preventDefault(){}});await tick();
 const write=h.calls.find(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow');assert.equal(write.params.name,'respond_edit_workflow');assert.equal(write.params.arguments.destination,'/new/Family.glyphs');assert.equal(write.params.arguments.expected_revision,1);assert.equal(h.get('status').textContent,'Changes applied. Save your font to keep them.');
 deliver(h,state(2),{server:state(4,'applied',[])});await tick();assert.equal(h.get('status').textContent,'Changes applied. Save your font to keep them.','older card results must not roll back revision');
 assert(h.calls.some(m=>m.method==='ui/update-model-context'));
 const disabled=host({tools:false});await tick();deliver(disabled,state());assert(disabled.get('actions').children.every(b=>b.disabled));assert(disabled.get('fallback').textContent.includes('Save and continue'));
 const warnings=host();await tick();const incomplete=state(1,'needs_review',[action('apply','Apply changes')]);incomplete.data.reviewInConversation=true;deliver(warnings,incomplete);await tick();assert(warnings.get('actions').children[0].disabled);assert(warnings.get('warnings').children[0].textContent.includes('complete report'));
 const failed=host({initialize:false});for(const timer of [...failed.timers.values()])timer.callback();await tick();deliver(failed,state());assert(failed.get('actions').children.every(b=>b.disabled));assert(failed.get('fallback').textContent.includes('conversation'));
 const errors=host({reject:true});await tick();deliver(errors,state());await tick();errors.click('save_continue');assert(errors.get('error').textContent.includes('permission'));assert.equal(errors.calls.filter(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow').length,0,'failed reconciliation must disable actions');
 const active=host();await tick();deliver(active,state(1,'preparing',[action('cancel','Cancel preparation')]));await tick();assert([...active.timers.values()].some(t=>t.delay===1500));active.document.hidden=true;active.document.getElementById('status');active.dispatch({method:'ui/resource-teardown',id:999});assert(![...active.timers.values()].some(t=>t.delay===1500));assert(active.calls.some(m=>m.id===999&&m.result));assert(!active.calls.some(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow'),'closing must not cancel');
 const review=host();await tick();const proposal=state(1,'needs_review',[action('apply','Apply changes')]);proposal.data.job={report:{requiredOverwrites:[{master:'M1',key:'x',before:1,after:2}]}};deliver(review,proposal);await tick();review.click('apply');assert(!review.calls.some(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow'));assert(review.get('error').textContent.includes('Approve every'));review.get('approvals').querySelectorAll('*').find(e=>e.tag==='input').checked=true;review.click('apply');await tick();assert.equal(review.calls.find(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow').params.arguments.approved_overwrites.length,1);
 // A remounted waiting snapshot must be read before any choice is enabled.
 const stale=host({deferReads:true});await tick();deliver(stale,state());
 assert(stale.get('actions').children.every(b=>b.disabled));stale.click('save_continue');
 assert(!stale.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 const read=stale.calls.find(m=>m.params?.name==='get_edit_workflow');
 stale.dispatch({id:read.id,result:{structuredContent:state(8,'saved',[])}});await tick();
 assert(stale.get('actions').hidden);assert.equal(JSON.parse(stale.calls.filter(m=>m.method==='ui/update-model-context').at(-1).params.content[1].text).state,'saved');
 // Host approval can take more than 15 seconds without losing an in-flight action.
 const slow=host({deferWrites:true});await tick();deliver(slow,state());await tick();slow.click('save_continue');
 const request=slow.calls.find(m=>m.params?.name==='respond_edit_workflow');
 assert([...slow.timers.values()].some(t=>t.delay===120000));
 assert(slow.get('actions').children.every(b=>b.disabled));
 slow.dispatch({id:request.id,result:{structuredContent:state(4,'applied',[action('save_result','Save font')])}});await tick();
 assert.equal(slow.get('error').textContent,'');
 const context=JSON.parse(slow.calls.filter(m=>m.method==='ui/update-model-context').at(-1).params.content[1].text);
 assert.equal(context.expected_revision,4);assert.equal(context.actions[0].action_token,'token-save_result');
 // A lost mutation response is reconciled by a read, never a second mutation.
 const lost=host({deferWrites:true});await tick();deliver(lost,state());await tick();lost.click('save_continue');
 lost.setState(state(7,'applied',[action('save_result','Save font')]));
 for(const t of [...lost.timers.values()]) if(t.delay===120000)t.callback();await tick();
 assert.equal(lost.get('error').textContent,'');
 assert.equal(lost.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1);
 assert.equal(lost.get('actions').children[0].textContent,'Save font');
 // Reopening a retained view also reads waiting states, not only poll=true ones.
 lost.document.hidden=true;lost.listeners.visibilitychange();lost.setState(state(9,'saved',[]));
 lost.document.hidden=false;lost.listeners.visibilitychange();await tick();assert(lost.get('actions').hidden);
 // Async completion publishes fresh action tokens to the conversation as well.
 const polling=host();await tick();deliver(polling,state(1,'preparing',[action('cancel','Cancel')]));await tick();
 polling.setState(state(5,'applied',[action('save_result','Save font')]));
 for(const t of [...polling.timers.values()])if(t.delay===1500)t.callback();await tick();
 assert.equal(JSON.parse(polling.calls.filter(m=>m.method==='ui/update-model-context').at(-1).params.content[1].text).expected_revision,5);
 const scriptsHost=host();await tick();
 const scriptReviewState=state(20,'waiting_run',[action('run_script','Run script'),action('cancel','Cancel')]);
 scriptReviewState.data.scope={kind:'python_script'};scriptReviewState.data.requestFingerprint='script-one';
 scriptReviewState.data.scriptReview={source:'print("<script>alert(1)</script>")',params:{value:'<b>literal</b>'},targets:[],entrypoint:'script'};
 scriptReviewState.data.message='Script ready.';
 deliver(scriptsHost,scriptReviewState);await tick();
 assert.equal(scriptsHost.get('script-source').textContent,scriptReviewState.data.scriptReview.source);
 assert.equal(scriptsHost.get('script-review').hidden,false);
 assert(!scriptsHost.calls.some(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow'),'script scriptReviewState must never auto-run');
 await scriptsHost.click('run_script');await tick();
 assert(scriptsHost.calls.some(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow'));
 const fast=host();await tick();
 const fastState=state(21,'waiting_run',[action('save_run_script','Save and run'),action('cancel','Cancel')]);
 fastState.data.scope={kind:'python_script'};fastState.data.requestFingerprint='script-two';
 fastState.data.scriptReview={...scriptReviewState.data.scriptReview};
 fastState.data.message='Save and run saves the whole font first.\nWhole-document restoration replaces all later edits.';
 deliver(fast,fastState);await tick();
 assert(fast.get('script-mode').textContent.includes('saved-version'));
 assert(!fast.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 assert(fast.get('fallback').textContent.includes('Save and run'));
 fast.click('save_run_script');await tick();
 assert.equal(fast.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1);
 deliver(fast,state(25,'applied',[action('restore_saved_script','Restore saved version')]));await tick();
 assert(fast.get('fallback').textContent.includes('Restore saved version'));
 const textOnlyFast=host({tools:false});await tick();deliver(textOnlyFast,fastState);
 assert(textOnlyFast.get('fallback').textContent.includes('Save and run'));
 assert(textOnlyFast.get('actions').children.every(b=>b.disabled));
 // Script details are lazy, safe text, and cached only for the matching request.
 const lazy=host();await tick();
 const compact=state(30,'waiting_run',[action('run_script','Run script')]);
 compact.data.scope={kind:'python_script'};compact.data.requestFingerprint='lazy-one';
 deliver(lazy,compact);await tick();
 assert.equal(lazy.get('script-source').textContent,'');
 assert(!lazy.calls.some(m=>m.params?.arguments?.include_review));
 const expanded=JSON.parse(JSON.stringify(compact));expanded.data.scriptReview={source:'<script>literal</script>',params:{},targets:[],entrypoint:'script'};
 lazy.setState(expanded);lazy.get('script-review').open=true;lazy.get('script-review').listeners.toggle();await tick();
 assert(lazy.calls.some(m=>m.params?.arguments?.include_review===true));
 assert.equal(lazy.get('script-source').textContent,'<script>literal</script>');
 deliver(lazy,compact);await tick();assert.equal(lazy.get('script-source').textContent,'<script>literal</script>');
 const changed=JSON.parse(JSON.stringify(compact));changed.data.revision=31;changed.data.requestFingerprint='lazy-two';
 deliver(lazy,changed);await tick();assert.equal(lazy.get('script-source').textContent,'');
 assert.equal(lazy.get('script-review').open,false);
 const whole=state(32,'applying',[]);whole.data.scope={kind:'python_script'};whole.data.entrypoint='script';
 whole.data.job={bridgeOperation:{totalChanges:100,completedChanges:0}};
 deliver(lazy,whole);await tick();assert(lazy.get('progress').hidden);
 const finished=state(33,'applied',[]);finished.data.scope={kind:'python_script'};finished.data.job={changeCount:null};
 deliver(lazy,finished);await tick();assert.equal(lazy.get('proposal').children.length,0);
 // Loaded output and tracebacks survive compact reads for this job only.
 const evidence=host();await tick();
 const full=state(40,'applying',[]);full.data.scope={kind:'python_script'};full.data.requestFingerprint='evidence';full.data.jobId='job_1';
 full.data.scriptReview={source:'print("<b>output</b>")',params:{},targets:[],entrypoint:'script'};
 full.data.job={bridgeOperation:{scriptResult:{output:'VISIBLE_OUTPUT',executed:true}}};
 full.data.error={code:'probe',message:'error',details:{traceback:'<script>TRACEBACK</script>'}};
 deliver(evidence,full);await tick();
 const small=JSON.parse(JSON.stringify(full));small.data.revision=41;delete small.data.scriptReview;
 delete small.data.job.bridgeOperation.scriptResult.output;delete small.data.error.details;
 deliver(evidence,small);await tick();
 assert(evidence.get('script-output').textContent.includes('VISIBLE_OUTPUT'));
 assert(evidence.get('script-output').textContent.includes('<script>TRACEBACK</script>'));
 const empty=JSON.parse(JSON.stringify(small));empty.data.revision=42;
 empty.data.job.bridgeOperation.scriptResult.output='';empty.data.error=null;
 deliver(evidence,empty);await tick();
 assert(!evidence.get('script-output').textContent.includes('VISIBLE_OUTPUT'));
 assert(!evidence.get('script-output').textContent.includes('TRACEBACK'));
 const newJob=JSON.parse(JSON.stringify(small));newJob.data.revision=43;newJob.data.jobId='job_2';
 deliver(evidence,newJob);await tick();assert.equal(evidence.get('script-source').textContent,'');assert.equal(evidence.get('script-output').textContent,'');
 // A completed compact result triggers one full read when details are open.
 const completion=host();await tick();deliver(completion,full);await tick();completion.get('script-review').open=true;
 const complete=JSON.parse(JSON.stringify(small));complete.data.revision=44;complete.data.state='applied';
 deliver(completion,complete);await tick();
 const finalFull=JSON.parse(JSON.stringify(complete));finalFull.data.scriptReview=full.data.scriptReview;
 finalFull.data.job.bridgeOperation.scriptResult.output='FINAL_OUTPUT';completion.setState(finalFull);
 for(const [id,t] of [...completion.timers])if(t.delay===0){completion.timers.delete(id);t.callback();}
 await tick();assert(completion.get('script-output').textContent.includes('FINAL_OUTPUT'));
 assert.equal(completion.calls.filter(m=>m.params?.arguments?.include_review).length,1);
 deliver(completion,complete);await tick();assert(![...completion.timers.values()].some(t=>t.delay===0));
 assert(completion.get('script-output').textContent.includes('FINAL_OUTPUT'));
 // A visible, reconciled successful result keeps once after 30 seconds.
 const autoState=()=>{
   const s=state(50,'applied',[action('finish_script','Keep changes without saving'),action('wait_for_answer','Wait for my answer')]);
   Object.assign(s.data,{scope:{kind:'python_script'},jobId:'job_auto',requestFingerprint:'auto',autoKeep:{enabled:true,delaySeconds:30,action:'finish_script'}});
   return s;
 };
 const auto=host();await tick();deliver(auto,autoState());await tick();
 assert(!auto.get('auto-keep').hidden);assert.equal(auto.get('auto-keep-progress').value,0);
 auto.advance(29000);await tick();assert(!auto.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 assert.equal(auto.get('auto-keep-progress').value,29);
 auto.advance(1000);await tick();
 const autoWrites=auto.calls.filter(m=>m.params?.name==='respond_edit_workflow');
 assert.equal(autoWrites.length,1);assert.equal(autoWrites[0].params.arguments.automatic,true);
 assert.equal(autoWrites[0].params.arguments.action_token,'token-finish_script');
 auto.advance(60000);await tick();assert.equal(auto.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1);
 // A text reply or another card can opt out while this card counts down.
 const opted=host();await tick();deliver(opted,autoState());await tick();
 const off=autoState();off.data.revision++;off.data.autoKeep.enabled=false;off.data.autoKeep.action=null;
 opted.setState(off);opted.advance(30000);await tick();assert(!opted.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 assert(opted.get('auto-keep').hidden);
 const waitButton=host({deferWrites:true});await tick();deliver(waitButton,autoState());await tick();
 waitButton.click('wait_for_answer');waitButton.advance(30000);await tick();
 const waitWrites=waitButton.calls.filter(m=>m.params?.name==='respond_edit_workflow');
 assert.equal(waitWrites.length,1);assert.equal(waitWrites[0].params.arguments.action_token,'token-wait_for_answer');
 assert(!waitWrites[0].params.arguments.automatic);
 waitButton.dispatch({id:waitWrites[0].id,result:{structuredContent:off}});await tick();waitButton.advance(60000);await tick();
 assert.equal(waitButton.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1);
 // A rejected Wait stays locally paused even if the server still says enabled.
 const rejectedWait=host({deferWrites:true});await tick();deliver(rejectedWait,autoState());await tick();
 rejectedWait.click('wait_for_answer');
 const rejectedWrite=rejectedWait.calls.find(m=>m.params?.name==='respond_edit_workflow');
 rejectedWait.dispatch({id:rejectedWrite.id,error:{message:'Permission rejected'}});await tick();
 deliver(rejectedWait,autoState());await tick();rejectedWait.advance(60000);await tick();
 assert(rejectedWait.get('auto-keep').hidden);
 assert.equal(rejectedWait.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1);
 const typed=host();await tick();const typedState=autoState();
 typedState.data.scope.kind='width_delta';typedState.data.autoKeep.action='finish_edit';
 typedState.data.actions[0]=action('finish_edit','Keep changes without saving');
 deliver(typed,typedState);await tick();typed.advance(30000);await tick();
 const typedWrites=typed.calls.filter(m=>m.params?.name==='respond_edit_workflow');
 assert.equal(typedWrites.length,1);assert.equal(typedWrites[0].params.arguments.action_token,'token-finish_edit');
 assert.equal(typedWrites[0].params.arguments.automatic,true);
 // Hidden cards, open details, and stale requests cannot consume elapsed time.
 const hidden=host();await tick();deliver(hidden,autoState());await tick();hidden.advance(20000);await tick();
 hidden.document.hidden=true;hidden.listeners.visibilitychange();hidden.advance(60000);await tick();
 assert(!hidden.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 hidden.document.hidden=false;hidden.listeners.visibilitychange();await tick();assert.equal(hidden.get('auto-keep-progress').value,0);
 hidden.advance(10000);await tick();hidden.get('script-review').open=true;hidden.get('script-review').listeners.toggle();await tick();
 hidden.advance(60000);await tick();assert(!hidden.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 const staleAuto=host();await tick();deliver(staleAuto,autoState());await tick();
 const newer=autoState();newer.data.revision++;newer.data.requestFingerprint='changed';staleAuto.setState(newer);
 staleAuto.advance(30000);await tick();assert(!staleAuto.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 assert.equal(staleAuto.get('auto-keep-progress').value,0);
 // Generic typed Details also pause; a failed automatic dispatch is never replayed.
 const details=host();await tick();deliver(details,typedState);await tick();
 details.get('result-details').open=true;details.get('result-details').listeners.toggle();
 details.advance(60000);await tick();assert(!details.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 const unknownKeep=host({deferWrites:true});await tick();deliver(unknownKeep,typedState);await tick();
 unknownKeep.advance(30000);await tick();
 const uncertainWrite=unknownKeep.calls.find(m=>m.params?.name==='respond_edit_workflow');
 unknownKeep.dispatch({id:uncertainWrite.id,error:{message:'Lost response'}});await tick();
 const nextRevision=JSON.parse(JSON.stringify(typedState));nextRevision.data.revision++;
 deliver(unknownKeep,nextRevision);await tick();unknownKeep.advance(60000);await tick();
 assert.equal(unknownKeep.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1);
 // No countdown for legacy snapshots, failure, cancellation, preparation or text-only hosts.
 for(const status of ['failed','cancelled','waiting_run','preparing','interrupted']) {
   const h=host();await tick();const s=autoState();s.data.state=status;deliver(h,s);await tick();h.advance(60000);await tick();
   assert(!h.calls.some(m=>m.params?.name==='respond_edit_workflow'));assert(h.get('auto-keep').hidden);
 }
 for(const config of [{tools:false},{deferReads:true}]) {
   const h=host(config);await tick();deliver(h,autoState());await tick();h.advance(60000);await tick();
   assert(!h.calls.some(m=>m.params?.name==='respond_edit_workflow'));assert(h.get('auto-keep').hidden);
 }
 const legacy=host();await tick();const oldAuto=autoState();delete oldAuto.data.autoKeep;deliver(legacy,oldAuto);await tick();legacy.advance(60000);await tick();
 assert(!legacy.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 const closed=host();await tick();deliver(closed,autoState());await tick();closed.dispatch({method:'ui/resource-teardown',id:999});closed.advance(60000);await tick();
 assert(!closed.calls.some(m=>m.params?.name==='respond_edit_workflow'));
 const lostAuto=host({deferWrites:true});await tick();deliver(lostAuto,autoState());await tick();lostAuto.advance(30000);await tick();
 lostAuto.advance(120000);await tick();lostAuto.advance(60000);await tick();
 assert.equal(lostAuto.calls.filter(m=>m.params?.name==='respond_edit_workflow').length,1,'never replay a timed-out automatic action');
 if (process.argv[3]) {
   const wording=host(); await tick();
   for (const payload of JSON.parse(fs.readFileSync(process.argv[3],'utf8'))) {
     deliver(wording,payload);await tick();
     const data=payload.data, [heading,...guidance]=data.message.split('\n');
     assert.equal(wording.get('status').textContent,heading);
     assert.equal(wording.get('message').textContent,guidance.join('\n'));
     assert.equal(wording.get('message').hidden,!guidance.length);
     assert.equal(wording.get('progress').hidden,true,'completed progress must be hidden');
     assert.equal(wording.get('fallback').hidden,!data.actions.length);
     if (!data.actions.length) assert.equal(wording.get('fallback').textContent,'');
     if (data.state==='saved') {
       assert.equal(heading,'Font saved.');
       assert.equal(wording.get('message').textContent,'');
     }
     if (data.state==='failed') {
       assert(!heading.includes('discarded'));
       assert(wording.get('details').textContent.includes('A later edit prevents undo.'));
     }
   }
 }
 console.log('MCP Apps host: actions, fallback, revision ordering, no retry, consent, and server/card wording passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
