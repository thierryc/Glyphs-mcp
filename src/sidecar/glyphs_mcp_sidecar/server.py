"""FastMCP transport for the standalone seven-tool sidecar."""

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
        """Return sidecar, external worker, and live bridge availability."""
        return _result(service.get_status)

    @mcp.tool(name="list_documents")
    def list_documents() -> dict[str, Any]:
        """Discover open Glyphs documents once for the intended target. With document.context.v1, isCurrent is native current-font evidence (true/false, null if unavailable); never infer it from list order. Retain its document_id on this connection for subsequent fresh reads; rediscover after document_not_found or changed target intent."""
        return _result(service.list_documents)

    @mcp.tool(name="read_entities")
    def read_entities(
        document_id: str, entities: list[dict[str, Any]], fields: list[str]
    ) -> dict[str, Any]:
        """Read up to 100 explicit targets using a known document_id on this connection; no preceding list_documents is needed for the same target. Reads validate the live font and return fresh contents. Rediscover on document_not_found, not target_not_found (missing glyph/layer). Never substitute another font. Current/frontmost intent may require fresh targeting. document.context.v1 advertises one {kind: context} selector with requested fields view, master and selectedGlyphs. View is font/edit/unavailable; master is exact id/name or null. SelectedGlyphs returns native-order names, source, total/returned/limit/complete; optional glyphLimit 1-100 (default 100) requires selectedGlyphs. Do not mix context with other entities. Incomplete or unavailable selection is not an edit scope; narrow the selection. No implicit node details. If document.context.v1 is absent, update bridge, sidecar and skills together. With negotiated glyphs.list.v1, discover names using one {kind: glyphs, limit: 100} selector and fields [name]. Limit is 1-100; values includes items, total, returned, complete and opaque nextCursor. Pass that cursor unchanged in the next glyph selector. On stale_glyph_cursor or any observed edit, discard partial results and restart without a cursor. Guards check document, count, change signal and boundary; pages are live, not atomic. If the capability is missing, update bridge, sidecar and skills together. Known glyphs need no inventory. With negotiated layers.list.v1, use one {kind: layers, glyph: <name>, limit: 100} selector with requested fields id, name, associatedMasterId, isMasterLayer, isSpecialLayer, isBraceLayer and/or isBracketLayer. Native layer collection order; values includes items, total, returned, complete and opaque nextCursor. Limit 1-100 defaults to 100. Reuse the cursor only for the same glyph/document. On stale_layer_cursor or any observed edit, discard partial results and restart. Pages are live, not atomic; null optional fields mean unavailable evidence. Nested backgrounds are not separate entries; flags do not establish compatibility or special-layer groups. No geometry in this inventory. Exact returned IDs feed ordinary layer reads. If layers.list.v1 is missing, update bridge, sidecar and skills together. Master selectors require exact IDs. Layers use {kind: layer, glyph: name, id: nativeLayerId}; layer.read.exact.v1 advertises strict IDs and returned id=layerId. Layer fields: id, name, width, vertWidth, vertOrigin, leftMetricsKey, rightMetricsKey, widthMetricsKey, bounds, outlineHash. With masters.list.v1 in get_status bridge.readCapabilities, use one {kind: masters, limit: 100} selector and fields [id, name] to discover live masters; follow values.nextCursor until values.complete. Do not mix a master page with other selectors. Selection requires selection.context.v1 in get_status readCapabilities; if absent, the private installation needs its bridge, sidecar and skills updated together. Use {kind: selection}, requesting glyph, layer, selectedNodeCount, selectedAnchorCount, selectedComponentCount, selectedGuideCount and selectedOtherCount for a summary. Optional nodes returns items (x, y, type, smooth, pathIndex in layer.paths, nodeIndex in path.nodes), total, returned, limit and complete. Details require one selection entity only; optional nodeLimit is an integer 1-256, default 64, allowed only with nodes. Counts use native types, including off-curve GSNodes. Null glyph/layer and nodes=null mean no active Edit View; active empty details are complete with zero items. Dirty documents need no Save. Only requested fields are returned. With negotiated kerning.groups.v1, named glyph reads also support left/right/top/bottomKerningGroup and left/right/top/bottomKerningKey properties (for example rightKerningKey); only requested properties. Group names, lookup keys and raw storage IDs differ. With kerning.pairs.v1 use one {kind: kerning_pairs, master: exactId, direction: LTR, limit: 100} selector and fields left, right and/or value. Each side is {key: rawKey, glyph: resolvedNameOrNull, kind: group/glyph/unresolved}. Optional leftKey/rightKey filters use exact raw stored keys, not glyph names. Limit 1-100; values includes items, total: null (unavailable), returned, complete, nextCursor, scanned and scanLimit: 256. Work counts outer groups including misses and inner entries. Empty incomplete pages require continuation; pass the opaque cursor with the same master/direction/filters. Native indices resume without previous-page rescans. On stale_kerning_cursor or any observed edit, discard partial results and restart; bounded guards do not make live pages atomic. No effective kerning, jobs or saves. Missing private capabilities require coordinated installation update. Kerning uses {kind: kerning, master: <exact native master ID>, direction: LTR, left: A, right: V} with fields [value] only. Required direction is LTR, RTL or vertical (case-sensitive). Keys are glyph names or explicit stored @MMK_ group keys, not native glyph IDs. Return exact storage: null means no entry for those keys; zero is stored. This does not compute effective kerning through class/exception precedence. Dirty and unsaved live reads need no job or Save. Invalid master, glyph or direction returns invalid_request; keep the document ID and correct the input."""
        return _result(lambda: service.read_entities(document_id, entities, fields))

    @mcp.tool(name="start_job")
    def start_job(
        document_id: str,
        kind: str,
        delta: float | None = None,
        glyphs: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare width_delta, spacing, kerning_collision, start_nodes or slant outside Glyphs. Options select references, contours, explicit pairs, masters and optional straight-stem preservation; get_job reports evidence."""
        return _result(
            lambda: service.start_job(
                document_id, kind=kind, delta=delta, glyphs=glyphs, options=options
            )
        )

    @mcp.tool(name="get_job")
    def get_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Return job progress, counts, warnings and preview samples. Use include_preview=false for polling after reading the full report once; it omits both samples, retains report metadata and explicitly returns previewIncluded=false. The default includes previews."""
        return _result(lambda: service.get_job(job_id, include_preview=include_preview))

    @mcp.tool(name="apply_job")
    def apply_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Show the prepared result as a reversible live change; this is not acceptance. Use include_preview=false after reviewing the report to omit repeated samples."""
        return _result(lambda: service.apply_job(job_id, include_preview=include_preview))

    @mcp.tool(name="discard_job")
    def discard_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Cancel an unapplied job or reverse its still-current live targets. Use include_preview=false to omit repeated samples; errors and progress remain available."""
        return _result(lambda: service.discard_job(job_id, include_preview=include_preview))

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
