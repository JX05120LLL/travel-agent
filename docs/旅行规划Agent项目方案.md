# 旅行规划小助手 Agent — 项目方案

> 用户输入旅游目的地，Agent 自动搜索景点/美食/天气/交通，生成完整行程规划。
> 支持多用户、会话管理，Docker 部署上服务器。

---

## 技术选型

| 分层 | 技术 | 说明 |
|------|------|------|
| LLM | DeepSeek-V3 | OpenAI 兼容接口，国内直连无需代理，价格便宜 |
| Agent 框架 | LangGraph | 节点+边的有向图编排，支持条件路由、多轮循环 |
| 后端框架 | FastAPI | 处理用户认证、会话管理、业务接口 |
| 网络搜索 | Tavily Search API | 专为 LLM 设计，免费额度 1000次/月 |
| 天气 | 和风天气 API | 国内免费，中文返回，支持7天预报 |
| 城际交通/路线 | 高德地图 API | 免费5000次/日，城际路线+市内交通+POI搜索 |
| 高铁/火车票 | RapidAPI（12306 封装） | 可查班次/余票/票价，免费额度有限，有失效风险 |
| 机票 | Amadeus API | 个人开发者可免费注册，沙盒环境查真实航班数据 |
| 向量数据库 | Qdrant（Docker） | 存储景点/美食/攻略知识库 + 用户偏好 |
| Embedding | sentence-transformers（本地） | 推荐 `shibing624/text2vec-base-chinese` |
| 关系型数据库 | PostgreSQL | 存用户信息、对话历史、收藏行程 |
| 缓存 | Redis | JWT Token 黑名单、API 结果缓存 |
| 前端界面 | Gradio | 网页对话界面，支持流式输出 |
| 通知推送 | 企业微信机器人 + 飞书机器人 | Webhook 推送行程卡片，主动通知天气/行程提醒 |
| 定时任务 | APScheduler | 出发前自动推送天气预报、当天行程提醒 |
| 部署 | Docker Compose | 一键启动所有服务 |

---

## 项目目录结构

```
travel-agent/
├── main.py                      # 入口：启动 Gradio 界面
├── requirements.txt
├── .env                         # API Keys（不提交 git！）
├── .gitignore
├── docker-compose.yml           # 一键部署所有服务
│
├── agent/
│   ├── __init__.py
│   ├── graph.py                 # LangGraph 核心：节点 + 边 + 路由逻辑
│   ├── state.py                 # Agent 状态定义
│   └── prompts.py               # 系统提示词
│
├── tools/
│   ├── __init__.py
│   ├── search.py                # Tavily 联网搜索（景点/美食/攻略）
│   ├── weather.py               # 和风天气查询
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── amap.py              # 高德地图：城际路线 + 市内交通 + POI
│   │   ├── train.py             # RapidAPI：高铁/火车班次/余票
│   │   └── flight.py           # Amadeus API：机票查询
│   ├── rag_retriever.py         # Qdrant 向量检索
│   └── notify.py                # 企业微信/飞书推送工具
│
├── notify/
│   ├── __init__.py
│   ├── wecom.py                 # 企业微信机器人 Webhook 推送
│   ├── feishu.py                # 飞书机器人 Webhook 推送
│   ├── scheduler.py             # APScheduler 定时任务（出发提醒/天气预报）
│   └── templates.py             # 卡片消息模板（行程卡片/天气卡片/提醒卡片）
│
├── rag/
│   ├── __init__.py
│   ├── ingest.py                # 文档向量化入库
│   └── data/                   # 原始知识库文档
│       ├── 北京景点.md
│       ├── 成都美食.md
│       └── ...
│
├── api/                         # FastAPI 后端（用户系统 + 会话管理）
│   ├── __init__.py
│   ├── app.py                   # FastAPI 入口
│   ├── routers/
│   │   ├── auth.py              # 注册/登录/JWT
│   │   ├── chat.py              # 对话接口（调 Agent）
│   │   └── history.py          # 历史记录/收藏行程
│   ├── models/
│   │   ├── user.py              # 用户数据模型
│   │   └── session.py          # 会话数据模型
│   └── middleware/
│       └── auth_middleware.py   # JWT 鉴权中间件
│
├── db/
│   ├── postgres.py              # PostgreSQL 连接和操作
│   └── redis_client.py         # Redis 连接
│
└── ui/
    └── app.py                   # Gradio 界面组件
```

---

## Agent 工作流

