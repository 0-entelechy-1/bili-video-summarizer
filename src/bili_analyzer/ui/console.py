"""共享 Rich UI 原语

提供：
- console: 全局 Rich Console 实例
- print_banner / print_step_header / print_step_elapsed
- print_warning / print_error / print_success / print_info
- print_exception: 带语法高亮的 traceback
- spinner: 旋转 spinner 上下文管理器（用于无法解析进度的长任务）
- make_progress: Rich Progress 工厂
- print_summary_table: 任务结束汇总表格
- print_video_card / print_config_summary / print_markdown_preview / print_output_tree
- check_conda_env: 检测是否在 conda AI 环境
- is_no_color: 解析 --no-color 参数
- format_elapsed: 耗时格式化（被各模块复用）
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, List, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

if TYPE_CHECKING:
    from bili_analyzer.api.bilibili import PageInfo, VideoInfo
    from bili_analyzer.config import AppConfig

# 全局 console：自动检测 TTY；非 TTY 退化为纯文本
# stderr=True 让 console 输出与 logging 走同一通道，避免进度条与日志相互覆盖
console = Console(stderr=True)


# ---------- 耗时格式化 ----------

def format_elapsed(seconds: float) -> str:
    """把秒数格式化为'X分Y秒'或'Y秒'，统一全项目的时间显示风格。"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


# ---------- 横幅 / 步骤标题 ----------

def print_banner(version: str = "1.0.0") -> None:
    """彩色启动横幅。"""
    title = Text()
    title.append("🎬  ", style="bold magenta")
    title.append(f"B站视频分析器  ", style="bold cyan")
    title.append(f"v{version}", style="dim cyan")
    title.append("\n")
    title.append("    自动提取知识点 · 生成学习报告", style="green")

    panel = Panel(
        title,
        border_style="bright_magenta",
        padding=(1, 4),
        expand=False,
    )
    console.print(panel)
    console.print()


_STEP_ICONS = ["📋", "⬇️", "📝", "🤖", "🖼️", "📄", "🧹"]


def print_step_header(step: int, total: int, title: str) -> None:
    """步骤标题：`━━━ 步骤 1/7 ━━━ 📋 获取视频信息`。"""
    icon = _STEP_ICONS[step - 1] if 1 <= step <= len(_STEP_ICONS) else "▶"
    header = Text()
    header.append(f"━━━ 步骤 {step}/{total} ", style="bold bright_blue")
    header.append("━━━ ", style="bold bright_blue")
    header.append(f"{icon}  {title}", style="bold")

    console.print()
    console.print(header)
    console.print("─" * min(60, console.width or 60), style="dim")


def print_step_elapsed(seconds: float) -> None:
    """步骤耗时：`⏱  步骤耗时: 5分23秒`。"""
    console.print(f"  [dim]⏱  步骤耗时:[/] [cyan]{format_elapsed(seconds)}[/]")


# ---------- 信息输出 ----------

def print_info(msg: str) -> None:
    console.print(f"  [cyan]ℹ[/]  {msg}")


def print_warning(msg: str) -> None:
    console.print(f"  [yellow]⚠[/]  {msg}")


def print_error(msg: str) -> None:
    console.print(f"  [bold red]✖[/]  {msg}")


def print_success(msg: str) -> None:
    console.print(f"  [bold green]✔[/]  {msg}")


def print_exception(show_locals: bool = False) -> None:
    """带语法高亮的异常 traceback。"""
    console.print_exception(show_locals=show_locals)


# ---------- Spinner 上下文管理器 ----------

@contextmanager
def spinner(text: str) -> Iterator[Spinner]:
    """旋转 spinner 上下文管理器。

    用法:
        with spinner("加载模型中…") as sp:
            do_slow_thing()
            sp.update("正在处理结果…")
            do_more()
    """
    status = console.status(f"[bold cyan]{text}[/]", spinner="dots")
    status.__enter__()
    try:
        yield status
    finally:
        status.__exit__(None, None, None)


# ---------- Rich Progress 工厂 ----------

def make_progress() -> Progress:
    """生成统一的 Rich Progress 实例（用于截图批量、字幕下载等）。"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>5.1f}%",
        "•",
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


def make_download_progress() -> Progress:
    """为 yt-dlp 视频/字幕下载专用的 Progress（含已下载量/速度/ETA）。"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>5.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        "•",
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


