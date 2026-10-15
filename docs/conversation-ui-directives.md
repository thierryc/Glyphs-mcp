# Glyphs MCP conversation UI directives

Reviewed: October 14, 2026.

Use native questions for decisions and missing information, grouping related
questions when they can be answered together. Use native conversation feedback
for routine progress, success and errors. Use cards when visual evidence,
interactive inspection, substantial reports or recovery controls add real value.

This guide consolidates the current interaction rules and maps them to use cases.
It records presentation policy and current implementation limits; it does not
introduce new font operations or authorize edits, saves or restoration.

## UI types

| UI type | Purpose | Fallback |
| --- | --- | --- |
| Native choice question | Resolve one decision with concise choices. | Ask the same question in ordinary chat. |
| Native free-text question | Collect missing information that choices cannot express. | Ask for a natural-language reply. |
| Grouped native questions | Collect related, independently answerable decisions in one submission. | Ask a compact set of questions in chat, or split according to host limits. |
| Native conversation feedback | Explain current activity, verified results, warnings and errors. Native tool activity may supplement it. | Ordinary conversation remains the baseline. |
| Optional MCP card | Present useful visual evidence, substantial reports, live controls or recovery information. | Preserve the same workflow and explain its state and offered actions in chat. |
| Host permission prompt | Obtain permissions required by the host's execution or access policy. | Follow the host's permission mechanism; a font-design answer does not replace it. |

“Native” means the conversation host renders the interaction. The Glyphs skill
instructs the agent which interaction to use; it does not control native styling.
Choose by the tools and capabilities actually available, rather than assuming
support from a client name such as ChatGPT, Codex, Claude or Cursor.

## Use cases for decisions and missing information

| Use case | Preferred UI | Directive |
| --- | --- | --- |
| Font or document is ambiguous | Native question | Identify the intended document before acting. Distinguish similarly named fonts. |
| Master and glyph scope are missing | Grouped native questions | Ask together when the answers are independent. Do not ask again for scope already supplied. |
| Foreground/background or owning layer is ambiguous | Native question | Clarify the intended target; resolve exact internal identifiers without exposing them as user input requirements. |
| An exact value or custom glyph list is missing | Native free-text question | Collect only missing information and validate it against the operation's supported scope. |
| A later question depends on an earlier choice | Sequential native questions | Ask the dependent question after receiving the earlier answer. Do not bundle incompatible stages. |
| An explicit preview needs acceptance | Native choice question | Offer current Apply/Cancel choices. Include a card only when its evidence helps the review. |
| A requested edit or script is already authorized | No additional question | Execute the offered Apply/Run action within that authorization. Do not add a second approval just to use native UI. |
| Typed editing requires saving a dirty font first | Native choice question, unless saving is already authorized | Explain that prerequisite Save includes the whole font and existing unsaved work. Offer only the workflow's current alternatives. |
| Save As needs a destination | Native free-text or grouped questions | Collect folder and filename together when useful. Show the resolved absolute new destination before saving. Never overwrite an existing file. |
| The user will save manually in Glyphs | Conversation feedback, then a question only if needed | Retain the request. Check and continue after the user reports saving; do not poll an unchanged waiting choice. |
| Existing Dimensions values would be replaced | Explicit native question with exact values | Obtain approval for every required old/new replacement. Use a supporting card if a long list makes review clearer. |
| A short warning needs a decision | Conversation explanation plus native question | Explain coverage and consequences before asking. Reuse existing authorization where it covers the proposal. |
| A successful result needs a Keep/Save/recovery decision | Native choice question | Offer current valid choices; explain saving and recovery consequences. Disable Automatic Keep before waiting. |
| The user requests Save or Restore clearly and within scope | No repeated question | Revalidate current state and execute under existing authorization. Clarify only unresolved scope or consequences. |
| An earlier workflow blocks a new request | Native question about the earlier workflow | Resolve its current Keep/Save/recovery choices. Do not automatically settle it or invent an Undo option for a script. |
| The user skips, dismisses or does not answer | Conversation fallback when appropriate | Apply no choice, leave Automatic Keep off and preserve recovery. Do not reopen the same question automatically. |

