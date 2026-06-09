"""DeepSeek API 分析器

使用 DeepSeek 兼容 OpenAI 协议的 Chat Completions 接口。
每次调用返回 `(结果, TokenUsage)`，与智谱分析器接口保持一致。
"""

import time
from typing import Any, Dict, Tuple

from bili_analyzer.analyzer.base import (
    ANALYSIS_SYSTEM_PROMPT,
    FORMAT_TRANSCRIPT_SYSTEM_PROMPT,
    BaseAnalyzer,
    build_analysis_task_instruction,
    build_cached_messages,
    build_format_transcript_task_instruction,
    normalize_transcript_format,
    parse_llm_response,
    validate_analysis_result,
)
from bili_analyzer.analyzer.usage import TokenUsage
from bili_analyzer.logger import get_logger
from bili_analyzer.ui.console import (
    print_info,
    print_success,
    print_token_usage,
    spinner,
)

logger = get_logger("analyzer.deepseek")


def _extract_usage(response, model: str, step: str) -> TokenUsage:
    """从 OpenAI 兼容响应中提取 token 用量"""
    usage_data = getattr(response, "usage", None)
    prompt_tokens = getattr(usage_data, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage_data, "completion_tokens", 0) or 0
    total_tokens = getattr(usage_data, "total_tokens", 0) or 0
    ptd = getattr(usage_data, "prompt_tokens_details", None)
    cached_tokens = getattr(ptd, "cached_tokens", 0) or 0 if ptd else 0
    finish_reason = (
        response.choices[0].finish_reason
        if getattr(response, "choices", None) else "unknown"
    ) or "unknown"
    request_id = (
        getattr(response, "id", None)
        or getattr(response, "request_id", None)
    )
    return TokenUsage(
        provider="deepseek",
        model=model,
        step=step,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        finish_reason=finish_reason,
        request_id=request_id,
    )


def _log_and_show_usage(usage: TokenUsage, prompt_len: int, response_text: str) -> None:
    """统一处理：详细日志 + 终端显示 + 异常 finish_reason 警告"""
    logger.debug(f"[deepseek.{usage.step}] model={usage.model} prompt_chars={prompt_len}")
    logger.debug(f"[deepseek.{usage.step}] request_id={usage.request_id} finish_reason={usage.finish_reason}")
    logger.debug(f"[deepseek.{usage.step}] usage={usage.to_log_dict()}")
    logger.debug(f"[deepseek.{usage.step}] response.content[:200]={response_text[:200]!r}")

    logger.info(
        f"[deepseek.{usage.step}] tokens: prompt={usage.prompt_tokens} "
        f"completion={usage.completion_tokens} total={usage.total_tokens} "
        f"cached={usage.cached_tokens} finish_reason={usage.finish_reason}"
    )

    print_token_usage(usage)

    if usage.finish_reason not in ("stop", "interactive"):
        logger.warning(
            f"[deepseek.{usage.step}] 非正常 finish_reason={usage.finish_reason}，"
            f"输出可能不完整（length=截断 / content_filter=安全过滤 / sensitive=敏感词）"
        )


class DeepseekAnalyzer(BaseAnalyzer):
    """DeepSeek 分析器"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @property
    def name(self) -> str:
        return f"DeepSeek {self.model}"

    def analyze(self, video_info: Dict, srt_content: str) -> Tuple[Dict[str, Any], TokenUsage]:
        """使用 DeepSeek API 分析字幕内容"""
        from openai import OpenAI

        # 启用 prefix cache：SRT 作为独立 user message 处于 messages[1] 位置
        messages = build_cached_messages(
            ANALYSIS_SYSTEM_PROMPT,
            srt_content,
            build_analysis_task_instruction(video_info),
        )

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        _t0 = time.time()
        try:
            with spinner(f"调用 DeepSeek API ({self.model}) 中…  30-120 秒，请耐心等待") as sp:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=8192,
                    response_format={"type": "json_object"},
                )
                _duration = time.time() - _t0
                sp.update(
                    f"调用 DeepSeek API 完成（耗时 {int(_duration)}s），正在解析结果…"
                )
        except Exception:
            logger.debug(f"[deepseek.analyze] 异常时耗时: {time.time() - _t0:.2f}s")
            raise

        content = response.choices[0].message.content

        usage = _extract_usage(response, self.model, step="analyze")
        usage.duration_seconds = time.time() - _t0
        _log_and_show_usage(usage, len(srt_content), content or "")

        result = parse_llm_response(content)
        validate_analysis_result(result)

        print_success("DeepSeek 分析完成")
        print_info(f"  知识点: {len(result.get('knowledge_points', []))} 个")
        print_info(f"  关键截图: {len(result.get('key_screenshots', []))} 个")

        return result, usage

    def format_transcript(self, srt_content: str) -> Tuple[str, TokenUsage]:
        """使用 DeepSeek API 排版字幕"""
        from openai import OpenAI

        # 启用 prefix cache：与 analyze 调用共享 messages[1] 的 SRT 内容
        messages = build_cached_messages(
            FORMAT_TRANSCRIPT_SYSTEM_PROMPT,
            srt_content,
            build_format_transcript_task_instruction(),
        )

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        _t0 = time.time()
        try:
            with spinner("调用 DeepSeek API 进行字幕分段排版…") as sp:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=8192,
                )
                _duration = time.time() - _t0
                sp.update(
                    f"DeepSeek 字幕排版完成（耗时 {int(_duration)}s）"
                )
        except Exception:
            logger.debug(f"[deepseek.format_transcript] 异常时耗时: {time.time() - _t0:.2f}s")
            raise

        content = response.choices[0].message.content

        usage = _extract_usage(response, self.model, step="format_transcript")
        usage.duration_seconds = time.time() - _t0
        _log_and_show_usage(usage, len(srt_content), content or "")

        return normalize_transcript_format(content), usage
