"""Catalog-driven FastMCP transport for the generic v2 contract."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Set

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ..application import GlyphsMCPApplication
from ..catalog import MODEL_AND_APP, TOOL_DEFINITIONS, ToolDefinition
from ..versions import SERVER_NAME, SERVER_VERSION


Sha256Fingerprint = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
PageSize = Annotated[int, Field(ge=1, le=500)]
EntityKind = Literal[
    "document",
    "font",
    "axis",
    "master",
    "instance",
    "glyph",
    "layer",
    "shape",
    "anchor",
    "kerning",
    "feature",
    "class",
    "prefix",
    "metric",
    "stem",
    "number",
]


def _compact_parameter_schema(value: Any) -> Any:
    if isinstance(value, dict):
        compact = {
            key: _compact_parameter_schema(item)
            for key, item in value.items()
            if key not in {"title", "discriminator"}
            and not (key == "default" and item is None)
        }
        if compact.get("type") == "object" and "properties" in compact:
            compact.pop("description", None)
            compact.setdefault("additionalProperties", False)
        return compact
    if isinstance(value, list):
        return [_compact_parameter_schema(item) for item in value]
    return value


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Projection(StrictInputModel):
    fields: List[str] = Field(min_length=1, max_length=64)
    includeProvenance: bool = True


class EntitySelector(StrictInputModel):
    entity: EntityKind
    ids: Optional[List[str]] = None
    parent: Dict[str, JsonValue] = Field(default_factory=dict)
    where: Dict[str, JsonValue] = Field(default_factory=dict)
    orderBy: str = "identity"
    descending: bool = False
    pageSize: PageSize = 100
    cursor: Optional[str] = None
    relations: Optional[List["EntityRelation"]] = None


class EntityRelation(StrictInputModel):
    name: str = Field(min_length=1, max_length=80)
    selector: EntitySelector
    projection: Projection


EntitySelector.model_rebuild()


class LiteralOperand(StrictInputModel):
    kind: Literal["literal"]
    value: JsonValue


class FieldOperand(StrictInputModel):
    kind: Literal["field"]
    selector: EntitySelector
    field: str = Field(min_length=1)


class ReferenceOperand(StrictInputModel):
    kind: Literal["reference"]
    selector: EntitySelector


class Constraint(StrictInputModel):
    label: Optional[str] = None
    phase: Literal["before", "after"] = "before"
    left: LiteralOperand | FieldOperand | ReferenceOperand
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte", "within", "in_range"]
    right: LiteralOperand | FieldOperand | ReferenceOperand
    tolerance: Optional[Annotated[float, Field(allow_inf_nan=False, ge=0)]] = None


class TranslationDelta(StrictInputModel):
    x: Annotated[float, Field(allow_inf_nan=False)] = 0
    y: Annotated[float, Field(allow_inf_nan=False)] = 0


class ChangeOperation(StrictInputModel):
    op: Literal["set", "translate", "insert", "remove", "move", "duplicate"]
    target: EntitySelector
    field: Optional[str] = None
    value: Optional[JsonValue] = None
    delta: Optional[TranslationDelta] = None
    index: Optional[Annotated[int, Field(ge=0)]] = None
    newId: Optional[str] = None
    overrides: Optional[Dict[str, JsonValue]] = None
    quantizer: Literal["exact", "grid"] = "exact"

    @model_validator(mode="after")
    def closed_operation_shape(self) -> "ChangeOperation":
        supplied = set(self.model_fields_set) - {"op", "target"}
        allowed = {
            "set": {"field", "value", "quantizer"},
            "translate": {"delta", "quantizer"},
            "insert": {"field", "value", "index", "newId"},
            "remove": set(),
            "move": {"index"},
            "duplicate": {"newId", "overrides", "index"},
        }[self.op]
        unexpected = supplied - allowed
        if unexpected:
            raise ValueError(
                "{} does not accept {}".format(
                    self.op, ", ".join(sorted(unexpected))
                )
            )
        if self.op == "set" and (not self.field or "value" not in supplied):
            raise ValueError("set requires field and value")
        if self.op == "translate" and self.delta is None:
            raise ValueError("translate requires delta")
        if self.op == "insert" and "value" not in supplied:
            raise ValueError("insert requires value")
        if self.op == "move" and self.index is None:
            raise ValueError("move requires index")
        if self.op == "duplicate" and not self.newId:
            raise ValueError("duplicate requires newId")
        return self


def _transport_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_unset=True)
    if isinstance(value, list):
        return [_transport_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_transport_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _transport_value(item) for key, item in value.items()}
    return value


class ToolHandlers:
    """Concrete typed signatures for the complete public v2 surface."""

    def __init__(self, application: GlyphsMCPApplication) -> None:
        self._application = application

    def _invoke(self, tool: str, arguments: Dict[str, Any]) -> ToolResult:
        response = self._application.invoke(
            tool,
            {
                key: _transport_value(value)
                for key, value in arguments.items()
                if key != "self" and value is not None
            },
        )
        return ToolResult(content=response.summary, structured_content=response.to_dict())

    async def get_server_info(self) -> ToolResult:
        return self._invoke("get_server_info", {})

    async def list_documents(self) -> ToolResult:
        return self._invoke("list_documents", {})

    async def read_document(
        self,
        documentId: str,
        selector: EntitySelector,
        projection: Projection,
    ) -> ToolResult:
        return self._invoke("read_document", locals())

    async def evaluate_constraints(
        self,
        documentId: str,
        constraints: List[Constraint],
    ) -> ToolResult:
        return self._invoke("evaluate_constraints", locals())

    async def preview_change(
        self,
        documentId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
        operations: List[ChangeOperation],
        constraints: Optional[List[Constraint]] = None,
    ) -> ToolResult:
        return self._invoke("preview_change", locals())

    async def apply_change(
        self,
        documentId: str,
        previewId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
        reason: Annotated[str, Field(min_length=1, max_length=1000)],
    ) -> ToolResult:
        return self._invoke("apply_change", locals())

    async def get_operation(
        self,
        operationId: str,
        pageSize: PageSize = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("get_operation", locals())

    async def list_history(
        self,
        documentId: str,
        pageSize: PageSize = 100,
    ) -> ToolResult:
        return self._invoke("list_history", locals())

    async def revert_change(
        self,
        documentId: str,
        operationId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
    ) -> ToolResult:
        return self._invoke("revert_change", locals())

    async def search_knowledge(
        self,
        query: Annotated[str, Field(min_length=1, max_length=500)],
        topics: Optional[List[str]] = None,
        authorities: Optional[List[Literal["authoritative", "practice", "heuristic"]]] = None,
        glyphsVersions: Optional[List[str]] = None,
        pageSize: Annotated[int, Field(ge=1, le=100)] = 20,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("search_knowledge", locals())

    async def get_knowledge(
        self,
        entryIds: Annotated[List[str], Field(min_length=1, max_length=20)],
    ) -> ToolResult:
        return self._invoke("get_knowledge", locals())

    async def execute_python(
        self,
        mode: Literal["read_only", "staged_document", "live_open_world"],
        reason: Optional[str] = None,
        code: Optional[str] = None,
        documentId: Optional[str] = None,
        glyphName: Optional[str] = None,
        masterId: Optional[str] = None,
        layerId: Optional[str] = None,
        expectedDocumentFingerprint: Optional[Sha256Fingerprint] = None,
        approvalId: Optional[str] = None,
        confirm: bool = False,
        maxOutputChars: Annotated[int, Field(ge=1, le=8192)] = 8192,
        maxErrorChars: Annotated[int, Field(ge=1, le=8192)] = 8192,
    ) -> ToolResult:
        return self._invoke("execute_python", locals())

    async def preview_export(
        self,
        documentId: str,
        destination: str,
        overwritePolicy: Literal["fail_if_nonempty", "replace_if_match"] = "fail_if_nonempty",
        compatibilityMode: Literal["component_preserving", "decomposed_export"] = "component_preserving",
        expectedDestinationFingerprint: Optional[Sha256Fingerprint] = None,
        acknowledgedFindingIds: Optional[List[str]] = None,
    ) -> ToolResult:
        return self._invoke("preview_export", locals())

    async def apply_export(self, previewId: str) -> ToolResult:
        return self._invoke("apply_export", locals())

    async def save_document(
        self,
        documentId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
        confirm: bool,
        reason: Annotated[str, Field(min_length=1, max_length=1000)],
        destination: Optional[str] = None,
        expectedSourceFingerprint: Optional[Sha256Fingerprint] = None,
        overwritePolicy: Literal["fail_if_exists", "replace_if_match"] = "fail_if_exists",
        expectedDestinationFingerprint: Optional[Sha256Fingerprint] = None,
    ) -> ToolResult:
        return self._invoke("save_document", locals())

    async def open_document_view(
        self,
        documentId: str,
        glyphNames: Annotated[List[str], Field(min_length=1, max_length=64)],
        masterId: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("open_document_view", locals())

    async def get_runtime_status(self) -> ToolResult:
        return self._invoke("get_runtime_status", {})

    async def repair_runtime(
        self,
        expectedIncidentId: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ToolResult:
        return self._invoke("repair_runtime", locals())


class CatalogRegistrar:
    """The only v2 component permitted to call FastMCP registration."""

    def __init__(self, server: FastMCP, application: GlyphsMCPApplication) -> None:
        self._server = server
        self._handlers = ToolHandlers(application)
        self._registered: Set[str] = set()

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._registered:
            raise RuntimeError("tool registered more than once: {}".format(definition.name))
        invoke = getattr(self._handlers, definition.handler_name)
        visibility = ["model", "app"] if definition.visibility == MODEL_AND_APP else ["app"]
        tool = self._server.tool(
            name=definition.name,
            title=definition.title,
            description=definition.description,
            output_schema=definition.discovery_output_schema,
            annotations=definition.annotations,
            meta={"ui": {"visibility": visibility}},
        )(invoke)
        tool.parameters = _compact_parameter_schema(tool.parameters)
        self._registered.add(definition.name)

    def register_all(self) -> None:
        for definition in TOOL_DEFINITIONS:
            self.register(definition)

    @property
    def registered_names(self) -> Set[str]:
        return set(self._registered)


def create_server(application: GlyphsMCPApplication) -> FastMCP:
    server = FastMCP(name=SERVER_NAME, version=SERVER_VERSION)
    registrar = CatalogRegistrar(server, application)
    registrar.register_all()
    return server


__all__ = [
    "CatalogRegistrar",
    "ChangeOperation",
    "Constraint",
    "EntitySelector",
    "Projection",
    "ToolHandlers",
    "create_server",
]
