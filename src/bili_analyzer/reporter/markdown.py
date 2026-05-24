"""Markdown 报告生成器

功能:
- 生成总-分-总结构的学习笔记
- 开头: 摘要、关键词、视频简介
- 中间: 知识点卡片
- 末尾: 内容总结、字幕原文
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def format_duration(seconds: float) -> str:
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
    transcript_text: str = "",
    timestamp: str = "",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    title = video_info.get('title', 'video')
    safe_title = "".join(
        c for c in title if c.isalnum() or c in (' ', '-', '_', '(', ')', '，', '。', '"', '"')
    ).strip()[:50]

    if timestamp:
        report_filename = f"{safe_title}_{timestamp}_学习笔记.md"
        report_time = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
    else:
        report_filename = f"{safe_title}_学习笔记.md"
        report_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    report_path = output_dir / report_filename

    lines = []

    lines.append(f"# 《{title}》学习笔记")
    lines.append("")

    lines.append("## 📋 摘要")
    lines.append("")
    lines.append(analysis.get('summary', ''))
    lines.append("")

    keywords = analysis.get('keywords', [])
    if keywords:
        lines.append(f"**关键词**: {'、'.join(keywords)}")
        lines.append("")

    lines.append("## 📺 视频简介")
    lines.append("")
    duration = video_info.get('duration', 0)
    duration_str = format_duration(duration)
    owner = video_info.get('owner', '未知')
    bvid = video_info.get('bvid', '')
    desc = video_info.get('desc', '')
    lines.append(f"| 项目 | 内容 |")
    lines.append(f"| --- | --- |")
    lines.append(f"| 标题 | {title} |")
    lines.append(f"| UP主 | {owner} |")
    lines.append(f"| 时长 | {duration_str} |")
    lines.append(f"| BV号 | {bvid} |")
    if desc:
        lines.append(f"| 简介 | {desc} |")
    lines.append("")

    lines.append("---")
    lines.append("")

    knowledge_points = analysis.get('knowledge_points', [])

    lines.append("## 📝 知识点详解")
    lines.append("")

    for i, kp in enumerate(knowledge_points, 1):
        title_kp = kp.get('title', f'知识点 {i}')
        core_concept = kp.get('core_concept', kp.get('content', ''))
        details = kp.get('details', '')
        key_points = kp.get('key_points', [])
        timestamp = kp.get('timestamp')

        lines.append(f"### 📌 {i}. {title_kp}")
        lines.append("")

        lines.append(f"**核心概念**: {core_concept}")
        lines.append("")
        lines.append("")

        closest_screenshot = None
        min_diff = 10.0

        if timestamp:
            for sc_time, sc_path in screenshots.items():
                diff = abs(sc_time - timestamp)
                if diff < min_diff:
                    min_diff = diff
                    closest_screenshot = sc_path

        if closest_screenshot:
            try:
                rel_path = os.path.relpath(str(closest_screenshot), str(report_path.parent)).replace("\\", "/")
                lines.append(f'<img src="{rel_path}" width="600" alt="知识点配图"/>')
            except ValueError:
                abs_path = str(closest_screenshot).replace("\\", "/")
                lines.append(f'<img src="{abs_path}" width="600" alt="知识点配图"/>')
            lines.append("")
            lines.append("")

        if details:
            lines.append("#### 📖 详细说明")
            lines.append("")
            lines.append(details)
            lines.append("")

        if key_points:
            lines.append("#### 🔑 关键要点")
            lines.append("")
            for point in key_points:
                lines.append(f"- {point}")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("## 📚 内容总结")
    lines.append("")
    lines.append(analysis.get('conclusion', ''))
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

    if transcript_text:
        lines.append("## 📄 字幕原文")
        lines.append("")
        lines.append(transcript_text)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"**生成时间**: {report_time}")
    lines.append("")

    content = '\n'.join(lines)
    report_path.write_text(content, encoding='utf-8')

    kp_count = len(knowledge_points)
    file_size = report_path.stat().st_size / 1024
    print(f"\n学习笔记已生成: {report_path}")
    print(f"  文件大小: {file_size:.2f} KB")
    print(f"  知识点数: {kp_count}")
    print(f"  截图数: {len(screenshots)}")

    return report_path
