"""yt-dlp 字幕下载转录器

通过 yt-dlp 的 --write-subs --convert-subs srt --skip-download 命令下载 B站字幕，
绕开自定义 CC 字幕 API 调用的不稳定性。
"""

from pathlib import Path
from typing import Optional

from bili_analyzer.downloader.ytdlp import download_subtitle
from bili_analyzer.transcriber.base import BaseTranscriber


class YtdlpSubtitleTranscriber(BaseTranscriber):
    """通过 yt-dlp 下载 B站字幕"""

    def __init__(
        self,
        video_url: str,
        sub_langs: str = "zh-CN,zh-Hans,zh-TW,ai-zh",
        cookies: Optional[dict] = None,
    ):
        """
        Args:
            video_url: 视频 URL（含 ?p=N 分P参数）
            sub_langs: 字幕语言列表，逗号分隔（中文人工优先，AI 兜底）
            cookies: B站 Cookie 字典
        """
        self.video_url = video_url
        self.sub_langs = sub_langs
        self.cookies = cookies

    @property
    def name(self) -> str:
        return "yt-dlp字幕"

    def transcribe(self, video_path: Path, output_dir: Path) -> Path:
        """通过 yt-dlp 下载字幕并保存为 SRT 文件

        Args:
            video_path: 视频文件路径（仅用于取 stem 作为输出文件名）
            output_dir: 输出目录

        Returns:
            Path: SRT 字幕文件路径

        Raises:
            RuntimeError: 无可用字幕
        """
        srt_path = download_subtitle(
            video_url=self.video_url,
            output_dir=output_dir,
            sub_langs=self.sub_langs,
            cookies=self.cookies,
            output_name=video_path.stem,
        )
        if srt_path is None:
            raise RuntimeError("该视频无yt-dlp可下载的字幕")

        print(f"yt-dlp字幕已保存: {srt_path.name}")
        return srt_path
