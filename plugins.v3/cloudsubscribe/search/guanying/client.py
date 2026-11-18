"""观影账号登录、搜索与资源接口客户端。"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from app.log import logger
from bs4 import BeautifulSoup

from .parser import parse_search_results
from ...utils.http_client import (
    RequestGate,
    gated_idempotent_request,
    gated_request,
    normalize_proxies,
    request_error_summary,
    requests,
)


class GuanyingError(RuntimeError):
    """观影登录、验证或搜索异常。"""

    def __init__(self, message: str, code: str = "guanying_error"):
        super().__init__(message)
        self.code = code


class GuanyingClient:
    """维护观影登录会话，并自动完成站点的浏览器 PoW 验证。"""

    BASE_URL = "https://www.xn--wcv59z.com"
    _SESSION_DATA_KEY = "guanying_auth_session"
    _LOGIN_LOCK = threading.RLock()
    _POW_ID_RE = re.compile(r"powChallengeId\s*=\s*['\"]([^'\"]+)", re.I)
    _HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    }

    def __init__(
            self,
            username: str,
            password: str,
            base_url: str = BASE_URL,
            proxy: Any = None,
            request_timeout: int = 60,
            request_interval: float = 1.0,
            get_data_func: Optional[Callable] = None,
            save_data_func: Optional[Callable] = None,
    ):
        self.base_url = str(base_url or self.BASE_URL).rstrip("/")
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self._proxies = normalize_proxies(proxy)
        self._request_timeout = max(5, min(int(request_timeout or 60), 120))
        self._get_data_func = get_data_func
        self._save_data_func = save_data_func
        self._session = requests.Session(impersonate="chrome")
        self._session.headers.update(self._HEADERS)
        self._lock = threading.RLock()
        self._logged_in = False
        self._request_gate = RequestGate.shared(
            "观影",
            f"{self.base_url}|{self.username.casefold()}|{self._proxies}",
            request_interval=max(0.5, float(request_interval or 1.0)),
            minimum_interval=0.5,
        )
        self._restore_session()

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    @property
    def _timeout(self) -> tuple[int, int]:
        return min(15, self._request_timeout), self._request_timeout

    def _restore_session(self) -> None:
        if not self._get_data_func:
            return
        try:
            data = self._get_data_func(self._SESSION_DATA_KEY) or {}
            if not isinstance(data, dict) or str(data.get("username") or "").strip() != self.username:
                return
            for name, value in (data.get("cookies") or {}).items():
                self._session.cookies.set(name, str(value))
            self._logged_in = bool(data.get("logged_in"))
        except Exception as error:
            logger.debug(f"观影恢复本地会话失败：{error}")

    def _save_session(self) -> None:
        if not self._save_data_func:
            return
        try:
            cookies = self._session.cookies.get_dict()
            self._save_data_func(self._SESSION_DATA_KEY, {
                "username": self.username,
                "cookies": cookies,
                "logged_in": self._logged_in,
                "updated_at": time.time(),
            } if cookies else {})
        except Exception as error:
            logger.debug(f"观影持久化会话失败：{error}")

    def _session_request(self, *args, **kwargs):
        if self._proxies:
            kwargs.setdefault("proxies", self._proxies)
        return self._session.request(*args, **kwargs)

    def _raw_request(
            self,
            method: str,
            path: str,
            *,
            params: Optional[Dict[str, Any]] = None,
            headers: Optional[Dict[str, str]] = None,
            data: Optional[Any] = None,
            idempotent: bool = False,
    ):
        url = f"{self.base_url}/{path.lstrip('/')}"
        req_headers = dict(self._HEADERS)
        if headers:
            req_headers.update(headers)
        request_func = gated_idempotent_request if idempotent else gated_request
        try:
            return request_func(
                self._request_gate,
                self._session_request,
                method,
                url,
                params=params,
                headers=req_headers,
                data=data,
                timeout=self._timeout,
            )
        except requests.exceptions.HTTPError as error:
            status = getattr(getattr(error, "response", None), "status_code", 0)
            if status in (401, 403):
                raise GuanyingError(f"观影身份验证失败 (HTTP {status})", "guanying_auth_failed") from error
            raise GuanyingError(f"观影请求失败: {request_error_summary(error)}", "guanying_http_error") from error
        except GuanyingError:
            raise
        except Exception as error:
            raise GuanyingError(f"观影网络异常: {request_error_summary(error)}", "guanying_network_error") from error

    @classmethod
    def _pow_id(cls, text: str) -> str:
        matched = cls._POW_ID_RE.search(str(text or ""))
        return matched.group(1) if matched else ""

    def _ensure_pow(self) -> None:
        response = self._raw_request("GET", "/", idempotent=True)
        challenge_id = self._pow_id(response.text)
        if not challenge_id:
            return
        challenge_response = self._raw_request(
            "GET",
            "/res/pow",
            headers={"X-Pow-Id": challenge_id, "Accept": "application/json"},
            idempotent=True,
        )
        try:
            challenge = challenge_response.json()
            modulus = int(str(challenge.get("N") or ""), 16)
            value = int(str(challenge.get("x") or ""), 16)
            iterations = int(challenge.get("t") or 0)
            submit_id = str(challenge.get("challenge_id") or challenge_id)
        except Exception as error:
            raise GuanyingError("观影 PoW 验证参数解析失败", "guanying_pow_parse_error") from error
        if modulus <= 0 or iterations <= 0 or iterations > 2_000_000:
            raise GuanyingError("观影 PoW 验证参数无效", "guanying_pow_invalid")
        for _ in range(iterations):
            value = (value * value) % modulus
        result = self._raw_request(
            "POST",
            "/res/pow",
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/",
                "Accept": "application/json",
            },
            data={"y": format(value, "x"), "id": submit_id},
        )
        try:
            success = bool(result.json().get("success"))
        except Exception:
            success = False
        if not success:
            raise GuanyingError("观影 PoW 验证失败", "guanying_pow_failed")
        self._save_session()

    @staticmethod
    def _logged_out(response: Any) -> bool:
        url = str(getattr(response, "url", "") or "").casefold()
        text = str(getattr(response, "text", "") or "")
        return "/user/login" in url or "登录后访问受限内容" in text or "<title>未登录" in text

    @staticmethod
    def _authenticated_html(response: Any) -> bool:
        """判断站点是否返回了已经登录的普通网页。"""
        text = str(getattr(response, "text", "") or "")
        return bool(
            re.search(r"_obj\.header\s*=", text, re.I)
            and re.search(r"['\"]u['\"]\s*:\s*\{", text, re.I)
            and "/user/login" not in text.casefold()
        )

    @staticmethod
    def _page_title(response: Any) -> str:
        text = str(getattr(response, "text", "") or "")
        matched = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        return re.sub(r"\s+", " ", matched.group(1)).strip()[:80] if matched else "无标题网页"

    def _confirm_logged_in(self) -> bool:
        """登录接口返回非 JSON 时，通过首页确认会话是否已经生效。"""
        response = self._raw_request("GET", "/", idempotent=True)
        if self._pow_id(response.text):
            return False
        return not self._logged_out(response) and self._authenticated_html(response)

    def _login(self, force: bool = False) -> None:
        if not self.is_configured:
            raise GuanyingError("观影账号或密码未配置", "guanying_not_configured")
        with self._LOGIN_LOCK:
            if self._logged_in and not force:
                return
            last_page_title = ""
            for attempt in range(2):
                self._ensure_pow()
                response = self._raw_request(
                    "POST",
                    "/user/login",
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": f"{self.base_url}/user/login",
                        "Accept": "application/json",
                    },
                    data={
                        "code": "",
                        "siteid": "1",
                        "dosubmit": "1",
                        "cookietime": "10506240",
                        "username": self.username,
                        "password": self.password,
                    },
                )
                try:
                    payload = response.json()
                except Exception:
                    last_page_title = self._page_title(response)
                    if self._authenticated_html(response) or self._confirm_logged_in():
                        break
                    logger.warning(
                        f"观影登录返回非 JSON 网页（{last_page_title}），"
                        f"尝试重新过盾登录 {attempt + 1}/2"
                    )
                    continue
                if not isinstance(payload, dict):
                    raise GuanyingError("观影登录响应格式异常", "guanying_login_parse_error")
                if int(payload.get("code") or 0) == 200:
                    break
                message = str(payload.get("msg") or payload.get("message") or "登录失败")
                if "验证码" in message or "captcha" in message.casefold():
                    raise GuanyingError("观影登录需要验证码，请稍后在网页确认账号状态再测试", "guanying_captcha_required")
                raise GuanyingError(f"观影登录失败: {message}", "guanying_login_failed")
            else:
                raise GuanyingError(
                    f"观影登录连续返回网页（{last_page_title or '未知页面'}），已自动重试",
                    "guanying_login_html_response",
                )
            self._logged_in = True
            self._save_session()
            logger.info("观影账号登录成功")

    def check_login(self, force: bool = False) -> bool:
        if not self.is_configured:
            return False
        with self._lock:
            if force or not self._logged_in:
                self._login(force=True)
                return True
            response = self._raw_request("GET", "/", idempotent=True)
            if self._pow_id(response.text):
                self._logged_in = False
                self._login(force=True)
            elif self._logged_out(response):
                self._logged_in = False
                self._login(force=True)
            return True

    def _authorized_get(self, path: str, params: Optional[Dict[str, Any]] = None):
        self.check_login()
        response = self._raw_request("GET", path, params=params, idempotent=True)
        if self._pow_id(response.text) or self._logged_out(response):
            self._logged_in = False
            self._login(force=True)
            response = self._raw_request("GET", path, params=params, idempotent=True)
        return response

    def get_account_info(self) -> Dict[str, Any]:
        response = self._authorized_get("/")
        soup = BeautifulSoup(response.text, "html.parser")
        account_name = self.username
        for anchor in soup.select('a[href*="/user"], a[href*="/uid/"]'):
            text = anchor.get_text(" ", strip=True)
            if text and text not in {"登录", "注册", "退出"}:
                account_name = text
                break
        return {
            "name": account_name,
            "level": "已登录",
            "points": 0,
            "signin_days": None,
            "details": {"site": self.base_url},
        }

    def search_media(self, keyword: str) -> List[Dict[str, str]]:
        query = str(keyword or "").strip()
        if not query:
            return []
        response = self._authorized_get("/search", params={"q": query, "mode": "2"})
        return parse_search_results(response.text)

    def get_resources(self, media_dir: str, media_id: str) -> Dict[str, Any]:
        if media_dir not in {"mv", "tv", "ac"} or not re.fullmatch(r"[A-Za-z0-9_-]+", str(media_id or "")):
            raise GuanyingError("观影详情参数无效", "guanying_invalid_detail")
        response = self._authorized_get(f"/res/downurl/{media_dir}/{media_id}")
        try:
            payload = response.json()
        except Exception as error:
            raise GuanyingError("观影资源响应解析失败", "guanying_resource_parse_error") from error
        if not isinstance(payload, dict) or int(payload.get("code") or 0) not in (0, 200):
            message = str((payload or {}).get("msg") or "资源接口返回异常")
            raise GuanyingError(f"观影资源获取失败: {message}", "guanying_resource_failed")
        return payload

    def clear_cache(self) -> Dict[str, int]:
        return {"session": 0}

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass
