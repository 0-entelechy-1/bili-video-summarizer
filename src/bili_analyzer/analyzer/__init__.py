"""分析器工厂

根据配置选择 LLM 提供商，API 失败时降级。
"""

from typing import Any, Dict, List

from bili_analyzer.analyzer.base import BaseAnalyzer
from bili_analyzer.config import AppConfig


def create_analyzer(config: AppConfig) -> BaseAnalyzer:
    """根据配置创建分析器

    Args:
        config: 应用配置

    Returns:
        BaseAnalyzer: 分析器实例

    Raises:
        ValueError: 配置的提供商不可用
    """
    provider = config.llm.provider

    if provider == "zhipu":
        api_key = config.llm.zhipu.api_key
        if not api_key:
            raise ValueError("未配置 ZHIPU_API_KEY")
        from bili_analyzer.analyzer.zhipu import ZhipuAnalyzer
        return ZhipuAnalyzer(
            api_key=api_key,
            model=config.llm.zhipu.model,
            max_tokens=config.llm.zhipu.max_tokens,
            thinking_enabled=config.llm.zhipu.thinking_enabled,
        )

    if provider == "deepseek":
        api_key = config.llm.deepseek.api_key
        if not api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY")
        from bili_analyzer.analyzer.deepseek import DeepseekAnalyzer
        return DeepseekAnalyzer(
            api_key=api_key,
            base_url=config.llm.deepseek.base_url,
            model=config.llm.deepseek.model,
        )

    if provider == "interactive":
        from bili_analyzer.analyzer.interactive import InteractiveAnalyzer
        return InteractiveAnalyzer()

    raise ValueError(f"未知的 LLM 提供商: {provider}")


def get_analyzer_chain(config: AppConfig) -> List[BaseAnalyzer]:
    """获取分析器降级链

    按优先级返回分析器列表，第一个失败则尝试下一个。
    最终降级为交互式模式。

    Returns:
        List[BaseAnalyzer]: 分析器列表
    """
    chain = []
    provider = config.llm.provider

    # 首选提供商
    if provider == "zhipu" and config.llm.zhipu.api_key:
        from bili_analyzer.analyzer.zhipu import ZhipuAnalyzer
        chain.append(ZhipuAnalyzer(
            api_key=config.llm.zhipu.api_key,
            model=config.llm.zhipu.model,
            max_tokens=config.llm.zhipu.max_tokens,
            thinking_enabled=config.llm.zhipu.thinking_enabled,
        ))
    elif provider == "deepseek" and config.llm.deepseek.api_key:
        from bili_analyzer.analyzer.deepseek import DeepseekAnalyzer
        chain.append(DeepseekAnalyzer(
            api_key=config.llm.deepseek.api_key,
            base_url=config.llm.deepseek.base_url,
            model=config.llm.deepseek.model,
        ))

    # 降级：如果首选不是另一个 API 提供商，尝试另一个
    if provider != "deepseek" and config.llm.deepseek.api_key:
        from bili_analyzer.analyzer.deepseek import DeepseekAnalyzer
        chain.append(DeepseekAnalyzer(
            api_key=config.llm.deepseek.api_key,
            base_url=config.llm.deepseek.base_url,
            model=config.llm.deepseek.model,
        ))

    if provider != "zhipu" and config.llm.zhipu.api_key:
        from bili_analyzer.analyzer.zhipu import ZhipuAnalyzer
        chain.append(ZhipuAnalyzer(
            api_key=config.llm.zhipu.api_key,
            model=config.llm.zhipu.model,
            max_tokens=config.llm.zhipu.max_tokens,
            thinking_enabled=config.llm.zhipu.thinking_enabled,
        ))

    # 最终降级为交互式
    from bili_analyzer.analyzer.interactive import InteractiveAnalyzer
    chain.append(InteractiveAnalyzer())

    return chain