# ---------- 汇总表格 ----------

def print_summary_table(rows: List[dict], title: str = "📦 分析产物") -> None:
    """最终任务汇总表格。

    rows 每项必须包含 keys: page, title, report, screenshots, srt, transcript
    可选 keys: video
    """
    table = Table(
        title=title,
        title_style="bold magenta",
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("分P", style="cyan", no_wrap=True, justify="center")
    table.add_column("标题", style="green", no_wrap=False, max_width=40)
    table.add_column("报告路径", style="blue", overflow="fold")
    table.add_column("截图", justify="right", style="magenta")
    table.add_column("耗时", justify="right", style="yellow")

    for r in rows:
        table.add_row(
            str(r.get("page", "1")),
            r.get("title", ""),
            str(r.get("report", "")),
            str(r.get("screenshots", 0)),
            r.get("elapsed", ""),
        )
    console.print()
    console.print(table)


# ---------- 简易 Live 文本（用于动态状态切换） ----------

@contextmanager
def live_status(initial: str) -> Iterator[Live]:
    """Live 区域，用于动态刷新同一行的状态文本（如登录扫码状态）。"""
    text = Text(initial, style="cyan")
    with Live(text, console=console, refresh_per_second=4, transient=False) as live:
        def _update(new_text: str, style: str = "cyan") -> None:
            live.update(Text(new_text, style=style))
        live.update_text = _update  # type: ignore[attr-defined]
        yield live


# ---------- 视频信息卡片（步骤 1 完成后展示） ----------

def _format_duration(seconds: int) -> str:
    """把秒数格式化为 'X小时Y分Z秒'。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}小时{minutes:02d}分{secs:02d}秒"
    if minutes > 0:
        return f"{minutes}分{secs:02d}秒"
    return f"{secs}秒"


def print_video_card(video_info: "VideoInfo", pages: List["PageInfo"]) -> None:
    """视频信息卡片（Panel + Table）。"""
    table = Table(
        show_header=False,
        show_lines=False,
        box=None,
        padding=(0, 2),
    )
    table.add_column("项目", style="bold cyan", no_wrap=True, justify="right")
    table.add_column("值", style="white")

    desc = (video_info.desc or "").strip()
    if len(desc) > 100:
        desc = desc[:100] + "…"
    table.add_row("标题", video_info.title)
    table.add_row("UP主", f"[magenta]{video_info.owner}[/]")
    table.add_row("BV号", f"[blue]{video_info.bvid}[/]")
    table.add_row("时长", _format_duration(video_info.duration))
    table.add_row("分P", f"[cyan]{len(pages)} 个[/]")
    if desc:
        table.add_row("简介", f"[dim]{desc}[/]")

    console.print()
    console.print(Panel(
        table,
        title="[bold bright_cyan]📺 视频信息[/]",
        border_style="bright_cyan",
        padding=(0, 1),
        expand=False,
    ))
    console.print()


# ---------- 配置摘要表（启动时展示） ----------

def print_config_summary(config: "AppConfig") -> None:
    """启动时打印当前运行配置摘要表。"""
    # 解析 cookie 来源
    cookie_source = "未配置"
    if config.bilibili.cookie:
        cookie_source = "命令行参数 --cookie"
    else:
        # 检查项目根目录下的 cookies.txt
        from bili_analyzer.api.auth import PROJECT_ROOT_COOKIES_FILE
        if PROJECT_ROOT_COOKIES_FILE.is_file():
            cookie_source = f"{PROJECT_ROOT_COOKIES_FILE.name}"

    # LLM 提供商与模型
    llm_provider = getattr(config.llm, "provider", "未知")
    # 根据 provider 从子配置中取 model
    llm_model = "默认"
    if llm_provider == "zhipu":
        llm_model = getattr(config.llm.zhipu, "model", llm_model)
    elif llm_provider == "deepseek":
        llm_model = getattr(config.llm.deepseek, "model", llm_model)

    table = Table(
        title="[bold magenta]⚙  当前运行配置[/]",
        title_style="bold magenta",
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("项目", style="bold cyan", no_wrap=True)
    table.add_column("值", style="white")

    table.add_row("视频 URL", config.video_url or "未提供")
    table.add_row("画质", config.download.quality)
    table.add_row("LLM 提供商", f"[magenta]{llm_provider}[/] / {llm_model}")
    table.add_row("Whisper 模型", config.transcriber.whisper.model or "medium")
    table.add_row("字幕语言", config.transcriber.sub_langs or "zh-CN,zh-Hans,zh-TW,ai-zh")
    table.add_row("Cookie 来源", f"[green]{cookie_source}[/]")
    table.add_row("输出目录", config.output_dir)

    console.print()
    console.print(table)
    console.print()


# ---------- 环境自检 ----------

def check_conda_env() -> bool:
    """检测当前 Python 环境是否是 conda 'AI' 环境。

    检测策略（双保险）：
    1. CONDA_DEFAULT_ENV 环境变量 == "AI"
    2. sys.executable 路径含 "anaconda3/envs/AI"

    Returns:
        bool: True 表示在 AI 环境，False 表示在别的环境
    """
    if os.environ.get("CONDA_DEFAULT_ENV", "").lower() == "ai":
        return True
    exe = sys.executable.replace("\\", "/").lower()
    if "anaconda3/envs/ai" in exe or "anaconda3\\envs\\ai" in exe.lower():
        return True
    return False


# ---------- 报告 Markdown 预览 ----------

def print_markdown_preview(report_path: Path, lines: int = 30) -> None:
    """渲染 report_path 前 N 行作为 Markdown 预览。

    Args:
        report_path: Markdown 文件路径
        lines: 预览的行数（默认 30）
    """
    report_path = Path(report_path)
    if not report_path.is_file():
        return
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return
    head_lines = text.splitlines()[:lines]
    if not head_lines:
        return
    preview = "\n".join(head_lines)
    md = Markdown(preview, code_theme="monokai")
    console.print()
    console.print(Panel(
        md,
        title=f"[bold green]📄 报告预览（前 {len(head_lines)} 行）[/]",
        border_style="green",
        padding=(0, 1),
    ))
    console.print(f"  [dim]完整报告:[/] [blue]{report_path}[/]")
    console.print()


# ---------- 产物目录树 ----------

def print_output_tree(video_dir: Path, max_depth: int = 3, max_nodes: int = 200) -> None:
    """递归扫描 video_dir，用 Rich Tree 展示目录结构。

    Args:
        video_dir: 要展示的根目录
        max_depth: 最大递归深度（默认 3，避免极深目录刷屏）
        max_nodes: 最大节点数（默认 200，防止极大输出爆栈/刷屏）
    """

    def _build_tree(path: Path, depth: int, remaining: List[int]) -> Tree:
        """递归构造 Tree 节点；通过 remaining[0] 共享计数器。"""
        if depth > max_depth or remaining[0] <= 0:
            tree = Tree(f"[dim]…（已截断）[/]")
            return tree
        remaining[0] -= 1
        tree = Tree(f"[bold cyan]📂 {path.name}/[/]")
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return tree
        for entry in entries:
            if remaining[0] <= 0:
                tree.add("[dim]…（已截断）[/]")
                break
            remaining[0] -= 1
            try:
                if entry.is_dir():
                    subtree = _build_tree(entry, depth + 1, remaining)
                    tree.add(subtree)
                else:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f}KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f}MB"
                    tree.add(f"[dim]{entry.name}[/]  [yellow]{size_str}[/]")
            except OSError:
                tree.add(f"[dim]{entry.name}[/]")
        return tree

    video_dir = Path(video_dir)
    if not video_dir.is_dir():
        return
    remaining = [max_nodes]
    tree = _build_tree(video_dir, 0, remaining)
    console.print()
    console.print(Panel(
        tree,
        title=f"[bold bright_magenta]🌳 产物目录树[/]  [dim]{video_dir}[/]",
        border_style="bright_magenta",
        padding=(0, 1),
    ))
    console.print()


# ---------- --no-color 解析 ----------

def is_no_color() -> bool:
    """检查 sys.argv 是否含 --no-color；若有则设置环境变量并返回 True。

    必须在解析 argparse 之前调用（cli.py 的 main() 第一行），
    避免 Rich Console 拿到错误的颜色检测结果。
    """
    if "--no-color" in sys.argv:
        os.environ["NO_COLOR"] = "1"
        # 同步关闭已存在的 console（双保险）
        try:
            console.no_color = True
        except Exception:
            pass
        return True
    return False
