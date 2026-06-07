"""转录器工厂

按优先级选择转录方式：CC 字幕 → 配置指定 → 降级
"""

from pathlib import Path
from typing import Dict, Optional

from bili_analyzer.config import AppConfig
from bili_analyzer.transcriber.base import BaseTranscriber
from bili_analyzer.transcriber.cc_subtitle import CCSubtitleTranscriber


def create_transcriber(config: AppConfig, bvid: str, prefer_language: str = "zh") -> BaseTranscriber:
    prefer = config.transcriber.prefer

    if prefer == "whisper":
        from bili_analyzer.transcriber.whisper_local import WhisperTranscriber
        return WhisperTranscriber(
            model=config.transcriber.whisper.model,
            model_path=config.transcriber.whisper.model_path,
        )

    if prefer == "volcengine":
        from bili_analyzer.transcriber.volcengine import VolcengineTranscriber
        return VolcengineTranscriber(
            token=config.transcriber.volcengine.token,
            appid=config.transcriber.volcengine.appid,
        )

    if prefer == "auto":
        return CCSubtitleTranscriber(bvid=bvid, prefer_language=prefer_language)

    return CCSubtitleTranscriber(bvid=bvid, prefer_language=prefer_language)


def get_transcriber_chain(
    config: AppConfig,
    bvid: str,
    cid: Optional[int] = None,
    aid: Optional[int] = None,
    cookies: Optional[Dict[str, str]] = None,
    duration: Optional[int] = None,
    skip_cc: bool = False,
) -> list:
    chain = []

    prefer = config.transcriber.prefer

    # CC 字幕不需要额外配置，作为保底选项加入链中
    # 如果调用方已经检测过 CC 字幕且确认没有，可设置 skip_cc=True 避免重复请求
    if not skip_cc:
        chain.append(CCSubtitleTranscriber(
            bvid=bvid,
            prefer_language="zh",
            cid=cid,
            aid=aid,
            cookies=cookies,
            duration=duration,
        ))

    if prefer in ("auto", "volcengine"):
        if config.transcriber.volcengine.token and config.transcriber.volcengine.appid:
            from bili_analyzer.transcriber.volcengine import VolcengineTranscriber
            chain.append(VolcengineTranscriber(
                token=config.transcriber.volcengine.token,
                appid=config.transcriber.volcengine.appid,
            ))

    if prefer in ("auto", "whisper"):
        try:
            from bili_analyzer.transcriber.whisper_local import WhisperTranscriber
            chain.append(WhisperTranscriber(
                model=config.transcriber.whisper.model,
                model_path=config.transcriber.whisper.model_path,
            ))
        except ImportError:
            pass

    return chain