```
用户输入（"帮我规划从西安出发，3天成都旅行"）
              ↓
        [router 节点]  ←─────────────────────────────────┐
              │  LLM 判断当前需要调用哪个工具               │
              ├──→ [search_node]      联网搜索景点/美食/攻略 │
              ├──→ [weather_node]     查询目的地天气         │
              ├──→ [amap_node]        高德：城际路线+市内交通 │
              ├──→ [train_node]       RapidAPI：高铁班次余票 │
              ├──→ [flight_node]      Amadeus：机票查询      │
              ├──→ [rag_node]         检索本地知识库         │
              ├──→ [answer_node]      信息足够，生成最终答案 │
              └──→ [notify_node]      推送行程到企业微信/飞书│
                         │ 工具执行完，结果写入 State        │
                         └─────────────────────────────────┘
                               循环直到进入 answer_node
                                        ↓
                                 输出行程规划给用户
                                        ↓
                               [notify_node]（可选）
                         用户要求推送 → 发送飞书/企业微信卡片
```

---

## 向量数据库存什么 / 关系型数据库存什么

### Qdrant（向量数据库）— 存需要语义搜索的内容

```
景点知识库       "故宫是明清两代的皇家宫殿，位于北京中轴线中心..."
美食攻略         "成都宽窄巷子附近推荐：龙抄手、赖汤圆、夫妻肺片..."
旅行攻略长文     "三亚5日游攻略：第一天建议先去亚龙湾适应气候..."
常见Q&A          Q:"西藏高反怎么应对" A:"提前3天服用红景天..."
用户偏好摘要     "该用户偏好人少景点、预算中等、不喜欢爬山、爱吃辣"
                  ↑ 每次对话结束后，用 LLM 从对话中自动提取，向量化存入 Qdrant
                    下次对话开始时，先召回偏好，注入 system prompt，实现个性化推荐

# 偏好提取流程（借鉴 Hermes Agent 的跨 Session 记忆设计）：
# 1. 对话结束 → 调 LLM：「从以下对话中提取用户旅行偏好，JSON格式输出」
# 2. 输出示例：{"budget": "中等", "dislikes": ["爬山"], "food": ["辣"], "style": ["人少"]}
# 3. 向量化摘要文本 → upsert 到 Qdrant（user_id 作为 filter 条件）
# 4. 下次对话：检索该用户偏好 → 追加到 system prompt：
#    「该用户偏好：人少景点、预算中等、不喜欢爬山，请据此个性化推荐」
```

### PostgreSQL（关系型数据库）— 存结构化业务数据

```
users 表         id、昵称、邮箱、密码hash、注册时间
sessions 表      id、user_id、创建时间、标题（如"成都3日游"）
messages 表      id、session_id、role（user/assistant）、content、时间
favorites 表     id、user_id、行程内容、收藏时间
trip_reminders 表  id、user_id、destination、trip_date、webhook_url（飞书/企业微信）、已推送标记
```

---

## 用户系统 & 会话管理

```
注册/登录  →  返回 JWT Token
               ↓
每次请求携带 Token  →  FastAPI 中间件验证
               ↓
按 session_id 隔离对话历史
               ↓
LangGraph MemorySaver 维护当前会话上下文
               ↓
对话结束后，提取用户偏好 → 向量化 → 存 Qdrant
```

> 和你在实习中做的「对话式账号绑定 + 跨对话持久化」思路完全一致，只是换成了 Python 实现。

---

## 设计原则（借鉴 OpenClaw & Hermes Agent）

### 原则一：工具原子化（来自 Hermes Agent 的 47 工具设计）

Hermes Agent 把每个能力拆成独立的小工具，LangGraph 负责编排组合。本项目同样遵循此原则：

```
❌ 错误设计：一个大工具包揽所有
   get_travel_plan(destination, days) → 内部自己查天气+搜景点+查交通

✅ 正确设计：每个 API 一个原子工具，Agent 自由组合
   search_attractions(city)          → 只负责搜景点
   get_weather(city, date)           → 只负责查天气
   search_flights(origin, dest, date)→ 只负责查机票
   get_train_tickets(...)            → 只负责查火车
   search_restaurants(city)          → 只负责搜美食
   retrieve_local_knowledge(query)   → 只负责查本地RAG
```

**好处：** LangGraph 可以灵活按需调用，"只问天气"不会触发机票查询；同时每个工具可以独立测试、独立替换 API。

---

### 原则二：记得你、主动找你（来自 OpenClaw + Hermes Agent）

OpenClaw 的核心理念是"学习你的偏好"，Hermes 的核心是"跨 Session 召回"。两者都证明：**光会查信息不够，Agent 要有记忆，还要主动联系你。**

本项目的实现策略：

```
被动响应（基础）       用户问 → Agent 答
        +
主动记忆（进阶）       每次对话结束 → LLM 自动提取偏好 → 存 Qdrant
        +
主动出击（高级）       出发前3天 → Agent 主动推送天气预报到飞书/企业微信
```

---

### 原则三：一键可用（来自 OpenClaw 的 `npm i -g openclaw` 体验）

