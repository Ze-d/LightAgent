import json
from openai import OpenAI

from app.configs.config import *
from app.configs.logger import logger
from app.obj.types import ChatMessage, FunctionCallOutput
from app.tools.register import build_default_registry
tool_registry = build_default_registry()

class AgentError(Exception):
    """Agent 基础异常"""
    pass


class ConfigError(AgentError):
    """配置异常"""
    pass


class ToolExecutionError(AgentError):
    """工具执行异常"""
    pass


class MinimalAgent:
    def __init__(self, model: str = LLM_MODEL_ID):
        if not LLM_API_KEY:
            raise ConfigError("Missing LLM_API_KEY in environment variables.")

        self.client = OpenAI(api_key=LLM_API_KEY,base_url=LLM_BASE_URL, timeout=LLM_TIMEOUT)
        self.model = model

    def run(self, history: list[ChatMessage]) -> str:
        current_input = history

        for step in range(1, MAX_STEPS + 1):
            logger.info(f"Agent step={step} start")
            logger.debug(f"Current input: {current_input}")
            logger.debug(f"Available tools: {[tool['name'] for tool in TOOLS]}")
            logger.debug(f"Model: {self.model}, Timeout: {LLM_TIMEOUT}s")   
            response = self.client.responses.create(
                model=self.model,
                input=current_input,
                tools=tool_registry.get_openai_tools()
            )

            function_calls = [
                item for item in response.output
                if item.type == "function_call"
            ]

            if not function_calls:
                final_answer = response.output_text or "模型没有返回文本结果。"
                logger.info(f"Agent step={step} finished with final answer")
                return final_answer

            logger.info(f"Agent step={step} function_calls={len(function_calls)}")

            next_input : list[FunctionCallOutput]= []

            for fc in function_calls:
                tool_name = fc.name
                call_id = fc.call_id

                try:
                    tool_args = json.loads(fc.arguments)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Tool args parse failed, tool={tool_name}, raw={fc.arguments}"
                    )
                    result = "工具参数解析失败。"
                else:
                    logger.info(f"Tool call: {tool_name}, args={tool_args}")

                    tool_func = tool_registry.get_handler(tool_name)
                    if not tool_func:
                        logger.warning(f"Unknown tool: {tool_name}")
                        result = f"未知工具：{tool_name}"
                    else:
                        try:
                            result = tool_registry.call(tool_name, **tool_args)
                            logger.info(f"Tool result: {tool_name} -> {result}")
                        except Exception as e:
                            logger.exception(f"Tool execution failed: {tool_name}")
                            result = f"工具执行失败：{e}"

                next_input.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result
                })

            current_input = next_input

        logger.warning("Agent exceeded max steps")
        return "抱歉，任务执行步数过多，已停止。"