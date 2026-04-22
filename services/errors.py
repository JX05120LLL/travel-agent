"""Service 层通用异常。

这里先用很轻量的异常分层，把 Web 层和业务层隔开。
后续如果要继续往 Java 风格靠，可以再细分成更明确的业务异常族。
"""

from __future__ import annotations


class ServiceError(Exception):
    """业务层基类异常。"""


class ServiceNotFoundError(ServiceError):
    """业务对象不存在。"""


class ServiceValidationError(ServiceError):
    """业务参数不合法或状态不允许。"""


class ServiceConfigError(ServiceError):
    """运行配置缺失或不合法。"""


class ServiceIntegrationError(ServiceError):
    """调用外部服务失败。"""
