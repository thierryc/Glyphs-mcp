# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import ast
import asyncio
import contextlib
import io
import json
import traceback
from typing import Optional

try:
    import objc  # type: ignore[import-not-found]
    from Foundation import NSObject  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - depends on Glyphs runtime
    objc = None
    NSObject = None

from GlyphsApp import Glyphs, GSAnchor, GSComponent, GSGlyph, GSLayer, GSNode, GSPath  # type: ignore[import-not-found]

from mcp_tools import mcp


_SCRIPT_PAYLOAD_PREFIX = "__glyphs_mcp_payload__:"
_USER_CODE_FILENAME = "<glyphs-mcp-user-code>"


def _truncate(value: str, limit: Optional[int]) -> tuple[str, bool]:
    if limit is None:
        return value, False

    try:
        limit_int = int(limit)
    except Exception:
        return value, False

    if limit_int <= 0:
        return "", True if value else False
    if len(value) <= limit_int:
        return value, False

    # Keep the tail, which is usually the most useful part of a traceback.
    return value[-limit_int:], True


def _macro_panel_snippet(user_code: str) -> str:
    user_code = (user_code or "").rstrip()
    header = [
        "# Glyphs MCP - Macro Panel snippet (execute_code)",
        "# Paste into: Glyphs -> Window -> Macro Panel",
        "# Note: This snippet is NOT executed by the MCP tool when snippet_only=true.",
        "",
        "import json",
        "from GlyphsApp import Glyphs, GSGlyph, GSLayer, GSPath, GSNode, GSComponent, GSAnchor  # type: ignore",
        "",
        "# --- your code starts here ---",
    ]
    return "\n".join(header + [user_code, ""])


def _macro_panel_snippet_with_context(user_code: str, font_index: int, glyph_name: Optional[str]) -> str:
    glyph_literal = repr(glyph_name) if glyph_name is not None else "None"
    user_code = (user_code or "").rstrip()
    header = [
        "# Glyphs MCP - Macro Panel snippet (execute_code_with_context)",
        "# Paste into: Glyphs -> Window -> Macro Panel",
        "# Note: This snippet is NOT executed by the MCP tool when snippet_only=true.",
        "",
        "import json",
        "from GlyphsApp import Glyphs, GSGlyph, GSLayer, GSPath, GSNode, GSComponent, GSAnchor  # type: ignore",
        "",
        "font_index = {}".format(int(font_index)),
        "glyph_name = {}".format(glyph_literal),
        "master_id = None  # set to a specific master id string for more control",
        "",
        "font = Glyphs.fonts[font_index] if 0 <= font_index < len(Glyphs.fonts) else None",
        "glyph = font.glyphs[glyph_name] if (font is not None and glyph_name and font.glyphs[glyph_name]) else None",
        "layer = None",
        "if glyph is not None and font is not None:",
        "    if master_id:",
        "        layer = glyph.layers[master_id] if glyph.layers[master_id] else None",
        "    elif font.selectedFontMaster:",
        "        layer = glyph.layers[font.selectedFontMaster.id]",
        "    elif font.masters:",
        "        layer = glyph.layers[font.masters[0].id]",
        "",
        "print('Context:', {'font': getattr(font, 'familyName', None), 'glyph': getattr(glyph, 'name', None), 'layer': getattr(layer, 'name', None)})",
        "",
        "# --- your code starts here ---",
        user_code,
        "",
    ]
    return "\n".join(header)


def _namespace_base():
    return {
        "__builtins__": __builtins__,
        "Glyphs": Glyphs,
        "GSGlyph": GSGlyph,
        "GSLayer": GSLayer,
        "GSPath": GSPath,
        "GSNode": GSNode,
        "GSComponent": GSComponent,
        "GSAnchor": GSAnchor,
        "json": json,
        "print": print,
    }


