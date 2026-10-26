"""Importance Agent — 判断事件重要性，决定目标记忆层。

多因子：novelty, goal_relevance, relationship_weight, risk,
        long_term_value, correction_value。
MVP: goals 为空 → goal_relevance 默认低。

target_memory_layer 允许值：working / episode_candidate / archive。

规则示例：
- risk 高 → importance 上升
- correction_value 高 → importance 上升
- long_term_value 高 → 进入 episode_candidate
- 普通短消息 → working
- 空消息 / 极低价值 → archive

本阶段只判断目标层，不实际写 Memory。
"""
from __future__ import annotations
import re

from soul.agents.base import BaseAgent
from soul.agents.emotion import EmotionAgent


def _strip_punct(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


class ImportanceAgent(BaseAgent):
    """输入: Event + Appraisal + 可选 goals
    输出: dict {importance_score, target_memory_layer, factors, reason}
    """
    name = "importance"

    def process(self, event: object, appraisal: dict, goals: list | None = None) -> dict:
        # 提取文本
        text = ""
        if isinstance(event, dict):
            text = event.get("normalized_content", "")
        elif hasattr(event, "normalized_content"):
            text = event.normalized_content
        else:
            text = str(event)

        vec = appraisal.get("vector", {})
        risk = vec.get("risk", 0.0)
        stress = vec.get("stress", 0.0)
        novelty = vec.get("uncertainty", 0.0)  # MVP 用 uncertainty 近似新奇度
        reward = vec.get("reward", 0.0)

        factors: dict[str, float] = {}
        # novelty 改用"新概念词命中数"驱动（不等同 uncertainty）
        text_no_punct = _strip_punct(text)
        # 中文新概念词 + 英文项目词（英文消息也能触发 episode_candidate）
        novel_hits = sum(
            1 for w in ("新", "全新", "架构", "设计", "方案", "模型", "概念", "首次",
                         # 英文项目关键词：Project Soul 开发阶段/模块命中即算高概念
                         "project soul", "evidence", "memory", "reflection",
                         "belief", "narrative", "self", "phase", "loop")
            if w in text_no_punct
        )
        # 英文全匹配短语计 2 hits（避免只含一个常见词就高估）
        if "projectsoul" in text_no_punct or "evidencestore" in text_no_punct:
            novel_hits += 1
        novelty = min(1.0, 0.2 + 0.25 * novel_hits)
        factors["novelty"] = round(novelty, 3)
        factors["goal_relevance"] = 0.0
        factors["relationship_weight"] = 0.0
        factors["risk"] = round(risk, 3)
        factors["long_term_value"] = round(novelty * 0.6 + len(text.strip()) * 0.005 + reward * 0.3, 3)
        factors["correction_value"] = round(risk * 0.5 + stress * 0.5, 3)

        if not text.strip():
            return {
                "importance_score": 0.0,
                "target_memory_layer": "archive",
                "factors": factors,
                "reason": "empty message; low value -> archive",
            }

        # 多因子加权
        score = (
            factors["novelty"] * 1.2
            + factors["risk"] * 2.0
            + factors["correction_value"] * 1.5
            + factors["long_term_value"] * 1.0
            + factors["goal_relevance"] * 1.0
        )
        # 普通消息给一个基础分，避免全 0 进 archive
        score += 0.15
        score = round(min(1.0, score), 3)

        # 目标层判定
        text_len = len(text.strip())
        # 高长期价值 / 高新奇 → episode_candidate
        if factors["long_term_value"] >= 0.6 or factors["novelty"] >= 0.55:
            layer = "episode_candidate"
            reason = "high long-term value / novelty"
        elif factors["risk"] >= 0.6 or factors["correction_value"] >= 0.6:
            layer = "episode_candidate"
            reason = "risk / correction signal high"
        elif text_len == 0:
            layer = "archive"
            reason = "empty message"
        else:
            layer = "working"
            reason = "normal message"

        return {
            "importance_score": score,
            "target_memory_layer": layer,
            "factors": factors,
            "reason": reason,
        }