"""DeepSeek API 分析器"""

from typing import Any, Dict

from bili_analyzer.analyzer.base import (
    BaseAnalyzer,
    build_analysis_prompt,
    build_format_transcript_prompt,
    parse_llm_response,
    validate_analysis_result,
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

    def analyze(self, video_info: Dict, srt_content: str) -> Dict[str, Any]:
        """使用 DeepSeek API 分析字幕内容"""
        from openai import OpenAI

        prompt = build_analysis_prompt(video_info, srt_content)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        print(f"正在调用 DeepSeek API (模型: {self.model})...")
        print("  这可能需要30-120秒，请耐心等待...")

        response = client.chat.completions.create(
            model=self.model,
            messages=[
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
            temperature=0.3,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content

        result = parse_llm_response(content)
        validate_analysis_result(result)

        print(f"DeepSeek 分析完成")
        print(f"  知识点: {len(result.get('knowledge_points', []))} 个")
        print(f"  关键截图: {len(result.get('key_screenshots', []))} 个")

        return result

    def format_transcript(self, srt_content: str) -> str:
        from openai import OpenAI

        prompt = build_format_transcript_prompt(srt_content)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        print("正在调用 LLM 进行字幕分段排版...")

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一位专业的文字排版专家。"
                        "请按照要求的格式对字幕进行语义分段排版,"
                        "直接输出排版后的纯文本,不要包含任何解释或额外标记。"
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=8192,
        )

        return response.choices[0].message.content
