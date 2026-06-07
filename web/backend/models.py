"""SQLAlchemy 数据模型"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from web.backend.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    video_url = Column(String(500), nullable=False)
    video_title = Column(String(200), nullable=True)
    bvid = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, default=7)
    step_name = Column(String(100), nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    report_path = Column(String(500), nullable=True)
    output_dir = Column(String(500), nullable=True)
    llm_provider = Column(String(20), nullable=True)
    quality = Column(String(10), nullable=True)
    keep_video = Column(Integer, default=0)
    pages = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    step = Column(Integer, nullable=True)
    level = Column(String(10), default="info")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="logs")
