# encoding: utf-8

from __future__ import division, print_function, unicode_literals
import json
import io
import contextlib
import asyncio
from GlyphsApp import Glyphs, GSGlyph, GSLayer, GSPath, GSNode, GSComponent, GSAnchor # type: ignore[import-not-found]

from mcp_tools import mcp


@mcp.tool()
async def execute_code(code: str, timeout: int = 30) -> str:
    """Execute Python code within the Glyphs environment with access to GlyphsApp API.
    
    Args:
        code (str): Python code to execute. Required.
        timeout (int): Maximum execution time in seconds. Defaults to 30.
    
    Returns:
        str: JSON-encoded result containing:
            success (bool): Whether the code executed successfully.
            output (str): Standard output from the code execution.
            error (str): Error message if execution failed.
            result (any): The result of the last expression (if any).
    """
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
        
        # Capture stdout and stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        result = None
        error = None
        
        try:
            # Redirect stdout and stderr
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                # Try to compile the code first
                try:
                    compiled_code = compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    # If it fails as exec, try as eval for single expressions
                    try:
                        compiled_code = compile(code, '<string>', 'eval')
                        result = eval(compiled_code, namespace)
                    except:
                        raise e
                else:
                    # Execute the compiled code
                    exec(compiled_code, namespace)
                    
                    # Try to get the result of the last expression if it exists
                    lines = code.strip().split('\n')
                    if lines:
                        last_line = lines[-1].strip()
                        if last_line and not last_line.startswith(('print', 'import', 'from', 'def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'except:', 'finally:', 'with ')):
                            try:
                                result = eval(last_line, namespace)
                            except:
                                pass  # Ignore errors when trying to evaluate the last line
        
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}"
            error_output = stderr_capture.getvalue()
            if error_output:
                error += f"\n{error_output}"
        
        # Get captured output
        output = stdout_capture.getvalue()
        
        # Prepare result
        response = {
            "success": error is None,
            "output": output,
            "error": error,
            "result": str(result) if result is not None else None
        }
        
        return json.dumps(response)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "output": "",
            "error": f"Code execution failed: {str(e)}",
            "result": None
        })


@mcp.tool()
async def execute_code_with_context(code: str, font_index: int = 0, glyph_name: str = None, timeout: int = 30) -> str:
    """Execute Python code with automatic context setup for a specific font and glyph.
    
    Args:
        code (str): Python code to execute. Required.
        font_index (int): Index of the font to work with. Defaults to 0.
        glyph_name (str): Name of the glyph to work with. Optional.
        timeout (int): Maximum execution time in seconds. Defaults to 30.
    
    Returns:
        str: JSON-encoded result containing:
            success (bool): Whether the code executed successfully.
            output (str): Standard output from the code execution.
            error (str): Error message if execution failed.
            result (any): The result of the last expression (if any).
            context (dict): Information about the font and glyph context.
    """
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
        
        # Capture stdout and stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        result = None
        error = None
        
        try:
            # Redirect stdout and stderr
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                # Try to compile the code first
                try:
                    compiled_code = compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    # If it fails as exec, try as eval for single expressions
                    try:
                        compiled_code = compile(code, '<string>', 'eval')
                        result = eval(compiled_code, namespace)
                    except:
                        raise e
                else:
                    # Execute the compiled code
                    exec(compiled_code, namespace)
                    
                    # Try to get the result of the last expression if it exists
                    lines = code.strip().split('\n')
                    if lines:
                        last_line = lines[-1].strip()
                        if last_line and not last_line.startswith(('print', 'import', 'from', 'def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'except:', 'finally:', 'with ')):
                            try:
                                result = eval(last_line, namespace)
                            except:
                                pass  # Ignore errors when trying to evaluate the last line
        
        except Exception as e:
            error = f"{type(e).__name__}: {str(e)}"
            error_output = stderr_capture.getvalue()
            if error_output:
                error += f"\n{error_output}"
        
        # Get captured output
        output = stdout_capture.getvalue()
        
        # Prepare result
        response = {
            "success": error is None,
            "output": output,
            "error": error,
            "result": str(result) if result is not None else None,
            "context": context_info
        }
        
        return json.dumps(response)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "output": "",
            "error": f"Code execution failed: {str(e)}",
            "result": None,
            "context": {}
        })