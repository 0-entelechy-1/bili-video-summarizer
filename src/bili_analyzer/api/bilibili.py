"""B站 API 接口 - 视频信息获取"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("bili_analyzer")


@dataclass
class VideoInfo:
    """视频信息"""
    bvid: str
    aid: int
    title: str
    owner: str
    duration: int  # 秒
    cid: int
    desc: str = ""


@dataclass
class PageInfo:
    """分P信息"""
    cid: int
    title: str
    duration: int  # 秒
    page: int  # 分P序号


# 请求头
def _request_with_retry(session, url, params=None, max_retries=3, timeout=15):
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code >= 500:
                if attempt < max_retries - 1:
                    import time as _time
                    _time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"API 请求失败: HTTP {resp.status_code}")
            return resp
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                import time as _time
                _time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"API 请求超时: {url}")
        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                import time as _time
                _time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"API 连接错误: {url}")


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

# Cookie 存储
_cookies: Optional[Dict] = None


def set_cookies(cookies: Dict[str, str]) -> None:
    """设置 B站 Cookie（用于需要登录的 API）"""
    global _cookies
    _cookies = cookies


def _get_session() -> requests.Session:
    """创建带 Cookie 的请求会话"""
    session = requests.Session()
    session.headers.update(_HEADERS)
    if _cookies:
        session.cookies.update(_cookies)
    return session


def extract_bvid(url_or_bvid: str) -> str:
    """从 URL 或 BV 号中提取 BV 号

    Args:
        url_or_bvid: B站视频链接或 BV 号

    Returns:
        str: BV 号

    Raises:
        ValueError: 无法提取 BV 号
    """
    url_or_bvid = url_or_bvid.strip()

    # 直接是 BV 号
    if re.match(r"^BV[a-zA-Z0-9]+$", url_or_bvid):
        return url_or_bvid

    # 从 URL 中提取
    patterns = [
        r"bilibili\.com/video/(BV[a-zA-Z0-9]+)",
        r"b23\.tv/(BV[a-zA-Z0-9]+)",
        r"/(BV[a-zA-Z0-9]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_bvid)
        if match:
            return match.group(1)

    raise ValueError(f"无法从输入中提取 BV 号: {url_or_bvid}")


def get_video_info(bvid: str) -> VideoInfo:
    """获取视频信息

    Args:
        bvid: BV 号

    Returns:
        VideoInfo: 视频信息

    Raises:
        RuntimeError: API 调用失败
    """
    session = _get_session()
    resp = _request_with_retry(session, "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})

    data = resp.json()
    if data["code"] != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message', '未知错误')}")

    info = data["data"]
    return VideoInfo(
        bvid=info["bvid"],
        aid=info["aid"],
        title=info["title"],
        owner=info["owner"]["name"],
        duration=info["duration"],
        cid=info["cid"],
        desc=info.get("desc", ""),
    )


def get_pages(bvid: str) -> List[PageInfo]:
    """获取视频分P信息列表

    Args:
        bvid: BV 号

    Returns:
        List[PageInfo]: 分P信息列表

    Raises:
        RuntimeError: API 调用失败
    """
    session = _get_session()
    resp = _request_with_retry(session, "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})

    data = resp.json()
    if data["code"] != 0:
        raise RuntimeError(f"获取视频分P信息失败: {data.get('message', '未知错误')}")

    pages = data["data"].get("pages", [])
    result = []
    for p in pages:
        result.append(PageInfo(
            cid=p.get("cid", 0),
            title=p.get("part", ""),
            duration=p.get("duration", 0),
            page=p.get("page", 0),
        ))
    return result
