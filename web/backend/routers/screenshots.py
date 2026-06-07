"""截图静态文件服务"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/screenshots", tags=["screenshots"])


@router.get("")
def get_screenshot(path: str = Query(...)):
    """获取截图文件"""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)
