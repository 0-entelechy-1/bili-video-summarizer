"""FastAPI 应用主入口"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from web.backend.database import init_db
from web.backend.routers import tasks, reports, config, screenshots
from web.backend.websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    init_db()
    logger.info("数据库初始化完成")
    yield
    # 关闭时清理
    logger.info("应用关闭")


app = FastAPI(
    title="B站视频分析器 Web API",
    description="为 B站视频分析器提供 Web 界面 API 服务",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(tasks.router)
app.include_router(reports.router)
app.include_router(config.router)
app.include_router(screenshots.router)


@app.get("/api/health")
def health_check():
    """健康检查"""
    return {"status": "ok"}


@app.websocket("/ws/tasks/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str):
    """任务进度 WebSocket 连接"""
    await manager.connect(websocket, task_id)
    try:
        while True:
            # 保持连接，接收心跳或关闭信号
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)
    except Exception:
        manager.disconnect(websocket, task_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
