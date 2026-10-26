"""Emotion/Appraisal Agent — 对 Event 生成 8 维工程情绪向量。

维度：curiosity, confidence, uncertainty, reward, risk, conflict, stress, familiarity。
每个分数范围 0.0 - 1.0。
注意：emotion 是工程变量，不是拟人化表演。MVP 用规则实现（无模型）。

规则示例：
- 问句 / 含"如何/为什么/怎么" → curiosity 较高
- 含"错误/失败/风险/挂掉/问题" → risk、stress 较高
- 明确确认类消息 → confidence 较高
- 新概念较多 → uncertainty 较高
- 普通消息 → 中性分数

trace 需体现评分原因。
"""
from __future__ import annotations
import re

from soul.agents.base import BaseAgent

EMOTION_DIMS = [
    "curiosity", "confidence", "uncertainty",
    "reward", "risk", "conflict", "stress", "familiarity",
]

# 风险 / 问题触发词
_RISK_WORDS = ["错误", "失败", "风险", "挂掉", "问题", "错误", "异常", "损坏", "error", "fail", "risk", "bug"]
_QUESTION_PAT = re.compile(r"如何|为什么|怎么|怎样|是什么|什么问题|how|why|what|which|who|\?|？")
_CONFIRM_PAT = re.compile(r"确认|开始|执行|可以|好的|继续|会|同意|approve|yes|ok|go ahead|start|confirm")
_NOVEL_WORDS = ["新", "首次", "第一次", "概念", "架构", "设计", "方案", "模型", "agent", "new", "novel", "concept"]


class EmotionAgent(BaseAgent):
    """输入: Event（或 normalized text）
    输出: Appraisal dict — {"vector": {8 维}, "reasons": {dim: [原因]}}
    """
    name = "emotion"

    def process(self, event: object) -> dict:
        text = ""
        if isinstance(event, dict):
            text = event.get("normalized_content", "")
        elif hasattr(event, "normalized_content"):
            text = event.normalized_content
        else:
            text = str(event)
        text_l = text.lower()

        reasons: dict[str, list[str]] = {}

        # curiosity
        curiosity = 0.0
        if _QUESTION_PAT.search(text):
            curiosity = 0.7
            reasons["curiosity"] = ["contains question structure"]
        # confidence（确认类高、稳定默认 .15）
        confidence = 0.15
        if _CONFIRM_PAT.search(text_l):
            confidence = 0.6
            reasons["confidence"] = ["confirmation/acknowledgment"]

        # uncertainty（新概念多则高）
        novel_hits = sum(1 for w in _NOVEL_WORDS if w.lower() in text_l)
        uncertainty = 0.0
        if _QUESTION_PAT.search(text):
            uncertainty += 0.25
            reasons.setdefault("uncertainty", []).append("question implies some uncertainty")
        if novel_hits >= 2:
            uncertainty += 0.4
            reasons.setdefault("uncertainty", []).append("several new concepts")

        # reward（含正面词 default .1，含"完成/成功"升）
        reward = 0.1
        if re.search(r"完成|成功|通过|搞定|done|success|complete|pass", text_l):
            reward = 0.6
            reasons["reward"] = ["completion/success terms"]

        # risk & stress
        risk = 0.0
        stress = 0.0
        risk_hits = sum(1 for w in _RISK_WORDS if w.lower() in text_l)
        if risk_hits:
            risk = min(0.9, 0.4 + 0.2 * risk_hits)
            stress = min(0.85, 0.35 + 0.15 * risk_hits)
            reasons["risk"] = [f"risk terms detected ({risk_hits})"]
            reasons["stress"] = [f"negative/risk terms detected ({risk_hits})"]

        # conflict
        conflict = 0.0
        if risk_hits and ("但是" in text or "but" in text_l or "然而" in text):
            conflict = 0.5
            reasons["conflict"] = ["risk + contrast detected"]

        # familiarity（含"继续/之前/更新"= 已有上下文；默认 .1）
        familiarity = 0.05
        if re.search(r"继续|之前|之前|更新|again|continue|already|previous|update", text_l):
            familiarity = 0.5
            reasons["familiarity"] = ["references prior/continued context"]

        vector = {
            "curiosity": round(min(1.0, curiosity), 3),
            "confidence": round(min(1.0, confidence), 3),
            "uncertainty": round(min(1.0, uncertainty), 3),
            "reward": round(min(1.0, reward), 3),
            "risk": round(min(1.0, risk), 3),
            "conflict": round(min(1.0, conflict), 3),
            "stress": round(min(1.0, stress), 3),
            "familiarity": round(min(1.0, familiarity), 3),
        }
        return {"vector": vector, "reasons": reasons}