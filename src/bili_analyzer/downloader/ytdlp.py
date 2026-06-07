"""yt-dlp 视频下载封装

使用 yt-dlp 下载 B站视频，支持画质选择和进度提示。
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("bili_analyzer.downloader")

# 模拟浏览器的 User-Agent / Referer，B站风控必需
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BROWSER_REFERER = "https://www.bilibili.com"


def check_ytdlp() -> bool:
    if not shutil.which('yt-dlp'):
        raise RuntimeError(
            "未找到 yt-dlp!\n\n"
            "请先安装:\n"
            "  pip install yt-dlp\n"
        )
    return True


def _warm_buvid3(cookies: dict) -> dict:
    """通过访问 bilibili.com 预热 buvid3 等风控 cookie

    B站风控对 /x/player/v2 等接口要求请求中包含 buvid3 cookie。
    该 cookie 由 B站在首次访问 https://www.bilibili.com 时通过 Set-Cookie 写入。
    QR 登录返回的 cookies 中不含 buvid3，需主动预热。

    Args:
        cookies: 现有 cookies 字典（用于已登录身份访问首页）

    Returns:
        dict: 合并 buvid3 等风控 cookie 后的新字典（不修改原 dict）
    """
    enriched = dict(cookies) if cookies else {}
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": _BROWSER_UA,
            "Referer": _BROWSER_REFERER,
        })
        # 若有 SESSDATA 等登录态，一并设置
        if cookies:
            for name, value in cookies.items():
                session.cookies.set(name, value, domain=".bilibili.com")
        session.get("https://www.bilibili.com", timeout=10, allow_redirects=True)
        for cookie in session.cookies:
            if cookie.domain.endswith("bilibili.com"):
                enriched.setdefault(cookie.name, cookie.value)
        logger.debug(f"buvid3 预热后 cookies: {list(enriched.keys())}")
    except Exception as e:
        logger.warning(f"buvid3 预热失败（不影响主流程）: {e}")
    return enriched


def _write_cookies_file(cookies: dict, output_dir: Path) -> Path:
    """将 cookie 字典写入临时 Netscape 文件

    ⚠️ 不再预热 buvid3 / b_nut：B站 WAF（openresty）会把"requests 库访问
    首页拿到的低信任度 buvid3"识别为机器人特征，反而触发 412。直接使用 QR
    登录返回的 cookies 即可（SESSDATA/sid/first_domain 等已通过 WAF 验证）。

    保留 _warm_buvid3 函数仅作为历史参考，不要再调用。

    Args:
        cookies: B站 Cookie 字典（QR 登录获取的 8 项）
        output_dir: 临时文件输出目录

    Returns:
        Path: 写入的 .cookies.txt 路径
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cookies_path = output_dir / ".cookies.txt"

    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in cookies.items():
        lines.append(f".bilibili.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}")
    cookies_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"已写入 cookies 文件: {cookies_path} ({len(cookies)} 项)")
    return cookies_path


def _resolve_cookies_path(
    cookies: Optional[dict],
    cookies_file: Optional[str],
    output_dir: Path,
) -> Optional[Path]:
    """按优先级选择 cookies 路径：
    1. 用户显式提供的 cookies_file（最高优先级，浏览器导出）
    2. QR 登录 cookies + buvid3 预热
    """
    if cookies_file and Path(cookies_file).is_file():
        logger.info(f"使用外部 cookies 文件: {cookies_file}")
        return Path(cookies_file)
    if cookies:
        return _write_cookies_file(cookies, output_dir)
    return None


def _yt_dlp_base_args(cookies_path: Optional[Path]) -> list:
    """构造 yt-dlp 命令的公共部分（UA/Referer/通用选项）"""
    cmd = [
        "--user-agent", _BROWSER_UA,
        "--add-headers", f"Referer:{_BROWSER_REFERER}",
        "--no-cache-dir",
        "--retries", "10",
    ]
    if cookies_path:
        cmd.extend(["--cookies", str(cookies_path)])
    return cmd


def download_video(
    video_url: str,
    output_dir: Path,
    quality: str = "1080p",
    cookies: Optional[dict] = None,
    cookies_file: Optional[str] = None,
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

    # 解析 URL 中的分P参数，确保 yt-dlp 下载正确的分P
    # B站多P视频在 yt-dlp 中被视为播放列表，--no-playlist 会忽略 ?p=N 参数导致总是下载第1P
    import urllib.parse
    parsed = urllib.parse.urlparse(video_url)
    query_params = urllib.parse.parse_qs(parsed.query)
    page_num = query_params.get("p", ["1"])[0]

    cookies_path = _resolve_cookies_path(cookies, cookies_file, output_dir)

    cmd = [
        "yt-dlp",
        "-f", format_str,
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--playlist-items", page_num,
        "--abort-on-unavailable-fragment",
        "--fragment-retries", "10",
    ]
    cmd.extend(_yt_dlp_base_args(cookies_path))
    cmd.append(video_url)

    print(f"正在下载视频: {video_url}")
    print(f"画质: {quality}")
    print()
    logger.info(f"下载视频: url={video_url}, 画质={quality}, 输出目录={output_dir}")
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
        if cookies_path and cookies_path.exists() and cookies_path == (output_dir / ".cookies.txt"):
            try:
                cookies_path.unlink()
            except OSError:
                pass


def download_subtitle(
    video_url: str,
    output_dir: Path,
    sub_langs: str = "zh-CN,zh-Hans,zh-TW,ai-zh",
    cookies: Optional[dict] = None,
    cookies_file: Optional[str] = None,
    output_name: str = "video",
) -> Optional[Path]:
    """使用 yt-dlp 下载 B站字幕并转换为 SRT

    Args:
        video_url: 视频 URL（含 ?p=N 分P参数）
        output_dir: 字幕输出目录
        sub_langs: 字幕语言列表，逗号分隔（传给 --sub-langs）
        cookies: B站 Cookie 字典（QR 登录获取的 4 项）
        cookies_file: 用户提供的浏览器导出的 cookies.txt 路径（优先级高于 cookies）
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

    cookies_path = _resolve_cookies_path(cookies, cookies_file, output_dir)

    cmd = [
        "yt-dlp",
        "--write-subs",
        "--sub-langs", sub_langs,
        "--convert-subs", "srt",
        "--skip-download",
        "--playlist-items", page_num,
        "-o", output_template,
    ]
    cmd.extend(_yt_dlp_base_args(cookies_path))
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
        if cookies_path and cookies_path.exists() and cookies_path == (output_dir / ".cookies.txt"):
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
