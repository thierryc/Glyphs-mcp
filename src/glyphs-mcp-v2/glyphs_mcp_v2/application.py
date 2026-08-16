"""Read-only Glyphs MCP 2.0 application services."""

from __future__ import annotations

from typing import Callable, Dict

from .contracts import API_MAJOR, API_VERSION, ToolError, ToolResponse
from .ports import HostAccessError, ReadOnlyHost
from .versions import SERVER_NAME, SERVER_VERSION


class ReadOnlyApplication:
    def __init__(self, host: ReadOnlyHost) -> None:
        self._host = host
        self._handlers: Dict[str, Callable[[], ToolResponse]] = {
            "get_server_info": self.get_server_info,
            "list_open_fonts": self.list_open_fonts,
        }

    def invoke(self, handler_name: str) -> ToolResponse:
        handler = self._handlers.get(handler_name)
        if handler is None:
            return ToolResponse.failure(
                tool=handler_name or "unknown",
                effect="read",
                summary="Unknown Glyphs MCP 2.0 operation.",
                error=ToolError(
                    code="unknown_tool",
                    message="The requested operation is not part of this runtime.",
                    recoverable=False,
                ),
            )
        try:
            return handler()
        except HostAccessError as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect="read",
                summary="Glyphs host state is temporarily unavailable.",
                error=ToolError(
                    code="host_unavailable",
                    message=str(exc) or "Glyphs host state is unavailable.",
                    recoverable=True,
                ),
            )
        except Exception as exc:
            return ToolResponse.failure(
                tool=handler_name,
                effect="read",
                summary="The read-only operation failed safely.",
                error=ToolError(
                    code="internal_error",
                    message="The operation failed before returning host state.",
                    recoverable=True,
                    details={"exceptionType": type(exc).__name__},
                ),
            )

    def get_server_info(self) -> ToolResponse:
        runtime = self._host.runtime_snapshot()
        return ToolResponse.success(
            tool="get_server_info",
            effect="read",
            summary="Glyphs MCP {} is available with {} open document(s).".format(
                API_VERSION,
                runtime.open_document_count,
            ),
            data={
                "serverName": SERVER_NAME,
                "serverVersion": SERVER_VERSION,
                "apiMajor": API_MAJOR,
                "apiVersion": API_VERSION,
                "capabilities": ["read_only_v2_spine", "stable_document_ids"],
                "host": runtime.to_dict(),
            },
        )

    def list_open_fonts(self) -> ToolResponse:
        documents = tuple(self._host.list_documents())
        return ToolResponse.success(
            tool="list_open_fonts",
            effect="read",
            summary="Found {} open Glyphs document(s).".format(len(documents)),
            data={
                "count": len(documents),
                "documents": [document.to_dict() for document in documents],
            },
        )


__all__ = ["ReadOnlyApplication"]
