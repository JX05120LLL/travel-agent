# 旅行规划 Agent

> 一个以 LangGraph 为核心的旅行规划 Agent 学习项目。  
> 项目目标不是只把功能做出来，而是通过真实项目边学边做，系统理解 Agent 应用开发流程。

## 项目定位

这个项目当前聚焦在旅行规划场景：

- 用户输入旅行需求
- Agent 自动调用天气、搜索、本地知识库等工具
- 输出结构化 Markdown 旅行建议
- 支持飞书 / 企业微信推送
- 后续会逐步扩展到用户系统、会话管理、高德地图、长期记忆、语音输入输出和部署上线

当前阶段的重点是：

- 学会 Tool Calling / Function Calling
- 学会 LangGraph 的 State / Node / Edge
- 学会 Agent 的短期上下文管理
- 学会把一个 Agent demo 逐步做成完整 AI 应用

## 当前已实现能力

- DeepSeek 模型接入
- LangChain Tool Use / Function Calling
- LangGraph 基础 Agent 循环
- 和风天气查询工具
- Tavily 联网搜索工具
- Qdrant 本地知识库检索
- FastAPI + SSE 流式输出
- 基础 Web 聊天界面
- 飞书 / 企业微信推送基础能力

## 技术栈

### 当前已用

| 模块 | 技术 |
|------|------|
| LLM | DeepSeek（OpenAI 兼容接口） |
| Agent 编排 | LangGraph |
| 后端 | FastAPI |
| 页面 | Jinja2 + 原生 JS |
| 搜索 | Tavily Search API |
| 天气 | 和风天气 API |
| 向量库 | Qdrant |
| Embedding | fastembed / BAAI bge-small-zh-v1.5 |
| 推送 | 飞书 Webhook / 企业微信 Webhook |

### 后续规划

| 模块 | 技术 |
|------|------|
| 用户 / 会话管理 | PostgreSQL + Redis |
| 前端升级 | React + TypeScript + Vite |
| 地图 / POI / 路线 | 高德地图 API |
| 长期记忆 | PostgreSQL + Qdrant |
| 语音转文字 / 文字转语音 | MiniMax STT / TTS |
| 部署 | Docker Compose + Nginx |

## 当前项目结构

```text
travel-agent/
├── agent/
│   ├── graph.py                 # LangGraph Agent 编排
│   ├── state.py                 # AgentState 定义
│   └── prompts.py               # 系统提示词
│
├── tools/
│   ├── weather.py               # 和风天气
│   ├── search.py                # Tavily 搜索
│   ├── rag_retriever.py         # Qdrant 检索
│   ├── feishu_sender.py         # 飞书推送
│   └── wechat_sender.py         # 企业微信推送
│
├── rag/
│   ├── ingest.py                # 文档向量化入库
│   └── data/                    # 本地知识库文档
│
├── web/
│   ├── app.py                   # FastAPI Web 入口
│   ├── templates/               # 页面模板
│   └── static/                  # 静态资源
│
├── docs/
│   ├── 旅行规划Agent项目方案.md   # 分阶段开发规划
│   └── 开发日志记录.md
│
├── test_agent.py
├── test_tool_use.py
├── test_deepseek.py
└── requirements.txt
```

## 当前工作流

```text
用户输入旅行问题
        ↓
FastAPI 接收请求
        ↓
LangGraph Agent
        ↓
LLM 判断是否需要工具
        ↓
  ├── 天气工具
  ├── 搜索工具
  ├── 本地知识库工具
  ├── 飞书推送工具
  └── 企业微信推送工具
        ↓
LLM 整合工具结果
        ↓
输出 Markdown 结果
        ↓
（可选）发送到飞书 / 企业微信
```

## 快速开始

### 环境要求

- Python 3.10+
- Docker（仅 Qdrant 需要）

### 1. 克隆项目

```bash
git clone <repo-url>
cd travel-agent
```

### 2. 创建并激活虚拟环境

Windows PowerShell:

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 `.env`

请在项目根目录准备 `.env`，至少配置：

```env
DEEPSEEK_API_KEY=your_key
TAVILY_API_KEY=your_key
QWEATHER_API_KEY=your_key
QWEATHER_HOST=your_qweather_host
FEISHU_WEBHOOK_URL=your_feishu_webhook
WECHAT_WORK_WEBHOOK_URL=your_wechat_webhook
```

## 5. 启动 Qdrant

```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

### 6. 初始化本地知识库

```bash
python rag/ingest.py
```

### 7. 启动 Web 应用

```bash
python web/app.py
```

打开浏览器访问：

```text
http://localhost:7860
```

## 常用测试方式

### CLI 测试 Agent

```bash
python test_agent.py
```

### CLI 测试 Tool Calling

```bash
python test_tool_use.py
```

### CLI 测试 DeepSeek 基础多轮对话

```bash
python test_deepseek.py
```

## 需要准备的服务 / API Key

| 服务 | 用途 |
|------|------|
| DeepSeek API | 大模型推理 |
| Tavily Search | 联网搜索补充信息 |
| 和风天气 | 天气查询 |
| Qdrant | 本地知识库向量检索 |
| 飞书机器人 | 推送 Markdown 行程 |
| 企业微信机器人 | 推送 Markdown 行程 |

后续还会接入：

- 高德地图 API
- PostgreSQL
- Redis
- MiniMax STT / TTS

## 当前项目状态

项目现在已经不是最初的 CLI Demo，而是一个可运行的 Agent 原型：

- 已经能完成：文本输入 -> Agent 调工具 -> Markdown 输出 -> 页面展示
- 已经具备：知识库检索、天气、联网搜索、推送
- 尚未完成：用户系统、多会话、长期记忆、高德地图、语音、部署

## 学习路线

这个项目的开发路线不是“先把所有功能堆满”，而是按学习收益来推进：

1. 吃透当前 Agent 原型
2. 做稳文本 Agent
3. 做用户系统和会话管理
4. 做 trip 出行管理
5. 接高德地图
6. 做长期记忆
7. 升级前端到 React + TypeScript
8. 接入 MiniMax STT / TTS
9. 部署上线

详细规划见：

- [docs/旅行规划Agent项目方案.md](docs/旅行规划Agent项目方案.md)

## 当前适合写进简历的描述

```text
旅行规划 Agent 系统                                        Python · 个人项目
- 基于 LangGraph 构建多工具旅行规划 Agent，支持天气、联网搜索、本地知识库与消息推送
- 使用 FastAPI + SSE 实现流式聊天页面，输出结构化 Markdown 行程建议
- 接入 Qdrant 构建本地攻略知识库，提升景点、美食、城市攻略问答效果
- 逐步扩展用户管理、会话管理、高德地图、长期记忆、语音能力与部署上线能力
```

## 说明

这个仓库当前仍处于持续迭代阶段，README 会优先反映“当前已实现状态”和“明确的后续路线”，更完整的学习型阶段规划请以 `docs/旅行规划Agent项目方案.md` 为准。
