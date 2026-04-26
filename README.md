# Travel Agent

一个面向中文旅行规划场景的 Agent 项目。

它不是单纯的聊天机器人，而是把用户的旅行需求沉淀为可追踪、可导出、可继续完善的正式行程方案。当前项目正从“能跑的 Demo”进入“产品化收口阶段”，重点围绕成品行程单、地图预览、会话工作区、导出和外部能力编排持续打磨。

---

## 当前产品定位

当前产品目标是做一个中文旅行规划 Agent，核心体验是：

- 用户用自然语言描述目的地、天数、预算、偏好和出发信息
- 系统自动补齐天气、到达方式、酒店建议、景点顺序、交通衔接、美食和预算
- 最终输出可直接发送给用户的成品行程单
- 同时保留结构化工作区能力，支撑候选方案、比较、正式 Trip、导出和后续推送

当前主交付物是：

- `document_markdown`
- `delivery_payload`
- `trip`
- 地图预览 / 高德专属地图链接

---

## 当前已实现能力

### 1. 会话与工作区

- 会话创建、切换、重命名、删除、置顶
- 消息持久化、历史回放、会话事件记录
- 候选方案 `plan_option`、方案比较 `plan_comparison`、正式行程 `trip`
- checkpoint、memory、recall、preferences 等工作区数据层

### 2. Agent 编排

- 基于 `LangGraph` 的 `llm -> tools -> llm` 循环
- 系统提示词与工具策略集中在 `agent/prompts.py`
- 工具注册集中在 `agent/graph.py`
- 通过 `services/session_service.py` 编排会话动作、规划流程与工作区同步

### 3. 地图与路线能力

- 高德 Web 服务能力：POI、地理编码、天气、步行/驾车/公交路线、周边美食、酒店发现
- 高德 MCP 能力：地图预览、导航链接、专属地图链接尝试生成
- 已有结构化地图结果：`map_preview`

### 4. 火车 / 高铁到达方案

- 已有统一的 `RailProvider` 架构
- 已接入 `MCP12306Provider`
- 保留第三方 fallback 与 placeholder 兜底
- 始终附带 `12306` 官方提醒与官网 / App 入口说明

### 5. 成品行程单与导出

- `TripDocumentService` 负责把结构化上下文编排为 `delivery_payload` 和 `document_markdown`
- `TripExportService` 支持导出 Markdown / PDF
- 当前导出源统一围绕 Trip 文档，不再直接拼聊天正文

### 6. 前端产品态

- 主视图已收口为“聊天 + 成品行程单”方向
- 左侧会话栏与右侧聊天区滚动解耦
- 会话三点菜单承载置顶、重命名、删除、导出入口
- 工具过程默认折叠，尽量减少开发态信息暴露

---

## 当前未完成与限制

### 火车票 / 高铁票

- 当前只做查询参考，不做站内购票闭环
- 车次、票价、余票、购票规则始终以 `12306` 官方为准
- 第三方与 MCP 查询能力仍在持续验收稳定性

### 酒店 / 民宿

- 当前以高德酒店发现为主
- 不承诺实时成交价，不做站内下单
- 输出中需要提示用户去美团、携程、飞猪等平台确认房态与价格

### 地图预览

- 高德地图预览与专属地图能力已接入基础链路
- 仍在持续收口成更产品化的“左侧 Day 行程 + 右侧实时地图预览”体验
- 当前更偏“轻量预览 + 跳转链接”，不是完整携程式地图产品态

### 产品阶段

- 当前项目处于“产品化收口阶段”，不是简单 Demo
- 也尚未达到生产级交付状态
- 文档、前端交互、导出样式、外部服务稳定性仍在持续整理

---

## 架构总览

### 主要目录

```text
agent/      LangGraph Agent、状态、提示词、工具编排
services/   业务编排、provider/service 封装、导出、记忆、召回、工作区
tools/      Agent 可调用工具层
web/        FastAPI、SSE、模板、静态资源、导出接口
db/         SQLAlchemy 模型与 repository
domain/     纯规则、拆分、排序、摘要等领域逻辑
tests/      服务、工具、Web、前端 contract、集成 smoke
```

### 分层原则

当前项目大体按下面的企业常见分层推进：

