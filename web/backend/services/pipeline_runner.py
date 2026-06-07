"""Pipeline 运行器

将现有的 CLI pipeline 封装为可在 Web 后端异步调用的接口，
并通过 WebSocket 推送实时进度。
"""

import asyncio
import io
import logging
import sys
import threading
import time
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from bili_analyzer.config import load_config, apply_cli_overrides, AppConfig
from bili_analyzer.pipeline import run_pipeline
from bili_analyzer.api.bilibili import extract_bvid, get_video_info
from web.backend.database import SessionLocal
from web.backend.services import task_service
from web.backend.websocket_manager import manager

logger = logging.getLogger(__name__)


class PipelineProgressHandler(logging.Handler):
    """自定义日志处理器，将日志转为 WebSocket 消息"""

    def __init__(self, task_id: str, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.task_id = task_id
        self.loop = loop
        self.step_names = {
            1: "获取视频信息",
            2: "下载视频",
            3: "获取字幕",
            4: "LLM分析字幕内容",
            5: "截取关键画面",
            6: "生成学习笔记",
            7: "清理",
        }

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            # 解析步骤信息
            step = None
            step_name = None
            for s, name in self.step_names.items():
                if f"步骤 {s}/" in msg or f"步骤{s}/" in msg:
                    step = s
                    step_name = name
                    break
                if name in msg:
                    step = s
                    step_name = name

            # 构建消息
            message = {
                "type": "log",
                "level": record.levelname.lower(),
                "message": msg,
                "timestamp": datetime.utcnow().isoformat(),
            }
            if step is not None:
                message["step"] = step
                message["step_name"] = step_name

            # 使用 run_coroutine_threadsafe 在主线程事件循环中发送
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_to_task(self.task_id, message),
                self.loop
            )
        except Exception:
            pass


class PrintCapture:
    """捕获 print 输出并转为 WebSocket 消息"""

    def __init__(self, task_id: str, loop: asyncio.AbstractEventLoop):
        self.task_id = task_id
        self.loop = loop
        self.buffer = ""
        self.step_names = {
            1: "获取视频信息",
            2: "下载视频",
            3: "获取字幕",
            4: "LLM分析字幕内容",
            5: "截取关键画面",
            6: "生成学习笔记",
            7: "清理",
        }

    def write(self, text: str):
        self.buffer += text
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            self.buffer = lines[-1]  # 保留未完成的行
            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                self._send_line(line)

    def _send_line(self, line: str):
        step = None
        step_name = None
        msg_type = "log"

        # 解析步骤
        for s, name in self.step_names.items():
            if f"[步骤 {s}/" in line or f"[步骤{s}/" in line:
                step = s
                step_name = name
                msg_type = "step_start"
                break
            if name in line and ("开始" in line or "耗时" in line):
                step = s
                step_name = name

        # 解析步骤完成
        if "步骤耗时" in line or "耗时:" in line:
            msg_type = "step_progress"

        message = {
            "type": msg_type,
            "level": "info",
            "message": line,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if step is not None:
            message["step"] = step
            message["step_name"] = step_name

        asyncio.run_coroutine_threadsafe(
            manager.broadcast_to_task(self.task_id, message),
            self.loop
        )

    def flush(self):
        if self.buffer.strip():
            self._send_line(self.buffer.strip())
            self.buffer = ""


def _run_pipeline_sync(
    task_id: str,
    video_url: str,
    llm_provider: Optional[str],
    quality: Optional[str],
    keep_video: bool,
    pages: Optional[str],
    loop: asyncio.AbstractEventLoop,
):
    """同步运行 pipeline（在后台线程中执行）"""
    db = SessionLocal()
    try:
        # 更新状态为运行中
        task_service.update_task_status(db, task_id, status="running")

        # 设置日志捕获
        log_handler = PipelineProgressHandler(task_id, loop)
        log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(message)s")
        log_handler.setFormatter(formatter)
        root_logger = logging.getLogger("bili_analyzer")
        root_logger.addHandler(log_handler)

        # 加载配置
        config = load_config()
        config = apply_cli_overrides(
            config,
            video_url=video_url,
            llm_provider=llm_provider,
            keep_video=keep_video,
            quality=quality,
            page=pages,
        )

        # 捕获 print 输出
        print_capture = PrintCapture(task_id, loop)
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = print_capture
        sys.stderr = print_capture

        try:
            # 获取视频信息用于更新任务标题
            try:
                bvid = extract_bvid(video_url)
                video_info = get_video_info(bvid)
                task_service.update_task_status(
                    db, task_id,
                    video_title=video_info.title,
                    bvid=bvid,
                )
            except Exception:
                pass

            # 运行分析流程
            run_pipeline(config)

            # 查找生成的报告文件
            output_dir = Path(config.output_dir)
            reports_dir = output_dir / "reports"
            report_files = list(reports_dir.glob("*_学习笔记.md"))
            report_path = str(report_files[0]) if report_files else None

            # 更新完成状态
            task_service.update_task_status(
                db, task_id,
                status="completed",
                current_step=7,
                progress=100,
                step_name="完成",
                report_path=report_path,
                output_dir=str(output_dir),
            )

            # 发送完成消息
            try:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast_to_task(task_id, {
                        "type": "task_complete",
                        "result": {
                            "report_path": report_path,
                            "output_dir": str(output_dir),
                        },
                    }),
                    loop
                )
            except Exception:
                pass

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Pipeline 运行失败: {error_msg}", exc_info=True)
            task_service.update_task_status(
                db, task_id,
                status="failed",
                error_message=error_msg,
            )
            try:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast_to_task(task_id, {
                        "type": "task_failed",
                        "error": error_msg,
                    }),
                    loop
                )
            except Exception:
                pass
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            root_logger.removeHandler(log_handler)
            print_capture.flush()

    finally:
        db.close()


async def run_pipeline_async(
    task_id: str,
    video_url: str,
    llm_provider: Optional[str] = None,
    quality: Optional[str] = None,
    keep_video: bool = False,
    pages: Optional[str] = None,
):
    """异步运行 pipeline（在后台线程中执行同步代码）"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _run_pipeline_sync,
        task_id,
        video_url,
        llm_provider,
        quality,
        keep_video,
        pages,
        loop,
    )
