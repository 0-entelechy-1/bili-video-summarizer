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
    model: str = "deepseek-v4-flash"


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
    sub_langs: str = "zh-CN,zh-Hans,zh-TW,ai-zh"  # yt-dlp 字幕语言列表（中文人工优先，AI 兜底）
    cookies_file: Optional[str] = None  # 浏览器导出的 cookies.txt 路径（优先级高于 QR 登录 cookies）
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)


@dataclass
class CleanupConfig:
    auto_delete_video: bool = True
    auto_delete_audio: bool = True


@dataclass
class DownloadConfig:
    quality: str = "1080p"


@dataclass
class ScreenshotConfig:
    count: int = 10
    quality: int = 2


@dataclass
class BilibiliConfig:
    cookie: str = ""


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    transcriber: TranscriberConfig = field(default_factory=TranscriberConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    screenshot: ScreenshotConfig = field(default_factory=ScreenshotConfig)
    bilibili: BilibiliConfig = field(default_factory=BilibiliConfig)
    # 运行时参数（不由配置文件设置）
    output_dir: str = ""
    video_url: str = ""
    keep_video: bool = False
    page: Optional[str] = None


def _find_config_file() -> Optional[Path]:
    """返回项目根目录下的配置文件路径"""
    path = Path(__file__).parent.parent.parent / "config.yaml"
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
    if os.getenv("BILIBILI_COOKIE"):
        config.bilibili.cookie = os.environ["BILIBILI_COOKIE"]
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
        config.transcriber.sub_langs = trans_data.get("sub_langs", config.transcriber.sub_langs)
        config.transcriber.cookies_file = trans_data.get("cookies_file", config.transcriber.cookies_file)
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
        config.cleanup.auto_delete_audio = cleanup_data.get("auto_delete_audio", config.cleanup.auto_delete_audio)

    # 下载配置
    download_data = data.get("download", {})
    if download_data:
        config.download.quality = download_data.get("quality", config.download.quality)

    # 截图配置
    screenshot_data = data.get("screenshot", {})
    if screenshot_data:
        config.screenshot.count = screenshot_data.get("count", config.screenshot.count)
        config.screenshot.quality = screenshot_data.get("quality", config.screenshot.quality)

    bilibili_data = data.get("bilibili", {})
    if bilibili_data:
        config.bilibili.cookie = bilibili_data.get("cookie", config.bilibili.cookie)

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
        print(f"加载配置文件: {yaml_path.resolve()}")
        data = _load_yaml_config(yaml_path)
        config = _dict_to_config(data)
    else:
        print("警告: 未找到配置文件，使用默认配置")
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
    else:
        # 未指定时，固定使用项目根目录下的 outputs 文件夹
        from pathlib import Path
        config.output_dir = str(Path(__file__).resolve().parent.parent.parent / "outputs")
    if kwargs.get("video_url"):
        config.video_url = kwargs["video_url"]
    if kwargs.get("llm_provider"):
        config.llm.provider = kwargs["llm_provider"]
    if kwargs.get("keep_video"):
        config.keep_video = True
    if kwargs.get("quality"):
        config.download.quality = kwargs["quality"]
    if kwargs.get("page") is not None:
        config.page = kwargs["page"]
    if kwargs.get("cookie"):
        config.bilibili.cookie = kwargs["cookie"]
    if kwargs.get("whisper_model"):
        config.transcriber.whisper.model = kwargs["whisper_model"]
    return config