- `Tool`：面向 Agent 暴露能力
- `Provider`：适配某个外部数据源或协议
- `Service`：组合业务逻辑、做降级与结构化输出
- `Orchestrator`：会话 / Trip / 工作区编排
- `Delivery`：面向前端与导出的最终交付层

---

## MCP 与外部能力接入策略

项目当前对 MCP 的定位是：`可插拔增强层`，不是唯一主业务数据平面。

当前策略：

- 高德 MCP：用于地图预览、导航链接、专属地图等增强能力
- 12306 MCP：作为火车票 / 高铁票查询型 Provider
- 本地 `service/provider` 编排仍是主链路，方便治理、降级、缓存、审计与测试

外部能力主要包括：

- 高德 Web 服务 API
- 高德 MCP
- 12306 MCP
- Tavily 搜索
- 本地知识库 / RAG
- PDF 导出依赖 `reportlab`

---

## 12306 MCP 本地运行说明

项目默认通过独立 HTTP 服务接入 `12306 MCP`，配置项在 `.env` 中：

```env
MCP_12306_HTTP_URL=http://127.0.0.1:18000/mcp
MCP_12306_TIMEOUT_SECONDS=15
```

推荐启动方式：

```powershell
$env:SERVER_PORT="18000"
$env:DEBUG="false"
uvx --from mcp-server-12306 python -m mcp_12306.server
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:18000/health -UseBasicParsing
```

注意事项：

- 如果本机存在全局环境变量 `DEBUG=release`，需要显式覆盖为 `false`
- 如果 `18000` 被占用，请同步修改 `MCP_12306_HTTP_URL`
- 主项目调用的是 MCP 服务地址，不是直接把 12306 逻辑内嵌进主进程

---

## 高德地图 / 高德 MCP 在项目中的角色

### 高德 Web 服务 API

负责：

- POI 搜索
- 地理编码 / 逆地理编码
- 天气
- 步行 / 公交 / 驾车路线
- 酒店和美食发现

### 高德 MCP

负责：

- 地图预览增强
- 导航链接 / 打车链接
- 专属地图链接尝试生成
- 与 Agent 的地图能力衔接

### 当前判断

如果要做成更接近携程 AI 助手的体验，后续需要：

- 继续保留高德 MCP 与 Web 服务 API 作为数据能力
- 额外在前端做真正的地图渲染与 Day 路线联动
- 让 `daily_itinerary` 与 `map_preview` 成为页面主消费对象

---

## 测试与本地运行

### 环境准备

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 启动 Web

请按你当前项目已有启动方式运行 FastAPI Web 入口。

### 常用验证

```powershell
node --check web/static/app.js
venv\Scripts\python -m pytest tests/test_session_service.py -q
venv\Scripts\python -m pytest tests/test_frontend_layout_contract.py -q
```

### 当前测试覆盖方向

- Agent prompt / graph smoke
- Amap service / tools
- 12306 MCP provider / tool
- session / memory / recall / checkpoint
- trip document / export
- web API / workspace API
- frontend layout contract / markdown smoke

---

## 文档索引

建议按下面顺序阅读：

1. [AI应用开发学习计划-基于TravelAgent项目](docs/AI应用开发学习计划-基于TravelAgent项目.md)
2. [当前进度与决策](docs/当前进度与决策.md)
3. [开发日志记录](docs/开发日志记录.md)
4. [旅行规划Agent项目方案](docs/旅行规划Agent项目方案.md)
5. [项目分层方案](docs/项目分层方案.md)
6. [MCP服务接入方案](docs/MCP服务接入方案.md)
7. [agent-session-memory-context-design](docs/agent-session-memory-context-design.md)

---

## 当前建议

如果你接下来准备边维护项目边系统学习，建议先看：

- `agent/graph.py`
- `agent/prompts.py`
- `services/session_service.py`
- `services/intent_router.py`
- `services/memory_service.py`
- `services/train_12306_service.py`
- `services/amap_mcp_service.py`
- `services/trip_document_service.py`

这些模块基本覆盖了 AI 应用开发岗位里最核心的几个能力面：Prompt、Context、Tool、Provider、Memory、Recall、Orchestration、Delivery。
