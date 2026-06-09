"""交互式分析器（降级方案）

当 API 不可用时，输出 prompt 供用户手动发送给 LLM，
然后将 LLM 返回的 JSON 粘贴回来。
"""

import sys
import re
from typing import Any, Dict, Tuple

from rich.panel import Panel
from rich.syntax import Syntax

from bili_analyzer.analyzer.base import (
    BaseAnalyzer,
    build_analysis_prompt,
    build_format_transcript_prompt,
    parse_llm_response,
    validate_analysis_result,
)
from bili_analyzer.analyzer.usage import TokenUsage
from bili_analyzer.parser.srt import parse_srt_file, get_full_transcript
from bili_analyzer.ui.console import (
    console,
    print_info,
    print_success,
    print_token_usage,
    spinner,
)


class InteractiveAnalyzer(BaseAnalyzer):
    """交互式分析器"""

    @property
    def name(self) -> str:
        return "交互式"

    def analyze(self, video_info: Dict, srt_content: str) -> Tuple[Dict[str, Any], TokenUsage]:
        """交互式分析：输出 prompt，等待用户粘贴 LLM 返回的 JSON"""
        prompt = build_analysis_prompt(video_info, srt_content)

        console.print()
        console.rule("[bold magenta]LLM 分析 Prompt[/]", align="left", style="magenta")
        console.print()
        console.print(
            "  [cyan]请将下方内容复制并发送给 LLM（如 DeepSeek、Claude、GPT-4 等）[/]"
        )
        console.print()

        # 把 prompt 用 syntax 高亮（markdown 风格）显示
        syntax = Syntax(prompt, "markdown", theme="monokai", word_wrap=True, background_color="default")
        console.print(syntax)
        console.print()

        console.rule("[bold magenta]等待 LLM 响应[/]", align="left", style="magenta")
        console.print()
        console.print("  [cyan]请将 LLM 返回的 JSON 结果粘贴到下方，然后:[/]")
        console.print("    [dim]• Windows: 按 回车然后 Ctrl+Z 最后再回车[/]")
        console.print("    [dim]• macOS / Linux: 按 Ctrl+D[/]")
        console.print()
        console.print("  [bold]开始输入:[/]")
        console.print("─" * 60, style="dim")

        lines = []
        try:
            with spinner("等待 LLM 响应（Ctrl+D/Z 结束输入）…"):
                for line in sys.stdin:
                    lines.append(line)
        except KeyboardInterrupt:
            raise ValueError("用户取消输入")

        response = "".join(lines).strip()
        if not response:
            raise ValueError("未收到任何输入")

        console.print("─" * 60, style="dim")
        print_info(f"已接收 {len(response)} 字符的响应")

        result = parse_llm_response(response)
        validate_analysis_result(result)

        print_success("分析结果验证通过")
        # 交互式无 API 调用，标记 finish_reason=interactive
        usage = TokenUsage(
            provider="interactive",
            model="manual",
            step="analyze",
            finish_reason="interactive",
        )
        print_token_usage(usage)
        return result, usage

    def format_transcript(self, srt_content: str) -> Tuple[str, TokenUsage]:
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
        # 交互式本地处理，无 API 调用
        usage = TokenUsage(
            provider="interactive",
            model="manual",
            step="format_transcript",
            finish_reason="interactive",
        )
        return '　　' + ''.join(text_lines), usage
