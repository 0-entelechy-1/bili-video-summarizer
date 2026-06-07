"""WebSocket 连接管理器

管理每个任务的 WebSocket 连接，负责向客户端推送实时进度消息
"""

from typing import Dict, Set
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    """管理所有 WebSocket 连接，按 task_id 分组"""

    def __init__(self):
        # task_id -> set of active connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        """接受连接并加入 task_id 分组"""
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        logger.debug(f"WebSocket connected for task {task_id}, total connections: {len(self.active_connections[task_id])}")

    def disconnect(self, websocket: WebSocket, task_id: str):
        """移除连接"""
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def broadcast_to_task(self, task_id: str, message: dict):
        """向 task_id 的所有连接广播消息"""
        if task_id not in self.active_connections:
            return

        disconnected = []
        for websocket in self.active_connections[task_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        # 清理断开的连接
        for ws in disconnected:
            self.disconnect(ws, task_id)


# 全局单例
manager = WebSocketManager()
