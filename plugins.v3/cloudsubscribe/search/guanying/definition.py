"""观影搜索渠道自描述规范与表单声明。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import GuanyingClient
from .provider import create_guanying_provider
from .resource import GuanyingResourceService
from .service import GuanyingSearchService
from ...core.definitions import FieldSpec, GroupSpec, SearchSourceDefinition


class GuanyingSourceDefinition(SearchSourceDefinition):
    id = "guanying"
    name = "观影"
    icon = "mdi-movie-open-outline"
    color = "cyan-darken-2"
    order = 46

    @classmethod
    def create_client(cls, config: Dict[str, Any], context: Optional[Any] = None) -> Any:
        ctx = context or {}
        username = str(cls.config_value(config, "guanying_username", "") or "").strip()
        password = str(cls.config_value(config, "guanying_password", "") or "")
        if not username or not password:
            return None
        return GuanyingClient(
            base_url=str(cls.config_value(config, "guanying_base_url", GuanyingClient.BASE_URL) or GuanyingClient.BASE_URL),
            username=username,
            password=password,
            proxy=ctx.get("proxy"),
            request_timeout=int(cls.config_value(config, "guanying_timeout", 60) or 60),
            request_interval=float(cls.config_value(config, "guanying_request_interval", 1.0) or 1.0),
            **cls.storage_hooks(ctx),
        )

    @classmethod
    def get_config_groups(cls, context: Optional[Dict[str, Any]] = None) -> List[GroupSpec]:
        return [
            GroupSpec(
                tab="guanying",
                title="观影账号",
                icon="mdi-account-key-outline",
                hint="自动完成浏览器安全验证，并使用网站账号登录后搜索网盘与磁力资源。",
                fields=[
                    FieldSpec(
                        key="guanying_account_info",
                        type="account",
                        account_key="search:guanying",
                        compact=True,
                        cols=12,
                    ),
                    FieldSpec(
                        key="guanying_base_url",
                        label="服务地址",
                        placeholder=GuanyingClient.BASE_URL,
                        default=GuanyingClient.BASE_URL,
                        cols=12,
                    ),
                    FieldSpec(key="guanying_username", label="登录账号", cols=6),
                    FieldSpec(
                        key="guanying_password",
                        label="登录密码",
                        type="password",
                        cols=6,
                    ),
                    FieldSpec(
                        key="test_guanying",
                        label="测试搜索",
                        type="test-source",
                        source="guanying",
                        cols=12,
                    ),
                ],
            ),
            GroupSpec(
                tab="guanying",
                title="搜索与风控",
                icon="mdi-shield-search",
                hint="搜索页与详情资源接口共用访问间隔，结果缓存 15 分钟。",
                fields=[
                    FieldSpec(
                        key="guanying_result_limit",
                        label="候选上限",
                        type="number",
                        default=10,
                        min=1,
                        max=30,
                        cols=4,
                    ),
                    FieldSpec(
                        key="guanying_request_interval",
                        label="请求间隔",
                        type="number",
                        default=1.0,
                        min=0.5,
                        max=10,
                        step=0.5,
                        suffix="秒",
                        cols=4,
                    ),
                    FieldSpec(
                        key="guanying_timeout",
                        label="搜索超时",
                        type="number",
                        default=60,
                        min=5,
                        max=120,
                        suffix="秒",
                        cols=4,
                    ),
                ],
            ),
        ]

    @classmethod
    def create_provider(
            cls, service: Any, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Any:
        ctx = context or {}
        resource_types = ctx.get("resource_types", ())
        if not client or not client.is_configured or not resource_types:
            return None
        resources = GuanyingResourceService(client)
        limit = int(cls.config_value(config, "guanying_result_limit", 10) or 10)
        search_service = GuanyingSearchService(client, resources, resource_types, limit)
        return create_guanying_provider(
            search_service,
            client,
            resource_types,
            {"result_limit": limit, "resource_types": list(resource_types)},
        )
