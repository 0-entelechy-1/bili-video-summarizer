"""转录器工厂

按优先级选择转录方式：yt-dlp 字幕 → 配置指定的语音识别链
"""

from typing import Dict, Optional

from bili_analyzer.config import AppConfig


def create_transcriber(config: AppConfig, bvid: str, prefer_language: str = "zh"):
    """创建单个转录器实例（兼容旧 API）"""
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

    raise ValueError(
        f"不支持的转录方式: {prefer}。"
        "请使用 get_transcriber_chain() 获取转录链，"
        "yt-dlp 字幕下载已由 pipeline.py 单独处理。"
    )


def get_transcriber_chain(
    config: AppConfig,
    bvid: str,
    page_num: int = 1,
    cookies: Optional[Dict[str, str]] = None,
) -> list:
    """构造语音识别转录链（兜底链，不含 yt-dlp 字幕节点）

    yt-dlp 字幕下载由 pipeline.py 在调用本链之前单独尝试，
    本链只用于 yt-dlp 失败后的语音识别兜底。

    Args:
        config: 应用配置
        bvid: BV 号（保留参数以便未来扩展）
        page_num: 分P序号（保留参数以便未来扩展）
        cookies: B站 Cookie 字典（保留参数以便未来扩展）

    Returns:
        list: 转录器实例列表，按优先级排序
    """
    chain = []
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
