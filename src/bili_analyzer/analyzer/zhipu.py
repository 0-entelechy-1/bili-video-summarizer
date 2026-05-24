"""智谱 GLM API 分析器

使用智谱 GLM-4.7-Flash 模型进行内容分析。
支持 zhipuai SDK 和 OpenAI SDK 两种调用方式。
"""

import os
from typing import Any, Dict

from bili_analyzer.analyzer.base import (
    BaseAnalyzer,
    build_analysis_prompt,
    build_format_transcript_prompt,
    parse_llm_response,
    validate_analysis_result,
)


class ZhipuAnalyzer(BaseAnalyzer):
    """智谱 GLM 分析器"""

    def __init__(self, api_key: str, model: str = "glm-4.7-flash"):
        """
        Args:
            api_key: 智谱 API Key
            model: 模型名称
        """
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return f"智谱 {self.model}"

    def analyze(self, video_info: Dict, srt_content: str) -> Dict[str, Any]:
        """使用智谱 GLM API 分析字幕内容"""
        prompt = build_analysis_prompt(video_info, srt_content)

        # 优先尝试 zhipuai SDK
        try:
            response_text = self._call_with_zhipuai_sdk(prompt, force_json=True)
        except ImportError:
            # 降级为 OpenAI SDK
            response_text = self._call_with_openai_sdk(prompt, force_json=True)

        result = parse_llm_response(response_text)
        validate_analysis_result(result)

        print(f"智谱分析完成")
        print(f"  知识点: {len(result.get('knowledge_points', []))} 个")
        print(f"  关键截图: {len(result.get('key_screenshots', []))} 个")

        return result

    def format_transcript(self, srt_content: str) -> str:
        prompt = build_format_transcript_prompt(srt_content)

        try:
            response_text = self._call_with_zhipuai_sdk(prompt, force_json=False)
        except ImportError:
            response_text = self._call_with_openai_sdk(prompt, force_json=False)

        return response_text

    def _call_with_zhipuai_sdk(self, prompt: str, force_json: bool = True) -> str:
        """使用 zhipuai SDK 调用"""
        from zhipuai import ZhipuAI

        client = ZhipuAI(api_key=self.api_key)

        print(f"正在调用智谱 API (模型: {self.model})...")
        print("  这可能需要30-120秒，请耐心等待...")

        kwargs = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一位专业的学术内容分析专家。"
                        "请严格按照要求的 JSON 格式返回分析结果,"
                        "不要包含任何其他文字、解释或 markdown 标记。"
                        "直接输出纯 JSON 对象。"
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 8192,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("智谱 API 返回空内容")
        return content

    def _call_with_openai_sdk(self, prompt: str, force_json: bool = True) -> str:
        """使用 OpenAI SDK 调用智谱 API（兼容模式）"""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )

        print(f"正在调用智谱 API (模型: {self.model}, OpenAI兼容模式)...")
        print("  这可能需要30-120秒，请耐心等待...")

        kwargs = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一位专业的学术内容分析专家。"
                        "请严格按照要求的 JSON 格式返回分析结果,"
                        "不要包含任何其他文字、解释或 markdown 标记。"
                        "直接输出纯 JSON 对象。"
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 8192,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("智谱 API 返回空内容")
        return content
