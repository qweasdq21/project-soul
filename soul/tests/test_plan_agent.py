"""test_plan_agent.py — Phase 10 PlanningAgent plan + task generation。"""
from soul.agents.planning import PlanningAgent


def _goal(gid="goal-g1", gtype="project_milestone", priority=0.6):
    return {"goal_id": gid, "goal_type": gtype, "status": "active", "priority": priority,
            "title": "Implement the next Project Soul phase", "description": "x",
            "evidence_ids": ["ev-1"], "evidence_ids_json": None, "updated_at": "t"}


def _sm(content, mid="sm1", ev="ev-1"):
    return {"memory_id": mid, "content": content,
            "source_event_ids": [ev], "source_event_ids_json": None}


def _run(gtype="project_milestone"):
    return PlanningAgent().process(goals=[_goal(gtype=gtype)], semantic_mems=[
        {"memory_id": "m1", "content": "phase completed verified", "source_event_ids": ["ev-1"]}],
        goal_progress={"goal-g1": {"progress_id": "gp-1", "progress_value": 0.5,
                                   "progress_status": "in_progress"}})[0]


# ---------- plan 生成 ----------
def test_plan_generates_plan_and_tasks():
    cand = _run()
    assert cand["plan"]["plan_id"].startswith("plan-")
    assert cand["plan"]["goal_id"] == "goal-g1"
    assert cand["plan"]["status"] in ("proposed", "active")
    assert cand["plan"]["plan_type"] in ("implementation", "verification", "safety",
                                         "maintenance", "general")
    assert cand["tasks"]


def test_plan_links_evidence_and_goal():
    cand = _run()
    plan = cand["plan"]
    assert plan["goal_id"] == "goal-g1"
    assert plan["evidence_ids"]  # must cite evidence
    assert "goal-g1" in plan["source_goal_ids"]


def test_plan_type_maps_from_goal_type():
    assert _run(gtype="project_milestone")["plan"]["plan_type"] == "implementation"
    assert _run(gtype="implementation")["plan"]["plan_type"] == "implementation"
    assert _run(gtype="safety")["plan"]["plan_type"] == "safety"
    assert _run(gtype="verification")["plan"]["plan_type"] == "verification"
    assert _run(gtype="maintenance")["plan"]["plan_type"] == "maintenance"


def test_plan_not_auto_completed():
    assert _run()["plan"]["status"] not in ("completed", "completed_candidate")


def test_plan_priority_in_range():
    p = float(_run()["plan"]["priority"])
    assert 0.0 <= p <= 1.0


# ---------- task 生成 ----------
def test_tasks_have_required_fields():
    for t in _run()["tasks"]:
        assert t["task_id"].startswith("task-")
        assert t["goal_id"] == "goal-g1"
        assert t["evidence_ids"]  # must cite evidence
        assert t["execution_mode"] == "manual_only"  # 唯一安全默认
        assert t["status"] in ("proposed", "ready")
        assert t["task_type"] in ("inspect", "implement", "verify", "document",
                                  "review", "maintain", "research", "general")


def test_task_sequential_dependencies():
    tasks = _run()["tasks"]
    for i, t in enumerate(tasks):
        if i > 0:
            assert t["depends_on_task_ids"] == [tasks[i - 1]["task_id"]]
        else:
            assert t["depends_on_task_ids"] == []


def test_safety_goal_tasks_reference_constitution():
    tasks = _run(gtype="safety")["tasks"]
    assert any("Constitution" in t["title"] or "constitution" in t["title"].lower()
               for t in tasks)


def test_task_types_per_goal():
    impl_types = {t["task_type"] for t in _run(gtype="project_milestone")["tasks"]}
    assert "inspect" in impl_types and "implement" in impl_types and "verify" in impl_types

    verify_types = {t["task_type"] for t in _run(gtype="verification")["tasks"]}
    assert "verify" in verify_types and "document" in verify_types

    maint_types = {t["task_type"] for t in _run(gtype="maintenance")["tasks"]}
    assert "inspect" in maint_types and "document" in maint_types


def test_no_evidence_goal_yields_no_plan():
    g = _goal()
    g["evidence_ids"] = []
    cands = PlanningAgent().process(goals=[g])
    assert cands == []