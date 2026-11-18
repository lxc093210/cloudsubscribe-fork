"""观影页面与资源接口的纯数据解析函数。"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup


_DETAIL_PATH_RE = re.compile(r"^/(mv|tv|ac)/([A-Za-z0-9_-]+)$", re.I)
_INFO_HASH_RE = re.compile(r"^(?:[A-Fa-f0-9]{40}|[A-Z2-7a-z]{32})$")


def parse_search_results(html: str) -> List[Dict[str, str]]:
    """从搜索页提取影视详情入口并按详情地址去重。"""
    soup = BeautifulSoup(str(html or ""), "html.parser")
    results: List[Dict[str, str]] = []
    seen = set()
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        try:
            path = urlparse(href).path
        except ValueError:
            continue
        matched = _DETAIL_PATH_RE.match(path)
        if not matched:
            continue
        media_dir, media_id = matched.groups()
        key = (media_dir.casefold(), media_id)
        if key in seen:
            continue
        title = str(anchor.get("title") or anchor.get_text(" ", strip=True) or "").strip()
        if not title:
            continue
        seen.add(key)
        results.append({
            "dir": media_dir.casefold(),
            "id": media_id,
            "title": title,
            "path": path,
        })
    return results


def _at(values: Any, index: int, default: Any = "") -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else default


def parse_panlist(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将接口的并行数组形式网盘列表转换为记录列表。"""
    panlist = (payload or {}).get("panlist")
    if not isinstance(panlist, dict):
        return []
    names = panlist.get("name") if isinstance(panlist.get("name"), list) else []
    urls = panlist.get("url") if isinstance(panlist.get("url"), list) else []
    ids = panlist.get("id") if isinstance(panlist.get("id"), list) else []
    types = panlist.get("type") if isinstance(panlist.get("type"), list) else []
    type_names = panlist.get("tname") if isinstance(panlist.get("tname"), list) else []
    count = max(len(names), len(urls), len(ids), len(types))
    rows: List[Dict[str, Any]] = []
    seen = set()
    for index in range(count):
        url = str(_at(urls, index) or "").strip()
        if not url or url.casefold().startswith("javascript:"):
            continue
        if str(_at(panlist.get("gid"), index, "")) == "6":
            continue
        if url in seen:
            continue
        seen.add(url)
        raw_type = _at(types, index, "")
        try:
            platform = str(_at(type_names, int(raw_type), "") or "").strip()
        except (TypeError, ValueError):
            platform = str(raw_type or "").strip()
        rows.append({
            "id": str(_at(ids, index, index) or index),
            "title": str(_at(names, index) or "").strip(),
            "url": url,
            "password": str(_at(panlist.get("p"), index) or "").strip(),
            "platform": platform,
            "uploader": str(_at(panlist.get("user"), index) or "").strip(),
            "update_time": str(_at(panlist.get("time"), index) or "").strip(),
        })
    return rows


def parse_magnets(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """提取接口中未加密的磁力资源；加密条目保持跳过。"""
    downlist = (payload or {}).get("downlist")
    if not isinstance(downlist, dict):
        return []
    listing = downlist.get("list")
    if not isinstance(listing, dict):
        return []
    hashes = listing.get("m") if isinstance(listing.get("m"), list) else []
    titles = listing.get("t") if isinstance(listing.get("t"), list) else []
    kinds = listing.get("k") if isinstance(listing.get("k"), list) else []
    rows: List[Dict[str, Any]] = []
    seen = set()
    for index, info_hash in enumerate(hashes):
        clean_hash = str(info_hash or "").strip()
        try:
            encrypted = int(_at(kinds, index, 1) or 0) != 0
        except (TypeError, ValueError):
            encrypted = True
        if encrypted or not _INFO_HASH_RE.match(clean_hash) or clean_hash.casefold() in seen:
            continue
        seen.add(clean_hash.casefold())
        rows.append({
            "id": str(_at(listing.get("u"), index, index) or index),
            "title": str(_at(titles, index) or "").strip(),
            "url": f"magnet:?xt=urn:btih:{clean_hash}",
            "size": str(_at(listing.get("s"), index) or "").strip(),
            "seeds": _at(listing.get("e"), index, 0),
            "update_time": str(_at(listing.get("n"), index) or "").strip(),
        })
    return rows
