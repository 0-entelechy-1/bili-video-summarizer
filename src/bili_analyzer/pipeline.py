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
from bili_analyzer.api.bilibili import extract_bvid, get_video_info, get_pages, PageInfo
from bili_analyzer.downloader.ytdlp import download_video, check_ytdlp
from bili_analyzer.screenshot.ffmpeg import check_ffmpeg, batch_capture
from bili_analyzer.parser.srt import parse_srt_file, get_full_transcript
from bili_analyzer.reporter.markdown import generate_markdown

logger = logging.getLogger("bili_analyzer")


def _safe_dirname(title: str) -> str:
    return "".join(
        c for c in title if c.isalnum() or c in (' ', '-', '_', '(', ')', '，', '。', '"', '"', '？', '！', '、')
    ).strip()[:50]


def _print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║         B站视频分析器  v1.0.0                                ║
║                                                              ║
║         自动提取知识点 · 生成学习报告                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def _print_step(step: int, total: int, message: str):
    print(f"\n[步骤 {step}/{total}] {message}...")
    print("-" * 60)


def _format_elapsed(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def _cleanup_video(video_path: Path, keep_video: bool):
    if keep_video:
        print(f"\n视频文件已保留: {video_path}")
        return

    try:
        if video_path.exists():
            file_size_mb = video_path.stat().st_size / (1024 * 1024)
            video_path.unlink()
            print(f"\n视频文件已自动清理: {video_path.name} (释放 {file_size_mb:.1f} MB)")
    except Exception as e:
        print(f"\n视频清理失败: {e}")


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
                    print(f"⚠️  警告: 忽略无效的分P编号: {invalid}")
                return valid_indices
            else:
                print(f"⚠️  警告: --page 参数 '{page_config}' 无效，未找到有效的分P编号")
        except ValueError:
            print(f"⚠️  警告: --page 参数 '{page_config}' 格式错误，应为数字或逗号分隔的数字")

    print(f"\n该视频共有 {len(pages)} 个分P:")
    for i, p in enumerate(pages, 1):
        print(f"  [{i}] {p.title} ({p.duration}秒)")

    while True:
        print("\n请输入要分析的分P编号（多个用逗号分隔，如 1,3,5），或输入 all 选择全部")
        print("10分钟内未输入将默认选择全部")

        try:
            import platform

            if platform.system() != "Windows":
                import signal

                def alarm_handler(signum, frame):
                    raise TimeoutError

                signal.signal(signal.SIGALRM, alarm_handler)
                signal.alarm(600)

                try:
                    raw = input("选择: ").strip()
                finally:
                    signal.alarm(0)
            else:
                from threading import Thread
                import time as _time

                input_done = [False]

                def wait_and_notify():
                    _time.sleep(600)
                    if not input_done[0]:
                        print("\n[提示] 已等待10分钟，按回车将默认选择全部")

                t = Thread(target=wait_and_notify, daemon=True)
                t.start()
                raw = input("选择: ").strip()
                input_done[0] = True

            if raw.lower() == "all":
                return list(range(len(pages)))

            if not raw:
                print("⚠️  输入为空，请重新输入")
                continue

            import re
            try:
                indices = [int(x.strip()) - 1 for x in re.split(r"[,，]", raw)]
            except ValueError:
                print(f"⚠️  输入 '{raw}' 格式错误，请输入数字或逗号分隔的数字")
                continue

            valid_indices = [i for i in indices if 0 <= i < len(pages)]
            if valid_indices:
                if len(valid_indices) < len(indices):
                    invalid = [i + 1 for i in indices if i < 0 or i >= len(pages)]
                    print(f"⚠️  忽略无效的分P编号: {invalid}")
                return valid_indices
            else:
                print(f"⚠️  输入 '{raw}' 无效，请输入 1-{len(pages)} 之间的编号")
                continue

        except TimeoutError:
            print("\n已超时，默认选择全部分P")
            return list(range(len(pages)))
        except Exception:
            print("⚠️  输入无效，请重新输入")
            continue


def _cleanup_audio(video_dir: Path, video_stem: str, auto_delete: bool):
    if not auto_delete:
        return
    audio_path = video_dir / f"{video_stem}.mp3"
    try:
        if audio_path.exists():
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)
            audio_path.unlink()
            print(f"音频文件已自动清理: {audio_path.name} (释放 {file_size_mb:.1f} MB)")
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

    # 2. 尝试从本地凭证文件加载
    if not cookies:
        from bili_analyzer.api.auth import load_credentials
        cookies = load_credentials()
        if cookies:
            print("已从本地凭证文件加载 B站 Cookie")

    if cookies:
        from bili_analyzer.api.bilibili import set_cookies
        set_cookies(cookies)
        print(f"已加载 B站 Cookie ({len(cookies)} 项)")
        logger.info(f"已加载 B站 Cookie ({len(cookies)} 项)")
    else:
        print("未配置 B站 Cookie，部分功能可能受限，使用 --login 扫码登录")
        logger.info("未配置 B站 Cookie")

    return cookies


