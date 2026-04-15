# 旅行规划小助手 Agent

> 输入旅游目的地，Agent 自动搜索景点 / 美食 / 天气 / 交通，生成完整行程规划。
> 支持多用户、会话管理，Docker 一键部署。

## 技术栈

| 分层 | 技术 |
|------|------|
| LLM | DeepSeek-V3（OpenAI 兼容接口）|
| Agent 框架 | LangGraph |
| 后端框架 | FastAPI |
| 联网搜索 | Tavily Search API |
| 天气 | 和风天气 API |
| 交通 / 地图 | 高德地图 API |
| 火车票 | RapidAPI（12306 封装）|
| 机票 | Amadeus API |
| 向量数据库 | Qdrant（Docker）|
| Embedding | sentence-transformers（本地）|
| 关系型数据库 | PostgreSQL |
| 缓存 | Redis |
| 前端 | Gradio |
| 通知推送 | 飞书机器人 / 企业微信机器人 |
| 定时任务 | APScheduler |
| 部署 | Docker Compose |

## 项目结构

```
travel-agent/
├── main.py                      # 入口：启动 Gradio 界面
├── requirements.txt
├── .env                         # API Keys（不提交 git）
├── docker-compose.yml
│
├── agent/
│   ├── graph.py                 # LangGraph 核心：节点 + 边 + 路由
│   ├── state.py                 # Agent 状态定义
│   └── prompts.py               # 系统提示词
│
├── tools/
│   ├── search.py                # Tavily 联网搜索
│   ├── weather.py               # 和风天气查询
│   ├── transport/
│   │   ├── amap.py              # 高德地图（城际路线 + 市内交通 + POI）
│   │   ├── train.py             # 高铁 / 火车班次余票
│   │   └── flight.py            # 机票查询
│   ├── rag_retriever.py         # Qdrant 向量检索
│   └── notify.py                # 飞书 / 企业微信推送
│
├── rag/
│   ├── ingest.py                # 文档向量化入库
│   └── data/                    # 本地知识库（景点 / 美食攻略）
│
├── api/                         # FastAPI 后端
│   ├── routers/                 # auth / chat / history
│   ├── models/                  # 数据模型
│   └── middleware/              # JWT 鉴权
│
├── notify/
│   ├── wecom.py                 # 企业微信 Webhook
│   ├── feishu.py                # 飞书 Webhook
│   ├── scheduler.py             # APScheduler 定时任务
│   └── templates.py             # 消息卡片模板
│
├── db/
│   ├── postgres.py              # PostgreSQL
│   └── redis_client.py         # Redis
│
└── ui/
    └── app.py                   # Gradio 界面
```

## Agent 工作流

```
用户输入（"帮我规划从西安出发，3天成都旅行"）
              ↓
        [router 节点]  ←─────────────────────────────────┐
              │  LLM 判断当前需要调用哪个工具               │
              ├──→ [search_node]      联网搜索景点/美食/攻略 │
              ├──→ [weather_node]     查询目的地天气         │
              ├──→ [amap_node]        高德：城际路线+市内交通 │
              ├──→ [train_node]       高铁班次余票           │
              ├──→ [flight_node]      机票查询               │
              ├──→ [rag_node]         检索本地知识库         │
              └──→ [answer_node]      信息足够，生成最终答案 │
                         │ 工具执行完，结果写入 State        │
                         └─────────────────────────────────┘
                                        ↓
                                 输出行程规划给用户
                                        ↓
                               [notify_node]（可选）
                         用户要求推送 → 发送飞书/企业微信卡片
```

## 快速开始

### 环境要求

- Python 3.10+
- Docker & Docker Compose

### 本地运行

```bash
git clone <repo-url>
cd travel-agent

# 安装依赖
pip install -r requirements.txt

# 配置 API Keys
cp .env.example .env
# 编辑 .env，填入各服务 API Key

# 启动 Qdrant（向量数据库）
docker run -d -p 6333:6333 qdrant/qdrant

# 向量化知识库
python rag/ingest.py

# 启动 Agent
python main.py
```

### Docker 一键部署

```bash
git clone <repo-url>
cp .env.example .env   # 填入 API Keys
docker compose up
```

## 需要准备的 API Key

| API | 获取地址 | 费用 |
|-----|---------|------|
| DeepSeek | platform.deepseek.com | 充 5 元够用很久 |
| Tavily Search | app.tavily.com | 免费 1000次/月 |
| 和风天气 | dev.qweather.com | 免费版够用 |
| 高德地图 | lbs.amap.com | 免费 5000次/日 |
| RapidAPI（12306） | rapidapi.com | 有免费额度 |
| Amadeus | developers.amadeus.com | 免费沙盒环境 |
| 飞书机器人 | 飞书群设置 → 添加机器人 | 完全免费 |
| 企业微信机器人 | 企业微信群设置 → 添加机器人 | 完全免费 |

## 分阶段开发进度

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | 环境搭建 + 调通 LLM 多轮对话 | ✅ 完成 |
| Phase 2 | Tool Use / Function Calling | ✅ 完成 |
| Phase 3 | LangGraph Agent 框架 | 进行中 |
| Phase 4 | Qdrant RAG 知识库 + 用户偏好记忆 | 待开始 |
| Phase 5 | Gradio 界面 + 飞书/企业微信推送 | 待开始 |
| Phase 6 | FastAPI 用户系统 + 会话管理 | 待开始 |
| Phase 7 | APScheduler 定时主动推送 | 待开始 |
| Phase 8 | Docker Compose 部署上线 | 待开始 |

## 设计原则

**工具原子化**：每个 API 封装为独立工具，单一职责，LangGraph 按需组合调用，互不干扰。

**持久化记忆**：对话结束后 LLM 自动提取用户偏好写入 Qdrant，新会话开始时召回偏好注入 system prompt，实现个性化推荐。

**主动推送**：APScheduler 定时检查出发日期，出发前3天自动推送天气预报，出发当天早8点推送行程摘要。
