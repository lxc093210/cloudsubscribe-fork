"""观影影视匹配与资源转换服务。"""

from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, List, Optional

from app.log import logger

from .client import GuanyingClient, GuanyingError
from .parser import parse_magnets, parse_panlist
from ..magnet import parse_size_str
from ..matching import extract_season, extract_year, resource_title_matches
from ..types import (
    SUPPORTED_RESOURCE_TYPES,
    append_share_password,
    resource_type_from_text,
    resource_type_from_url,
)
from ...utils.cache import create_platform_ttl_cache


class GuanyingResourceService:
    """检索详情页并转换为 CloudSubscribe 的统一资源记录。"""

    def __init__(self, client: GuanyingClient):
        self._client = client
        self._lock = threading.RLock()
        identity = f"{client.base_url}|{client.username.casefold()}"
        self._search_cache = create_platform_ttl_cache(
            "guanying:search", identity, maxsize=256, ttl=15 * 60
        )
        self._resource_cache = create_platform_ttl_cache(
            "guanying:resources", identity, maxsize=512, ttl=15 * 60
        )
        self._resolved: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _card_matches(
            card: Dict[str, str],
            expected_titles: List[str],
            expected_year: str,
            media_type: str,
    ) -> bool:
        if media_type == "movie" and card.get("dir") != "mv":
            return False
        if media_type == "tv" and card.get("dir") not in {"tv", "ac"}:
            return False
        title = str(card.get("title") or "")
        if not resource_title_matches(title, expected_titles, expected_year, strict_year=False):
            return False
        card_year = extract_year(title)
        if expected_year and card_year:
            if media_type == "movie" and card_year != expected_year:
                return False
            if media_type == "tv" and abs(int(card_year) - int(expected_year)) > 1:
                return False
        return True

    def search(
            self,
            title: str,
            alternative_titles: Optional[Iterable[str]] = None,
            year: Optional[str] = None,
            media_type: str = "movie",
            season: Optional[int] = None,
            resource_type_order: Optional[Iterable[str]] = None,
            limit: int = 10,
            resource_list_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        del resource_list_mode
        titles = list(dict.fromkeys(
            str(value).strip()
            for value in [title, *(alternative_titles or [])]
            if str(value or "").strip()
        ))
        if not titles:
            return []
        expected_year = extract_year(year)
        allowed_types = tuple(dict.fromkeys(
            str(value).strip().casefold()
            for value in (resource_type_order or ())
            if str(value).strip().casefold() in SUPPORTED_RESOURCE_TYPES
        )) or tuple(SUPPORTED_RESOURCE_TYPES)
        order_map = {value: index for index, value in enumerate(allowed_types)}

        matched_cards: List[Dict[str, str]] = []
        seen_cards = set()
        with self._lock:
            for keyword in titles:
                cache_key = keyword.casefold()
                cards = self._search_cache.get(cache_key)
                if cards is None:
                    cards = self._client.search_media(keyword)
                    self._search_cache[cache_key] = cards
                for card in cards:
                    card_key = (card.get("dir"), card.get("id"))
                    if card_key in seen_cards:
                        continue
                    if self._card_matches(card, titles, expected_year, media_type):
                        seen_cards.add(card_key)
                        matched_cards.append(card)
                if len(matched_cards) >= 3:
                    break

            collected: List[Dict[str, Any]] = []
            seen_urls = set()
            for card in matched_cards[:3]:
                detail_key = f"{card['dir']}:{card['id']}"
                payload = self._resource_cache.get(detail_key)
                if payload is None:
                    try:
                        payload = self._client.get_resources(card["dir"], card["id"])
                        self._resource_cache[detail_key] = payload
                    except GuanyingError:
                        raise
                    except Exception as error:
                        logger.debug(f"观影获取 {detail_key} 详情失败：{error}")
                        continue

                detail_url = f"{self._client.base_url}/{card['dir']}/{card['id']}"
                for item in parse_panlist(payload):
                    raw_url = str(item.get("url") or "").strip()
                    resource_type = (
                        resource_type_from_url(raw_url)
                        or resource_type_from_text(item.get("platform") or "")
                    )
                    if resource_type not in order_map or raw_url in seen_urls:
                        continue
                    resource_title = str(item.get("title") or card.get("title") or "").strip()
                    resource_season = extract_season(resource_title)
                    if media_type == "tv" and season is not None and resource_season is not None and resource_season != season:
                        continue
                    final_url = append_share_password(
                        resource_type, raw_url, item.get("password") or ""
                    )
                    resource_id = f"guanying:{detail_key}:pan:{item['id']}"
                    record = {
                        "resource_id": resource_id,
                        "title": resource_title,
                        "url": final_url,
                        "resource_type": resource_type,
                        "size": parse_size_str(resource_title),
                        "source": "guanying",
                        "source_url": detail_url,
                        "identity_verified": True,
                        "target_season": season,
                        "uploader": item.get("uploader") or "",
                        "update_time": item.get("update_time") or "",
                        "description": " · ".join(filter(None, (
                            card.get("title"), item.get("platform"), item.get("uploader")
                        ))),
                    }
                    self._resolved[resource_id] = record
                    seen_urls.add(raw_url)
                    collected.append(record)

                if "magnet" in order_map:
                    for item in parse_magnets(payload):
                        raw_url = item["url"]
                        if raw_url in seen_urls:
                            continue
                        resource_title = str(item.get("title") or card.get("title") or "").strip()
                        resource_season = extract_season(resource_title)
                        if media_type == "tv" and season is not None and resource_season is not None and resource_season != season:
                            continue
                        resource_id = f"guanying:{detail_key}:magnet:{item['id']}"
                        record = {
                            "resource_id": resource_id,
                            "title": resource_title,
                            "url": raw_url,
                            "resource_type": "magnet",
                            "size": parse_size_str(item.get("size")),
                            "source": "guanying",
                            "source_url": detail_url,
                            "identity_verified": True,
                            "target_season": season,
                            "update_time": item.get("update_time") or "",
                            "description": f"{card.get('title') or ''} · 做种 {item.get('seeds') or 0}",
                        }
                        self._resolved[resource_id] = record
                        seen_urls.add(raw_url)
                        collected.append(record)

            collected.sort(key=lambda item: (
                order_map.get(item["resource_type"], 999),
                -int(item.get("size") or 0),
            ))
            return collected[:max(1, min(int(limit or 10), 80))]

    def resolve_resource(self, resource_id: str) -> Dict[str, Any]:
        record = self._resolved.get(str(resource_id or ""))
        if not record:
            raise GuanyingError("未找到指定的观影资源", "guanying_resource_not_found")
        return dict(record)

    def clear_cache(self) -> Dict[str, int]:
        count = len(self._search_cache) + len(self._resource_cache) + len(self._resolved)
        self._search_cache.clear()
        self._resource_cache.clear()
        self._resolved.clear()
        return {"resources": count}
