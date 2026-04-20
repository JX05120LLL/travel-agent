# 数据库接入说明

当前项目已经进入 `PostgreSQL + SQLAlchemy` 阶段。

## 1. 需要补充的环境变量

在项目根目录 `.env` 中新增：

```env
DATABASE_URL=postgresql+psycopg://postgres:你的密码@localhost:5432/travel_agent
```

## 2. 当前已建立的模型

- `users`
- `sessions`
- `messages`

对应代码文件：

- `db/models.py`

## 3. 当前目标

先让项目代码可以正式连接 PostgreSQL，后面再继续做：

1. `POST /sessions`
2. `GET /sessions`
3. `GET /sessions/{session_id}/messages`
4. 改造 `POST /chat`

## 4. 说明

当前数据库表已经由 SQL 文件初始化：

- `sql/001_init_core_tables.sql`

所以这一步先不在代码里自动建表，而是先让 ORM 模型和已有表结构对齐，方便学习。
## 5. 当前需要执行的 SQL

如果是新库初始化，建议按顺序执行：

- `sql/001_init_core_tables.sql`
- `sql/002_enterprise_session_memory_schema.sql`

如果数据库已经执行过 `002`，这次为了让 `plan_option` 正式升级为“分支化方案模型”，还需要补执行：

- `sql/003_plan_option_branch_model.sql`
