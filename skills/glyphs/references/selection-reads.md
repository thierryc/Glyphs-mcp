# Native selection context

For the toolbar master or selected glyphs in Font/Edit View, use the separate
[document context read](context-reads.md), requiring `document.context.v1`.
Keep this existing node/object selection response unchanged.

Use the current private lean installation. On the **specific MCP connection**,
check the retained `get_status` → `readCapabilities` for **`selection.context.v1`**;
do not fetch status again solely to enter this reference. This is
the sidecar/bridge capability intersection. Do not infer support from the Beta 1
product label or a different connection.

If the capability is unavailable, explain: **“This installation needs updating:
update the bridge, sidecar and skills together to use selection.context.v1.”**
Stop this selection workflow until the updated components are running. Do not
substitute earlier private v2 requests, live Python or UI inspection as a fallback.
Use the existing installer; verify fresh status after reloading the updated
bridge in Glyphs and restarting the sidecar. Follow the existing installation
ownership/conflict guidance rather than editing plugin caches.

Use the retained `document_id` for this connection, including changed selections.
Only if the binding is missing or stale, resolve it through `list_documents`.
Follow [document targeting](document-targeting.md)
for stale IDs and current/frontmost intent. Recommend this compact summary,
with every field explicitly requested:

```json
{"document_id":"doc_…","entities":[{"kind":"selection"}],"fields":["glyph","layer","selectedNodeCount","selectedAnchorCount","selectedComponentCount","selectedGuideCount","selectedOtherCount"]}
```

`glyph` is the active Edit View glyph name; `layer` is its exact native layer ID.
The five counts classify the native layer selection by `GSNode`, `GSAnchor`,
`GSComponent`, `GSGuide`, and remaining objects. Off-curves count as nodes;
anchors, components and guides do not. The categories do not overlap. Request
fewer fields when only a particular value is needed. Never add node details to
every read or treat a count as geometry evidence.

For coordinates and node locations, add `nodes` to `fields`. Use one selector
`{"kind":"selection","nodeLimit":64}`. Omit `nodeLimit` to use 64; an explicit
integer from 1 to 256 is allowed only with `nodes`. No other entities can share
a detailed request. The response returns shared glyph/layer metadata once:

```json
{"nodes":{"total":1,"returned":1,"limit":64,"complete":true,"items":[{"x":50.375,"y":0.375,"type":"offcurve","smooth":false,"pathIndex":0,"nodeIndex":2}]}}
```

This is the additional `values.nodes` field, not the complete response envelope.
Each item's coordinates, type and Boolean smooth status come from the native
node. `pathIndex` is zero-based in **layer.paths**, excluding components, even
when layer.shapes intermixes paths and components. `nodeIndex` is zero-based in
the complete **path.nodes** collection, including off-curves. Items follow native
selection enumeration order, not guaranteed click order. Indices identify this
live read; they are not persistent IDs or cross-master correspondence.

`total` counts all selected GSNodes; `returned` equals the number of items.
`complete:false` explicitly means the node limit truncated the evidence. For
256 selected nodes at limit 64, say **“64 of 256 selected nodes inspected”**.
Do not report all nodes checked. Request a larger limit only if useful, up to
256, or ask the user to narrow a larger selection. There is no pagination or
implicit reselection. Native evidence errors are explicit; never invent an
index, turn missing evidence into zero, or call an unavailable result complete.

A live layer with zero selected nodes retains its glyph/layer identities;
requested `nodes` has total/returned 0, complete true and an empty items list.
Selected anchors/components/guides may still have nonzero counts. Null
glyph/layer and `nodes:null` mean **no active Edit View**, including Font View
with glyphs selected. They do not mean a complete empty node inspection. This
request does not identify the frontmost document; target the intended document.

Reads work on dirty or untitled documents and need no job, preparation or Save.
Only requested fields appear. Summary requests retain the existing 100-selector
bound; detailed inspection stays within one active glyph/layer. Keep editing,
Undo/discard and cross-master mapping outside this read workflow. Do not invent
a `get_selected_nodes` tool.