def _compile_user_code(code: str, return_last_expression: bool):
    module_ast = ast.parse(code or "", filename="<string>", mode="exec")
    if not return_last_expression or not module_ast.body:
        return compile(module_ast, "<string>", "exec"), None

    last_stmt = module_ast.body[-1]
    if not isinstance(last_stmt, ast.Expr):
        return compile(module_ast, "<string>", "exec"), None

    exec_code = None
    prefix_body = module_ast.body[:-1]
    if prefix_body:
        prefix_module = ast.Module(body=prefix_body, type_ignores=[])
        ast.fix_missing_locations(prefix_module)
        exec_code = compile(prefix_module, "<string>", "exec")

    expr_module = ast.Expression(last_stmt.value)
    ast.fix_missing_locations(expr_module)
    expr_code = compile(expr_module, "<string>", "eval")
    return exec_code, expr_code


def _execute_code_payload(
    code: str,
    namespace: dict,
    *,
    capture_output: bool,
    return_last_expression: bool,
    max_output_chars: Optional[int],
    max_error_chars: Optional[int],
    system_exit_message: str,
    keyboard_interrupt_message: str,
    context_info: Optional[dict] = None,
) -> str:
    stdout_capture = io.StringIO() if capture_output else None
    stderr_capture = io.StringIO() if capture_output else None
    result = None
    error = None

    try:
        redirect_out = (
            contextlib.redirect_stdout(stdout_capture) if stdout_capture is not None else contextlib.nullcontext()
        )
        redirect_err = (
            contextlib.redirect_stderr(stderr_capture) if stderr_capture is not None else contextlib.nullcontext()
        )
        with redirect_out, redirect_err:
            exec_code, expr_code = _compile_user_code(code, return_last_expression)
            if exec_code is not None:
                exec(exec_code, namespace)
            if expr_code is not None:
                result = eval(expr_code, namespace)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        if isinstance(exc, SystemExit):
            error = system_exit_message.format(code=getattr(exc, "code", None))
        elif isinstance(exc, KeyboardInterrupt):
            error = keyboard_interrupt_message
        else:
            error = traceback.format_exc()

        error_output = stderr_capture.getvalue() if stderr_capture is not None else ""
        if error_output:
            error += "\n{}".format(error_output)

    output = stdout_capture.getvalue() if stdout_capture is not None else ""
    output, output_truncated = _truncate(output, max_output_chars)
    if error is not None:
        error, error_truncated = _truncate(error, max_error_chars)
    else:
        error_truncated = False

    response = {
        "success": error is None,
        "executed": True,
        "snippet": None,
        "output": output,
        "error": error,
        "result": str(result) if result is not None else None,
        "output_truncated": output_truncated,
        "error_truncated": error_truncated,
    }
    if context_info is not None:
        response["context"] = context_info
    return json.dumps(response)


def _source_offset(code: str, lineno: int, col_offset: int) -> int:
    if lineno <= 0:
        return 0

    lines = code.splitlines(True)
    if lineno > len(lines):
        return len(code)
    return sum(len(line) for line in lines[: lineno - 1]) + col_offset


def _split_user_code(code: str, return_last_expression: bool) -> tuple[str, Optional[str]]:
    user_code = code or ""
    if not return_last_expression:
        return user_code, None

    try:
        module_ast = ast.parse(user_code, filename=_USER_CODE_FILENAME, mode="exec")
    except SyntaxError:
        return user_code, None

    if not module_ast.body:
        return user_code, None

    last_stmt = module_ast.body[-1]
    if not isinstance(last_stmt, ast.Expr):
        return user_code, None

    expr_source = ast.get_source_segment(user_code, last_stmt.value)
    if not expr_source:
        return user_code, None

    start_offset = _source_offset(user_code, last_stmt.lineno, last_stmt.col_offset)
    exec_source = user_code[:start_offset]
    return exec_source, expr_source