Questions use the workflow's latest offered actions. Do not invent actions to
make a question look consistent. Avoid collecting every possible preference at
the beginning of a task; ask only what is needed to proceed.

## Use cases for progress and outcomes

| Use case | Preferred UI | Directive |
| --- | --- | --- |
| Routine request start | Native conversation/tool feedback | State the intended font, change and scope briefly. No introductory card. |
| Preparation or short application | Native conversation/tool feedback | Say “Preparing changes…” or “Applying changes…”, as appropriate. Preparation is not application. |
| Repeated reads with unchanged state | No additional message | Poll the same workflow only while required. Do not narrate every refresh. |
| Long-running work with useful monitoring or cancellation | Optional card plus concise conversation feedback | Open a card only when the controls or monitoring are useful. Reuse it through later stages. |
| Script preparation is complete | Conversation feedback | Preparation validates the request without executing Python. Run under existing edit authorization; explicit previews still wait. |
| A script is running | Native conversation/tool feedback | Give the execution warning once; keep exact source and parameters optional. A running callback may not be interruptible. |
| Edits are complete and verified | Native conversation feedback | Report observed changes and scope. Do not equate completed execution with verified design correctness. |
| The font was saved | Native conversation feedback | Say “Font saved.” Saving and an optional project checkpoint are separate outcomes. |
| Changes were kept without saving | Native conversation feedback | Make clear that Keep ends the workflow's recovery offer and does not save the font. |
| A preview was discarded | Native conversation feedback | Say “Changes discarded.” Do not claim applied changes were undone if nothing was applied. |
| A request was cancelled | Native conversation feedback | Report cancellation and any known partial changes. Cancellation does not necessarily restore earlier changes. |
| A routine error occurs | Native conversation feedback | Explain what failed, what is known about the font and the useful next step. No error-only card by default. |
| A request times out or its outcome is uncertain | Conversation feedback, then Check result | Reconcile the same workflow. Do not replay a mutation or infer success from elapsed time. |
| The proposal or target became stale | Conversation explanation plus a fresh decision if needed | Re-read state. Old approval does not transfer to a materially changed proposal, target or consequence. |
| Saving succeeded but its Git checkpoint failed | Native conversation feedback | Report Save success separately. Retry only the checkpoint when authorized. |

Progress feedback is the conversation's ordinary activity/status presentation.
It does not promise a custom native progress bar, spinner, toast or animation.
Only report measured counts or percentages supplied by the operation.

## Use cases that justify a card

| Use case | Card value | How questions fit |
| --- | --- | --- |
| Before/after glyph comparison | Geometry and placement are easier to judge visually. | Ask an unresolved acceptance decision natively, using the comparison as evidence. |
| Interactive glyph inspection | Zooming, selecting, overlaying or examining details adds value when a suitable renderer exists. | Collect intent and scope natively; use the card for inspection. |
| Substantial report | Many affected targets, warnings, skipped items or replacement approvals need organized evidence. | Ask the remaining decision once; do not duplicate it across several surfaces. |
| Useful recovery controls | Recovery state and consequences are easier to inspect or act on together. | A native question remains suitable for a simple Keep/Save/Undo/Restore decision. |
| Long-running progress with useful controls | Persistent monitoring or cancellation helps the user. | Routine status remains concise in chat. |
| The user explicitly requests a card | The requested display itself is useful to the user. | Keep the same workflow and authorization rules. |

The current workflow card supports lifecycle state, reports/proposals, offered
actions, Save As, details, recovery and countdown controls. This routing policy
does not mean a dedicated interactive outline viewer or visual glyph comparison
has been implemented in that template. Use actual available evidence/renderers;
do not substitute a generic status card for a promised visual comparison.

Do not create cards for routine starts, every poll, simple questions, empty
results, short success messages or routine errors. Lack of a native question
tool alone does not justify a card. Keep one useful existing card and refresh it
instead of producing a new card at every stage. Closing a card does not cancel
authorized work, and the agent cannot remove host-owned historical cards.

## Native question behavior

