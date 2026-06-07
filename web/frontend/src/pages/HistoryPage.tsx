import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Trash2,
  FileText,
  Loader2,
  Clock,
  ExternalLink,
} from "lucide-react";
import { api, type Task } from "../services/api";

export function HistoryPage() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");

  const loadTasks = async () => {
    try {
      const res = await api.tasks.list(filter || undefined);
      setTasks(res.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 5000);
    return () => clearInterval(interval);
  }, [filter]);

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除这个任务吗？")) return;
    try {
      await api.tasks.delete(id);
      setTasks((prev) => prev.filter((t) => t.id !== id));
    } catch {
      alert("删除失败");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#00AEEC]" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-white">历史记录</h1>
        <div className="flex items-center gap-3">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="px-3 py-2 bg-[#18181B] border border-[#27272A] rounded-lg text-white text-sm focus:outline-none focus:border-[#00AEEC]"
          >
            <option value="">全部状态</option>
            <option value="pending">等待中</option>
            <option value="running">分析中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
          </select>
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className="text-center py-20 bg-[#18181B] rounded-2xl border border-[#27272A]">
          <Clock className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h2 className="text-xl text-white mb-2">暂无任务</h2>
          <p className="text-gray-500 mb-6">还没有分析过任何视频</p>
          <button
            onClick={() => navigate("/")}
            className="px-6 py-2 bg-[#00AEEC] hover:bg-[#0095D5] text-white rounded-lg transition-colors"
          >
            开始分析
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <div
              key={task.id}
              className="bg-[#18181B] rounded-xl p-5 border border-[#27272A] hover:border-[#3F3F46] transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-white font-medium truncate">
                      {task.video_title || task.video_url}
                    </h3>
                    <StatusBadge status={task.status} />
                  </div>
                  <div className="flex items-center gap-4 text-sm text-gray-500">
                    <span>{task.video_url}</span>
                    {task.bvid && (
                      <span className="px-2 py-0.5 bg-[#27272A] rounded text-xs">
                        {task.bvid}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                    <span>LLM: {task.llm_provider || "默认"}</span>
                    <span>画质: {task.quality || "默认"}</span>
                    <span>
                      {task.created_at
                        ? new Date(task.created_at).toLocaleString("zh-CN")
                        : ""}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 ml-4">
                  {task.status === "running" && (
                    <button
                      onClick={() => navigate(`/task/${task.id}`)}
                      className="p-2 rounded-lg bg-[#00AEEC]/10 text-[#00AEEC] hover:bg-[#00AEEC]/20 transition-colors"
                      title="查看进度"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </button>
                  )}

                  {task.status === "completed" && (
                    <>
                      <button
                        onClick={() => navigate(`/report/${task.id}`)}
                        className="p-2 rounded-lg bg-[#00AEEC]/10 text-[#00AEEC] hover:bg-[#00AEEC]/20 transition-colors"
                        title="查看报告"
                      >
                        <FileText className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => api.reports.download(task.id)}
                        className="p-2 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
                        title="下载报告"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </button>
                    </>
                  )}

                  <button
                    onClick={() => handleDelete(task.id)}
                    className="p-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                    title="删除任务"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
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
      className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
        styles[status] || styles.pending
      }`}
    >
      {labels[status] || status}
    </span>
  );
}
