import logging
from typing import Any
from jsonschema import ValidationError, Draft7Validator
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def validate_against_schema(
    data: dict[str, Any], schema: dict[str, Any] | type[BaseModel]
) -> tuple[bool, str | None]:
    try:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            schema = schema.model_json_schema()

        validator = Draft7Validator(schema)
        validator.validate(data)

        return True, None
    except ValidationError as e:
        error_msg = (
            f"Validation error at {'.'.join(str(p) for p in e.path)}: {e.message}"
        )
        logger.warning(f"Schema validation failed: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected validation error: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def is_valid_json_schema(schema: dict[str, Any]) -> bool:
    try:
        Draft7Validator.check_schema(schema)
        return True
    except Exception as e:
        logger.warning(f"Invalid JSON Schema: {e}")
        return False