1. Reuse information and scoped authorization already provided.
2. Group related independent questions within the current host's limits. Use
   concise choices, free text or a combination when supported.
3. Before waiting, disable this workflow's Automatic Keep through its offered
   `wait_for_answer` action, or start with `auto_keep=false` if the need is known.
4. Treat silence, Skip and dismissal as no answer. A selected default that was
   never submitted is not authorization.
5. Re-read the same workflow before acting on a later reply and check that the
   proposal, target and consequences still match the answer.
6. Dispatch the current revision-bound, server-issued action internally. Users
   never need to enter workflow IDs, tokens or JSON.

If a useful card is already visible, keep it as evidence and request one answer.
Do not require both a native answer and a card click for the same decision.
Native questions come from the agent's host tools; the current implementation
does not add a Glyphs MCP server elicitation endpoint or native form integration.

## Automatic Keep is a separate card behavior

Native questions never automatically accept an unanswered choice. The existing
card-only Automatic Keep behavior is a separate, explicit workflow mechanism.

| Condition | Behavior |
| --- | --- |
| Eligible successful result, Automatic Keep enabled, card visible, connected and freshly reconciled | After 30 seconds, Keep without saving ends the workflow recovery offer. |
| A native question is waiting, or the user has said “wait for my answer” | Automatic Keep is disabled. Retain that preference until changed. |
| The card is hidden, reconnecting, or details/options are being inspected | Pause/reset elapsed time and reconcile before a fresh countdown. |
| Failed, partial, blocked or uncertain result | Never automatically Keep. |
| Text-only interaction without an eligible visible card | Remain manual. |
| Run, Apply, Save, Undo or Restore | No countdown-based authorization or execution. Existing authorized Apply/Run behavior remains separate. |

Keep never saves. Typed Keep preserves native Glyphs Undo/Redo; script Keep ends
the session-local Restore offer and does not promise native Undo/Redo. Script
Restore replaces the whole font with its pre-run copy, including earlier unsaved
work, discards later edits, clears Undo and never saves. Typed Undo is selective
and checks for conflicting later edits.

## Card action and countdown presentation

These are the approved custom-card rules; native host controls retain their own
appearance.

| Element | Presentation rule |
| --- | --- |
| Result buttons | Keep is neutral, Save is primary and available script Restore is neutral with an inline back-arrow icon. Display Keep, Save, Restore in that order; emphasis does not determine ordering or authorize Save. Typed recovery remains Undo these changes. |
| Save destination | A pathless script result still labels its button Save; it opens the existing Save As form. The accessible description explains the new destination requirement. |
| Button descriptions | Do not show result-button tooltips on hover or focus. Keep explanations accessible through aria-describedby, with consequences visible in supporting text. |
| Supporting text | Below the actions and countdown, show “Choosing **Keep** or **Save** closes this task and ends its temporary recovery option.” Use exact button labels and bold them. Partial outcomes mention only available choices. Keep Restore consequences visible outside View details. |
| Outcome text | Retain a confirmed Keep, Save, Restore or typed Undo receipt after button feedback fades, including when another surface completes the task. Unknown and failed outcomes never receive a success receipt. Keep checkpoint failure separate from successful font saving. |
| Action feedback | Reuse the clicked button, retaining its width and position. Do not append another success button. |
| Working label | Use short labels such as “Run…”, “Save…”, “Apply…” or “Keep…” with an inline spinner. |
| Completed label | Use compact labels such as “Done”, “Saved”, “Applied”, “Kept” or “Restored”. Only show success after confirmation. |
| Final transition | Hold normal completion feedback for 1.5 seconds, then fade over 600 milliseconds. Respect reduced-motion preferences. |
| Competing controls | Hide unrelated actions during submission; retain cancellation when it is useful and valid. |
| Action row | Keep the primary, secondary and pause controls on one compact line. Avoid label wrapping. |
| Icon and label | Keep a readable gap smaller than horizontal padding: 6 px gap / 13 px padding normally; 4 px / 7 px in the compact feedback layout. |
| Pause control | Remain a 42 × 42 px icon button. Show its spinner in place, then keep it disabled in place after pausing; do not add “countdown paused” text. |
| Countdown progress | Display progress inside Keep, independently of Save’s primary styling. |
| Countdown text | Place the muted 11 px line below the buttons with a 6 px gap. |
| Countdown layout stability | Reserve the countdown line's space for the same result when its text disappears. Do not reserve empty lines on unrelated cards. |
| Save As form | Replace competing action controls while the form is open; show the resolved destination and prevent overwrites. |
| Details and warnings | Put source, parameters and diagnostics in optional details; keep material warnings and recovery consequences visible. |
| Accessibility | Preserve accessible names, focus indication, status announcements and reduced-motion behavior. Short visual labels do not remove action meaning. |

