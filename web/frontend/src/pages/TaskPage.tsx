import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CheckCircle, XCircle, ArrowLeft, FileText, Loader2 } from "lucide-react";
import { api, type Task } from "../services/api";
import { useWebSocket } from "../hooks/useWebSocket";

const STEP_NAMES = [
  "准备",
  "获取视频信息",
  "下载视频",
  "获取字幕",
  "LLM分析字幕内容",
  "截取关键画面",
  "生成学习笔记",
  "清理",
];

export function TaskPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const { messages, isConnected } = useWebSocket(taskId || null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!taskId) return;
    api.tasks.get(taskId).then((t) => {
      setTask(t);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [taskId]);

  // 定期刷新任务状态
  useEffect(() => {
    if (!taskId || !task) return;
    if (task.status === "completed" || task.status === "failed") return;

    const interval = setInterval(() => {
      api.tasks.get(taskId).then(setTask).catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [taskId, task]);

  // 自动滚动日志
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#00AEEC]" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="text-center py-20">
        <XCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
        <h2 className="text-xl text-white mb-2">任务不存在</h2>
        <button
          onClick={() => navigate("/")}
          className="text-[#00AEEC] hover:underline"
        >
          返回首页
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* 头部 */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={() => navigate("/")}
          className="p-2 rounded-lg bg-[#18181B] hover:bg-[#27272A] text-gray-400 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-white">
            {task.video_title || task.video_url}
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <StatusBadge status={task.status} />
            <span className="text-sm text-gray-500">
              {isConnected ? (
                <span className="text-green-400">● 实时连接中</span>
              ) : (
                <span className="text-gray-500">○ 未连接</span>
              )}
            </span>
          </div>
        </div>
      </div>

      {/* 步骤进度 */}
      <div className="bg-[#18181B] rounded-2xl p-6 border border-[#27272A] mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">分析进度</h2>
        <div className="space-y-3">
          {STEP_NAMES.slice(1).map((name, idx) => {
            const step = idx + 1;
            const isActive = task.current_step === step;
            const isCompleted = task.current_step > step || task.status === "completed";
            const isFailed = task.status === "failed" && isActive;

            return (
              <div
                key={step}
                className={`flex items-center gap-4 p-3 rounded-lg transition-all ${
                  isActive
                    ? "bg-[#00AEEC]/10 border border-[#00AEEC]/30"
                    : isCompleted
                    ? "bg-[#27272A]/50"
                    : "bg-transparent opacity-50"
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                    isCompleted
                      ? "bg-green-500 text-white"
                      : isActive
                      ? isFailed
                        ? "bg-red-500 text-white"
                        : "bg-[#00AEEC] text-white"
                      : "bg-[#3F3F46] text-gray-400"
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircle className="w-5 h-5" />
                  ) : isFailed ? (
                    <XCircle className="w-5 h-5" />
                  ) : (
                    step
                  )}
                </div>
                <div className="flex-1">
                  <div className="text-white font-medium">{name}</div>
                  {isActive && task.step_name && (
                    <div className="text-sm text-[#00AEEC]">{task.step_name}</div>
                  )}
                </div>
                {isActive && task.status === "running" && (
                  <Loader2 className="w-5 h-5 animate-spin text-[#00AEEC]" />
                )}
              </div>
            );
          })}
        </div>

        {/* 进度条 */}
        <div className="mt-4">
          <div className="h-2 bg-[#27272A] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                task.status === "failed" ? "bg-red-500" : "bg-[#00AEEC]"
              }`}
              style={{
                width: `${task.status === "completed" ? 100 : task.progress}%`,
              }}
            />
          </div>
          <div className="text-right text-sm text-gray-400 mt-1">
            {task.status === "completed"
              ? "100%"
              : `${task.progress}%`}
          </div>
        </div>
      </div>

      {/* 错误信息 */}
      {task.error_message && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 text-red-400 mb-2">
            <XCircle className="w-5 h-5" />
            <span className="font-medium">分析失败</span>
          </div>
          <p className="text-red-300 text-sm">{task.error_message}</p>
        </div>
      )}

      {/* 实时日志 */}
      <div className="bg-[#18181B] rounded-2xl border border-[#27272A] mb-6">
        <div className="px-6 py-4 border-b border-[#27272A] flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">实时日志</h2>
          <span className="text-xs text-gray-500 font-mono">
            {messages.length} 条消息
          </span>
        </div>
        <div className="terminal-log">
          {messages.length === 0 ? (
            <div className="text-gray-500 text-center py-8">等待任务开始...</div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={idx}
                className={`log-line ${
                  msg.type === "step_start"
                    ? "step"
                    : msg.level || "info"
                }`}
              >
                {msg.message}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* 完成后的操作 */}
      {task.status === "completed" && (
        <div className="flex gap-4">
          <button
            onClick={() => navigate(`/report/${task.id}`)}
            className="flex-1 py-3 px-6 bg-[#00AEEC] hover:bg-[#0095D5] text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2"
          >
            <FileText className="w-5 h-5" />
            查看学习笔记
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
    running: "bg-[#00AEEC]/10 text-[#00AEEC] border-[#00AEEC]/30",
    completed: "bg-green-500/10 text-green-400 border-green-500/30",
    failed: "bg-red-500/10 text-red-400 border-red-500/30",
  };

  const labels: Record<string, string> = {
    pending: "等待中",
    running: "分析中",
    completed: "已完成",
    failed: "失败",
  };

  return (
    <span
      className={`px-3 py-1 rounded-full text-sm font-medium border ${
        styles[status] || styles.pending
      }`}
    >
      {labels[status] || status}
    </span>
  );
}
