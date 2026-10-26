"""Soul Feed Layer — Project Soul 感知入口（Phase 15A，GPT 批复）。

目标：把 Project Soul 从「事后记录系统」升级为「事前感知工作流系统」。
本阶段不接真实自动执行，只建立：

    External Work Source → Work Item → Action Candidate → Execution Gate

闭环。

职责边界（安全铁律）：
- 本 agent 只「感知」外部待办源、转成标准 Work Item。
- **不创建 Decision、不创建 Execution Request、不执行任何动作、不修改 goal/plan/task 状态。**
- 执行轨迹交给 Execution Gate 裁决；本文件只负责喂料 + 生成候选。

Design:
- `FeedProvider` 是抽象 connector 接口（real connector 预留位）。
- `MockFeedProvider` 从 JSON fixture 输入产 WorkItem（MVP，不接真实网络）。
- `SoulFeedAgent.ingest()` 调 provider 取原始待办 → 去重 → 落 work_items 表 → 写
  work_item_ingested evidence（每个 WorkItem 可追溯）。
- `ActionCandidateAgent.generate()` 按 work_type 把 new/observed WorkItem 映射成
  ActionCandidate（引用 work_item_id + evidence_ids，不允许凭空创建 action）。
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# 源类型与 work_type → action 映射表（Phase 15A 契约，GPT 原文）
# ---------------------------------------------------------------------------
SUPPORTED_SOURCES = ["feishu_task", "shipping_pending", "customer_email_pending"]

# work_type → (action_name, action_level)
WORK_TYPE_ACTION_MAP: dict[str, tuple[str, str]] = {
    "customer_email_pending": ("draft_reply_email", "L1"),
    "shipping_pending": ("create_shipping_label", "L0"),
    "task_reminder": ("internal_review_task", "L0"),
    # 未知 work_type 默认 internal_review_task（只读复核，永不直接执行外部动作）
}

WORK_ITEM_STATUSES = ("new", "observed", "candidate_created", "processed", "ignored")
CANDIDATE_STATUSES = ("pending_gate", "accepted", "rejected")


# ---------------------------------------------------------------------------
# 1. Feed Provider 抽象（real connector 的预留接口）
# ---------------------------------------------------------------------------
class FeedProvider(ABC):
    """外部待办源 connector 的抽象接口。Phase 15B 接真实手臂时实现它的子类。"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """返回源标识，如 feishu_task / shipping_pending / customer_email_pending。"""

    @abstractmethod
    def fetch_raw_items(self, **kw: Any) -> list[dict[str, Any]]:
        """拉取原始待办（dict 列表）。字段由各 provider 自行定义，SoulFeedAgent 归一化。"""


class MockFeedProvider(FeedProvider):
    """MVP：从 JSON fixture 输入产出原始待办（不接网络，测试/演示用）。

    输入是外部待办列表，每项须含 source_id / work_type / title（等），
    缺省字段由 fetch 归一化补上。这是 Phase 15A 的「第一真实源」占位。
    """

    def __init__(self, source: str = "feishu_task", fixtures: list[dict[str, Any]] | None = None):
        if source not in SUPPORTED_SOURCES:
            raise ValueError(f"unsupported source: {source}")
        self._source = source
        self._fixtures = fixtures or []

    @property
    def source_name(self) -> str:
        return self._source

    def load_fixture_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", data) if isinstance(data, dict) else data
        self._fixtures = items or []

    def fetch_raw_items(self, **kw: Any) -> list[dict[str, Any]]:
        return list(self._fixtures)


# ---------------------------------------------------------------------------
# 2. Soul Feed Agent
# ---------------------------------------------------------------------------
class SoulFeedAgent:
    """把外部待办源转成标准 Work Item，写 evidence。不执行任何动作。"""

    def __init__(
        self,
        sqlite: Any,
        evidence: Any | None = None,
        provider: FeedProvider | None = None,
    ):
        self.sqlite = sqlite
        self.evidence = evidence
        self.provider = provider or MockFeedProvider()

    # ---- evidence helper（每个 WorkItem 必须可追溯）----
    def _write_work_item_evidence(self, wi: dict[str, Any]) -> str:
        """写一条 work_item_ingested evidence，返回 event_id。"""
        if self.evidence is None:
            return ""
        ev = self.evidence.compute_and_append({
            "event_id": _uid("event"),
            "event_type": "work_item_ingested",
            "source": "soul_feed",
            "actor": "soul_feed",
            "content": "",
            "raw_content": json.dumps({
                "source": wi.get("source"),
                "source_id": wi.get("source_id"),
                "work_type": wi.get("work_type"),
                "title": wi.get("title"),
            }, ensure_ascii=False),
            "metadata": {
                "source": wi.get("source"),
                "source_id": wi.get("source_id"),
                "work_item_id": wi.get("work_item_id"),
                "work_type": wi.get("work_type"),
                "created_at": _utc_now(),
            },
        })
        return ev["event_id"]

    def ingest(self, raw_items: list[dict[str, Any]] | None = None,
               *, dedupe: bool = True) -> dict[str, Any]:
        """拉取 provider 原始待办 → 去重 → 落 work_items → 写 evidence。

        返回 {ingested, skipped, items}。
        """
        items = list(raw_items) if raw_items is not None else self.provider.fetch_raw_items()
        # 已存在的 source_id 跳过（同源同名不重复摄入）
        existing = set()
        if dedupe:
            for wi in self.sqlite.list_work_items(limit=100000) or []:
                if wi.get("source_id"):
                    existing.add((wi.get("source"), wi.get("source_id")))

        ingested: list[dict[str, Any]] = []
        skipped = 0
        for raw in items:
            source_id = str(raw.get("source_id") or raw.get("id") or _uid("raw"))
            if dedupe and (self.provider.source_name, source_id) in existing:
                skipped += 1
                continue
            wi = self._normalize(raw, source_id)
            self.sqlite.add_work_item(wi)
            eid = self._write_work_item_evidence(wi)
            if eid:
                wi["evidence_ids"] = wi.get("evidence_ids", []) + [eid]
            ingested.append(wi)
        return {"ingested": len(ingested), "skipped": skipped, "items": ingested}

    def _normalize(self, raw: dict[str, Any], source_id: str) -> dict[str, Any]:
        return {
            "work_item_id": _uid("wi"),
            "source": self.provider.source_name,
            "source_id": source_id,
            "work_type": raw.get("work_type") or self._infer_work_type(raw),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "priority_hint": raw.get("priority_hint", ""),
            "related_goal_ids": raw.get("related_goal_ids", []),
            "related_plan_ids": raw.get("related_plan_ids", []),
            "evidence_ids": [],
            "status": "new",
            "created_at": _utc_now(),
        }

    @staticmethod
    def _infer_work_type(raw: dict[str, Any]) -> str:
        # 从语义字段推断 work_type；无法推断归 task_reminder（只读复核）
        if raw.get("kind") in ("email", "customer_email"):
            return "customer_email_pending"
        if raw.get("kind") in ("shipping", "shipment"):
            return "shipping_pending"
        return "task_reminder"


# ---------------------------------------------------------------------------
# 3. ActionCandidateAgent
# ---------------------------------------------------------------------------
class ActionCandidateAgent:
    """按 work_type 把 new/observed WorkItem 映射成 ActionCandidate（引用 work_item + evidence）。"""

    def __init__(self, sqlite: Any):
        self.sqlite = sqlite

    def generate_for(self, work_item: dict[str, Any]) -> dict[str, Any] | None:
        """为一个 work_item 生成 action_candidate。已 candidate_created 的跳过。

        返回 candidate dict（已落库）或 None（已生成过 / 无映射）。
        """
        if not work_item:
            return None
        if work_item.get("status") in ("processed", "ignored", "candidate_created"):
            return None
        wtype = work_item.get("work_type") or "task_reminder"
        action_name, action_level = WORK_TYPE_ACTION_MAP.get(
            wtype, WORK_TYPE_ACTION_MAP["task_reminder"])
        # 候选必引用 work_item_id + evidence_ids（不允许凭空创建 action）
        cand = {
            "candidate_id": _uid("cand"),
            "work_item_id": work_item["work_item_id"],
            "action_name": action_name,
            "action_level": action_level,
            "payload": {
                "work_item_id": work_item["work_item_id"],
                "source": work_item.get("source"),
                "source_id": work_item.get("source_id"),
                "title": work_item.get("title"),
                "work_type": wtype,
            },
            "risk_factors": {"source": "soul_feed", "level": action_level},
            "evidence_ids": work_item.get("evidence_ids", []),
            "source": work_item.get("source"),
            "status": "pending_gate",
            "created_at": _utc_now(),
        }
        # 标记 work_item 为 candidate_created（幂等）
        self.sqlite.add_action_candidate(cand)
        self.sqlite.update_work_item_status(work_item["work_item_id"], "candidate_created")
        return cand

    def generate_all(self) -> dict[str, Any]:
        """扫描所有 new/observed work_item，批量建候选。返回 {generated, skipped}。"""
        generated: list[dict[str, Any]] = []
        skipped = 0
        for wi in self.sqlite.list_work_items(limit=100000) or []:
            if wi.get("status") in ("processed", "ignored", "candidate_created"):
                skipped += 1
                continue
            cand = self.generate_for(wi)
            if cand:
                generated.append(cand)
            else:
                skipped += 1
        return {"generated": len(generated), "skipped": skipped, "items": generated}