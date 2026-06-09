"""主流程编排

串联完整分析流程：
1. 获取视频信息
2. 下载视频
3. 获取/转录字幕（优先 CC 字幕）
4. LLM 分析
5. 截取关键画面
6. 生成报告
7. 清理视频（可配置）
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from bili_analyzer.config import AppConfig
from bili_analyzer.analyzer.usage import TokenTracker
from bili_analyzer.api.bilibili import extract_bvid, get_video_info, get_pages, PageInfo
from bili_analyzer.downloader.ytdlp import download_video, check_ytdlp, DiskSpaceError
from bili_analyzer.screenshot.ffmpeg import check_ffmpeg, batch_capture
from bili_analyzer.parser.srt import parse_srt_file, get_full_transcript
from bili_analyzer.reporter.markdown import generate_markdown
from bili_analyzer.ui.console import (
    check_conda_env,
    console,
    format_elapsed,
    print_banner,
    print_config_summary,
    print_error,
    print_info,
    print_output_tree,
    print_step_elapsed,
    print_step_header,
    print_summary_table,
    print_success,
    print_total_token_summary,
    print_video_card,
    print_warning,
)

logger = logging.getLogger("bili_analyzer")


def _safe_dirname(title: str) -> str:
    return "".join(
        c for c in title if c.isalnum() or c in (' ', '-', '_', '(', ')', '，', '。', '"', '"', '？', '！', '、')
    ).strip()[:50]


def _print_banner():
    """彩色启动横幅（步骤1的开始处也会用）"""
    from bili_analyzer import __version__
    print_banner(__version__)


def _print_step(step: int, total: int, message: str):
    print_step_header(step, total, message)


def _cleanup_video(video_path: Path, keep_video: bool):
    if keep_video:
        print_info(f"视频文件已保留: {video_path}")
        return

    try:
        if video_path.exists():
            file_size_mb = video_path.stat().st_size / (1024 * 1024)
            video_path.unlink()
            print_success(f"视频文件已自动清理: {video_path.name} (释放 {file_size_mb:.1f} MB)")
    except Exception as e:
        print_error(f"视频清理失败: {e}")


def _cleanup_empty_video_dirs(output_dir: Path, safe_video_title: str) -> None:
    """清理空的视频输出目录（时间戳目录下没有任何成功生成的文件时）"""
    videos_dir = output_dir / "videos"
    if not videos_dir.exists():
        return

    for item in videos_dir.iterdir():
        if item.is_dir() and item.name.startswith(safe_video_title + "_"):
            # 检查目录是否为空或只包含临时文件
            has_content = False
            for f in item.rglob("*"):
                if f.is_file() and f.suffix not in (".part", ".ytdl", ".tmp"):
                    has_content = True
                    break
            if not has_content:
                import shutil
                try:
                    shutil.rmtree(item)
                    logger.info(f"清理空目录: {item}")
                except Exception as e:
                    logger.warning(f"清理空目录失败: {item}, {e}")


def _select_pages(pages, page_config: Optional[str]) -> List[int]:
    """选择要分析的分P

    Args:
        pages: PageInfo 列表
        page_config: 命令行传入的 --page 参数

    Returns:
        List[int]: 选中的分P索引列表（从0开始）
    """
    if len(pages) == 1:
        return [0]

    if page_config:
        if page_config.lower() == "all":
            return list(range(len(pages)))
        try:
            import re
            indices = [int(x.strip()) - 1 for x in re.split(r"[,，]", page_config)]
            valid_indices = [i for i in indices if 0 <= i < len(pages)]
            if valid_indices:
                if len(valid_indices) < len(indices):
                    invalid = [i + 1 for i in indices if i < 0 or i >= len(pages)]
                    print_warning(f"忽略无效的分P编号: {invalid}")
                return valid_indices
            else:
                print_warning(f"--page 参数 '{page_config}' 无效，未找到有效的分P编号")
        except ValueError:
            print_warning(f"--page 参数 '{page_config}' 格式错误，应为数字或逗号分隔的数字")

    # 分P 列表用 Panel 包裹展示
    from rich.panel import Panel
    from rich.table import Table
    pages_table = Table(show_header=False, box=None, padding=(0, 2))
    pages_table.add_column(style="bold cyan", no_wrap=True, justify="right")
    pages_table.add_column(style="white")
    pages_table.add_column(style="dim", no_wrap=True, justify="right")
    for i, p in enumerate(pages, 1):
        pages_table.add_row(f"[{i}]", p.title, f"{p.duration}秒")
    console.print()
    console.print(Panel(
        pages_table,
        title=f"[bold magenta]📋 该视频共有 {len(pages)} 个分P[/]",
        border_style="magenta",
        padding=(0, 1),
    ))
    console.print()

    while True:
        print_info("请输入要分析的分P编号（多个用逗号分隔，如 1,3,5），或输入 all 选择全部")
        print_info("10分钟内未输入将默认选择全部")
        console.print()

        try:
            import platform

            if platform.system() != "Windows":
                import signal

                def alarm_handler(signum, frame):
                    raise TimeoutError

                signal.signal(signal.SIGALRM, alarm_handler)
                signal.alarm(600)

                try:
                    raw = input("[bold cyan]选择:[/] ").strip()
                finally:
                    signal.alarm(0)
            else:
                from threading import Thread
                import time as _time

                input_done = [False]

                def wait_and_notify():
                    _time.sleep(600)
                    if not input_done[0]:
                        console.print("  [yellow][提示] 已等待10分钟，按回车将默认选择全部[/]")

                t = Thread(target=wait_and_notify, daemon=True)
                t.start()
                raw = input("[bold cyan]选择:[/] ").strip()
                input_done[0] = True

            if raw.lower() == "all":
                return list(range(len(pages)))

            if not raw:
                print_warning("输入为空，请重新输入")
                continue

            import re
            try:
                indices = [int(x.strip()) - 1 for x in re.split(r"[,，]", raw)]
            except ValueError:
                print_warning(f"输入 '{raw}' 格式错误，请输入数字或逗号分隔的数字")
                continue

            valid_indices = [i for i in indices if 0 <= i < len(pages)]
            if valid_indices:
                if len(valid_indices) < len(indices):
                    invalid = [i + 1 for i in indices if i < 0 or i >= len(pages)]
                    print_warning(f"忽略无效的分P编号: {invalid}")
                return valid_indices
            else:
                print_warning(f"输入 '{raw}' 无效，请输入 1-{len(pages)} 之间的编号")
                continue

        except TimeoutError:
            print_warning("已超时，默认选择全部分P")
            return list(range(len(pages)))
        except Exception:
            print_warning("输入无效，请重新输入")
            continue


def _cleanup_audio(video_dir: Path, video_stem: str, auto_delete: bool):
    if not auto_delete:
        return
    audio_path = video_dir / f"{video_stem}.mp3"
    try:
        if audio_path.exists():
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)
            audio_path.unlink()
            print_success(f"音频文件已自动清理: {audio_path.name} (释放 {file_size_mb:.1f} MB)")
            logger.info(f"音频文件已自动清理: {audio_path.name} (释放 {file_size_mb:.1f} MB)")
    except Exception as e:
        logger.warning(f"音频清理失败: {e}")


def _parse_cookie_str(cookie_str: str) -> dict:
    """解析 Cookie 字符串为字典"""
    cookies = {}
    if "=" in cookie_str:
        for item in cookie_str.split(";"):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
            else:
                cookies[item] = ""
    else:
        cookies["SESSDATA"] = cookie_str
    return cookies


def _load_bilibili_cookie(cookie_str: str) -> Optional[Dict[str, str]]:
    cookies = None

    # 1. 优先使用传入的 cookie_str
    if cookie_str:
        cookies = _parse_cookie_str(cookie_str)

    # 2. 尝试从项目根目录下的 cookies.txt（Netscape 格式）加载
    if not cookies:
        from bili_analyzer.api.auth import load_cookies_netscape, PROJECT_ROOT_COOKIES_FILE
        cookies = load_cookies_netscape(PROJECT_ROOT_COOKIES_FILE)
        if cookies:
            print_info(f"已从 {PROJECT_ROOT_COOKIES_FILE.name} 加载 B站 Cookie")

    if cookies:
        from bili_analyzer.api.bilibili import set_cookies
        set_cookies(cookies)
        print_success(f"已加载 B站 Cookie ({len(cookies)} 项)")
        logger.info(f"已加载 B站 Cookie ({len(cookies)} 项)")
    else:
        print_warning("未配置 B站 Cookie，部分功能可能受限")
        print_info("  请先运行: python -m bili_analyzer --login  扫码登录")
        logger.info("未配置 B站 Cookie")

    return cookies


def _save_transcript(srt_path: Path, video_dir: Path, video_stem: str) -> Path:
    segments = parse_srt_file(srt_path)
    transcript_text = get_full_transcript(segments, include_timestamps=False)
    transcript_path = video_dir / f"{video_stem}_字幕原文.txt"
    transcript_path.write_text(transcript_text, encoding='utf-8')
    print_success(f"字幕原文已保存: {transcript_path.name}")
    return transcript_path


def _analyze_single_page(
    config: AppConfig,
    bvid: str,
    video_info,
    page_info: PageInfo,
    output_dir: Path,
    reports_dir: Path,
    step_offset: int,
    cookies: Optional[Dict[str, str]] = None,
    total_pages: int = 1,
    safe_video_title: str = "",
    timestamp: str = "",
) -> Dict[str, Any]:
    """分析单个分P

    Args:
        config: 应用配置
        bvid: BV号
        video_info: 视频信息
        page_info: 分P信息
        output_dir: 输出目录
        reports_dir: 报告目录
        step_offset: 步骤编号偏移量
        total_pages: 总分P数（用于判断单P/多P）
        safe_video_title: 处理后的视频标题（用于构建目录）
        timestamp: 统一时间戳

    Returns:
        Dict: 包含 report_path, screenshots_dir, srt_path 等结果信息
    """
    total_steps = 7
    video_path = None
    result = {}
    _page_start = time.time()  # 整个分P处理的起始时间（用于最终 elapsed）
    token_tracker = TokenTracker()  # 本分P 的 LLM token 累计

    # 构建输出目录和文件名，附加时间戳避免目录复用导致断点续传冲突
    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not safe_video_title:
        safe_video_title = _safe_dirname(video_info.title)
    safe_page_title = _safe_dirname(page_info.title)
    if not safe_page_title:
        safe_page_title = safe_video_title

    is_single_page = total_pages == 1

    if is_single_page:
        # 单P视频：outputs/videos/视频名_时间戳/
        video_dir = output_dir / "videos" / f"{safe_video_title}_{timestamp}"
        output_name = safe_video_title
        # 兜底：检查完整路径长度，超过 200 字符时回退到 BV号
        test_path = video_dir / f"{output_name}.mp4"
        if len(str(test_path)) > 200:
            output_name = bvid
    else:
        # 多P视频：outputs/videos/视频名_时间戳/P2_分P名/
        if safe_page_title:
            page_folder_name = f"P{page_info.page}_{safe_page_title[:40]}"
        elif safe_video_title:
            page_folder_name = f"P{page_info.page}_{safe_video_title[:40]}"
        else:
            page_folder_name = f"P{page_info.page}_{bvid}"
        video_dir = output_dir / "videos" / f"{safe_video_title}_{timestamp}" / page_folder_name
        output_name = page_folder_name

    video_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"分P输出目录: {video_dir}")

    # 构建视频下载 URL（多P需要 ?p=N 参数）
    page_video_url = f"https://www.bilibili.com/video/{bvid}?p={page_info.page}"

    # ===== 步骤 2: 下载视频 =====
    _print_step(2 + step_offset, total_steps, f"下载视频 - {page_info.title}")
    logger.info(f"开始下载视频: {page_video_url}, 画质: {config.download.quality}")

    step_start = time.time()

    try:
        video_path = download_video(
            video_url=page_video_url,
            output_dir=video_dir,
            quality=config.download.quality,
            cookies=cookies,
            output_name=output_name,
            duration_sec=page_info.duration,
        )
    except DiskSpaceError as e:
        # 磁盘满：列出可执行清理建议（让用户知道下一步该做什么）
        from bili_analyzer.downloader.ytdlp import estimate_required_mb
        required_mb = estimate_required_mb(config.download.quality, page_info.duration)
        print_error(f"分P《{page_info.title}》下载失败：磁盘空间不足（需 ~{required_mb}MB）")
        print_warning("可执行以下命令清理后重试：")
        print_warning(f"  1. 清理旧视频目录: Remove-Item '{output_dir}\\videos\\*' -Recurse -Force")
        print_warning(f"  2. 清理 conda 缓存: conda clean --all -y")
        print_warning(f"  3. 清理 pip 缓存: pip cache purge")
        print_warning(f"  4. 清理旧日志: Remove-Item '{Path(__file__).parent.parent.parent}\\logs\\bili_analyzer_*.log' -Force")
        logger.error(f"分P《{page_info.title}》磁盘空间不足：{e}")
        raise  # 让上层走"分P失败"流程
    # 注：download_video() 内部已 print_success + logger.info（带文件大小），这里不再重复记录

    step_elapsed = time.time() - step_start
    print_step_elapsed(step_elapsed)
    logger.info("步骤 2 耗时: %s", format_elapsed(step_elapsed))

    # ===== 步骤 3: 获取/转录字幕 =====
    _print_step(3 + step_offset, total_steps, f"获取字幕 - {page_info.title}")

    step_start = time.time()

    srt_path = None
    transcriber_chain = None

    video_info_dict = {
        "bvid": video_info.bvid,
        "aid": video_info.aid,
        "title": video_info.title,
        "owner": video_info.owner,
        "duration": page_info.duration,
        "cid": page_info.cid,
        "desc": video_info.desc,
        "page_title": page_info.title,
        "page": page_info.page,
    }

    # 先尝试 yt-dlp 下载字幕（sub_langs 配置决定语言优先级，中文人工优先，AI 兜底）
    ytdlp_sub_langs = config.transcriber.sub_langs
    print_info(f"尝试通过 yt-dlp 下载字幕 (sub_langs={ytdlp_sub_langs})…")
    logger.info(f"尝试通过 yt-dlp 下载字幕: {page_video_url}, sub_langs={ytdlp_sub_langs}")

    from bili_analyzer.transcriber.ytdlp_subtitle import YtdlpSubtitleTranscriber
    ytdlp_transcriber = YtdlpSubtitleTranscriber(
        video_url=page_video_url,
        sub_langs=ytdlp_sub_langs,
        cookies=cookies,
        cookies_file=config.transcriber.cookies_file,
    )

    try:
        srt_path = ytdlp_transcriber.transcribe(video_path, video_dir)
        print_success("已通过 yt-dlp 获取字幕")
        logger.info("已通过 yt-dlp 获取字幕")
    except Exception as e:
        logger.warning(f"yt-dlp 字幕下载失败: {e}")
        print_warning(f"yt-dlp 字幕下载失败: {e}")
        print_warning("回退到语音识别…")
        logger.info("回退到语音识别")

        from bili_analyzer.transcriber import get_transcriber_chain
        transcriber_chain = get_transcriber_chain(
            config, bvid, page_num=page_info.page, cookies=cookies,
        )

        if not transcriber_chain:
            raise RuntimeError(
                "无可用转录方式!\n"
                "请安装以下任一:\n"
                "  - pip install openai-whisper (本地转录)\n"
                "  - 配置火山引擎 API (在线转录)\n"
            )

        last_error = e
        for transcriber in transcriber_chain:
            try:
                print_info(f"尝试使用 {transcriber.name} 转录…")
                logger.info(f"尝试使用 {transcriber.name} 转录")
                srt_path = transcriber.transcribe(video_path, video_dir)
                logger.info(f"{transcriber.name} 转录成功: {srt_path.name}")
                break
            except Exception as ex:
                logger.warning(f"{transcriber.name} 转录失败: {ex}")
                last_error = ex
                continue
        else:
            raise RuntimeError("所有转录方式均失败") from last_error

        _cleanup_audio(video_dir, video_path.stem, config.cleanup.auto_delete_audio)

    if not srt_path or not srt_path.exists():
        raise RuntimeError("字幕文件生成失败")

    _save_transcript(srt_path, video_dir, video_path.stem)

    step_elapsed = time.time() - step_start
    print_step_elapsed(step_elapsed)
    logger.info("步骤 3 耗时: %s", format_elapsed(step_elapsed))

    # ===== 步骤 4: LLM 分析 =====
    _print_step(4 + step_offset, total_steps, f"LLM分析字幕内容 - {page_info.title}")

    step_start = time.time()

    srt_content = srt_path.read_text(encoding='utf-8')

    from bili_analyzer.analyzer import get_analyzer_chain
    analyzer_chain = get_analyzer_chain(config)

    analysis_result = None
    last_error = None
    success_analyzer = None

    for analyzer in analyzer_chain:
        try:
            print_info(f"尝试使用 {analyzer.name} 分析…")
            logger.info(f"尝试使用 {analyzer.name} 分析")
            analysis_result, analyze_usage = analyzer.analyze(video_info_dict, srt_content)
            token_tracker.add(analyze_usage)
            success_analyzer = analyzer
            logger.info(f"{analyzer.name} 分析成功")
            break
        except Exception as e:
            logger.warning(f"{analyzer.name} 分析失败: {e}")
            last_error = e
            continue

    if analysis_result is None:
        raise RuntimeError("所有分析方式均失败") from last_error

    analysis_json_path = video_dir / f"{video_path.stem}_analysis.json"
    for analyzer in analyzer_chain:
        try:
            analyzer.save_analysis(analysis_result, analysis_json_path)
            break
        except Exception:
            analysis_json_path.write_text(
                json.dumps(analysis_result, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            print_success(f"分析结果已保存: {analysis_json_path}")
            break

    step_elapsed = time.time() - step_start
    print_step_elapsed(step_elapsed)
    logger.info("步骤 4 耗时: %s", format_elapsed(step_elapsed))

    # ===== 步骤 5: 生成学习笔记（含 LLM 排版，cache 命中点） =====
    # 注：本步骤把"字幕排版" LLM 调用（与步骤 4 的 analyze 共享 prefix cache）
    # 提到步骤 5，并先生成不含截图的报告草稿。
    # 步骤 6 截取关键画面后，会用真实截图重新生成报告。
    _print_step(5 + step_offset, total_steps, f"生成学习笔记 - {page_info.title}")

    step_start = time.time()

    transcript_text = ""
    if success_analyzer:
        try:
            print_info(f"使用 {success_analyzer.name} 进行字幕排版…")
            logger.info(f"使用 {success_analyzer.name} 进行字幕排版")
            transcript_text, format_usage = success_analyzer.format_transcript(srt_content)
            token_tracker.add(format_usage)
            logger.info("字幕原文语义分段排版完成")
        except Exception as e:
            logger.warning(f"字幕分段排版失败: {e}")

    if not transcript_text:
        segments = parse_srt_file(srt_path)
        transcript_text = get_full_transcript(segments, include_timestamps=True)

    # 草稿报告（不含截图，截图在步骤 6 截取后注入）
    report_path = generate_markdown(
        video_info=video_info_dict,
        analysis=analysis_result,
        screenshots={},  # 草稿不嵌入截图
        srt_content=srt_content,
        output_dir=reports_dir,
        transcript_text=transcript_text,
        timestamp=timestamp,
    )

    step_elapsed = time.time() - step_start
    print_step_elapsed(step_elapsed)
    logger.info("步骤 5 耗时: %s", format_elapsed(step_elapsed))

    # ===== 步骤 6: 截取关键画面 + 用真实截图重新生成报告 =====
    _print_step(6 + step_offset, total_steps, f"截取关键画面 - {page_info.title}")

    step_start = time.time()

    key_screenshots = analysis_result.get('key_screenshots', [])
    screenshots_dir = video_dir / "screenshots"

    screenshot_mapping = batch_capture(
        video_path=video_path,
        timestamps=key_screenshots,
        output_dir=screenshots_dir,
        quality=config.screenshot.quality,
        max_workers=4,
        show_progress=True,
    )

    # 用真实截图重新生成报告（覆盖步骤 5 的草稿）
    report_path = generate_markdown(
        video_info=video_info_dict,
        analysis=analysis_result,
        screenshots=screenshot_mapping,
        srt_content=srt_content,
        output_dir=reports_dir,
        transcript_text=transcript_text,
        timestamp=timestamp,
    )

    step_elapsed = time.time() - step_start
    print_step_elapsed(step_elapsed)
    logger.info("步骤 6 耗时: %s", format_elapsed(step_elapsed))

    # ===== 步骤 7: 清理视频 =====
    _print_step(7 + step_offset, total_steps, f"清理 - {page_info.title}")

    step_start = time.time()

    should_keep = config.keep_video or not config.cleanup.auto_delete_video
    _cleanup_video(video_path, should_keep)

    step_elapsed = time.time() - step_start
    print_step_elapsed(step_elapsed)
    logger.info("步骤 7 耗时: %s", format_elapsed(step_elapsed))

    result["report_path"] = report_path
    result["screenshots_dir"] = screenshots_dir
    result["srt_path"] = srt_path
    result["transcript_path"] = video_dir / f"{video_path.stem}_字幕原文.txt"
    result["video_path"] = video_path if should_keep else None
    result["video_dir"] = video_dir
    result["should_keep"] = should_keep
    result["page"] = page_info.page
    result["title"] = page_info.title
    result["elapsed"] = format_elapsed(time.time() - _page_start)
    result["elapsed_seconds"] = time.time() - _page_start
    result["token_usage_summary"] = token_tracker.totals()
    result["token_usages"] = [u.to_log_dict() for u in token_tracker.usages]

    return result


def run_pipeline(config: AppConfig, timestamp: str = "") -> None:
    total_steps = 7

    total_start = time.time()
    _print_banner()

    # 环境自检：当前 Python 是否在 conda AI 环境
    if not check_conda_env():
        print_warning("当前 Python 环境不是 conda 'AI'，可能出现模块缺失。详见 .trae/rules/conda-env.md")
        logger.warning("当前 Python 环境不是 conda 'AI' 环境")

    # 启动配置摘要表
    print_config_summary(config)

    try:
        current_cookies = _load_bilibili_cookie(config.bilibili.cookie)
        print_info("检查运行环境 (FFmpeg / yt-dlp)…")
        logger.info("开始检查运行环境")
        check_ffmpeg()
        check_ytdlp()
        logger.info("运行环境检查通过")
        print_success("运行环境检查通过")
        console.print()

        # ===== 步骤 1: 获取视频信息 =====
        _print_step(1, total_steps, "获取视频信息")

        step_start = time.time()

        bvid = extract_bvid(config.video_url)
        print_info(f"BV号: {bvid}")

        video_info = get_video_info(bvid)
        logger.info(f"视频信息: BV号={bvid}, 标题={video_info.title}, UP主={video_info.owner}, 时长={video_info.duration}秒")

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输出目录: {output_dir}")
        print_info(f"输出目录: {output_dir.resolve()}")

        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # 获取分P列表
        pages = get_pages(bvid)

        # 视频信息卡片（Panel 展示）
        print_video_card(video_info, pages)

        # 分P选择
        selected_indices = _select_pages(pages, config.page)
        selected_pages = [pages[i] for i in selected_indices]

        if len(pages) > 1:
            console.print()
            console.print(f"  [bold cyan]已选择 {len(selected_pages)} 个分P进行分析:[/]")
            for p in selected_pages:
                console.print(f"    [cyan]•[/] 第{p.page}P: [green]{p.title}[/] [dim]({p.duration}秒)[/]")

        safe_video_title = _safe_dirname(video_info.title)

        step_elapsed = time.time() - step_start
        print_step_elapsed(step_elapsed)
        logger.info("步骤 1 耗时: %s", format_elapsed(step_elapsed))

        # 对每个选中的分P进行分析
        all_results = []
        failed_pages = []
        for idx, page_info in enumerate(selected_pages):
            if len(selected_pages) > 1:
                console.print()
                console.rule(
                    f"[bold magenta]开始分析第 {idx + 1}/{len(selected_pages)} 个分P:[/] [green]{page_info.title}[/]",
                    align="left",
                    style="magenta",
                )
                console.print()

            step_offset = 0
            try:
                result = _analyze_single_page(
                    config=config,
                    bvid=bvid,
                    video_info=video_info,
                    page_info=page_info,
                    output_dir=output_dir,
                    reports_dir=reports_dir,
                    step_offset=step_offset,
                    cookies=current_cookies,
                    total_pages=len(pages),
                    safe_video_title=safe_video_title,
                    timestamp=timestamp,
                )
                all_results.append(result)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"第{page_info.page}P分析失败: {error_msg}")
                failed_pages.append((page_info, error_msg))

        # 清理空的视频输出目录（当所有分P都失败时）
        _cleanup_empty_video_dirs(output_dir, safe_video_title)

        # ===== 完成 =====
        console.print()
        console.rule("[bold green]✅ 分析完成[/]", align="left", style="green")
        console.print()

        if all_results:
            # 准备汇总表格数据
            table_rows = []
            for r in all_results:
                # 计算截图数：从 video_dir/screenshots 下数 jpg
                screenshots_dir = r.get("screenshots_dir")
                screenshot_count = 0
                if screenshots_dir and screenshots_dir.exists():
                    screenshot_count = len(list(screenshots_dir.glob("*.jpg")))
                table_rows.append({
                    "page": f"P{r['page']}" if len(pages) > 1 else "单P",
                    "title": r.get("title", ""),
                    "report": str(r.get("report_path", "")),
                    "screenshots": screenshot_count,
                    "elapsed": r.get("elapsed", ""),
                })
            print_summary_table(table_rows)

            # LLM Token 总消耗汇总（跨分P 累加）
            all_token_totals = [r.get("token_usage_summary", {}) for r in all_results if r.get("token_usage_summary")]
            print_total_token_summary(all_token_totals)

            # 详细路径列表（路径太长，单独放在 Table 之后用嵌套结构展示）
            console.print()
            console.print("  [bold cyan]📂 详细产物路径:[/]")
            for r in all_results:
                if len(pages) > 1:
                    console.print(f"    [bold]第{r['page']}P:[/] [green]{r.get('title','')}[/]")
                else:
                    console.print(f"    [bold]视频:[/] [green]{r.get('title','')}[/]")
                console.print(f"      [blue]📄 报告:[/]   {r.get('report_path')}")
                console.print(f"      [magenta]🖼  截图:[/]   {r.get('screenshots_dir')}")
                console.print(f"      [yellow]📝 字幕:[/]   {r.get('srt_path')}")
                console.print(f"      [yellow]📄 原文:[/]   {r.get('transcript_path')}")
                if r.get("should_keep") and r.get("video_path"):
                    console.print(f"      [red]🎬 视频:[/]   {r.get('video_path')}")
                console.print()

            # 产物目录树（多P 时按 P1/P2/... 分别展示；单P 时只展示一次）
            for r in all_results:
                video_dir = r.get("video_dir")
                if video_dir and video_dir.exists():
                    print_output_tree(video_dir)

        if failed_pages:
            console.print()
            console.print("  [bold red]❌ 分析失败的分P:[/]")
            for page_info, error_msg in failed_pages:
                if len(pages) > 1:
                    console.print(f"    [red]✖[/] 第{page_info.page}P: {page_info.title} — {error_msg}")
                else:
                    console.print(f"    [red]✖[/] {page_info.title} — {error_msg}")
            console.print()

        total_elapsed = time.time() - total_start
        print_step_elapsed(total_elapsed)
        console.print(f"  [dim]⏱  总运行时间:[/] [bold cyan]{format_elapsed(total_elapsed)}[/]")
        logger.info(f"总运行时间: {format_elapsed(total_elapsed)}")

        if failed_pages and not all_results:
            raise RuntimeError(f"所有分P分析均失败，共 {len(failed_pages)} 个分P")

    except KeyboardInterrupt:
        total_elapsed = time.time() - total_start
        console.print()
        console.print(f"  [bold yellow]⚠  用户中断[/] (已运行 [cyan]{format_elapsed(total_elapsed)}[/])")
        logger.warning("用户中断")
        raise
    except Exception as e:
        total_elapsed = time.time() - total_start
        console.print()
        console.print(f"  [bold red]✖ 运行出错[/] (已运行 [cyan]{format_elapsed(total_elapsed)}[/]): {e}")
        logger.error(f"运行出错: {e}", exc_info=True)
        # 打印带语法高亮的 traceback
        from bili_analyzer.ui.console import print_exception
        print_exception(show_locals=False)
        raise
