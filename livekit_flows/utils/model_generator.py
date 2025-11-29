from pydantic import BaseModel, Field, create_model
from typing import Optional, Type, Any
from ..core import ConversationFlow


def _get_python_type_from_json_schema(
    schema_type: str, schema_format: str | None = None
) -> Type:
    """Convert JSON Schema type to Python type"""
    type_mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return type_mapping.get(schema_type, str)


def _extract_fields_from_schema(
    schema: dict[str, Any] | Type[BaseModel],
) -> dict[str, tuple]:
    """Extract field definitions from a JSON Schema or Pydantic model"""
    field_definitions = {}

    # Convert Pydantic model to JSON Schema if needed
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        json_schema = schema.model_json_schema()
        properties = json_schema.get("properties", {})
        required_fields = json_schema.get("required", [])
    else:
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

    for field_name, field_schema in properties.items():
        field_type_str = field_schema.get("type", "string")
        field_format = field_schema.get("format")
        description = field_schema.get("description", "")

        base_type = _get_python_type_from_json_schema(field_type_str, field_format)

        is_required = field_name in required_fields

        if is_required:
            field_type = base_type
            field_definition = Field(description=description)
        else:
            field_type = Optional[base_type]
            field_definition = Field(default=None, description=description)

        field_definitions[field_name] = (field_type, field_definition)

    return field_definitions


def _build_field_map_from_schemas(flow: ConversationFlow) -> dict[str, tuple]:
    """Build a unified field map from all input schemas in the flow"""
    all_field_definitions = {}

    for node in flow.nodes:
        for edge in node.edges:
            if edge.input_schema:
                field_defs = _extract_fields_from_schema(edge.input_schema)

                # Merge fields, keeping first definition on conflict
                for field_name, field_def in field_defs.items():
                    if field_name not in all_field_definitions:
                        all_field_definitions[field_name] = field_def

    return all_field_definitions


def generate_userdata_class(
    flow: ConversationFlow, class_name: str = "FlowUserData"
) -> Type[BaseModel]:
    """Generate a Pydantic model class from all input schemas in the flow"""
    field_definitions = _build_field_map_from_schemas(flow)

    if not field_definitions:
        return create_model(class_name)

    return create_model(class_name, **field_definitions)  # type: ignore[call-overload]
