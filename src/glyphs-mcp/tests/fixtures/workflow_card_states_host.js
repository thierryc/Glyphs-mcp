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
const resultButtons = () => {
  const s = state(1,'applied',[
    {...action('finish_script','Keep'),presentation:'secondary',tooltip:'Keep current changes in Glyphs without saving. Close this task and end its recovery option.'},
    {...action('save_result','Save'),presentation:'primary',tooltip:'Save the whole font, including other unsaved edits. Close this task and end recovery after saving succeeds.'},
    {...action('restore_saved_script','Restore'),presentation:'secondary',tooltip:'Restore the whole font to its pre-script state. Remove later edits and clear Undo history. Does not save.'},
    {...action('wait_for_answer','Wait for my answer'),presentation:'auto_keep'},
  ]);
  Object.assign(s.data,{jobId:'job_a',requestFingerprint:'request_a',scope:{kind:'python_script'},
    savedVersion:{available:true,kind:'memory_snapshot'},
    job:{status:'applied',bridgeOperation:{scriptResult:{executed:true,executionSucceeded:true}}},
    autoKeep:{enabled:true,action:'finish_script',delaySeconds:30},uiRefreshIntervalMs:5000,
    actionSupportText:'Choosing Keep or Save closes this task and ends its temporary recovery option.'});
  return s;
};
const cases = {
  async activity_progress() {
    const h=host();await tick();
    const s=state(1,'applying',[]);
    Object.assign(s.data,{jobId:'job_a',entrypoint:'per_target',scope:{kind:'python_script'},
      progress:{workflowId:s.data.id,jobId:'job_a',state:'applying',status:'working',label:'Running script',
        completed:3,total:10,indeterminate:false,updatedAt:123}});
    deliver(h,s);await tick();
    assert.equal(h.get('progress').textContent,'3 / 10');
    assert.equal(h.get('progress').getAttribute('aria-label'),'3 / 10 callbacks completed');
    assert.equal(h.get('activity-progress').value,3);
    assert.equal(h.get('activity-progress').max,10);
    assert(!h.get('activity-progress').hidden);
    assert(h.get('activity-updated').textContent.startsWith('Updated '));
    const whole=JSON.parse(JSON.stringify(s));whole.data.revision=2;whole.data.entrypoint='script';
    Object.assign(whole.data.progress,{completed:null,total:null,indeterminate:true});
    deliver(h,whole);await tick();
    assert.equal(h.get('progress').textContent,'');
    assert.equal(h.get('activity-progress').getAttribute('value'),null);
    assert(!h.get('activity-progress').hidden);
    const finished=state(3,'applied',[]);finished.data.jobId='job_a';
    finished.data.progress={...s.data.progress,state:'applied',status:'finished',completed:10,indeterminate:false};
    deliver(h,finished);await tick();assert(h.get('activity-progress').hidden);
    const wrong=state(4,'applying',[]);wrong.data.progress={...s.data.progress,workflowId:'other_workflow'};
    deliver(h,wrong);await tick();assert(h.get('activity-progress').hidden);
    assert.equal(writes(h).length,0,'progress display never takes a workflow action');
  },
  async result_buttons() {
    const h=host({deferWrites:true});await tick();deliver(h,resultButtons());await tick();
    const buttons=h.get('actions').children;
    assert.deepEqual(buttons.map(b=>b.textContent),['Keep','Save','Restore']);
    assert.deepEqual(buttons.map(b=>b.className),['','primary','']);
    assert.equal(h.get('more-options').hidden,true);
    assert(buttons[0].children.includes(h.get('auto-keep-progress')));
    assert(!buttons[1].children.includes(h.get('auto-keep-progress')));
    assert.equal(buttons[2].children[0].tag,'svg');
    assert.equal(buttons[2].children[0]['aria-hidden'],'true');
    assert(h.get('restore-coverage').textContent.includes('clear Undo history'));
    assert.deepEqual(h.get('restore-coverage').children.filter(e=>e.tag==='strong').map(e=>e.textContent),['Restore']);
    assert(!h.get('restore-coverage').hidden);
    assert(!h.get('action-support').hidden);
    assert.equal(writes(h).length,0,'primary Save must never auto-dispatch');
    h.advance(30000);await tick();
    assert.equal(writes(h).length,1);
    assert.equal(writes(h)[0].params.arguments.action_token,'token-finish_script');
    assert.equal(writes(h)[0].params.arguments.automatic,true);
  },
  async result_descriptions() {
    const h=host();await tick();deliver(h,resultButtons());await tick();
    for(const button of h.get('actions').children) {
      const description=h.get('action-descriptions').children.find(t=>t.id===button['aria-describedby']);
      assert(description && description.tag==='span');
      assert.equal(button.title,'','result buttons have no native hover tooltip');
      assert(!button.listeners.mouseenter && !button.listeners.focus,'descriptions must not open hover or focus popovers');
      assert(description.textContent.includes(button.dataset.action==='save_result'?'whole font':button.dataset.action==='finish_script'?'without saving':'pre-script'));
    }
    assert.deepEqual(h.get('action-support').children.filter(e=>e.tag==='strong').map(e=>e.textContent),['Keep','Save']);
    assert.equal(h.get('action-support').textContent,'Choosing Keep or Save closes this task and ends its temporary recovery option.');
    assert.equal(writes(h).length,0);
  },
  async outcome_support() {
    for(const [name,end,text] of [
      ['finish_script','executed','Changes kept. No save was performed. Task closed; recovery ended.'],
      ['save_result','saved','Font saved. Task closed; recovery ended.'],
      ['restore_saved_script','discarded','Pre-run font restored without saving. Later edits were removed; task closed.'],
    ]) {
      const h=host({deferWrites:true});await tick();deliver(h,resultButtons());await tick();
      h.click(name);
      const done=state(2,end,[]);done.data.scope={kind:'python_script'};
      done.data.jobId='job_a';done.data.requestFingerprint='request_a';
      done.data.actionSupportText=text;
      if(name==='finish_script')done.data.job={status:'completed',error:{message:'Original script failed'},bridgeOperation:{error:{message:'Original script failed'}}};
      h.setState(done);
      h.dispatch({id:writes(h)[0].id,result:{structuredContent:done}});await tick();
      assert.equal(h.get('action-support').textContent,text);assert(!h.get('action-support').hidden);
      assert(h.get('actions').children.some(b=>b.dataset.feedbackPhase==='done'),'a settled partial result retains successful closure feedback');
      h.advance(1500);await tick();h.advance(600);await tick();
      assert(h.get('actions').hidden);assert(!h.get('action-support').hidden);
      assert.equal(h.get('action-support').textContent,text,'outcome persists after button fade');
      const external=host();await tick();deliver(external,done);await tick();
      assert.equal(external.get('action-support').textContent,text,'external completion and remount use server evidence');
      const unknown=state(3,'uncertain',[]);deliver(h,unknown);await tick();
      assert(h.get('action-support').hidden,'uncertain result clears the receipt');
    }
    const h=host({deferReads:true});await tick();
    const saved=state(1,'saved',[action('retry_checkpoint','Retry checkpoint without saving')]);
    saved.data.actionSupportText='Font saved. Task closed; recovery ended. The Git checkpoint failed; the font save succeeded.';
    saved.data.uiRefreshIntervalMs=5000;
    deliver(h,saved);h.dispatch({id:reads(h)[0].id,result:{structuredContent:saved}});await tick();
    h.advance(5000);await tick();
    assert(!h.get('action-support').hidden,'a routine pending refresh must retain the confirmed save receipt');
    assert.equal(h.get('action-support').textContent,saved.data.actionSupportText);
  },
  async checkpoint_retry_feedback() {
    for(const success of [false,true]) {
      const h=host({deferWrites:true});await tick();
      const initial=state(1,'saved',[{...action('retry_checkpoint','Retry checkpoint without saving'),presentation:'primary'}]);
      initial.data.receipt={checkpoint:{status:'failed'}};
      deliver(h,initial);await tick();h.click('retry_checkpoint');
      const next=JSON.parse(JSON.stringify(initial));next.data.revision=2;
      next.data.receipt.checkpoint.status=success?'created':'failed';
      if(success)next.data.actions=[];
      h.setState(next);h.dispatch({id:writes(h)[0].id,result:{structuredContent:next}});await tick();
      if(success)assert.equal(h.get('actions').children[0].textContent,'Ready');
      else {assert.equal(h.get('actions').children[0].textContent,'Retry checkpoint without saving');assert(!h.get('actions').children[0].dataset.feedbackPhase);}
    }
  },
  async script_unverified_feedback() {
    const h=host({deferWrites:true});await tick();
    const ready=state(1,'waiting_run',[action('run_script','Run script')]);ready.data.scope={kind:'python_script'};
    deliver(h,ready);await tick();h.click('run_script');
    const unverified=state(2,'applied',[action('finish_script','Keep without saving')]);
    unverified.data.scope={kind:'python_script'};
    unverified.data.job={bridgeOperation:{scriptResult:{executed:true,executionSucceeded:false}}};
    h.setState(unverified);h.dispatch({id:writes(h)[0].id,result:{structuredContent:unverified}});await tick();
    assert(h.get('actions').children.every(b=>!b.dataset.feedbackPhase),'an applied state alone cannot prove script success');
    assert(![...h.timers.values()].some(t=>t.delay===600));
  },
  async other_actions() {
    for(const [name,label,start,end,completion,kind='width_delta'] of [
      ['apply','Apply changes','ready','applied','Applied'],
      ['discard','Undo these changes','applied','discarded','Undone'],
      ['discard','Cancel preview','ready','discarded','Done'],
      ['cancel','Cancel','ready','cancelled','OK'],
      ['reprepare','Prepare again','outdated','ready','Ready'],
      ['reprepare','Prepare again','outdated','waiting_run','Ready','python_script'],
      ['manual_save',"I'll save in Glyphs",'waiting_save','waiting_manual','Ready'],
      ['save_result','Save font','applied','saved','Saved'],
      ['restore_saved_script','Restore before run','applied','discarded','Restored'],
    ]) {
      const h=host({deferWrites:true});await tick();
      const offered=[{...action('finish_edit','Keep without saving'),presentation:'primary'},
        {...action(name,label),presentation:'secondary'}];
      const initial=state(1,start,offered);initial.data.scope={kind};
      deliver(h,initial);await tick();
      const button=h.get('actions').children[1];h.click(name);
      if(name.includes('restore'))assert.equal(button.textContent,'Restore…','Restore must never announce saving');
      assert.equal(h.get('actions').children[1],button,name+' must stay in its original slot');
      assert.equal(h.get('actions').children[0].dataset.feedbackMuted,'true','unrelated choices stay hidden during feedback');
      assert(button.disabled);assert(h.get('action-feedback').hidden);
      const done=state(2,end,[]);done.data.scope={kind};h.setState(done);h.dispatch({id:writes(h)[0].id,result:{structuredContent:done}});await tick();
      assert.equal(h.get('actions').children[1],button);assert.equal(button.textContent,completion);
      assert(h.get('actions').children[0].disabled,'retired neighboring choices must never remain clickable');
      h.advance(1500);await tick();assert.equal(button.dataset.feedbackPhase,'fading');
      h.advance(600);await tick();assert(h.get('actions').hidden);
    }
  },
  async form_feedback() {
    const h=host({deferWrites:true});await tick();deliver(h,state());await tick();
    h.click('save_as_continue');const submit=h.get('save-form').querySelector('button[type=submit]');
    assert.equal(h.get('main')['data-form-open'],'true','the form replaces the original choices');
    h.get('save-form').listeners.submit({preventDefault(){}});
    assert.equal(submit.textContent,'Save…');assert(submit.disabled);
    assert(!h.get('save-form').hidden);assert(h.get('action-feedback').hidden);
    const saved=state(2,'saved',[]);h.setState(saved);h.dispatch({id:writes(h)[0].id,result:{structuredContent:saved}});await tick();
    assert.equal(h.get('save-form').querySelector('button[type=submit]'),submit);
    assert.equal(submit.textContent,'Saved');assert(!h.get('save-form').hidden);
    h.advance(1500);await tick();assert.equal(submit.dataset.feedbackPhase,'fading');
    h.advance(600);await tick();assert(h.get('save-form').hidden);
  },
  async status_feedback() {
    const h=host({deferReads:true});await tick();deliver(h,payload());
    h.dispatch({id:reads(h)[0].id,error:{message:'Offline'}});await tick();
    const button=h.get('check-status');assert(!button.hidden);
    button.listeners.click();assert.equal(button.textContent,'Check…');assert(button.disabled);
    h.dispatch({id:reads(h).at(-1).id,result:{structuredContent:payload(2)}});await tick();
    assert.equal(button.textContent,'Checked');assert(!button.hidden);assert(h.get('action-feedback').hidden);
    h.advance(1500);await tick();assert.equal(button.dataset.feedbackPhase,'fading');
    h.advance(600);await tick();assert(button.hidden);assert.equal(button.textContent,'Check status');
  },
  async uncertain_feedback() {
    const h=host({deferWrites:true});await tick();deliver(h,state(1,'applied',[action('restore_saved_script','Restore before run')]));await tick();
    h.click('restore_saved_script');
    const unknown=state(2,'uncertain',[action('check_outcome','Check result')]);
    h.setState(unknown);h.dispatch({id:writes(h)[0].id,result:{structuredContent:unknown}});await tick();
    assert(h.get('actions').children.every(b=>!b.dataset.feedbackPhase));
    assert(h.get('action-feedback').hidden);
    assert(![...h.timers.values()].some(t=>t.delay===1500||t.delay===600),'unknown outcomes must not schedule a success transition');
  },
  async keep_in_button() {
    const h=host({deferWrites:true});await tick();
    const applied=state(1,'applied',[
      {...action('finish_edit','Keep without saving'),presentation:'primary'},
      {...action('discard','Undo these changes'),presentation:'secondary'},
    ]);deliver(h,applied);await tick();
    const button=h.get('actions').children[0];h.click('finish_edit');
    assert.equal(h.get('actions').children[0],button,'keep feedback must reuse the clicked button');
    assert.equal(button.textContent,'Keep…');assert(button.disabled);
    assert(h.get('action-feedback').hidden);
    const kept=state(2,'executed',[]);h.setState(kept);
    h.dispatch({id:writes(h)[0].id,result:{structuredContent:kept}});await tick();
    assert.equal(h.get('actions').children[0],button);
    assert.equal(button.textContent,'Kept');assert(button.disabled);
    assert(h.get('action-feedback').hidden);
    h.advance(1500);await tick();assert.equal(h.get('actions').children[0],button);
    h.advance(600);await tick();assert(h.get('actions').hidden);
  },
  async inline_pause() {
    const h=host({deferWrites:true});await tick();
    const s=state(1,'applied',[
      {...action('finish_edit','Keep without saving'),presentation:'primary'},
      {...action('discard','Undo these changes'),presentation:'secondary'},
      {...action('wait_for_answer','Wait for my answer'),presentation:'auto_keep'},
    ]);
    s.data.autoKeep={enabled:true,action:'finish_edit',delaySeconds:30};
    deliver(h,s);await tick();assert.equal(h.get('auto-keep').dataset.reserved,'true');h.click('wait_for_answer');
    assert(h.get('action-feedback').hidden,'pause must not replace the row with a large feedback button');
    assert.equal(h.get('main')['data-action-feedback'],'');
    assert.equal(h.get('auto-keep-actions').children[0].dataset.feedbackPhase,'working');
    assert(h.get('auto-keep-actions').children[0].disabled);
    const paused=JSON.parse(JSON.stringify(s));paused.data.revision=2;paused.data.autoKeep.enabled=false;
    paused.data.actions=paused.data.actions.filter(a=>a.action!=='wait_for_answer');
    h.setState(paused);h.dispatch({id:writes(h)[0].id,result:{structuredContent:paused}});await tick();
    assert(h.get('action-feedback').hidden);
    assert.equal(h.get('auto-keep-actions').children[0].className,'icon-button');
    assert.equal(h.get('auto-keep-actions').children[0].title,'Pause countdown');
    assert.equal(h.get('auto-keep-actions').children[0].dataset.feedbackPhase,'disabled');
    assert(h.get('auto-keep-actions').children[0].disabled);
    assert.equal(h.get('inline-feedback-status').textContent,'');
    assert(h.get('auto-keep').hidden,'the paused countdown text stays hidden');
    assert.equal(h.get('auto-keep').dataset.reserved,'true','the hidden countdown retains its layout space');
    assert.equal(h.get('actions').children[0].disabled,false,'Keep remains available after pause is confirmed');
    h.advance(5000);await tick();assert(!h.get('auto-keep-actions').hidden);
    assert(h.get('auto-keep-actions').children[0].disabled);
    assert.equal(h.get('auto-keep-actions').children[0].dataset.feedbackPhase,'disabled');
    assert.equal(h.get('actions').children.length,2);
  },
  async action_feedback() {
    const h=host({deferWrites:true});await tick();
    const ready=state(1,'waiting_run',[action('run_script','Run script')]);
    ready.data.scope={kind:'python_script'};deliver(h,ready);await tick();
    const button=h.get('actions').children[0];
    h.click('run_script');
    assert.equal(h.get('actions').children[0],button);
    assert.equal(button.textContent,'Run…');assert(button.disabled);
    assert(h.get('action-feedback').hidden);
    h.click('run_script');assert.equal(writes(h).length,1,'duplicate clicks are blocked');
    const running=state(2,'applying',[action('cancel','Cancel remaining targets')]);running.data.scope={kind:'python_script'};
    h.setState(running);h.dispatch({id:writes(h)[0].id,result:{structuredContent:running}});await tick();
    assert.equal(button.textContent,'Run…');
    assert.equal(button.dataset.feedbackPhase,'working');
    const cancel=h.get('actions').children.find(b=>b.dataset.action==='cancel');
    assert(cancel&&!cancel.dataset.feedbackMuted&&!cancel.disabled,'active cancellation must remain available');
    const finished=state(3,'applied',[action('finish_script','Keep without saving')]);finished.data.scope={kind:'python_script'};
    finished.data.job={bridgeOperation:{scriptResult:{executed:true,executionSucceeded:true}}};
    deliver(h,finished);await tick();
    assert.equal(button.textContent,'Done');
    assert.equal(button.dataset.feedbackPhase,'done');
    assert(!h.get('actions').children.some(b=>b.dataset.action==='finish_script'),'new choices wait for feedback to settle');
    h.advance(1500);await tick();assert.equal(button.dataset.feedbackPhase,'fading');
    h.advance(600);await tick();assert(h.get('action-feedback').hidden);
    h.click('finish_script');assert.equal(writes(h).length,2);
    h.dispatch({id:writes(h)[1].id,result:failed('demo_rejected')});await tick();
    assert(h.get('action-feedback').hidden,'rejected choices never show success feedback');
  },
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
    assert(!h.get('actions').hidden);assert.equal(h.get('check-status').textContent,'Checked');assert.equal(h.get('error').textContent,'');
    h.advance(1500);await tick();h.advance(600);await tick();assert(h.get('check-status').hidden);
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
    assert.equal(h.get('auto-keep-actions').children[0]['aria-label'],'Turn off automatic Keep');
    assert.equal(h.get('auto-keep-actions').children[0].className,'icon-button');
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
    deliver(h,s);await tick();assert.equal(h.get('auto-keep-actions').children[0]['aria-label'],'Pause countdown');
    assert.equal(h.get('auto-keep-actions').children[0].title,'Pause countdown');
    assert.equal(h.get('auto-keep-actions').children[0].textContent,'');
    assert(h.get('actions').children[0].children.includes(h.get('auto-keep-progress')));
    assert.equal(h.get('auto-keep-progress').hidden,false);
    for(let seconds=5;seconds<30;seconds+=5) {
      h.advance(5000);await tick();assert.equal(writes(h).length,0);assert.equal(h.get('auto-keep-progress').value,seconds);
      assert(h.get('actions').children[0].children.includes(h.get('auto-keep-progress')));
    }
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
