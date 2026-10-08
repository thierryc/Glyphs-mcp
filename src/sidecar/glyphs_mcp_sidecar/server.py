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

    @mcp.tool(name="create_document")
    def create_document(family_name: str, idempotency_key: str, units_per_em: int = 1000) -> dict[str, Any]:
        """With font-creation authorization, create and open a new unsaved Glyphs font with one Regular master and one Regular instance; no existing document is required. Requires document.create.v1. family_name is 1-255 characters; units_per_em is an integer from 16 to 16384 (default 1000). Return its id for subsequent reads/edits/save_document, plus native masterIds and instanceIds. Creation never saves. Save As uses save_document with separate existing/explicit save authorization and a new absolute .glyphs or .glyphspackage destination. Retain a fresh idempotency_key per intended font and retry exactly the same arguments after a timeout. A reused key with different arguments conflicts; a closed created document is not recreated. After a bridge restart, creation_outcome_unknown requires reconciliation of the original font rather than another creation request. No saved baseline or edit workflow is required."""
        return _result(lambda: service.create_document(family_name, idempotency_key, units_per_em))

    @mcp.tool(name="open_document")
    def open_document(path: str, idempotency_key: str) -> dict[str, Any]:
        """With file-opening authorization, open an existing absolute local .glyphs file or .glyphspackage folder in Glyphs 4. Requires document.open.v1; no existing document, saved baseline or script is needed. Reuse an already-open source without reloading, saving, discarding unsaved edits or duplicating its document. Return its id, path, familyName, dirty, generation, alreadyOpen, openId and bridgeSessionId; retain id for subsequent reads/edits/save_document. Opening never saves or closes another font. Use a fresh retained idempotency_key per intended Open and retry identical arguments after a timeout. A changed path conflicts; a closed result is not reopened by a retry. After a bridge restart, opening_outcome_unknown requires reconciling the original document. Missing paths and non-native formats reject; binary/UFO import is separate. A partial native failure may return documentId in error details; inspect it without repeating Open."""
        return _result(lambda: service.open_document(path, idempotency_key))

    @mcp.tool(name="import_document")
    def import_document(path: str, idempotency_key: str) -> dict[str, Any]:
        """Import an absolute local .ufo folder, .otf file or .ttf file through Glyphs. No open font is required. Reuse the same key after lost responses; never replay an uncertain import with a new key. Import never saves or overwrites its source. Compiled fonts are view-only until Save As to a new .glyphs/.glyphspackage source, and can lose hinting or OpenType tables. Use the returned exact document ID."""
        return _result(lambda: service.import_document(path, idempotency_key))

    @mcp.tool(name="activate_document")
    def activate_document(document_id: str) -> dict[str, Any]:
        """Show the window for an exact live document ID and bring Glyphs to the front. Resolve IDs with list_documents; never substitute the current font. Repeated activation is safe and never reopens a closed font. Does not change outlines, save or resolve jobs."""
        return _result(lambda: service.activate_document(document_id))

    @mcp.tool(name="close_document")
    def close_document(document_id: str, idempotency_key: str, unsaved_changes: str = "refuse", destination: str | None = None) -> dict[str, Any]:
        """Close an exact live font with explicit unsaved handling: refuse (default), save, or discard. Discard requires the user's explicit authorization to lose all unsaved edits in this font. Save verifies the native save and file hash first; pathless/imported fonts require a new .glyphs/.glyphspackage destination. Failure leaves the font open. Active, ready, applied or unresolved jobs block Close; resolve their existing lifecycle first. Cancel means do not call this tool. Reuse the same key and options after lost responses; a stale font requires renewed review before a new key. Never closes another font or prompts through a modal dialog."""
        return _result(lambda: service.close_document(document_id, idempotency_key, unsaved_changes, destination))

    @mcp.tool(name="read_entities")
    def read_entities(
        document_id: str, entities: list[dict[str, Any]], fields: list[str]
    ) -> dict[str, Any]:
        """Read fresh, bounded evidence for a known document_id. Dirty and unsaved fonts need no Save. Request 1-100 entities and 1-32 fields. Reuse the binding; rediscover on document_not_found, not target_not_found. Never substitute another font. Check get_status readCapabilities; missing support requires a coordinated installation update.

        Exact selectors: {kind:glyph,id:name}; {kind:layer,glyph:name,id:nativeLayerId}; {kind:master,id:exactId}. Layers require layer.read.exact.v1; fields include id/name, width/vertWidth/vertOrigin, left/right/widthMetricsKey, bounds and outlineHash. Glyphs support name/unicode/category/subCategory/export/color (0-11 or null), plus left/right/top/bottomKerningGroup and KerningKey with kerning.groups.v1. Group names, lookup keys and raw storage IDs differ. Master properties (master.properties.v1): id/name, ascender/capHeight/xHeight/descender/italicAngle/axes. Axes are native-order internal/external values, at most 32 per master and 256 master-axis items per request; incomplete/null means unavailable. Dimensions: master.dimensions.read.v1, 1-4 exact masters, fields [dimensions]; persisted reference notes, zero is set, no outline measurement.

        Inventories require one sole selector {kind:glyphs|masters|layers,limit:100,cursor:opaque}; layers also requires glyph. Capabilities: glyphs.list.v1, masters.list.v1, layers.list.v1. Fields: glyphs [name]; masters requested master properties except dimensions; layers id/name/associatedMasterId/isMasterLayer/isSpecialLayer/isBraceLayer/isBracketLayer. Page limit 1-100; follow values.nextCursor until complete. Keep document/selector unchanged. On stale cursor errors or observed edits, discard partial results and restart. Pages are live, not atomic; known targets need no inventory.

        Context (document.context.v1): sole {kind:context,glyphLimit:100}, fields view/master/selectedGlyphs. Native selection order; incomplete/unavailable selection is not an edit scope. Selection (selection.context.v1): {kind:selection}, fields glyph/layer, selectedNodeCount/selectedAnchorCount/selectedComponentCount/selectedGuideCount/selectedOtherCount. Optional nodes requires a sole selector with nodeLimit 1-256 (default 64); items include x/y/type/smooth/pathIndex/nodeIndex, counts and completeness. No implicit node details.

        Kerning uses {kind:kerning,master:<exact native master ID>,direction:LTR,left:A,right:V}, fields [value] only. Direction is LTR, RTL or vertical. Keys are glyph names or stored @MMK_ keys; null means no entry, zero is stored. This is exact storage, not effective class/exception kerning. With kerning.proof.v1, sole {kind:kerning_proof,master,direction,languages:[en,fr],limit:100,cursor?}, fields [pairs], returns language-tagged pairs to inspect, bounded proof strings and existing group/exception coverage. Mapping and candidate scans are each bounded at 256 per read; follow nextCursor even on empty mapping pages. Primary Unicode only; ambiguous mappings are skipped. Native effective status may be unknown. No suggestions, shaping, assignments or collision analysis. With kerning.pairs.v1, sole {kind:kerning_pairs,master,direction,limit:100,leftKey?,rightKey?,cursor?}, fields left/right/value, pages raw keys and resolved names. Filters are exact raw keys. Scan budget 256; empty incomplete pages still require continuation; total may be null.

        Paths require paths.list.v1/path.geometry.v1: sole {kind:paths,glyph,layer,limit?,cursor?} with fields [items]; {kind:path,glyph,layer,index,limit?,cursor?} with fields [nodes]; or {kind:segment,glyph,layer,path,endNode} with type/startNode/endNode/controlNodes/points/length/pathHash. Path/node limits 100/256. outline.background.read.v1 allows surface:background on layer/path selectors; IDs identify the owning foreground layer. Never substitute foreground geometry or create missing backgrounds.

        With features.read.v1, sole {kind:feature_blocks,blockType:prefix|class|feature,limit:100,cursor?}, fields [items], or exact {kind:feature_block,blockType,id}. With instances.read.v1, sole {kind:instances,limit:100,cursor?}, fields [items], or exact {kind:instance,id}; returned persistent IDs feed export jobs. With font.checkpoints.v1, fields [checkpoint] and one checkpoint_history/checkpoint_details/checkpoint_compare/checkpoint_scope selector read bounded Git evidence using full revisions/cursors. Invalid selector input returns invalid_request; keep the document binding and correct the input. Full selectors/fields: shipped Glyphs references and the eighteen-tool command reference."""
        return _result(lambda: service.read_entities(document_id, entities, fields))

    @mcp.tool(name="start_job")
    def start_job(
        document_id: str,
        kind: str,
        delta: float | None = None,
        glyphs: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare a low-level job without applying or saving. Prefer start_edit_workflow for conversation edits. Typed kinds: width_delta (delta and optional glyphs), spacing, kerning_edit, kerning_collision, start_nodes, slant, outline_edit, dimensions_edit and native_action. Use negotiated jobCapabilities for feature_compile diagnostic or font_export artifact jobs; analysis/export retain external processing. python_script requires script.native.v1 and start_edit_workflow; it cannot start here.

        Use typed options and exact targets. outline_edit supports surface:background only with outline.background.edit.v1; layer/reference IDs identify owning foregrounds. native_action uses only get_status.nativeActions: e.g. options={action:set_glyph_color,arguments:{color:orange},targets:[{glyph:A}]}; color:none clears. dimensions_edit requires master.dimensions.edit.v1 and options.changes of 1-100 {master,key,value} entries (number or null to clear), without delta/glyphs. Inspect full report.targets/requiredOverwrites; existing-value overwrites or clears require conversational approval.

        Mutation preparation requires a saved clean font. Application remains separate and never saves. checkpoint_restore, with font.checkpoint-restore.v1 and options={revision:full_revision}, prepares a whole-font historical reload; applying replaces later unsaved edits and clears Undo, returning a fresh binding without saving. Retain job_id and reconcile after timeouts; never replace an uncertain operation.        kerning_edit requires kerning.edit.exact.v1 and uses options.edits (1-100). Each entry has op=set|remove, exact master, direction=LTR|RTL|vertical, left/right={kind:glyph,name:...}|{kind:group,key:...}; only set takes finite value, including zero. No top-level glyphs/delta. Native preparation needs no source copy or external worker. Reuses guarded application and selective Undo; no collision analysis."""
        return _result(
            lambda: service.start_job(
                document_id, kind=kind, delta=delta, glyphs=glyphs, options=options
            )
        )

    @mcp.tool(name="compare_fonts")
    def compare_fonts(baseline_files: list[str], candidate_files: list[str], options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Compare explicit local static/variable TTF files with the optional managed Diffenator runtime. Requires font.compare.diffenator.v1 in get_status.comparisonCapabilities. No live Glyphs document or Save is required. Each list contains 1-32 absolute existing TTF paths. options: styles=instances (default), masters or cross_product; filterStyles=style regex; userWordlist=absolute .txt/.csv file. Inputs are privately snapshotted and hashed. Return a job ID; use get_job for stages/HTML entry point, discard_job for cancellation and accept_job with a new destination directory to publish the report. Comparison never applies changes or saves fonts. Completion is not a judgement that differences are acceptable."""
        return _result(lambda: service.compare_fonts(baseline_files, candidate_files, options))

    @mcp.tool(name="get_job")
    def get_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Return progress and a typed mutation, diagnostic or artifact result with report, manifest, warnings and bounded previews. Use include_preview=false for compact polling."""
        return _result(lambda: service.get_job(job_id, include_preview=include_preview))

    @mcp.tool(name="apply_job")
    def apply_job(job_id: str, include_preview: bool = True, approved_overwrites: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Apply mutation jobs only; diagnostic or artifact results cannot be applied. This is not acceptance and never saves. Typed application verifies guarded targets and retains selective Undo. checkpoint_restore replaces the whole font, later unsaved edits and Undo history.

        Dimensions blank fills need no confirmation. Before overwriting/clearing existing values, show every master/field and exact old/new value and obtain explicit conversational approval. Then pass exact report.requiredOverwrites as approved_overwrites. This records assistant-reported approval, not authenticated consent. Mixed batches wait together; prepare a reduced job for declined changes."""
        return _result(lambda: service.apply_job(job_id, include_preview=include_preview, approved_overwrites=approved_overwrites))

    @mcp.tool(name="accept_job")
    def accept_job(
        job_id: str,
        destination: str | None = None,
        include_preview: bool = True,
    ) -> dict[str, Any]:
        """With save authorization, verify an applied mutation and save the whole font (including later edits), ending workflow recovery. Optional destination is an absolute new Save As path and must not exist. Native Undo remains. For artifact jobs, publish verified export or compiled-font comparison artifacts to a new absolute destination directory. Return source-bound receipts; reconcile uncertain outcomes instead of replaying."""
        return _result(
            lambda: service.accept_job(
                job_id,
                destination=destination,
                include_preview=include_preview,
            )
        )

    @mcp.tool(name="discard_job")
    def discard_job(job_id: str, include_preview: bool = True) -> dict[str, Any]:
        """Cancel preparation, delete private artifact staging, or selectively undo a still-current typed mutation. Conflicting later edits reject recovery. Terminal diagnostics need no discard. Script Keep/Restore and historical restore results use their original conversation workflow."""
        return _result(lambda: service.discard_job(job_id, include_preview=include_preview))

    @mcp.tool(name="save_document")
    def save_document(
        document_id: str, destination: str | None = None, retry_checkpoint_job_id: str | None = None
    ) -> dict[str, Any]:
        """With explicit or existing save authorization, save one document's whole live contents without a dialog. Optional destination is an absolute new .glyphs or .glyphspackage Save As path; never overwrite a Save As destination. Applied-job owners require accept_job or their workflow Save action. With font.checkpoints.v1, enabled projects create a local checkpoint after verified Save. Git failure does not undo the Save; retry_checkpoint_job_id retries only that recorded checkpoint and never saves again."""
        return _result(
            lambda: service.save_document(document_id, destination=destination, retry_checkpoint_job_id=retry_checkpoint_job_id)
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
