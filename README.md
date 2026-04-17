# Travel Agent

一个面向中文旅行规划场景的多模态 Agent 应用。  
用户可以通过文本或语音描述旅行需求，系统会自动结合天气、知识库、地图和搜索能力，生成结构化 Markdown 攻略，并支持一键发送到飞书或企业微信。

---

## 项目亮点

- 基于 `LangGraph` 构建多工具 Agent，支持自动工具选择与多轮编排
- 接入 `高德地图 API`，支持景点、酒店、POI 检索与路线规划
- 接入 `和风天气`、`Tavily`、本地 `Qdrant` 知识库，提供更完整的旅行信息
- 支持 `MiniMax STT / TTS`，实现语音输入与语音播报
- 支持 `PostgreSQL + Redis + Qdrant` 的分层存储设计
- 支持 `飞书 / 企业微信` 推送结构化 Markdown 行程
- 支持用户系统、会话管理、旅行计划保存、收藏与提醒
- 支持 `Docker Compose + Nginx` 部署到云服务器，通过域名访问

---

## 核心功能

### 1. 智能旅行规划

用户可以直接输入自然语言需求，例如：

> 我想去南京旅游 5 天，帮我整理一份攻略，包含天气、出行方式、酒店住宿和每天行程安排，最后发到我的飞书。

系统会自动完成：

- 识别目的地、天数、预算、偏好
- 查询天气信息
- 检索本地攻略知识库
- 查询高德地图 POI / 路线 / 酒店
- 补充联网搜索结果
- 输出结构化 Markdown 攻略

### 2. 多轮对话与会话管理

- 一个用户可以创建多个独立对话
- 每个对话都有独立的上下文和消息历史
- 支持查看历史会话、继续追问、保存结果

### 3. 长期用户记忆

系统支持跨对话记住用户稳定偏好，例如：

- 喜欢轻松路线
- 不喜欢爬山
- 更关注美食和夜景
- 住宿偏好靠近地铁或商圈

### 4. 结构化旅行计划

生成结果不只是普通问答，而是可保存、可分享、可再次编辑的旅行方案，包括：

- 行程概览
- 天气建议
- 交通方式
- 酒店住宿建议
- 每日安排
- 美食推荐
- 注意事项

### 5. 消息推送

- 一键发送旅行攻略到飞书
- 一键发送旅行攻略到企业微信
- 支持出发前天气提醒与出发当天行程提醒

### 6. 语音交互

- 语音输入：MiniMax STT
- 语音播报：MiniMax TTS
- 支持“说需求 -> 自动生成攻略 -> 播报摘要”

---

## 技术架构

### 应用层

- `Frontend`: React + TypeScript + Vite
- `Backend`: FastAPI
- `Agent`: LangGraph

### 能力层

- `LLM`: DeepSeek / OpenAI 兼容接口
- `Map`: 高德地图 API
- `Weather`: 和风天气 API
- `Search`: Tavily Search API
- `Voice`: MiniMax STT / TTS
- `Notify`: 飞书 Webhook / 企业微信 Webhook

### 数据层

- `PostgreSQL`: 用户、会话、消息、trip、收藏、提醒、结构化偏好
- `Redis`: Token、缓存、热点查询结果
- `Qdrant`: 本地攻略知识库、长期偏好语义记忆

---

## 系统设计

### 记忆分层

项目采用三层记忆设计：

- 短期记忆：当前会话内的最近消息、工具结果、当前 trip 草稿
- 会话摘要：当前对话的阶段性总结
- 长期记忆：用户跨对话稳定偏好

### 数据存储职责

#### PostgreSQL

用于存储结构化业务数据：

- users
- sessions
- messages
- trips
- trip_itineraries
- trip_favorites
- trip_reminders
- user_preferences

#### Redis

用于存储：

- JWT token
- 高频缓存
- 查询结果缓存
- 临时会话状态

#### Qdrant

用于存储：

- 景点 / 美食 / 城市攻略知识库
- 用户长期偏好摘要

---

## 整体流程

```text
文本 / 语音输入
      ↓
前端页面（React + TS）
      ↓
FastAPI 接口层
      ↓
LangGraph Agent
      ↓
工具编排
  ├── 天气
  ├── 高德地图
  ├── Tavily 搜索
  ├── Qdrant 知识库
  ├── MiniMax STT / TTS
  └── 飞书 / 企业微信推送
      ↓
结构化 Markdown 输出
      ↓
保存 trip / 推送 / 播报
```

---

## 技术栈

| 模块 | 技术 |
|------|------|
| LLM | DeepSeek（OpenAI 兼容接口） |
| Agent 编排 | LangGraph |
| 后端框架 | FastAPI |
| 前端框架 | React + TypeScript + Vite |
| ORM / 数据模型 | SQLAlchemy + Pydantic |
| 关系型数据库 | PostgreSQL |
| 缓存 | Redis |
| 向量数据库 | Qdrant |
| 地图与路线 | 高德地图 API |
| 天气 | 和风天气 API |
| 联网搜索 | Tavily Search API |
| 语音能力 | MiniMax STT / TTS |
| 推送 | 飞书 Webhook / 企业微信 Webhook |
| 部署 | Docker Compose + Nginx |

