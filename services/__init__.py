"""按层分组后的服务包，而不是单层平铺目录。

子包说明：
- `services.core`：公共错误、熔断保护等横切能力
- `services.chat`：聊天运行时、记忆、召回和单轮执行
- `services.session`：会话生命周期和工作区管理
- `services.travel`：旅行规划、Trip 和导出相关能力
- `services.providers`：地图、酒店、12306 等外部能力编排
- `services.channels`：OpenClaw 之类的渠道适配层
"""

__all__ = [
    "auth",
    "core",
    "chat",
    "session",
    "travel",
    "providers",
    "channels",
    "integrations",
]
