# ADR-003: 采用 DashScope API（阿里云）作为 LLM 后端

## 状态
Accepted

## 背景

系统需要接入大语言模型作为 Agent 的推理引擎。需要在通用性、成本、区域合规之间做出选择。

**已知约束**：
- 项目面向中文场景，需要较好的中文理解能力
- 需要成本可控的 API 定价
- DashScope 提供 OpenAI 兼容接口，接入成本低

## 备选方案

### 方案 A：OpenAI API（GPT-4o / GPT-4o-mini）
- 通用性最强，模型能力领先
- 成本较高，中美跨境网络延迟不稳定

### 方案 B：DashScope API（qwen3.5-flash）
- 阿里云通义千问系列，中文场景优秀
- OpenAI 兼容接口，代码改动小
- 国内访问延迟低，成本相对可控

### 方案 C：自建开源模型（vLLM / Ollama）
- 完全自控，无 API 费用
- 需要 GPU 资源，运维复杂度高

## 决策

采用 **方案 B：DashScope API**

具体模型使用 `qwen3.5-flash`（通过 `gpt-5.4-mini` 接口名兼容），`base_url` 为 `https://dashscope.aliyuncs.com/compatible-mode/v1`。

## 原因

1. **中文场景优势**：qwen3.5-flash 在中文理解、指令遵循上对中文场景有优化
2. **接入成本低**：DashScope 提供 OpenAI 兼容接口，只需改 `base_url` 和 `api_key`，无需修改 SDK 调用方式
3. **国内访问延迟低**：无需跨境访问，响应速度更稳定
4. **成本可控**：qwen3.5-flash 定价较低，适合初期开发和测试
5. **快速验证**：无需自建 GPU 集群，可快速启动项目

## 影响

### 收益
- 项目可快速接入 LLM，专注 Agent 逻辑开发
- 阿里云内网访问，延迟和稳定性优于跨境访问

### 代价
- **厂商锁定**：若未来需要切换模型，需要修改 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_ID` 三个环境变量
- **模型能力受限**：qwen3.5-flash 是轻量模型，在复杂推理场景可能弱于 GPT-4o
- **合规依赖**：服务可用性依赖阿里云 DashScope 服务状态

### 技术债
- 当前 `config.py` 中硬编码了 DashScope 的 `base_url`，未来切换需同时修改代码中的 endpoint 逻辑（若 SDK 不自动处理）
- 尚未实现模型降级/熔断机制，DashScope 服务异常时 Agent 直接失败

## 相关链接

- 配置定义：[app/configs/config.py](app/configs/config.py)
- API 调用：[app/core/runner.py](app/core/runner.py)
- 阿里云 DashScope：[https://dashscope.console.aliyun.com/](https://dashscope.console.aliyun.com/)