def _context_setup_source(font_index: Optional[int], glyph_name: Optional[str]) -> str:
    if font_index is None:
        return ""

    return "\n".join(
        [
            "font_index = {}".format(int(font_index)),
            "glyph_name = {!r}".format(glyph_name),
            "font = Glyphs.fonts[font_index] if 0 <= font_index < len(Glyphs.fonts) else None",
            "glyph = font.glyphs[glyph_name] if (font is not None and glyph_name and font.glyphs[glyph_name]) else None",
            "layer = None",
            "if glyph is not None and font is not None:",
            "    if font.selectedFontMaster:",
            "        layer = glyph.layers[font.selectedFontMaster.id]",
            "    elif font.masters:",
            "        layer = glyph.layers[font.masters[0].id]",
        ]
    )


def _build_script_wrapper(
    code: str,
    *,
    return_last_expression: bool,
    font_index: Optional[int],
    glyph_name: Optional[str],
    system_exit_message: str,
    keyboard_interrupt_message: str,
) -> str:
    exec_source, expr_source = _split_user_code(code, return_last_expression)
    context_source = _context_setup_source(font_index, glyph_name)

    script_lines = [
        "import json",
        "import traceback",
        "from GlyphsApp import Glyphs, GSGlyph, GSLayer, GSPath, GSNode, GSComponent, GSAnchor  # type: ignore",
        "__glyphs_mcp_payload_prefix = {!r}".format(_SCRIPT_PAYLOAD_PREFIX),
        "__glyphs_mcp_exec_source = {!r}".format(exec_source),
        "__glyphs_mcp_expr_source = {!r}".format(expr_source),
        "__glyphs_mcp_result = None",
        "__glyphs_mcp_error = None",
    ]

    if context_source:
        script_lines.extend(["", context_source])

    script_lines.extend(
        [
            "",
            "try:",
            "    if __glyphs_mcp_exec_source:",
            "        exec(compile(__glyphs_mcp_exec_source, {!r}, 'exec'), globals(), globals())".format(
                _USER_CODE_FILENAME
            ),
            "    if __glyphs_mcp_expr_source is not None:",
            "        __glyphs_mcp_result = eval(compile(__glyphs_mcp_expr_source, {!r}, 'eval'), globals(), globals())".format(
                _USER_CODE_FILENAME
            ),
            "except BaseException as exc:",
            "    if isinstance(exc, SystemExit):",
            "        __glyphs_mcp_error = {}".format(repr(system_exit_message)).replace(
                "{code}", "{}"
            )
            + ".format(getattr(exc, 'code', None))",
            "    elif isinstance(exc, KeyboardInterrupt):",
            "        __glyphs_mcp_error = {!r}".format(keyboard_interrupt_message),
            "    else:",
            "        __glyphs_mcp_error = traceback.format_exc()",
            "",
            "print(",
            "    __glyphs_mcp_payload_prefix",
            "    + json.dumps(",
            "        {",
            "            'result': str(__glyphs_mcp_result) if __glyphs_mcp_result is not None else None,",
            "            'error': __glyphs_mcp_error,",
            "        }",
            "    )",
            ")",
            "",
        ]
    )
    return "\n".join(script_lines)


def _make_output_collector():
    if objc is not None and NSObject is not None:

        class _Collector(NSObject):  # type: ignore[misc,valid-type]
            def init(self):
                self = objc.super(_Collector, self).init()
                if self is None:
                    return None
                self.stdout_chunks = []
                self.stderr_chunks = []
                return self

            def setWrite_(self, text):
                self.stdout_chunks.append(str(text))

            def setWriteError_(self, text):
                self.stderr_chunks.append(str(text))

        return _Collector.alloc().init()

    class _Collector(object):
        def __init__(self):
            self.stdout_chunks = []
            self.stderr_chunks = []

        def setWrite_(self, text):
            self.stdout_chunks.append(str(text))

        def setWriteError_(self, text):
            self.stderr_chunks.append(str(text))

    return _Collector()


