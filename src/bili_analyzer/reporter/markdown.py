"""Markdown 报告生成器（清洁版学习笔记风格）

功能:
- 生成知识点卡片式学习笔记
- 包含核心概念、详细说明、关键要点
- 配合截图，简洁专业
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def format_duration(seconds: float) -> str:
    """格式化时长为可读字符串"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}小时{minutes:02d}分{secs:02d}秒"
    return f"{minutes}分{secs:02d}秒"


def generate_markdown(
    video_info: Dict,
    analysis: Dict[str, Any],
    screenshots: Dict[float, Path],
    srt_content: str,
    output_dir: Path,
) -> Path:
    """生成完整的 Markdown 报告（清洁版学习笔记风格）

    Args:
        video_info: 视频信息，包含 title, owner, duration 等
        analysis: LLM 分析结果，包含:
            - summary: 内容摘要
            - knowledge_points: 知识点列表
            - knowledge_framework: 核心知识框架（可选）
            - practical_value: 实践价值（可选）
            - learning_suggestions: 学习建议列表（可选）
        screenshots: 时间戳到截图路径的映射
        srt_content: 完整字幕内容（未使用）
        output_dir: 输出目录

    Returns:
        Path: 生成的报告文件路径
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    title = video_info.get('title', 'video')
    safe_title = "".join(
        c for c in title if c.isalnum() or c in (' ', '-', '_', '(', ')', '，', '。', '"', '"')
    ).strip()[:50]

    report_filename = f"{safe_title}_学习笔记.md"
    report_path = output_dir / report_filename

    lines = []

    # === 标题 ===
    lines.append(f"# 《{title}》学习笔记")
    lines.append("")

    # === 视频信息概览 ===
    duration = video_info.get('duration', 0)
    duration_str = format_duration(duration)
    kp_count = len(analysis.get('knowledge_points', []))

    lines.append(f"**视频时长**: {duration_str} | **知识点**: {kp_count} 个")
    lines.append("")
    lines.append("---")
    lines.append("")

    # === 知识点卡片 ===
    knowledge_points = analysis.get('knowledge_points', [])

    for i, kp in enumerate(knowledge_points, 1):
        title_kp = kp.get('title', f'知识点 {i}')
        core_concept = kp.get('core_concept', kp.get('content', ''))
        details = kp.get('details', '')
        key_points = kp.get('key_points', [])
        timestamp = kp.get('timestamp')

        lines.append(f"## 📌 {i}. {title_kp}")
        lines.append("")

        # 核心概念
        lines.append(f"**核心概念**: {core_concept}")
        lines.append("")
        lines.append("")
        lines.append("")

        # 查找对应截图
        closest_screenshot = None
        min_diff = 10.0

        if timestamp:
            for sc_time, sc_path in screenshots.items():
                diff = abs(sc_time - timestamp)
                if diff < min_diff:
                    min_diff = diff
                    closest_screenshot = sc_path

        # 插入截图
        if closest_screenshot:
            try:
                rel_path = os.path.relpath(str(closest_screenshot), str(report_path.parent))
                lines.append(f'<img src="{rel_path}" width="600" alt="知识点配图"/>')
            except ValueError:
                lines.append(f'<img src="{closest_screenshot}" width="600" alt="知识点配图"/>')
            lines.append("")
            lines.append("")

        # 详细说明
        if details:
            lines.append("### 📖 详细说明")
            lines.append("")
            lines.append(details)
            lines.append("")

        # 关键要点
        if key_points:
            lines.append("### 🔑 关键要点")
            lines.append("")
            for point in key_points:
                lines.append(f"- {point}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # === 全文总结 ===
    lines.append("## 📚 全文总结")
    lines.append("")

    if analysis.get('knowledge_framework'):
        lines.append("### 核心知识框架")
        lines.append("")
        lines.append(analysis['knowledge_framework'])
        lines.append("")

    if analysis.get('practical_value'):
        lines.append("### 实践价值")
        lines.append("")
        lines.append(analysis['practical_value'])
        lines.append("")

    if analysis.get('learning_suggestions'):
        lines.append("### 学习建议")
        lines.append("")
        for i, suggestion in enumerate(analysis['learning_suggestions'], 1):
            lines.append(f"{i}. {suggestion}")
        lines.append("")

    # === 页脚 ===
    lines.append("---")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    # 写入文件
    content = '\n'.join(lines)
    report_path.write_text(content, encoding='utf-8')

    file_size = report_path.stat().st_size / 1024
    print(f"\n学习笔记已生成: {report_path}")
    print(f"  文件大小: {file_size:.2f} KB")
    print(f"  知识点数: {kp_count}")
    print(f"  截图数: {len(screenshots)}")

    return report_path
