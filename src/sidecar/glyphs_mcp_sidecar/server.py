"""FastMCP transport for the standalone sidecar and conversation workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from glyphs_mcp_protocol import TOOL_NAMES, load_or_create_token

from .bridge_client import BridgeClient
from .jobs import JobStore
from .identity import RELEASE_VERSION
from .service import ServiceError, SidecarService
from .worker import GlyphsCliWorker


def _result(callback: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": callback()}
    except ServiceError as exc:
        return {"ok": False, "error": exc.as_dict()}


def create_server(service: SidecarService, *, control_token: str | None = None) -> Any:
    from fastmcp import FastMCP

    mcp = FastMCP(name="Glyphs MCP Sidecar", version=RELEASE_VERSION)

    @mcp.tool(name="get_status")
    def get_status() -> dict[str, Any]:
        """Return sidecar, worker and bridge availability, negotiated read/write/jobCapabilities, job kinds, and the filtered closed nativeActions catalog."""
        return _result(service.get_status)

    @mcp.tool(name="list_documents")
    def list_documents() -> dict[str, Any]:
        """Discover open Glyphs documents once for the intended target. With document.context.v1, isCurrent is native current-font evidence (true/false, null if unavailable); never infer it from list order. Retain its document_id on this connection for subsequent fresh reads; rediscover after document_not_found or changed target intent."""
        return _result(service.list_documents)

    @mcp.tool(name="read_entities")
    def read_entities(
        document_id: str, entities: list[dict[str, Any]], fields: list[str]
    ) -> dict[str, Any]:
        """Read up to 100 explicit targets using a known document_id on this connection; no preceding list_documents is needed for the same target. Reads validate the live font and return fresh contents. Rediscover on document_not_found, not target_not_found (missing glyph/layer). Never substitute another font. Current/frontmost intent may require fresh targeting. document.context.v1 advertises one {kind: context} selector with requested fields view, master and selectedGlyphs. View is font/edit/unavailable; master is exact id/name or null. SelectedGlyphs returns native-order names, source, total/returned/limit/complete; optional glyphLimit 1-100 (default 100) requires selectedGlyphs. Do not mix context with other entities. Incomplete or unavailable selection is not an edit scope; narrow the selection. No implicit node details. If document.context.v1 is absent, update bridge, sidecar and skills together. With negotiated glyphs.list.v1, discover names using one {kind: glyphs, limit: 100} selector and fields [name]. Limit is 1-100; values includes items, total, returned, complete and opaque nextCursor. Pass that cursor unchanged in the next glyph selector. On stale_glyph_cursor or any observed edit, discard partial results and restart without a cursor. Guards check document, count, change signal and boundary; pages are live, not atomic. If the capability is missing, update bridge, sidecar and skills together. Known glyphs need no inventory. With negotiated layers.list.v1, use one {kind: layers, glyph: <name>, limit: 100} selector with requested fields id, name, associatedMasterId, isMasterLayer, isSpecialLayer, isBraceLayer and/or isBracketLayer. Native layer collection order; values includes items, total, returned, complete and opaque nextCursor. Limit 1-100 defaults to 100. Reuse the cursor only for the same glyph/document. On stale_layer_cursor or any observed edit, discard partial results and restart. Pages are live, not atomic; null optional fields mean unavailable evidence. Nested backgrounds are not separate entries; flags do not establish compatibility or special-layer groups. No geometry in this inventory. Exact returned IDs feed ordinary layer reads. If layers.list.v1 is missing, update bridge, sidecar and skills together. Master selectors require exact IDs. Layers use {kind: layer, glyph: name, id: nativeLayerId}; layer.read.exact.v1 advertises strict IDs and returned id=layerId. Layer fields: id, name, width, vertWidth, vertOrigin, leftMetricsKey, rightMetricsKey, widthMetricsKey, bounds, outlineHash. With masters.list.v1 in get_status bridge.readCapabilities, use one {kind: masters, limit: 100} selector and fields [id, name] to discover live masters; follow values.nextCursor until values.complete. Do not mix a master page with other selectors. With negotiated master.properties.v1, exact masters and master pages also accept requested ascender, capHeight, xHeight, descender, italicAngle and axes. Metrics are fractional native master defaults, not layer-specific metrics. Axes contains native-order items (axisId, tag, name, index, internalValue, externalValue), total, returned and complete; null positions have explicit unavailable locations and complete:false. Maximum 32 axes per master and 256 master-axis items per request; narrow masters/page size or omit axes on invalid_request. No implicit fields, save, slant or axis mapping. With master.dimensions.read.v1, 1-4 exact master selectors accept fields [dimensions]. Values include key, label, script, present, value, storedValue, valid and editable; zero is set and malformed data is never blank. Reads need no Save and do not create metadata. Dimensions are per-master reference notes, not outlines or hinting stems. Do not request dimensions on master pages. Missing private capability requires a coordinated update. Selection requires selection.context.v1 in get_status readCapabilities; if absent, the private installation needs its bridge, sidecar and skills updated together. Use {kind: selection}, requesting glyph, layer, selectedNodeCount, selectedAnchorCount, selectedComponentCount, selectedGuideCount and selectedOtherCount for a summary. Optional nodes returns items (x, y, type, smooth, pathIndex in layer.paths, nodeIndex in path.nodes), total, returned, limit and complete. Details require one selection entity only; optional nodeLimit is an integer 1-256, default 64, allowed only with nodes. Counts use native types, including off-curve GSNodes. Null glyph/layer and nodes=null mean no active Edit View; active empty details are complete with zero items. Dirty documents need no Save. Only requested fields are returned. With negotiated kerning.groups.v1, named glyph reads also support left/right/top/bottomKerningGroup and left/right/top/bottomKerningKey properties (for example rightKerningKey); only requested properties. Group names, lookup keys and raw storage IDs differ. With kerning.pairs.v1 use one {kind: kerning_pairs, master: exactId, direction: LTR, limit: 100} selector and fields left, right and/or value. Each side is {key: rawKey, glyph: resolvedNameOrNull, kind: group/glyph/unresolved}. Optional leftKey/rightKey filters use exact raw stored keys, not glyph names. Limit 1-100; values includes items, total: null (unavailable), returned, complete, nextCursor, scanned and scanLimit: 256. Work counts outer groups including misses and inner entries. Empty incomplete pages require continuation; pass the opaque cursor with the same master/direction/filters. Native indices resume without previous-page rescans. On stale_kerning_cursor or any observed edit, discard partial results and restart; bounded guards do not make live pages atomic. No effective kerning, jobs or saves. Missing private capabilities require coordinated installation update. Kerning uses {kind: kerning, master: <exact native master ID>, direction: LTR, left: A, right: V} with fields [value] only. Required direction is LTR, RTL or vertical (case-sensitive). Keys are glyph names or explicit stored @MMK_ group keys, not native glyph IDs. Return exact storage: null means no entry for those keys; zero is stored. This does not compute effective kerning through class/exception precedence. Dirty and unsaved live reads need no job or Save. With paths.list.v1 and path.geometry.v1, one sole selector reads path summaries via fields [items], normalized path nodes via fields [nodes], or explicit segment fields. Path/node pages use opaque stale-checked cursors with limits 100/256 and remain available for dirty or unsaved fonts. With features.read.v1, page one prefix/class/feature collection with {kind: feature_blocks, blockType, limit} and fields [items], or read an exact persistent ID with {kind: feature_block, blockType, id}. With instances.read.v1, page {kind: instances, limit} with fields [items], or read {kind: instance, id}; exact IDs feed export jobs. Invalid master, glyph or direction returns invalid_request; keep the document ID and correct the input."""
        return _result(lambda: service.read_entities(document_id, entities, fields))

    @mcp.tool(name="start_job")
    def start_job(
        document_id: str,
        kind: str,
        delta: float | None = None,
        glyphs: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare a supported mutation, feature_compile diagnostic, or font_export artifact through negotiated jobCapabilities. Closed jobs accept only typed fields and never accept Python, menu items, or selectors. get_job reports evidence. With master.dimensions.edit.v1, dimensions_edit uses options.changes (1-100 exact {master, key, value} entries; numeric values or null to clear), and no delta or glyphs. Requires a saved clean font. It proposes reference metadata edits only, never measures outlines. Read the complete report.targets and requiredOverwrites; fill blanks freely using task-established values, ask in conversation only before overwriting or clearing existing values."""
        return _result(
            lambda: service.start_job(
                document_id, kind=kind, delta=delta, glyphs=glyphs, options=options
            )
        )

    @mcp.tool(name="get_job")
    def get_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Return progress and a typed mutation, diagnostic or artifact result with report, manifest, warnings and bounded previews. Use include_preview=false for compact polling."""
        return _result(lambda: service.get_job(job_id, include_preview=include_preview))

    @mcp.tool(name="apply_job")
    def apply_job(job_id: str, include_preview: bool = True, approved_overwrites: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Apply mutation jobs only as a reversible live change; diagnostic and artifact jobs are not applicable. This is not acceptance. Dimensions blank fills need no confirmation. Before overwriting or clearing an existing Dimensions value, show every master/field and exact old/new value and wait for explicit approval in the conversation. Only then pass the exact report.requiredOverwrites entries as approved_overwrites. This records assistant-reported approval, not authenticated human consent. Mixed batches wait together; regenerate a reduced job if changes are declined. Never save automatically."""
        return _result(lambda: service.apply_job(job_id, include_preview=include_preview, approved_overwrites=approved_overwrites))

    @mcp.tool(name="accept_job")
    def accept_job(
        job_id: str,
        destination: str | None = None,
        include_preview: bool = True,
    ) -> dict[str, Any]:
        """Persist a current applied mutation with verified Save/Save As, or publish verified export artifacts to a new absolute destination directory. Neither mode overwrites; both return source-bound receipts."""
        return _result(
            lambda: service.accept_job(
                job_id,
                destination=destination,
                include_preview=include_preview,
            )
        )

    @mcp.tool(name="discard_job")
    def discard_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Cancel preparation, delete private artifact staging, or reverse still-current live mutation targets. Terminal diagnostics need no discard."""
        return _result(lambda: service.discard_job(job_id, include_preview=include_preview))

    @mcp.tool(name="save_document")
    def save_document(
        document_id: str, destination: str | None = None
    ) -> dict[str, Any]:
        """Save one explicit Glyphs document without a dialog, or Save As to an absolute new .glyphs or .glyphspackage path. This saves the entire live document, never replaces a Save As destination, and refuses documents owned by an applied job; use accept_job for those."""
        return _result(
            lambda: service.save_document(document_id, destination=destination)
        )

    from .edit_workflow_ui import register_edit_workflow_tools
    register_edit_workflow_tools(mcp, service)
    mcp._glyphs_tool_names = TOOL_NAMES
    if control_token:
        from .management import register_routes
        register_routes(mcp, service, control_token)
    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default="http://127.0.0.1:9681")
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9680)
    parser.add_argument("--glyphs-cli")
    parser.add_argument("--glyphs-app")
    args = parser.parse_args(argv)
    token = load_or_create_token()
    service = SidecarService(
        BridgeClient(args.bridge, token),
        jobs=JobStore(args.jobs or Path.home() / "Library/Application Support/Glyphs MCP/lean-v2/jobs"),
        worker=GlyphsCliWorker(executable=args.glyphs_cli, app=args.glyphs_app),
    )
    service.lifecycle.control_lock = Path.home() / "Library/Application Support/Glyphs MCP/.control.lock"
    server = create_server(service, control_token=token)
    try:
        if args.transport == "http":
            # Jobs outlive individual stateless HTTP requests and sessions.
            server.run(transport="streamable-http", host=args.host, port=args.port,
                       path="/mcp/", stateless_http=True)
        else:
            server.run()
    finally:
        # FastMCP's MCP lifespan runs per request in stateless mode. Cleanup
        # belongs to the process lifetime, after the transport has stopped.
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
