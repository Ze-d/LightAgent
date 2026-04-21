"""Built-in tools with Pydantic-based parameter validation."""
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.tools.sandbox import safe_eval


class CalculatorInput(BaseModel):
    expression: str


class GetCurrentTimeInput(BaseModel):
    city: str


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
