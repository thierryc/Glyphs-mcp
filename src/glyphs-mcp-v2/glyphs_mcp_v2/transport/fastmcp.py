"""Catalog-driven FastMCP transport for the generic v2 contract."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Set, Union

import anyio
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel, model_validator

from ..application import GlyphsMCPApplication
from ..catalog import MODEL_AND_APP, TOOL_DEFINITIONS, ToolDefinition
from ..mechanics_registry import (
    CONSTRAINT_OPERATORS as REGISTRY_CONSTRAINT_OPERATORS,
    ENTITY_KINDS as REGISTRY_ENTITY_KINDS,
    ORDER_TYPES as REGISTRY_ORDER_TYPES,
    PREDICATE_OPERATORS as REGISTRY_PREDICATE_OPERATORS,
    REDUCER_KINDS as REGISTRY_REDUCER_KINDS,
)
from ..versions import SERVER_NAME, SERVER_VERSION


Sha256Fingerprint = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
PageSize = Annotated[int, Field(ge=1, le=500)]
EntityKind = Literal[*tuple(sorted(REGISTRY_ENTITY_KINDS))]
PredicateOperator = Literal[*tuple(sorted(REGISTRY_PREDICATE_OPERATORS))]
OrderType = Literal[*tuple(sorted(REGISTRY_ORDER_TYPES))]
ReducerKind = Literal[*tuple(sorted(REGISTRY_REDUCER_KINDS))]
ConstraintOperator = Literal[*tuple(sorted(REGISTRY_CONSTRAINT_OPERATORS))]


def _compact_parameter_schema(value: Any) -> Any:
    if isinstance(value, dict):
        compact = {
            key: _compact_parameter_schema(item)
            for key, item in value.items()
            if key != "title"
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


class LastSavedComparisonReference(StrictInputModel):
    kind: Literal["last_saved"]


class LocalGitComparisonReference(StrictInputModel):
    kind: Literal["local_git"]
    revision: Annotated[str, Field(min_length=1, max_length=512)]
    repositoryPath: Optional[Annotated[str, Field(min_length=1, max_length=4096)]] = None
    fontPath: Optional[Annotated[str, Field(min_length=1, max_length=4096)]] = None


class GitHubComparisonReference(StrictInputModel):
    kind: Literal["github"]
    repositoryUrl: Annotated[str, Field(min_length=1, max_length=4096)]
    revision: Annotated[str, Field(min_length=1, max_length=512)]
    fontPath: Optional[Annotated[str, Field(min_length=1, max_length=4096)]] = None


ComparisonReference = Annotated[
    Union[
        LastSavedComparisonReference,
        LocalGitComparisonReference,
        GitHubComparisonReference,
    ],
    Field(discriminator="kind"),
]


class Predicate(StrictInputModel):
    op: PredicateOperator
    field: Optional[str] = None
    value: Optional[JsonValue] = None
    exists: Optional[bool] = None
    items: Optional[List["Predicate"]] = None
    item: Optional["Predicate"] = None

    @model_validator(mode="after")
    def closed_predicate_shape(self) -> "Predicate":
        supplied = set(self.model_fields_set) - {"op"}
        if self.op in {"and", "or"}:
            if supplied != {"items"} or not self.items:
                raise ValueError("Boolean predicates require only non-empty items")
        elif self.op == "not":
            if supplied != {"item"} or self.item is None:
                raise ValueError("not predicates require only item")
        elif self.op == "exists":
            if not self.field or supplied - {"field", "exists"}:
                raise ValueError("exists predicates require field and optional exists")
        elif not self.field or supplied != {"field", "value"}:
            raise ValueError("comparison predicates require only field and value")
        return self


Predicate.model_rebuild()


class OrderSpec(StrictInputModel):
    field: str = "identity"
    type: OrderType = "auto"
    descending: bool = False


class Reducer(StrictInputModel):
    name: str = Field(min_length=1, max_length=80)
    op: ReducerKind
    field: Optional[str] = None

    @model_validator(mode="after")
    def reducer_field(self) -> "Reducer":
        if self.op != "count" and not self.field:
            raise ValueError("non-count reducers require field")
        return self


class Projection(StrictInputModel):
    fields: List[str] = Field(min_length=1, max_length=64)
    includeProvenance: bool = True
    reducers: Optional[List[Reducer]] = None


class EntitySelector(StrictInputModel):
    entity: EntityKind
    ids: Optional[List[str]] = None
    parent: Dict[str, JsonValue] = Field(default_factory=dict)
    where: Dict[str, JsonValue] = Field(default_factory=dict)
    predicate: Optional[Predicate] = None
    orderBy: Union[str, OrderSpec] = "identity"
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
    operator: ConstraintOperator
    right: LiteralOperand | FieldOperand | ReferenceOperand
    tolerance: Optional[Annotated[float, Field(allow_inf_nan=False, ge=0)]] = None


class TranslationDelta(StrictInputModel):
    x: Annotated[float, Field(allow_inf_nan=False)] = 0
    y: Annotated[float, Field(allow_inf_nan=False)] = 0


class _OperationBase(StrictInputModel):
    target: EntitySelector


class SetOperation(_OperationBase):
    op: Literal["set"]
    field: str = Field(min_length=1)
    value: JsonValue
    quantizer: Literal["exact"] = "exact"


class TranslateOperation(_OperationBase):
    op: Literal["translate"]
    delta: TranslationDelta
    quantizer: Literal["exact"] = "exact"


class TransformOperation(_OperationBase):
    op: Literal["transform"]
    matrix: Annotated[
        List[Annotated[float, Field(allow_inf_nan=False)]],
        Field(min_length=6, max_length=6),
    ]
    origin: Annotated[
        List[Annotated[float, Field(allow_inf_nan=False)]],
        Field(min_length=2, max_length=2),
    ] = Field(default_factory=lambda: [0, 0])
    quantizer: Literal["exact"] = "exact"
    include: Annotated[
        List[Literal["paths", "anchors", "components"]],
        Field(min_length=1),
    ] = Field(default_factory=lambda: ["paths", "anchors", "components"])
    componentComposition: Literal[
        "prepend", "append", "conjugate", "unchanged"
    ] = "prepend"
    alignmentPolicy: Literal[
        "preserve", "explicit_noncommuting", "explicit_all"
    ] = "preserve"


class InsertOperation(_OperationBase):
    op: Literal["insert"]
    value: JsonValue
    field: Optional[str] = None
    index: Optional[Annotated[int, Field(ge=0)]] = None
    newId: Optional[str] = None


class RemoveOperation(_OperationBase):
    op: Literal["remove"]


class MoveOperation(_OperationBase):
    op: Literal["move"]
    index: Annotated[int, Field(ge=0)]


class DuplicateOperation(_OperationBase):
    op: Literal["duplicate"]
    newId: str = Field(min_length=1)
    overrides: Optional[Dict[str, JsonValue]] = None
    index: Optional[Annotated[int, Field(ge=0)]] = None


class MaterializeOperation(_OperationBase):
    op: Literal["materialize"]
    destinationEntity: Literal["master"]
    newId: str = Field(min_length=1)
    overrides: Optional[Dict[str, JsonValue]] = None
    index: Optional[Annotated[int, Field(ge=0)]] = None


OperationVariant = Annotated[
    Union[
        SetOperation,
        TranslateOperation,
        TransformOperation,
        InsertOperation,
        RemoveOperation,
        MoveOperation,
        DuplicateOperation,
        MaterializeOperation,
    ],
    Field(discriminator="op"),
]


class ChangeOperation(RootModel[OperationVariant]):
    @property
    def op(self) -> str:
        return self.root.op

    def model_dump(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return self.root.model_dump(*args, **kwargs)


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

    async def _invoke(self, tool: str, arguments: Dict[str, Any]) -> ToolResult:
        values = {
            key: _transport_value(value)
            for key, value in arguments.items()
            if key != "self" and value is not None
        }
        create_context = getattr(
            self._application, "create_invocation_context", None
        )
        context = create_context(tool, values) if callable(create_context) else None
        try:
            response = await anyio.to_thread.run_sync(
                lambda: (
                    self._application.invoke(
                        tool,
                        values,
                        invocation_context=context,
                    )
                    if context is not None
                    else self._application.invoke(tool, values)
                ),
                abandon_on_cancel=True,
            )
        except BaseException as exc:
            cancelled_type = anyio.get_cancelled_exc_class()
            if context is not None and isinstance(exc, cancelled_type):
                context.request_cancel(classification="cancelled")
            elif context is not None and isinstance(exc, TimeoutError):
                context.request_cancel(classification="timeout")
            raise
        return ToolResult(content=response.summary, structured_content=response.to_dict())

    async def get_server_info(self) -> ToolResult:
        return await self._invoke("get_server_info", {})

    async def list_documents(self) -> ToolResult:
        return await self._invoke("list_documents", {})

    async def read_document(
        self,
        documentId: str,
        selector: EntitySelector,
        projection: Projection,
    ) -> ToolResult:
        return await self._invoke("read_document", locals())

    async def read_document_view(self, documentId: str) -> ToolResult:
        return await self._invoke("read_document_view", locals())

    async def configure_document_view(
        self,
        documentId: str,
        comparisonReference: Optional[ComparisonReference] = None,
        refreshComparisonReference: bool = False,
        showChangesAgainstReference: Optional[bool] = None,
        timeoutSeconds: Annotated[int, Field(ge=5, le=120)] = 60,
    ) -> ToolResult:
        return await self._invoke("configure_document_view", locals())

    async def evaluate_constraints(
        self,
        documentId: str,
        constraints: List[Constraint],
    ) -> ToolResult:
        return await self._invoke("evaluate_constraints", locals())

    async def preview_change(
        self,
        documentId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
        operations: List[ChangeOperation],
        constraints: Optional[List[Constraint]] = None,
        verificationMode: Literal["semantic", "strict_archive"] = "semantic",
        transactionMode: Literal[
            "verified", "snapshot_backed_recovery"
        ] = "verified",
    ) -> ToolResult:
        return await self._invoke("preview_change", locals())

    async def apply_change(
        self,
        documentId: str,
        previewId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
        reason: Annotated[str, Field(min_length=1, max_length=1000)],
        confirmRecovery: bool = False,
    ) -> ToolResult:
        return await self._invoke("apply_change", locals())

    async def get_operation(
        self,
        operationId: str,
        pageSize: PageSize = 100,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return await self._invoke("get_operation", locals())

    async def list_history(
        self,
        documentId: str,
        pageSize: PageSize = 100,
    ) -> ToolResult:
        return await self._invoke("list_history", locals())

    async def revert_change(
        self,
        documentId: str,
        operationId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
    ) -> ToolResult:
        return await self._invoke("revert_change", locals())

    async def search_knowledge(
        self,
        query: Annotated[str, Field(min_length=1, max_length=500)],
        topics: Optional[List[str]] = None,
        authorities: Optional[List[Literal["authoritative", "practice", "heuristic"]]] = None,
        glyphsVersions: Optional[List[str]] = None,
        pageSize: Annotated[int, Field(ge=1, le=100)] = 20,
        cursor: Optional[str] = None,
    ) -> ToolResult:
        return await self._invoke("search_knowledge", locals())

    async def get_knowledge(
        self,
        entryIds: Annotated[List[str], Field(min_length=1, max_length=20)],
    ) -> ToolResult:
        return await self._invoke("get_knowledge", locals())

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
        return await self._invoke("execute_python", locals())

    async def preview_export(
        self,
        documentId: str,
        destination: str,
        overwritePolicy: Literal["fail_if_nonempty", "replace_if_match"] = "fail_if_nonempty",
        compatibilityMode: Literal["component_preserving", "decomposed_export"] = "component_preserving",
        expectedDestinationFingerprint: Optional[Sha256Fingerprint] = None,
        acknowledgedFindingIds: Optional[List[str]] = None,
    ) -> ToolResult:
        return await self._invoke("preview_export", locals())

    async def apply_export(self, previewId: str) -> ToolResult:
        return await self._invoke("apply_export", locals())

    async def save_document(
        self,
        documentId: str,
        expectedDocumentFingerprint: Sha256Fingerprint,
        confirm: bool,
        reason: Annotated[str, Field(min_length=1, max_length=1000)],
        destination: Optional[str] = None,
        expectedSourceFileFingerprint: Optional[Sha256Fingerprint] = None,
        overwritePolicy: Literal["fail_if_exists", "replace_if_match"] = "fail_if_exists",
        expectedDestinationFileFingerprint: Optional[Sha256Fingerprint] = None,
    ) -> ToolResult:
        return await self._invoke("save_document", locals())

    async def open_document_view(
        self,
        documentId: str,
        glyphNames: Annotated[List[str], Field(min_length=1, max_length=64)],
        masterId: Optional[str] = None,
        activateDocument: bool = False,
    ) -> ToolResult:
        return await self._invoke("open_document_view", locals())

    async def get_runtime_status(self) -> ToolResult:
        return await self._invoke("get_runtime_status", {})

    async def repair_runtime(
        self,
        expectedIncidentId: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ToolResult:
        return await self._invoke("repair_runtime", locals())


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
    "ComparisonReference",
    "Constraint",
    "EntitySelector",
    "Projection",
    "ToolHandlers",
    "create_server",
]
