"""Tests for Pydantic parameter validation in tools."""
import pytest

from pydantic import BaseModel

from app.tools.validator import (
    validate_params,
    pydantic_to_openai_schema,
    create_tool_spec,
)
from app.tools.register import build_default_registry


# --- validate_params decorator tests ---

class TestValidateParamsDecorator:
    """Test parameter validation via @validate_params decorator."""

    def test_valid_params_returns_result(self):
        class Input(BaseModel):
            name: str

        @validate_params(Input)
        def greet(name: str) -> str:
            return f"Hello, {name}"

        result = greet(name="Alice")
        assert result == "Hello, Alice"

    def test_missing_required_field_returns_error(self):
        class Input(BaseModel):
            expression: str

        @validate_params(Input)
        def calc(expression: str) -> str:
            return expression

        result = calc()
        assert "Parameter validation failed" in result
        assert "expression" in result
        assert "Field required" in result

    def test_wrong_type_returns_error(self):
        class Input(BaseModel):
            expression: str

        @validate_params(Input)
        def calc(expression: str) -> str:
            return expression

        result = calc(expression=123)
        assert "Parameter validation failed" in result
        assert "expression" in result
        assert "Input should be a valid string" in result

    def test_multiple_fields_missing_one(self):
        class Input(BaseModel):
            x: int
            y: int

        @validate_params(Input)
        def add(x: int, y: int) -> int:
            return x + y

        result = add(x=1)
        assert "Parameter validation failed" in result
        assert "y" in result

    def test_extra_field_ignored(self):
        """Extra fields not defined in model are silently ignored (Pydantic v2 default)."""
        class Input(BaseModel):
            expression: str

        @validate_params(Input)
        def calc(expression: str) -> str:
            return expression

        result = calc(expression="2+2", extra_field="ignored")
        # Extra fields are ignored; only expression is passed through
        assert result == "2+2"


# --- pydantic_to_openai_schema tests ---

class TestSchemaGeneration:
    """Test OpenAI schema generation from Pydantic models."""

    def test_required_field_in_required_list(self):
        class Input(BaseModel):
            expression: str

        schema = pydantic_to_openai_schema(Input)
        assert "required" in schema
        assert "expression" in schema["required"]

    def test_optional_field_not_in_required_list(self):
        class Input(BaseModel):
            city: str
            timezone: str | None = None

        schema = pydantic_to_openai_schema(Input)
        assert "required" in schema
        assert "city" in schema["required"]
        assert "timezone" not in schema["required"]

    def test_field_with_default_not_required(self):
        class Input(BaseModel):
            city: str
            count: int = 10

        schema = pydantic_to_openai_schema(Input)
        assert "count" not in schema.get("required", [])
        assert schema["properties"]["count"]["default"] == 10

    def test_string_type_maps_to_string(self):
        class Input(BaseModel):
            name: str

        schema = pydantic_to_openai_schema(Input)
        assert schema["properties"]["name"]["type"] == "string"

    def test_int_type_maps_to_integer(self):
        class Input(BaseModel):
            count: int

        schema = pydantic_to_openai_schema(Input)
        assert schema["properties"]["count"]["type"] == "integer"

    def test_float_type_maps_to_number(self):
        class Input(BaseModel):
            value: float

        schema = pydantic_to_openai_schema(Input)
        assert schema["properties"]["value"]["type"] == "number"

    def test_bool_type_maps_to_boolean(self):
        class Input(BaseModel):
            flag: bool

        schema = pydantic_to_openai_schema(Input)
        assert schema["properties"]["flag"]["type"] == "boolean"


# --- create_tool_spec tests ---

class TestCreateToolSpec:
    """Test tool spec creation with validation."""

    def test_spec_has_validation_wrapper(self):
        class Input(BaseModel):
            expression: str

        spec = create_tool_spec(
            name="calc",
            description="Calculate",
            model_cls=Input,
            handler=lambda expression: str(int(eval(expression))),
        )

        # Handler is wrapped with validation
        result = spec["handler"](expression="2+3")
        assert result == "5"

    def test_spec_invalid_param_returns_error(self):
        class Input(BaseModel):
            expression: str

        spec = create_tool_spec(
            name="calc",
            description="Calculate",
            model_cls=Input,
            handler=lambda expression: "ok",
        )

        result = spec["handler"](expression=999)
        assert "Parameter validation failed" in result

    def test_spec_contains_openai_schema(self):
        class Input(BaseModel):
            city: str

        spec = create_tool_spec(
            name="time",
            description="Get time",
            model_cls=Input,
            handler=lambda city: city,
        )

        assert "parameters" in spec
        assert spec["parameters"]["type"] == "object"
        assert "city" in spec["parameters"]["properties"]


# --- Integration: registered tools with validation ---

class TestRegisteredToolsValidation:
    """Test that built-in registered tools enforce parameter validation."""

    def test_calculator_valid_expression(self):
        registry = build_default_registry()
        result = registry.call("calculator", expression="10 * 5")
        assert result == "50"

    def test_calculator_missing_expression(self):
        registry = build_default_registry()
        result = registry.call("calculator")
        assert "Parameter validation failed" in result
        assert "expression" in result

    def test_calculator_wrong_type(self):
        registry = build_default_registry()
        result = registry.call("calculator", expression=["not", "a", "string"])
        assert "Parameter validation failed" in result

    def test_calculator_injection_attempt_blocked(self):
        """Injection via validated params is blocked by sandbox."""
        registry = build_default_registry()
        result = registry.call("calculator", expression="os.system('ls')")
        assert "Calculation error" in result
        assert "unsupported" in result.lower() or "error" in result.lower()

    def test_get_current_time_valid_city(self):
        registry = build_default_registry()
        result = registry.call("get_current_time", city="beijing")
        assert "2026" in result  # Date should contain year

    def test_get_current_time_missing_city(self):
        registry = build_default_registry()
        result = registry.call("get_current_time")
        assert "Parameter validation failed" in result
        assert "city" in result

    def test_get_current_time_unknown_city(self):
        registry = build_default_registry()
        result = registry.call("get_current_time", city="invalid_city_xyz")
        assert "Unknown city" in result
