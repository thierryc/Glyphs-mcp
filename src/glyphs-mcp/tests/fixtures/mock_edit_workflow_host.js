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
  const elements=new Map(), calls=[], timers=new Map(), listeners={};let sequence=0;
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  document={documentElement:new Element(),hidden:false,getElementById:get,createElement:t=>new Element(t),createTextNode:t=>({textContent:t}),querySelector:()=>get('main'),querySelectorAll:s=>[...elements.values()].flatMap(e=>e.querySelectorAll(s)),addEventListener:(k,f)=>listeners[k]=f};
  const parent={postMessage(message){calls.push(message);if(message.method==='ui/initialize'&&initialize)queueMicrotask(()=>dispatch({id:message.id,result:{hostCapabilities:tools?{serverTools:{}}:{},hostContext:{theme:'dark'}}}));if(message.method==='tools/call') { const read=message.params.name==='get_edit_workflow'; if (read ? deferReads : deferWrites) return; queueMicrotask(()=>dispatch(reject?{id:message.id,error:{message:'Host tool permission unavailable'}}:{id:message.id,result:{structuredContent:read?serverState:(serverState=state(4,'applied',[]))}})); }}};
  const dispatch=data=>listeners.message({source:parent,origin:'https://host.test',data:{jsonrpc:'2.0',...data}});
  vm.runInNewContext(code,{window:{parent,addEventListener:(k,f)=>listeners[k]=f},document,Map,Promise,console,setTimeout:(callback,delay)=>{timers.set(++sequence,{callback,delay});return sequence;},clearTimeout:id=>timers.delete(id)});
  return {get,document,calls,timers,dispatch,listeners,setState:s=>serverState=s,click:name=>get('actions').children.find(b=>b.dataset.action===name).listeners.click()};
}
const action=(name,label,destination=false)=>({action:name,label,token:'token-'+name,requiresDestination:destination});
const state=(revision=1,value='waiting_save',actions=[action('save_continue','Save and continue'),action('save_as_continue','Save As…',true)])=>({ok:true,data:{id:'edit_example',revision,state:value,document:{id:'doc_A',familyName:'Two fonts with this name',path:'/fonts/version A.glyphs'},scope:{kind:'width_delta',glyphs:['A'],masters:['M1']},actions,message:value==='applied'?'Changes applied. Save your font to keep them.\nSaving includes the whole font.':'Preparing changes…',text:'Conversation alternative',modelContext:JSON.stringify({workflow_id:'edit_example',expected_revision:revision,state:value,actions:actions.map(a=>({action:a.action,label:a.label,action_token:a.token,requiresDestination:a.requiresDestination}))}),poll:value==='preparing'}});
const deliver=(h,s,{server=s}={})=>{h.setState(server);h.dispatch({method:'ui/notifications/tool-result',params:{structuredContent:s}});};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
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
