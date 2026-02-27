# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import json
import io
import contextlib
import asyncio
import traceback
from typing import Optional
from GlyphsApp import Glyphs, GSGlyph, GSLayer, GSPath, GSNode, GSComponent, GSAnchor # type: ignore[import-not-found]

from mcp_tools import mcp


@mcp.tool()
async def execute_code(
    code: str,
    timeout: int = 60,
    capture_output: bool = True,
    return_last_expression: bool = True,
    max_output_chars: Optional[int] = None,
    max_error_chars: Optional[int] = None,
) -> str:
    """Execute Python code within the Glyphs environment with access to GlyphsApp API.
    
    Args:
        code (str): Python code to execute. Required.
        timeout (int): Maximum execution time in seconds. Defaults to 60. The bridge enforces the same limit per request.
        capture_output (bool): When true (default), capture stdout/stderr and return it in the response.
            When false, output is not captured (prints go to the Glyphs macro console) which can be faster for large jobs.
        return_last_expression (bool): When true (default), attempt to evaluate the last line as an expression and return it.
        max_output_chars (int|None): Optional cap for returned stdout characters. When set, the output is truncated and a flag is returned.
        max_error_chars (int|None): Optional cap for returned error characters. When set, the error is truncated and a flag is returned.
    
    Returns:
        str: JSON-encoded result containing:
            success (bool): Whether the code executed successfully.
            output (str): Standard output from the code execution.
            error (str): Error message if execution failed, including traceback details.
            result (any): The result of the last expression (if any).
            output_truncated (bool): Whether output was truncated due to max_output_chars.
            error_truncated (bool): Whether error was truncated due to max_error_chars.
    """

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
        # Keep the tail (usually more useful for tracebacks) and mark as truncated.
        return value[-limit_int:], True

    try:
        # Create a custom namespace with access to Glyphs API
        namespace = {
            '__builtins__': __builtins__,
            'Glyphs': Glyphs,
            'GSGlyph': GSGlyph,
            'GSLayer': GSLayer,
            'GSPath': GSPath,
            'GSNode': GSNode,
            'GSComponent': GSComponent,
            'GSAnchor': GSAnchor,
            'json': json,
            'print': print,
        }
        
        # Capture stdout and stderr (optional; avoid overhead for large jobs)
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
                # Try to compile the code first
                try:
                    compiled_code = compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    # If it fails as exec, try as eval for single expressions
                    try:
                        compiled_code = compile(code, '<string>', 'eval')
                        result = eval(compiled_code, namespace)
                    except Exception:
                        raise e
                else:
                    # Execute the compiled code
                    exec(compiled_code, namespace)
                    
                    # Try to get the result of the last expression if it exists
                    if return_last_expression:
                        lines = code.strip().split('\n')
                        if lines:
                            last_line = lines[-1].strip()
                            if last_line and not last_line.startswith(('print', 'import', 'from', 'def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'except:', 'finally:', 'with ')):
                                try:
                                    result = eval(last_line, namespace)
                                except:
                                    pass  # Ignore errors when trying to evaluate the last line
        
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            if isinstance(e, SystemExit):
                code_value = getattr(e, "code", None)
                error = "SystemExit is not allowed in execute_code (code={}).".format(code_value)
            elif isinstance(e, KeyboardInterrupt):
                error = "KeyboardInterrupt in execute_code."
            else:
                error = traceback.format_exc()
            error_output = stderr_capture.getvalue() if stderr_capture is not None else ""
            if error_output:
                error += f"\n{error_output}"
        
        # Get captured output
        output = stdout_capture.getvalue() if stdout_capture is not None else ""
        output, output_truncated = _truncate(output, max_output_chars)
        if error is not None:
            error, error_truncated = _truncate(error, max_error_chars)
        else:
            error_truncated = False
        
        # Prepare result
        response = {
            "success": error is None,
            "output": output,
            "error": error,
            "result": str(result) if result is not None else None,
            "output_truncated": output_truncated,
            "error_truncated": error_truncated,
        }
        
        return json.dumps(response)
        
    except asyncio.CancelledError:
        raise
    except BaseException:
        return json.dumps({
            "success": False,
            "output": "",
            "error": f"Code execution failed: {traceback.format_exc()}",
            "result": None
        })


@mcp.tool()
async def execute_code_with_context(
    code: str,
    font_index: int = 0,
    glyph_name: str = None,
    timeout: int = 60,
    capture_output: bool = True,
    return_last_expression: bool = True,
    max_output_chars: Optional[int] = None,
    max_error_chars: Optional[int] = None,
) -> str:
    """Execute Python code with automatic context setup for a specific font and glyph.
    
    Args:
        code (str): Python code to execute. Required.
        font_index (int): Index of the font to work with. Defaults to 0.
        glyph_name (str): Name of the glyph to work with. Optional.
        timeout (int): Maximum execution time in seconds. Defaults to 60. The bridge honours the same per-call limit.
        capture_output (bool): When true (default), capture stdout/stderr and return it in the response.
            When false, output is not captured (prints go to the Glyphs macro console) which can be faster for large jobs.
        return_last_expression (bool): When true (default), attempt to evaluate the last line as an expression and return it.
        max_output_chars (int|None): Optional cap for returned stdout characters. When set, the output is truncated and a flag is returned.
        max_error_chars (int|None): Optional cap for returned error characters. When set, the error is truncated and a flag is returned.
    
    Returns:
        str: JSON-encoded result containing:
            success (bool): Whether the code executed successfully.
            output (str): Standard output from the code execution.
            error (str): Error message if execution failed, including traceback details.
            result (any): The result of the last expression (if any).
            context (dict): Information about the font and glyph context.
            output_truncated (bool): Whether output was truncated due to max_output_chars.
            error_truncated (bool): Whether error was truncated due to max_error_chars.
    """

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
        return value[-limit_int:], True

    try:
        # Get font context
        font = None
        glyph = None
        layer = None
        
        context_info = {}
        
        if len(Glyphs.fonts) > font_index >= 0:
            font = Glyphs.fonts[font_index]
            context_info["font"] = font.familyName
            
            if glyph_name and font.glyphs[glyph_name]:
                glyph = font.glyphs[glyph_name]
                context_info["glyph"] = glyph_name
                
                # Get the current master's layer
                if font.selectedFontMaster:
                    layer = glyph.layers[font.selectedFontMaster.id]
                    context_info["layer"] = layer.name
                elif font.masters:
                    layer = glyph.layers[font.masters[0].id]
                    context_info["layer"] = layer.name
        
        # Create a custom namespace with context
        namespace = {
            '__builtins__': __builtins__,
            'Glyphs': Glyphs,
            'GSGlyph': GSGlyph,
            'GSLayer': GSLayer,
            'GSPath': GSPath,
            'GSNode': GSNode,
            'GSComponent': GSComponent,
            'GSAnchor': GSAnchor,
            'json': json,
            'print': print,
            'font': font,
            'glyph': glyph,
            'layer': layer,
        }
        
        # Capture stdout and stderr (optional; avoid overhead for large jobs)
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
                # Try to compile the code first
                try:
                    compiled_code = compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    # If it fails as exec, try as eval for single expressions
                    try:
                        compiled_code = compile(code, '<string>', 'eval')
                        result = eval(compiled_code, namespace)
                    except Exception:
                        raise e
                else:
                    # Execute the compiled code
                    exec(compiled_code, namespace)
                    
                    # Try to get the result of the last expression if it exists
                    if return_last_expression:
                        lines = code.strip().split('\n')
                        if lines:
                            last_line = lines[-1].strip()
                            if last_line and not last_line.startswith(('print', 'import', 'from', 'def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'except:', 'finally:', 'with ')):
                                try:
                                    result = eval(last_line, namespace)
                                except:
                                    pass  # Ignore errors when trying to evaluate the last line
        
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            if isinstance(e, SystemExit):
                code_value = getattr(e, "code", None)
                error = "SystemExit is not allowed in execute_code_with_context (code={}).".format(code_value)
            elif isinstance(e, KeyboardInterrupt):
                error = "KeyboardInterrupt in execute_code_with_context."
            else:
                error = traceback.format_exc()
            error_output = stderr_capture.getvalue() if stderr_capture is not None else ""
            if error_output:
                error += f"\n{error_output}"
        
        # Get captured output
        output = stdout_capture.getvalue() if stdout_capture is not None else ""
        output, output_truncated = _truncate(output, max_output_chars)
        if error is not None:
            error, error_truncated = _truncate(error, max_error_chars)
        else:
            error_truncated = False
        
        # Prepare result
        response = {
            "success": error is None,
            "output": output,
            "error": error,
            "result": str(result) if result is not None else None,
            "context": context_info,
            "output_truncated": output_truncated,
            "error_truncated": error_truncated,
        }
        
        return json.dumps(response)
        
    except asyncio.CancelledError:
        raise
    except BaseException:
        return json.dumps({
            "success": False,
            "output": "",
            "error": f"Code execution failed: {traceback.format_exc()}",
            "result": None,
            "context": {}
        })
