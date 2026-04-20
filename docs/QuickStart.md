# Minimal Agent API - QuickStart

## 1. 依赖版本

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | >= 3.10 | 推荐 3.12+ |
| fastapi | 最新 | Web 框架 |
| openai | 最新 | LLM API 客户端 |
| python-dotenv | 最新 | 环境变量管理 |
| uvicorn | 最新 | ASGI 服务器 |
| pytest | 最新 | 测试框架 |

## 2. 环境变量

在项目根目录创建 `.env` 文件：

```bash
# 模型名称
LLM_MODEL_ID=qwen3.5-flash

# API 密钥（替换为你的密钥）
LLM_API_KEY=sk-your-api-key-here

# 服务地址
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 超时时间（秒）
LLM_TIMEOUT=60

# Agent 最大执行步数
MAX_STEPS=5
```

> **注意**: `LLM_API_KEY` 必须替换为有效的阿里云 DashScope API 密钥。

## 3. 本地服务启动

### 3.1 安装依赖

```bash
pip install -r requirements.txt
```

### 3.2 启动 API 服务

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

服务启动后访问：
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/

### 3.3 数据库 / 缓存 / 消息队列

**本项目无外部依赖**，全部使用内存管理：

| 组件 | 实现方式 | 说明 |
|------|----------|------|
| 会话存储 | `InMemorySessionManager` | 内存存储，重启后丢失 |
| 工具注册 | `ToolRegistry` | 内存字典 |
| 事件通道 | `EventChannel` | 内存队列 |

如需持久化，请自行扩展 `BaseSessionManager` 接口。

## 4. 测试数据准备

### 4.1 内置工具

项目内置两个工具，注册在默认注册表中：

| 工具 | 参数 | 说明 |
|------|------|------|
| `calculator` | `expression: string` | 数学表达式计算 |
| `get_current_time` | `city: string` | 获取城市当前时间 |

支持的 city: `tokyo`, `beijing`, `shanghai`, `london`, `new york`

### 4.2 测试 API

**普通对话：**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

**流式对话（带 SSE）：**
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "北京现在几点了"}'
```

### 4.3 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/core/test_runner.py

# 运行并显示打印
pytest -s tests/tools/test_registry.py
```

## 5. 一键启动命令

```bash
# 安装依赖 + 启动服务
pip install -r requirements.txt && uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

## 6. API 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| POST | `/chat` | 普通对话 |
| POST | `/chat/stream` | 流式对话（SSE） |

### 请求格式 (ChatRequest)

```json
{
  "message": "用户消息",
  "session_id": "可选，会话 ID"
}
```

### 响应格式 (ChatResponse)

```json
{
  "session_id": "会话 ID",
  "answer": "模型回复",
  "history_length": 消息历史长度
}
```
