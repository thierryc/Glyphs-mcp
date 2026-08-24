"""Declarative Glyphs-format coverage contract for canonical model schema v6.

This module is pure Python.  It classifies the pinned public Glyphs v4 file
format without importing GlyphsApp and gives the native adapter one compact
registry for identity, ordering, field role, impact, and public coverage.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping
from urllib.parse import quote


MODEL_SCHEMA_VERSION = 6
GLYPHS_FORMAT_REVISION = "569244a7181e08fc7c5230bcdfad6b9f7e5ea11f"
GLYPHS_FORMAT_SCHEMA_SHA256 = (
    "3be341e85a574b563a8df2851fe48225e6700c24a827d572c1ad1ec909aa09b0"
)
KNOWLEDGE_REVISION = "GlyphsSDK:{}".format(GLYPHS_FORMAT_REVISION)


# Canonical ``font`` is a compact projection of official document fields and
# the grid settings that Glyphs exposes directly on GSFont.  Capture,
# classification, and replay must consume the same contract: duplicating this
# list allowed ``date`` to be captured and replayed while the mutation kernel
# still classified it as unsupported.
CANONICAL_FONT_SCALAR_FIELDS = (
    "familyName",
    "upm",
    "versionMajor",
    "versionMinor",
    "note",
    "date",
    "grid",
    "gridSubDivision",
)


class FieldRole(str, Enum):
    WRITABLE = "writable"
    DERIVED = "derived"
    READ_ONLY = "read_only"
    OPAQUE = "opaque"
    VOLATILE = "volatile"
    UI_SESSION = "ui_session"


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    COMPLETE_WITH_OPAQUE_PRESERVATION = "complete_with_opaque_preservation"
    PARTIAL = "partial"
    RECOVERY_ONLY = "recovery_only"


@dataclass(frozen=True)
class CanonicalObjectSpec:
    source: str
    fields: tuple[str, ...]
    native_source: str
    serialized_source: str
    canonical_path: tuple[str, ...]
    normalizer: str
    value_type: str
    identity: str = "singleton"
    ordered: bool = False
    shard: str = "root"
    impact: str = "root"
    replay: str = "adapter"
    public_redaction: str = "bounded_summary"
    roles: Mapping[str, FieldRole] = field(default_factory=dict)
    open_container: bool = False

    def role_for(self, name: str) -> FieldRole | None:
        if name in self.fields:
            return self.roles.get(name, FieldRole.WRITABLE)
        if name == "*" and self.open_container:
            return self.roles.get("*", FieldRole.OPAQUE)
        return None


@dataclass(frozen=True)
class CanonicalFieldSpec:
    """One flattened registry declaration consumed by coverage gates.

    Object specifications keep the registry compact; this generated view is
    the per-field contract required by capture, replay and audit tooling.
    """

    official_path: str
    native_path: str
    native_presence_path: str | None
    serialized_path: str
    canonical_path: tuple[str, ...]
    normalizer: str
    value_type: str
    role: FieldRole
    identity: str
    ordered: bool
    shard: str
    impact: str
    replay: str
    public_redaction: str


@dataclass(frozen=True)
class CanonicalSchemaRegistry:
    model_schema_version: int
    knowledge_revision: str
    objects: tuple[CanonicalObjectSpec, ...]

    @property
    def classified_paths(self) -> frozenset[str]:
        values: set[str] = set()
        for spec in self.objects:
            values.update("{}.{}".format(spec.source, name) for name in spec.fields)
            if spec.open_container:
                values.add("{}.*".format(spec.source))
        return frozenset(values)

    def role_for(self, source_path: str) -> FieldRole | None:
        # Match the longest registered object prefix. Official provenance
        # properties begin with a literal dot, producing paths such as
        # ``document..appVersion``; rpartition would lose that distinction.
        for spec in sorted(self.objects, key=lambda value: len(value.source), reverse=True):
            prefix = spec.source + "."
            if source_path.startswith(prefix):
                return spec.role_for(source_path[len(prefix) :])
        return None

    def object_for(self, source: str) -> CanonicalObjectSpec:
        for spec in self.objects:
            if spec.source == source:
                return spec
        raise KeyError("canonical schema source is not registered: {}".format(source))

    def fields_for(
        self,
        source: str,
        *,
        roles: Iterable[FieldRole] | None = None,
    ) -> tuple[str, ...]:
        """Return the reviewed official fields for one registered object.

        Capture and replay adapters use this view for generic records, making
        the coverage registry an executable contract instead of a parallel
        documentation inventory.
        """

        spec = self.object_for(source)
        allowed = frozenset(roles) if roles is not None else None
        return tuple(
            name
            for name in spec.fields
            if allowed is None or spec.role_for(name) in allowed
        )

    def canonical_fields_for(
        self,
        source: str,
        *,
        roles: Iterable[FieldRole] | None = None,
        replays: Iterable[str] | None = None,
    ) -> tuple[str, ...]:
        """Return canonical leaf names selected by their declared role.

        Runtime mutation classification must consume the same role contract as
        the official-format coverage audit.  Returning canonical aliases here
        prevents a field from being described as read-only by the registry but
        remaining writable through a second hand-maintained allow-list.
        """

        spec = self.object_for(source)
        allowed = frozenset(roles) if roles is not None else None
        allowed_replays = frozenset(replays) if replays is not None else None
        aliases = _CANONICAL_FIELD_ALIASES.get(source, {})
        return tuple(
            aliases.get(name, name)
            for name in spec.fields
            if (allowed is None or spec.role_for(name) in allowed)
            and (
                allowed_replays is None
                or _REPLAY_OVERRIDES.get(source, {}).get(name, spec.replay)
                in allowed_replays
            )
        )

    def field_spec_for_canonical(
        self, source: str, canonical_name: str
    ) -> CanonicalFieldSpec:
        """Resolve one canonical leaf to its complete replay contract."""

        matches = tuple(
            field
            for field in self.field_specs
            if field.official_path.startswith(source + ".")
            and field.canonical_path[-1] == canonical_name
        )
        if len(matches) != 1:
            raise KeyError(
                "canonical field is not uniquely registered: {}.{}".format(
                    source, canonical_name
                )
            )
        return matches[0]

    def default_for_canonical(self, source: str, canonical_name: str) -> Any:
        """Return one reviewed official default in canonical spelling.

        ObjectWrapper may omit a selector for a legacy serialized field. The
        live adapter still has to spell absence exactly like flat/package
        capture; defaults therefore belong to this registry seam rather than
        to a replay branch.
        """

        spec = self.object_for(source)
        aliases = _CANONICAL_FIELD_ALIASES.get(source, {})
        matches = tuple(
            name
            for name in spec.fields
            if aliases.get(name, name) == canonical_name
            and name in _CANONICAL_DEFAULTS.get(source, {})
        )
        if len(matches) != 1:
            raise KeyError(
                "canonical field has no unique reviewed default: {}.{}".format(
                    source, canonical_name
                )
            )
        return copy.deepcopy(_CANONICAL_DEFAULTS[source][matches[0]])

    def serialized_default_for_archive_path(
        self, path: Iterable[str | int]
    ) -> tuple[bool, Any]:
        """Resolve one reviewed official omission default for native proof.

        Glyphs may serialize an official default explicitly after copying a
        native entity even when the original package omitted it. Canonical
        equality already proves the saved-document meaning; this registry
        seam lets native archive proof treat only pinned official defaults as
        omission-equivalent. Unknown and ambiguous fields remain strict.
        """

        parts = tuple(str(part) for part in path)
        if not parts:
            return False, None
        field_name = parts[-1]
        tokens = {part.lower() for part in parts}
        candidates: list[tuple[int, str, Any]] = []
        for source, defaults in _OFFICIAL_SERIALIZED_DEFAULTS.items():
            if field_name not in defaults:
                continue
            spec = self.object_for(source)
            source_name = source.rsplit(".", 1)[-1]
            hints = {
                source_name.lower(),
                (source_name + "s").lower(),
                *(
                    str(part).lower()
                    for part in spec.canonical_path
                    if part != "*"
                ),
            }
            score = len(tokens.intersection(hints))
            candidates.append((score, source, defaults[field_name]))
        if not candidates:
            return False, None
        best_score = max(candidate[0] for candidate in candidates)
        best = [candidate for candidate in candidates if candidate[0] == best_score]
        if len(best) != 1 or (best_score == 0 and len(candidates) != 1):
            return False, None
        return True, copy.deepcopy(best[0][2])

    def native_field_for_canonical(
        self, source: str, canonical_name: str
    ) -> str:
        """Resolve one canonical leaf to its reviewed native property name."""

        spec = self.object_for(source)
        matches = []
        canonical_aliases = _CANONICAL_FIELD_ALIASES.get(source, {})
        native_aliases = _NATIVE_FIELD_ALIASES.get(source, {})
        for official_name in spec.fields:
            candidate = canonical_aliases.get(official_name, official_name)
            if candidate == canonical_name:
                matches.append(native_aliases.get(official_name, official_name))
        if len(matches) != 1:
            raise KeyError(
                "canonical field is not uniquely registered: {}.{}".format(
                    source, canonical_name
                )
            )
        return matches[0]

    def native_field_for_official(
        self, source: str, official_name: str
    ) -> str:
        """Resolve one official serialized leaf to its reviewed native name."""

        spec = self.object_for(source)
        if official_name not in spec.fields:
            raise KeyError(
                "official field is not registered: {}.{}".format(
                    source, official_name
                )
            )
        return _NATIVE_FIELD_ALIASES.get(source, {}).get(
            official_name, official_name
        )

    def native_presence_field_for_canonical(
        self, source: str, canonical_name: str
    ) -> str | None:
        """Return the native explicit-override flag for an optional field.

        Several ``GSGlyph`` getters expose a GlyphData-derived effective value
        even when the corresponding property is absent from the saved font.
        Their ``store*`` flags are therefore part of the adapter boundary that
        maps serialized absence to canonical ``None``.  They are not separate
        saved-document fields and never enter the fingerprint themselves.
        """

        spec = self.object_for(source)
        canonical_aliases = _CANONICAL_FIELD_ALIASES.get(source, {})
        matches = [
            official_name
            for official_name in spec.fields
            if canonical_aliases.get(official_name, official_name) == canonical_name
        ]
        if len(matches) != 1:
            return None
        return _NATIVE_PRESENCE_FIELD_ALIASES.get(source, {}).get(matches[0])

    def canonical_value_for_official(
        self, source: str, official_name: str, value: Any
    ) -> Any:
        """Normalize one official serialized enum to its native semantic value.

        Glyphs' v4 file format deliberately uses readable enum names while
        the ObjectWrapper exposes several of the same fields as integers.
        Keeping this translation in the schema registry gives live, flat, and
        package sources one representation and prevents replay code from
        accumulating domain-specific string conversions.
        """

        values = _CANONICAL_VALUE_ALIASES.get(source, {}).get(official_name)
        if values is None or value is None:
            return value
        if value in values.values():
            return value
        if value not in values:
            raise ValueError(
                "unregistered official enum value: {}.{}={!r}".format(
                    source, official_name, value
                )
            )
        return values[value]

    @property
    def field_specs(self) -> tuple[CanonicalFieldSpec, ...]:
        result: list[CanonicalFieldSpec] = []
        for spec in self.objects:
            names = spec.fields + (("*",) if spec.open_container else ())
            for name in names:
                role = spec.role_for(name)
                if role is None:
                    continue
                result.append(
                    CanonicalFieldSpec(
                        official_path="{}.{}".format(spec.source, name),
                        native_path="{}.{}".format(
                            spec.native_source,
                            _NATIVE_FIELD_ALIASES.get(spec.source, {}).get(name, name),
                        ),
                        native_presence_path=(
                            "{}.{}".format(
                                spec.native_source,
                                _NATIVE_PRESENCE_FIELD_ALIASES[spec.source][name],
                            )
                            if name
                            in _NATIVE_PRESENCE_FIELD_ALIASES.get(spec.source, {})
                            else None
                        ),
                        serialized_path="{}.{}".format(spec.serialized_source, name),
                        canonical_path=spec.canonical_path
                        + (_CANONICAL_FIELD_ALIASES.get(spec.source, {}).get(name, name),),
                        normalizer=spec.normalizer,
                        value_type=spec.value_type,
                        role=role,
                        identity=spec.identity,
                        ordered=spec.ordered,
                        shard=spec.shard,
                        impact=spec.impact,
                        replay=_REPLAY_OVERRIDES.get(spec.source, {}).get(
                            name, spec.replay
                        ),
                        public_redaction=spec.public_redaction,
                    )
                )
        return tuple(result)


@dataclass(frozen=True)
class SchemaCoverageAudit:
    classified_count: int
    unclassified: tuple[str, ...]
    stale_registry_entries: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.unclassified and not self.stale_registry_entries


@dataclass(frozen=True)
class CanonicalCoverage:
    status: CoverageStatus
    opaque_paths: tuple[tuple[str, ...], ...] = ()
    unsupported_paths: tuple[tuple[str, ...], ...] = ()
    knowledge_revision: str = KNOWLEDGE_REVISION

    def __post_init__(self) -> None:
        if self.status is CoverageStatus.COMPLETE and (
            self.opaque_paths or self.unsupported_paths
        ):
            raise ValueError("complete canonical coverage cannot contain uncovered paths")
        if (
            self.status is CoverageStatus.COMPLETE_WITH_OPAQUE_PRESERVATION
            and self.unsupported_paths
        ):
            raise ValueError("opaque-preserved coverage cannot contain unsupported paths")

    @classmethod
    def complete(cls) -> "CanonicalCoverage":
        return cls(status=CoverageStatus.COMPLETE)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "modelSchemaVersion": MODEL_SCHEMA_VERSION,
            "status": self.status.value,
            "opaqueChangeCount": len(self.opaque_paths),
            "unsupportedChangeCount": len(self.unsupported_paths),
            "knowledgeRevision": self.knowledge_revision,
        }


def deterministic_occurrence_id(kind: str, semantic_key: Any, occurrence: int) -> str:
    if int(occurrence) < 0:
        raise ValueError("canonical occurrence cannot be negative")
    key = quote(str(semantic_key or ""), safe="._-")
    return "{}:{}:{}".format(str(kind), key, int(occurrence))


def _fields(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.split() if part)


# This compact inventory is deliberately independent from the vendored JSON
# schema. Updating the official schema therefore creates an unclassified path
# until this registry is reviewed. Dynamic dictionary containers are the only
# wildcard entries.
_OFFICIAL_FIELDS: Mapping[str, tuple[str, ...]] = {
    "document": _fields(
        ".appVersion .formatVersion DisplayStrings axes classes customParameters date "
        "featurePrefixes features fontMaster glyphs instances kerningContext "
        "kerningLTR kerningRTL kerningVertical metrics note numbers properties "
        "settings stems unitsPerEm userData versionMajor versionMinor"
    ),
    "document.settings": _fields(
        "dependencies disablesAutomaticAlignment disablesNiceNames fontType gridLength "
        "gridSubDivision keepAlternatesTogether keyboardIncrement keyboardIncrementBig "
        "keyboardIncrementHuge previewRemoveOverlap snapToObjects"
    ),
    "definition.anchor": _fields("attr locked name orientation pos"),
    "definition.annotation": _fields("angle pos text type width"),
    "definition.axis": _fields("default hidden name names tag userData"),
    "definition.class": _fields("automatic code disabled name notes"),
    "definition.component": _fields(
        "alignment anchor angle attr keepWeight locked masterId orientation piece pos ref "
        "scale slant traverseAnchors"
    ),
    "definition.customParameter": _fields("disabled name value"),
    "definition.feature": _fields("automatic code disabled labels notes tag"),
    "definition.featurePrefix": _fields("automatic code disabled name notes"),
    "definition.fontMaster": _fields(
        "active axesValues customParameters guides iconName id metricValues name "
        "numberValues properties stemValues tempData userData visible"
    ),
    "definition.glyph": _fields(
        "axes case category color direction export glyphname group groupIdx kernBottom "
        "kernLeft kernRight kernTop lastChange layers locked metricBottom metricLeft "
        "metricRight metricTop metricVertOrigin metricVertWidth metricWidth note "
        "partsSettings production script sortName sortNameKeep subCategory tags unicode userData"
    ),
    "definition.gradient": _fields(
        "angle center colors controlRadius end endRadius extend start startAngle startRadius type"
    ),
    "definition.guide": _fields(
        "angle attr filter grid length lockAngle locked name orientation pos showMeasurement "
        "size slope type"
    ),
    "definition.hint": _fields(
        "horizontal name options origin other1 other2 place scale settings stem target type"
    ),
    "definition.image": _fields(
        "alpha angle attr crop imagePath imageURL locked pos scale slant"
    ),
    "definition.infoProperty": _fields("key value values"),
    "definition.infoValue": _fields("language value"),
    "definition.instance": _fields(
        "axesValues customParameters exports id instanceInterpolations isBold isItalic "
        "linkStyle manualInterpolation properties type userData visible weightClass widthClass"
    ),
    "definition.layer": _fields(
        "active anchors annotations associatedMasterId attr background backgroundImage color "
        "guides hints layerId metricBottom metricLeft metricRight metricTop metricVertOrigin "
        "metricVertWidth metricWidth name partSelection shapes userData vertOrigin vertWidth "
        "visible width"
    ),
    "definition.layer.background": _fields(
        "anchors annotations backgroundImage guides hints shapes"
    ),
    "definition.layerAttr": _fields("axisRules color colorPalette coordinates sbixSize svg"),
    "definition.metric": _fields("filter horizontal name type"),
    "definition.metricStore": _fields("over pos"),
    "definition.nodeAttr": _fields("hoi userData"),
    "definition.palettes": _fields("names palettes"),
    "definition.partProperty": _fields("bottomValue name topValue"),
    "definition.path": _fields("attr closed locked nodes"),
    "definition.shadow": _fields("blur color offsetX offsetY"),
    "definition.shapeAttr": _fields(
        "color compositing fill fillColor gradient group hidden lineCapEnd lineCapStart "
        "lineJoin mask opacity reversePaths shadow shadowIn strokeColor strokeGradient "
        "strokeHeight strokePos strokeWidth"
    ),
    "definition.shapeGroup": _fields("attr groupId"),
}

_OPEN_CONTAINERS = {
    "document.settings.dependencies",
    "definition.attr",
    "definition.component.piece",
    "definition.instance.instanceInterpolations",
    "definition.kerning",
    "definition.kerningContext",
    "definition.layer.partSelection",
    "definition.layerAttr",
    "definition.nodeAttr.hoi",
    "definition.palettes.names",
    "definition.shapeAttr",
}

_ROLE_OVERRIDES: Mapping[str, Mapping[str, FieldRole]] = {
    "document": {
        ".appVersion": FieldRole.VOLATILE,
        ".formatVersion": FieldRole.VOLATILE,
        "DisplayStrings": FieldRole.UI_SESSION,
    },
    "definition.fontMaster": {"tempData": FieldRole.VOLATILE},
    "definition.glyph": {
        "lastChange": FieldRole.DERIVED,
        # ``partsSettings`` remains accepted by the official v4 schema for
        # legacy Smart Glyph data, but Glyphs 4 exposes no corresponding
        # GSGlyph selector.  Added/deleted glyphs preserve it through their
        # detached native template or tombstone; retained-object edits cannot
        # be replayed through the public live API and therefore fail closed.
        "partsSettings": FieldRole.READ_ONLY,
    },
}

_REPLAY_OVERRIDES: Mapping[str, Mapping[str, str]] = {
    "definition.feature": {
        # Glyphs 4 build 4004 exposes the official serialized ``labels``
        # array as one GSInfoValueLocalized through ``label``/``setLabel:``;
        # ObjectWrapper's older plural setter is not available in the host.
        "labels": "info_value_label",
    },
    "definition.glyph": {
        "partsSettings": "native_template_only",
    },
}

_CANONICAL_DEFAULTS: Mapping[str, Mapping[str, Any]] = {
    "definition.glyph": {
        "partsSettings": [],
    },
}

# Defaults below retain the official serialized spelling. They are used only
# to distinguish an omitted public field from the same explicit default in
# exact native-archive proof. Adding an entry is a reviewed knowledge change;
# no unregistered native field can inherit this behavior.
_OFFICIAL_SERIALIZED_DEFAULTS: Mapping[str, Mapping[str, Any]] = {
    "definition.fontMaster": {
        "visible": True,
    },
    "definition.layer": {
        "active": True,
        "anchors": [],
        "annotations": [],
        "attr": {},
        "guides": [],
        "hints": [],
        "name": "",
        "shapes": [],
        "userData": {},
        "vertOrigin": 0,
        "vertWidth": 0,
        "visible": False,
    },
}

_OPEN_CONTAINER_ROLES: Mapping[str, FieldRole] = {
    source: FieldRole.WRITABLE for source in _OPEN_CONTAINERS
}

_OBJECT_POLICIES: Mapping[str, tuple[tuple[str, ...], str, bool, str]] = {
    "definition.axis": (("axes",), "tag", True, "root_entity"),
    "definition.class": (("classes",), "name", True, "root_entity"),
    "definition.feature": (("features",), "tag", True, "root_entity"),
    "definition.featurePrefix": (
        ("featurePrefixes",),
        "name",
        True,
        "root_entity",
    ),
    "definition.fontMaster": (("masters",), "id", True, "root_entity"),
    "definition.instance": (("instances",), "id", True, "root_entity"),
    "definition.glyph": (("glyphs",), "glyphname", True, "glyph"),
    "definition.layer": (("glyphs", "*", "layers"), "layerId", True, "layer"),
    "definition.anchor": (("glyphs", "*", "layers", "*", "anchors"), "name_occurrence", True, "layer"),
    "definition.customParameter": (("*", "customParameters"), "name_occurrence", True, "owner"),
    "definition.metric": (("metrics",), "semantic_occurrence", True, "root_entity"),
}

_NATIVE_SOURCES: Mapping[str, str] = {
    "document": "GSFont",
    "document.settings": "GSFont.settings",
    "definition.anchor": "GSAnchor",
    "definition.annotation": "GSAnnotation",
    "definition.axis": "GSAxis",
    "definition.class": "GSClass",
    "definition.component": "GSComponent",
    "definition.customParameter": "GSCustomParameter",
    "definition.feature": "GSFeature",
    "definition.featurePrefix": "GSFeaturePrefix",
    "definition.fontMaster": "GSFontMaster",
    "definition.glyph": "GSGlyph",
    "definition.guide": "GSGuide",
    "definition.hint": "GSHint",
    "definition.image": "GSBackgroundImage",
    "definition.instance": "GSInstance",
    "definition.layer": "GSLayer",
    "definition.layer.background": "GSBackgroundLayer",
    "definition.metric": "GSMetric",
    "definition.path": "GSPath",
    "definition.shapeGroup": "GSShapeGroup",
}

_NATIVE_FIELD_ALIASES: Mapping[str, Mapping[str, str]] = {
    "document": {
        "fontMaster": "masters",
        "kerningLTR": "kerning",
        "unitsPerEm": "upm",
    },
    "definition.anchor": {"attr": "attributes", "pos": "position"},
    "definition.component": {
        "angle": "rotation",
        "attr": "attributes",
        "masterId": "componentMasterId",
        "piece": "smartComponentValues",
        "pos": "position",
        "ref": "componentName",
    },
    # The file format calls the feature identity ``tag``; ObjectWrapper uses
    # ``GSFeature.name`` for that same four-character value.
    "definition.feature": {"labels": "label", "tag": "name"},
    "definition.glyph": {
        "glyphname": "name",
        "kernBottom": "bottomKerningGroup",
        "kernLeft": "leftKerningGroup",
        "kernRight": "rightKerningGroup",
        "kernTop": "topKerningGroup",
        "metricBottom": "bottomMetricsKey",
        "metricLeft": "leftMetricsKey",
        "metricRight": "rightMetricsKey",
        "metricTop": "topMetricsKey",
        "metricVertOrigin": "vertOriginMetricsKey",
        "metricVertWidth": "vertWidthMetricsKey",
        "metricWidth": "widthMetricsKey",
        "partsSettings": "propertyList.partsSettings",
        "production": "productionName",
    },
    "definition.guide": {
        "attr": "attributes",
        "pos": "position",
        "slope": "hasSlope",
    },
    "definition.hint": {
        "origin": "originIndex",
        "target": "targetIndex",
        "other1": "otherIndex1",
        "other2": "otherIndex2",
    },
    "definition.image": {"attr": "attributes", "pos": "position"},
    "definition.layer": {
        "associatedMasterId": "associatedMasterId",
        "attr": "attributes",
        "layerId": "layerId",
        "metricBottom": "bottomMetricsKey",
        "metricLeft": "leftMetricsKey",
        "metricRight": "rightMetricsKey",
        "metricTop": "topMetricsKey",
        "metricVertOrigin": "vertOriginMetricsKey",
        "metricVertWidth": "vertWidthMetricsKey",
        "metricWidth": "widthMetricsKey",
    },
    "definition.path": {"attr": "attributes"},
    "definition.shapeGroup": {"attr": "attributes"},
}

# A small set of GSGlyph properties are serialized only when their matching
# ``store*`` flag is enabled.  The ordinary getter nevertheless returns the
# effective GlyphData-derived value when the flag is disabled.  Keep this
# presence contract beside the native aliases so every adapter can preserve
# the semantic difference between an absent override and an explicit value.
# The flags are native evidence, not additional saved-document fields.
_NATIVE_PRESENCE_FIELD_ALIASES: Mapping[str, Mapping[str, str]] = {
    "definition.glyph": {
        "case": "storeCase",
        "category": "storeCategory",
        "direction": "storeDirection",
        "group": "storeGroup",
        "groupIdx": "storeGroupIdx",
        "production": "storeProductionName",
        "script": "storeScript",
        "sortName": "storeSortName",
        "sortNameKeep": "storeSortName",
        "subCategory": "storeSubCategory",
    },
}

# Serialized format names are sometimes compact spellings rather than the
# semantic keys exposed by the canonical model. Keep that translation beside
# the native aliases so the generated registry describes all three paths
# accurately and adapters can resolve native fields from canonical leaves.
_CANONICAL_FIELD_ALIASES: Mapping[str, Mapping[str, str]] = {
    "document": {
        "fontMaster": "masters",
        "kerningLTR": "kerning",
        "unitsPerEm": "upm",
    },
    "definition.anchor": {"attr": "attributes", "pos": "position"},
    "definition.component": {
        "attr": "attributes",
        "pos": "position",
        "ref": "name",
    },
    "definition.glyph": {
        "axes": "smartAxes",
        "glyphname": "name",
        "kernBottom": "bottomKerningGroup",
        "kernLeft": "leftKerningGroup",
        "kernRight": "rightKerningGroup",
        "kernTop": "topKerningGroup",
        "metricBottom": "bottomMetricsKey",
        "metricLeft": "leftMetricsKey",
        "metricRight": "rightMetricsKey",
        "metricTop": "topMetricsKey",
        "metricVertOrigin": "vertOriginMetricsKey",
        "metricVertWidth": "vertWidthMetricsKey",
        "metricWidth": "widthMetricsKey",
        "production": "productionName",
    },
    "definition.guide": {"attr": "attributes", "pos": "position"},
    "definition.image": {"attr": "attributes", "pos": "position"},
    "definition.layer": {
        "attr": "attributes",
        "metricBottom": "bottomMetricsKey",
        "metricLeft": "leftMetricsKey",
        "metricRight": "rightMetricsKey",
        "metricTop": "topMetricsKey",
        "metricVertOrigin": "vertOriginMetricsKey",
        "metricVertWidth": "vertWidthMetricsKey",
        "metricWidth": "widthMetricsKey",
    },
    "definition.path": {"attr": "attributes"},
}

# Official v4 files spell these values as strings; Glyphs' native API exposes
# the same semantic state as compact integer enums. Values are pinned to the
# reviewed Glyphs 4 SDK/runtime contract. Unknown future spellings fail closed
# through ``canonical_value_for_official`` instead of silently becoming a new
# fingerprint representation.
_CANONICAL_VALUE_ALIASES: Mapping[str, Mapping[str, Mapping[Any, Any]]] = {
    "document.settings": {
        "fontType": {
            "default": 0,
            "variable": 1,
            "layerFont": 2,
            "iconSet": 3,
        },
    },
    "definition.anchor": {
        "orientation": {"left": 0, "center": 1, "right": 2},
    },
    "definition.annotation": {
        "type": {"Text": 1, "Arrow": 2, "Circle": 3, "Plus": 4, "Minus": 5},
    },
    "definition.component": {
        "orientation": {"left": 0, "center": 1, "right": 2},
    },
    "definition.glyph": {
        "case": {
            "noCase": 0,
            "upper": 1,
            "lower": 2,
            "smallCaps": 3,
            "minor": 4,
            "other": 5,
        },
        "direction": {"BIDI": 1, "LTR": 0, "RTL": 2, "VTR": 4, "VTL": 8},
    },
    "definition.guide": {
        "orientation": {"left": 0, "center": 1, "right": 2},
        "type": {"Line": 0, "Circle": 1, "Rect": 2},
    },
    "definition.hint": {
        "type": {
            "Tag": -2,
            "TopGhost": -1,
            "Stem": 0,
            "BottomGhost": 1,
            "Flex": 2,
            "TTSnap": 3,
            "TTStem": 4,
            "TTShift": 5,
            "TTInterpolate": 6,
            "Unknown": 7,
            "TTDiagonal": 8,
            "TTDelta": 9,
            "Corner": 16,
            "Cap": 17,
            "Brush": 18,
            "Segment": 19,
            "Head": 20,
            "Auto": 127,
        },
    },
    "definition.metric": {
        "type": {
            "ascender": 1,
            "cap height": 2,
            "slant height": 3,
            "x-height": 4,
            "midHeight": 5,
            "bodyHeight": 6,
            "descender": 7,
            "baseline": 8,
            "italic angle": 9,
            "italic slope": 10,
        },
    },
}


def _registry() -> CanonicalSchemaRegistry:
    objects = []
    for source, fields in _OFFICIAL_FIELDS.items():
        path, identity, ordered, shard = _OBJECT_POLICIES.get(
            source, ((source.replace("definition.", ""),), "singleton", False, "root")
        )
        objects.append(
            CanonicalObjectSpec(
                source=source,
                fields=fields,
                native_source=_NATIVE_SOURCES.get(source, source),
                serialized_source=source,
                canonical_path=path,
                normalizer="canonical_json",
                value_type="official_schema",
                identity=identity,
                ordered=ordered,
                shard=shard,
                impact=shard,
                replay="adapter",
                public_redaction="bounded_summary",
                roles={
                    **dict(_ROLE_OVERRIDES.get(source, {})),
                    **(
                        {"*": _OPEN_CONTAINER_ROLES[source]}
                        if source in _OPEN_CONTAINERS
                        else {}
                    ),
                },
                open_container=source in _OPEN_CONTAINERS,
            )
        )
    for source in sorted(_OPEN_CONTAINERS - set(_OFFICIAL_FIELDS)):
        objects.append(
            CanonicalObjectSpec(
                source=source,
                fields=(),
                native_source=_NATIVE_SOURCES.get(source, source),
                serialized_source=source,
                canonical_path=(source,),
                normalizer="recursive_json_safe",
                value_type="wildcard_mapping",
                impact="owner",
                replay="mapping",
                public_redaction="count_and_fingerprint",
                roles={"*": _OPEN_CONTAINER_ROLES[source]},
                open_container=True,
            )
        )
    return CanonicalSchemaRegistry(
        model_schema_version=MODEL_SCHEMA_VERSION,
        knowledge_revision=KNOWLEDGE_REVISION,
        objects=tuple(objects),
    )


CANONICAL_SCHEMA = _registry()


def _walk_schema(node: Any, path: str, result: set[str]) -> None:
    if not isinstance(node, Mapping):
        return
    properties = node.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            child_path = "{}.{}".format(path, name)
            result.add(child_path)
            _walk_schema(child, child_path, result)
    if node.get("patternProperties") or node.get("additionalProperties") not in (
        None,
        False,
    ):
        result.add("{}.*".format(path))
    for branch_name in ("oneOf", "anyOf", "allOf"):
        branches = node.get(branch_name)
        if isinstance(branches, Iterable) and not isinstance(branches, (str, bytes)):
            for branch in branches:
                _walk_schema(branch, path, result)


def official_schema_inventory(schema: Mapping[str, Any]) -> frozenset[str]:
    result: set[str] = set()
    _walk_schema(schema, "document", result)
    definitions = schema.get("$defs") or schema.get("definitions") or {}
    if isinstance(definitions, Mapping):
        for name, definition in definitions.items():
            _walk_schema(definition, "definition.{}".format(name), result)
    return frozenset(result)


def audit_official_schema(
    schema: Mapping[str, Any], registry: CanonicalSchemaRegistry
) -> SchemaCoverageAudit:
    inventory = official_schema_inventory(schema)
    classified = registry.classified_paths
    return SchemaCoverageAudit(
        classified_count=len(inventory & classified),
        unclassified=tuple(sorted(inventory - classified)),
        stale_registry_entries=tuple(sorted(classified - inventory)),
    )


def canonical_coverage_summary(schema: Mapping[str, Any]) -> dict[str, Any]:
    audit = audit_official_schema(schema, CANONICAL_SCHEMA)
    roles = {role.value: 0 for role in FieldRole}
    for path in official_schema_inventory(schema):
        role = CANONICAL_SCHEMA.role_for(path)
        if role is not None:
            roles[role.value] += 1
    return {
        "modelSchemaVersion": MODEL_SCHEMA_VERSION,
        "knowledgeRevision": KNOWLEDGE_REVISION,
        "officialPropertyCount": audit.classified_count + len(audit.unclassified),
        "classifiedPropertyCount": audit.classified_count,
        "unclassifiedPropertyCount": len(audit.unclassified),
        "staleRegistryEntryCount": len(audit.stale_registry_entries),
        "registryObjectCount": len(CANONICAL_SCHEMA.objects),
        "roles": roles,
        "status": "complete" if audit.complete else "partial",
    }


def render_canonical_coverage_markdown(schema: Mapping[str, Any]) -> str:
    summary = canonical_coverage_summary(schema)
    role_lines = "\n".join(
        "- `{}`: {}".format(name, count)
        for name, count in sorted(summary["roles"].items())
    )
    return """# Glyphs MCP canonical schema v6 coverage

