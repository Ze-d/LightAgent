import json
from openai import OpenAI

from app.configs.logger import logger
from app.obj.types import AgentRunResult, ChatMessage, FunctionCallOutput, ToolCallEvent
from app.agents.agent_base import BaseAgent
from app.core.tool_registry import ToolRegistry


class AgentRunner:
    def __init__(self, client: OpenAI, max_steps: int = 5):
        self.client = client
        self.max_steps = max_steps

    def run(
        self,
        agent: BaseAgent,
        history: list[ChatMessage],
        tool_registry: ToolRegistry | None = None,
    ) -> AgentRunResult:
        current_input = history
        collected_events: list[ToolCallEvent] = []
        tools = (
            tool_registry.get_openai_tools()
            if (tool_registry and agent.supports_tools())
            else []
        )
        # 每一步都让 Agent 生成输出，直到没有工具调用或达到最大步数
        for step in range(1, self.max_steps + 1):
            logger.info(f"runner step={step} agent={agent.name}")

            response = self.client.responses.create(
                model=agent.model,
                input=current_input,
                tools=tools if tools else None,
            )

            function_calls = [
                item for item in response.output
                if item.type == "function_call"
            ]

            if not function_calls:
                return {
                    "answer": response.output_text or "模型没有返回文本结果。",
                    "success": True,
                    "steps": step,
                    "tool_events": collected_events,
                    "error": None,
                }


            if tool_registry is None:
                 return {
                    "answer": "当前 Agent 未配置工具注册中心。",
                    "success": False,
                    "steps": step,
                    "tool_events": collected_events,
                    "error": "missing_tool_registry",
                }


            next_input: list[FunctionCallOutput] = []

            for fc in function_calls:
                tool_name = fc.name
                call_id = fc.call_id

                try:
                    tool_args = json.loads(fc.arguments)
                except json.JSONDecodeError:
                    result = "工具参数解析失败。"
                else:
                    try:
                        result : str = tool_registry.call(tool_name, **tool_args)
                    except Exception as e:
                        result = f"工具执行失败：{e}"
                        agent.emit_tool_event({
                            "agent_name": agent.name,
                            "step": step,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "status": "error",
                            "error": str(e),
                        })
                    else:
                        agent.emit_tool_event({
                            "agent_name": agent.name,
                            "step": step,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": result,
                            "status": "success",
                        })

                next_input.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result,
                })

            current_input = next_input

        return {
            "answer": "抱歉，任务执行步数过多，已停止。",
            "success": False,
            "steps": self.max_steps,
            "tool_events": collected_events,
            "error": "max_steps_exceeded",
        }