"""LLM token 消耗统计

每次 LLM API 调用都会返回一个 `usage` 数据类，字段：
- prompt_tokens / completion_tokens / total_tokens
- cached_tokens（智谱 prompt_tokens_details.cached_tokens，缓存命中数）
- duration_seconds / finish_reason / request_id

`TokenTracker` 负责把多次调用累加，用于整个分P（甚至整次运行）的 token 汇总输出。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TokenUsage:
    """单次 LLM 调用的 token 消耗"""
    provider: str            # "zhipu" / "deepseek" / "interactive"
    model: str               # "glm-4.7-flash" / "deepseek-chat"
    step: str                # "analyze" / "format_transcript"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0   # 智谱缓存命中 token 数
    duration_seconds: float = 0.0
    finish_reason: str = "unknown"  # stop / length / content_filter / sensitive / interactive / unknown
    request_id: Optional[str] = None  # 智谱/DeepSeek 响应中的唯一 ID

    def to_log_dict(self) -> Dict:
        """转为可序列化的 dict（用于 logging / JSON 存储）"""
        return {
            "provider": self.provider,
            "model": self.model,
            "step": self.step,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "duration_s": round(self.duration_seconds, 2),
            "finish_reason": self.finish_reason,
            "request_id": self.request_id,
        }


@dataclass
class TokenTracker:
    """多次 LLM 调用的 token 累计器

    用法：
        tracker = TokenTracker()
        usage = TokenUsage(...)
        tracker.add(usage)
        totals = tracker.totals()
    """
    usages: List[TokenUsage] = field(default_factory=list)

    def add(self, usage: TokenUsage) -> None:
        self.usages.append(usage)

    def totals(self) -> Dict:
        """返回 dict 形式的累计数据（用于 pipeline result 存储）"""
        return {
            "prompt": sum(u.prompt_tokens for u in self.usages),
            "completion": sum(u.completion_tokens for u in self.usages),
            "total": sum(u.total_tokens for u in self.usages),
            "cached": sum(u.cached_tokens for u in self.usages),
            "calls": len(self.usages),
        }

    def is_all_interactive(self) -> bool:
        """是否所有调用都是交互式（即没有真实 API 调用）"""
        return len(self.usages) > 0 and all(
            u.provider == "interactive" for u in self.usages
        )

    def is_empty(self) -> bool:
        return len(self.usages) == 0
