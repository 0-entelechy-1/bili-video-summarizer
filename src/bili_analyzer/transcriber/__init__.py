"""转录器工厂

按优先级选择转录方式：CC 字幕 → 配置指定 → 降级
"""

from pathlib import Path
from typing import Optional

from bili_analyzer.config import AppConfig
from bili_analyzer.transcriber.base import BaseTranscriber
from bili_analyzer.transcriber.cc_subtitle import CCSubtitleTranscriber


def create_transcriber(config: AppConfig, bvid: str) -> BaseTranscriber:
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
        return CCSubtitleTranscriber(bvid=bvid)

    return CCSubtitleTranscriber(bvid=bvid)


def get_transcriber_chain(config: AppConfig, bvid: str) -> list:
    chain = []

    cc = CCSubtitleTranscriber(bvid=bvid)
    chain.append(cc)

    prefer = config.transcriber.prefer

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
