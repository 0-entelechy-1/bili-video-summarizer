"""交互式分析器（降级方案）

当 API 不可用时，输出 prompt 供用户手动发送给 LLM，
然后将 LLM 返回的 JSON 粘贴回来。
"""

import sys
import re
from typing import Any, Dict

from bili_analyzer.analyzer.base import (
    BaseAnalyzer,
    build_analysis_prompt,
    build_format_transcript_prompt,
    parse_llm_response,
    validate_analysis_result,
)
from bili_analyzer.parser.srt import parse_srt_file, get_full_transcript


class InteractiveAnalyzer(BaseAnalyzer):
    """交互式分析器"""

    @property
    def name(self) -> str:
        return "交互式"

    def analyze(self, video_info: Dict, srt_content: str) -> Dict[str, Any]:
        """交互式分析：输出 prompt，等待用户粘贴 LLM 返回的 JSON"""
        prompt = build_analysis_prompt(video_info, srt_content)

        print("\n" + "=" * 70)
        print("LLM 分析 Prompt")
        print("=" * 70)
        print("\n请将以下内容复制并发送给 LLM (如 DeepSeek、Claude、GPT-4 等):\n")
        print(prompt)
        print("\n" + "=" * 70)
        print("等待 LLM 响应")
        print("=" * 70)
        print("\n请将 LLM 返回的 JSON 结果粘贴到下方，然后:")
        print("  - Windows: 按 回车然后 Ctrl+Z 最后再回车")
        print("  - macOS/Linux: 按 Ctrl+D")
        print("\n开始输入:")
        print("-" * 70)

        lines = []
        try:
            for line in sys.stdin:
                lines.append(line)
        except KeyboardInterrupt:
            raise ValueError("用户取消输入")

        response = "".join(lines).strip()
        if not response:
            raise ValueError("未收到任何输入")

        print("-" * 70)
        print(f"已接收 {len(response)} 字符的响应")

        result = parse_llm_response(response)
        validate_analysis_result(result)

        print("分析结果验证通过")
        return result

    def format_transcript(self, srt_content: str) -> str:
        lines = srt_content.strip().split('\n')
        text_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.isdigit():
                continue
            if re.match(r'[\d:,]+\s*-->\s*[\d:,]+', stripped):
                continue
            text_lines.append(stripped)
        return '　　' + ''.join(text_lines)
