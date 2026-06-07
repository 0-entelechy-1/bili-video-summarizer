"""配置相关 API 路由"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bili_analyzer.config import load_config, AppConfig

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigResponse(BaseModel):
    llm_provider: str
    zhipu_api_key: str
    zhipu_model: str
    deepseek_api_key: str
    deepseek_model: str
    transcriber_prefer: str
    whisper_model: str
    volcengine_token: str
    volcengine_appid: str
    auto_delete_video: bool
    auto_delete_audio: bool
    quality: str
    screenshot_count: int
    screenshot_quality: int
    bilibili_cookie: str


@router.get("", response_model=ConfigResponse)
def get_config():
    """获取当前配置"""
    config = load_config()
    return ConfigResponse(
        llm_provider=config.llm.provider,
        zhipu_api_key=config.llm.zhipu.api_key,
        zhipu_model=config.llm.zhipu.model,
        deepseek_api_key=config.llm.deepseek.api_key,
        deepseek_model=config.llm.deepseek.model,
        transcriber_prefer=config.transcriber.prefer,
        whisper_model=config.transcriber.whisper.model,
        volcengine_token=config.transcriber.volcengine.token,
        volcengine_appid=config.transcriber.volcengine.appid,
        auto_delete_video=config.cleanup.auto_delete_video,
        auto_delete_audio=config.cleanup.auto_delete_audio,
        quality=config.download.quality,
        screenshot_count=config.screenshot.count,
        screenshot_quality=config.screenshot.quality,
        bilibili_cookie=config.bilibili.cookie,
    )
