"""B站 API 接口 - 视频信息获取与CC字幕获取"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

from bili_analyzer.api.wbi import sign_params


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
    resp = session.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        timeout=15,
    )

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


def get_subtitle_metas(aid: int, cid: int) -> List[SubtitleMeta]:
    """获取视频的 CC 字幕元数据列表

    Args:
        aid: av 号
        cid: cid

    Returns:
        List[SubtitleMeta]: 字幕元数据列表，无字幕时返回空列表
    """
    session = _get_session()

    # 需要 Wbi 签名
    params = sign_params({"aid": str(aid), "cid": str(cid)})

    resp = session.get(
        "https://api.bilibili.com/x/player/wbi/v2",
        params=params,
        timeout=15,
    )

    data = resp.json()
    if data["code"] != 0:
        # Wbi 签名失败时尝试不带签名
        resp = session.get(
            "https://api.bilibili.com/x/player/wbi/v2",
            params={"aid": aid, "cid": cid},
            timeout=15,
        )
        data = resp.json()
        if data["code"] != 0:
            return []

    subtitles = data.get("data", {}).get("subtitle", {}).get("subtitles", [])

    result = []
    for sub in subtitles:
        url = sub.get("subtitle_url", "")
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


def get_subtitle_content(meta: SubtitleMeta) -> List[SubtitleLine]:
    """获取字幕内容

    Args:
        meta: 字幕元数据

    Returns:
        List[SubtitleLine]: 字幕行列表
    """
    resp = requests.get(meta.url, headers=_HEADERS, timeout=15)
    data = resp.json()

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


def fetch_cc_subtitle(bvid: str, prefer_human: bool = True) -> Optional[str]:
    """获取 B站视频的 CC 字幕（便捷方法）

    优先获取人工字幕，无 CC 字幕时返回 None。

    Args:
        bvid: BV 号
        prefer_human: 是否优先选择人工字幕

    Returns:
        Optional[str]: SRT 格式字幕文本，无字幕时返回 None
    """
    # 获取视频信息（需要 cid）
    video_info = get_video_info(bvid)

    # 获取字幕元数据
    metas = get_subtitle_metas(video_info.aid, video_info.cid)

    if not metas:
        return None

    # 选择字幕：优先人工字幕
    selected = None
    if prefer_human:
        selected = next((m for m in metas if not m.is_ai), None)
    if selected is None:
        selected = metas[0]

    # 获取字幕内容
    lines = get_subtitle_content(selected)

    if not lines:
        return None

    return subtitle_to_srt(lines)
