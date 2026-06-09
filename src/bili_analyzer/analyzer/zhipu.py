"""智谱 GLM API 分析器

使用智谱 GLM-4.7-Flash 模型进行内容分析。
支持 zhipuai SDK 和 OpenAI SDK 两种调用方式。

每次调用返回 `(结果, TokenUsage)`，并输出：
- DEBUG 级别完整请求/响应/usage 详情
- INFO 级别 token 汇总
- 终端彩色 token 消耗行
- finish_reason 异常时 WARNING
"""

import os
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

logger = get_logger("analyzer.zhipu")


def _extract_usage(response, model: str, step: str) -> TokenUsage:
    """从智谱/OpenAI 兼容响应中提取 token 用量"""
    usage_data = getattr(response, "usage", None)
    prompt_tokens = getattr(usage_data, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage_data, "completion_tokens", 0) or 0
    total_tokens = getattr(usage_data, "total_tokens", 0) or 0
    # 智谱特有字段：prompt_tokens_details.cached_tokens
    ptd = getattr(usage_data, "prompt_tokens_details", None)
    cached_tokens = getattr(ptd, "cached_tokens", 0) or 0 if ptd else 0
    finish_reason = (
        response.choices[0].finish_reason
        if getattr(response, "choices", None) else "unknown"
    ) or "unknown"
    request_id = (
        getattr(response, "request_id", None)
        or getattr(response, "id", None)
    )
    return TokenUsage(
        provider="zhipu",
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
    logger.debug(f"[zhipu.{usage.step}] model={usage.model} prompt_chars={prompt_len}")
    logger.debug(f"[zhipu.{usage.step}] request_id={usage.request_id} finish_reason={usage.finish_reason}")
    logger.debug(f"[zhipu.{usage.step}] usage={usage.to_log_dict()}")
    logger.debug(f"[zhipu.{usage.step}] response.content[:200]={response_text[:200]!r}")

    logger.info(
        f"[zhipu.{usage.step}] tokens: prompt={usage.prompt_tokens} "
        f"completion={usage.completion_tokens} total={usage.total_tokens} "
        f"cached={usage.cached_tokens} finish_reason={usage.finish_reason}"
    )

    print_token_usage(usage)

    if usage.finish_reason not in ("stop", "interactive"):
        logger.warning(
            f"[zhipu.{usage.step}] 非正常 finish_reason={usage.finish_reason}，"
            f"输出可能不完整（length=截断 / content_filter=安全过滤 / sensitive=敏感词）"
        )


class ZhipuAnalyzer(BaseAnalyzer):
    """智谱 GLM 分析器

    Args:
        api_key: 智谱 API Key
        model: 模型名称
        max_tokens: 单次输出 token 上限（官方推荐 65536，模型最大 128K）
        thinking_enabled: 是否启用 GLM-4.7 思考模式（Chain-of-Thought）
    """

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4.7-flash",
        max_tokens: int = 32768,
        thinking_enabled: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_enabled = thinking_enabled

    @property
    def name(self) -> str:
        return f"智谱 {self.model}"

    def analyze(self, video_info: Dict, srt_content: str) -> Tuple[Dict[str, Any], TokenUsage]:
        """使用智谱 GLM API 分析字幕内容"""
        # 启用 prefix cache：SRT 作为独立 user message 处于 messages[1] 位置
        system_content = ANALYSIS_SYSTEM_PROMPT
        task_instruction = build_analysis_task_instruction(video_info)

        # 优先尝试 zhipuai SDK
        try:
            response_text, usage = self._call_with_zhipuai_sdk(
                system_content=system_content,
                srt_content=srt_content,
                task_instruction=task_instruction,
                force_json=True,
                step="analyze",
            )
        except ImportError:
            # 降级为 OpenAI SDK
            response_text, usage = self._call_with_openai_sdk(
                system_content=system_content,
                srt_content=srt_content,
                task_instruction=task_instruction,
                force_json=True,
                step="analyze",
            )

        result = parse_llm_response(response_text)
        validate_analysis_result(result)

        print_success("智谱分析完成")
        print_info(f"  知识点: {len(result.get('knowledge_points', []))} 个")
        print_info(f"  关键截图: {len(result.get('key_screenshots', []))} 个")

        return result, usage

    def format_transcript(self, srt_content: str) -> Tuple[str, TokenUsage]:
        """使用智谱 GLM API 排版字幕"""
        # 启用 prefix cache：与 analyze 调用共享 messages[1] 的 SRT 内容
        system_content = FORMAT_TRANSCRIPT_SYSTEM_PROMPT
        task_instruction = build_format_transcript_task_instruction()

        try:
            response_text, usage = self._call_with_zhipuai_sdk(
                system_content=system_content,
                srt_content=srt_content,
                task_instruction=task_instruction,
                force_json=False,
                step="format_transcript",
            )
        except ImportError:
            response_text, usage = self._call_with_openai_sdk(
                system_content=system_content,
                srt_content=srt_content,
                task_instruction=task_instruction,
                force_json=False,
                step="format_transcript",
            )

        return normalize_transcript_format(response_text), usage

    def _call_with_zhipuai_sdk(
        self,
        system_content: str,
        srt_content: str,
        task_instruction: str,
        force_json: bool = True,
        step: str = "unknown",
    ) -> Tuple[str, TokenUsage]:
        """使用 zhipuai SDK 调用

        注意：zhipuai SDK 旧版本不支持 `thinking` 关键字参数（会抛 TypeError）。
        本方法自动检测并通过 `extra_body` 透传给 OpenAI 兼容模式。
        如旧版 SDK 完全不支持，会降级为 OpenAI SDK 调用。

        Args:
            system_content: 系统提示（messages[0]）
            srt_content: 字幕内容（messages[1]，与 format_transcript 共享，cache 命中点）
            task_instruction: 任务指令（messages[2]）
        """
        from zhipuai import ZhipuAI

        client = ZhipuAI(api_key=self.api_key)

        # 使用 build_cached_messages 构造 messages 数组，启用 prefix cache
        messages = build_cached_messages(system_content, srt_content, task_instruction)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}
        # zhipuai SDK 旧版不支持 thinking 参数；先尝试，失败则降级到 OpenAI SDK
        if self.thinking_enabled:
            try:
                # 新版 zhipuai SDK（v4+）支持 extra_body 透传
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            except Exception:
                pass

        _t0 = time.time()
        try:
            with spinner(f"调用智谱 API ({self.model}) 中…  30-120 秒，请耐心等待") as sp:
                response = client.chat.completions.create(**kwargs)
                _duration = time.time() - _t0
                sp.update(
                    f"调用智谱 API 完成（耗时 {int(_duration)}s），正在解析结果…"
                )
        except TypeError as e:
            # 旧版 zhipuai SDK 不支持 thinking/extra_body → 降级到 OpenAI SDK
            if "thinking" in str(e) or "extra_body" in str(e):
                logger.warning(
                    f"[zhipu.{step}] zhipuai SDK 不支持 thinking 参数，"
                    f"降级为 OpenAI SDK 兼容模式以启用 thinking: {e}"
                )
                return self._call_with_openai_sdk(
                    system_content=system_content,
                    srt_content=srt_content,
                    task_instruction=task_instruction,
                    force_json=force_json,
                    step=step,
                )
            raise
        except Exception:
            # 异常情况下也要记录耗时
            logger.debug(f"[zhipu.{step}] 异常时耗时: {time.time() - _t0:.2f}s")
            raise

        content = response.choices[0].message.content
        if not content or not content.strip():
            # GLM-4.7 启用思考模式时，真实答案可能落在 reasoning_content
            content = getattr(response.choices[0].message, "reasoning_content", None) or ""
            if content and content.strip():
                logger.info(
                    f"[zhipu.{step}] content 为空但 reasoning_content 非空 "
                    f"({len(content)} 字符)，fallback 到 reasoning_content"
                )
        if not content or not content.strip():
            # 即使返回空，也记录一次 usage（虽然可能是 0）
            usage = _extract_usage(response, self.model, step)
            usage.duration_seconds = time.time() - _t0
            _log_and_show_usage(usage, len(srt_content) + len(task_instruction), content or "")
            raise RuntimeError("智谱 API 返回空内容")

        usage = _extract_usage(response, self.model, step)
        usage.duration_seconds = time.time() - _t0
        _log_and_show_usage(usage, len(srt_content) + len(task_instruction), content)
        return content, usage

    def _call_with_openai_sdk(
        self,
        system_content: str,
        srt_content: str,
        task_instruction: str,
        force_json: bool = True,
        step: str = "unknown",
    ) -> Tuple[str, TokenUsage]:
        """使用 OpenAI SDK 调用智谱 API（兼容模式）

        Args:
            system_content: 系统提示（messages[0]）
            srt_content: 字幕内容（messages[1]，与 format_transcript 共享，cache 命中点）
            task_instruction: 任务指令（messages[2]）
        """
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )

        # 使用 build_cached_messages 构造 messages 数组，启用 prefix cache
        messages = build_cached_messages(system_content, srt_content, task_instruction)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}
        # GLM-4.7 思考模式：OpenAI 兼容路径必须通过 extra_body 透传给智谱网关
        if self.thinking_enabled:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        _t0 = time.time()
        try:
            with spinner(f"调用智谱 API ({self.model}, OpenAI 兼容) 中…  30-120 秒") as sp:
                response = client.chat.completions.create(**kwargs)
                _duration = time.time() - _t0
                sp.update(
                    f"调用智谱 API 完成（耗时 {int(_duration)}s），正在解析结果…"
                )
        except Exception:
            logger.debug(f"[zhipu.{step}] 异常时耗时: {time.time() - _t0:.2f}s")
            raise

        content = response.choices[0].message.content
        if not content or not content.strip():
            # GLM-4.7 启用思考模式时，真实答案可能落在 reasoning_content
            content = getattr(response.choices[0].message, "reasoning_content", None) or ""
            if content and content.strip():
                logger.info(
                    f"[zhipu.{step}] content 为空但 reasoning_content 非空 "
                    f"({len(content)} 字符)，fallback 到 reasoning_content"
                )
        if not content or not content.strip():
            usage = _extract_usage(response, self.model, step)
            usage.duration_seconds = time.time() - _t0
            _log_and_show_usage(usage, len(srt_content) + len(task_instruction), content or "")
            raise RuntimeError("智谱 API 返回空内容")

        usage = _extract_usage(response, self.model, step)
        usage.duration_seconds = time.time() - _t0
        _log_and_show_usage(usage, len(srt_content) + len(task_instruction), content)
        return content, usage
