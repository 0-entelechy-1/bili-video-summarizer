"""B站 API 接口 - 视频信息获取与CC字幕获取"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

from bili_analyzer.api.wbi import sign_params

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


@dataclass
class SubtitleMeta:
    """字幕元数据"""
    id: int
    language: str  # 如 "zh-CN"
    language_doc: str  # 如 "中文（中国）"
    url: str  # 字幕内容 URL
    is_ai: bool  # 是否为 AI 生成


@dataclass
class SubtitleLine:
    """字幕行"""
    start: float  # 开始时间（秒）
    end: float  # 结束时间（秒）
    content: str  # 字幕文本


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


def get_subtitle_metas(aid: int, cid: int) -> List[SubtitleMeta]:
    """获取视频的 CC 字幕元数据列表

    使用旧接口 /x/player/v2 绕过 WBI 签名风控。
    需要先访问B站首页获取 buvid3 等浏览器指纹 cookie。

    Args:
        aid: av 号
        cid: cid

    Returns:
        List[SubtitleMeta]: 字幕元数据列表，无字幕时返回空列表
    """
    session = _get_session()

    # 先访问B站首页获取 buvid3 等浏览器指纹 cookie（关键！）
    try:
        session.get("https://www.bilibili.com", timeout=10)
    except Exception:
        pass

    # 使用旧接口，不需要 WBI 签名
    resp = _request_with_retry(
        session, "https://api.bilibili.com/x/player/v2",
        params={"aid": aid, "cid": cid}
    )

    data = resp.json()
    if data["code"] != 0:
        logger.warning(f"获取字幕元数据失败: code={data.get('code')}, message={data.get('message')}")
        return []

    subtitles = data.get("data", {}).get("subtitle", {}).get("subtitles", [])

    result = []
    for sub in subtitles:
        url = sub.get("subtitle_url", "")
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url

        result.append(SubtitleMeta(
            id=sub.get("id", 0),
            language=sub.get("lan", ""),
            language_doc=sub.get("lan_doc", ""),
            url=url,
            is_ai=sub.get("ai_status", 0) != 0,
        ))

    return result


def get_subtitle_content(meta: SubtitleMeta, cookies: Optional[Dict[str, str]] = None) -> List[SubtitleLine]:
    """获取字幕内容

    Args:
        meta: 字幕元数据
        cookies: B站 Cookie 字典，用于访问需要登录的字幕资源

    Returns:
        List[SubtitleLine]: 字幕行列表
    """
    if not meta.url:
        logger.warning("字幕元数据 URL 为空，跳过获取")
        return []

    session = _get_session()

    # 如果有 Cookie，设置到 session
    if cookies:
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".bilibili.com")
            session.cookies.set(name, value, domain=".hdslb.com")

    resp = session.get(meta.url, timeout=15)

    # 检查响应状态
    if resp.status_code != 200:
        logger.warning(f"字幕内容请求失败: HTTP {resp.status_code}, url={meta.url}")
        return []

    text = resp.text.strip()
    if not text:
        logger.warning(f"字幕内容为空: url={meta.url}")
        return []

    # 清洗 BOM 等不可见前缀字符
    if text.startswith('\ufeff'):
        text = text[1:]

    # 尝试解析 JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"字幕内容 JSON 解析失败: {e}, url={meta.url}, 内容前500字符: {text[:500]!r}")
        return []

    lines = []
    for item in data.get("body", []):
        lines.append(SubtitleLine(
            start=item.get("from", 0.0),
            end=item.get("to", 0.0),
            content=item.get("content", ""),
        ))

    return lines


def subtitle_to_srt(lines: List[SubtitleLine]) -> str:
    """将字幕行列表转换为 SRT 格式文本

    Args:
        lines: 字幕行列表

    Returns:
        str: SRT 格式文本
    """
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    srt_parts = []
    for i, line in enumerate(lines, 1):
        srt_parts.append(str(i))
        srt_parts.append(f"{_format_time(line.start)} --> {_format_time(line.end)}")
        srt_parts.append(line.content)
        srt_parts.append("")  # 空行分隔

    return "\n".join(srt_parts)


def fetch_cc_subtitle(
    bvid: str,
    prefer_human: bool = True,
    prefer_language: str = "zh",
    cid: Optional[int] = None,
    cookies: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """获取 B站视频的 CC 字幕（便捷方法）

    优先获取人工字幕，无 CC 字幕时返回 None。

    Args:
        bvid: BV 号
        prefer_human: 是否优先选择人工字幕
        prefer_language: 优先语言前缀，如 "zh"
        cid: 指定分P的 cid，为 None 时使用视频默认 cid

    Returns:
        Optional[str]: SRT 格式字幕文本，无字幕时返回 None
    """
    # 获取视频信息（需要 aid 和 cid）
    video_info = get_video_info(bvid)
    aid = video_info.aid
    use_cid = cid if cid is not None else video_info.cid

    # 获取字幕元数据
    metas = get_subtitle_metas(aid, use_cid)

    if not metas:
        return None

    # 选择字幕：先按 prefer_human 筛选，再按 prefer_language 前缀匹配
    candidates = metas
    if prefer_human:
        human_metas = [m for m in metas if not m.is_ai]
        if human_metas:
            candidates = human_metas

    selected = next(
        (m for m in candidates if m.language.startswith(prefer_language)),
        None,
    )
    if selected is None:
        selected = candidates[0]

    # 获取字幕内容
    lines = get_subtitle_content(selected, cookies=cookies)

    if not lines:
        return None

    return subtitle_to_srt(lines)