The optional action `tooltip` and workflow `actionSupportText` fields carry the
same explanations in accessible descriptions and conversational results; tooltip metadata does not create a visible popup. Keep still means keep
without saving; Save saves the whole font; script Restore uses the recovery
actually offered by that workflow. Existing natural-language phrases remain
valid. These presentation fields change no action identifiers, freshness tokens,
mutation signatures or persisted workflow records. A companion Tasks view and
broader blocker discovery remain separate future work.

## Implementation responsibilities

| Component | Responsibility |
| --- | --- |
| Skill directives | Tell the agent when to ask, group questions, use conversation feedback or open a useful card. |
| `start_edit_workflow` | Start the retained request and return state/actions without automatically opening a card. |
| `get_edit_workflow` | Read state without mutation or a new card. |
| `respond_edit_workflow` | Execute a valid offered action under its revision, token and authorization checks; no automatic card. |
| `show_edit_workflow` | Read-only display of an existing workflow through the optional MCP card. It does not start, apply or save work. |
| Conversation host | Render available native questions, activity, permissions and optional MCP Apps. Availability is capability-dependent. |
| Preview gallery | Simulate routing and card behavior. Its native-question rendering is a demo, not the real host's native UI. |

## Documentation alignment

The primary skill, detailed workflow reference and tool registration agree on
native-first routing and optional cards. Grouped questions and progress/error
guidance are present in the canonical skill and its synchronized plugin copy.

The reviewed inconsistencies have been corrected in the current documentation:

| Location | Correction | Current directive |
| --- | --- | --- |
| Conversation and first-session tutorials | Removed assumptions that a card always appears or that retaining edits requires saving. | Use native questions/chat by default. Say “Changes applied.” Keep without saving remains a valid choice and ends workflow recovery. |
| Main and scripting skills, countdown references and public documentation | Made eligibility and native-question handling explicit. | Timed Keep requires an enabled, visible, connected, reconciled successful result card. Native questions disable it; failed, partial, blocked and uncertain outcomes remain manual. |
| Public tool reference, plugin README and tutorials | Aligned grouped questions, routine feedback and value-based card routing. | Group independent missing information; use conversation feedback for routine progress, success and errors; reuse useful cards. |
| Visual comparisons and interactive inspection | Clarified the difference between UI routing and available renderers. | Use a supported renderer or native Glyphs view; the workflow card is not a dedicated outline viewer. |

Canonical skills and their packaged copies are synchronized. These are
documentation and agent-guidance changes; they do not change runtime behavior or
require a service restart. Historical release and qualification records retain
the behavior of the versions they describe.

## Source directives and implementation

- [Main Glyphs skill](../skills/glyphs/SKILL.md)
- [Detailed conversation workflow](../skills/glyphs/references/edit-workflow.md)
- [Script execution and recovery](../skills/glyphs/references/python-scripts.md)
- [MCP workflow tool registration](../src/sidecar/glyphs_mcp_sidecar/edit_workflow_ui.py)
- [Workflow card template](../src/sidecar/glyphs_mcp_sidecar/edit_workflow_v1.html)
- [Conversation tutorial](../content/tutorial/conversation-edits.mdx)
- [Packaged skill copy](../plugins/glyphs-mcp/skills/glyphs/SKILL.md)
- [Interactive preview generator](../output/ui-gallery/build_gallery.py)
