import { useEffect, useState } from "react";
import { Loader2, Save, AlertCircle } from "lucide-react";
import { api, type AppConfig } from "../services/api";

export function SettingsPage() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving] = useState(false);
  const [message] = useState("");

  useEffect(() => {
    api.config
      .get()
      .then((c) => {
        setConfig(c);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#00AEEC]" />
      </div>
    );
  }

  if (!config) {
    return (
      <div className="text-center py-20">
        <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
        <h2 className="text-xl text-white mb-2">加载配置失败</h2>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-8">设置</h1>

      {message && (
        <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400">
          {message}
        </div>
      )}

      <div className="space-y-6">
        {/* LLM 配置 */}
        <Section title="LLM 配置">
          <SelectField
            label="默认 LLM 提供商"
            value={config.llm_provider}
            options={[
              { value: "zhipu", label: "智谱 GLM" },
              { value: "deepseek", label: "DeepSeek" },
              { value: "interactive", label: "交互模式" },
            ]}
            onChange={(v) => setConfig({ ...config, llm_provider: v })}
          />
          <InputField
            label="智谱 API Key"
            value={config.zhipu_api_key}
            onChange={(v) => setConfig({ ...config, zhipu_api_key: v })}
            placeholder="从 https://open.bigmodel.cn/ 获取"
            type="password"
          />
          <InputField
            label="智谱模型"
            value={config.zhipu_model}
            onChange={(v) => setConfig({ ...config, zhipu_model: v })}
          />
          <InputField
            label="DeepSeek API Key"
            value={config.deepseek_api_key}
            onChange={(v) => setConfig({ ...config, deepseek_api_key: v })}
            placeholder="从 https://platform.deepseek.com/ 获取"
            type="password"
          />
          <InputField
            label="DeepSeek 模型"
            value={config.deepseek_model}
            onChange={(v) => setConfig({ ...config, deepseek_model: v })}
          />
        </Section>

        {/* 转录配置 */}
        <Section title="转录配置">
          <SelectField
            label="转录方式"
            value={config.transcriber_prefer}
            options={[
              { value: "auto", label: "自动 (CC字幕优先)" },
              { value: "whisper", label: "强制本地 Whisper" },
              { value: "volcengine", label: "强制火山引擎" },
            ]}
            onChange={(v) => setConfig({ ...config, transcriber_prefer: v })}
          />
          <SelectField
            label="Whisper 模型"
            value={config.whisper_model}
            options={[
              { value: "tiny", label: "tiny (最快)" },
              { value: "base", label: "base" },
              { value: "small", label: "small" },
              { value: "medium", label: "medium" },
              { value: "large", label: "large (最准)" },
            ]}
            onChange={(v) => setConfig({ ...config, whisper_model: v })}
          />
          <InputField
            label="火山引擎 Token"
            value={config.volcengine_token}
            onChange={(v) => setConfig({ ...config, volcengine_token: v })}
            type="password"
          />
          <InputField
            label="火山引擎 AppID"
            value={config.volcengine_appid}
            onChange={(v) => setConfig({ ...config, volcengine_appid: v })}
          />
        </Section>

        {/* 下载配置 */}
        <Section title="下载配置">
          <SelectField
            label="视频清晰度"
            value={config.quality}
            options={[
              { value: "1080p", label: "1080p" },
              { value: "720p", label: "720p" },
              { value: "480p", label: "480p" },
              { value: "best", label: "最佳" },
            ]}
            onChange={(v) => setConfig({ ...config, quality: v })}
          />
        </Section>

        {/* 截图配置 */}
        <Section title="截图配置">
          <InputField
            label="关键截图数量"
            value={String(config.screenshot_count)}
            onChange={(v) =>
              setConfig({ ...config, screenshot_count: parseInt(v) || 10 })
            }
            type="number"
          />
          <InputField
            label="JPEG 质量 (1-31, 越小越好)"
            value={String(config.screenshot_quality)}
            onChange={(v) =>
              setConfig({ ...config, screenshot_quality: parseInt(v) || 2 })
            }
            type="number"
          />
        </Section>

        {/* 清理配置 */}
        <Section title="清理配置">
          <div className="flex items-center gap-3 py-2">
            <input
              type="checkbox"
              checked={config.auto_delete_video}
              onChange={(e) =>
                setConfig({ ...config, auto_delete_video: e.target.checked })
              }
              className="w-4 h-4 rounded border-gray-500 text-[#00AEEC]"
            />
            <span className="text-gray-300">分析完成后自动删除视频文件</span>
          </div>
          <div className="flex items-center gap-3 py-2">
            <input
              type="checkbox"
              checked={config.auto_delete_audio}
              onChange={(e) =>
                setConfig({ ...config, auto_delete_audio: e.target.checked })
              }
              className="w-4 h-4 rounded border-gray-500 text-[#00AEEC]"
            />
            <span className="text-gray-300">语音识别完成后自动删除音频文件</span>
          </div>
        </Section>

        {/* B站配置 */}
        <Section title="B站配置">
          <InputField
            label="Cookie (SESSDATA=xxx; bili_jct=yyy)"
            value={config.bilibili_cookie}
            onChange={(v) => setConfig({ ...config, bilibili_cookie: v })}
            placeholder="可选，用于访问部分需要登录的视频"
          />
        </Section>

        {/* 保存按钮 */}
        <div className="pt-4">
          <button
            disabled={saving}
            className="px-6 py-3 bg-[#00AEEC] hover:bg-[#0095D5] disabled:bg-gray-600 text-white font-semibold rounded-xl transition-all flex items-center gap-2"
          >
            {saving ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save className="w-5 h-5" />
                保存配置
              </>
            )}
          </button>
          <p className="text-sm text-gray-500 mt-3">
            注：当前版本为只读展示，修改配置请直接编辑项目根目录下的 config.yaml 文件。
          </p>
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-[#18181B] rounded-2xl p-6 border border-[#27272A]">
      <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function InputField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-2">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 bg-[#27272A] border border-[#3F3F46] rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-[#00AEEC]"
      />
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="block text-sm text-gray-400 mb-2">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 bg-[#27272A] border border-[#3F3F46] rounded-lg text-white focus:outline-none focus:border-[#00AEEC]"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
