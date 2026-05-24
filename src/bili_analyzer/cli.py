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
        help="输出目录 (默认: ./outputs)"
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
        "--version", "-v",
        action="version",
        version="%(prog)s 1.0.0"
    )

    return parser


def main():
    """CLI 主入口"""
    parser = create_parser()
    args = parser.parse_args()

    # 扫码登录模式
    if args.login:
        from bili_analyzer.api.auth import perform_login
        perform_login()
        sys.exit(0)

    # 检查 video_url 是否提供
    if not args.video_url:
        parser.print_help()
        print("\n错误: 必须提供视频链接或BV号")
        sys.exit(1)

    # 加载配置
    try:
        config = load_config(args.config_path)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)

    # 命令行参数覆盖
    config = apply_cli_overrides(
        config,
        video_url=args.video_url,
        output_dir=args.output_dir,
        llm_provider=args.llm_provider,
        keep_video=args.keep_video,
        page=args.page,
        cookie=args.cookie,
    )

    # 生成统一的时间戳
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 初始化日志（传入时间戳）
    setup_logger(timestamp=run_timestamp)

    # 执行分析流程（传入时间戳）
    try:
        run_pipeline(config, timestamp=run_timestamp)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