OpenClaw 的安装极度简洁。本项目 Docker Compose 部署目标：

```bash
git clone <repo>
cp .env.example .env   # 填入 API Keys
docker compose up      # 完事
```

任何人 clone 下来，3 条命令跑通，这是简历展示和面试 demo 的基本要求。

---

## 交通模块说明

| 功能 | 接口 | 说明 |
|------|------|------|
| 城际路线规划 | 高德地图跨城 API | 查高铁/飞机/大巴出行方案，含时间+换乘 |
| 市内交通 | 高德地图市内路线 API | 地铁/公交/步行导航 |
| 景点坐标/POI | 高德地图 POI 搜索 | 搜索景点、餐厅位置 |
| 高铁/火车班次 | RapidAPI 12306封装 | 查余票/票价/班次，注意稳定性问题 |
| 机票查询 | Amadeus API | 个人免费注册，沙盒查真实航班数据 |

> **RapidAPI 说明：** 依赖第三方封装，有失效风险，做好降级处理（查不到时走高德路线+Tavily搜索兜底）。

---

## 通知推送模块说明

### 两种机器人对比

| | 企业微信机器人 | 飞书机器人 |
|---|---|---|
| 接入方式 | 群机器人 Webhook | 群机器人 Webhook |
| 消息类型 | 文本/Markdown/图文 | 文本/富文本/交互式卡片 |
| 卡片效果 | 一般 | **更美观**，支持按钮交互 |
| 适合场景 | 企业内部演示 | 简历展示首选 |
| 费用 | 免费 | 免费 |
| 接入代码量 | ~20行 | ~30行 |

### 飞书卡片推送示例

```python
# notify/feishu.py
import httpx

async def send_itinerary_card(webhook_url: str, destination: str, days: int, plan: str):
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🗺️ {destination} {days}日行程规划"},
                "template": "blue"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": plan}},
                {"tag": "hr"},
                {"tag": "note", "elements": [
                    {"tag": "plain_text", "content": "由旅行规划 Agent 自动生成"}
                ]}
            ]
        }
    }
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=card)
```

### 定时提醒逻辑（APScheduler）

```
用户设置出发日期（如 2026-05-01）
              ↓
PostgreSQL 存储 trip_date + user_webhook
              ↓
APScheduler 每天检查数据库
              ↓
出发前3天 → 推送目的地天气预报卡片
出发当天早8点 → 推送当天行程摘要 + 实时天气 + 交通提示
```

### 触发方式

用户可通过对话主动触发推送，也可设置出发提醒：

```
用户："把这个行程发到飞书"           → 立即推送行程卡片
用户："5月1号出发，出发前提醒我天气"  → 注册定时任务
```

---

## 分阶段开发计划

### 一期：核心功能（边学边做，本地跑通）

**Phase 1：环境搭建 + 调通 LLM**
- 创建项目目录，配置 `.env`
- 安装依赖，写第一个脚本调用 DeepSeek 多轮对话
- 学会 OpenAI 兼容接口格式（messages 列表结构）
- **产出：** 命令行能和 LLM 正常多轮对话 ✅

**Phase 2：Tool Use / Function Calling**
- 写天气查询工具（最简单，一个 HTTP 请求）
- 用 LangChain `@tool` 装饰器注册工具
- 让 LLM 自动识别「需要查天气」并调用
- **严格遵循原子化原则**：每个 API 一个工具，单一职责
- **产出：** 问「北京明天天气怎么样」，LLM 自动调 API 回答 ✅

**Phase 3：LangGraph Agent 框架**
- 学 State / Node / Edge / Conditional Edge 四个核心概念
- 把所有工具（搜索/天气/交通）封装成节点
- 用条件边实现自动路由
- **产出：** 完整 Agent 骨架，能根据用户问题自动选工具 ✅

**Phase 4：Qdrant RAG 知识库 + 用户偏好记忆**
- Docker 启动本地 Qdrant
- 写 `ingest.py` 把景点/美食文档向量化存入 Qdrant
- 写 `rag_retriever.py` 做语义检索
- 接入 Agent：先查本地库，再联网搜索补充
- **实现偏好提取**：对话结束后 LLM 自动提取偏好 → 向量化 → upsert Qdrant
- **实现偏好召回**：新对话开始时检索用户偏好 → 注入 system prompt
- **产出：** 问「成都有什么好吃的」优先命中本地知识库；第二次规划自动记住"不喜欢爬山" ✅

**Phase 5：Gradio 界面 + 通知推送**
- 用 `gr.ChatInterface` 包装 Agent
- 支持流式逐字输出（打字机效果）
- 实现飞书机器人 Webhook 推送（30行代码）
- 实现企业微信机器人 Webhook 推送
- Agent 识别"发到飞书/企业微信"意图，自动触发推送
- **产出：** 完整可演示的旅行规划 Agent，支持一键推送行程到飞书/企业微信 ✅

