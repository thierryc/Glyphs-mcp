"""Narrow companion recovery facade over the existing workflow actions."""
import hmac

from .edit_workflow_state import action_token, offered_actions, action_support_text
from .task_inventory import _state


def _choices(value):
    offered = dict(offered_actions(value))
    job = value.get('job') or {}
    choices = []
    if not value.get('blockerId'):
        for name in ('finish_script', 'finish_edit'):
            if name in offered and job.get('status') in {'applied', 'failed', 'cancelled'}:
                consequence = ('Keep current changes in Glyphs without saving. Close this task and end its selective Undo option. Native Undo remains available.'
                               if name == 'finish_edit' and value['request']['kind'] != 'checkpoint_restore' else
                               'Keep current changes in Glyphs without saving. Close this task and end its temporary recovery option.')
                if value['state'] in {'failed', 'cancelled'}:
                    consequence += ' Partial edits may remain; inspect the font before closing.'
                choices.append(dict(action=name, label='Close Without Saving', consequence=consequence, token=action_token(value, name)))
    if 'cancel' in offered:
        running_script = (not value.get('blockerId') and value['state'] == 'applying'
                          and job.get('resultKind') == 'script' and job.get('status') == 'applying')
        pending = (not value.get('jobId') or job.get('status') in {'preparing', 'ready'})
        if running_script or pending:
            choices.append(dict(action='cancel', label='Cancel Remaining Work' if running_script else 'Cancel Task',
                                consequence=('Request cancellation of remaining targets. Applied changes remain. Cancellation may take time, and recovery may still need a decision.' if running_script else
                                             'Cancel this pending request without saving. Earlier blocking tasks remain open.'),
                                token=action_token(value, 'cancel')))
    if ('discard' in offered and value['state'] in {'ready', 'needs_review'}
            and job.get('status') == 'ready' and not value.get('blockerId')):
        choices.append(dict(action='discard', label='Cancel Task',
                            consequence='Discard this unapplied preview and close the task. No font save or edit is performed.',
                            token=action_token(value, 'discard')))
    return choices


def options(service, workflow_id):
    workflows = service.edit_workflows
    with workflows.lock, service._lock:
        value = workflows._find(workflow_id)
        problem = None
        # Never advance a blocked request: resolving its owner could start it.
        # Never turn an old ready/preparing job into a resumable apply intent.
        if value.get('jobId') and not value.get('blockerId'):
            try:
                job = service.get_job(value['jobId'])
                if job.get('status') not in {'ready', 'preparing'}:
                    workflows._advance(value, allow_apply=False)
                else:
                    workflows._set(value, job=job)
            except Exception:
                problem = 'The current outcome could not be checked. Reconnect and check again before closing this task.'
        job = value.get('job') or {}
        closed = _state(value, job, True)[1]
        choices = [] if problem or closed else _choices(value)
        pending = value['state'] in {'discarding', 'resolving'} or job.get('status') in {'cancelling', 'discarding'}
        receipt = action_support_text(value) if closed else None
        if closed and not receipt:
            receipt = 'Task cancelled. No save was performed.' if value['state'] == 'cancelled' else 'This task is already closed. Its recorded outcome has been retained.'
        message = problem or (receipt if closed else
            'Cancellation is still in progress. Changes already applied may remain; check again for the final outcome.' if pending else
            'The outcome is not confirmed. Check again or continue in your agent. This task cannot be closed safely here yet.' if not choices and value['state'] in {'interrupted', 'uncertain'} else
            'No closing action is currently available. Work may still be running or require review in your agent.' if not choices else
            'Review the consequences before resolving this abandoned task.')
        document = value['document']
        return dict(workflowId=value['id'], revision=value['revision'], state=value['state'],
                    documentName=document.get('familyName') or 'Untitled font', path=document.get('path'),
                    warning=(value.get('error') or job.get('error') or {}).get('message'),
                    message=message, closed=closed and problem is None, pending=pending,
                    receipt=receipt if problem is None else None, actions=choices)


def respond(service, workflow_id, revision, token):
    workflows = service.edit_workflows
    with workflows.lock, service._script_dispatch_lock, service._lock:
        current = options(service, workflow_id)
        choice = next((item for item in current['actions'] if hmac.compare_digest(item['token'], token)), None)
        if type(revision) is not int or revision != current['revision'] or choice is None:
            raise workflows.error('stale_workflow_action', 'This choice is outdated or unavailable. Check the task again before choosing.')
        # Existing lifecycle reservation, token consumption, native guards and
        # recovery ownership remain authoritative. No action is synthesized.
        result = workflows.respond(workflow_id, revision, token)
        if error := result.get('error'):
            raise workflows.error(error['code'], error['message'], details=error.get('details'))
        return options(service, workflow_id)
