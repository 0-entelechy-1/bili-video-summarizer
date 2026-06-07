import { Link, useLocation } from "react-router-dom";
import {
  Home,
  History,
  Settings,
  PlayCircle,
} from "lucide-react";

const navItems = [
  { path: "/", label: "新建任务", icon: Home },
  { path: "/history", label: "历史记录", icon: History },
  { path: "/settings", label: "设置", icon: Settings },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  return (
    <div className="flex min-h-screen">
      {/* 侧边栏 */}
      <aside className="w-64 bg-[#18181B] border-r border-[#27272A] flex flex-col fixed h-full">
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#00AEEC] flex items-center justify-center">
            <PlayCircle className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">B站视频分析器</h1>
            <p className="text-xs text-gray-400">Web 界面</p>
          </div>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                  isActive
                    ? "bg-[#00AEEC]/10 text-[#00AEEC]"
                    : "text-gray-400 hover:bg-[#27272A] hover:text-white"
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-[#27272A]">
          <div className="text-xs text-gray-500 text-center">
            v1.0.0 · 自动提取知识点
          </div>
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 ml-64 p-8">
        {children}
      </main>
    </div>
  );
}
