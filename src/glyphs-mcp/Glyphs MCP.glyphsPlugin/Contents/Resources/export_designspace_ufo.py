"""Headless export of UFO and designspace packages for Glyphs MCP.

This module adapts the original “Export UFO and designspace files” Glyphs
script for automated use inside the MCP server.  The upstream script relied on
Vanilla UI elements and mutable global state inside Glyphs.  Here we expose the
core logic behind a small API so that tooling can request exports without
opening UI dialogs.

The refactor keeps behaviour as close as possible to the original script while
providing the following improvements:

* pure-Python configuration via :class:`ExportOptions`;
* structured :class:`ExportResult` data that reports generated assets;
* log callbacks for streaming progress back to the MCP client;
* the ability to override the output directory and skip automatic Finder
  launching (which is inappropriate for headless usage);
* minor clean ups to make the code friendlier to static analysis.

The implementation still depends on Glyphs’ Python environment.  It assumes
the same optional packages (``fontParts``, ``fontTools``) are available as in
the original workflow.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from GlyphsApp import GSFont, GSFontMaster, GSInstance, GSLayer  # type: ignore[import-not-found]
from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    InstanceDescriptor,
    LocationLabelDescriptor,
    RuleDescriptor,
    SourceDescriptor,
)
from fontParts.fontshell.anchor import RAnchor
from fontParts.fontshell.component import RComponent
from fontParts.fontshell.contour import RContour
from fontParts.fontshell.font import RFont
from fontParts.fontshell.glyph import RGlyph
from fontParts.fontshell.guideline import RGuideline
from fontParts.fontshell.layer import RLayer
from fontParts.fontshell.lib import RLib
from fontParts.world import NewFont

__all__ = [
    "ExportDesignspaceAndUFO",
    "ExportOptions",
    "ExportResult",
]


@dataclass
class ExportOptions:
    """Configuration for exporting designspace and UFO packages."""

    include_variable: bool = True
    include_static: bool = True
    brace_layers_mode: str = "layers"  # "layers" or "separate_ufos"
    include_build_script: bool = True
    decompose_glyphs: Sequence[str] = ()
    remove_overlap_glyphs: Sequence[str] = ()
    keep_glyphs_lib: bool = False
    production_names: bool = False
    decompose_smart_components: bool = True
    decompose_smart_corners: bool = True
    output_directory: Optional[str] = None
    open_destination: bool = False

    def validate(self) -> None:
        if not (self.include_variable or self.include_static):
            raise ValueError("At least one of variable or static exports must be enabled")
        if self.brace_layers_mode not in {"layers", "separate_ufos"}:
            raise ValueError("brace_layers_mode must be 'layers' or 'separate_ufos'")


@dataclass
class ExportResult:
    """Summary data describing a completed export operation."""

    output_directory: str
    designspace_files: List[str] = field(default_factory=list)
    master_ufos: List[str] = field(default_factory=list)
    brace_ufos: List[str] = field(default_factory=list)
    support_files: List[str] = field(default_factory=list)
    log: List[str] = field(default_factory=list)


class _StatusLogger:
    """Collect log messages and relay them to an optional callback."""

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        self._messages: List[str] = []
        self._callback = callback

    @property
    def messages(self) -> List[str]:
        return list(self._messages)

    def log(self, message: str) -> None:
        if not message:
            return
        self._messages.append(message)
        if self._callback:
            try:
                self._callback(message)
            except Exception:
                # Avoid surfacing logging errors to the export process.
                pass


class ExportDesignspaceAndUFO:
    """Headless port of the original Glyphs export script."""

    def __init__(
        self,
        font: GSFont,
        options: Optional[ExportOptions] = None,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        options = options or ExportOptions()
        options.validate()
        self.options = options
        self._logger = _StatusLogger(logger)
        self._source_font = font

        # Attributes initialised during ``run``.
        self.font: GSFont = font
        self.to_build: Dict[str, bool] = {}
        self.brace_layers_as_layers: bool = True
        self.to_add_build_script: bool = True
        self.to_decompose: List[str] = []
        self.to_remove_overlap: List[str] = []
        self.keep_glyphs_lib = False
        self.production_names = False
        self.decompose_smart = False
        self.variable_font_family = ""
        self.has_variable_font_name = False
        self.origin_master: str = ""
        self.special_layers: List[GSLayer] = []
        self.special_layer_axes: List[Dict[str, int]] = []
        self.axis_map_to_build: Dict[str, Dict[int, int]] = {}
        self.origin_coords: List[int] = []
        self.muted_glyphs: List[str] = []
        self.kerning: Dict[str, Dict[str, List[List[Union[str, int]]]]] = {}

    # ------------------------------------------------------------------
    # Public API

    def _debug(self, message: str) -> None:
        """Emit a temporary debug message to the console and export log."""
        if not message:
            return
        prefixed = f"[ExportDesignspaceAndUFO DEBUG] {message}"
        try:
            print(prefixed)
        except Exception:
            pass
        self._logger.log(prefixed)

    def run(self) -> ExportResult:
        """Execute the export and return metadata about the output."""

        self._prepare_state()
        dest, designspace_files, master_ufos, brace_ufos, support_files = self._export_project()

        log_messages = self._logger.messages
        return ExportResult(
            output_directory=dest,
            designspace_files=designspace_files,
            master_ufos=master_ufos,
            brace_ufos=brace_ufos,
            support_files=support_files,
            log=log_messages,
        )

    # ------------------------------------------------------------------
    # Internal helpers mostly migrated from the original script.

    def _prepare_state(self) -> None:
        self.font = self._source_font.copy()
        self.to_build = {
            "variable": self.options.include_variable,
            "static": self.options.include_static,
        }
        self.brace_layers_as_layers = self.options.brace_layers_mode == "layers"
        self.to_add_build_script = self.options.include_build_script
        self.to_decompose = list(self.options.decompose_glyphs)
        self.to_remove_overlap = list(self.options.remove_overlap_glyphs)
        self.keep_glyphs_lib = self.options.keep_glyphs_lib
        self.production_names = self.options.production_names
        self.decompose_smart = self.options.decompose_smart_components

        self.origin_master = self.getOriginMaster()
        self.kerning = self.getKerning()
        self.variable_font_family = self.getVariableFontFamily()
        self.has_variable_font_name = bool(self.hasVariableFamilyName())
        self.special_layers = self.getSpecialLayers()
        self.muted_glyphs = self.getMutedGlyphs()
        self.special_layer_axes = self.getSpecialLayerAxes()
        self.axis_map_to_build = self.getAxisMapToBuild()
        self.origin_coords = self.getOriginCoords()

        if self.options.decompose_smart_components:
            self.decomposeSmartComponents()
        if self.options.decompose_smart_corners:
            self.decomposeCorners()

        self.alignSpecialLayers()
        self.updateFeatures()
        self.removeOverlaps()
        self.decomposeGlyphs()

    def _export_project(self) -> Tuple[str, List[str], List[str], List[str], List[str]]:
        font_parent = getattr(self._source_font, "parent", None)
        file_url = None
        if font_parent is not None:
            try:
                file_url = font_parent.fileURL()
            except Exception:
                file_url = None

        if file_url is None and not self.options.output_directory:
            raise ValueError(
                "The font must be saved to disk or an explicit output_directory must be provided."
            )

        if file_url is not None:
            file_path = file_url.path()
            file_dir = os.path.dirname(file_path)
        else:
            file_dir = os.getcwd()

        dest = (
            self.options.output_directory
            if self.options.output_directory
            else os.path.join(file_dir, "ufo")
        )

        designspace_files: List[str] = []
        master_ufos: List[str] = []
        brace_ufos: List[str] = []
        support_files: List[str] = []

        if os.path.exists(dest):
            self._debug(f"Removing existing destination directory: {dest}")
            shutil.rmtree(dest)

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_project_folder = os.path.join(tmp_dir, "ufo")
            os.mkdir(temp_project_folder)
            master_dir = os.path.join(temp_project_folder, "masters")
            os.mkdir(master_dir)
            self._debug(f"Created temporary project folder: {temp_project_folder}")

            # Generate designspace documents when the font is multi-master with axes.
            axes = list(getattr(self.font, "axes", []) or [])
            masters = list(getattr(self.font, "masters", []) or [])
            has_defined_axes = any(getattr(axis, "axisTag", None) for axis in axes)
            is_multi_master = len(masters) > 1
            should_export_designspace = is_multi_master and has_defined_axes

            if should_export_designspace:
                self._logger.log("Detected multi-master font with axes; exporting designspace document(s).")

                if self.to_build["static"]:
                    self._logger.log("Building designspace from font metadata (static).")
                    static_doc = self.getDesignSpaceDocument("static")
                    static_path = os.path.join(
                        temp_project_folder,
                        f"{self.getFamilyName('static').replace(' ', '')}.designspace",
                    )
                    static_doc.write(static_path)
                    designspace_files.append(os.path.relpath(static_path, temp_project_folder))

                if self.to_build["variable"]:
                    self._logger.log("Building variable designspace from font metadata.")
                    variable_doc = self.getDesignSpaceDocument("variable")
                    variable_path = os.path.join(
                        temp_project_folder,
                        f"{self.getFamilyName('variable').replace(' ', '')}.designspace",
                    )
                    variable_doc.write(variable_path)
                    designspace_files.append(os.path.relpath(variable_path, temp_project_folder))
            else:
                self._logger.log(
                    "Skipping designspace export: requires multiple masters and defined axes."
                )

            self.removeSubsFromOT()

            self._logger.log("Building UFOs for masters.")
            self._debug(
                f"Export configuration - masters: {len(self.font.masters)}, "
                f"glyphs: {len(getattr(self.font, 'glyphs', []))}, "
                f"brace_layers_as_layers: {self.brace_layers_as_layers}"
            )
            if self.to_build["variable"] and not self.to_build["static"]:
                master_ufos.extend(self.exportUFOMasters(temp_project_folder, "variable"))
                if not self.brace_layers_as_layers:
                    self._logger.log("Building UFOs for brace layers (separate masters).")
                    brace_ufos.extend(self.generateMastersAtBraces(temp_project_folder, "variable"))
            else:
                master_ufos.extend(self.exportUFOMasters(temp_project_folder, "static"))
                if not self.brace_layers_as_layers:
                    self._logger.log("Building UFOs for brace layers (separate masters).")
                    brace_ufos.extend(self.generateMastersAtBraces(temp_project_folder, "static"))

            for file in glob.glob(os.path.join(temp_project_folder, "*.ufo")):
                self._debug(f"Moving top-level UFO to masters folder: {file}")
                shutil.move(file, master_dir)

            if self.to_add_build_script:
                build_script = self.addBuildScript(temp_project_folder)
                if build_script:
                    support_files.append(os.path.relpath(build_script, temp_project_folder))

            self.writeFeatureFiles(temp_project_folder)

            self._debug(f"Copying export bundle to destination: {dest}")
            shutil.copytree(temp_project_folder, dest)

        if self.options.open_destination:
            subprocess.run(["open", dest], check=False)

        self._logger.log("Export completed.")

        designspace_files = [os.path.join(dest, path) for path in designspace_files]
        master_ufos = [os.path.join(dest, path) for path in master_ufos]
        brace_ufos = [os.path.join(dest, path) for path in brace_ufos]
        support_files = [os.path.join(dest, path) for path in support_files]

        return dest, designspace_files, master_ufos, brace_ufos, support_files

    # ------------------------------------------------------------------
    # Adapted helpers from the original script (with logging adjustments).

    def addBuildScript(self, dest: str) -> Optional[str]:
        """Create an optional ``build.sh`` helper script."""

        if not self.to_add_build_script:
            return None

        static_font_name = self.getFamilyName("static").replace(" ", "")
        vf_font_name = self.getFamilyName("variable").replace(" ", "")
        nl = "\n"
        vf_script = f"python3 -m fontmake -m {vf_font_name}.designspace -o variable --output-dir build/vf"
        static_script = (
            "python3 -m fontmake -i --expand-features-to-instances -m "
            f"{static_font_name}.designspace -o ttf --output-dir build/ttf{nl}"
            "python3 -m fontmake -i --expand-features-to-instances -m "
            f"{static_font_name}.designspace -o otf --output-dir build/otf"
        )
        if self.to_build["static"] and self.to_build["variable"]:
            build_script = "#!/bin/bash" + "\n" + vf_script + "\n" + static_script + "\n"
        elif self.to_build["static"]:
            build_script = "#!/bin/bash" + "\n" + static_script + "\n"
        else:
            build_script = "#!/bin/bash" + "\n" + vf_script + "\n"
        script_name = os.path.join(dest, "build.sh")
        with open(script_name, "w") as fh:
            fh.write(build_script)
        subprocess.run(["chmod", "+x", script_name], check=False)
        return script_name

    def decomposeGlyphs(self) -> None:
        """Decompose glyphs listed in :attr:`to_decompose`."""

        for glyph in self.to_decompose:
            if self.font.glyphs[glyph]:
                for layer in self.font.glyphs[glyph].layers:
                    if len(layer.components) > 0:
                        if layer.isMasterLayer or layer.isSpecialLayer:
                            layer.decomposeComponents()

    def removeOverlaps(self) -> None:
        """Remove overlaps for glyphs listed in :attr:`to_remove_overlap`."""

        for glyph in self.to_remove_overlap:
            if self.font.glyphs[glyph]:
                for layer in self.font.glyphs[glyph].layers:
                    if layer.isMasterLayer or layer.isSpecialLayer:
                        layer.removeOverlap()

    def getMutedGlyphs(self) -> List[str]:
        return [glyph.name for glyph in self.font.glyphs if not glyph.export]

    def getBoundsByTag(self, tag: str) -> List[Optional[int]]:
        minimum = None
        maximum = None
        for i, axis in enumerate(self.font.axes):
            if axis.axisTag != tag:
                continue
            for master in self.font.masters:
                coord = master.axes[i]
                if minimum is None or coord < minimum:
                    minimum = coord
                if maximum is None or coord > maximum:
                    maximum = coord
        return [minimum, maximum]

    def getOriginMaster(self) -> str:
        master_id = None
        for parameter in self.font.customParameters:
            if parameter.name == "Variable Font Origin":
                master_id = parameter.value
        if master_id is None:
            return self.font.masters[0].id
        return master_id

    def getOriginCoords(self) -> List[int]:
        master_id = None
        for parameter in self.font.customParameters:
            if parameter.name == "Variable Font Origin":
                master_id = parameter.value
        if master_id is None:
            master_id = self.font.masters[0].id
        for master in self.font.masters:
            if master.id == master_id:
                return list(master.axes)
        return []

    def getAxisNameByTag(self, tag: str) -> Optional[str]:
        for axis in self.font.axes:
            if axis.axisTag == tag:
                return axis.name
        return None

    def hasVariableFamilyName(self) -> bool:
        for instance in self.font.instances:
            if instance.variableStyleName:
                return True
        return False

    def getVariableFontFamily(self) -> str:
        for instance in self.font.instances:
            if instance.type == 1:
                return self.font.familyName + " " + instance.name
        return self.font.familyName

    def getFamilyName(self, format: str) -> str:
        if format == "variable":
            family_name = self.variable_font_family
        else:
            family_name = self.font.familyName
        return family_name

    def getFamilyNameWithMaster(self, master: GSFontMaster, format: str) -> str:
        master_name = master.name
        if self.has_variable_font_name:
            if format == "static":
                font_name = "%s - %s" % (self.font.familyName, master_name)
            else:
                font_name = "%s - %s" % (self.variable_font_family, master_name)
        else:
            font_name = "%s - %s" % (self.font.familyName, master_name)
        return font_name

    def getStyleNameWithAxis(self, axes: Sequence[int]) -> str:
        style_name = ""
        for i, axis in enumerate(axes):
            style_name = "%s %s %s" % (style_name, self.font.axes[i].name, axis)
        return style_name.strip()

    def getNameWithAxis(self, axes: Sequence[int]) -> str:
        if not self.to_build["static"]:
            font_name = "%s -" % self.variable_font_family
        else:
            font_name = "%s -" % (self.font.familyName)
        for i, axis in enumerate(axes):
            font_name = "%s %s %s" % (font_name, self.font.axes[i].name, axis)
        return font_name

    def alignSpecialLayers(self) -> None:
        master_id = self.origin_master
        special_layers = self.special_layers
        for layer in special_layers:
            layer.associatedMasterId = master_id

    def getSources(self, format: str) -> List[SourceDescriptor]:
        sources: List[SourceDescriptor] = []
        for i, master in enumerate(self.font.masters):
            source = SourceDescriptor()
            if self.has_variable_font_name and not self.to_build["static"]:
                font_name = self.getFamilyNameWithMaster(master, "variable")
            else:
                font_name = self.getFamilyNameWithMaster(master, "static")
            source.filename = "masters/%s.ufo" % font_name
            source.familyName = self.getFamilyName(format)
            source.styleName = master.name
            locations = dict()
            for x, axis in enumerate(master.axes):
                locations[self.font.axes[x].name] = axis
            source.designLocation = locations
            source.mutedGlyphNames = self.muted_glyphs
            sources.append(source)
        return sources

    def addSources(self, doc: DesignSpaceDocument, sources: Iterable[SourceDescriptor]) -> None:
        for source in sources:
            doc.addSource(source)

    def getSpecialLayers(self) -> List[GSLayer]:
        return [l for g in self.font.glyphs for l in g.layers if l.isSpecialLayer and l.attributes.get("coordinates")]

    def getSpecialLayerAxes(self) -> List[Dict[str, int]]:
        special_layer_axes: List[Dict[str, int]] = []
        layers = self.special_layers
        for layer in layers:
            layer_axes: Dict[str, int] = dict()
            for i, coords in enumerate(layer.attributes["coordinates"]):
                layer_axes[self.font.axes[i].name] = int(layer.attributes["coordinates"][coords])
            if layer_axes not in special_layer_axes:
                special_layer_axes.append(layer_axes)
        return special_layer_axes

    def getSpecialGlyphNames(self, axes: Sequence[int]) -> List[str]:
        glyph_names: List[str] = []
        for glyph in self.font.glyphs:
            for layer in glyph.layers:
                if layer.isSpecialLayer and layer.attributes.get("coordinates"):
                    coords = list(map(int, layer.attributes["coordinates"].values()))
                    if list(axes) == coords:
                        glyph_names.append(glyph.name)
                        continue
        return glyph_names

    def getMasterById(self, master_id: str) -> Optional[GSFontMaster]:
        for master in self.font.masters:
            if master.id == master_id:
                return master
        return None

    def getSpecialSources(self, format: str) -> List[SourceDescriptor]:
        sources: List[SourceDescriptor] = []
        special_layer_axes = self.special_layer_axes
        for special_layer_axis in special_layer_axes:
            axes = list(special_layer_axis.values())
            source = SourceDescriptor()
            master = self.getMasterById(self.origin_master)
            if master is None:
                continue
            if self.brace_layers_as_layers:
                if self.hasVariableFamilyName() and not self.to_build["static"]:
                    font_name = self.getFamilyNameWithMaster(master, "variable")
                else:
                    font_name = self.getFamilyNameWithMaster(master, "static")
            else:
                font_name = self.getNameWithAxis(axes)
            source.location = special_layer_axis
            source.familyName = self.getFamilyName(format)
            source.styleName = master.name
            source.familyName = font_name
            source.filename = "masters/%s.ufo" % font_name
            if self.brace_layers_as_layers:
                layer_axis_name = "{" + ",".join(str(x) for x in list(special_layer_axis.values())) + "}"
                source.layerName = layer_axis_name
            sources.append(source)
        return sources

    def getAxisMapToBuild(self) -> Dict[str, Dict[int, int]]:
        axis_map: Dict[str, Dict[int, int]] = dict()
        for instance in self.font.instances:
            if instance.type == 0:
                for i, internal in enumerate(instance.axes):
                    if instance.customParameters["Axis Location"]:
                        external = instance.customParameters["Axis Location"][i]["Location"]
                    else:
                        external = internal
                    axis_tag = self.font.axes[i].axisTag
                    axis_map.setdefault(axis_tag, dict())[internal] = external
        return axis_map

    def getLabels(self, format: str) -> List[LocationLabelDescriptor]:
        labels: List[LocationLabelDescriptor] = []
        instances = [instance for instance in self.font.instances if instance.active and instance.type == 0]
        for instance in instances:
            if format == "variable" and instance.variableStyleName:
                style_name = instance.variableStyleName
            else:
                style_name = instance.name

            elidable = False
            for i, axis in enumerate(instance.axes):
                axis_tag = self.font.axes[i].axisTag
                if (
                    instance.customParameters["Elidable STAT Axis Value Name"]
                    and instance.customParameters["Elidable STAT Axis Value Name"] == axis_tag
                ):
                    elidable = True

            if self.font.customParameters["Axis Mappings"]:
                axis_map = self.font.customParameters["Axis Mappings"]
            else:
                axis_map = self.axis_map_to_build

            user_location: Dict[str, int] = dict()
            for i, axis in enumerate(instance.axes):
                user_name = self.font.axes[i].name
                user_coord = axis_map[self.font.axes[i].axisTag][axis]
                user_location[user_name] = user_coord

            label = LocationLabelDescriptor(name=style_name, userLocation=user_location, elidable=elidable)
            if label not in labels:
                labels.append(label)
        labels = list(dict.fromkeys(labels))
        return labels

    def addLabels(self, doc: DesignSpaceDocument, labels: List[LocationLabelDescriptor]) -> DesignSpaceDocument:
        doc.locationLabels = labels
        return doc

    def addAxes(self, doc: DesignSpaceDocument) -> None:
        for i, axis in enumerate(self.font.axes):
            if self.font.customParameters["Axis Mappings"]:
                axis_map = self.font.customParameters["Axis Mappings"].get(axis.axisTag)
                self._debug(
                    f"Axis '{axis.name}' uses custom Axis Mapping keys: "
                    f"{sorted((axis_map or {}).keys()) if axis_map else '[]'}"
                )
            else:
                axis_map = self.axis_map_to_build
                if axis_map is not None:
                    axis_map = axis_map.get(axis.axisTag)
                self._debug(
                    f"Axis '{axis.name}' uses computed Axis Mapping keys: "
                    f"{sorted((axis_map or {}).keys()) if axis_map else '[]'}"
                )
            if axis_map:
                descriptor = AxisDescriptor()

                axis_min, axis_max = self.getBoundsByTag(axis.axisTag)
                self._debug(
                    f"Axis '{axis.name}' min={axis_min}, max={axis_max}, origin={self.origin_coords[i] if i < len(self.origin_coords) else None}"
                )

                for k in sorted(axis_map.keys()):
                    descriptor.map.append((axis_map[k], k))
                try:
                    descriptor.maximum = axis_map[axis_max]  # type: ignore[index]
                    descriptor.minimum = axis_map[axis_min]  # type: ignore[index]
                except KeyError as missing_key:
                    available = sorted(axis_map.keys())
                    self._debug(
                        f"Axis '{axis.name}' missing mapping for coordinate {missing_key!r}. Available keys: {available}"
                    )
                    raise
                except Exception as exc:
                    self._logger.log("Error: the font's axis mappings don't match its real min/max coords")
                    self._debug(
                        f"Axis '{axis.name}' mismatch while resolving min/max ({exc!r}). "
                        f"Axis map keys: {sorted(axis_map.keys())}"
                    )
                origin_coord = self.origin_coords[i]
                try:
                    user_origin = axis_map[origin_coord]
                except KeyError as missing_origin:
                    available = sorted(axis_map.keys())
                    self._debug(
                        f"Axis '{axis.name}' missing mapping for origin coordinate {missing_origin!r}. Available keys: {available}"
                    )
                    raise
                descriptor.default = user_origin
                descriptor.name = axis.name
                descriptor.tag = axis.axisTag
                doc.addAxis(descriptor)

    def getConditionsFromOT(self) -> Tuple[List[List[dict]], List[List[Tuple[str, str]]]]:
        feature_code = ""
        for feature_itr in self.font.features:
            for line in feature_itr.code.splitlines():
                if line.startswith("condition "):
                    feature_code = feature_itr.code
        condition_index = 0
        condition_list: List[List[dict]] = []
        replacement_list: List[List[Tuple[str, str]]] = [[]]
        for line in feature_code.splitlines():
            if line.startswith("condition"):
                conditions = []
                conditions_list = line.split(",")
                for condition in conditions_list:
                    m = re.findall(r"< (\w{4})", condition)
                    tag = m[0]
                    axis_name = self.getAxisNameByTag(tag)
                    m = re.findall(r"\d+(?:\.|)\d*", condition)
                    cond_min = float(m[0])
                    if len(m) > 1:
                        cond_max = float(m[1])
                        range_dict = dict(name=axis_name, minimum=cond_min, maximum=cond_max)
                    else:
                        _, cond_max = self.getBoundsByTag(tag)
                        range_dict = dict(name=axis_name, minimum=cond_min, maximum=cond_max)
                    conditions.append(range_dict)
                condition_list.append(conditions)
                condition_index = condition_index + 1
            elif line.startswith("sub"):
                m = re.findall(r"sub (.*) by (.*);", line)[0]
                replace = (m[0], m[1])
                try:
                    replacement_list[condition_index - 1].append(replace)
                except Exception:
                    replacement_list.append(list())
                    replacement_list[condition_index - 1].append(replace)
        return [condition_list, replacement_list]

    def removeSubsFromOT(self) -> None:
        feature_index = None
        for i, feature_itr in enumerate(self.font.features):
            for line in feature_itr.code.splitlines():
                if line.startswith("condition "):
                    feature_index = i
                    break
        if feature_index is not None:
            feature = self.font.features[feature_index]
            feature.code = re.sub(r'#ifdef VARIABLE.*?#endif', '', feature.code, flags=re.DOTALL)
            if not feature.code.strip():
                del self.font.features[feature_index]

    def applyConditionsToRules(
        self,
        doc: DesignSpaceDocument,
        condition_list: List[List[dict]],
        replacement_list: List[List[Tuple[str, str]]],
    ) -> None:
        rules = []
        for i, condition in enumerate(condition_list):
            rule = RuleDescriptor()
            rule.name = "Rule %s" % str(i + 1)
            rule.conditionSets.append(condition)
            for sub in replacement_list[i]:
                rule.subs.append(sub)
            rules.append(rule)
        doc.rules = rules

    def getInstances(self, format: str) -> List[InstanceDescriptor]:
        instances_to_return: List[InstanceDescriptor] = []
        for instance in self.font.instances:
            if not instance.active:
                continue
            if instance.type == 1:
                continue
            ins = InstanceDescriptor()
            postScriptName = instance.fontName
            if instance.isBold:
                style_map_style = "bold"
            elif instance.isItalic:
                style_map_style = "italic"
            else:
                style_map_style = "regular"
            if format == "variable":
                family_name = self.variable_font_family
            else:
                if instance.preferredFamily:
                    family_name = instance.preferredFamily
                else:
                    family_name = self.font.familyName
            ins.familyName = family_name
            if format == "variable":
                style_name = instance.variableStyleName
            else:
                style_name = instance.name
            ins.styleName = style_name
            ins.filename = "instances/%s.ufo" % postScriptName
            ins.postScriptFontName = postScriptName
            ins.styleMapFamilyName = instance.preferredFamily
            ins.styleMapStyleName = style_map_style
            design_location: Dict[str, Union[int, float]] = {}
            for i, axis_value in enumerate(instance.axes):
                design_location[self.font.axes[i].name] = axis_value
            ins.designLocation = design_location

            axis_map = self.axis_map_to_build
            user_location: Dict[str, Union[int, float]] = {}
            for i, axis_value in enumerate(instance.axes):
                user_location[self.font.axes[i].name] = axis_map[self.font.axes[i].axisTag][axis_value]
            ins.userLocation = user_location

            instances_to_return.append(ins)
        return instances_to_return

    def addInstances(self, doc: DesignSpaceDocument, instances: List[InstanceDescriptor]) -> None:
        for instance in instances:
            doc.addInstance(instance)

    def updateFeatures(self) -> None:
        for feature in self.font.features:
            if feature.automatic:
                feature.update()

    def getDesignSpaceDocument(self, format: str) -> DesignSpaceDocument:
        self._debug(f"Constructing designspace document (format='{format}').")
        doc = DesignSpaceDocument()
        self.addAxes(doc)
        self._debug(f"Designspace axes: {[axis.name for axis in doc.axes]}")
        sources = self.getSources(format)
        self.addSources(doc, sources)
        special_sources = self.getSpecialSources(format)
        self.addSources(doc, special_sources)
        instances = self.getInstances(format)
        self.addInstances(doc, instances)
        labels = self.getLabels(format)
        self.addLabels(doc, labels)
        condition_list, replacement_list = self.getConditionsFromOT()
        self.applyConditionsToRules(doc, condition_list, replacement_list)
        doc.rulesProcessingLast = True
        return doc

    def generateMastersAtBraces(self, temp_project_folder: str, format: str) -> List[str]:
        generated: List[str] = []
        special_layer_axes = self.special_layer_axes
        self._debug(
            f"Generating brace masters ({len(special_layer_axes)} layers) in format '{format}'."
        )
        for special_layer_axis in special_layer_axes:
            axes = list(special_layer_axis.values())
            self.font.instances.append(GSInstance())
            ins = self.font.instances[-1]
            ins.name = self.getNameWithAxis(axes)
            ufo_file_name = "%s.ufo" % ins.name
            style_name = self.getStyleNameWithAxis(axes)
            ins.styleName = style_name
            ins.axes = axes
            brace_font = ins.interpolatedFont
            brace_font.masters[0].name = style_name
            brace_glyphs = self.getSpecialGlyphNames(axes)
            for glyph in self.font.glyphs:
                if glyph.name not in brace_glyphs:
                    del brace_font.glyphs[glyph.name]
            feature_keys = [feature.name for feature in brace_font.features]
            for key in feature_keys:
                del brace_font.features[key]
            class_keys = [font_class.name for font_class in brace_font.classes]
            for key in class_keys:
                del brace_font.classes[key]
            for glyph in brace_font.glyphs:
                if glyph.rightKerningGroup:
                    glyph.rightKerningGroup = None
                if glyph.leftKerningGroup:
                    glyph.leftKerningGroup = None
                if glyph.topKerningGroup:
                    glyph.topKerningGroup = None
                if glyph.bottomKerningGroup:
                    glyph.bottomKerningGroup = None
            brace_font.kerning = {}
            brace_font.kerningRTL = {}
            brace_font.kerningVertical = {}
            ufo_file_path = os.path.join(temp_project_folder, ufo_file_name)
            self._debug(
                f"Brace master '{ins.name}' -> {ufo_file_path}"
            )
            ufo = self.buildUfoFromMaster(brace_font.masters[0])
            ufo.save(ufo_file_path)
            generated.append(os.path.join("masters", ufo_file_name))
        self._debug(f"Generated {len(generated)} brace master UFOs.")
        return generated

    def getIndexByMaster(self, font: GSFont, master: GSFontMaster) -> Optional[int]:
        for i, m in enumerate(font.masters):
            if master.id == m.id:
                return i
        return None

    def addGroups(self, ufo: RFont) -> RFont:
        groups = {"left": {}, "right": {}}
        for glyph in self.font.glyphs:
            if glyph.leftKerningGroup:
                groups.setdefault("left", {}).setdefault(glyph.leftKerningGroup, []).append(glyph.name)
            if glyph.rightKerningGroup:
                groups.setdefault("right", {}).setdefault(glyph.rightKerningGroup, []).append(glyph.name)

        for group, glyph_names in groups.get("left", {}).items():
            group_name = "public.kern1." + group
            ufo.groups[group_name] = glyph_names

        for group, glyph_names in groups.get("right", {}).items():
            group_name = "public.kern2." + group
            ufo.groups[group_name] = glyph_names
        return ufo

    def formatValue(self, value, value_type: str):
        if not value:
            return None
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return bool(value)
        return value

    def addFontInfoToUfo(self, master: GSFontMaster, ufo: RFont) -> RFont:
        font = master.font
        ufo.info.versionMajor = font.versionMajor
        ufo.info.versionMinor = font.versionMinor

        ufo.info.copyright = font.copyright
        ufo.info.trademark = font.trademark

        ufo.info.unitsPerEm = font.upm
        ufo.info.ascender = master.ascender
        ufo.info.descender = master.descender
        ufo.info.xHeight = master.xHeight
        ufo.info.capHeight = master.capHeight
        ufo.info.ascender = master.ascender
        ufo.info.italicAngle = master.italicAngle

        ufo.info.note = font.note

        ufo.info.openTypeHeadCreated = font.date.strftime("%Y/%m/%d %H:%M:%S")

        ufo.info.openTypeNameDesigner = font.designer
        ufo.info.openTypeNameDesignerURL = font.designerURL
        ufo.info.openTypeNameManufacturer = font.manufacturer
        ufo.info.openTypeNameManufacturerURL = font.manufacturerURL
        ufo.info.openTypeNameLicense = font.license
        for info in font.properties:
            if info.key == "licenseURL":
                ufo.info.openTypeNameLicenseURL = info.value
        ufo.info.openTypeNameDescription = font.description
        ufo.info.openTypeNameSampleText = font.sampleText

        ufo.info.openTypeHheaAscender = self.formatValue(master.customParameters["hheaAscender"], "int")
        ufo.info.openTypeHheaDescender = self.formatValue(master.customParameters["hheaDescender"], "int")
        ufo.info.openTypeHheaLineGap = self.formatValue(master.customParameters["hheaLineGap"], "int")

        for info in font.properties:
            if info.key == "vendorID":
                ufo.info.openTypeOS2VendorID = info.value if info.value else None

        ufo.info.openTypeOS2Panose = [int(p) for p in font.customParameters["panose"]] if font.customParameters["panose"] else None

        ufo.info.openTypeOS2TypoAscender = self.formatValue(master.customParameters["typoAscender"], "int")
        ufo.info.openTypeOS2TypoDescender = self.formatValue(master.customParameters["typoDescender"], "int")
        ufo.info.openTypeOS2TypoLineGap = self.formatValue(master.customParameters["typoLineGap"], "int")

        ufo.info.openTypeOS2WinAscent = self.formatValue(master.customParameters["winAscent"], "int")
        ufo.info.openTypeOS2WinDescent = self.formatValue(master.customParameters["winDescent"], "int")

        try:
            ufo.info.openTypeOS2Type = [int(font.customParameters["fsType"]["value"])]
        except Exception:
            ufo.info.openTypeOS2Type = [0]

        ufo.info.openTypeOS2SubscriptXSize = self.formatValue(master.customParameters["subscriptXSize"], "int")
        ufo.info.openTypeOS2SubscriptYSize = self.formatValue(master.customParameters["subscriptYSize"], "int")
        ufo.info.openTypeOS2SubscriptXOffset = self.formatValue(master.customParameters["subscriptXOffset"], "int")
        ufo.info.openTypeOS2SubscriptYOffset = self.formatValue(master.customParameters["subscriptYOffset"], "int")
        ufo.info.openTypeOS2SuperscriptXSize = self.formatValue(master.customParameters["subscriptYOffset"], "int")

        ufo.info.openTypeOS2SuperscriptYSize = self.formatValue(master.customParameters["superscriptYSize"], "int")
        ufo.info.openTypeOS2SuperscriptXOffset = self.formatValue(master.customParameters["superscriptXOffset"], "int")
        ufo.info.openTypeOS2SuperscriptYOffset = self.formatValue(master.customParameters["superscriptYOffset"], "int")
        ufo.info.openTypeOS2StrikeoutSize = self.formatValue(master.customParameters["strikeoutSize"], "int")
        ufo.info.openTypeOS2StrikeoutPosition = self.formatValue(master.customParameters["strikeoutPosition"], "int")

        ufo.info.postscriptUniqueID = font.customParameters["uniqueID"]
        ufo.info.postscriptUnderlineThickness = self.formatValue(master.customParameters["underlineThickness"], "int")
        ufo.info.postscriptUnderlinePosition = self.formatValue(master.customParameters["underlinePosition"], "int")
        ufo.info.postscriptIsFixedPitch = self.formatValue(font.customParameters["isFixedPitch"], "bool")

        ufo.info.postscriptStemSnapH = [
            int(stem)
            for i, stem in enumerate(master.stems)
            if font.stems[i].horizontal
        ]
        ufo.info.postscriptStemSnapV = [
            int(stem)
            for i, stem in enumerate(master.stems)
            if not font.stems[i].horizontal
        ]

        ufo.info.postscriptBlueFuzz = self.formatValue(font.customParameters["blueFuzz"], "float")
        ufo.info.postscriptBlueShift = self.formatValue(font.customParameters["blueShift"], "float")
        ufo.info.postscriptBlueScale = self.formatValue(font.customParameters["blueScale"], "float")

        return ufo

    def getGlyphFromGSLayer(self, ufo: RFont, layer: GSLayer) -> RGlyph:
        glyph = RGlyph()
        glyph.width = layer.width
        glyph.leftMargin = layer.LSB
        glyph.rightMargin = layer.RSB
        glyph.name = layer.parent.name
        if layer.anchors:
            for anchor in layer.anchors:
                ufo_anchor = RAnchor()
                ufo_anchor.name = anchor.name
                ufo_anchor.x = anchor.x
                ufo_anchor.y = anchor.y
                glyph.appendAnchor(anchor=ufo_anchor)
        if layer.shapes:
            for shape in layer.shapes:
                if shape.shapeType == 2:
                    contour = RContour()
                    contour.clockwise = False if shape.direction == -1 else True
                    nodes = shape.nodes
                    for i, node in enumerate(nodes):
                        if shape.closed is False and i == 0:
                            contour.appendPoint((node.x, node.y), "move")
                        else:
                            if node.type in {"line", "curve", "offcurve"}:
                                contour.appendPoint((node.x, node.y), node.type, node.smooth)
                    glyph.appendContour(contour)
                elif shape.shapeType == 4:
                    component = RComponent()
                    component.baseGlyph = shape.name
                    component.scale = (shape.scale.x, shape.scale.y)
                    component.transform = shape.transform
                    component.rotateBy(shape.rotation)
                    component.offset = (shape.x, shape.y)
                    glyph.appendComponent(component=component)
        if layer.guides:
            for guide in layer.guides:
                guideline = RGuideline()
                guideline.x = guide.position.x
                guideline.y = guide.position.y
                guideline.angle = guide.angle
                guideline.name = guide.name
                ufo[glyph.name].appendGuideline(guideline=guideline)
        return glyph

    def buildUfoFromMaster(self, master: GSFontMaster) -> RFont:
        font = master.font
        master_index = self.getIndexByMaster(font, master)
        if master_index is None:
            raise ValueError("Master index could not be determined")

        self._logger.log("Building master: %s - %s" % (master.font.familyName, master.name))

        glyphs = font.glyphs
        glyph_count = len(glyphs)
        self._debug(
            f"Master '{master.name}': preparing {glyph_count} glyph containers (index={master_index})."
        )
        ufo = NewFont(familyName=font.familyName, styleName=master.name)
        ufo = self.addFontInfoToUfo(master, ufo)
        for idx, glyph in enumerate(glyphs, start=1):
            ufo.newGlyph(glyph.name)
            if glyph.unicodes is not None:
                ufo[glyph.name].unicodes = glyph.unicodes
            ufo[glyph.name].export = glyph.export
            if idx % 100 == 0 or idx == glyph_count:
                self._debug(
                    f"Master '{master.name}': initialised {idx}/{glyph_count} glyph shells."
                )
        for idx, glyph in enumerate(glyphs, start=1):
            for layer in glyph.layers:
                if layer.isMasterLayer and layer.master.id == font.masters[master_index].id:
                    r_glyph = self.getGlyphFromGSLayer(ufo, layer)
                    ufo[glyph.name] = r_glyph
                    if glyph.unicodes is not None:
                        ufo[glyph.name].unicodes = glyph.unicodes
                    ufo[glyph.name].export = glyph.export
            if idx % 50 == 0 or idx == glyph_count:
                self._debug(
                    f"Master '{master.name}': populated outlines for {idx}/{glyph_count} glyphs."
                )
        return ufo

    def getKerning(self) -> Dict[str, Dict[str, List[List[Union[str, int]]]]]:
        kerning: Dict[str, Dict[str, Union[Dict[str, str], List[List[Union[str, int]]]]]] = {
            "feature": {},
            "ufo": {},
        }

        if not self.font.kerning.items():
            return kerning  # type: ignore[return-value]

        glyph_ids: Dict[str, str] = dict()

        feature_kerning: Dict[str, str] = dict()
        ufo_kerning: Dict[str, List[List[Union[str, int]]]] = dict()
        for glyph in self.font.glyphs:
            glyph_ids[glyph.id] = glyph.name
        for master_id, value in self.font.kerning.items():
            kerning_str = ""
            for left_group, value in self.font.kerning[master_id].items():
                if left_group[0:4] == "@MMK":
                    left_ufo_group = "public.kern1." + left_group[7:]
                else:
                    left_ufo_group = glyph_ids[left_group]
                for right_group, value in value.items():
                    if right_group[0:4] == "@MMK":
                        right_ufo_group = "public.kern2." + right_group[7:]
                    else:
                        right_ufo_group = glyph_ids[right_group]
                    ufo_kerning.setdefault(master_id, []).append([left_ufo_group, right_ufo_group, int(value)])
                    continue
                kerning_str += f"        pos {left_group} {right_group} {value};\n"
            kerning_str.strip()

            use_extension = " useExtension" if self.font.customParameters["Use Extension Kerning"] else None
            feature_kerning_str = f"""feature kern {{
    lookup kern_DFLT{use_extension if use_extension else ""} {{
{kerning_str}    }}
}}
"""
            try:
                feature_kerning[master_id] = feature_kerning_str
                kerning["ufo"][master_id] = ufo_kerning[master_id]
                kerning["feature"][master_id] = feature_kerning[master_id]
            except Exception:
                pass

        return kerning  # type: ignore[return-value]

    def addUfoKerning(self, ufo: RFont, master_id: str) -> RFont:
        try:
            for left, right, value in self.kerning["ufo"][master_id]:
                ufo.kerning[(left, right)] = value
        except Exception:
            pass
        return ufo

    def addFeatureIncludes(self, ufo: RFont, master: GSFontMaster) -> RFont:
        features = self.getFeatureDict(master.font)
        feature_str = """include(../../features/prefixes.fea);
