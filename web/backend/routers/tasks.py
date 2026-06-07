"""任务相关 API 路由"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from web.backend.database import get_db
from web.backend.services import task_service
from web.backend.services.pipeline_runner import run_pipeline_async

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    video_url: str
    pages: Optional[str] = None
    llm_provider: Optional[str] = None
    quality: Optional[str] = None
    keep_video: bool = False


class TaskResponse(BaseModel):
    id: str
    video_url: str
    video_title: Optional[str]
    bvid: Optional[str]
    status: str
    current_step: int
    total_steps: int
    step_name: Optional[str]
    progress: int
    error_message: Optional[str]
    report_path: Optional[str]
    llm_provider: Optional[str]
    quality: Optional[str]
    keep_video: int
    pages: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int


@router.post("", response_model=TaskResponse)
async def create_task(
    req: CreateTaskRequest,
    db: Session = Depends(get_db),
):
    """创建新分析任务"""
    task = task_service.create_task(
        db,
        video_url=req.video_url,
        llm_provider=req.llm_provider,
        quality=req.quality,
        keep_video=req.keep_video,
        pages=req.pages,
    )

    # 启动后台任务
    import asyncio
    asyncio.create_task(run_pipeline_async(
        task_id=task.id,
        video_url=req.video_url,
        llm_provider=req.llm_provider,
        quality=req.quality,
        keep_video=req.keep_video,
        pages=req.pages,
    ))

    return _task_to_response(task)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """获取任务列表"""
    tasks = task_service.get_tasks(db, status=status, limit=limit, offset=offset)
    return TaskListResponse(
        items=[_task_to_response(t) for t in tasks],
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    """获取单个任务详情"""
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_to_response(task)


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    """删除任务"""
    success = task_service.delete_task(db, task_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": "任务已删除"}


def _task_to_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        video_url=task.video_url,
        video_title=task.video_title,
        bvid=task.bvid,
        status=task.status,
        current_step=task.current_step,
        total_steps=task.total_steps,
        step_name=task.step_name,
        progress=task.progress,
        error_message=task.error_message,
        report_path=task.report_path,
        llm_provider=task.llm_provider,
        quality=task.quality,
        keep_video=task.keep_video,
        pages=task.pages,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )
