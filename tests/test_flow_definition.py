import json
from typing import Any, cast

import pytest
from pydantic import BaseModel, Field, ValidationError

from livekit_flows import ConversationFlow, Edge, FlowNode
from livekit_flows.utils.model_generator import generate_userdata_class
from livekit_flows.utils.schema_validator import (
    is_valid_json_schema,
    validate_against_schema,
)


class GuestDetails(BaseModel):
    name: str = Field(description="Guest name")
    party_size: int | None = Field(default=None, description="Party size")


def _flow(**overrides) -> ConversationFlow:
    data = {
        "system_prompt": "You help with reservations.",
        "initial_node": "welcome",
        "nodes": [
            {
                "id": "welcome",
                "name": "Welcome",
                "static_text": "Hello {{ userdata.name }}",
                "edges": [
                    {
                        "id": "to_confirm",
                        "condition": "Got details",
                        "target_node_id": "confirm",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Guest name",
                                },
                                "party_size": {
                                    "type": "integer",
                                    "description": "Party size",
                                },
                            },
                            "required": ["name"],
                        },
                    }
                ],
            },
            {"id": "confirm", "name": "Confirm", "is_final": True, "edges": []},
        ],
    }
    data.update(overrides)
    return ConversationFlow.model_validate(data)


def test_edge_converts_pydantic_model_into_json_schema():
    edge = Edge(
        id="to_confirm",
        condition="Got details",
        target_node_id="confirm",
        input_schema=GuestDetails,
    )

    schema = edge.input_schema
    assert isinstance(schema, dict)
    assert schema["type"] == "object"
    assert schema["properties"]["name"]["description"] == "Guest name"
    assert schema["required"] == ["name"]


def test_generate_userdata_class_merges_schemas_and_keeps_first_definition():
    flow = _flow()
    flow.nodes[1].edges.append(
        Edge(
            id="extra",
            condition="Extra",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "integer", "description": "Should be ignored"},
                    "notes": {"type": "string", "description": "Notes"},
                },
                "required": ["notes"],
            },
        )
    )

    user_data_cls = generate_userdata_class(flow)

    assert user_data_cls.__name__ == "FlowUserData"
    assert user_data_cls.model_fields["name"].annotation is str
    assert user_data_cls.model_fields["name"].is_required()
    assert user_data_cls.model_fields["party_size"].default is None
    assert user_data_cls.model_fields["notes"].is_required()

    guest = user_data_cls.model_validate({"name": "Ada", "notes": "window"})
    assert guest.model_dump() == {
        "name": "Ada",
        "party_size": None,
        "notes": "window",
    }


def test_generate_userdata_class_without_schemas_is_empty():
    flow = ConversationFlow(
        system_prompt="Hi",
        initial_node="only",
        nodes=[FlowNode(id="only", name="Only")],
    )

    user_data_cls = generate_userdata_class(flow, class_name="EmptyData")

    assert user_data_cls.__name__ == "EmptyData"
    assert user_data_cls().model_dump() == {}


def test_validate_against_schema_accepts_dict_and_pydantic_model():
    valid, error = validate_against_schema({"name": "Ada"}, GuestDetails)
    assert valid is True
    assert error is None

    valid, error = validate_against_schema(
        {"party_size": 2},
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    )
    assert valid is False
    assert error is not None
    assert "name" in error


def test_validate_against_schema_reports_invalid_schema():
    valid, error = validate_against_schema({}, cast(Any, "not-a-schema"))

    assert valid is False
    assert error is not None
    assert "Unexpected validation error" in error


def test_is_valid_json_schema():
    assert is_valid_json_schema({"type": "object"}) is True
    assert is_valid_json_schema({"type": "nope"}) is False


def test_load_flow_from_yaml_and_json_strings():
    yaml_flow = ConversationFlow.from_yaml_string(
        """
        system_prompt: You help with reservations.
        initial_node: welcome
        nodes:
          - id: welcome
            name: Welcome
            static_text: Hi
        """
    )
    json_flow = ConversationFlow.from_json_string(
        json.dumps(
            {
                "system_prompt": "You help with reservations.",
                "initial_node": "welcome",
                "nodes": [{"id": "welcome", "name": "Welcome", "static_text": "Hi"}],
            }
        )
    )

    assert yaml_flow.initial_node == "welcome"
    assert json_flow.nodes[0].static_text == "Hi"


def test_load_flow_from_files_by_extension(tmp_path):
    payload = {
        "system_prompt": "You help with reservations.",
        "initial_node": "welcome",
        "nodes": [{"id": "welcome", "name": "Welcome"}],
    }
    yaml_path = tmp_path / "flow.yaml"
    yml_path = tmp_path / "flow.yml"
    json_path = tmp_path / "flow.json"
    yaml_path.write_text(
        "system_prompt: You help with reservations.\ninitial_node: welcome\nnodes:\n  - id: welcome\n    name: Welcome\n"
    )
    yml_path.write_text(yaml_path.read_text())
    json_path.write_text(json.dumps(payload))

    assert ConversationFlow.from_file(yaml_path).nodes[0].id == "welcome"
    assert ConversationFlow.from_yaml_file(yml_path).initial_node == "welcome"
    assert ConversationFlow.from_json_file(json_path).system_prompt.startswith(
        "You help"
    )


def test_loaders_reject_missing_invalid_and_unsupported_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="Flow file not found"):
        ConversationFlow.from_file(tmp_path / "missing.yaml")

    broken_yaml = tmp_path / "broken.yaml"
    broken_yaml.write_text("nodes: [\n")
    with pytest.raises(ValueError, match="Invalid YAML"):
        ConversationFlow.from_yaml_file(broken_yaml)

    broken_json = tmp_path / "broken.json"
    broken_json.write_text("{")
    with pytest.raises(ValueError, match="Invalid JSON"):
        ConversationFlow.from_json_file(broken_json)

    invalid_flow = tmp_path / "invalid.json"
    invalid_flow.write_text("{}")
    with pytest.raises(ValueError, match="Invalid flow definition"):
        ConversationFlow.from_json_file(invalid_flow)

    text_file = tmp_path / "flow.txt"
    text_file.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        ConversationFlow.from_file(text_file)

    with pytest.raises(ValueError, match="Invalid YAML content"):
        ConversationFlow.from_yaml_string(":\n  -")

    with pytest.raises(ValueError, match="Invalid JSON content"):
        ConversationFlow.from_json_string("{")

    with pytest.raises(ValidationError):
        ConversationFlow.model_validate({"system_prompt": "Hi"})