include(../../features/classes.fea);
"""
        font = master.font
        nl = "\n"
        for feature in features.keys():
            if not feature.startswith("size_"):
                feature_str = feature_str + f"include(../../features/{feature}.fea);{nl}"
            ufo.features.text = feature_str

        return ufo

    def addGlyphLayersToUfo(self, ufo: RFont) -> RFont:
        brace_layers = self.special_layers
        for layer in brace_layers:
            axes = list(dict.fromkeys(layer.attributes["coordinates"].values()))
            axes = [str(a) for a in axes]
            special_layer_name = "{" + ",".join(axes) + "}"
            glyph = self.getGlyphFromGSLayer(ufo, layer)
            glyph.name = layer.parent.name
            try:
                r_layer = ufo.getLayer(special_layer_name)
            except Exception:
                r_layer = RLayer()
                r_layer.name = special_layer_name
                r_layer = ufo.insertLayer(r_layer)
            r_layer.insertGlyph(glyph)
        return ufo

    def addLayersToUfo(self, ufo: RFont) -> RFont:
        special_layer_axes = self.special_layer_axes
        for special_layer_axis in special_layer_axes:
            axes = list(special_layer_axis.values())
            axes = [str(a) for a in axes]
            special_layer_name = "{" + ",".join(axes) + "}"
            try:
                ufo.getLayer(special_layer_name)
            except Exception:
                r_layer = RLayer()
                r_layer.name = special_layer_name
                ufo.insertLayer(r_layer)
        return ufo

    def addSkipExport(self, ufo: RFont) -> RFont:
        lib = RLib()
        lib["public.skipExportGlyphs"] = [g.name for g in self.font.glyphs if g.export is False]
        ufo.lib.update(lib)
        return ufo

    def addGlyphOrder(self, ufo: RFont) -> RFont:
        ufo.glyphOrder = list(g.name for g in self.font.glyphs)
        return ufo

    def exportUFOMasters(self, dest: str, format: str) -> List[str]:
        exported: List[str] = []
        masters = list(self.font.masters)
        self._debug(f"Exporting {len(masters)} masters to '{dest}' (format='{format}').")
        for index, master in enumerate(masters, start=1):
            font_name = self.getFamilyNameWithMaster(master, format)
            ufo_file_name = "%s.ufo" % font_name
            ufo_file_path = os.path.join(dest, ufo_file_name)
            self._debug(f"[Master {index}/{len(masters)}] Building UFO: {ufo_file_name}")
            ufo = self.buildUfoFromMaster(master)
            ufo = self.addGroups(ufo)
            ufo = self.addUfoKerning(ufo, master.id)
            ufo = self.addFeatureIncludes(ufo, master)
            ufo = self.addPostscriptNames(ufo)
            ufo = self.addGlyphOrder(ufo)
            ufo = self.addSkipExport(ufo)
            if self.brace_layers_as_layers:
                ufo = self.addLayersToUfo(ufo)
                if master.id == self.origin_master:
                    ufo = self.addGlyphLayersToUfo(ufo)
            ufo.save(ufo_file_path)
            self._debug(f"[Master {index}/{len(masters)}] Saved to {ufo_file_path}")
            exported.append(os.path.join("masters", ufo_file_name))
        return exported

    def getFeatureDict(self, font: GSFont) -> OrderedDict:
        nl = "\n"
        features: "OrderedDict[str, str]" = OrderedDict()

        for feature in font.features:
            feature_code = ""
            for line in feature.code.splitlines():
                feature_code = feature_code + "  " + line + "\n"
            if feature.name[0:2] == "ss":
                feature_str = f"""feature {feature.name} {{ {nl}{feature_code}}} {feature.name};{nl}{nl}"""
                features["ss"] = features.get("ss", "") + feature_str
            elif feature.name[0:2] == "cv":
                feature_str = f"""feature {feature.name} {{ {nl}{feature_code}}} {feature.name};{nl}{nl}"""
                features["cv"] = features.get("cv", "") + feature_str
            else:
                features[feature.name] = f"""feature {feature.name} {{ {nl}{feature_code}}} {feature.name};{nl}"""
        if "ss" in features:
            features["ss"] = features["ss"].strip()
        if "cv" in features:
            features["cv"] = features["cv"].strip()

        if self.to_build["static"] is not False:
            size_arr = list(
                dict.fromkeys(
                    [instance.customParameters["Optical Size"] for instance in font.instances if instance.customParameters["Optical Size"]]
                )
            )
            nl = "\n"
            for s, size in enumerate(size_arr):
                size_str = "feature size {\n"
                size_params = size.split(";")
                for i in range(0, len(size_params) - 1):
                    if i == 0:
                        size_str = size_str + f"    parameters {size_params[i]}"
                    else:
                        size_str = size_str + " " + size_params[i]
                size_str = size_str + ";\n"
                size_str = size_str + f"    sizemenuname \"{size_params[-1]}\";{nl}"
                size_str = size_str + f"    sizemenuname 1 \"{size_params[-1]}\";{nl}"
                size_str = size_str + f"    sizemenuname 1 21 0 \"{size_params[-1]}\";{nl}"
                size_str = size_str + "} size;"
                key = "size_" + str(s)
                features[key] = size_str

        return features

    def writeFeatureFiles(self, dest: str) -> None:
        feature_dir = "features"
        os.mkdir(os.path.join(dest, feature_dir))
        features = self.getFeatureDict(self.font)
        for f_name, f_code in features.items():
            f_dest = os.path.join(dest, feature_dir, f"{f_name}.fea")
            with open(f_dest, "w") as fh:
                fh.write(f_code)

        prefixes = ""
        for prefix in self.font.featurePrefixes:
            prefixes = prefixes + prefix.code + "\n"
        prefixes.strip()
        p_dest = os.path.join(dest, feature_dir, "prefixes.fea")
        with open(p_dest, "w") as fh:
            fh.write(prefixes)

        font_classes = ""
        nl = "\n"
        for font_class in self.font.classes:
            font_classes = font_classes + f"@{font_class.name} = [{font_class.code.strip()}];{nl}{nl}"
        font_classes.strip()
        c_dest = os.path.join(dest, feature_dir, "classes.fea")
        with open(c_dest, "w") as fh:
            fh.write(font_classes)

    def addPostscriptNames(self, ufo: RFont) -> RFont:
        lib = RLib()
        lib["public.postscriptNames"] = dict()
        glyphs = [g for g in self.font.glyphs if g.export is True]
        for glyph in glyphs:
            if glyph.productionName is not None and glyph.productionName != glyph.name:
                lib["public.postscriptNames"][glyph.name] = glyph.productionName
        ufo.lib.update(lib)
        return ufo

    def decomposeSmartComponents(self) -> None:
        for glyph in self.font.glyphs:
            if glyph.smartComponentAxes:
                for layer in glyph.layers:
                    if layer.isMasterLayer or layer.isSpecialLayer:
                        if len(layer.components) > 0:
                            for component in layer.components:
                                if component.smartComponentValues:
                                    component.decompose()

    def decomposeCorners(self) -> None:
        for glyph in self.font.glyphs:
            for layer in glyph.layers:
                if layer.isMasterLayer or layer.isSpecialLayer:
                    layer.decomposeCorners()
