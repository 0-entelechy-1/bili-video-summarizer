"""转录器基类"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseTranscriber(ABC):
    """转录器基类，定义统一接口"""

    @abstractmethod
    def transcribe(self, video_path: Path, output_dir: Path) -> Path:
        """转录视频生成 SRT 字幕文件

        Args:
            video_path: 视频文件路径
            output_dir: 输出目录

        Returns:
            Path: SRT 字幕文件路径
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """转录器名称"""
        ...
