"""配置管理模块

支持 YAML 配置文件 + 环境变量 + 命令行参数，优先级：
命令行 > 环境变量 > 配置文件 > 默认值
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ZhipuConfig:
    api_key: str = ""
    model: str = "glm-4.7-flash"


@dataclass
class DeepseekConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"


@dataclass
class LLMConfig:
    provider: str = "zhipu"  # zhipu / deepseek / interactive
    zhipu: ZhipuConfig = field(default_factory=ZhipuConfig)
    deepseek: DeepseekConfig = field(default_factory=DeepseekConfig)


@dataclass
class WhisperConfig:
    model: str = "medium"
    model_path: str = "./model"


@dataclass
class VolcengineConfig:
    token: str = ""
    appid: str = ""


@dataclass
class TranscriberConfig:
    prefer: str = "auto"  # auto / whisper / volcengine
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)


@dataclass
class CleanupConfig:
    auto_delete_video: bool = True


@dataclass
class DownloadConfig:
    quality: str = "1080p"


@dataclass
class ScreenshotConfig:
    count: int = 10
    quality: int = 2


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    transcriber: TranscriberConfig = field(default_factory=TranscriberConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    screenshot: ScreenshotConfig = field(default_factory=ScreenshotConfig)
    # 运行时参数（不由配置文件设置）
    output_dir: str = "./outputs"
    video_url: str = ""
    keep_video: bool = False


def _find_config_file() -> Optional[Path]:
    """搜索配置文件，优先级：当前目录 > 项目根目录 > 包目录"""
    search_paths = [
        Path.cwd() / "config.yaml",
        Path.cwd() / "bili_analyzer" / "config.yaml",
        Path(__file__).parent.parent.parent / "config.yaml",
    ]
    for path in search_paths:
        if path.exists():
            return path
    return None


def _load_yaml_config(path: Path) -> dict:
    """加载 YAML 配置文件"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    """用环境变量覆盖配置"""
    # 智谱
    if os.getenv("ZHIPU_API_KEY"):
        config.llm.zhipu.api_key = os.environ["ZHIPU_API_KEY"]
    # DeepSeek
    if os.getenv("DEEPSEEK_API_KEY"):
        config.llm.deepseek.api_key = os.environ["DEEPSEEK_API_KEY"]
    if os.getenv("DEEPSEEK_BASE_URL"):
        config.llm.deepseek.base_url = os.environ["DEEPSEEK_BASE_URL"]
    if os.getenv("DEEPSEEK_MODEL"):
        config.llm.deepseek.model = os.environ["DEEPSEEK_MODEL"]
    # 火山引擎
    if os.getenv("BYTEDANCE_VC_TOKEN"):
        config.transcriber.volcengine.token = os.environ["BYTEDANCE_VC_TOKEN"]
    if os.getenv("BYTEDANCE_VC_APPID"):
        config.transcriber.volcengine.appid = os.environ["BYTEDANCE_VC_APPID"]
    return config


def _dict_to_config(data: dict) -> AppConfig:
    """将字典转换为 AppConfig"""
    config = AppConfig()

    # LLM 配置
    llm_data = data.get("llm", {})
    if llm_data:
        config.llm.provider = llm_data.get("provider", config.llm.provider)
        zhipu_data = llm_data.get("zhipu", {})
        if zhipu_data:
            config.llm.zhipu.api_key = zhipu_data.get("api_key", config.llm.zhipu.api_key)
            config.llm.zhipu.model = zhipu_data.get("model", config.llm.zhipu.model)
        deepseek_data = llm_data.get("deepseek", {})
        if deepseek_data:
            config.llm.deepseek.api_key = deepseek_data.get("api_key", config.llm.deepseek.api_key)
            config.llm.deepseek.base_url = deepseek_data.get("base_url", config.llm.deepseek.base_url)
            config.llm.deepseek.model = deepseek_data.get("model", config.llm.deepseek.model)

    # 转录配置
    trans_data = data.get("transcriber", {})
    if trans_data:
        config.transcriber.prefer = trans_data.get("prefer", config.transcriber.prefer)
        whisper_data = trans_data.get("whisper", {})
        if whisper_data:
            config.transcriber.whisper.model = whisper_data.get("model", config.transcriber.whisper.model)
            config.transcriber.whisper.model_path = whisper_data.get("model_path", config.transcriber.whisper.model_path)
        volc_data = trans_data.get("volcengine", {})
        if volc_data:
            config.transcriber.volcengine.token = volc_data.get("token", config.transcriber.volcengine.token)
            config.transcriber.volcengine.appid = volc_data.get("appid", config.transcriber.volcengine.appid)

    # 清理配置
    cleanup_data = data.get("cleanup", {})
    if cleanup_data:
        config.cleanup.auto_delete_video = cleanup_data.get("auto_delete_video", config.cleanup.auto_delete_video)

    # 下载配置
    download_data = data.get("download", {})
    if download_data:
        config.download.quality = download_data.get("quality", config.download.quality)

    # 截图配置
    screenshot_data = data.get("screenshot", {})
    if screenshot_data:
        config.screenshot.count = screenshot_data.get("count", config.screenshot.count)
        config.screenshot.quality = screenshot_data.get("quality", config.screenshot.quality)

    return config


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """加载配置，合并 YAML + 环境变量

    Args:
        config_path: 指定配置文件路径，None 则自动搜索

    Returns:
        AppConfig: 合并后的配置
    """
    # 1. 加载 YAML 配置
    if config_path:
        yaml_path = Path(config_path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {yaml_path}")
    else:
        yaml_path = _find_config_file()

    if yaml_path:
        data = _load_yaml_config(yaml_path)
        config = _dict_to_config(data)
    else:
        config = AppConfig()

    # 2. 环境变量覆盖
    config = _apply_env_overrides(config)

    return config


def apply_cli_overrides(config: AppConfig, **kwargs) -> AppConfig:
    """用命令行参数覆盖配置

    仅覆盖非 None 的参数
    """
    if kwargs.get("output_dir"):
        config.output_dir = kwargs["output_dir"]
    if kwargs.get("video_url"):
        config.video_url = kwargs["video_url"]
    if kwargs.get("llm_provider"):
        config.llm.provider = kwargs["llm_provider"]
    if kwargs.get("keep_video"):
        config.keep_video = True
    return config
