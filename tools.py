from typing import Any

def calculator(expression: str) -> str:
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"
    
tools : list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "calculator",
        "description": "Calculate a math expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The math expression to calculate."
                }
            },
            "required": ["expression"],
            "additionalProperties": False
        }
    }
]
tool_map = {
    "calculator": calculator
}