---

## 项目结构

```text
travel-agent/
├── backend/
│   ├── agent/                  # LangGraph Agent 编排与状态管理
│   ├── api/                    # FastAPI 路由
│   ├── db/                     # PostgreSQL / Redis / 数据模型
│   ├── services/               # 业务服务层
│   ├── tools/                  # 天气、地图、搜索、推送、语音等工具
│   ├── rag/                    # 知识库与向量化
│   └── web/                    # Web 入口 / SSE / 静态服务
│
├── frontend/
│   ├── src/
│   │   ├── pages/              # 页面
│   │   ├── components/         # 通用组件
│   │   ├── features/           # 会话、trip、语音、用户功能模块
│   │   ├── services/           # API 请求层
│   │   ├── store/              # 状态管理
│   │   └── types/              # TS 类型定义
│
├── docs/
│   ├── 旅行规划Agent项目方案.md
│   └── 开发日志记录.md
│
├── deploy/
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── .env.example
│
└── README.md
```

---

## 本地开发

### 环境要求

- Python 3.10+
- Node.js 18+
- Docker
- PostgreSQL
- Redis

### 1. 克隆仓库

```bash
git clone <repo-url>
cd travel-agent
```

### 2. 后端环境

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=your_key
TAVILY_API_KEY=your_key
QWEATHER_API_KEY=your_key
QWEATHER_HOST=your_qweather_host
AMAP_API_KEY=your_key
FEISHU_WEBHOOK_URL=your_feishu_webhook
WECHAT_WORK_WEBHOOK_URL=your_wechat_webhook
POSTGRES_URL=postgresql://user:password@localhost:5432/travel_agent
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333
MINIMAX_API_KEY=your_key
```

### 4. 启动依赖服务

```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
docker run -d --name redis -p 6379:6379 redis
```

PostgreSQL 可以本地安装，也可以用 Docker：

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=travel_agent \
  -p 5432:5432 \
  postgres:16
```

### 5. 初始化知识库

```bash
python rag/ingest.py
```

### 6. 启动后端

```bash
python web/app.py
```

### 7. 启动前端

```bash
cd frontend
npm install
npm run dev
```

---

## Docker Compose 部署

```bash
docker compose up -d
```

部署服务建议包括：

- frontend
- backend
- postgres
- redis
- qdrant
- nginx

---

## API 能力概览

### 用户系统

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

### 聊天与会话

- `POST /chat`
- `GET /sessions`
- `POST /sessions`
- `GET /sessions/{id}/messages`

### trip 管理

- `POST /trips`
- `GET /trips`
- `GET /trips/{trip_id}`
- `PUT /trips/{trip_id}`
- `DELETE /trips/{trip_id}`

### 收藏与提醒

- `POST /favorites/{trip_id}`
- `DELETE /favorites/{trip_id}`
- `POST /reminders`
- `GET /reminders`

### 语音

- `POST /voice/stt`
- `POST /voice/tts`

---

## 输出格式示例

系统会优先输出结构化 Markdown：

```md
# 南京 5 天旅行攻略

## 一、行程概览

## 二、天气建议

## 三、出行方式

## 四、住宿建议

## 五、每日安排

## 六、美食推荐

## 七、注意事项
```

---

## 部署建议

### 推荐服务器

- 2 核 4G 起步
- 推荐 2 核 8G

### 推荐部署方式

- Ubuntu / Debian
- Docker Compose
- Nginx 反向代理
- 域名 + HTTPS

### 推荐上线能力

- 主站域名访问
- 登录与多会话
- 文本对话
- 语音输入 / 播报
- 飞书 / 企业微信推送

---

## 适合写进简历的描述

```text
旅行规划 Agent 系统                                        Python / TypeScript · 个人项目
- 基于 LangGraph 构建多工具旅行规划 Agent，统一编排天气、联网搜索、本地知识库、高德地图、推送与语音能力
- 使用 FastAPI + PostgreSQL + Redis 实现用户管理、会话管理、旅行计划保存、收藏与提醒系统
- 基于 Qdrant 构建攻略知识库与用户长期偏好记忆，支持跨会话个性化推荐
- 使用 React + TypeScript 构建前端页面，支持多会话聊天、Markdown 展示与语音交互
- 接入 MiniMax STT/TTS 实现语音输入与结果播报，接入飞书 / 企业微信完成结构化攻略推送
- 通过 Docker Compose + Nginx 部署至云服务器，支持域名访问
```

---

## License

本项目仅用于学习、演示与个人项目实践。
