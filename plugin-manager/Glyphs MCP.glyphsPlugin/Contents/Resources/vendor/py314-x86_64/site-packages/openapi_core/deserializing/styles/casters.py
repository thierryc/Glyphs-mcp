from typing import Any

from jsonschema_path import SchemaPath

from openapi_core.util import forcebool


def cast_primitive(value: Any, schema: SchemaPath) -> Any:
    """Cast a primitive value based on schema type."""
    schema_type = (schema / "type").read_str("")

    if schema_type == "integer":
        return int(value)
    elif schema_type == "number":
        return float(value)
    elif schema_type == "boolean":
        return forcebool(value)

    return value


def cast_value(value: Any, schema: SchemaPath, cast: bool) -> Any:
    """Recursively cast a value based on schema."""
    if not cast:
        return value

    schema_type = (schema / "type").read_str("")

    # Handle arrays
    if schema_type == "array":
        if not isinstance(value, list):
            raise ValueError(
                f"Expected list for array type, got {type(value)}"
            )
        items_schema = schema.get("items", SchemaPath.from_dict({}))
        return [cast_value(item, items_schema, cast) for item in value]

    # Handle objects
    if schema_type == "object":
        if not isinstance(value, dict):
            raise ValueError(
                f"Expected dict for object type, got {type(value)}"
            )
        properties = schema.get("properties", SchemaPath.from_dict({}))
        result = {}
        for key, val in value.items():
            if key in properties:
                prop_schema = schema / "properties" / key
                result[key] = cast_value(val, prop_schema, cast)
            else:
                result[key] = val
        return result

    # Handle primitives
    return cast_primitive(value, schema)
