import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Video, Play, Loader2, AlertCircle } from "lucide-react";
import { api, type CreateTaskRequest } from "../services/api";

export function HomePage() {
  const navigate = useNavigate();
  const [videoUrl, setVideoUrl] = useState("");
  const [llmProvider, setLlmProvider] = useState("zhipu");
  const [quality, setQuality] = useState("1080p");
  const [pages, setPages] = useState("");
  const [keepVideo, setKeepVideo] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) {
          setError("后端服务未响应，请确保已运行 start-web.ps1 启动服务");
        }
      })
      .catch(() => {
        setError("无法连接到后端服务，请确保已运行 start-web.ps1 启动服务");
      });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!videoUrl.trim()) {
      setError("请输入视频链接或BV号");
      return;
    }

    setIsSubmitting(true);
    setError("");

    try {
      const req: CreateTaskRequest = {
        video_url: videoUrl.trim(),
        llm_provider: llmProvider,
        quality,
        pages: pages || undefined,
        keep_video: keepVideo,
      };
      const task = await api.tasks.create(req);
      navigate(`/task/${task.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-white mb-3">
          B站视频分析器
        </h1>
        <p className="text-gray-400 text-lg">
          自动提取视频知识点，生成结构化学习笔记
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* 视频链接输入 */}
        <div className="bg-[#18181B] rounded-2xl p-6 border border-[#27272A]">
          <label className="block text-sm font-medium text-gray-300 mb-3">
            <Video className="w-4 h-4 inline mr-2" />
            视频链接或 BV 号
          </label>
          <input
            type="text"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="例如: BV1ms4y1Y76i 或 https://www.bilibili.com/video/BV1ms4y1Y76i"
            className="w-full px-4 py-3 bg-[#27272A] border border-[#3F3F46] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-[#00AEEC] transition-colors"
          />
        </div>

        {/* 配置选项 */}
        <div className="bg-[#18181B] rounded-2xl p-6 border border-[#27272A]">
          <h3 className="text-sm font-medium text-gray-300 mb-4">分析配置</h3>
          <div className="grid grid-cols-2 gap-4">
            {/* LLM 提供商 */}
            <div>
              <label className="block text-xs text-gray-400 mb-2">LLM 提供商</label>
              <select
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
                className="w-full px-3 py-2 bg-[#27272A] border border-[#3F3F46] rounded-lg text-white focus:outline-none focus:border-[#00AEEC]"
              >
                <option value="zhipu">智谱 GLM (免费)</option>
                <option value="deepseek">DeepSeek</option>
                <option value="interactive">交互模式</option>
              </select>
            </div>

            {/* 视频清晰度 */}
            <div>
              <label className="block text-xs text-gray-400 mb-2">视频清晰度</label>
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                className="w-full px-3 py-2 bg-[#27272A] border border-[#3F3F46] rounded-lg text-white focus:outline-none focus:border-[#00AEEC]"
              >
                <option value="1080p">1080p</option>
                <option value="720p">720p</option>
                <option value="480p">480p</option>
                <option value="best">最佳</option>
              </select>
            </div>

            {/* 分P选择 */}
            <div>
              <label className="block text-xs text-gray-400 mb-2">
                分P选择（留空则交互式选择）
              </label>
              <input
                type="text"
                value={pages}
                onChange={(e) => setPages(e.target.value)}
                placeholder="例如: 1,3,5 或 all"
                className="w-full px-3 py-2 bg-[#27272A] border border-[#3F3F46] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-[#00AEEC]"
              />
            </div>

            {/* 保留视频 */}
            <div className="flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={keepVideo}
                  onChange={(e) => setKeepVideo(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-500 text-[#00AEEC] focus:ring-[#00AEEC]"
                />
                <span className="text-sm text-gray-300">分析完成后保留视频文件</span>
              </label>
            </div>
          </div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="flex items-center gap-2 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* 提交按钮 */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full py-4 px-6 bg-[#00AEEC] hover:bg-[#0095D5] disabled:bg-gray-600 text-white font-semibold rounded-xl transition-all flex items-center justify-center gap-2"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              提交中...
            </>
          ) : (
            <>
              <Play className="w-5 h-5" />
              开始分析
            </>
          )}
        </button>
      </form>

      {/* 功能说明 */}
      <div className="mt-10 grid grid-cols-3 gap-4">
        {[
          { title: "智能字幕", desc: "CC字幕优先，语音识别兜底" },
          { title: "LLM 分析", desc: "自动提取知识点和关键画面" },
          { title: "学习笔记", desc: "生成结构化 Markdown 笔记" },
        ].map((item) => (
          <div
            key={item.title}
            className="bg-[#18181B]/50 rounded-xl p-4 border border-[#27272A] text-center"
          >
            <h4 className="text-white font-medium mb-1">{item.title}</h4>
            <p className="text-gray-500 text-sm">{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
