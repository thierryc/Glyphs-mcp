"""Authenticated application management on the existing loopback listener."""
import asyncio
import hmac
import json

from starlette.responses import JSONResponse


def register_routes(mcp, service, token):
    def authorized(request):
        peer = request.client.host if request.client else ""
        supplied = request.headers.get("authorization", "")
        return peer in ("127.0.0.1", "::1") and hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode())

    async def respond(request, callback):
        if not authorized(request):
            return JSONResponse({"ok": False, "error": {"code": "unauthorized", "message": "Local authentication is required."}}, status_code=403)
        try:
            data = await asyncio.to_thread(callback)
            return JSONResponse({"ok": True, "data": data}, headers={"Cache-Control": "no-store"})
        except Exception as error:
            details = error.as_dict() if callable(getattr(error, "as_dict", None)) else {
                "code": "control_failed", "message": str(error)}
            return JSONResponse({"ok": False, "error": details}, status_code=409)

    @mcp.custom_route("/internal/status", methods=["GET"])
    async def status(request):
        return await respond(request, service.get_status)

    @mcp.custom_route("/internal/control", methods=["POST"])
    async def control(request):
        if not authorized(request):
            return await respond(request, lambda: None)
        try:
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 4096:
                    raise ValueError("Request is too large")
                body.extend(chunk)
            value = json.loads(body)
            action = value.get("action")
            if action == "reserve":
                callback = service.reserve_idle
            elif action == "release" and isinstance(value.get("reservationId"), str):
                callback = lambda: service.release_idle(value["reservationId"])
            else:
                raise ValueError("Unknown management action")
        except (ValueError, AttributeError):
            return JSONResponse({"ok": False, "error": {"code": "invalid_request", "message": "Invalid management action."}}, status_code=400)
        return await respond(request, callback)

    @mcp.custom_route('/internal/checkpoints', methods=['POST'])
    async def checkpoints(request):
        if not authorized(request):
            return await respond(request, lambda: None)
        try:
            body=bytearray()
            async for chunk in request.stream():
                if len(body)+len(chunk)>16384:raise ValueError('Request too large')
                body.extend(chunk)
            value=json.loads(body);action=value.pop('action')
            if action=='documents' and not value:
                callback=service.list_documents
            elif action=='read' and set(value)=={'document_id','selector'}:
                callback=lambda: service.read_entities(value['document_id'],[value['selector']],['checkpoint'])
            elif action=='restore' and set(value)=={'document_id','revision','idempotency_key'}:
                callback=lambda: service.edit_workflows.start(value['document_id'],kind='checkpoint_restore',options={'revision':value['revision']},idempotency_key=value['idempotency_key'],auto_keep=False)
            elif action=='workflow' and set(value)=={'workflow_id'}:
                callback=lambda: service.edit_workflows.get(value['workflow_id'])
            elif action=='respond' and set(value)=={'workflow_id','expected_revision','action_token'}:
                callback=lambda: service.edit_workflows.respond(value['workflow_id'],value['expected_revision'],value['action_token'])
            else:raise ValueError('Unknown checkpoint action')
        except (ValueError,KeyError,TypeError,AttributeError):
            return JSONResponse({'ok':False,'error':{'code':'invalid_request','message':'Invalid checkpoint request.'}},status_code=400)
        return await respond(request,callback)
