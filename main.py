import json
from openai import OpenAI

client = OpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    timeout=30,
    api_key="sk-27066e5594b74bbaa7dcfacdb8103a95"
)

def calculator(expression: str) -> str:
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
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

# 第一次请求：让模型决定是否调工具
response = client.responses.create(
    model="qwen3.5-flash",
    input="帮我计算 23 * 47",
    tools=tools
)
for item in response.output:
    print(item)
function_calls = [item for item in response.output if item.type == "function_call"]

if not function_calls:
    print(response.output_text)
else:
    fc = function_calls[0]
    tool_name = fc.name
    tool_args = json.loads(fc.arguments)
    call_id = fc.call_id

    tool_result = tool_map[tool_name](**tool_args)

    # 第二次请求：把工具结果喂回模型
    response2 = client.responses.create(
        model="qwen3.5-flash",
        input=[
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": tool_result
            }
        ],
        tools=tools
    )

    print(response2.output_text)