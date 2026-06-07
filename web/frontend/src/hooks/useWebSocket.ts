import { useEffect, useRef, useState, useCallback } from "react";

export interface WSMessage {
  type: string;
  step?: number;
  step_name?: string;
  progress?: number;
  message?: string;
  level?: string;
  error?: string;
  result?: Record<string, unknown>;
  timestamp?: string;
}

export function useWebSocket(taskId: string | null) {
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) return;

    const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/tasks/${taskId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSMessage;
        setMessages((prev) => [...prev, data]);
      } catch {
        // ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    // 心跳
    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send("ping");
      }
    }, 30000);

    return () => {
      clearInterval(interval);
      ws.close();
    };
  }, [taskId]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return { messages, isConnected, clearMessages };
}
