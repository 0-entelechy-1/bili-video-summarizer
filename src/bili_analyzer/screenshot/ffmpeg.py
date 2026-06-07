"""FFmpeg 视频截图工具

功能:
- 检查 FFmpeg 是否可用
- 在指定时间戳截取视频画面
- 批量并发截图
"""

import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

from bili_analyzer.ui.console import (
    make_progress,
    print_success,
    print_warning,
)

logger = logging.getLogger("bili_analyzer")


def check_ffmpeg() -> bool:
    """检查 FFmpeg 是否安装且可用

    Returns:
        bool: True 表示可用

    Raises:
        RuntimeError: FFmpeg 不可用
    """
    if not shutil.which('ffmpeg'):
        raise RuntimeError(
            "未找到 FFmpeg!\n\n"
            "请先安装 FFmpeg:\n"
            "  Windows: 从 https://ffmpeg.org/download.html 下载并添加到 PATH\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
        )

    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True, text=True, timeout=5,
            encoding='utf-8', errors='replace',
        )
        if result.returncode == 0:
            print_success("FFmpeg: 已安装")
            return True
        raise RuntimeError("FFmpeg 执行失败")
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg 响应超时")


def capture_screenshot(
    video_path: Path,
    timestamp: float,
    output_path: Path,
    quality: int = 2,
    timeout: int = 15,
    retry: int = 3,
) -> bool:
    """在指定时间戳截取视频画面

    Args:
        video_path: 视频文件路径
        timestamp: 时间戳(秒)
        output_path: 输出图片路径
        quality: JPEG 质量(1-31, 越小越好), 默认2
        timeout: 超时时间(秒)
        retry: 重试次数

    Returns:
        bool: 成功返回 True
    """
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not video_path.exists():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        'ffmpeg', '-ss', str(timestamp),
        '-i', str(video_path),
        '-frames:v', '1',
        '-q:v', str(quality),
        '-y', str(output_path),
    ]

    for attempt in range(retry):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='replace',
            )
            if result.returncode == 0 and output_path.exists():
                return True
        except (subprocess.TimeoutExpired, Exception):
            if attempt == retry - 1:
                return False

    return False


def batch_capture(
    video_path: Path,
    timestamps: List[Dict],
    output_dir: Path,
    quality: int = 2,
    max_workers: int = 4,
    show_progress: bool = True,
) -> Dict[float, Path]:
    """批量截取视频画面

    Args:
        video_path: 视频文件路径
        timestamps: 时间戳列表, 每个元素为字典:
            {"timestamp": 83.5, "description": "关键公式展示"}
        output_dir: 截图输出目录
        quality: JPEG 质量
        max_workers: 最大并发数
        show_progress: 是否显示进度条

    Returns:
        Dict[float, Path]: 时间戳到截图路径的映射
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 准备任务
    tasks = []
    for i, item in enumerate(timestamps):
        timestamp = float(item['timestamp'])
        output_filename = f"screenshot_{i+1:03d}_{int(timestamp)}s.jpg"
        output_path = output_dir / output_filename
        tasks.append({
            'timestamp': timestamp,
            'output_path': output_path,
            'description': item.get('description', ''),
        })

    # 并发执行
    screenshot_mapping = {}
    failed_count = 0

    progress_ctx = make_progress() if show_progress else _NullProgress()
    with progress_ctx as progress:
        if show_progress:
            task_id = progress.add_task(f"🖼  截取关键画面", total=len(tasks))
        else:
            task_id = None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(
                    capture_screenshot, video_path,
                    task['timestamp'], task['output_path'], quality
                ): task
                for task in tasks
            }

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    success = future.result()
                    if success:
                        screenshot_mapping[task['timestamp']] = task['output_path']
                    else:
                        failed_count += 1
                        logger.warning(
                            "截图失败: timestamp=%.2fs, video=%s, output=%s",
                            task['timestamp'], video_path, task['output_path']
                        )
                except Exception as e:
                    failed_count += 1
                    logger.warning(
                        "截图异常: timestamp=%.2fs, video=%s, output=%s, error=%s",
                        task['timestamp'], video_path, task['output_path'], e
                    )

                if task_id is not None:
                    progress.update(task_id, advance=1)

    summary = f"截图完成: 成功 {len(screenshot_mapping)} 张" \
              + (f"，失败 {failed_count} 张" if failed_count > 0 else "")
    if failed_count > 0:
        print_warning(summary)
    else:
        print_success(summary)
    logger.info(summary)

    return screenshot_mapping


class _NullProgress:
    """show_progress=False 时的空 Progress 占位符（with 协议兼容）"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def add_task(self, *args, **kwargs):
        return None

    def update(self, *args, **kwargs):
        pass
