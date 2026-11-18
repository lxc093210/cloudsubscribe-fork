"""观影搜索能力声明。"""

from typing import Any, Iterable, Mapping

from ...core.search import SearchCapability, SearchPolicy, SearchProvider


def create_guanying_provider(
        service: Any,
        client: Any,
        resource_types: Iterable[str],
        cache_context: Mapping[str, Any],
) -> SearchProvider:
    return SearchProvider(
        key="guanying",
        name="观影",
        resource_types=frozenset(resource_types),
        services={
            SearchCapability.RESOURCE_SEARCH: service,
            SearchCapability.RESOURCE_RESOLVE: service,
            SearchCapability.ACCOUNT: client,
            SearchCapability.CACHE_MAINTENANCE: service,
            SearchCapability.LIFECYCLE: client,
        },
        policy=SearchPolicy(
            cacheable=False,
            cache_context=cache_context,
            max_concurrency=1,
        ),
    )
