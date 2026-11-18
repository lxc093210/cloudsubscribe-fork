"""观影搜索服务。"""

from typing import Iterable

from app.schemas.types import MediaType

from .client import GuanyingClient
from .resource import GuanyingResourceService
from ..magnet import clear_cache, media_titles, normalize_magnets
from ...core.search import SearchQuery


class GuanyingSearchService:
    def __init__(
            self,
            client: GuanyingClient,
            resources: GuanyingResourceService,
            resource_types: Iterable[str],
            result_limit: int,
    ):
        self._client = client
        self._resources = resources
        self._resource_types = tuple(resource_types)
        self._result_limit = result_limit

    def search(self, query: SearchQuery):
        titles = media_titles(query.mediainfo)
        resources = self._resources.search(
            title=titles[0] if titles else "",
            alternative_titles=titles[1:],
            year=getattr(query.mediainfo, "year", None),
            media_type="tv" if query.media_type == MediaType.TV else "movie",
            season=query.season,
            resource_type_order=self._resource_types,
            limit=(query.result_limit or self._result_limit)
            if query.resource_list_mode else self._result_limit,
            resource_list_mode=query.resource_list_mode,
        )
        return normalize_magnets(resources, "guanying")

    def resolve(self, **kwargs):
        return self._resources.resolve_resource(str(kwargs.get("resource_id") or ""))

    def clear_cache(self) -> int:
        return clear_cache(self._resources)
