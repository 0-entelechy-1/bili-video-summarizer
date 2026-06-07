import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Image, Loader2, XCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type Report } from "../services/api";

export function ReportPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    api.reports
      .get(taskId)
      .then((r) => {
        setReport(r);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [taskId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#00AEEC]" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="text-center py-20">
        <XCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
        <h2 className="text-xl text-white mb-2">报告不存在</h2>
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
    <div className="max-w-5xl mx-auto">
      {/* 头部 */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate("/history")}
            className="p-2 rounded-lg bg-[#18181B] hover:bg-[#27272A] text-gray-400 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white">
              {report.video_title || "学习笔记"}
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              {report.created_at}
            </p>
          </div>
        </div>
        <button
          onClick={() => taskId && api.reports.download(taskId)}
          className="px-4 py-2 bg-[#00AEEC] hover:bg-[#0095D5] text-white rounded-lg transition-colors flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          下载 Markdown
        </button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* 左侧：Markdown 内容 */}
        <div className="col-span-2">
          <div className="bg-[#18181B] rounded-2xl p-8 border border-[#27272A]">
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {report.markdown}
              </ReactMarkdown>
            </div>
          </div>
        </div>

        {/* 右侧：截图画廊 */}
        <div className="col-span-1">
          <div className="bg-[#18181B] rounded-2xl p-4 border border-[#27272A] sticky top-8">
            <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
              <Image className="w-5 h-5" />
              关键截图
            </h3>
            {report.screenshots.length === 0 ? (
              <p className="text-gray-500 text-sm">暂无截图</p>
            ) : (
              <div className="space-y-3">
                {report.screenshots.map((path, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSelectedImage(path)}
                    className="w-full aspect-video rounded-lg overflow-hidden border border-[#27272A] hover:border-[#00AEEC] transition-colors"
                  >
                    <img
                      src={`/api/screenshots?path=${encodeURIComponent(path)}`}
                      alt={`截图 ${idx + 1}`}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 图片预览弹窗 */}
      {selectedImage && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-8"
          onClick={() => setSelectedImage(null)}
        >
          <img
            src={`/api/screenshots?path=${encodeURIComponent(selectedImage)}`}
            alt="预览"
            className="max-w-full max-h-full rounded-lg"
          />
        </div>
      )}
    </div>
  );
}
