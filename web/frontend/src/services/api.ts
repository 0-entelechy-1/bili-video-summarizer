const API_BASE = "/api";

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("后端服务未启动或API路径错误，请确保已运行 start-web.ps1 启动服务");
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export interface CreateTaskRequest {
  video_url: string;
  pages?: string;
  llm_provider?: string;
  quality?: string;
  keep_video?: boolean;
}

export interface Task {
  id: string;
  video_url: string;
  video_title?: string;
  bvid?: string;
  status: string;
  current_step: number;
  total_steps: number;
  step_name?: string;
  progress: number;
  error_message?: string;
  report_path?: string;
  llm_provider?: string;
  quality?: string;
  keep_video: number;
  pages?: string;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
}

export interface TaskList {
  items: Task[];
  total: number;
}

export interface Report {
  task_id: string;
  video_title?: string;
  markdown: string;
  screenshots: string[];
  created_at?: string;
}

export interface AppConfig {
  llm_provider: string;
  zhipu_api_key: string;
  zhipu_model: string;
  deepseek_api_key: string;
  deepseek_model: string;
  transcriber_prefer: string;
  whisper_model: string;
  volcengine_token: string;
  volcengine_appid: string;
  auto_delete_video: boolean;
  auto_delete_audio: boolean;
  quality: string;
  screenshot_count: number;
  screenshot_quality: number;
  bilibili_cookie: string;
}

export const api = {
  tasks: {
    create: (req: CreateTaskRequest) =>
      fetchJson<Task>(`${API_BASE}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }),
    list: (status?: string) =>
      fetchJson<TaskList>(
        `${API_BASE}/tasks${status ? `?status=${status}` : ""}`
      ),
    get: (id: string) => fetchJson<Task>(`${API_BASE}/tasks/${id}`),
    delete: (id: string) =>
      fetch(`${API_BASE}/tasks/${id}`, { method: "DELETE" }),
  },
  reports: {
    get: (taskId: string) => fetchJson<Report>(`${API_BASE}/reports/${taskId}`),
    download: (taskId: string) =>
      window.open(`${API_BASE}/reports/${taskId}/download`, "_blank"),
  },
  config: {
    get: () => fetchJson<AppConfig>(`${API_BASE}/config`),
  },
};
