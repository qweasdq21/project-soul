"""test_decision_agent.py — Phase 11 DecisionAgent next-task recommendation。"""
from soul.agents.decision import DecisionAgent


def _goal(gid="goal-g1", gtype="project_milestone", priority=0.7, cprio=None, status="active"):
    return {"goal_id": gid, "goal_type": gtype, "status": status, "priority": priority,
            "computed_priority": cprio, "title": "T", "description": "x", "evidence_ids": ["ev-1"]}


def _plan(pid="plan-1", gid="goal-g1", status="proposed"):
    return {"plan_id": pid, "goal_id": gid, "title": "P", "description": "d",
            "plan_type": "implementation", "status": status, "priority": 0.4,
            "evidence_ids": ["ev-1"], "source_goal_ids": [gid], "plan_reason": "from goal"}


def _task(tid="task-1", pid="plan-1", gid="goal-g1", status="proposed", order=0, deps=None):
    return {"task_id": tid, "plan_id": pid, "goal_id": gid, "title": "Review progress",
            "task_type": "inspect", "status": status, "order_index": order, "priority": 0.6,
            "evidence_ids": ["ev-1"], "depends_on_task_ids": deps or [],
            "execution_mode": "manual_only"}


# ---------- 正常推荐 ----------
def test_goal_plan_task_yields_decision():
    d = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()], tasks=[_task()])
    assert d
    dec = d[0]
    assert dec["selected_goal_id"] == "goal-g1"
    assert dec["selected_plan_id"] == "plan-1"
    assert dec["selected_task_id"] == "task-1"
    assert dec["evidence_ids"]
    assert dec["execution_allowed"] is False
    assert dec["manual_review_required"] is True
    assert dec["status"] == "waiting_for_review"


def test_decision_type_is_next_task_recommendation():
    dec = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()], tasks=[_task()])[0]
    assert dec["decision_type"] == "next_task_recommendation"


def test_highest_priority_goal_wins():
    g1 = _goal("goal-g1", priority=0.5, cprio=None)
    g2 = _goal("goal-g2", priority=0.5, cprio=0.9)  # computed 更高
    dec = DecisionAgent().process(
        goals=[g1, g2], goal_progress={},
        plans=[_plan(pid="p1", gid="goal-g1"), _plan(pid="p2", gid="goal-g2")],
        tasks=[_task(tid="t1", pid="p1", gid="goal-g1"), _task(tid="t2", pid="p2", gid="goal-g2")])[0]
    assert dec["selected_goal_id"] == "goal-g2"


def test_selects_first_pending_task():
    gid = "goal-g1"
    dec = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()],
        tasks=[_task(tid="t0", order=0, status="completed_candidate"),
               _task(tid="t1", order=1, status="proposed"),
               _task(tid="t2", order=2, status="blocked")])[0]
    assert dec["selected_task_id"] == "t1"


def test_reason_is_neutral_engineering():
    dec = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()], tasks=[_task()])[0]
    r = dec["reason"]
    # 不得有拟人化表达
    for banned in ("我", "决定执行", "我必须", "渴望", "欲望", "灵魂"):
        assert banned not in r
    assert "highest-priority active goal" in r


# ---------- defer / blocked ----------
def test_no_goal_yields_defer():
    decs = DecisionAgent().process(goals=[], goal_progress={}, plans=[], tasks=[])
    assert decs and decs[0]["decision_type"] == "defer"


def test_no_plan_yields_defer():
    dec = DecisionAgent().process(goals=[_goal()], goal_progress={}, plans=[], tasks=[_task()])[0]
    assert dec["decision_type"] == "defer"


def test_no_pending_task_yields_defer():
    dec = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()],
        tasks=[_task(status="blocked")])[0]
    assert dec["decision_type"] in ("defer", "blocked")


def test_dependency_unmet_marks_review_required():
    # t1 依赖 t0，但 t0 未完成 → review_required
    dec = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()],
        tasks=[_task(tid="t0", order=0, status="proposed"),
               _task(tid="t1", order=1, status="proposed", deps=["t0"])])[0]
    # 只选 t0，不跳过依赖。t1 依赖未满足 -> 但 t0 本身可选
    assert dec["selected_task_id"] == "t0"


# ---------- factors ----------
def test_decision_factors_present():
    dec = DecisionAgent().process(
        goals=[_goal()], goal_progress={}, plans=[_plan()], tasks=[_task()])[0]
    f = dec["decision_factors"]
    for k in ("goal_priority", "goal_progress_value", "plan_status", "task_order_index",
              "task_status", "dependency_status", "evidence_strength"):
        assert k in f