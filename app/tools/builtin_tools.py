from datetime import datetime
from zoneinfo import ZoneInfo


def calculator(expression: str) -> str:
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
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