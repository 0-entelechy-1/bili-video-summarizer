"""报告相关 API 路由"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from web.backend.database import get_db
from web.backend.services import task_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportResponse(BaseModel):
    task_id: str
    video_title: Optional[str]
    markdown: str
    screenshots: list
    created_at: Optional[str]


@router.get("/{task_id}", response_model=ReportResponse)
def get_report(task_id: str, db: Session = Depends(get_db)):
    """获取报告内容"""
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not task.report_path:
        raise HTTPException(status_code=404, detail="报告尚未生成")

    report_path = Path(task.report_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")

    markdown = report_path.read_text(encoding="utf-8")

    # 查找截图
    screenshots = []
    if task.output_dir:
        output_dir = Path(task.output_dir)
        # 尝试找到 screenshots 目录
        for screenshots_dir in output_dir.rglob("screenshots"):
            if screenshots_dir.is_dir():
                for img in sorted(screenshots_dir.glob("*.jpg")):
                    screenshots.append(str(img.resolve()))
                break

    return ReportResponse(
        task_id=task.id,
        video_title=task.video_title,
        markdown=markdown,
        screenshots=screenshots,
        created_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.get("/{task_id}/download")
def download_report(task_id: str, db: Session = Depends(get_db)):
    """下载报告文件"""
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not task.report_path:
        raise HTTPException(status_code=404, detail="报告尚未生成")

    report_path = Path(task.report_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")

    content = report_path.read_bytes()
    filename = report_path.name

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
