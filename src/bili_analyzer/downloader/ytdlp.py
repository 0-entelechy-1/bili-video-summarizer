"""yt-dlp 视频下载封装

使用 yt-dlp 下载 B站视频，支持画质选择和进度提示。
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bili_analyzer.downloader")


def check_ytdlp() -> bool:
    if not shutil.which('yt-dlp'):
        raise RuntimeError(
            "未找到 yt-dlp!\n\n"
            "请先安装:\n"
            "  pip install yt-dlp\n"
        )
    return True


def download_video(
    video_url: str,
    output_dir: Path,
    quality: str = "1080p",
) -> Path:
    check_ytdlp()

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if video_url.startswith("BV"):
        video_url = f"https://www.bilibili.com/video/{video_url}/"

    output_template = str(output_dir / "%(title)s.%(ext)s")

    format_map = {
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "best": "bestvideo+bestaudio/best",
    }
    format_str = format_map.get(quality, format_map["1080p"])

    cmd = [
        "yt-dlp",
        "-f", format_str,
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        "--no-warnings",
        video_url,
    ]

    print(f"正在下载视频: {video_url}")
    print(f"画质: {quality}")
    print()
    logger.info(f"下载视频: url={video_url}, 画质={quality}, 输出目录={output_dir}")
    logger.debug(f"yt-dlp 命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )

        video_files = list(output_dir.glob("*.mp4"))
        logger.debug(f"在 {output_dir} 中找到的 mp4 文件: {video_files}")

        if not video_files:
            raise RuntimeError("下载完成但未找到视频文件")

        video_path = max(video_files, key=lambda p: p.stat().st_mtime)
        file_size_mb = video_path.stat().st_size / (1024 * 1024)

        print(f"\n视频已下载: {video_path.name} ({file_size_mb:.1f} MB)")
        logger.info(f"视频下载完成: {video_path} ({file_size_mb:.1f} MB)")
        return video_path

    except subprocess.CalledProcessError as e:
        stderr_msg = (e.stderr or "").strip()[:500]
        logger.error(f"视频下载失败, 退出码: {e.returncode}, stderr: {stderr_msg}")
        raise RuntimeError(f"视频下载失败 (退出码 {e.returncode}): {stderr_msg}") from e


def extract_audio(
    video_path: Path,
    output_path: Optional[Path] = None,
) -> Path:
    video_path = Path(video_path)

    if output_path is None:
        output_path = video_path.parent / f"{video_path.stem}.mp3"

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-q:a", "0",
        "-map", "a",
        "-y", str(output_path),
    ]

    print("正在提取音频...")

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
        print(f"音频已提取: {output_path.name}")
        return output_path
    except subprocess.CalledProcessError as e:
        stderr_msg = (e.stderr or "").strip()[:500]
        logger.error(f"音频提取失败: {stderr_msg}")
        raise RuntimeError(f"音频提取失败: {stderr_msg}") from e
