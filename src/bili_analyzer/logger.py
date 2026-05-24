"""日志模块

每次运行生成一份日志文件，记录完整的运行过程。
日志文件保存在 logs/ 目录下，以时间戳命名。
通过 threading.excepthook 和 sys.excepthook 确保所有异常都被日志捕获。
"""

import logging
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    logger = logging.getLogger("bili_analyzer")
    tb_lines = traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    tb_text = "".join(tb_lines)
    logger.error(f"线程异常 (thread={args.thread.name}):\n{tb_text}")


def _sys_excepthook(exc_type, exc_value, exc_tb):
    if exc_type is SystemExit:
        return
    logger = logging.getLogger("bili_analyzer")
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.error(f"未捕获异常:\n{tb_text}")


def setup_logger(log_dir: str = "", timestamp: str = "") -> logging.Logger:
    if log_dir:
        log_path = Path(log_dir).resolve()
    else:
        log_path = _PROJECT_ROOT / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"bili_analyzer_{timestamp}.log"

    logger = logging.getLogger("bili_analyzer")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    threading.excepthook = _thread_excepthook
    sys.excepthook = _sys_excepthook

    logger.info(f"日志文件: {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"bili_analyzer.{name}")
