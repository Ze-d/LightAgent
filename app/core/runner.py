import json
from openai import OpenAI

from app.configs.logger import logger
from app.core.hooks import BaseRunnerHooks
from app.core.middleware import BaseRunnerMiddleware, MiddlewareAbort
from app.obj.types import AgentRunResult, ChatMessage, FunctionCallOutput, RunStartEvent, ToolCallEvent
from app.agents.agent_base import BaseAgent
from app.core.tool_registry import ToolRegistry


class AgentRunner:
    def __init__(self, client: OpenAI, max_steps: int = 5, 
                 hooks: BaseRunnerHooks | None = None,
                 middleware: BaseRunnerMiddleware | None = None,):
        self.client = client
        self.max_steps = max_steps
        self.hooks = hooks
        self.middleware = middleware

    def run(
        self,
        agent: BaseAgent,
        history: list[ChatMessage],
        tool_registry: ToolRegistry | None = None,
        hooks: BaseRunnerHooks | None = None,
    ) -> AgentRunResult:
        # Use provided hooks or fall back to instance hooks
        effective_hooks = hooks if hooks is not None else self.hooks
        # hooks: 运行前触发 run_start 事件
        start_event: RunStartEvent = {
            "agent_name": agent.name,
            "history_length": len(history),
            "model": agent.model,
        }
        if effective_hooks:
            effective_hooks.on_run_start(start_event)
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
            # hooks: 生成前触发 llm_start 事件
            if effective_hooks:
                effective_hooks.on_llm_start({
                    "agent_name": agent.name,
                    "step": step,
                    "model": agent.model,
                    "input_length": len(current_input),
                })
            # middleware: 生成前调用 before_llm，允许修改输入或阻止生成
            llm_context = {
                "agent_name": agent.name,
                "model": agent.model,
                "step": step,
                "current_input": current_input,
            }
            try:
                llm_context = self.middleware.before_llm(llm_context)
            except MiddlewareAbort as e:
                return {
                    "answer": e.message,
                    "success": False,
                    "steps": step,
                    "tool_events": collected_events,
                    "error": "middleware_abort_before_llm",
                }
            current_input = llm_context["current_input"]            
            # 调用模型接口  
            response = self.client.responses.create(
                model=agent.model,
                input=current_input,
                tools=tools if tools else None,
            )
            # hooks: 生成后触发 llm_end 事件
            if effective_hooks:
                effective_hooks.on_llm_end({
                    "agent_name": agent.name,
                    "step": step,
                    "output_items_count": len(response.output),
                })
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
                    # middleware: 工具调用前调用 before_tool，允许修改工具调用参数或阻止工具调用
                    tool_context = {
                        "agent_name": agent.name,
                        "step": step,
                        "tool_name": tool_name,
                        "arguments": tool_args,
                    }

                    try:
                        tool_context = self.middleware.before_tool(tool_context)
                    except MiddlewareAbort as e:
                        error_event = {
                            "agent_name": agent.name,
                            "step": step,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "status": "error",
                            "error": e.message,
                        }
                        collected_events.append(error_event)
                        self.hooks.on_tool_end(error_event)
                        agent.on_tool_event(error_event)
                        result = e.message
                    else:
                        tool_name = tool_context["tool_name"]
                        tool_args = tool_context["arguments"]
                except json.JSONDecodeError:
                    result = "工具参数解析失败。"
                else:
                    try:
                        result : str = tool_registry.call(tool_name, **tool_args)
                    except Exception as e:
                        result = f"工具执行失败：{e}"
                        tool_event : ToolCallEvent = {
                            "agent_name": agent.name,
                            "step": step,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "status": "error",
                            "error": str(e),
                        }
                        agent.on_tool_event(tool_event)
                        if effective_hooks:
                            effective_hooks.on_tool_end(tool_event)
                    else:
                        result = f"工具执行成功：{tool_name}"
                        tool_event : ToolCallEvent = {
                            "agent_name": agent.name,
                            "step": step,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "status": "success",
                            "result": result,
                        }
                        # 收集工具调用事件，供最终结果使用
                        agent.on_tool_event(tool_event)
                        # hooks: 工具调用后触发 tool_end 事件
                        if effective_hooks:
                            effective_hooks.on_tool_end(tool_event)

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