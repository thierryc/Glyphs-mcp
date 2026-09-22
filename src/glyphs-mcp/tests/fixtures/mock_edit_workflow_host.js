'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
function host({initialize=true, tools=true, reject=false}={}) {
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
  const parent={postMessage(message){calls.push(message);if(message.method==='ui/initialize'&&initialize)queueMicrotask(()=>dispatch({id:message.id,result:{hostCapabilities:tools?{serverTools:{}}:{},hostContext:{theme:'dark'}}}));if(message.method==='tools/call')queueMicrotask(()=>dispatch(reject?{id:message.id,error:{message:'Host tool permission unavailable'}}:{id:message.id,result:{structuredContent:state(4,'applied',[])}}));}};
  const dispatch=data=>listeners.message({source:parent,origin:'https://host.test',data:{jsonrpc:'2.0',...data}});
  vm.runInNewContext(code,{window:{parent,addEventListener:(k,f)=>listeners[k]=f},document,Map,Promise,console,setTimeout:(callback,delay)=>{timers.set(++sequence,{callback,delay});return sequence;},clearTimeout:id=>timers.delete(id)});
  return {get,document,calls,timers,dispatch,click:name=>get('actions').children.find(b=>b.dataset.action===name).listeners.click()};
}
const action=(name,label,destination=false)=>({action:name,label,token:'token-'+name,requiresDestination:destination});
const state=(revision=1,value='waiting_save',actions=[action('save_continue','Save and continue'),action('save_as_continue','Save As…',true)])=>({ok:true,data:{id:'edit_example',revision,state:value,document:{id:'doc_A',familyName:'Two fonts with this name',path:'/fonts/version A.glyphs'},scope:{kind:'width_delta',glyphs:['A'],masters:['M1']},actions,message:value==='applied'?'Changes applied. Save your font to keep them.\nSaving includes the whole font.':'Preparing changes…',text:'Conversation alternative',poll:value==='preparing'}});
const deliver=(h,s)=>h.dispatch({method:'ui/notifications/tool-result',params:{structuredContent:s}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const h=host();await tick();deliver(h,state());
 assert(h.calls.some(m=>m.method==='ui/notifications/initialized'));
 assert.equal(h.document.documentElement.style.colorScheme,'dark');
 assert.equal(h.get('path').textContent,'/fonts/version A.glyphs');
 h.click('save_as_continue');assert.equal(h.get('save-form').hidden,false);assert.equal(h.get('destination').textContent,'/fonts/version A-copy.glyphs');
 h.get('folder').value='/new';h.get('filename').value='Family.glyphs';h.get('save-form').listeners.submit({preventDefault(){}});await tick();
 const write=h.calls.find(m=>m.method==='tools/call');assert.equal(write.params.name,'respond_edit_workflow');assert.equal(write.params.arguments.destination,'/new/Family.glyphs');assert.equal(write.params.arguments.expected_revision,1);assert.equal(h.get('status').textContent,'Changes applied. Save your font to keep them.');
 deliver(h,state(2));assert.equal(h.get('status').textContent,'Changes applied. Save your font to keep them.','older card results must not roll back revision');
 assert(h.calls.some(m=>m.method==='ui/update-model-context'));
 const disabled=host({tools:false});await tick();deliver(disabled,state());assert(disabled.get('actions').children.every(b=>b.disabled));assert(disabled.get('fallback').textContent.includes('Save and continue'));
 const warnings=host();await tick();const incomplete=state(1,'needs_review',[action('apply','Apply changes')]);incomplete.data.reviewInConversation=true;deliver(warnings,incomplete);assert(warnings.get('actions').children[0].disabled);assert(warnings.get('warnings').children[0].textContent.includes('complete report'));
 const failed=host({initialize:false});for(const timer of [...failed.timers.values()])timer.callback();await tick();deliver(failed,state());assert(failed.get('actions').children.every(b=>b.disabled));assert(failed.get('fallback').textContent.includes('conversation'));
 const errors=host({reject:true});await tick();deliver(errors,state());errors.click('save_continue');await tick();await tick();assert(errors.get('error').textContent.includes('permission'));assert.equal(errors.calls.filter(m=>m.method==='tools/call'&&m.params.name==='respond_edit_workflow').length,1,'must not replay on host failure');
 const active=host();await tick();deliver(active,state(1,'preparing',[action('cancel','Cancel preparation')]));assert([...active.timers.values()].some(t=>t.delay===1500));active.document.hidden=true;active.document.getElementById('status');active.dispatch({method:'ui/resource-teardown',id:999});assert(![...active.timers.values()].some(t=>t.delay===1500));assert(active.calls.some(m=>m.id===999&&m.result));assert(!active.calls.some(m=>m.method==='tools/call'),'closing must not cancel');
 const review=host();await tick();const proposal=state(1,'needs_review',[action('apply','Apply changes')]);proposal.data.job={report:{requiredOverwrites:[{master:'M1',key:'x',before:1,after:2}]}};deliver(review,proposal);review.click('apply');assert(!review.calls.some(m=>m.method==='tools/call'));assert(review.get('error').textContent.includes('Approve every'));review.get('approvals').querySelectorAll('*').find(e=>e.tag==='input').checked=true;review.click('apply');await tick();assert.equal(review.calls.find(m=>m.method==='tools/call').params.arguments.approved_overwrites.length,1);
 if (process.argv[3]) {
   const wording=host(); await tick();
   for (const payload of JSON.parse(fs.readFileSync(process.argv[3],'utf8'))) {
     deliver(wording,payload);
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