def _script_runner_available() -> bool:
    try:
        handler_getter = getattr(Glyphs, "scriptingHandler", None)
        if not callable(handler_getter):
            return False
        handler = handler_getter()
    except Exception:
        return False
    return handler is not None and hasattr(handler, "runMacroString_stdOut_")


def _run_script_via_glyphs(script: str) -> tuple[str, str]:
    collector = _make_output_collector()

    if objc is not None and NSObject is not None:

        class _ScriptRunner(NSObject):  # type: ignore[misc,valid-type]
            def init(self):
                self = objc.super(_ScriptRunner, self).init()
                if self is None:
                    return None
                self._script = script
                self._collector = collector
                self.error = None
                return self

            def runScript_(self, _obj):
                try:
                    handler = Glyphs.scriptingHandler()
                    if handler is None or not hasattr(handler, "runMacroString_stdOut_"):
                        raise RuntimeError("Glyphs scripting handler is unavailable.")
                    handler.runMacroString_stdOut_(self._script, self._collector)
                except Exception as exc:  # pragma: no cover - depends on Glyphs runtime
                    self.error = exc

        helper = _ScriptRunner.alloc().init()
        helper.performSelectorOnMainThread_withObject_waitUntilDone_("runScript:", None, True)
        if getattr(helper, "error", None) is not None:
            raise helper.error
    else:
        handler = Glyphs.scriptingHandler()
        if handler is None or not hasattr(handler, "runMacroString_stdOut_"):
            raise RuntimeError("Glyphs scripting handler is unavailable.")
        handler.runMacroString_stdOut_(script, collector)

    stdout_text = "".join(getattr(collector, "stdout_chunks", []))
    stderr_text = "".join(getattr(collector, "stderr_chunks", []))
    return stdout_text, stderr_text


def _extract_script_payload(stdout_text: str) -> tuple[str, Optional[dict]]:
    marker_index = stdout_text.rfind(_SCRIPT_PAYLOAD_PREFIX)
    if marker_index < 0:
        return stdout_text, None

    payload_text = stdout_text[marker_index + len(_SCRIPT_PAYLOAD_PREFIX) :]
    payload_line, _, trailing = payload_text.partition("\n")
    try:
        payload = json.loads(payload_line)
    except Exception:
        return stdout_text, None

    return stdout_text[:marker_index] + trailing, payload


def _execute_code_via_script_runner(
    code: str,
    *,
    capture_output: bool,
    return_last_expression: bool,
    max_output_chars: Optional[int],
    max_error_chars: Optional[int],
    system_exit_message: str,
    keyboard_interrupt_message: str,
    context_info: Optional[dict] = None,
    font_index: Optional[int] = None,
    glyph_name: Optional[str] = None,
) -> str:
    wrapper = _build_script_wrapper(
        code,
        return_last_expression=return_last_expression,
        font_index=font_index,
        glyph_name=glyph_name,
        system_exit_message=system_exit_message,
        keyboard_interrupt_message=keyboard_interrupt_message,
    )
    stdout_text, stderr_text = _run_script_via_glyphs(wrapper)
    user_output, payload = _extract_script_payload(stdout_text)

    error = None
    result = None
    if payload is None:
        error = "Glyphs script runner did not return a structured result."
    else:
        error = payload.get("error")
        result = payload.get("result")

    if stderr_text:
        if error:
            if stderr_text not in error:
                error = "{}\n{}".format(error, stderr_text)
        else:
            error = stderr_text

    if not capture_output:
        if user_output:
            print(user_output, end="")
        if stderr_text:
            print(stderr_text, end="")
        output = ""
    else:
        output = user_output

    output, output_truncated = _truncate(output, max_output_chars)
    if error is not None:
        error, error_truncated = _truncate(error, max_error_chars)
    else:
        error_truncated = False

    response = {
        "success": error is None,
        "executed": True,
        "snippet": None,
        "output": output,
        "error": error,
        "result": result,
        "output_truncated": output_truncated,
        "error_truncated": error_truncated,
    }
    if context_info is not None:
        response["context"] = context_info
    return json.dumps(response)