def _save_transcript(srt_path: Path, video_dir: Path, video_stem: str) -> Path:
    segments = parse_srt_file(srt_path)
    transcript_text = get_full_transcript(segments, include_timestamps=False)
    transcript_path = video_dir / f"{video_stem}_字幕原文.txt"
    transcript_path.write_text(transcript_text, encoding='utf-8')
    print(f"字幕原文已保存: {transcript_path.name}")
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

    Returns:
        Dict: 包含 report_path, screenshots_dir, srt_path 等结果信息
    """
    total_steps = 7
    video_path = None
    result = {}

    # 构建输出目录和文件名，附加时间戳避免目录复用导致断点续传冲突
    timestamp = datetime.now().strftime("%m%d_%H%M%S")
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
    logger.info(f"分P输出目录: {video_dir.resolve()}")

    # 构建视频下载 URL（多P需要 ?p=N 参数）
    page_video_url = f"https://www.bilibili.com/video/{bvid}?p={page_info.page}"

    # ===== 步骤 2: 下载视频 =====
    _print_step(2 + step_offset, total_steps, f"下载视频 - {page_info.title}")
    logger.info(f"开始下载视频: {page_video_url}, 画质: {config.download.quality}")

    step_start = time.time()

    video_path = download_video(
        video_url=page_video_url,
        output_dir=video_dir,
        quality=config.download.quality,
        cookies=cookies,
        output_name=output_name,
    )
    logger.info(f"视频下载完成: {video_path}")

    step_elapsed = time.time() - step_start
    print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
    logger.info("步骤 2 耗时: %s", _format_elapsed(step_elapsed))

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

    from bili_analyzer.transcriber.cc_subtitle import CCSubtitleTranscriber
    cc_transcriber = CCSubtitleTranscriber(bvid=bvid, prefer_language="zh", cid=page_info.cid, cookies=cookies)

    if cc_transcriber.has_subtitle():
        print("检测到CC字幕，跳过语音识别")
        logger.info("检测到CC字幕，使用CC字幕")
        srt_path = cc_transcriber.transcribe(video_path, video_dir)
    else:
        print("未检测到CC字幕，使用语音识别")
        logger.info("未检测到CC字幕，使用语音识别")

        from bili_analyzer.transcriber import get_transcriber_chain
        transcriber_chain = get_transcriber_chain(config, bvid, cid=page_info.cid)

        if not transcriber_chain:
            raise RuntimeError(
                "无可用转录方式!\n"
                "请安装以下任一:\n"
                "  - pip install openai-whisper (本地转录)\n"
                "  - 配置火山引擎 API (在线转录)\n"
            )

        last_error = None
        for transcriber in transcriber_chain:
            try:
                print(f"尝试使用 {transcriber.name} 转录...")
                logger.info(f"尝试使用 {transcriber.name} 转录")
                srt_path = transcriber.transcribe(video_path, video_dir)
                logger.info(f"{transcriber.name} 转录成功: {srt_path}")
                break
            except Exception as e:
                logger.warning(f"{transcriber.name} 转录失败: {e}")
                last_error = e
                continue
        else:
            raise RuntimeError("所有转录方式均失败") from last_error

        _cleanup_audio(video_dir, video_path.stem, config.cleanup.auto_delete_audio)

    if not srt_path or not srt_path.exists():
        raise RuntimeError("字幕文件生成失败")

    _save_transcript(srt_path, video_dir, video_path.stem)

    step_elapsed = time.time() - step_start
    print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
    logger.info("步骤 3 耗时: %s", _format_elapsed(step_elapsed))

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
            print(f"尝试使用 {analyzer.name} 分析...")
            logger.info(f"尝试使用 {analyzer.name} 分析")
            analysis_result = analyzer.analyze(video_info_dict, srt_content)
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
    from bili_analyzer.analyzer.base import BaseAnalyzer
    for analyzer in analyzer_chain:
        try:
            analyzer.save_analysis(analysis_result, analysis_json_path)
            break
        except Exception:
            analysis_json_path.write_text(
                json.dumps(analysis_result, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            print(f"分析结果已保存: {analysis_json_path}")
            break

    step_elapsed = time.time() - step_start
    print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
    logger.info("步骤 4 耗时: %s", _format_elapsed(step_elapsed))

    # ===== 步骤 5: 截取关键画面 =====
    _print_step(5 + step_offset, total_steps, f"截取关键画面 - {page_info.title}")

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

    step_elapsed = time.time() - step_start
    print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
    logger.info("步骤 5 耗时: %s", _format_elapsed(step_elapsed))

    # ===== 步骤 6: 生成报告 =====
    _print_step(6 + step_offset, total_steps, f"生成学习笔记 - {page_info.title}")

    step_start = time.time()

    transcript_text = ""
    if success_analyzer:
        try:
            print(f"使用 {success_analyzer.name} 进行字幕排版...")
            logger.info(f"使用 {success_analyzer.name} 进行字幕排版")
            transcript_text = success_analyzer.format_transcript(srt_content)
            logger.info("字幕原文语义分段排版完成")
        except Exception as e:
            logger.warning(f"字幕分段排版失败: {e}")

    if not transcript_text:
        segments = parse_srt_file(srt_path)
        transcript_text = get_full_transcript(segments, include_timestamps=True)

    report_path = generate_markdown(
        video_info=video_info_dict,
        analysis=analysis_result,
        screenshots=screenshot_mapping,
        srt_content=srt_content,
        output_dir=reports_dir,
        transcript_text=transcript_text,
    )

    step_elapsed = time.time() - step_start
    print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
    logger.info("步骤 6 耗时: %s", _format_elapsed(step_elapsed))

    # ===== 步骤 7: 清理视频 =====
    _print_step(7 + step_offset, total_steps, f"清理 - {page_info.title}")

    step_start = time.time()

    should_keep = config.keep_video or not config.cleanup.auto_delete_video
    _cleanup_video(video_path, should_keep)

    step_elapsed = time.time() - step_start
    print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
    logger.info("步骤 7 耗时: %s", _format_elapsed(step_elapsed))

    result["report_path"] = report_path
    result["screenshots_dir"] = screenshots_dir
    result["srt_path"] = srt_path
    result["transcript_path"] = video_dir / f"{video_path.stem}_字幕原文.txt"
    result["video_path"] = video_path if should_keep else None
    result["video_dir"] = video_dir
    result["should_keep"] = should_keep
    result["page"] = page_info.page
    result["title"] = page_info.title

    return result


def run_pipeline(config: AppConfig) -> None:
    total_steps = 7
    video_path = None

    total_start = time.time()
    _print_banner()

    try:
        current_cookies = _load_bilibili_cookie(config.bilibili.cookie)
        print("检查运行环境...")
        logger.info("开始检查运行环境")
        check_ffmpeg()
        check_ytdlp()
        logger.info("运行环境检查通过")
        print()

        # ===== 步骤 1: 获取视频信息 =====
        _print_step(1, total_steps, "获取视频信息")

        step_start = time.time()

        bvid = extract_bvid(config.video_url)
        print(f"BV号: {bvid}")

        video_info = get_video_info(bvid)
        print(f"标题: {video_info.title}")
        print(f"UP主: {video_info.owner}")
        print(f"时长: {video_info.duration}秒")
        logger.info(f"视频信息: BV号={bvid}, 标题={video_info.title}, UP主={video_info.owner}, 时长={video_info.duration}秒")

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输出目录: {output_dir.resolve()}")

        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # 获取分P列表并选择
        pages = get_pages(bvid)
        selected_indices = _select_pages(pages, config.page)
        selected_pages = [pages[i] for i in selected_indices]

        if len(pages) > 1:
            print(f"\n已选择 {len(selected_pages)} 个分P进行分析")
            for p in selected_pages:
                print(f"  - 第{p.page}P: {p.title} ({p.duration}秒)")

        safe_video_title = _safe_dirname(video_info.title)

        step_elapsed = time.time() - step_start
        print(f"步骤耗时: {_format_elapsed(step_elapsed)}")
        logger.info("步骤 1 耗时: %s", _format_elapsed(step_elapsed))

        # 对每个选中的分P进行分析
        all_results = []
        failed_pages = []
        for idx, page_info in enumerate(selected_pages):
            if len(selected_pages) > 1:
                print(f"\n{'=' * 60}")
                print(f"开始分析第 {idx + 1}/{len(selected_pages)} 个分P: {page_info.title}")
                print(f"{'=' * 60}")

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
                )
                all_results.append(result)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"第{page_info.page}P分析失败: {error_msg}")
                failed_pages.append((page_info, error_msg))

        # 清理空的视频输出目录（当所有分P都失败时）
        _cleanup_empty_video_dirs(output_dir, safe_video_title)

        # ===== 完成 =====
        print("\n" + "=" * 60)
        print("分析完成!")
        print("=" * 60)

        if all_results:
            if len(pages) == 1:
                print("\n分析成功:")
            else:
                print("\n分析成功的分P:")
            for result in all_results:
                if len(pages) > 1:
                    print(f"\n第{result['page']}P: {result['title']}")
                else:
                    print(f"\n视频: {result['title']}")
                print(f"  报告路径: {result['report_path']}")
                print(f"  截图目录: {result['screenshots_dir']}")
                print(f"  字幕文件: {result['srt_path']}")
                print(f"  字幕原文: {result['transcript_path']}")
                if result["should_keep"] and result["video_path"]:
                    print(f"  视频文件: {result['video_path']}")

        if failed_pages:
            if len(pages) == 1:
                print("\n分析失败:")
            else:
                print("\n分析失败的分P:")
            for page_info, error_msg in failed_pages:
                if len(pages) > 1:
                    print(f"  第{page_info.page}P: {page_info.title} - {error_msg}")
                else:
                    print(f"  {page_info.title} - {error_msg}")

        total_elapsed = time.time() - total_start
        print(f"\n总运行时间: {_format_elapsed(total_elapsed)}")
        logger.info(f"总运行时间: {_format_elapsed(total_elapsed)}")

        if failed_pages and not all_results:
            raise RuntimeError(f"所有分P分析均失败，共 {len(failed_pages)} 个分P")

    except KeyboardInterrupt:
        total_elapsed = time.time() - total_start
        print(f"已运行时间: {_format_elapsed(total_elapsed)}")
        logger.info(f"异常时已运行时间: {_format_elapsed(total_elapsed)}")
        print("\n\n用户中断")
        logger.warning("用户中断")
        raise
    except Exception as e:
        total_elapsed = time.time() - total_start
        print(f"已运行时间: {_format_elapsed(total_elapsed)}")
        logger.info(f"异常时已运行时间: {_format_elapsed(total_elapsed)}")
        print(f"\n\n错误: {e}")
        logger.error(f"运行出错: {e}", exc_info=True)
        raise
