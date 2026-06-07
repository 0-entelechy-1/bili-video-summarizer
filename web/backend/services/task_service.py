"""任务管理服务

封装数据库操作和任务生命周期管理
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from web.backend.models import Task, TaskLog

logger = logging.getLogger(__name__)


def create_task(
    db: Session,
    video_url: str,
    llm_provider: Optional[str] = None,
    quality: Optional[str] = None,
    keep_video: bool = False,
    pages: Optional[str] = None,
) -> Task:
    """创建新任务"""
    task = Task(
        video_url=video_url,
        llm_provider=llm_provider,
        quality=quality,
        keep_video=1 if keep_video else 0,
        pages=pages,
        status="pending",
        current_step=0,
        progress=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: str) -> Optional[Task]:
    """获取单个任务"""
    return db.query(Task).filter(Task.id == task_id).first()


def get_tasks(
    db: Session,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Task]:
    """获取任务列表"""
    query = db.query(Task)
    if status:
        query = query.filter(Task.status == status)
    return query.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()


def update_task_status(
    db: Session,
    task_id: str,
    status: Optional[str] = None,
    current_step: Optional[int] = None,
    step_name: Optional[str] = None,
    progress: Optional[int] = None,
    error_message: Optional[str] = None,
    report_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    video_title: Optional[str] = None,
    bvid: Optional[str] = None,
) -> Optional[Task]:
    """更新任务状态"""
    task = get_task(db, task_id)
    if not task:
        return None

    if status is not None:
        task.status = status
        if status in ("completed", "failed"):
            task.completed_at = datetime.utcnow()
    if current_step is not None:
        task.current_step = current_step
    if step_name is not None:
        task.step_name = step_name
    if progress is not None:
        task.progress = progress
    if error_message is not None:
        task.error_message = error_message
    if report_path is not None:
        task.report_path = report_path
    if output_dir is not None:
        task.output_dir = output_dir
    if video_title is not None:
        task.video_title = video_title
    if bvid is not None:
        task.bvid = bvid

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


def add_task_log(
    db: Session,
    task_id: str,
    message: str,
    step: Optional[int] = None,
    level: str = "info",
) -> TaskLog:
    """添加任务日志"""
    log = TaskLog(
        task_id=task_id,
        step=step,
        level=level,
        message=message,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_task_logs(db: Session, task_id: str) -> List[TaskLog]:
    """获取任务的所有日志"""
    return (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task_id)
        .order_by(TaskLog.created_at.asc())
        .all()
    )


def delete_task(db: Session, task_id: str) -> bool:
    """删除任务及其日志"""
    task = get_task(db, task_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True
