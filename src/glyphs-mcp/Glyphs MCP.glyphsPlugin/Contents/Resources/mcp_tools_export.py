# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json
import traceback
from dataclasses import asdict

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp

from export_designspace_ufo import (
    ExportDesignspaceAndUFO as ExportDesignspaceAndUFOExporter,
    ExportOptions,
)


def _normalise_name_sequence(value):
    if not value:
        return []
    if isinstance(value, str):
        cleaned = value.replace(",", " ").split()
        return [name.strip() for name in cleaned if name.strip()]
    try:
        return [str(name).strip() for name in value if str(name).strip()]
    except TypeError:
        return []


@mcp.tool()
async def ExportDesignspaceAndUFO(
    font_index: int = 0,
    include_variable: bool = True,
    include_static: bool = True,
    brace_layers_mode: str = "layers",
    include_build_script: bool = True,
    decompose_glyphs: list | tuple | str | None = None,
    remove_overlap_glyphs: list | tuple | str | None = None,
    keep_glyphs_lib: bool = False,
    production_names: bool = False,
    decompose_smart_components: bool = True,
    decompose_smart_corners: bool = True,
    output_directory: str | None = None,
    open_destination: bool = False,
) -> str:
    """Export designspace and UFO packages for the selected font.

    Args:
        font_index: Index of the font in ``Glyphs.fonts`` to export.
        include_variable: Whether to generate variable designspace/UFO sources.
        include_static: Whether to generate static designspace/UFO sources.
        brace_layers_mode: ``"layers"`` keeps brace layers as glyph layers,
            ``"separate_ufos"`` exports them as standalone masters.
        include_build_script: Include a ``build.sh`` helper script.
        decompose_glyphs: Optional sequence of glyph names to decompose before
            export.
        remove_overlap_glyphs: Optional sequence of glyph names where overlaps
            should be removed before export.
        keep_glyphs_lib: Reserved for parity with the original script. When
            ``True`` the Glyphs lib is preserved (currently a no-op).
        production_names: Reserved for parity with the original script.
        decompose_smart_components: Decompose smart components before export.
        decompose_smart_corners: Decompose corner components before export.
        output_directory: Optional explicit destination directory. Required for
            unsaved fonts.
        open_destination: If ``True`` and the environment supports it, open the
            destination folder in Finder after export.

    Returns:
        JSON encoded dictionary with output paths and log messages.
    """

    log_messages = []
    options = None
    font = None

    def _capture_log(message):
        if message:
            log_messages.append(message)

    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(
                        font_index, len(Glyphs.fonts)
                    )
                }
            )

        font = Glyphs.fonts[font_index]

        brace_mode = (brace_layers_mode or "layers").strip().lower()

        options = ExportOptions(
            include_variable=include_variable,
            include_static=include_static,
            brace_layers_mode=brace_mode,
            include_build_script=include_build_script,
            decompose_glyphs=_normalise_name_sequence(decompose_glyphs),
            remove_overlap_glyphs=_normalise_name_sequence(remove_overlap_glyphs),
            keep_glyphs_lib=keep_glyphs_lib,
            production_names=production_names,
            decompose_smart_components=decompose_smart_components,
            decompose_smart_corners=decompose_smart_corners,
            output_directory=output_directory,
            open_destination=open_destination,
        )

        exporter = ExportDesignspaceAndUFOExporter(
            font, options=options, logger=_capture_log
        )
        result = exporter.run()

        return json.dumps(
            {
                "success": True,
                "outputDirectory": result.output_directory,
                "designspaceFiles": result.designspace_files,
                "masterUFOs": result.master_ufos,
                "braceUFOs": result.brace_ufos,
                "supportFiles": result.support_files,
                "log": result.log,
            }
        )
    except Exception as exc:
        error_payload = {
            "error": str(exc) or repr(exc),
            "errorType": type(exc).__name__,
            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
        }
        if font is not None:
            font_details = {"familyName": getattr(font, "familyName", None)}
            font_parent = getattr(font, "parent", None)
            if font_parent is not None:
                try:
                    file_url_obj = font_parent.fileURL()
                    if file_url_obj is not None:
                        font_details["filePath"] = getattr(file_url_obj, "path", lambda: None)()
                except Exception:
                    font_details["filePath"] = None
            error_payload["font"] = font_details
        if options is not None:
            error_payload["options"] = asdict(options)
        if log_messages:
            error_payload["log"] = log_messages
        return json.dumps(error_payload)

