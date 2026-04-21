"""Pydantic-based parameter validation decorator for tools.

Provides type-safe tool registration with automatic OpenAI schema generation.
"""
from functools import wraps
from typing import Any, get_origin, get_args

from pydantic import BaseModel, ValidationError

from app.configs.logger import logger
from app.obj.types import ToolSpec


def validate_params(model_cls: type[BaseModel]):
    """Decorator that validates tool arguments against a Pydantic model.

    Usage:
        class CalculatorInput(BaseModel):
            expression: str

        @validate_params(CalculatorInput)
        def calculator(expression: str) -> str:
            ...

    The decorated function receives **validated** keyword arguments.
    If validation fails, raises a ValueError with a clear message.

    Args:
        model_cls: Pydantic BaseModel subclass defining expected parameters
    """
    def decorator(func):
        @wraps(func)
        def wrapper(**kwargs) -> str:
            try:
                validated = model_cls.model_validate(kwargs, strict=False)
                return func(**validated.model_dump())
            except ValidationError as e:
                errors = "; ".join(
                    f"{err['loc'][0]}: {err['msg']}" for err in e.errors()
                )
                return f"Parameter validation failed: {errors}"
            except Exception as e:
                return f"Tool execution error: {e}"
        return wrapper
    return decorator


def pydantic_to_openai_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model to OpenAI tool parameter schema.

    Args:
        model_cls: Pydantic BaseModel subclass

    Returns:
        OpenAI-compatible parameters dict with type, properties, required
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for field_name, field_info in model_cls.model_fields.items():
        annotation = field_info.annotation
        default = field_info.default

        # Check if field is Optional (Union with NoneType)
        is_optional = _is_optional(annotation)
        # Effective annotation (unwrap Optional)
        effective_annotation = _unwrap_optional(annotation)
        # Effective default
        has_default = type(default).__name__ != "PydanticUndefinedType"

        py_type = _annotation_to_json_type(effective_annotation)
        prop_schema: dict[str, Any] = {"type": py_type}

        if field_info.description:
            prop_schema["description"] = field_info.description

        if has_default:
            prop_schema["default"] = default
        elif not is_optional:
            required.append(field_name)

        properties[field_name] = prop_schema

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required

    return schema


def _is_optional(annotation: Any) -> bool:
    """Check if annotation is Optional (Union with NoneType)."""
    from typing import Union
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        return type(None) in args
    return False


def _unwrap_optional(annotation: Any) -> Any:
    """Unwrap Optional[X] to X."""
    from typing import Union
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        return non_none[0] if non_none else annotation
    return annotation


def _annotation_to_json_type(annotation: Any) -> str:
    """Map Python type annotation to JSON schema type string."""
    origin = get_origin(annotation)

    if origin is None:
        # Direct type
        if annotation is str:
            return "string"
        if annotation is int:
            return "integer"
        if annotation is float:
            return "number"
        if annotation is bool:
            return "boolean"
        return "string"

    # Handle Union types (Optional)
    if origin is str:  # actually Union[..., str] where str is non-None
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _annotation_to_json_type(non_none[0])
        return "string"

    if origin is list:
        args = get_args(annotation)
        item_type = _annotation_to_json_type(args[0]) if args else "string"
        return "array"

    if origin is dict:
        return "object"

    # Fallback
    return "string"


def create_tool_spec(
    name: str,
    description: str,
    model_cls: type[BaseModel],
    handler,
) -> ToolSpec:  # type: ignore[misc]
    """Create a ToolSpec dict from a Pydantic model and handler.

    Convenience function that combines parameter validation and schema generation.

    Args:
        name: Tool name
        description: Tool description for LLM
        model_cls: Pydantic BaseModel defining parameters
        handler: Tool handler function (should accept typed kwargs)

    Returns:
        ToolSpec dict ready for ToolRegistry.register()
    """
    validated_handler = validate_params(model_cls)(handler)
    return {
        "name": name,
        "description": description,
        "parameters": pydantic_to_openai_schema(model_cls),
        "handler": validated_handler,
    }
