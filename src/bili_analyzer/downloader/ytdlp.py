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
    # 优先检查 Python 模块，再检查命令行
    try:
        import yt_dlp
        return True
    except ImportError:
        pass
    if not shutil.which('yt-dlp'):
        raise RuntimeError(
            "未找到 yt-dlp!\n\n"
            "请先安装:\n"
            "  pip install yt-dlp\n"
        )
    return True


def _write_cookies_file(cookies: dict, output_dir: Path) -> Path:
    cookies_path = output_dir / ".cookies.txt"
    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in cookies.items():
        lines.append(f".bilibili.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}")
    cookies_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cookies_path


def download_video(
    video_url: str,
    output_dir: Path,
    quality: str = "1080p",
    cookies: Optional[dict] = None,
    output_name: str = "video",
) -> Path:
    check_ytdlp()

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if video_url.startswith("BV"):
        video_url = f"https://www.bilibili.com/video/{video_url}/"

    output_template = str(output_dir / f"{output_name}.%(ext)s")

    format_map = {
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "best": "bestvideo+bestaudio/best",
    }
    format_str = format_map.get(quality, format_map["1080p"])

    cookies_path = None
    if cookies:
        cookies_path = _write_cookies_file(cookies, output_dir)

    # 解析 URL 中的分P参数，确保 yt-dlp 下载正确的分P
    # B站多P视频在 yt-dlp 中被视为播放列表，--no-playlist 会忽略 ?p=N 参数导致总是下载第1P
    import urllib.parse
    parsed = urllib.parse.urlparse(video_url)
    query_params = urllib.parse.parse_qs(parsed.query)
    page_num = query_params.get("p", ["1"])[0]

    cmd = [
        "yt-dlp",
        "-f", format_str,
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--playlist-items", page_num,
        "--no-warnings",
        "--no-cache-dir",
        "--abort-on-unavailable-fragment",
        "--retries", "10",
        "--fragment-retries", "10",
    ]
    if cookies_path:
        cmd.extend(["--cookies", str(cookies_path)])
    cmd.append(video_url)

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

        # 优先选择文件名与 output_name 匹配的视频，避免目录中残留其他视频文件导致选错
        expected_name = f"{output_name}.mp4"
        matched_files = [p for p in video_files if p.name == expected_name]
        if matched_files:
            video_path = matched_files[0]
        else:
            video_path = max(video_files, key=lambda p: p.stat().st_mtime)
        file_size_mb = video_path.stat().st_size / (1024 * 1024)

        print(f"\n视频已下载: {video_path.name} ({file_size_mb:.1f} MB)")
        logger.info(f"视频下载完成: {video_path} ({file_size_mb:.1f} MB)")
        return video_path

    except subprocess.CalledProcessError as e:
        stderr_msg = (e.stderr or "").strip()[:500]
        logger.error(f"视频下载失败, 退出码: {e.returncode}, stderr: {stderr_msg}")
        raise RuntimeError(f"视频下载失败 (退出码 {e.returncode}): {stderr_msg}") from e
    finally:
        if cookies_path and cookies_path.exists():
            try:
                cookies_path.unlink()
            except OSError:
                pass


def download_subtitle(
    video_url: str,
    output_dir: Path,
    sub_langs: str = "zh-CN,zh-Hans,zh-TW,ai-zh",
    cookies: Optional[dict] = None,
    output_name: str = "video",
) -> Optional[Path]:
    """使用 yt-dlp 下载 B站字幕并转换为 SRT

    Args:
        video_url: 视频 URL（含 ?p=N 分P参数）
        output_dir: 字幕输出目录
        sub_langs: 字幕语言列表，逗号分隔（传给 --sub-langs）
        cookies: B站 Cookie 字典
        output_name: 输出文件名前缀（不含扩展名）

    Returns:
        Optional[Path]: 成功下载时返回 SRT 文件路径，无可用字幕返回 None
    """
    check_ytdlp()

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 解析 URL 中的分P参数，确保 yt-dlp 下载正确的分P
    import urllib.parse
    parsed = urllib.parse.urlparse(video_url)
    query_params = urllib.parse.parse_qs(parsed.query)
    page_num = query_params.get("p", ["1"])[0]

    output_template = str(output_dir / f"{output_name}.%(ext)s")

    cookies_path = None
    if cookies:
        cookies_path = _write_cookies_file(cookies, output_dir)

    cmd = [
        "yt-dlp",
        "--write-subs",
        "--sub-langs", sub_langs,
        "--convert-subs", "srt",
        "--skip-download",
        "--playlist-items", page_num,
        "-o", output_template,
        "--no-warnings",
        "--no-cache-dir",
        "--retries", "10",
    ]
    if cookies_path:
        cmd.extend(["--cookies", str(cookies_path)])
    cmd.append(video_url)

    print(f"正在下载字幕: {video_url}")
    print(f"字幕语言: {sub_langs}")
    print()
    logger.info(f"下载字幕: url={video_url}, sub_langs={sub_langs}, 输出目录={output_dir}")
    logger.debug(f"yt-dlp 命令: {' '.join(cmd)}")

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )

        # 扫描 output_dir 中所有 SRT 文件，找到属于本次下载的
        # yt-dlp 输出文件名形如: <output_name>.<lang>.srt (e.g. video.zh-CN.srt)
        srt_candidates = list(output_dir.glob(f"{output_name}*.srt"))
        # 过滤掉完全等于 <output_name>.srt 的（理论上不会存在因为 yt-dlp 总会加语言后缀）
        srt_candidates = [p for p in srt_candidates if p.name != f"{output_name}.srt"]

        if not srt_candidates:
            logger.info("yt-dlp 未下载到任何 SRT 字幕文件")
            return None

        # 优先级: 中文人工字幕 (zh-CN/zh-Hans/zh-TW) > AI 字幕 (ai-zh) > 其他
        def _priority(p: Path) -> int:
            name = p.name.lower()
            if "ai-zh" in name:
                return 2  # AI 字幕优先级最低
            if "zh" in name:
                return 0  # 人工中文字幕优先
            return 1

        srt_candidates.sort(key=_priority)
        selected = srt_candidates[0]
        logger.debug(f"选中的字幕文件: {selected.name} (候选: {[p.name for p in srt_candidates]})")

        # 重命名为 <output_name>.srt（覆盖）
        target = output_dir / f"{output_name}.srt"
        if selected.resolve() != target.resolve():
            if target.exists():
                target.unlink()
            selected.rename(target)
            logger.info(f"字幕已重命名: {selected.name} -> {target.name}")

        print(f"\n字幕已下载: {target.name}")
        return target

    except subprocess.CalledProcessError as e:
        stderr_msg = (e.stderr or "").strip()[:500]
        logger.error(f"yt-dlp 字幕下载失败, 退出码: {e.returncode}, stderr: {stderr_msg}")
        # yt-dlp 在没有匹配字幕时也会返回非零退出码，视为"无字幕"而非错误
        return None
    finally:
        if cookies_path and cookies_path.exists():
            try:
                cookies_path.unlink()
            except OSError:
                pass


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
