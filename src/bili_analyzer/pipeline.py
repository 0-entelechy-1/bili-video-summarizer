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
from pathlib import Path
from typing import Dict, Any

from bili_analyzer.config import AppConfig
from bili_analyzer.api.bilibili import extract_bvid, get_video_info
from bili_analyzer.downloader.ytdlp import download_video, check_ytdlp
from bili_analyzer.screenshot.ffmpeg import check_ffmpeg, batch_capture
from bili_analyzer.parser.srt import parse_srt_file, get_full_transcript
from bili_analyzer.reporter.markdown import generate_markdown

logger = logging.getLogger("bili_analyzer")


def _safe_dirname(title: str) -> str:
    return "".join(
        c for c in title if c.isalnum() or c in (' ', '-', '_', '(', ')', '，', '。', '"', '"', '？', '！', '、')
    ).strip()[:80]


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


def _save_transcript(srt_path: Path, video_dir: Path, video_stem: str) -> Path:
    segments = parse_srt_file(srt_path)
    transcript_text = get_full_transcript(segments, include_timestamps=False)
    transcript_path = video_dir / f"{video_stem}_字幕原文.txt"
    transcript_path.write_text(transcript_text, encoding='utf-8')
    print(f"字幕原文已保存: {transcript_path.name}")
    return transcript_path


def run_pipeline(config: AppConfig) -> None:
    total_steps = 7
    video_path = None

    _print_banner()

    try:
        print("检查运行环境...")
        logger.info("开始检查运行环境")
        check_ffmpeg()
        check_ytdlp()
        logger.info("运行环境检查通过")
        print()

        # ===== 步骤 1: 获取视频信息 =====
        _print_step(1, total_steps, "获取视频信息")

        bvid = extract_bvid(config.video_url)
        print(f"BV号: {bvid}")

        video_info = get_video_info(bvid)
        print(f"标题: {video_info.title}")
        print(f"UP主: {video_info.owner}")
        print(f"时长: {video_info.duration}秒")
        logger.info(f"视频信息: BV号={bvid}, 标题={video_info.title}, UP主={video_info.owner}, 时长={video_info.duration}秒")

        # 准备输出目录
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输出目录: {output_dir.resolve()}")

        # 为当前视频创建独立子文件夹
        video_dirname = _safe_dirname(video_info.title)
        video_dir = output_dir / "videos" / video_dirname
        video_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"视频输出目录: {video_dir.resolve()}")

        # 报告统一输出目录
        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # ===== 步骤 2: 下载视频 =====
        _print_step(2, total_steps, "下载视频")
        logger.info(f"开始下载视频: {config.video_url}, 画质: {config.download.quality}")

        video_path = download_video(
            video_url=config.video_url,
            output_dir=video_dir,
            quality=config.download.quality,
        )
        logger.info(f"视频下载完成: {video_path}")

        # ===== 步骤 3: 获取/转录字幕 =====
        _print_step(3, total_steps, "获取字幕")

        srt_path = None
        transcriber_chain = None

        video_info_dict = {
            "bvid": video_info.bvid,
            "aid": video_info.aid,
            "title": video_info.title,
            "owner": video_info.owner,
            "duration": video_info.duration,
            "cid": video_info.cid,
            "desc": video_info.desc,
        }

        from bili_analyzer.transcriber.cc_subtitle import CCSubtitleTranscriber
        cc_transcriber = CCSubtitleTranscriber(bvid=bvid)

        if cc_transcriber.has_subtitle():
            print("检测到CC字幕，跳过语音识别")
            logger.info("检测到CC字幕，使用CC字幕")
            srt_path = cc_transcriber.transcribe(video_path, video_dir)
        else:
            print("未检测到CC字幕，使用语音识别")
            logger.info("未检测到CC字幕，使用语音识别")

            from bili_analyzer.transcriber import get_transcriber_chain
            transcriber_chain = get_transcriber_chain(config, bvid)

            transcriber_chain = [
                t for t in transcriber_chain
                if not isinstance(t, CCSubtitleTranscriber)
            ]

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
                    print(f"{transcriber.name} 转录失败: {e}")
                    logger.warning(f"{transcriber.name} 转录失败: {e}")
                    last_error = e
                    continue
            else:
                raise RuntimeError(f"所有转录方式均失败，最后一个错误: {last_error}")

        if not srt_path or not srt_path.exists():
            raise RuntimeError("字幕文件生成失败")

        # 保存字幕完整原文
        _save_transcript(srt_path, video_dir, video_path.stem)

        # ===== 步骤 4: LLM 分析 =====
        _print_step(4, total_steps, "LLM分析字幕内容")

        srt_content = srt_path.read_text(encoding='utf-8')

        from bili_analyzer.analyzer import get_analyzer_chain
        analyzer_chain = get_analyzer_chain(config)

        analysis_result = None
        last_error = None

        for analyzer in analyzer_chain:
            try:
                print(f"尝试使用 {analyzer.name} 分析...")
                logger.info(f"尝试使用 {analyzer.name} 分析")
                analysis_result = analyzer.analyze(video_info_dict, srt_content)
                logger.info(f"{analyzer.name} 分析成功")
                break
            except Exception as e:
                print(f"{analyzer.name} 分析失败: {e}")
                logger.warning(f"{analyzer.name} 分析失败: {e}")
                last_error = e
                continue

        if analysis_result is None:
            raise RuntimeError(f"所有分析方式均失败，最后一个错误: {last_error}")

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

        # ===== 步骤 5: 截取关键画面 =====
        _print_step(5, total_steps, "截取关键画面")

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

        # ===== 步骤 6: 生成报告 =====
        _print_step(6, total_steps, "生成学习笔记")

        report_path = generate_markdown(
            video_info=video_info_dict,
            analysis=analysis_result,
            screenshots=screenshot_mapping,
            srt_content=srt_content,
            output_dir=reports_dir,
        )

        # ===== 步骤 7: 清理视频 =====
        _print_step(7, total_steps, "清理")

        should_keep = config.keep_video or not config.cleanup.auto_delete_video
        _cleanup_video(video_path, should_keep)

        # ===== 完成 =====
        print("\n" + "=" * 60)
        print("分析完成!")
        print("=" * 60)
        print(f"\n报告路径: {report_path}")
        print(f"截图目录: {screenshots_dir}")
        print(f"字幕文件: {srt_path}")
        print(f"字幕原文: {video_dir / f'{video_path.stem}_字幕原文.txt'}")
        if should_keep:
            print(f"视频文件: {video_path}")
        print()
        logger.info(f"分析完成! 报告路径: {report_path}")

    except KeyboardInterrupt:
        print("\n\n用户中断")
        logger.warning("用户中断")
        if video_path and video_path.exists() and config.cleanup.auto_delete_video and not config.keep_video:
            _cleanup_video(video_path, False)
        raise
    except Exception as e:
        print(f"\n\n错误: {e}")
        logger.error(f"运行出错: {e}", exc_info=True)
        if video_path and video_path.exists() and config.cleanup.auto_delete_video and not config.keep_video:
            _cleanup_video(video_path, False)
        raise
