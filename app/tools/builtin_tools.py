"""Built-in tools with Pydantic-based parameter validation."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.tools.sandbox import safe_eval


class CalculatorInput(BaseModel):
    expression: str = Field(..., description="Math expression to calculate.")


class GetCurrentTimeInput(BaseModel):
    city: str = Field(..., description="City name, such as beijing or tokyo.")


class UnitConversionInput(BaseModel):
    value: float = Field(..., description="Numeric value to convert.")
    from_unit: str = Field(..., description="Source unit.")
    to_unit: str = Field(..., description="Target unit.")


class TextAnalysisInput(BaseModel):
    text: str = Field(..., description="Text to analyze.")


class WeatherLookupInput(BaseModel):
    city: str = Field(..., description="City name for deterministic demo weather.")


class KnowledgeSearchInput(BaseModel):
    query: str = Field(..., description="Search query for the local knowledge base.")
    top_k: int = Field(default=3, description="Maximum number of matching records.")


def calculator(expression: str) -> str:
    try:
        result = safe_eval(expression)
        if isinstance(result, float) and result == int(result):
            return str(int(result))
        return str(result)
    except ValueError as e:
        return f"Calculation error: {e}"
    except Exception as e:
        return f"Calculation error: {e}"


def get_current_time(city: str) -> str:
    city_to_tz = {
        "tokyo": "Asia/Tokyo",
        "beijing": "Asia/Shanghai",
        "shanghai": "Asia/Shanghai",
        "london": "Europe/London",
        "new york": "America/New_York",
    }
    tz_name = city_to_tz.get(city.strip().lower())
    if not tz_name:
        return f"Unknown city: {city}"

    now = datetime.now(ZoneInfo(tz_name))
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    from_unit = _normalize_unit(from_unit)
    to_unit = _normalize_unit(to_unit)

    if from_unit in _LENGTH_FACTORS and to_unit in _LENGTH_FACTORS:
        base_value = value * _LENGTH_FACTORS[from_unit]
        converted = base_value / _LENGTH_FACTORS[to_unit]
        return _format_number(converted)

    if from_unit in _MASS_FACTORS and to_unit in _MASS_FACTORS:
        base_value = value * _MASS_FACTORS[from_unit]
        converted = base_value / _MASS_FACTORS[to_unit]
        return _format_number(converted)

    if from_unit in _TEMPERATURE_UNITS and to_unit in _TEMPERATURE_UNITS:
        converted = _convert_temperature(value, from_unit, to_unit)
        return _format_number(converted)

    return f"Unsupported unit conversion: {from_unit} to {to_unit}"


def analyze_text(text: str) -> str:
    lines = text.splitlines() or [text]
    words = [word for word in text.split() if word]
    result = {
        "characters": len(text),
        "characters_no_spaces": len(text.replace(" ", "")),
        "words": len(words),
        "lines": len(lines),
    }
    return json.dumps(result, ensure_ascii=False)


def get_weather(city: str) -> str:
    weather = _WEATHER_BY_CITY.get(city.strip().lower())
    if weather is None:
        return f"Unknown city: {city}"
    return json.dumps(weather, ensure_ascii=False)


def search_knowledge(query: str, top_k: int = 3) -> str:
    query_terms = {
        term.lower()
        for term in query.replace("-", " ").replace("_", " ").split()
        if term.strip()
    }
    if not query_terms:
        return "[]"

    scored: list[tuple[int, dict[str, str]]] = []
    for item in _KNOWLEDGE_BASE:
        haystack = f"{item['title']} {item['content']}".lower()
        score = sum(1 for term in query_terms if term in haystack)
        if score:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    matches = [item for _, item in scored[:max(top_k, 1)]]
    return json.dumps(matches, ensure_ascii=False)


def _normalize_unit(unit: str) -> str:
    normalized = unit.strip().lower().replace(" ", "_")
    return _UNIT_ALIASES.get(normalized, normalized)


def _format_number(value: float) -> str:
    rounded = round(value, 6)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded).rstrip("0").rstrip(".")


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == "celsius":
        celsius = value
    elif from_unit == "fahrenheit":
        celsius = (value - 32) * 5 / 9
    else:
        celsius = value - 273.15

    if to_unit == "celsius":
        return celsius
    if to_unit == "fahrenheit":
        return celsius * 9 / 5 + 32
    return celsius + 273.15


_LENGTH_FACTORS = {
    "meter": 1.0,
    "kilometer": 1000.0,
    "centimeter": 0.01,
    "millimeter": 0.001,
    "inch": 0.0254,
    "foot": 0.3048,
    "yard": 0.9144,
    "mile": 1609.344,
}

_MASS_FACTORS = {
    "gram": 1.0,
    "kilogram": 1000.0,
    "ounce": 28.349523125,
    "pound": 453.59237,
}

_TEMPERATURE_UNITS = {"celsius", "fahrenheit", "kelvin"}

_UNIT_ALIASES = {
    "m": "meter",
    "meter": "meter",
    "meters": "meter",
    "km": "kilometer",
    "kilometer": "kilometer",
    "kilometers": "kilometer",
    "cm": "centimeter",
    "centimeter": "centimeter",
    "centimeters": "centimeter",
    "mm": "millimeter",
    "millimeter": "millimeter",
    "millimeters": "millimeter",
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "ft": "foot",
    "foot": "foot",
    "feet": "foot",
    "yd": "yard",
    "yard": "yard",
    "yards": "yard",
    "mi": "mile",
    "mile": "mile",
    "miles": "mile",
    "g": "gram",
    "gram": "gram",
    "grams": "gram",
    "kg": "kilogram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "oz": "ounce",
    "ounce": "ounce",
    "ounces": "ounce",
    "lb": "pound",
    "lbs": "pound",
    "pound": "pound",
    "pounds": "pound",
    "c": "celsius",
    "celsius": "celsius",
    "f": "fahrenheit",
    "fahrenheit": "fahrenheit",
    "k": "kelvin",
    "kelvin": "kelvin",
}

_WEATHER_BY_CITY = {
    "beijing": {"city": "beijing", "condition": "clear", "temperature_c": 18},
    "shanghai": {"city": "shanghai", "condition": "cloudy", "temperature_c": 21},
    "tokyo": {"city": "tokyo", "condition": "rain", "temperature_c": 16},
    "london": {"city": "london", "condition": "overcast", "temperature_c": 12},
    "new york": {"city": "new york", "condition": "windy", "temperature_c": 14},
}

_KNOWLEDGE_BASE = [
    {
        "title": "AgentRunner",
        "content": "AgentRunner orchestrates LLM calls, tool calls, middleware, hooks, and checkpoints.",
    },
    {
        "title": "ToolRegistry",
        "content": "ToolRegistry stores tool specs and exposes OpenAI-compatible tool schemas.",
    },
    {
        "title": "DocumentMemoryStore",
        "content": "DocumentMemoryStore keeps project, user, session, and task memory in markdown files.",
    },
    {
        "title": "MCPToolRegistry",
        "content": "MCPToolRegistry registers remote MCP server tools into the local tool registry.",
    },
]
