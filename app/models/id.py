from typing import Annotated, Any, Optional

from bson import ObjectId
from pydantic import BeforeValidator, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema


def validate_object_id(v: Any) -> Optional[str]:
    """Validate and convert various ObjectId formats to string."""
    if v is None:
        return None
    if isinstance(v, ObjectId):
        return str(v)
    elif isinstance(v, dict) and "$oid" in v:
        return v["$oid"]
    elif isinstance(v, str):
        try:
            # Validate if it's a valid ObjectId string
            ObjectId(v)
            return v
        except Exception:
            raise ValueError(f"Invalid ObjectId string format: {v}")
    raise ValueError(f"Invalid type for ObjectId conversion: {type(v)}")


class ObjectIdField(str):
    """Custom field type for handling MongoDB ObjectId."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetJsonSchemaHandler,
    ) -> CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(ObjectId),
                    core_schema.str_schema(),
                    core_schema.none_schema(),
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x) if isinstance(x, ObjectId) else x
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, _handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string", "format": "objectid"}


PyObjectId = Annotated[ObjectIdField, BeforeValidator(validate_object_id)]