def _resolve_context_info(font_index: int, glyph_name: Optional[str]) -> dict:
    context_info = {}
    if len(Glyphs.fonts) <= font_index or font_index < 0:
        return context_info

    font = Glyphs.fonts[font_index]
    context_info["font"] = font.familyName

    if glyph_name and font.glyphs[glyph_name]:
        glyph = font.glyphs[glyph_name]
        context_info["glyph"] = glyph_name

        if font.selectedFontMaster:
            layer = glyph.layers[font.selectedFontMaster.id]
            context_info["layer"] = layer.name
        elif font.masters:
            layer = glyph.layers[font.masters[0].id]
            context_info["layer"] = layer.name

    return context_info


@mcp.tool()
async def execute_code(
    code: str,
    capture_output: bool = True,
    return_last_expression: bool = True,
    snippet_only: bool = False,
    max_output_chars: Optional[int] = None,
    max_error_chars: Optional[int] = None,
) -> str:
    """Execute Python code within the Glyphs environment with access to GlyphsApp API.

    Args:
        code (str): Python code to execute. Required.
        capture_output (bool): When true (default), capture stdout/stderr and return it in the response.
            When false, output is not captured (prints go to the Glyphs macro console) which can be faster for large jobs.
        return_last_expression (bool): When true (default), evaluate a terminal top-level expression once and return its result.
        snippet_only (bool): When true, do not execute. Return a ready-to-paste Macro Panel snippet containing the code.
        max_output_chars (int|None): Optional cap for returned stdout characters. When set, the output is truncated and a flag is returned.
        max_error_chars (int|None): Optional cap for returned error characters. When set, the error is truncated and a flag is returned.

    Returns:
        str: JSON-encoded result containing:
            success (bool): Whether the code executed successfully.
            executed (bool): Whether the snippet was actually executed (false when snippet_only=true).
            snippet (str|None): Macro Panel snippet when snippet_only=true.
            output (str): Standard output from the code execution.
            error (str): Error message if execution failed, including traceback details.
            result (any): The result of the last expression (if any).
            output_truncated (bool): Whether output was truncated due to max_output_chars.
            error_truncated (bool): Whether error was truncated due to max_error_chars.
    """
    try:
        if snippet_only:
            return json.dumps(
                {
                    "success": True,
                    "executed": False,
                    "snippet": _macro_panel_snippet(code),
                    "output": "",
                    "error": None,
                    "result": None,
                    "output_truncated": False,
                    "error_truncated": False,
                }
            )

        if _script_runner_available():
            return _execute_code_via_script_runner(
                code,
                capture_output=bool(capture_output),
                return_last_expression=bool(return_last_expression),
                max_output_chars=max_output_chars,
                max_error_chars=max_error_chars,
                system_exit_message="SystemExit is not allowed in execute_code (code={code}).",
                keyboard_interrupt_message="KeyboardInterrupt in execute_code.",
            )

        return _execute_code_payload(
            code,
            _namespace_base(),
            capture_output=bool(capture_output),
            return_last_expression=bool(return_last_expression),
            max_output_chars=max_output_chars,
            max_error_chars=max_error_chars,
            system_exit_message="SystemExit is not allowed in execute_code (code={code}).",
            keyboard_interrupt_message="KeyboardInterrupt in execute_code.",
        )
    except asyncio.CancelledError:
        raise
    except BaseException:
        return json.dumps(
            {
                "success": False,
                "executed": False,
                "snippet": None,
                "output": "",
                "error": "Code execution failed: {}".format(traceback.format_exc()),
                "result": None,
            }
        )