---

### 二期：完善 + 部署上服务器

**Phase 6：用户系统 + 会话管理**
- 加 FastAPI 后端
- 实现注册/登录/JWT 鉴权（你 Spring 里做过，思路一样）
- PostgreSQL 存用户信息和对话历史
- Redis 做 Token 缓存
- **产出：** 多用户隔离，会话持久化 ✅

**Phase 7：定时主动推送（APScheduler）**
- 集成 APScheduler 进 FastAPI 应用
- PostgreSQL 新增 `trip_reminders` 表存储出发日期 + Webhook
- 实现出发前3天天气预报推送
- 实现出发当天早8点行程摘要推送
- **产出：** Agent 具备主动联系用户的能力，不再只是被动响应 ✅

**Phase 8：Docker Compose 部署**
- 编写 `docker-compose.yml`，打包所有服务
- 购买服务器（推荐 2核4G 起步），部署上线
- 配置域名 + HTTPS
- **产出：** 线上可访问，能给别人用 ✅

---

## 服务器配置建议

```
最低配置：2核 4G 内存（运行 Qdrant + Embedding 模型需要内存）
推荐配置：2核 8G 内存
推荐厂商：阿里云/腾讯云（学生机优惠价约 100元/年）

Docker Compose 服务清单：
├── travel-agent-api    FastAPI + LangGraph + APScheduler
├── qdrant              向量数据库
├── postgres            用户/会话/提醒数据
└── redis               缓存
```

---

## 需要准备的 API Key

| API | 注册地址 | 费用 |
|-----|----------|------|
| DeepSeek API | platform.deepseek.com | 充 5 元够用很久 |
| Tavily Search | app.tavily.com | 免费 1000次/月 |
| 和风天气 | dev.qweather.com | 免费版够用 |
| 高德地图 | lbs.amap.com | 免费 5000次/日 |
| RapidAPI（12306） | rapidapi.com | 按需选择，有免费额度 |
| Amadeus API | developers.amadeus.com | 免费沙盒环境 |
| 飞书机器人 | 飞书群设置 → 添加机器人 → 复制 Webhook URL | 完全免费 |
| 企业微信机器人 | 企业微信群设置 → 添加机器人 → 复制 Webhook URL | 完全免费 |

---

## requirements.txt 预览

```
# LLM & Agent
langchain
langgraph
langchain-openai          # DeepSeek 走 OpenAI 兼容接口

# 工具
tavily-python             # 联网搜索
httpx                     # HTTP 请求（天气/高德/Amadeus）

# 向量数据库
qdrant-client
sentence-transformers     # 本地 Embedding 模型

# 后端
fastapi
uvicorn
python-jose               # JWT
passlib                   # 密码加密
sqlalchemy                # ORM
asyncpg                   # PostgreSQL 异步驱动
redis

# 前端
gradio

# 通知推送
httpx                         # 飞书/企业微信 Webhook 调用（已包含在工具依赖中）
apscheduler                   # 定时任务（出发提醒/天气预报）

# 工具库
python-dotenv
pydantic
```

---

## 与你已有技术的对应关系

| 你的 Java/Spring 经验 | 对应 Python 新知识 |
|----------------------|------------------|
| Spring AI `@Tool` | LangChain `@tool` 装饰器，几乎一样 |
| Qdrant + Spring AI RAG | `qdrant-client` + LangChain RAG，换语言而已 |
| OpenClaw MCP 节点编排 | LangGraph Node + Edge，思路完全一致 |
| Spring Security + JWT | `python-jose` + FastAPI 依赖注入，思路一样 |
| MyBatis / JPA | SQLAlchemy ORM，更简单 |
| Redis 持久化 | redis-py，API 几乎一样 |
| 对话式绑定 binding.json | LangGraph MemorySaver + PostgreSQL |

---

## 做完能写进简历的内容

```
旅行规划 AI Agent                                          Python · 个人项目
- 基于 LangGraph 构建多工具 Agent，按原子化原则封装搜索/天气/高德/高铁/机票/RAG 六类独立工具，实现自动路由
- 接入 Qdrant 向量数据库构建景点知识库；对话结束后 LLM 自动提取用户偏好写入 Qdrant，新会话召回偏好注入 system prompt 实现个性化推荐
- 集成高德地图/和风天气/RapidAPI/Amadeus 多源 API，支持城际交通查询与中转路线规划
- 基于 FastAPI + JWT 实现多用户认证与会话隔离，PostgreSQL 持久化对话历史
- 集成飞书/企业微信 Webhook，支持一键推送行程卡片；APScheduler 实现出发前主动天气提醒
- Docker Compose 打包部署至云服务器，支持多用户在线使用
```
