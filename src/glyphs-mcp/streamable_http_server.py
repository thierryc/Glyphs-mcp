# streamable_http_server.py
import asyncio
import json
import uuid
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from aiohttp import web, WSMsgType
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from fastmcp import FastMCP
import logging

logger = logging.getLogger(__name__)

class StreamableHTTPServer:
    """MCP Streamable HTTP server implementation following the specification."""
    
    def __init__(self, mcp_server: FastMCP, host: str = "127.0.0.1", port: int = 9680):
        self.mcp_server = mcp_server
        self.host = host
        self.port = port
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
    def _validate_origin(self, request: Request) -> bool:
        """Validate Origin header to prevent DNS rebinding attacks."""
        origin = request.headers.get('Origin')
        if not origin:
            return True  # Allow requests without Origin header
            
        parsed = urlparse(origin)
        # Allow localhost origins for local development
        if parsed.hostname in ['127.0.0.1', 'localhost']:
            return True
            
        # For production, implement stricter validation
        # Allow specific origins based on configuration
        return False
        
    def _get_session_id(self, request: Request) -> str:
        """Get or create session ID from Mcp-Session-Id header."""
        session_id = request.headers.get('Mcp-Session-Id')
        if not session_id:
            session_id = str(uuid.uuid4())
            
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'created_at': asyncio.get_event_loop().time(),
                'last_event_id': 0
            }
            
        return session_id
        
    def _format_sse_event(self, data: Dict[str, Any], event_id: Optional[int] = None) -> str:
        """Format data as Server-Sent Events."""
        lines = []
        if event_id is not None:
            lines.append(f"id: {event_id}")
        lines.append(f"data: {json.dumps(data)}")
        lines.append("")  # Empty line terminates the event
        return "\n".join(lines)
        
    async def _handle_mcp_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP request using the FastMCP server."""
        try:
            # Convert to MCP format and process
            method = request_data.get('method')
            params = request_data.get('params', {})
            
            if method == 'tools/list':
                # List available tools
                tools = []
                for tool_name, tool_func in self.mcp_server._tools.items():
                    tools.append({
                        'name': tool_name,
                        'description': tool_func.__doc__ or f"Tool: {tool_name}",
                        'inputSchema': {
                            'type': 'object',
                            'properties': {},
                            'required': []
                        }
                    })
                return {
                    'jsonrpc': '2.0',
                    'id': request_data.get('id'),
                    'result': {'tools': tools}
                }
            elif method == 'tools/call':
                # Call a specific tool
                tool_name = params.get('name')
                arguments = params.get('arguments', {})
                
                if tool_name in self.mcp_server._tools:
                    tool_func = self.mcp_server._tools[tool_name]
                    result = await tool_func(**arguments)
                    return {
                        'jsonrpc': '2.0',
                        'id': request_data.get('id'),
                        'result': {
                            'content': [
                                {
                                    'type': 'text',
                                    'text': result
                                }
                            ]
                        }
                    }
                else:
                    return {
                        'jsonrpc': '2.0',
                        'id': request_data.get('id'),
                        'error': {
                            'code': -32601,
                            'message': f'Tool not found: {tool_name}'
                        }
                    }
            else:
                return {
                    'jsonrpc': '2.0',
                    'id': request_data.get('id'),
                    'error': {
                        'code': -32601,
                        'message': f'Method not found: {method}'
                    }
                }
        except Exception as e:
            logger.error(f"Error processing MCP request: {e}")
            return {
                'jsonrpc': '2.0',
                'id': request_data.get('id'),
                'error': {
                    'code': -32603,
                    'message': f'Internal error: {str(e)}'
                }
            }
    
    async def handle_request(self, request: Request) -> Response:
        """Handle incoming HTTP requests according to MCP Streamable HTTP spec."""
        
        # 1. Validate Origin header for security
        if not self._validate_origin(request):
            return web.Response(
                status=403,
                text="Forbidden: Invalid origin"
            )
        
        # 2. Get session ID
        session_id = self._get_session_id(request)
        
        # 3. Check Accept header
        accept_header = request.headers.get('Accept', '')
        wants_sse = 'text/event-stream' in accept_header
        wants_json = 'application/json' in accept_header
        
        if request.method == 'GET':
            # Handle SSE connection
            if wants_sse:
                return await self._handle_sse_connection(request, session_id)
            else:
                return web.Response(
                    status=400,
                    text="GET requests must accept text/event-stream"
                )
        
        elif request.method == 'POST':
            raw_body = await request.text()
            safe_headers = {
                key: value
                for key, value in request.headers.items()
                if key.lower() in {"accept", "content-type", "mcp-session-id", "last-event-id"}
            }
            payload_snippet_limit = 1024
            payload_snippet = raw_body[:payload_snippet_limit]
            if len(raw_body) > payload_snippet_limit:
                payload_snippet += "... [truncated]"
            
            if not raw_body.strip():
                detail = {
                    "error": "Missing JSON payload",
                    "details": {
                        "contentType": request.content_type,
                        "accept": request.headers.get("Accept"),
                        "reason": "Request body is empty or whitespace."
                    }
                }
                logger.warning("Empty POST body for %s; headers=%s", request.path_qs, safe_headers)
                return web.json_response(detail, status=400)
            
            try:
                body = json.loads(raw_body)
            except json.JSONDecodeError as decode_error:
                detail = {
                    "error": "Invalid JSON payload",
                    "details": {
                        "message": str(decode_error),
                        "line": decode_error.lineno,
                        "column": decode_error.colno,
                        "position": decode_error.pos,
                        "contentType": request.content_type,
                        "accept": request.headers.get("Accept"),
                        "payloadSnippet": payload_snippet
                    }
                }
                logger.warning(
                    "Invalid JSON for POST %s: %s; headers=%s",
                    request.path_qs,
                    detail["details"],
                    safe_headers,
                )
                return web.json_response(detail, status=400)
            except Exception as e:
                logger.error(f"Unexpected error decoding POST body: {e}")
                return web.Response(
                    status=500,
                    text=f"Internal server error: {str(e)}"
                )
            
            try:
                # Handle single request or batch
                if isinstance(body, list):
                    # Batch request
                    responses = []
                    for item in body:
                        response = await self._handle_mcp_request(item)
                        responses.append(response)
                    
                    if wants_sse:
                        return await self._send_sse_responses(responses, session_id)
                    else:
                        return web.json_response(responses)
                elif isinstance(body, dict):
                    # Single request
                    response = await self._handle_mcp_request(body)
                    
                    if wants_sse:
                        return await self._send_sse_responses([response], session_id)
                    else:
                        return web.json_response(response)
                else:
                    detail = {
                        "error": "Unsupported JSON payload type",
                        "details": {
                            "receivedType": type(body).__name__,
                            "expected": "object or array",
                            "accept": request.headers.get("Accept"),
                            "payloadSnippet": payload_snippet
                        }
                    }
                    logger.warning("Unsupported JSON type for POST %s: %s", request.path_qs, detail["details"])
                    return web.json_response(detail, status=400)
                        
            except Exception as e:
                logger.error(f"Error handling POST request: {e}")
                return web.Response(
                    status=500,
                    text=f"Internal server error: {str(e)}"
                )
        
        else:
            return web.Response(
                status=405,
                text="Method not allowed"
            )
    
    async def _handle_sse_connection(self, request: Request, session_id: str) -> Response:
        """Handle Server-Sent Events connection."""
        response = web.StreamResponse()
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Mcp-Session-Id'] = session_id
        
        await response.prepare(request)
        
        # Send initial connection event
        event_data = {
            'type': 'connection',
            'sessionId': session_id,
            'timestamp': asyncio.get_event_loop().time()
        }
        await response.write(self._format_sse_event(event_data, 1).encode())
        
        # Keep connection alive
        try:
            while True:
                await asyncio.sleep(30)  # Send keepalive every 30 seconds
                keepalive_data = {
                    'type': 'keepalive',
                    'timestamp': asyncio.get_event_loop().time()
                }
                await response.write(self._format_sse_event(keepalive_data).encode())
        except Exception as e:
            logger.error(f"SSE connection error: {e}")
        
        return response
    
    async def _send_sse_responses(self, responses: List[Dict[str, Any]], session_id: str) -> Response:
        """Send responses as Server-Sent Events."""
        response = web.StreamResponse()
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Mcp-Session-Id'] = session_id
        
        await response.prepare(request)
        
        session = self.sessions[session_id]
        
        for response_data in responses:
            session['last_event_id'] += 1
            event_id = session['last_event_id']
            
            sse_data = self._format_sse_event(response_data, event_id)
            await response.write(sse_data.encode())
        
        # Send end event
        end_event = self._format_sse_event({'type': 'end'})
        await response.write(end_event.encode())
        
        return response
    
    async def start_server(self):
        """Start the HTTP server."""
        app = web.Application()
        
        # Add routes - use root path for simplicity
        app.router.add_route('*', '/', self.handle_request)
        
        # Add CORS headers
        async def add_cors_headers(request, handler):
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Origin, Accept, Mcp-Session-Id, Last-Event-ID'
            return response
        
        app.middlewares.append(add_cors_headers)
        
        # Handle preflight requests
        async def handle_options(request):
            return web.Response(
                status=200,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Origin, Accept, Mcp-Session-Id, Last-Event-ID'
                }
            )
        
        app.router.add_route('OPTIONS', '/{path:.*}', handle_options)
        
        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"MCP Streamable HTTP server started on {self.host}:{self.port}")
        return runner
