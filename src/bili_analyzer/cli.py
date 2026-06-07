"""命令行接口"""

import argparse
import sys
from datetime import datetime

from bili_analyzer.config import load_config, apply_cli_overrides
from bili_analyzer.logger import setup_logger
from bili_analyzer.pipeline import run_pipeline


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="bili-analyzer",
        description="B站视频分析器 - 自动提取知识点并生成学习笔记",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  bili-analyzer BV1ms4y1Y76i
  bili-analyzer https://www.bilibili.com/video/BV1ms4y1Y76i
  bili-analyzer BV1ms4y1Y76i --output ./my_outputs
  bili-analyzer BV1ms4y1Y76i --llm zhipu
  bili-analyzer BV1ms4y1Y76i --keep-video
        """
    )

    parser.add_argument(
        "video_url",
        nargs="?",
        default=None,
        help="B站视频链接或BV号 (使用 --login 时不需要)"
    )

    parser.add_argument(
        "--output", "-o",
        dest="output_dir",
        default=None,
        help="输出目录 (默认: 项目根目录下的 outputs 文件夹)"
    )

    parser.add_argument(
        "--llm",
        dest="llm_provider",
        choices=["zhipu", "deepseek", "interactive"],
        default=None,
        help="LLM 提供商 (默认: 使用配置文件设置)"
    )

    parser.add_argument(
        "--keep-video",
        action="store_true",
        default=False,
        help="分析完成后保留视频文件 (覆盖配置文件设置)"
    )

    parser.add_argument(
        "--quality", "-q",
        dest="quality",
        choices=["1080p", "720p", "480p", "best"],
        default=None,
        help="视频下载清晰度 (默认: 使用配置文件设置)"
    )

    parser.add_argument(
        "--model", "-m",
        dest="whisper_model",
        choices=["tiny", "base", "small", "medium"],
        default=None,
        help="Whisper 语音识别模型: tiny/base/small/medium (默认: medium)"
    )

    parser.add_argument(
        "--page",
        dest="page",
        default=None,
        help="选择要分析的分P: 数字(如2)、all(全部)、不提供则交互式选择"
    )

    parser.add_argument(
        "--cookie",
        dest="cookie",
        default=None,
        help="B站 Cookie (如 SESSDATA=xxx; bili_jct=yyy)"
    )

    parser.add_argument(
        "--login",
        action="store_true",
        default=False,
        help="扫码登录 B站并保存凭证"
    )

    parser.add_argument(
        "--config", "-c",
        dest="config_path",
        default=None,
        help="配置文件路径 (默认: 自动搜索 config.yaml)"
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="禁用终端颜色（用于管道/重定向/CI 环境）"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 1.0.0"
    )

    return parser


def main():
    """CLI 主入口"""
    # --no-color 必须在导入 bili_analyzer 之前处理（关闭 Rich 颜色）
    # 局部导入 ui.console 以便设置 NO_COLOR 环境变量
    from bili_analyzer.ui.console import is_no_color
    is_no_color()

    parser = create_parser()
    args = parser.parse_args()

    from bili_analyzer.ui.console import (
        console,
        print_error,
        print_warning,
    )

    # 扫码登录模式
    if args.login:
        from bili_analyzer.api.auth import perform_login
        perform_login()
        sys.exit(0)

    # 检查 video_url 是否提供
    if not args.video_url:
        parser.print_help()
        print_error("必须提供视频链接或BV号")
        sys.exit(1)

    # 加载配置
    try:
        config = load_config(args.config_path)
    except FileNotFoundError as e:
        print_error(f"配置文件加载失败: {e}")
        sys.exit(1)

    # 命令行参数覆盖
    config = apply_cli_overrides(
        config,
        video_url=args.video_url,
        output_dir=args.output_dir,
        llm_provider=args.llm_provider,
        keep_video=args.keep_video,
        quality=args.quality,
        page=args.page,
        cookie=args.cookie,
        whisper_model=args.whisper_model,
    )

    # 生成统一的时间戳
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 初始化日志（传入时间戳）
    setup_logger(timestamp=run_timestamp)

    # 执行分析流程（传入时间戳）
    try:
        run_pipeline(config, timestamp=run_timestamp)
    except KeyboardInterrupt:
        print_warning("用户中断")
        sys.exit(1)
    except Exception as e:
        # 用 Rich 高亮 traceback（pipeline.py 内部已经 print_exception 过一次，
        # 这里只打印精简版最终错误信息，避免重复堆栈）
        console.print(f"  [bold red]✖ 顶层错误:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