This report is generated from the pinned official Glyphs File Format v4 JSON
schema. It describes registry classification, not a byte-for-byte mirror of
the serialized plist/package layout.

- Model schema: `{modelSchemaVersion}`
- Knowledge revision: `{knowledgeRevision}`
- Status: `{status}`
- Official properties and wildcard containers: {officialPropertyCount}
- Classified: {classifiedPropertyCount}
- Unclassified: {unclassifiedPropertyCount}
- Stale registry entries: {staleRegistryEntryCount}
- Registry object specifications: {registryObjectCount}

## Field roles

{role_lines}

Any unclassified official field blocks release qualification. Upstream drift
also blocks signing until the registry and this generated report are reviewed.
""".format(role_lines=role_lines, **summary)


__all__ = [
    "CANONICAL_FONT_SCALAR_FIELDS",
    "CANONICAL_SCHEMA",
    "GLYPHS_FORMAT_REVISION",
    "GLYPHS_FORMAT_SCHEMA_SHA256",
    "KNOWLEDGE_REVISION",
    "MODEL_SCHEMA_VERSION",
    "CanonicalCoverage",
    "CanonicalFieldSpec",
    "CanonicalObjectSpec",
    "CanonicalSchemaRegistry",
    "CoverageStatus",
    "FieldRole",
    "SchemaCoverageAudit",
    "audit_official_schema",
    "canonical_coverage_summary",
    "deterministic_occurrence_id",
    "official_schema_inventory",
    "render_canonical_coverage_markdown",
]
