"""B站 CC 字幕获取

优先获取人工字幕，无 CC 字幕时返回 None。
"""

from pathlib import Path
from typing import Optional

from bili_analyzer.api.bilibili import fetch_cc_subtitle, get_video_info
from bili_analyzer.transcriber.base import BaseTranscriber


class CCSubtitleTranscriber(BaseTranscriber):
    """B站 CC 字幕获取器"""

    def __init__(self, bvid: str, prefer_human: bool = True):
        """
        Args:
            bvid: BV 号
            prefer_human: 是否优先选择人工字幕
        """
        self.bvid = bvid
        self.prefer_human = prefer_human

    @property
    def name(self) -> str:
        return "CC字幕"

    def transcribe(self, video_path: Path, output_dir: Path) -> Path:
        """获取 CC 字幕并保存为 SRT 文件

        Args:
            video_path: 视频文件路径（未使用，CC 字幕不需要视频文件）
            output_dir: 输出目录

        Returns:
            Path: SRT 字幕文件路径

        Raises:
            RuntimeError: 无 CC 字幕
        """
        srt_content = fetch_cc_subtitle(self.bvid, prefer_human=self.prefer_human)

        if srt_content is None:
            raise RuntimeError("该视频无CC字幕")

        # 保存 SRT 文件
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        srt_path = output_dir / f"{video_path.stem}.srt"
        srt_path.write_text(srt_content, encoding='utf-8')

        print(f"CC字幕已保存: {srt_path.name}")
        return srt_path

    def has_subtitle(self) -> bool:
        """检查视频是否有 CC 字幕

        Returns:
            bool: 有字幕返回 True
        """
        try:
            result = fetch_cc_subtitle(self.bvid, prefer_human=self.prefer_human)
            return result is not None
        except Exception:
            return False
