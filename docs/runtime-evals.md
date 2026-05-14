# Agent Runtime Eval Suite

本目录用于评估 Agent Runtime 的框架能力，而不是评估某个具体业务 Agent
的最终回答质量。应用 eval 关注“任务完成得好不好”；runtime eval 关注
“工具调用、上下文、恢复、协议和事件流是否稳定、可控、可复现”。

## 运行方式

```bash
.venv\Scripts\python.exe -m evals.run
```

默认读取：

- `evals/cases/tool_calling.jsonl`
- `evals/cases/tool_zoo.jsonl`
- `evals/cases/tool_retrieval.jsonl`
- `evals/cases/checkpoint_recovery.jsonl`

默认输出：

- `reports/evals/runtime-eval-latest.md`

## 当前覆盖

### Tool Calling

通过 mock LLM 固定返回 function_call，验证 runtime 是否能正确完成：

- 工具名称路由
- 参数透传与校验
- 工具执行
- 工具输出 contract 校验
- 工具结果回灌后得到最终回答

`tool_calling` 覆盖生产默认 registry 中的全部工具，包括基础工具和
memory 工具。`tool_calling_zoo` 使用 eval-only Tool Zoo，专门覆盖更复杂的
参数形态和工具输出，不会注册到生产默认工具集中。

核心指标：

- `tool_selection_accuracy`
- `argument_accuracy`
- `schema_valid_rate`
- `tool_success_rate`
- `tool_result_contains_rate`
- `answer_contains_rate`
- `avg_latency_ms`

当前 seed cases：

- `tool_calling`：20 条，覆盖 12 个默认工具
- `tool_calling_zoo`：24 条，覆盖 15 个 eval-only 工具

### Tool Retrieval

验证工具数量暴涨时，runtime 是否能在全量工具目录中只向模型暴露相关
top-k tools，而不是把所有 MCP/A2A/本地工具 schema 全量注入上下文。

该 suite 使用 eval-only large registry：默认工具、Tool Zoo、模拟 MCP/A2A
远端工具，以及一组无关 noise tools。测试不调用真实 LLM，而是直接评估
ToolCatalog + HeuristicToolSelector 的召回、过滤和预算控制。

核心指标：

- `recall_at_k`：期望工具是否被选入本轮可见工具集合
- `schema_token_reduction_rate`：相比全量工具 schema 注入的估算 token 降幅
- `irrelevant_exposure_rate`：显式标注的无关工具暴露比例
- `avg_selected_tool_count`：平均每轮暴露给模型的工具数量
- `min_selected_tool_count` / `max_selected_tool_count`：不同复杂度任务下的工具暴露范围
- `namespace_cap_pass_rate`：单个 MCP/A2A namespace 是否被限额约束

当前 seed cases：

- `tool_retrieval`：19 条，覆盖本地工具、Tool Zoo 工具、模拟 MCP 工具、
  模拟 A2A agent 工具，以及需要多个工具协同的 pipeline 场景

### Checkpoint Recovery

通过故障注入验证长任务恢复能力：

- 工具执行成功后，下一次 LLM 调用前模拟中断
- 从 checkpoint 恢复时不重复执行已完成工具
- 对 running 状态的非幂等工具阻断自动恢复，避免重复副作用

核心指标：

- `recovery_success_rate`：只统计期望自动恢复成功的场景
- `expected_outcome_rate`：统计所有场景是否符合预期结果
- `duplicate_tool_execution_count`
- `non_idempotent_protection_rate`
- `checkpoint_phase_correct_rate`
- `avg_resume_latency_ms`

## 扩展方向

后续建议新增三个 suite：

- `context_memory`：评估上下文压缩、must-keep 信息保留、token 预算达标率
- `mcp_a2a_protocol`：评估 MCP/A2A 工具发现、命名空间隔离、取消传播、SSE 顺序
- `reliability`：评估限流、熔断、重试、超时和 trace span 完整性