@mcp.tool()
async def execute_code_with_context(
    code: str,
    font_index: int = 0,
    glyph_name: str = None,
    capture_output: bool = True,
    return_last_expression: bool = True,
    snippet_only: bool = False,
    max_output_chars: Optional[int] = None,
    max_error_chars: Optional[int] = None,
) -> str:
    """Execute Python code with automatic context setup for a specific font and glyph.

    Args:
        code (str): Python code to execute. Required.
        font_index (int): Index of the font to work with. Defaults to 0.
        glyph_name (str): Name of the glyph to work with. Optional.
        capture_output (bool): When true (default), capture stdout/stderr and return it in the response.
            When false, output is not captured (prints go to the Glyphs macro console) which can be faster for large jobs.
        return_last_expression (bool): When true (default), evaluate a terminal top-level expression once and return its result.
        snippet_only (bool): When true, do not execute. Return a ready-to-paste Macro Panel snippet with context setup.
        max_output_chars (int|None): Optional cap for returned stdout characters. When set, the output is truncated and a flag is returned.
        max_error_chars (int|None): Optional cap for returned error characters. When set, the error is truncated and a flag is returned.

    Returns:
        str: JSON-encoded result containing:
            success (bool): Whether the code executed successfully.
            executed (bool): Whether the snippet was actually executed (false when snippet_only=true).
            snippet (str|None): Macro Panel snippet when snippet_only=true.
            output (str): Standard output from the code execution.
            error (str): Error message if execution failed, including traceback details.
            result (any): The result of the last expression (if any).
            context (dict): Information about the font and glyph context.
            output_truncated (bool): Whether output was truncated due to max_output_chars.
            error_truncated (bool): Whether error was truncated due to max_error_chars.
    """
    try:
        if snippet_only:
            return json.dumps(
                {
                    "success": True,
                    "executed": False,
                    "snippet": _macro_panel_snippet_with_context(code, font_index, glyph_name),
                    "output": "",
                    "error": None,
                    "result": None,
                    "context": {"font_index": font_index, "glyph_name": glyph_name},
                    "output_truncated": False,
                    "error_truncated": False,
                }
            )

        context_info = _resolve_context_info(font_index, glyph_name)

        if _script_runner_available():
            return _execute_code_via_script_runner(
                code,
                capture_output=bool(capture_output),
                return_last_expression=bool(return_last_expression),
                max_output_chars=max_output_chars,
                max_error_chars=max_error_chars,
                system_exit_message="SystemExit is not allowed in execute_code_with_context (code={code}).",
                keyboard_interrupt_message="KeyboardInterrupt in execute_code_with_context.",
                context_info=context_info,
                font_index=font_index,
                glyph_name=glyph_name,
            )

        font = None
        glyph = None
        layer = None
        if len(Glyphs.fonts) > font_index >= 0:
            font = Glyphs.fonts[font_index]
            if glyph_name and font.glyphs[glyph_name]:
                glyph = font.glyphs[glyph_name]
                if font.selectedFontMaster:
                    layer = glyph.layers[font.selectedFontMaster.id]
                elif font.masters:
                    layer = glyph.layers[font.masters[0].id]

        namespace = _namespace_base()
        namespace.update({"font": font, "glyph": glyph, "layer": layer})

        return _execute_code_payload(
            code,
            namespace,
            capture_output=bool(capture_output),
            return_last_expression=bool(return_last_expression),
            max_output_chars=max_output_chars,
            max_error_chars=max_error_chars,
            system_exit_message="SystemExit is not allowed in execute_code_with_context (code={code}).",
            keyboard_interrupt_message="KeyboardInterrupt in execute_code_with_context.",
            context_info=context_info,
        )
    except asyncio.CancelledError:
        raise
    except BaseException:
        return json.dumps(
            {
                "success": False,
                "executed": False,
                "snippet": None,
                "output": "",
                "error": "Code execution failed: {}".format(traceback.format_exc()),
                "result": None,
                "context": {},
            }
        )
