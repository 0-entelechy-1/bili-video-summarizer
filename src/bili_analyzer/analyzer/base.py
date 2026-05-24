"""LLM 分析器基类

定义统一接口和共享的 prompt 构建逻辑。
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


def build_analysis_prompt(video_info: Dict, srt_content: str) -> str:
    """构造 LLM 分析 prompt

    Args:
        video_info: 视频信息字典
        srt_content: 完整字幕内容

    Returns:
        str: 格式化的分析 prompt
    """
    title = video_info.get("title", "未知标题")
    author = video_info.get("owner", "未知UP主")
    duration = video_info.get("duration", 0)
    bvid = video_info.get("bvid", "")
    duration_mins = int(duration // 60)
    duration_secs = int(duration % 60)
    duration_str = f"{duration_mins}分{duration_secs}秒"

    prompt = (
        "你是一位专业的学术内容分析专家。请深度分析以下学术视频的字幕内容,提取关键学术信息。\n\n"
        "**视频信息**:\n"
        f"- 标题: {title}\n"
        f"- UP主: {author}\n"
        f"- BV号: {bvid}\n"
        f"- 时长: {duration_str} ({duration}秒)\n\n"
        "**完整字幕内容**:\n"
        "```\n"
        f"{srt_content}\n"
        "```\n\n"
        "**分析要求**:\n"
        "1. **内容摘要**: 用100-200字概括视频核心内容,使用学术化表述\n"
        "2. **章节划分**: 根据内容逻辑划分3-6个章节,每章节包含时间范围和内容描述\n"
        "3. **知识点提取**: 提取10-20个关键知识点,按重要程度排序,包含详细说明\n"
        "4. **关键截图**: 识别6-10个需要截图的关键时间点(图表、公式、演示、重要概念等)\n"
        "5. **专业术语**: 提取10-15个重要的专业术语及其定义\n"
        "6. **关键词提取**: 提取3-8个最能代表视频内容的关键词\n"
        "7. **内容总结**: 用200-400字对视频内容作整体总结，概括核心观点和结论\n\n"
        "**输出格式**: 请严格按照以下 JSON 格式返回分析结果(不要包含任何其他文字):\n\n"
        "```json\n"
        "{\n"
        '  "summary": "视频内容摘要,使用专业学术表述,100-200字",\n'
        '  "chapters": [\n'
        "    {\n"
        '      "title": "章节标题",\n'
        '      "start_time": 开始时间(秒数,浮点数),\n'
        '      "end_time": 结束时间(秒数,浮点数),\n'
        '      "description": "章节内容描述,专业表述"\n'
        "    }\n"
        "  ],\n"
        '  "knowledge_points": [\n'
        "    {\n"
        '      "title": "知识点标题",\n'
        '      "content": "知识点详细内容,使用专业术语和学术表达",\n'
        '      "timestamp": 相关时间戳(秒数,浮点数),\n'
        '      "importance": "重要程度: high/medium/low"\n'
        "    }\n"
        "  ],\n"
        '  "key_screenshots": [\n'
        "    {\n"
        '      "timestamp": 时间戳(秒数,浮点数),\n'
        '      "description": "截图内容说明(图表类型、公式、演示内容等)",\n'
        '      "reason": "为什么需要截取这个画面(学术价值说明)"\n'
        "    }\n"
        "  ],\n"
        '  "terms": [\n'
        "    {\n"
        '      "term": "专业术语名称",\n'
        '      "definition": "术语的学术定义"\n'
        "    }\n"
        "  ],\n"
        '  "keywords": ["关键词1", "关键词2", "关键词3"],\n'
        '  "conclusion": "对视频内容的整体总结，200-400字，概括核心观点和结论"\n'
        "}\n"
        "```\n\n"
        "**注意事项**:\n"
        "- 所有时间戳必须是数字(秒数),不要使用字符串格式\n"
        "- 知识点按重要程度从高到低排序\n"
        "- 截图时间点优先选择包含图表、公式、关键概念展示的画面\n"
        "- 专业术语定义要准确、简洁\n"
        "- 使用专业学术表述,避免口语化\n"
        "- 确保JSON格式完全正确,可以被解析\n"
        "- 关键词应具有代表性和专业性\n"
        "- 内容总结要全面概括，突出核心观点和最终结论\n\n"
        "请开始分析并返回标准JSON格式的结果。"
    )
    return prompt


def build_format_transcript_prompt(srt_content: str) -> str:
    prompt = (
        "请对以下视频字幕内容进行语义分段排版。\n\n"
        "**要求**:\n"
        "1. 根据语义（话题转换、逻辑段落）将字幕分为若干段落，每段对应一个完整的话题\n"
        "2. 每段格式如下:\n"
        "   - 第一行: 【HH:MM:SS — HH:MM:SS】（该段的起止时间，不含毫秒）\n"
        "   - 第二行: 　　段落正文（前缀两个全角空格缩进）\n"
        "   - 段落之间空一行\n"
        "3. 不要遗漏任何字幕内容\n"
        "4. 直接输出排版后的纯文本，不要输出任何解释、标题或额外标记\n\n"
        "**字幕内容**:\n"
        "```\n"
        f"{srt_content}\n"
        "```\n\n"
        "请开始排版。"
    )
    return prompt


def parse_llm_response(response: str) -> Dict[str, Any]:
    """解析 LLM 返回的 JSON 响应

    支持格式:
    1. 纯 JSON: {...}
    2. Markdown代码块: ```json {...} ```
    3. 带前后文字的: ...前文... {...} ...后文...
    """
    if not response or not response.strip():
        raise ValueError("LLM 返回内容为空")

    response = response.strip()

    # 去除 Markdown 代码块
    if response.startswith("```"):
        lines = response.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        response = "\n".join(lines).strip()

    # 提取 JSON 对象
    start_idx = response.find("{")
    end_idx = response.rfind("}")

    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        # 打印前500字符便于调试
        preview = response[:500].replace("\n", " ")
        raise ValueError(f"未找到有效的JSON对象，响应预览: {preview}")

    json_str = response[start_idx:end_idx + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        preview = response[:500].replace("\n", " ")
        raise ValueError(f"JSON解析失败: {e}，响应预览: {preview}")


def validate_analysis_result(result: Dict[str, Any]) -> None:
    """验证分析结果的完整性"""
    required_fields = ["summary", "knowledge_points", "key_screenshots"]
    for field in required_fields:
        if field not in result:
            raise ValueError(f"缺少必需字段: {field}")

    if not isinstance(result["summary"], str) or len(result["summary"]) < 20:
        raise ValueError("摘要长度不足")

    if not isinstance(result["knowledge_points"], list) or len(result["knowledge_points"]) < 3:
        raise ValueError("知识点数量不足(至少需要3个)")

    if not isinstance(result["key_screenshots"], list) or len(result["key_screenshots"]) < 2:
        raise ValueError("关键截图数量不足(至少需要2个)")

    if "keywords" not in result:
        raise ValueError("缺少必需字段: keywords")
    if not isinstance(result["keywords"], list) or len(result["keywords"]) < 3:
        raise ValueError("关键词数量不足(至少需要3个)")
    if "conclusion" not in result:
        raise ValueError("缺少必需字段: conclusion")
    if not isinstance(result["conclusion"], str) or len(result["conclusion"]) < 50:
        raise ValueError("内容总结长度不足")


class BaseAnalyzer(ABC):
    """LLM 分析器基类"""

    @abstractmethod
    def analyze(self, video_info: Dict, srt_content: str) -> Dict[str, Any]:
        """分析字幕内容

        Args:
            video_info: 视频信息
            srt_content: 字幕内容

        Returns:
            Dict: 分析结果
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """分析器名称"""
        ...

    @abstractmethod
    def format_transcript(self, srt_content: str) -> str:
        """对字幕原文进行语义分段排版

        Args:
            srt_content: 原始 SRT 字幕内容

        Returns:
            str: 段落化排版后的纯文本
        """
        ...

    def save_analysis(self, result: Dict[str, Any], output_path: Path) -> None:
        """保存分析结果为 JSON 文件"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"分析结果已保存: {output_path}")
