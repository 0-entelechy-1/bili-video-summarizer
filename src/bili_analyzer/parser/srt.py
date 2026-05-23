"""SRT 字幕文件解析器

功能:
- 解析 SRT 格式字幕文件
- 提取时间戳和文本内容
- 时间戳格式转换(HH:MM:SS,mmm <-> 秒数)
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class SubtitleSegment:
    """字幕片段"""
    index: int          # 序号
    start_time: float   # 开始时间(秒)
    end_time: float     # 结束时间(秒)
    text: str           # 字幕文本

    def duration(self) -> float:
        """片段时长(秒)"""
        return self.end_time - self.start_time

    def format_time_range(self) -> str:
        """格式化时间范围"""
        return f"{format_timestamp(self.start_time)} --> {format_timestamp(self.end_time)}"


def parse_timestamp(timestamp_str: str) -> float:
    """将 SRT 时间戳转换为秒数

    Args:
        timestamp_str: "HH:MM:SS,mmm" 格式

    Returns:
        float: 秒数
    """
    pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    match = re.match(pattern, timestamp_str.strip())
    if not match:
        raise ValueError(f"无效的时间戳格式: {timestamp_str}")

    hours, minutes, seconds, milliseconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0


def format_timestamp(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳格式

    Args:
        seconds: 秒数

    Returns:
        str: "HH:MM:SS,mmm" 格式
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_srt_file(srt_path: Path) -> List[SubtitleSegment]:
    """解析 SRT 字幕文件

    Args:
        srt_path: SRT 文件路径

    Returns:
        List[SubtitleSegment]: 字幕片段列表
    """
    srt_path = Path(srt_path)
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT 文件不存在: {srt_path}")

    # 读取文件，尝试多种编码
    for encoding in ['utf-8', 'gbk', 'latin-1']:
        try:
            content = srt_path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = srt_path.read_text(encoding='utf-8', errors='replace')

    # 分割字幕块
    blocks = re.split(r'\n\s*\n', content.strip())
    segments = []

    for block in blocks:
        if not block.strip():
            continue

        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue

        try:
            index = int(lines[0].strip())
            time_match = re.match(r'([\d:,]+)\s*-->\s*([\d:,]+)', lines[1].strip())
            if not time_match:
                continue

            start_time = parse_timestamp(time_match.group(1))
            end_time = parse_timestamp(time_match.group(2))
            text = '\n'.join(lines[2:]).strip()

            segments.append(SubtitleSegment(
                index=index,
                start_time=start_time,
                end_time=end_time,
                text=text,
            ))
        except (ValueError, IndexError):
            continue

    return segments


def get_full_transcript(segments: List[SubtitleSegment], include_timestamps: bool = False) -> str:
    """获取完整转录文本

    Args:
        segments: 字幕片段列表
        include_timestamps: 是否包含时间戳

    Returns:
        str: 完整文本
    """
    lines = []
    for seg in segments:
        if include_timestamps:
            lines.append(f"[{format_timestamp(seg.start_time)}] {seg.text}")
        else:
            lines.append(seg.text)
    return '\n'.join(lines)


def get_text_at_time(segments: List[SubtitleSegment], time: float) -> Optional[str]:
    """获取指定时间点的字幕文本"""
    for seg in segments:
        if seg.start_time <= time <= seg.end_time:
            return seg.text
    return None
