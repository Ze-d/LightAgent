import json
from openai import OpenAI

client = OpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    timeout=30,
    api_key="sk-27066e5594b74bbaa7dcfacdb8103a95"
)

def calculator(expression: str) -> str:
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"Calculation error: {e}"

tool_map = {
    "calculator": calculator
}

tools = [
    {
        "type": "function",
        "name": "calculator",
        "description": "Calculate a math expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"],
            "additionalProperties": False
        }
    }
]

def run_agent(user_query: str) -> str:
    current_input = user_query

    while True:
        response = client.responses.create(
            model="qwen3.5-flash",
            input=current_input,
            tools=tools
        )

        function_calls = [item for item in response.output if item.type == "function_call"]

        if not function_calls:
            return response.output_text

        next_input = []

        for fc in function_calls:
            tool_name = fc.name
            call_id = fc.call_id

            try:
                tool_args = json.loads(fc.arguments)
            except json.JSONDecodeError:
                result = "Tool argument parse error."
            else:
                tool_func = tool_map.get(tool_name)
                if not tool_func:
                    result = f"Unknown tool: {tool_name}"
                else:
                    try:
                        result = tool_func(**tool_args)
                    except Exception as e:
                        result = f"Tool execution error: {e}"

            next_input.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": result
            })

        current_input = next_input

print("starting agent loop...")
print(run_agent("帮我计算 23 * 47"))
print("ending agent loop...")