"""B站 CC 字幕获取

优先获取人工字幕，无 CC 字幕时返回 None。
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from bili_analyzer.api.bilibili import fetch_cc_subtitle, get_video_info
from bili_analyzer.transcriber.base import BaseTranscriber

logger = logging.getLogger("bili_analyzer")


class CCSubtitleTranscriber(BaseTranscriber):
    """B站 CC 字幕获取器"""

    def __init__(
        self,
        bvid: str,
        prefer_human: bool = True,
        prefer_language: str = "zh",
        cid: Optional[int] = None,
        cookies: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            bvid: BV 号
            prefer_human: 是否优先选择人工字幕
            prefer_language: 优先语言
            cid: 分P ID
            cookies: B站 Cookie 字典
        """
        self.bvid = bvid
        self.prefer_human = prefer_human
        self.prefer_language = prefer_language
        self.cid = cid
        self.cookies = cookies
        self._cached_srt: Optional[str] = None
        self._cached_cid: Optional[int] = None

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
        if self._cached_srt is not None and self._cached_cid == self.cid:
            srt_content = self._cached_srt
        else:
            srt_content = fetch_cc_subtitle(
                self.bvid,
                prefer_human=self.prefer_human,
                prefer_language=self.prefer_language,
                cid=self.cid,
                cookies=self.cookies,
            )
            if srt_content is not None:
                self._cached_srt = srt_content
                self._cached_cid = self.cid

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
        if self._cached_srt is not None and self._cached_cid == self.cid:
            return True

        try:
            srt_content = fetch_cc_subtitle(
                self.bvid,
                prefer_human=self.prefer_human,
                prefer_language=self.prefer_language,
                cid=self.cid,
                cookies=self.cookies,
            )
        except RuntimeError as e:
            error_msg = str(e)
            if "无CC字幕" in error_msg:
                return False
            if "获取" in error_msg and "失败" in error_msg:
                logger.error(f"CC字幕 API 错误: {e}")
                return False
            logger.warning(f"获取CC字幕失败: {e}")
            return False
        except Exception as e:
            import requests.exceptions
            if isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                logger.warning(f"CC字幕网络错误: {e}")
            elif isinstance(e, (json.JSONDecodeError,)):
                logger.warning(f"CC字幕 JSON 解析失败，视为无字幕: {e}")
            else:
                logger.warning(f"获取CC字幕失败: {e}")
            return False

        if srt_content is not None:
            self._cached_srt = srt_content
            self._cached_cid = self.cid
            return True
        return False
